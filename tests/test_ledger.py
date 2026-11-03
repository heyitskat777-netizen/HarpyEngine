import asyncio
import json
import runpy
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import discord
import jsonschema
import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from sqlalchemy.exc import IntegrityError

from girlframe.__main__ import main
from girlframe.config import Settings
from girlframe.database import tables as t
from girlframe.database.connection import create_database_engine
from girlframe.database.maintenance import copy_database
from girlframe.delivery.outbox import OutboxWorker
from girlframe.discord_adapter.bot import ReadOnlyDiscordBot
from girlframe.discord_adapter.config import BotPolicy
from girlframe.discord_adapter.ledger import DiscordRollGateway, receipt_text
from girlframe.engine.drafts import DraftInput
from girlframe.engine.rolls import OsDice, RollReceipt
from girlframe.services.ledger import CampaignLedger
from girlframe.services.onboarding import OnboardingStore, WorkflowError
from girlframe.services.read_only_bot import GuildViewer, ReadOnlyBotService

ROOT = Path(__file__).resolve().parents[1]
ADMIN = GuildViewer(1, 200, True, True)
PLAYER = GuildViewer(2, 200, True, False)
OTHER = GuildViewer(3, 200, True, False)


class FixedDice:
    def __init__(self):
        self.calls = 0

    def roll(self):
        self.calls += 1
        return 4, 3


@pytest.fixture
def ledger(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'ledger.db'}"
    monkeypatch.setenv("GIRLFRAME_DATABASE_URL", url)
    command.upgrade(Config(str(ROOT / "alembic.ini")), "head")
    engine = create_database_engine(Settings(database_url=url))
    policy = BotPolicy(
        application_id=100,
        guild_id=200,
        campaign_id=uuid4(),
        sandbox=tmp_path,
        allow_guild_administrators=True,
        status_audience_approved=True,
    )
    store = OnboardingStore(engine, policy)
    yield CampaignLedger(store, dice=FixedDice())
    engine.dispose()


def revision(ledger, viewer=ADMIN):
    return ledger.status(viewer)["revision"]


def seed(ledger, viewer=PLAYER, callsign="SYNTH_A", notes="PRIVATE_CANARY"):
    ledger.join(viewer, f"join-{viewer.user_id}")
    ledger.save_draft(
        viewer,
        f"draft-{viewer.user_id}",
        0,
        DraftInput(
            callsign=callsign, girl_playbook="MOCKINGBIRD", frame_playbook="JANUS-B", notes=notes
        ),
    )


def channel(ledger):
    with ledger.engine.begin() as connection:
        connection.execute(
            t.resources.insert().values(
                campaign_id=ledger.campaign_id, key="ledger", discord_id="900", state="ready"
            )
        )


def count(ledger, table):
    with ledger.engine.connect() as connection:
        return connection.scalar(sa.select(sa.func.count()).select_from(table))


def test_m1_002_campaign_ids_principals_and_preserved_drafts(ledger):
    seed(ledger)
    original = ledger.draft(PLAYER)
    result = ledger.create_campaign(ADMIN, "create", revision(ledger), "Synthetic Pilot")
    assert result["name"] == "Synthetic Pilot"
    assert ledger.draft(PLAYER) == original
    assert ledger.create_campaign(ADMIN, "create", -1, "Synthetic Pilot") == result
    with pytest.raises(WorkflowError, match="already initialized"):
        ledger.create_campaign(ADMIN, "create-again", revision(ledger), "Other")
    with pytest.raises(WorkflowError):
        ledger.create_campaign(PLAYER, "forged-admin", revision(ledger), "Other")
    with ledger.engine.connect() as connection:
        row = connection.execute(sa.select(t.principals)).mappings().one()
        assert row["user_id"] == "2" and len(row["id"]) == 36


def test_m1_003_004_sheets_and_private_ledger_pagination(ledger):
    seed(ledger)
    ledger.join(OTHER, "join-other")
    private = ledger.roll_basic(PLAYER, "private", revision(ledger))
    assert ledger.draft(PLAYER)["notes"] == "PRIVATE_CANARY"
    assert "PRIVATE_CANARY" not in json.dumps(ledger.draft(OTHER, PLAYER.user_id))
    for viewer in (OTHER, ADMIN):
        if viewer == ADMIN:
            ledger.join(ADMIN, "join-admin")
        with pytest.raises(WorkflowError, match="unavailable"):
            ledger.get_roll_receipt(viewer, private.id)
        for cursor in (None, 100, 3, 1):
            page = ledger.list_events(viewer, before=cursor, limit=1)
            assert private.id not in json.dumps(page)
            assert "PRIVATE_CANARY" not in json.dumps(page)
    assert "PRIVATE_CANARY" not in json.dumps(ledger.public_export())
    assert ledger.public_export()["rolls"] == []
    with pytest.raises(WorkflowError):
        ledger.list_events(PLAYER, limit=1000)


def test_m1_005_same_callsign_two_campaigns_and_user_are_isolated(ledger):
    seed(ledger, notes="FIRST_CANARY")
    private = ledger.roll_basic(PLAYER, "roll", revision(ledger))
    policy = ledger.policy.model_copy(update={"campaign_id": uuid4(), "guild_id": 300})
    second = CampaignLedger(OnboardingStore(ledger.engine, policy), dice=FixedDice())
    second_player = GuildViewer(2, 300, True, False)
    seed(second, second_player, notes="SECOND_CANARY")
    assert second.draft(second_player)["callsign"] == ledger.draft(PLAYER)["callsign"]
    assert second.draft(second_player)["id"] != ledger.draft(PLAYER)["id"]
    assert "FIRST_CANARY" not in json.dumps(second.draft(second_player))
    with pytest.raises(WorkflowError):
        second.get_roll_receipt(second_player, private.id)
    with pytest.raises(WorkflowError):
        second.roll_basic(PLAYER, "wrong-guild", 0)
    conflicting = CampaignLedger(
        OnboardingStore(ledger.engine, policy.model_copy(update={"guild_id": 200})),
        dice=FixedDice(),
    )
    with pytest.raises(WorkflowError, match="binding conflicts"):
        conflicting.public_export()


def test_m1_006_os_dice_and_strict_receipt(ledger):
    seed(ledger)
    production = CampaignLedger(ledger)
    receipt = production.roll_basic(PLAYER, "os-roll", revision(ledger))
    assert isinstance(production.dice, OsDice)
    assert receipt.rng_source == "os" and receipt.total == sum(receipt.faces)
    assert all(type(face) is int and 1 <= face <= 6 for face in receipt.faces)
    assert receipt.kind == "raw_2d6_test"
    assert "no official Play" in receipt_text(receipt)
    schema = json.loads(
        (
            ROOT / "GIRLFRAME_Discord_Codex_Handoff_v0.2/contracts/roll_receipt.schema.json"
        ).read_text()
    )
    jsonschema.validate(receipt.contract(), schema, format_checker=jsonschema.FormatChecker())
    for faces, total in (((0, 2), 2), ((True, 2), 3), ((1, 2), 4)):
        bad = receipt.model_dump() | {"faces": faces, "total": total}
        with pytest.raises(ValueError):
            RollReceipt.model_validate(bad)


def test_m1_007_008_duplicate_restart_and_changed_payload_no_rng(ledger):
    seed(ledger)
    version = revision(ledger)
    first = ledger.roll_basic(PLAYER, "retry", version)
    after = revision(ledger)
    assert ledger.roll_basic(PLAYER, "retry", after) == first
    restarted = CampaignLedger(ledger, dice=FixedDice())
    assert restarted.roll_basic(PLAYER, "retry", -1) == first
    assert restarted.dice.calls == 0 and ledger.dice.calls == 1
    with pytest.raises(WorkflowError, match="IDEMPOTENCY_CONFLICT"):
        restarted.roll_basic(PLAYER, "retry", after, publish=True)
    assert count(ledger, t.rolls) == 1
    with ledger.engine.connect() as connection:
        events = (
            connection.execute(sa.select(t.events).where(t.events.c.command_key == "retry"))
            .mappings()
            .all()
        )
        assert [event["event_index"] for event in events] == [0, 1]
        assert [event["kind"] for event in events] == ["dice.rolled", "dice.recorded"]
    assert revision(ledger) == after


def test_m1_009_concurrent_revision_only_winner_samples(ledger):
    seed(ledger)
    version = revision(ledger)

    def run(key):
        try:
            return ledger.roll_basic(PLAYER, key, version)
        except WorkflowError as error:
            return str(error)

    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(run, ["one", "two"]))
    assert sum(isinstance(r, RollReceipt) for r in results) == 1
    assert any("STALE_REVISION" in str(r) for r in results if isinstance(r, str))
    assert ledger.dice.calls == 1 and count(ledger, t.rolls) == 1


def test_failure_before_commit_rolls_back_everything(ledger):
    seed(ledger)
    channel(ledger)
    version, events = revision(ledger), count(ledger, t.events)

    def fail_commit(connection, cursor, statement, parameters, context, executemany):
        if statement.startswith("INSERT INTO commands_inbox"):
            raise RuntimeError("synthetic crash before commit")

    sa.event.listen(ledger.engine, "before_cursor_execute", fail_commit)
    try:
        with pytest.raises(RuntimeError):
            ledger.roll_basic(PLAYER, "crash", version, publish=True)
    finally:
        sa.event.remove(ledger.engine, "before_cursor_execute", fail_commit)
    assert count(ledger, t.rolls) == count(ledger, t.outbox) == 0
    assert count(ledger, t.events) == events and revision(ledger) == version
    receipt = ledger.roll_basic(PLAYER, "crash", version, publish=True)
    assert receipt.total == 7 and count(ledger, t.rolls) == count(ledger, t.outbox) == 1


class FakeDelivery:
    def __init__(self, *, reconcile=True):
        self.posts = []
        self.can_reconcile = reconcile
        self.fail_after_send = False

    async def reconcile(self, channel_id, receipt_id):
        assert channel_id == 900
        if self.can_reconcile:
            return next((i + 100 for i, (r, _) in enumerate(self.posts) if r == receipt_id), None)
        return None

    async def send(self, channel_id, receipt, nonce):
        assert channel_id == 900 and receipt.visibility == "campaign"
        self.posts.append((receipt.id, nonce))
        if self.fail_after_send:
            self.fail_after_send = False
            raise TimeoutError("synthetic lost HTTP acknowledgement")
        return 99 + len(self.posts)


def test_m1_010_crash_after_commit_worker_restart(ledger):
    seed(ledger)
    channel(ledger)
    receipt = ledger.roll_basic(PLAYER, "public", revision(ledger), publish=True)
    before = count(ledger, t.events)
    worker = OutboxWorker(CampaignLedger(ledger, dice=FixedDice()))
    gateway = FakeDelivery()
    assert asyncio.run(worker.deliver_one(gateway))
    assert not asyncio.run(worker.deliver_one(gateway))
    assert [r for r, _ in gateway.posts] == [receipt.id]
    assert count(ledger, t.events) == before and ledger.dice.calls == 1


@pytest.mark.parametrize("reconcile", [True, False])
def test_m1_011_send_before_ack_crash_reconciles_or_duplicates_only_delivery(ledger, reconcile):
    seed(ledger)
    channel(ledger)
    receipt = ledger.roll_basic(PLAYER, "public", revision(ledger), publish=True)
    job = ledger.claim_delivery()
    gateway = FakeDelivery(reconcile=reconcile)
    asyncio.run(gateway.send(900, receipt, job["nonce"]))
    assert ledger.claim_delivery() is None  # Lease prevents another worker sending now.
    now = ledger.clock()
    ledger.clock = lambda: now + 121
    assert asyncio.run(OutboxWorker(ledger).deliver_one(gateway))
    assert len(gateway.posts) == (1 if reconcile else 2)
    assert {nonce for _, nonce in gateway.posts} == {job["nonce"]}
    assert count(ledger, t.rolls) == 1 and ledger.dice.calls == 1
    assert not ledger.mark_delivery(job, 999)  # Expired claimant cannot overwrite the new ACK.


def test_outbox_failed_http_backoff_and_privacy(ledger):
    seed(ledger)
    private = ledger.roll_basic(PLAYER, "private", revision(ledger))
    assert ledger.claim_delivery() is None
    channel(ledger)
    ledger.roll_basic(PLAYER, "public", revision(ledger), publish=True)
    gateway = FakeDelivery()
    gateway.fail_after_send = True
    assert not asyncio.run(OutboxWorker(ledger).deliver_one(gateway))
    assert ledger.claim_delivery() is None
    now = ledger.clock()
    ledger.clock = lambda: now + 10
    assert asyncio.run(OutboxWorker(ledger).deliver_one(gateway))
    assert len(gateway.posts) == 1 and gateway.posts[0][0] != private.id


def test_m1_012_rebuild_private_snapshots_without_reroll(ledger):
    seed(ledger)
    first = ledger.roll_basic(PLAYER, "roll", revision(ledger))
    ledger.save_draft(
        PLAYER,
        "edit",
        1,
        DraftInput(
            callsign="SYNTH_B", girl_playbook="OLDGEN", frame_playbook="JANUS-B", notes="NEW_CANARY"
        ),
    )
    original, events = ledger.draft(PLAYER), count(ledger, t.events)
    with ledger.engine.begin() as connection:
        connection.execute(
            t.characters.update().values(public_json="{}", private_json="{}", revision=99)
        )
    assert CampaignLedger(ledger, dice=FixedDice()).rebuild_projections() == 1
    assert ledger.draft(PLAYER) == original
    assert ledger.get_roll_receipt(PLAYER, first.id) == first
    assert ledger.dice.calls == 1 and count(ledger, t.events) == events + 1
    assert "NEW_CANARY" not in json.dumps(ledger.list_events(PLAYER))


@pytest.mark.parametrize("table", [t.events, t.rolls, t.snapshots])
@pytest.mark.parametrize("action", ["update", "delete"])
def test_append_only_journal_receipts_snapshots(ledger, table, action):
    seed(ledger)
    ledger.roll_basic(PLAYER, "roll", revision(ledger))
    with ledger.engine.begin() as connection:
        statement = (
            table.delete()
            if action == "delete"
            else table.update().values(**{next(iter(table.c)).name: "tampered"})
        )
        with pytest.raises(IntegrityError, match="append-only"):
            connection.execute(statement)


def test_safety_pause_persists_self_clear_only_and_replay_works(ledger):
    seed(ledger)
    ledger.join(OTHER, "join-other")
    receipt = ledger.roll_basic(PLAYER, "before-pause", revision(ledger))
    assert ledger.safety(OTHER, "pause-other", -1, pause=True)["paused"]
    ledger.safety(PLAYER, "pause-player", -1, pause=True)
    assert ledger.roll_basic(PLAYER, "before-pause", -1) == receipt
    with pytest.raises(WorkflowError, match="SAFETY_PAUSED"):
        ledger.roll_basic(PLAYER, "blocked", revision(ledger))
    assert ledger.dice.calls == 1
    restarted = CampaignLedger(ledger, dice=FixedDice())
    assert restarted.safety(PLAYER, "resume-player", revision(ledger), pause=False)["paused"]
    assert restarted.status(PLAYER)["paused"]
    assert not restarted.safety(OTHER, "resume-other", revision(ledger), pause=False)["paused"]


def test_published_receipt_and_filtered_export_are_shared_without_private_fields(ledger):
    seed(ledger)
    ledger.join(OTHER, "other")
    channel(ledger)
    receipt = ledger.roll_basic(PLAYER, "published", revision(ledger), publish=True)
    assert ledger.get_roll_receipt(OTHER, receipt.id) == receipt
    page = ledger.list_events(OTHER)
    assert receipt.id in json.dumps(page)
    exported = ledger.public_export()
    assert exported["rolls"][0]["id"] == receipt.id
    for key in ("actor_id", "character_id", "campaign_id", "event_id", "notes"):
        assert key not in exported["rolls"][0]
    assert "PRIVATE_CANARY" not in json.dumps(exported)
    for bad_viewer in (
        GuildViewer(2, None, False, False),
        GuildViewer(2, 300, True, True),
        GuildViewer(2, 200, False, True),
    ):
        with pytest.raises(WorkflowError):
            ledger.get_roll_receipt(bad_viewer, receipt.id)


def test_upgrade_populated_0002_preserves_data_and_backfills_snapshots(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'old.db'}"
    monkeypatch.setenv("GIRLFRAME_DATABASE_URL", url)
    config = Config(str(ROOT / "alembic.ini"))
    command.upgrade(config, "0002")
    engine = create_database_engine(Settings(database_url=url))
    with engine.begin() as connection:
        connection.exec_driver_sql("INSERT INTO campaigns VALUES ('camp','200',2)")
        connection.exec_driver_sql("INSERT INTO campaign_members VALUES ('camp','2','player')")
        connection.exec_driver_sql(
            "INSERT INTO characters VALUES ('camp','2','char',3,?,?)",
            ('{"callsign":"OLD_DRAFT"}', '{"notes":"OLD_PRIVATE_CANARY"}'),
        )
    command.upgrade(config, "head")
    command.check(config)
    with engine.connect() as connection:
        row = connection.execute(sa.select(t.characters)).mappings().one()
        snapshot = connection.execute(sa.select(t.snapshots)).mappings().one()
        assert row["revision"] == snapshot["revision"] == 3
        assert row["private_json"] == snapshot["private_json"]
        assert snapshot["event_id"] is None  # Explicit migration baseline, no invented old event.
        assert connection.scalar(sa.select(t.principals.c.user_id)) == "2"
        assert connection.exec_driver_sql("PRAGMA foreign_key_check").all() == []
    engine.dispose()


def test_backup_restore_wal_receipts_and_cli_refuse_existing(ledger, tmp_path, capsys):
    seed(ledger)
    receipt = ledger.roll_basic(PLAYER, "roll", revision(ledger))
    backup = tmp_path / "backup.db"
    assert main(["db", "backup", "--dest", str(backup)]) == 0
    assert backup.stat().st_mode & 0o777 == 0o600
    restored = tmp_path / "restored.db"
    assert main(["db", "restore", "--source", str(backup), "--dest", str(restored)]) == 0
    assert main(["db", "restore", "--source", str(backup), "--dest", str(restored)]) == 1
    engine = create_database_engine(Settings(database_url=f"sqlite:///{restored}"))
    try:
        other = CampaignLedger(OnboardingStore(engine, ledger.policy), dice=FixedDice())
        assert other.get_roll_receipt(PLAYER, receipt.id) == receipt
        assert other.draft(PLAYER) == ledger.draft(PLAYER)
        assert other.roll_basic(PLAYER, "roll", -1) == receipt and other.dice.calls == 0
    finally:
        engine.dispose()
    assert "PRIVATE_CANARY" not in capsys.readouterr().out
    with pytest.raises(FileExistsError):
        copy_database(backup, backup.parent / "ledger.db")


def test_revoked_members_cannot_replay_or_view(ledger):
    seed(ledger)
    receipt = ledger.roll_basic(PLAYER, "roll", revision(ledger))
    with ledger.engine.begin() as connection:
        connection.execute(t.members.update().values(active=False))
    for operation in (
        lambda: ledger.roll_basic(PLAYER, "roll", -1),
        lambda: ledger.get_roll_receipt(PLAYER, receipt.id),
        lambda: ledger.list_events(PLAYER),
        lambda: ledger.join(PLAYER, "rejoin"),
    ):
        with pytest.raises(WorkflowError):
            operation()


def test_export_rebuild_cli_and_offline_seed(ledger, tmp_path, monkeypatch, capsys):
    seed(ledger)
    policy = tmp_path / "policy.json"
    policy.write_text(ledger.policy.model_dump_json())
    output = tmp_path / "public.json"
    assert main(["db", "export", "--config", str(policy), "--dest", str(output)]) == 0
    assert "PRIVATE_CANARY" not in output.read_text()
    assert main(["db", "export", "--config", str(policy), "--dest", str(output)]) == 1
    original = ledger.draft(PLAYER)
    with ledger.engine.begin() as connection:
        connection.execute(t.characters.update().values(public_json="{}"))
    assert main(["db", "rebuild", "--config", str(policy)]) == 0
    assert ledger.draft(PLAYER) == original
    destination = tmp_path / "offline-synthetic.db"
    monkeypatch.setattr(sys, "argv", ["seed_synthetic.py", "--dest", str(destination)])
    runpy.run_path(str(ROOT / "tools/seed_synthetic.py"), run_name="__main__")
    with pytest.raises(FileExistsError):
        runpy.run_path(str(ROOT / "tools/seed_synthetic.py"), run_name="__main__")
    assert "PRIVATE_CANARY" not in capsys.readouterr().out


def test_fake_discord_command_sequence(ledger, monkeypatch):
    from girlframe.discord_adapter import onboarding

    monkeypatch.setattr(onboarding, "allow_action", lambda *a, **kw: True)

    def interaction(identity):
        member = MagicMock(spec=discord.Member)
        member.id = ADMIN.user_id
        member.guild_permissions = discord.Permissions(administrator=True)
        request = MagicMock()
        request.user, request.guild_id, request.id = member, 200, identity
        request.response.defer = AsyncMock()
        request.response.is_done.return_value = True
        request.edit_original_response = AsyncMock()
        return request

    async def run():
        async with ReadOnlyDiscordBot(
            ledger.policy, ReadOnlyBotService(ledger.policy, MagicMock()), None, ledger
        ) as bot:
            guild = discord.Object(id=200)
            campaign = bot.tree.get_command("campaign", guild=guild)
            create = interaction(1001)
            await campaign.get_command("create").callback(create, "Synthetic Pilot")
            join = interaction(1002)
            await campaign.get_command("join").callback(join)
            bot.ledger.save_draft(
                ADMIN,
                "human-save",
                0,
                DraftInput(
                    callsign="SYNTH_A",
                    girl_playbook="OLDGEN",
                    frame_playbook="JANUS-B",
                    notes="CANARY",
                ),
            )
            channel(bot.ledger)
            roll = interaction(1003)
            await bot.tree.get_command("roll", guild=guild).get_command("basic").callback(roll)
            text = roll.edit_original_response.call_args.kwargs["content"]
            assert "Raw 2d6 test" in text and "CANARY" not in text
            assert "Public ledger delivery queued." in text
            assert roll.response.defer.call_args.kwargs["ephemeral"]
            assert count(bot.ledger, t.outbox) == 1
            private = interaction(1004)
            await (
                bot.tree.get_command("roll", guild=guild)
                .get_command("basic")
                .callback(private, publish=False)
            )
            assert "Private receipt." in private.edit_original_response.call_args.kwargs["content"]
            assert count(bot.ledger, t.outbox) == 1
            with bot.ledger.engine.connect() as connection:
                assert connection.execute(
                    sa.select(t.rolls.c.visibility).order_by(t.rolls.c.command_key)
                ).scalars().all() == ["campaign", "private"]
            page = interaction(1005)
            await bot.tree.get_command("ledger", guild=guild).callback(page)
            assert "dice.rolled" in page.edit_original_response.call_args.kwargs["content"]

    asyncio.run(run())


def test_discord_delivery_gateway_scoped_nonce_mentions_and_reconciliation():
    channel_mock = MagicMock(spec=discord.TextChannel)
    guild = MagicMock(spec=discord.Guild)
    guild.id = 200
    guild.me = MagicMock(id=100)
    channel_mock.guild = guild
    channel_mock.permissions_for.return_value = discord.Permissions(
        view_channel=True, send_messages=True, read_message_history=True
    )
    guild.fetch_channel = AsyncMock(return_value=channel_mock)
    channel_mock.send = AsyncMock(return_value=MagicMock(id=777))
    receipt = RollReceipt(
        id=str(uuid4()),
        campaign_id=str(uuid4()),
        event_id=str(uuid4()),
        actor_id="2",
        character_id=str(uuid4()),
        callsign="@everyone *TEST*",
        faces=(4, 3),
        total=7,
        rolled_utc="2026-11-03T00:00:00+00:00",
        revision=1,
        visibility="campaign",
        rng_source="os",
        idempotency_key="discord:synthetic",
    )

    async def history(**kwargs):
        assert kwargs == {"limit": 50}
        yield MagicMock(id=888, author=MagicMock(id=999), content=receipt_text(receipt))
        yield MagicMock(id=777, author=guild.me, content=receipt_text(receipt))

    channel_mock.history = history

    async def run():
        gateway = DiscordRollGateway(guild)
        assert await gateway.reconcile(900, receipt.id) == 777
        assert await gateway.send(900, receipt, "stable-nonce") == 777
        kwargs = channel_mock.send.call_args.kwargs
        assert kwargs["nonce"] == "stable-nonce"
        assert kwargs["allowed_mentions"].everyone is False
        channel_mock.guild = MagicMock(id=300)
        with pytest.raises(WorkflowError):
            await gateway.send(900, receipt, "nonce")

    asyncio.run(run())
