"""Inbox relay tests with a fake Discord gateway."""

import asyncio
import sqlite3
from types import SimpleNamespace

import campaign_inbox
import discord
import pytest
from campaign_inbox import (
    NOTICES,
    InboxNotices,
    SentDM,
    deliver_one,
    pending_interactions,
    retire_one,
    send_notice,
)
from test_ledger import OTHER, PLAYER, seed
from test_ledger import ledger as ledger

from girlframe.engine.bonds import BondProposal
from girlframe.services.bonds import BondService
from girlframe.services.onboarding import WorkflowError

CAMPAIGN = "9af87500-1f24-4ebd-98cf-8753e97806c5"
FIRST = "333333333333333333"
SECOND = "444444444444444444"
ROLE = 12345
DM = SentDM("555555555555555555", "666666666666666666")


def sent_message():
    return SimpleNamespace(channel=SimpleNamespace(id=int(DM.channel)), id=int(DM.message))


def test_queue_uses_authoritative_recipient_and_deduplicates(tmp_path, monkeypatch):
    clock = [1000]
    monkeypatch.setattr(campaign_inbox, "time", lambda: clock[0])
    path = tmp_path / "inbox.sqlite3"
    notices = InboxNotices(path)
    receipt = {"id": "bond-a", "target": FIRST}
    setup = SimpleNamespace(
        store=SimpleNamespace(campaign_id=CAMPAIGN),
        bonds=SimpleNamespace(
            get=lambda *_: {
                "id": "bond-a",
                "target_id": SECOND,
                "state": "pending",
                "stale": False,
                "context": "private starting prompt",
            }
        ),
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
        get=lambda *_: {
            "mission": {
                "id": "mission-a",
                "phase": "offered",
                "offered_to": [int(FIRST), int(SECOND)],
                "responses": {FIRST: "accept"},
                "objective": "restricted mission objective",
            }
        },
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
        return sent_message()

    member.send = send

    async def fetch_member(user):
        recipients.append(user)
        return member

    registry = SimpleNamespace(
        bindings=lambda *_: [SimpleNamespace(id=CAMPAIGN, role_id=str(ROLE))]
    )
    bot = SimpleNamespace(
        activity_id=111,
        target=SimpleNamespace(id=222),
        get_guild=lambda _: SimpleNamespace(fetch_member=fetch_member),
    )
    item = CAMPAIGN, "bond", "bond-a", SECOND

    def pending(*_):
        return True

    asyncio.run(send_notice(bot, registry, item, pending))
    asyncio.run(send_notice(bot, registry, item, pending))
    assert recipients == [int(SECOND), int(SECOND)]
    assert len(calls) == 2
    assert calls[0][0] == (
        "A pilot filed a starting Bond proposal for your response. Open HarpyEngine and "
        "check your Inbox."
    )
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
        enrollment_choices=view(
            {
                "requests": [
                    {"id": "incoming", "incoming": True, "state": "pending"},
                    {"id": "outgoing", "incoming": False, "state": "pending"},
                ]
            }
        ),
        owned_followups=view([{"id": "work-owned", "action": "resolve"}, {"id": "read-only"}]),
        handler_punishments=view([]),
        beneath_work=view([{"id": "work-owned", "action": "resolve"}]),
        off_duty=view(
            {
                "period": "off-duty",
                "closing": {"handler": True, "status_ready": True},
                "invitations": [{"confirmed": False, "owner": FIRST}],
            }
        ),
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


@pytest.mark.parametrize(
    "failure, outcome",
    [
        (None, "sent"),
        ("closed", "unavailable"),
        ("timeout", "unconfirmed"),
        ("closed-action", "skipped"),
        ("unknown-action", "sent"),
    ],
)
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
        return sent_message()

    member = SimpleNamespace(bot=False, pending=False, get_role=lambda _: ROLE, send=send)

    async def fetch_member(user):
        assert user == int(SECOND)
        return member

    registry = SimpleNamespace(
        bindings=lambda *_: [SimpleNamespace(id=CAMPAIGN, role_id=str(ROLE))]
    )
    bot = SimpleNamespace(
        activity_id=111,
        target=SimpleNamespace(id=222),
        get_guild=lambda _: SimpleNamespace(fetch_member=fetch_member),
    )
    item = outbox.claim()
    if failure == "timeout":
        with pytest.raises(TimeoutError):
            asyncio.run(deliver_one(bot, registry, outbox, lambda *_: True, item))
        assert outbox.read_receipt(CAMPAIGN, FIRST, proof) == [(SECOND, "queued")]
        clock[0] += 121
    elif failure == "unknown-action":
        asyncio.run(deliver_one(bot, registry, outbox, lambda *_: None, item))
        assert outbox.read_receipt(CAMPAIGN, FIRST, proof) == [(SECOND, "queued")]
        clock[0] += 30
        assert outbox.claim() == item
        asyncio.run(deliver_one(bot, registry, outbox, lambda *_: True, item))
    else:
        asyncio.run(deliver_one(bot, registry, outbox, lambda *_: failure != "closed-action", item))
    reopened = InboxNotices(path)
    assert reopened.read_receipt(CAMPAIGN, FIRST, proof) == [(SECOND, outcome)]
    assert reopened.claim_cleanup() == ((item, DM) if outcome == "sent" else None)


def cleanup_bot(campaign, calls, failure=None):
    registry = SimpleNamespace(bindings=lambda *_: [SimpleNamespace(id=str(campaign))])

    def channel(channel_id, *, type):
        assert type is discord.ChannelType.private

        def message(message_id):
            async def delete():
                calls.append((channel_id, message_id))
                if failure == "missing":
                    raise discord.NotFound(SimpleNamespace(status=404, reason="Missing"), "")
                if failure == "forbidden":
                    raise discord.Forbidden(SimpleNamespace(status=403, reason="Forbidden"), "")
                if failure == "timeout":
                    raise TimeoutError

            return SimpleNamespace(delete=delete)

        return SimpleNamespace(get_partial_message=message)

    bot = SimpleNamespace(
        activity_id=111, target=SimpleNamespace(id=222), get_partial_messageable=channel
    )
    return bot, registry


@pytest.mark.parametrize("kind", list(NOTICES))
def test_cleanup_uses_only_the_exact_sent_reminder_after_reopening(tmp_path, monkeypatch, kind):
    clock = [1000]
    monkeypatch.setattr(campaign_inbox, "time", lambda: clock[0])
    path = tmp_path / "inbox.sqlite3"
    notices = InboxNotices(path)
    notices.file(CAMPAIGN, kind, "record", [SECOND])
    item = notices.claim()
    notices.finish(item, "sent", DM)
    receipt = notices.sender_receipt(CAMPAIGN, FIRST, kind, "record")
    notices = InboxNotices(path)
    calls = []
    bot, registry = cleanup_bot(CAMPAIGN, calls)

    for pending in (True, None, False):
        claim = notices.claim_cleanup()
        assert claim == (item, DM)
        asyncio.run(retire_one(bot, registry, notices, lambda *_, pending=pending: pending, *claim))
        if pending is not False:
            assert calls == []
        clock[0] += campaign_inbox.CLEANUP_INTERVAL

    assert calls == [(int(DM.channel), int(DM.message))]
    assert not InboxNotices(path).claim_cleanup()
    assert notices.read_receipt(CAMPAIGN, FIRST, receipt) == [(SECOND, "sent")]


@pytest.mark.parametrize("failure", ("missing", "timeout", "forbidden"))
def test_cleanup_handles_discord_deletion_failures(tmp_path, monkeypatch, failure):
    clock = [1000]
    monkeypatch.setattr(campaign_inbox, "time", lambda: clock[0])
    notices = InboxNotices(tmp_path / "inbox.sqlite3")
    notices.file(CAMPAIGN, "bond", "bond-a", [SECOND])
    notices.finish(notices.claim(), "sent", DM)
    calls = []
    bot, registry = cleanup_bot(CAMPAIGN, calls, failure)
    claim = notices.claim_cleanup()
    if failure == "timeout":
        with pytest.raises(TimeoutError):
            asyncio.run(retire_one(bot, registry, notices, lambda *_: False, *claim))
    else:
        asyncio.run(retire_one(bot, registry, notices, lambda *_: False, *claim))
    assert notices.claim_cleanup() is None
    clock[0] += campaign_inbox.CLEANUP_INTERVAL
    assert notices.claim_cleanup() == (claim if failure == "timeout" else None)


def test_cleanup_waits_for_a_readable_campaign_binding(tmp_path):
    notices = InboxNotices(tmp_path / "inbox.sqlite3")
    notices.file(CAMPAIGN, "bond", "bond-a", [SECOND])
    notices.finish(notices.claim(), "sent", DM)
    calls = []
    bot, registry = cleanup_bot(CAMPAIGN, calls)
    registry.bindings = lambda *_: []

    def pending(*_):
        pytest.fail("Cannot read an assignment without its campaign binding.")

    asyncio.run(retire_one(bot, registry, notices, pending, *notices.claim_cleanup()))
    assert calls == []


def test_countersigning_the_native_bond_clears_its_reminder_only(ledger, monkeypatch, tmp_path):
    clock = [1000]
    monkeypatch.setattr(campaign_inbox, "time", lambda: clock[0])
    seed(ledger, PLAYER, "TEST SUBJECT")
    seed(ledger, OTHER, "TEST COUNTERPART")
    bonds = BondService(ledger)
    proposal = bonds.propose(
        PLAYER,
        "file-native-bond",
        1,
        1,
        BondProposal(target_id=OTHER.user_id, prompt=0, context="PRIVATE PROMPT"),
    )
    notices = InboxNotices(tmp_path / "inbox.sqlite3")
    setup = SimpleNamespace(store=ledger, bonds=bonds)
    notices.bond(setup, PLAYER, proposal)
    notices.finish(notices.claim(), "sent", DM)
    other_dm = SentDM(DM.channel, "999999999999999999")
    notices.file(ledger.campaign_id, "mission", "still-pending", [OTHER.user_id])
    notices.finish(notices.claim(), "sent", other_dm)
    calls = []
    bot, registry = cleanup_bot(ledger.campaign_id, calls)

    def pending(_binding, item):
        _, kind, identity, recipient = item
        assert recipient == str(OTHER.user_id)
        key = kind, identity
        if kind == "mission":
            return True
        return key in pending_interactions(setup, None, None, OTHER, lookup=key)

    async def sweep():
        while claim := notices.claim_cleanup():
            await retire_one(bot, registry, notices, pending, *claim)

    asyncio.run(sweep())
    assert not calls
    bonds.decide(OTHER, "countersign-native-bond", proposal["id"], 1, "accept")
    ledger.engine.dispose()
    clock[0] += campaign_inbox.CLEANUP_INTERVAL
    asyncio.run(sweep())
    assert calls == [(int(DM.channel), int(DM.message))]
    assert bonds.get(OTHER, proposal["id"])["state"] == "accepted"
    assert b"PRIVATE PROMPT" not in notices.path.read_bytes()


def test_cleanup_rechecks_owned_invites_missions_and_choices_individually():
    viewer = SimpleNamespace(user_id=int(SECOND))
    invites = [{"id": "invitation"}]
    missions = [{"id": "offer", "needs_response": True}]
    choices = [{"id": "choice", "revision": 1}]
    setup = SimpleNamespace(
        records=SimpleNamespace(scene_invites=lambda _: invites),
        game=SimpleNamespace(choices=lambda _: choices),
    )
    desk = SimpleNamespace(list=lambda _: missions)

    def is_pending(kind, identity):
        key = kind, identity
        return key in pending_interactions(setup, desk, None, viewer, lookup=key)

    assert is_pending("scene_invite", "invitation")
    assert is_pending("mission", "offer")
    assert is_pending("play", "choice:1")
    invites.clear()
    missions[0]["needs_response"] = False
    choices[0]["revision"] = 2
    assert not is_pending("scene_invite", "invitation")
    assert not is_pending("mission", "offer")
    assert not is_pending("play", "choice:1")
    assert is_pending("play", "choice:2")


def test_cleanup_keeps_the_current_turn_during_a_temporary_battlefield_lock():
    viewer = SimpleNamespace(user_id=int(SECOND))
    encounter = {"turn": "epoch:4", "yours": True, "can_end_turn": False}
    arena = SimpleNamespace(view=lambda _: {"encounter": encounter})
    key = "battlefield", "epoch:4"
    assert key in pending_interactions(None, None, arena, viewer, lookup=key)
    encounter["turn"] = "epoch:5"
    assert key not in pending_interactions(None, None, arena, viewer, lookup=key)


def test_cleanup_keeps_known_work_and_defers_when_a_projection_is_unavailable():
    viewer = SimpleNamespace(user_id=int(SECOND))

    def unavailable(_):
        raise WorkflowError("The projection is temporarily unavailable.")

    followup = {"id": "card", "action": "confirm", "work_revision": 1}
    setup = SimpleNamespace(
        owned_followups=SimpleNamespace(view=unavailable),
        handler_punishments=SimpleNamespace(view=lambda _: [followup]),
        beneath_work=SimpleNamespace(view=lambda _: []),
    )
    missions = SimpleNamespace(owned_work=lambda _: [])
    key = "play_work", "card:confirm:1"
    assert key in pending_interactions(setup, missions, None, viewer, lookup=key)
    with pytest.raises(WorkflowError, match="temporarily unavailable"):
        pending_interactions(setup, missions, None, viewer, lookup=("play_work", "other"))


def test_cleanup_retires_off_duty_recovery_while_the_group_period_continues():
    viewer = SimpleNamespace(user_id=int(SECOND))
    period = {"period": "period-a", "reason": "Another assignment is blocking recovery."}
    off_duty = SimpleNamespace(
        view=lambda _: period,
        periods=SimpleNamespace(current=lambda _: {"id": "period-a", "phase": "active"}),
    )
    setup = SimpleNamespace(off_duty=off_duty)
    key = "off_duty", "period-a:recovery"
    assert key in pending_interactions(setup, None, None, viewer, lookup=key)
    period["recovered"] = True
    assert key not in pending_interactions(setup, None, None, viewer, lookup=key)
    period.clear()
    assert key not in pending_interactions(setup, None, None, viewer, lookup=key)


def test_legacy_finished_notice_is_not_reported_as_a_confirmed_send(tmp_path):
    path = tmp_path / "old.sqlite3"
    with sqlite3.connect(path) as db:
        db.execute("""CREATE TABLE notices (
            campaign TEXT NOT NULL, kind TEXT NOT NULL, record TEXT NOT NULL,
            recipient TEXT NOT NULL, created REAL NOT NULL, next_attempt REAL NOT NULL,
            finished INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (campaign, kind, record, recipient)
        )""")
        db.execute(
            "INSERT INTO notices VALUES (?, 'bond', 'bond-a', ?, 1, 1, 1)", (CAMPAIGN, SECOND)
        )
    outbox = InboxNotices(path)
    proof = outbox.sender_receipt(CAMPAIGN, FIRST, "bond", "bond-a")
    assert outbox.read_receipt(CAMPAIGN, FIRST, proof) == [(SECOND, "unconfirmed")]
    assert outbox.claim_cleanup() is None
    outbox.file(CAMPAIGN, "bond", "bond-b", (SECOND,))
    outbox.finish(outbox.claim(), "sent")
    assert outbox.claim_cleanup() is None
