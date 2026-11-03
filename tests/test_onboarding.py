import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import discord
import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config

from girlframe.config import Settings
from girlframe.database import tables as t
from girlframe.database.connection import create_database_engine
from girlframe.discord_adapter.bot import ReadOnlyDiscordBot
from girlframe.discord_adapter.config import BotPolicy
from girlframe.discord_adapter.onboarding import (
    DiscordProvisioningGateway,
    DraftModal,
    NewPlayerView,
    SaveDraftView,
    allow_action,
    sheet_text,
)
from girlframe.engine.drafts import DraftInput
from girlframe.services.onboarding import OnboardingStore, WorkflowError
from girlframe.services.provisioning import TEMPLATE, CreationRefused, Provisioner
from girlframe.services.read_only_bot import GuildViewer, ReadOnlyBotService

ADMIN = GuildViewer(1, 200, True, True)
PLAYER = GuildViewer(2, 200, True, False)


@pytest.fixture
def store(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'onboarding.db'}"
    monkeypatch.setenv("GIRLFRAME_DATABASE_URL", url)
    command.upgrade(Config(str(Path(__file__).resolve().parents[1] / "alembic.ini")), "head")
    engine = create_database_engine(Settings(database_url=url))
    policy = BotPolicy(
        application_id=100,
        guild_id=200,
        campaign_id=uuid4(),
        sandbox=tmp_path,
        allow_guild_administrators=True,
        status_audience_approved=True,
    )
    yield OnboardingStore(engine, policy)
    engine.dispose()


class FakeGateway:
    def __init__(self):
        self.data = {}
        self.calls = 0
        self.fail_at = None
        self.uncertain_at = None
        self.permission = True

    async def preflight(self):
        if not self.permission:
            raise CreationRefused("Missing Manage Channels")

    async def exists(self, identity, spec, parent):
        return self.data.get(identity) == (spec, parent)

    async def create(self, spec, parent):
        self.calls += 1
        if self.calls == self.fail_at:
            raise CreationRefused("Denied by Discord")
        identity = self.calls + 1000
        self.data[identity] = (spec, parent)
        if self.calls == self.uncertain_at:
            raise TimeoutError("Outcome unknown")
        return identity


def make_plan(store, key="plan"):
    return store.create_plan(ADMIN, key)["plan_id"]


def draft(name="Synthetic A", notes="PRIVATE_CANARY"):
    return DraftInput(
        callsign=name, girl_playbook="MOCKINGBIRD", frame_playbook="JANUS-B", notes=notes
    )


def test_setup_requires_admin_and_permissions_before_creating(store):
    with pytest.raises(WorkflowError):
        store.create_plan(PLAYER, "denied")
    plan = make_plan(store)
    gateway = FakeGateway()
    gateway.permission = False
    with pytest.raises(CreationRefused):
        asyncio.run(Provisioner(store).apply(ADMIN, plan, gateway))
    assert gateway.calls == 0
    with store.engine.connect() as connection:
        assert connection.scalar(sa.select(sa.func.count()).select_from(t.resources)) == 0


def test_setup_replay_restart_reuses_saved_resources(store):
    gateway = FakeGateway()
    plan = make_plan(store)
    assert asyncio.run(Provisioner(store).apply(ADMIN, plan, gateway)) == len(TEMPLATE)
    restarted = OnboardingStore(store.engine, store.policy)
    assert (
        asyncio.run(Provisioner(restarted).apply(ADMIN, make_plan(restarted, "again"), gateway))
        == 0
    )
    assert gateway.calls == len(TEMPLATE)
    assert len(gateway.data) == len(TEMPLATE)


def test_concurrent_confirmations_do_not_duplicate_resources(store):
    gateway = FakeGateway()
    plan = make_plan(store)

    async def run():
        provisioner = Provisioner(store)
        return await asyncio.gather(
            provisioner.apply(ADMIN, plan, gateway), provisioner.apply(ADMIN, plan, gateway)
        )

    assert sorted(asyncio.run(run())) == [0, len(TEMPLATE)]
    assert gateway.calls == len(TEMPLATE)


def test_confirmation_is_bound_to_actor_guild_and_expiry(store):
    plan = make_plan(store)
    gateway = FakeGateway()
    with pytest.raises(WorkflowError):
        asyncio.run(Provisioner(store).apply(GuildViewer(3, 200, True, True), plan, gateway))
    with pytest.raises(WorkflowError):
        asyncio.run(Provisioner(store).apply(GuildViewer(1, 201, True, True), plan, gateway))
    store.clock = lambda: 10**12
    with pytest.raises(WorkflowError, match="expired"):
        asyncio.run(Provisioner(store).apply(ADMIN, plan, gateway))
    assert gateway.calls == 0


def test_partial_setup_resumes_without_duplicate_successes(store):
    gateway = FakeGateway()
    gateway.fail_at = 4
    with pytest.raises(CreationRefused):
        asyncio.run(Provisioner(store).apply(ADMIN, make_plan(store), gateway))
    first = dict(gateway.data)
    gateway.fail_at = None
    restarted = OnboardingStore(store.engine, store.policy)
    assert (
        asyncio.run(Provisioner(restarted).apply(ADMIN, make_plan(restarted, "retry"), gateway))
        == 7
    )
    assert len(gateway.data) == 10
    assert all(gateway.data[key] == value for key, value in first.items())


def test_unknown_create_outcome_pauses_instead_of_duplicating(store):
    gateway = FakeGateway()
    gateway.uncertain_at = 4
    with pytest.raises(WorkflowError, match="unknown"):
        asyncio.run(Provisioner(store).apply(ADMIN, make_plan(store), gateway))
    assert gateway.calls == 4 and len(gateway.data) == 4
    with pytest.raises(WorkflowError, match="unknown"):
        asyncio.run(Provisioner(store).apply(ADMIN, make_plan(store, "retry"), gateway))
    assert gateway.calls == 4


def test_missing_saved_resource_requires_repair_not_unrelated_adoption(store):
    gateway = FakeGateway()
    asyncio.run(Provisioner(store).apply(ADMIN, make_plan(store), gateway))
    del gateway.data[1001]
    with pytest.raises(WorkflowError, match="missing"):
        asyncio.run(Provisioner(store).apply(ADMIN, make_plan(store, "retry"), gateway))
    assert gateway.calls == 10


def test_join_and_draft_replay_restart_and_stale_forms(store):
    with pytest.raises(WorkflowError, match="Join"):
        store.save_draft(PLAYER, "save", 0, draft())
    store.join(PLAYER, "join")
    first = store.save_draft(PLAYER, "save", 0, draft())
    assert store.save_draft(PLAYER, "save", 0, draft()) == first
    with pytest.raises(WorkflowError, match="IDEMPOTENCY_CONFLICT"):
        store.save_draft(PLAYER, "save", 0, draft("Changed"))
    with pytest.raises(WorkflowError, match="STALE_REVISION"):
        store.save_draft(PLAYER, "different", 0, draft("Stale"))
    restarted = OnboardingStore(store.engine, store.policy)
    assert restarted.draft(PLAYER)["id"] == first["id"]
    assert restarted.draft(PLAYER)["notes"] == "PRIVATE_CANARY"
    assert restarted.save_draft(PLAYER, "update", 1, draft("Updated"))["revision"] == 2


def test_other_admin_has_only_public_sheet_and_audit_has_no_notes(store):
    store.join(PLAYER, "join")
    store.join(ADMIN, "admin-join")
    store.save_draft(PLAYER, "save", 0, draft())
    public = store.draft(ADMIN, PLAYER.user_id)
    assert "notes" not in public and "PRIVATE_CANARY" not in json.dumps(public)
    assert store.draft(ADMIN) is None
    with store.engine.connect() as connection:
        assert "PRIVATE_CANARY" not in str(connection.execute(sa.select(t.events)).all())
        assert "PRIVATE_CANARY" not in str(connection.execute(sa.select(t.commands)).all())


def test_two_campaigns_with_same_owner_and_callsign_are_isolated(store):
    other_policy = store.policy.model_copy(update={"campaign_id": uuid4(), "guild_id": 201})
    other = OnboardingStore(store.engine, other_policy)
    other_player = GuildViewer(PLAYER.user_id, 201, True, False)
    store.join(PLAYER, "join")
    other.join(other_player, "join")
    first = store.save_draft(PLAYER, "save", 0, draft(notes="ONE"))
    second = other.save_draft(other_player, "save", 0, draft(notes="TWO"))
    assert first["id"] != second["id"]
    assert store.draft(PLAYER)["notes"] == "ONE"
    assert other.draft(other_player)["notes"] == "TWO"
    with pytest.raises(WorkflowError):
        other.draft(PLAYER)


def test_concurrent_draft_saves_commit_only_one_revision(store):
    store.join(PLAYER, "join")

    def save(index):
        try:
            return store.save_draft(PLAYER, f"save{index}", 0, draft(str(index)))
        except WorkflowError:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        result = list(pool.map(save, [1, 2]))
    assert sum(item is not None for item in result) == 1
    assert store.draft(PLAYER)["revision"] == 1


def test_rebinding_same_campaign_to_another_guild_cannot_read_or_confirm(store):
    store.join(PLAYER, "join")
    store.save_draft(PLAYER, "save", 0, draft())
    plan = make_plan(store)
    wrong = OnboardingStore(store.engine, store.policy.model_copy(update={"guild_id": 201}))
    with pytest.raises(WorkflowError, match="binding"):
        wrong.draft(GuildViewer(PLAYER.user_id, 201, True, False))
    with pytest.raises(WorkflowError, match="binding"):
        wrong.claim_resource(GuildViewer(ADMIN.user_id, 201, True, True), plan, "main")


def test_staff_overwrites_and_persistent_controls_are_explicit(store):
    async def run():
        guild = MagicMock(spec=discord.Guild)
        guild.default_role = MagicMock(spec=discord.Role)
        guild.me = MagicMock(spec=discord.Member)
        entry = NewPlayerView(store)
        gateway = DiscordProvisioningGateway(guild, entry)
        staff = next(spec for spec in TEMPLATE if spec.key == "review")
        overrides = gateway.overwrites(staff)
        assert overrides[guild.default_role].view_channel is False
        assert overrides[guild.me].view_channel is True
        assert entry.is_persistent()
        assert {item.custom_id for item in entry.children} == {
            "harpyengine:join:v1",
            "harpyengine:draft:v1",
            "harpyengine:sheet:v1",
        }

    asyncio.run(run())


def test_bot_registers_setup_join_character_sheet_when_store_enabled(store):
    async def run():
        service = ReadOnlyBotService(store.policy, MagicMock())
        async with ReadOnlyDiscordBot(store.policy, service, None, store) as bot:
            cmds = bot.tree.get_commands(guild=discord.Object(id=200))
            assert {cmd.name for cmd in cmds} == {
                "help",
                "campaign_status",
                "health",
                "server",
                "campaign",
                "character",
                "sheet",
                "girl",
                "roll",
                "ledger",
                "safety",
            }
            assert not bot.tree.get_commands()

    asyncio.run(run())


def test_draft_form_resumes_owner_fields_and_display_stays_bounded(store):
    store.join(PLAYER, "join")
    store.save_draft(PLAYER, "save", 0, draft(notes="*" * 1000))
    existing = store.draft(PLAYER)

    async def run():
        modal = DraftModal(store, PLAYER.user_id, existing)
        assert modal.revision == 1 and modal.callsign.default == existing["callsign"]
        assert modal.notes.default == "*" * 1000
        confirmation = SaveDraftView(store, PLAYER.user_id, 1, draft())
        assert confirmation.owner == PLAYER.user_id

    asyncio.run(run())
    assert len(sheet_text(existing)) <= 1900
    assert "rules unverified" in sheet_text(existing)


def test_save_button_cannot_be_used_by_another_player(store, monkeypatch):
    store.join(PLAYER, "join")
    store.join(ADMIN, "admin-join")
    store.save_draft(PLAYER, "save", 0, draft())
    monkeypatch.setattr(
        "girlframe.discord_adapter.onboarding.viewer_from_interaction", lambda interaction: ADMIN
    )
    request = MagicMock(spec=discord.Interaction)
    request.id = 900
    request.response.is_done.return_value = True
    request.response.defer = AsyncMock()
    request.edit_original_response = AsyncMock()

    async def run():
        view = SaveDraftView(store, PLAYER.user_id, 1, draft("Attempted overwrite"))
        await view.children[0].callback(request)

    asyncio.run(run())
    assert "another player" in request.edit_original_response.call_args.kwargs["content"]
    assert store.draft(PLAYER)["callsign"] == "Synthetic A"
    assert store.draft(ADMIN) is None


def test_fixture_with_unrelated_same_name_channel_is_not_adopted(store):
    gateway = FakeGateway()
    welcome = next(spec for spec in TEMPLATE if spec.key == "welcome")
    gateway.data[777] = (welcome, None)
    asyncio.run(Provisioner(store).apply(ADMIN, make_plan(store), gateway))
    assert gateway.data[777] == (welcome, None)
    assert gateway.calls == len(TEMPLATE)
    with store.engine.connect() as connection:
        saved = connection.execute(
            sa.select(t.resources.c.discord_id).where(
                t.resources.c.campaign_id == store.campaign_id, t.resources.c.key == "welcome"
            )
        ).scalar_one()
        assert saved != "777"


def test_ui_throttle_is_bounded_and_user_action_scoped():
    assert all(allow_action(999, 123, "synthetic", now=1) for _ in range(3))
    assert not allow_action(999, 123, "synthetic", now=2)
    assert allow_action(999, 124, "synthetic", now=2)
    assert allow_action(999, 123, "other", now=2)
    assert allow_action(999, 123, "synthetic", now=11)
