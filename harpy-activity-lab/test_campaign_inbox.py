"""Inbox relay tests with a fake Discord gateway."""

import asyncio
import sqlite3
from types import SimpleNamespace

import discord
import pytest

import campaign_inbox
from campaign_inbox import InboxNotices, deliver_one, pending_interactions, send_notice

CAMPAIGN = "9af87500-1f24-4ebd-98cf-8753e97806c5"
FIRST = "333333333333333333"
SECOND = "444444444444444444"
ROLE = 12345


def test_queue_uses_authoritative_recipient_and_deduplicates(tmp_path, monkeypatch):
    clock = [1000]
    monkeypatch.setattr(campaign_inbox, "time", lambda: clock[0])
    path = tmp_path / "inbox.sqlite3"
    notices = InboxNotices(path)
    receipt = {"id": "bond-a", "target": FIRST}
    setup = SimpleNamespace(
        store=SimpleNamespace(campaign_id=CAMPAIGN),
        bonds=SimpleNamespace(get=lambda *_: {
            "id": "bond-a", "target_id": SECOND, "state": "pending",
            "stale": False, "context": "private starting prompt",
        }),
    )
    notices.bond(setup, FIRST, receipt)
    notices.bond(setup, FIRST, receipt)
    item = notices.claim()
    assert item == (CAMPAIGN, "bond", "bond-a", SECOND)
    assert notices.claim() is None

    reopened = InboxNotices(path)
    clock[0] += 30
    assert reopened.claim() == item
    reopened.finish(item, "sent")
    reopened.bond(setup, FIRST, receipt)
    assert reopened.claim() is None
    assert b"private starting prompt" not in path.read_bytes()

    service = SimpleNamespace(
        store=setup.store,
        get=lambda *_: {"mission": {
            "id": "mission-a", "phase": "offered", "offered_to": [int(FIRST), int(SECOND)],
            "responses": {FIRST: "accept"}, "objective": "restricted mission objective",
        }},
    )
    reopened.mission(service, object(), {"id": "mission-a"})
    assert reopened.claim() == (CAMPAIGN, "mission", "mission-a", SECOND)
    assert b"restricted mission objective" not in path.read_bytes()


def test_delivery_rechecks_role_and_reuses_discord_nonce():
    calls = []
    recipients = []
    member = SimpleNamespace(bot=False, pending=False, get_role=lambda role: role == ROLE)

    async def send(message, **options):
        calls.append((message, options))

    member.send = send

    async def fetch_member(user):
        recipients.append(user)
        return member

    registry = SimpleNamespace(bindings=lambda *_: [SimpleNamespace(id=CAMPAIGN, role_id=str(ROLE))])
    bot = SimpleNamespace(
        activity_id=111, target=SimpleNamespace(id=222),
        get_guild=lambda _: SimpleNamespace(fetch_member=fetch_member),
    )
    item = CAMPAIGN, "bond", "bond-a", SECOND
    pending = lambda *_: True
    asyncio.run(send_notice(bot, registry, item, pending))
    asyncio.run(send_notice(bot, registry, item, pending))
    assert recipients == [int(SECOND), int(SECOND)]
    assert len(calls) == 2
    assert calls[0][0] == "A pilot filed a starting Bond proposal for your response. Open HarpyEngine and check your Inbox."
    assert calls[0][1]["allowed_mentions"].to_dict() == {"parse": []}
    assert calls[0][1]["nonce"] == calls[1][1]["nonce"]
    asyncio.run(send_notice(bot, registry, item, lambda *_: False))
    member.get_role = lambda _: None
    asyncio.run(send_notice(bot, registry, item, pending))
    assert len(calls) == 2


def test_new_assignments_are_observed_once_without_an_old_mail_burst(tmp_path):
    notices = InboxNotices(tmp_path / "notices.sqlite3")
    baseline = ("play", "existing:1", FIRST)
    notices.sync(CAMPAIGN, [baseline])
    assert notices.claim() is None
    new = ("play", "new:1", SECOND)
    invites = {"id": "new-invitation", "recipient": SECOND}
    setup = SimpleNamespace(store=SimpleNamespace(campaign_id=CAMPAIGN))
    notices.scene_invite(setup, FIRST, invites)
    item = notices.claim()
    assert item == (CAMPAIGN, "scene_invite", "new-invitation", SECOND)
    notices.finish(item, "sent")
    reopened = InboxNotices(notices.path)
    reopened.sync(CAMPAIGN, [baseline, new])
    item = reopened.claim()
    assert item == (CAMPAIGN, *new)
    reopened.finish(item, "sent")
    reopened.sync(CAMPAIGN, [baseline, new])
    assert not reopened.claim()


def test_projection_excludes_observers_and_optional_actions():
    def view(result):
        return SimpleNamespace(view=lambda *_: result)

    setup = SimpleNamespace(
        handler=object(),
        game=SimpleNamespace(choices=lambda _: [{"id": "real-choice", "revision": 3}]),
        bonds=SimpleNamespace(list=lambda _: []),
        enrollment_choices=view({"requests": [
            {"id": "incoming", "incoming": True, "state": "pending"},
            {"id": "outgoing", "incoming": False, "state": "pending"},
        ]}),
        owned_followups=view([{"id": "work-owned", "action": "resolve"}, {"id": "read-only"}]),
        handler_punishments=view([]),
        beneath_work=view([{"id": "work-owned", "action": "resolve"}]),
        off_duty=view({
            "period": "off-duty",
            "closing": {"handler": True, "status_ready": True},
            "invitations": [{"confirmed": False, "owner": FIRST}],
        }),
    )
    missions = SimpleNamespace(
        list=lambda _: [],
        owned_work=lambda _: [
            {"id": "work-owned", "state": "pending", "owner_id": SECOND, "revision": 2},
            {"id": "work-other", "state": "pending", "owner_id": FIRST, "revision": 1},
        ],
    )
    arena = view({"encounter": {"can_end_turn": True, "turn": "epoch:4"}})
    assert pending_interactions(setup, missions, arena, SimpleNamespace(user_id=int(SECOND))) == {
        ("play", "real-choice:3"),
        ("play_work", "work-owned:2"),
        ("enrollment", "incoming"),
        ("off_duty", f"off-duty:scene:{FIRST}"),
        ("off_duty", "off-duty:status"),
        ("battlefield", "epoch:4"),
    }


@pytest.mark.parametrize("failure, outcome", [
    (None, "sent"), ("closed", "unavailable"), ("timeout", "unconfirmed"), ("closed-action", "skipped"),
])
def test_sender_receipt_reports_only_confirmed_dm_outcomes(tmp_path, monkeypatch, failure, outcome):
    clock = [1000]
    monkeypatch.setattr(campaign_inbox, "time", lambda: clock[0])
    path = tmp_path / "outbox.sqlite3"
    outbox = InboxNotices(path)
    outbox.file(CAMPAIGN, "scene_invite", "scene-a", [SECOND])
    proof = outbox.sender_receipt(CAMPAIGN, FIRST, "scene_invite", "scene-a")
    assert outbox.sender_receipt(CAMPAIGN, FIRST, "scene_invite", "scene-a") == proof
    assert outbox.read_receipt(CAMPAIGN, FIRST, proof) == [(SECOND, "queued")]
    assert not outbox.read_receipt(CAMPAIGN, SECOND, proof)
    assert not outbox.read_receipt("other-campaign", FIRST, proof)

    async def send(*_, **__):
        assert outbox.read_receipt(CAMPAIGN, FIRST, proof) == [(SECOND, "queued")]
        assert failure != "closed-action"
        if failure == "closed":
            raise discord.Forbidden(SimpleNamespace(status=403, reason="Forbidden"), "Closed DMs")
        if failure == "timeout":
            raise TimeoutError

    member = SimpleNamespace(bot=False, pending=False, get_role=lambda _: ROLE, send=send)

    async def fetch_member(user):
        assert user == int(SECOND)
        return member

    registry = SimpleNamespace(bindings=lambda *_: [SimpleNamespace(id=CAMPAIGN, role_id=str(ROLE))])
    bot = SimpleNamespace(
        activity_id=111, target=SimpleNamespace(id=222),
        get_guild=lambda _: SimpleNamespace(fetch_member=fetch_member),
    )
    item = outbox.claim()
    if failure == "timeout":
        with pytest.raises(TimeoutError):
            asyncio.run(deliver_one(bot, registry, outbox, lambda *_: True, item))
        assert outbox.read_receipt(CAMPAIGN, FIRST, proof) == [(SECOND, "queued")]
        clock[0] += 121
    else:
        asyncio.run(deliver_one(bot, registry, outbox, lambda *_: failure != "closed-action", item))
    assert InboxNotices(path).read_receipt(CAMPAIGN, FIRST, proof) == [(SECOND, outcome)]


def test_legacy_finished_notice_is_not_reported_as_a_confirmed_send(tmp_path):
    path = tmp_path / "old.sqlite3"
    with sqlite3.connect(path) as db:
        db.execute("""CREATE TABLE notices (
            campaign TEXT NOT NULL, kind TEXT NOT NULL, record TEXT NOT NULL,
            recipient TEXT NOT NULL, created REAL NOT NULL, next_attempt REAL NOT NULL,
            finished INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (campaign, kind, record, recipient)
        )""")
        db.execute("INSERT INTO notices VALUES (?, 'bond', 'bond-a', ?, 1, 1, 1)", (CAMPAIGN, SECOND))
    outbox = InboxNotices(path)
    proof = outbox.sender_receipt(CAMPAIGN, FIRST, "bond", "bond-a")
    assert outbox.read_receipt(CAMPAIGN, FIRST, proof) == [(SECOND, "unconfirmed")]
