import asyncio
import json
from dataclasses import dataclass, field
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest
from pydantic import ValidationError
from test_onboarding import ADMIN, PLAYER
from test_onboarding import store as store  # noqa: F401 -- shared pytest fixture

from girlframe.discord_adapter.character_tags import DiscordCharacterTagGateway
from girlframe.discord_adapter.onboarding import CharacterSelectionView, DraftModal
from girlframe.engine.drafts import DraftInput
from girlframe.engine.playbooks import FRAME_TYPES, GIRL_TYPES
from girlframe.services.character_tags import CharacterTagSynchronizer
from girlframe.services.onboarding import WorkflowError


@dataclass
class Role:
    id: int
    position: int
    name: str
    permissions: discord.Permissions = field(default_factory=discord.Permissions.none)
    managed: bool = False

    def __lt__(self, other):
        return self.position < other.position

    def __ge__(self, other):
        return self.position >= other.position

    def is_default(self):
        return self.id == 0


class Member:
    def __init__(self, identity, roles, permissions=None):
        self.id = identity
        self.roles = roles
        self.nick = None
        self.guild_permissions = permissions or discord.Permissions.none()
        self.added = []
        self.removed = []
        self.edits = []
        self.on_add = None

    async def add_roles(self, *roles, **kwargs):
        self.added.extend(role.id for role in roles)
        self.roles += [role for role in roles if role.id not in {old.id for old in self.roles}]
        if self.on_add:
            callback = self.on_add
            self.on_add = None
            callback()

    async def remove_roles(self, *roles, **kwargs):
        self.removed.extend(role.id for role in roles)
        removing = {role.id for role in roles}
        self.roles = [role for role in self.roles if role.id not in removing]

    async def edit(self, **kwargs):
        self.nick = kwargs["nick"]
        self.edits.append(kwargs)


class Guild:
    def __init__(self):
        self.owner_id = 999
        self.roles = {
            0: Role(0, 0, "everyone"),
            10: Role(10, 10, "bot"),
            90: Role(90, 2, "MOCKINGBIRD", discord.Permissions(administrator=True)),
            91: Role(91, 3, "Community"),
        }
        self.me = Member(
            100,
            [self.roles[0], self.roles[10]],
            discord.Permissions(manage_roles=True, manage_nicknames=True),
        )
        self.member = Member(PLAYER.user_id, [self.roles[0], self.roles[91]])
        self.created = []
        self.unknown_create = False
        self.missing_member = False

    async def fetch_roles(self):
        return list(self.roles.values())

    async def fetch_member(self, owner):
        assert owner == self.member.id
        if self.missing_member:
            raise discord.NotFound(MagicMock(status=404, reason="Not Found"), {"code": 10007})
        return self.member

    async def create_role(self, **kwargs):
        assert (
            kwargs["permissions"].value == 0 and not kwargs["hoist"] and not kwargs["mentionable"]
        )
        role = Role(20 + len(self.created), 1, kwargs["name"])
        self.roles[role.id] = role
        self.created.append(kwargs)
        if self.unknown_create:
            raise TimeoutError("unknown outcome")
        return role


def save_sorrow(store):
    store.join(PLAYER, "join")
    return store.save_draft(
        PLAYER,
        "save",
        0,
        DraftInput(
            callsign="SORROW",
            girl_playbook="MOCKINGBIRD",
            frame_playbook="JANUS-B",
            notes="PRIVATE_CANARY",
        ),
    )


def test_dropdowns_and_details_modal_have_no_free_text_playbook_fields(store):
    store.join(PLAYER, "join")

    async def run():
        view = CharacterSelectionView(store, PLAYER.user_id, None)
        selects = [item for item in view.children if isinstance(item, discord.ui.Select)]
        assert len(selects) == 2
        assert {option.value for option in selects[0].options} == set(GIRL_TYPES)
        assert {option.value for option in selects[1].options} == set(FRAME_TYPES)
        assert all(len(item.options) <= 25 for item in selects)
        assert view.continue_button.disabled
        modal = DraftModal(store, PLAYER.user_id, None, "MOCKINGBIRD", "JANUS-B")
        assert len(modal.children) == 2 and modal.callsign.max_length == 32

    asyncio.run(run())


def test_dropdown_rejects_forged_choices_and_other_owner(store, monkeypatch):
    request = MagicMock(spec=discord.Interaction)
    request.response.is_done.return_value = False
    request.response.send_message = AsyncMock()
    request.response.edit_message = AsyncMock()
    monkeypatch.setattr(
        "girlframe.discord_adapter.onboarding.viewer_from_interaction", lambda i: PLAYER
    )

    async def run():
        view = CharacterSelectionView(store, PLAYER.user_id, None)
        await view.choose("girl", "ADMINISTRATOR", request)
        assert view.girl is None
        await view.choose("girl", "MOCKINGBIRD", request)
        await view.choose("frame", "JANUS-B", request)
        assert not view.continue_button.disabled
        monkeypatch.setattr(
            "girlframe.discord_adapter.onboarding.viewer_from_interaction", lambda i: ADMIN
        )
        await view.choose("girl", "OLDGEN", request)
        assert view.girl == "MOCKINGBIRD"

    asyncio.run(run())


@pytest.mark.parametrize(
    "changes",
    [{"girl_playbook": "Administrator"}, {"frame_playbook": "arbitrary"}, {"callsign": "A" * 33}],
)
def test_backend_rejects_unknown_role_labels_and_oversize_nicknames(changes):
    values = {
        "callsign": "SORROW",
        "girl_playbook": "MOCKINGBIRD",
        "frame_playbook": "JANUS-B",
    } | changes
    with pytest.raises(ValidationError):
        DraftInput.model_validate(values)


def test_sorrow_sync_creates_safe_roles_and_nickname_preserves_unrelated_roles(store):
    save_sorrow(store)
    job = store.sync_job(PLAYER)
    assert job["state"] == "pending" and "PRIVATE_CANARY" not in job["desired_json"]
    guild = Guild()
    sync = CharacterTagSynchronizer(store)
    message = asyncio.run(sync.sync(PLAYER, DiscordCharacterTagGateway(guild)))
    assert "synchronized" in message and guild.member.nick == "SORROW"
    assert {request["name"] for request in guild.created} == {"MOCKINGBIRD", "JANUS-B"}
    assert 91 in {role.id for role in guild.member.roles}
    assert 90 not in {
        role.id for role in guild.member.roles
    }  # Unowned same-name admin role ignored.
    assert {role.name for role in guild.member.roles if role.id >= 20 and role.id < 90} == {
        "MOCKINGBIRD",
        "JANUS-B",
    }
    assert store.sync_job(PLAYER)["state"] == "complete"
    asyncio.run(sync.sync(PLAYER, DiscordCharacterTagGateway(guild)))
    assert len(guild.created) == 2


def test_edit_replaces_only_owned_labels(store):
    save_sorrow(store)
    guild = Guild()
    sync = CharacterTagSynchronizer(store)
    asyncio.run(sync.sync(PLAYER, DiscordCharacterTagGateway(guild)))
    store.save_draft(
        PLAYER,
        "edit",
        1,
        DraftInput(callsign="SORROW", girl_playbook="OLDGEN", frame_playbook="JANUS"),
    )
    asyncio.run(sync.sync(PLAYER, DiscordCharacterTagGateway(guild)))
    assert {role.name for role in guild.member.roles} == {
        "everyone",
        "Community",
        "OLDGEN",
        "JANUS",
    }
    assert len(guild.member.removed) == 2


def test_permissions_failure_does_not_lose_draft_and_retry_recovers(store):
    save_sorrow(store)
    guild = Guild()
    guild.me.guild_permissions.manage_roles = False
    sync = CharacterTagSynchronizer(store)
    message = asyncio.run(sync.sync(PLAYER, DiscordCharacterTagGateway(guild)))
    assert "Manage Roles" in message and guild.member.nick == "SORROW"
    assert (
        store.draft(PLAYER)["callsign"] == "SORROW" and store.sync_job(PLAYER)["state"] == "pending"
    )
    guild.me.guild_permissions.manage_roles = True
    asyncio.run(sync.sync(PLAYER, DiscordCharacterTagGateway(guild)))
    assert store.sync_job(PLAYER)["state"] == "complete" and len(guild.created) == 2


def test_owner_cannot_be_renamed_but_roles_succeed_without_false_success(store):
    save_sorrow(store)
    guild = Guild()
    guild.owner_id = PLAYER.user_id
    message = asyncio.run(
        CharacterTagSynchronizer(store).sync(PLAYER, DiscordCharacterTagGateway(guild))
    )
    assert "server owner" in message and not guild.member.edits
    assert "nickname matches" not in message and len(guild.member.added) == 2


def test_nickname_hierarchy_failure_is_retryable(store):
    save_sorrow(store)
    guild = Guild()
    guild.roles[91].position = 20
    sync = CharacterTagSynchronizer(store)
    message = asyncio.run(sync.sync(PLAYER, DiscordCharacterTagGateway(guild)))
    assert "highest role" in message and not guild.member.edits
    guild.roles[10].position = 30
    asyncio.run(sync.sync(PLAYER, DiscordCharacterTagGateway(guild)))
    assert guild.member.nick == "SORROW" and store.sync_job(PLAYER)["state"] == "complete"


def test_unknown_role_create_never_duplicates_and_does_not_adopt_by_name(store):
    save_sorrow(store)
    guild = Guild()
    guild.unknown_create = True
    sync = CharacterTagSynchronizer(store)
    asyncio.run(sync.sync(PLAYER, DiscordCharacterTagGateway(guild)))
    guild.unknown_create = False
    message = asyncio.run(sync.sync(PLAYER, DiscordCharacterTagGateway(guild)))
    assert "review" in message and len(guild.created) == 1
    assert not guild.member.added and store.sync_job(PLAYER)["state"] == "pending"


def test_changed_managed_role_permissions_are_not_granted(store):
    save_sorrow(store)
    guild = Guild()
    sync = CharacterTagSynchronizer(store)
    asyncio.run(sync.sync(PLAYER, DiscordCharacterTagGateway(guild)))
    next(
        role for role in guild.roles.values() if role.name == "JANUS-B"
    ).permissions = discord.Permissions(administrator=True)
    store.queue_sync(PLAYER, "retry")
    message = asyncio.run(sync.sync(PLAYER, DiscordCharacterTagGateway(guild)))
    assert "unsafe permissions" in message and len(guild.member.added) == 2


def test_old_acknowledgement_cannot_clear_newer_draft_job(store):
    save_sorrow(store)
    guild = Guild()
    sync = CharacterTagSynchronizer(store)
    guild.member.on_add = lambda: store.save_draft(
        PLAYER,
        "newer",
        1,
        DraftInput(callsign="NEW CALLSIGN", girl_playbook="OLDGEN", frame_playbook="JANUS"),
    )
    message = asyncio.run(sync.sync(PLAYER, DiscordCharacterTagGateway(guild)))
    assert "newer draft" in message and store.sync_job(PLAYER)["revision"] == 2
    assert store.sync_job(PLAYER)["state"] == "pending"
    asyncio.run(sync.sync(PLAYER, DiscordCharacterTagGateway(guild)))
    assert guild.member.nick == "NEW CALLSIGN" and store.sync_job(PLAYER)["state"] == "complete"


def test_role_claim_is_catalog_and_guild_scoped(store):
    save_sorrow(store)
    with pytest.raises(WorkflowError):
        store.claim_role(PLAYER, "girl:ADMINISTRATOR")
    assert set(json.loads(store.sync_job(PLAYER)["desired_json"])) == {
        "callsign",
        "girl_playbook",
        "frame_playbook",
    }


def test_renamed_owned_role_is_not_silently_assigned(store):
    save_sorrow(store)
    guild = Guild()
    sync = CharacterTagSynchronizer(store)
    asyncio.run(sync.sync(PLAYER, DiscordCharacterTagGateway(guild)))
    next(role for role in guild.roles.values() if role.name == "JANUS-B").name = "Repurposed"
    store.queue_sync(PLAYER, "retry")
    message = asyncio.run(sync.sync(PLAYER, DiscordCharacterTagGateway(guild)))
    assert "renamed" in message and len(guild.member.added) == 2


def test_member_departure_never_creates_or_assigns_roles(store):
    save_sorrow(store)
    guild = Guild()
    guild.missing_member = True
    message = asyncio.run(
        CharacterTagSynchronizer(store).sync(PLAYER, DiscordCharacterTagGateway(guild))
    )
    assert "membership" in message and not guild.created and not guild.member.edits
    assert store.sync_job(PLAYER)["state"] == "pending"


def test_deleted_owned_role_is_recreated_from_known_id_without_adopting_names(store):
    save_sorrow(store)
    guild = Guild()
    sync = CharacterTagSynchronizer(store)
    asyncio.run(sync.sync(PLAYER, DiscordCharacterTagGateway(guild)))
    removed = next(role.id for role in guild.member.roles if role.name == "MOCKINGBIRD")
    del guild.roles[removed]
    guild.member.roles = [role for role in guild.member.roles if role.id != removed]
    store.queue_sync(PLAYER, "retry")
    message = asyncio.run(sync.sync(PLAYER, DiscordCharacterTagGateway(guild)))
    assert "synchronized" in message and len(guild.created) == 3
    assert 90 not in {role.id for role in guild.member.roles}


def test_pending_role_job_survives_reconstructed_store(store):
    from girlframe.services.onboarding import OnboardingStore

    save_sorrow(store)
    restarted = OnboardingStore(store.engine, store.policy)
    guild = Guild()
    asyncio.run(CharacterTagSynchronizer(restarted).sync(PLAYER, DiscordCharacterTagGateway(guild)))
    assert restarted.sync_job(PLAYER)["state"] == "complete" and guild.member.nick == "SORROW"


def test_reconnect_does_not_duplicate_retry_worker_and_close_cancels_it(store):
    from girlframe.discord_adapter.bot import ReadOnlyDiscordBot
    from girlframe.services.read_only_bot import ReadOnlyBotService

    async def run():
        entered = asyncio.Event()
        async with ReadOnlyDiscordBot(
            store.policy, ReadOnlyBotService(store.policy, MagicMock()), None, store
        ) as bot:

            async def worker():
                entered.set()
                await asyncio.Event().wait()

            bot._sync_character_tags = worker
            await bot.on_ready()
            await entered.wait()
            task = bot._tag_worker
            await bot.on_ready()
            assert bot._tag_worker is task
            await bot.close()
            assert task.cancelled()

    asyncio.run(run())
