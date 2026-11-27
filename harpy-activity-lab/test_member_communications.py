"""Campaign-member communications, bounded provider retries and explicit bot appointment."""

import io
import json
from http import HTTPStatus
from urllib.error import HTTPError
from uuid import UUID

import activity_records
import discord_session as oauth
import pytest
from activity_records import ActivityRecords
from campaign_inbox import InboxNotices, SentDM
from test_campaign_role_access import CONFIG, TESTER, request, role_activity
from test_handler_pilot_view import login


def test_rate_limit_honors_body_and_blocks_repeated_provider_reads(monkeypatch):
    clock = [100.0]
    calls = []
    oauth._provider_cooldowns.clear()
    monkeypatch.setattr(oauth, "monotonic", lambda: clock[0])
    monkeypatch.setattr(
        oauth, "sleep", lambda delay: pytest.fail("Do not retry during Discord's rate limit")
    )

    def provider(*args, **kwargs):
        calls.append(1)
        raise HTTPError(
            "https://discord.com/api/v10/users/@me/guilds/g/member",
            429,
            "limited",
            {},
            io.BytesIO(b'{"retry_after":30,"global":true}'),
        )

    monkeypatch.setattr(oauth, "urlopen", provider)
    with pytest.raises(oauth.SignInError) as error:
        oauth.discord_request("/users/@me/guilds/g/member", token="synthetic")
    assert error.value.status == 429 and "30 seconds" in str(error.value)
    assert error.value.retry_after == 30
    with pytest.raises(oauth.SignInError):
        oauth.discord_request("/users/@me", token="synthetic")
    assert len(calls) == 1
    clock[0] += 31
    with pytest.raises(oauth.SignInError):
        oauth.discord_request("/users/@me/guilds/g/member", token="synthetic")
    assert len(calls) == 2
    oauth._provider_cooldowns.clear()


def test_user_rate_limit_does_not_block_other_discord_accounts(monkeypatch):
    calls = []
    monkeypatch.setattr(oauth, "_provider_cooldowns", {})

    def provider(request, **_):
        calls.append(request.get_header("Authorization"))
        if calls[-1] == "Bearer first":
            raise HTTPError(
                request.full_url,
                429,
                "limited",
                {
                    "X-RateLimit-Scope": "user",
                    "Retry-After": "16",
                },
                io.BytesIO(b"{}"),
            )
        return io.BytesIO(b'{"roles":[]}')

    monkeypatch.setattr(oauth, "urlopen", provider)
    member = "/users/@me/guilds/g/member"
    for _ in range(2):
        with pytest.raises(oauth.SignInError) as error:
            oauth.discord_request(member, token="first")
        assert error.value.retry_after == 16
    assert oauth.discord_request(member, token="second") == {"roles": []}
    assert calls == ["Bearer first", "Bearer second"]


def test_pending_members_can_message_with_owner_private_history_after_profile_save(tmp_path):
    with role_activity(tmp_path) as host:
        one = login(host, "role-pilot")
        two = login(host, "invited")
        campaign = request(host, "/api/campaigns", one)["campaigns"][0]["id"]
        query = "?campaign=" + campaign
        peer = request(host, "/api/player-setup" + query, two)
        first = request(host, "/api/player-setup" + query, one)
        peer = request(host, "/api/player-setup" + query, two)
        contact = next(
            p for p in first["communications"] if p["id"].endswith(CONFIG.invited_user_id)
        )
        actor = next(p for p in peer["communications"] if p["id"].endswith(TESTER))
        request(
            host,
            "/api/communications/" + contact["id"] + query,
            one,
            {"text": "A private enrollment transmission."},
        )
        updates = request(host, "/api/presence" + query, two)
        assert updates["mailbox"] == peer["mailbox"]
        assert (
            next(p for p in updates["communications"] if p["id"] == actor["id"])["latest_message"]
            > 0
        )
        assert "A private enrollment transmission." not in json.dumps(updates)
        assert not any(
            p["latest_message"]
            for p in request(host, "/api/presence" + query, one)["communications"]
        )
        assert (
            request(host, "/api/communications/" + actor["id"] + query, two)["entries"][0]["body"]
            == "A private enrollment transmission."
        )
        request(
            host,
            "/api/player-setup/profile" + query,
            one,
            {"revision": first["revision"], "callsign": "PENDING TRANSMITTER"},
        )
        request(
            host,
            "/api/player-setup/profile" + query,
            two,
            {"revision": peer["revision"], "callsign": "PENDING RECIPIENT"},
        )
        first = request(host, "/api/player-setup" + query, one)
        contact = next(p for p in first["communications"] if p["label"] == "PENDING RECIPIENT")
        assert (
            request(host, "/api/communications/" + contact["id"] + query, one)["entries"][0]["body"]
            == "A private enrollment transmission."
        )
        third = login(host, "other")
        outsider = request(host, "/api/player-setup" + query, third)
        contact3 = next(p for p in outsider["communications"] if p["label"] == "PENDING RECIPIENT")
        assert (
            request(host, "/api/communications/" + contact3["id"] + query, third)["entries"] == []
        )
        assert not any(
            p["latest_message"]
            for p in request(host, "/api/presence" + query, third)["communications"]
        )
        reopened = login(host, "role-pilot")
        assert (
            request(host, "/api/communications/" + contact["id"] + query, reopened)["entries"][0][
                "body"
            ]
            == "A private enrollment transmission."
        )


def test_new_comms_alert_is_once_per_saved_message_and_sender_private(tmp_path):
    body = "Private lock-screen text fixture."
    with role_activity(tmp_path, bot_handler=True, inbox=True) as host:
        sender = login(host, "role-pilot")
        recipient = login(host, "invited")
        outsider = login(host, "other")
        campaign = request(host, "/api/campaigns", sender)["campaigns"][0]["id"]
        query = "?campaign=" + campaign
        request(host, "/api/player-setup" + query, recipient)
        setup = request(host, "/api/player-setup" + query, sender)
        contacts = setup["communications"]
        contact = next(
            row
            for row in contacts
            if f"pilot-account-{CONFIG.invited_user_id}" in (row["id"], *row["aliases"])
        )
        assert "notice_recipient" not in contact
        route = "/api/communications/" + contact["id"] + query
        sent = request(host, route, sender, {"text": body}, key="comms-dm")
        assert request(host, route, sender, {"text": body}, key="comms-dm") == sent
        assert set(sent) == {"entry", "dm_receipt"}
        assert "notice_recipient" not in request(host, route, sender)["recipient"]
        proof = "/api/dm-receipts/" + sent["dm_receipt"] + query
        request(host, proof, recipient, status=HTTPStatus.NOT_FOUND)
        request(host, proof, outsider, status=HTTPStatus.NOT_FOUND)
        record = request(host, proof, sender)["recipients"][0]
        assert record["status"] == "queued"
        bot = next(row for row in contacts if row["bot"])
        saved_to_bot = request(
            host, "/api/communications/" + bot["id"] + query, sender, {"text": "Message to bot."}
        )
        assert set(saved_to_bot) == {"entry"}

        outbox_path = (
            tmp_path
            / "role-runtime"
            / f"activity-inbox-notices-{CONFIG.client_id}-{CONFIG.guild_id}.sqlite3"
        )
        outbox = InboxNotices(outbox_path)
        item = (str(UUID(campaign)), "communication", str(sent["entry"]), CONFIG.invited_user_id)
        assert outbox.claim() == item
        outbox.finish(item, "sent", SentDM("123456", "123457"))
        assert outbox.claim() is None
        assert outbox.claim_cleanup() is None
        assert request(host, proof, sender)["recipients"] == [record | {"status": "sent"}]
        delivery = request(host, "/api/dm-receipts" + query + "&view=delivery", sender)
        assert [row["kind"] for row in delivery["deliveries"]] == ["communication"]
        assert body.encode() not in outbox_path.read_bytes()


def test_comms_alert_rechecks_message_recipient_and_age(tmp_path, monkeypatch):
    monkeypatch.setattr(activity_records, "time", lambda: 1000)
    records = ActivityRecords(tmp_path / "comms.sqlite3", 1)
    receipt = records.send_private(
        "source", {"id": "pilot-account-1", "label": "SENDER"}, "pilot-account-2", "Private."
    )
    entry = str(receipt["entry"])
    assert records.private_message_for(entry, ["pilot-account-2"], since=1000)
    assert not records.private_message_for(entry, ["pilot-account-1", "handler-1"], since=1000)
    assert not records.private_message_for(entry, ["pilot-account-2"], since=1001)


def test_explicit_bot_assignment_preserves_the_former_handlers_own_draft(tmp_path, monkeypatch):
    import mission_lab as mission
    from bot_handler_assignment import assign_bot_handler
    from discord_test_host import managed_campaign_fixture
    from player_setup import PlayerSetup

    from girlframe.engine.drafts import DraftInput
    from girlframe.services.read_only_bot import GuildViewer

    monkeypatch.setattr(mission, "RUNTIME", tmp_path / "bot-assignment")
    catalog = managed_campaign_fixture("discord-offline-single-role")
    binding = catalog.bindings(CONFIG.client_id, CONFIG.guild_id)[0]
    service = mission.open_managed_campaign(binding, initialize=False)
    human = GuildViewer(int(binding.handler_id), int(binding.guild_id), True, False)
    service.store.save_draft(
        human,
        "before-reassignment-profile",
        0,
        DraftInput(
            callsign="FORMER HANDLER",
            girl_playbook="MOCKINGBIRD",
            frame_playbook="JANUS",
            notes="Keep private notes.",
        ),
    )

    def character_rows():
        with service.store.engine.connect() as c:
            return list(c.exec_driver_sql("SELECT * FROM characters").fetchall())

    before = character_rows()
    options = dict(
        bot_id=binding.application_id,
        expected_handler=binding.handler_id,
        actor_id=binding.handler_id,
        key="explicit-bot-appointment",
    )
    updated = assign_bot_handler(service, catalog, binding, **options)
    assert updated.handler_id == binding.application_id
    assert character_rows() == before
    assert assign_bot_handler(service, catalog, updated, **options) == updated
    assert (
        catalog.bindings(CONFIG.client_id, CONFIG.guild_id)[0].handler_id == binding.application_id
    )
    reopened = mission.open_managed_campaign(updated, initialize=False)
    bot = GuildViewer(int(updated.handler_id), int(updated.guild_id), True, False)
    setup = PlayerSetup(reopened.store, bot, bot, bot, bound_roster=True)
    setup.enable_activity_records()
    result = setup.view(human)
    assert result["stage"] == "draft" and result["callsign"] == "FORMER HANDLER"
    assert not any("Handler account" in issue for issue in result["review"]["issues"])
    assert reopened.store.draft(human)["notes"] == "Keep private notes."
    assert any(p["handler"] and p["name"] == "HarpyEngine" for p in setup.campaign_members(human))
    with pytest.raises(ValueError):
        assign_bot_handler(
            service, catalog, updated, **(options | {"actor_id": CONFIG.other_user_id})
        )
