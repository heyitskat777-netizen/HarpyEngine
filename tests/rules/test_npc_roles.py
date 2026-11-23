"""Separately played roles, including the Director, require a real human response."""

import asyncio
from concurrent.futures import ThreadPoolExecutor

import pytest
import sqlalchemy as sa
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger_fixture
from test_m2_game import state
from test_mission_ui import current
from test_world import initial
from test_world_service import ready

from girlframe.database import tables as t
from girlframe.discord_adapter.m3_npc_roles import open_invitation
from girlframe.engine import m3_npc_roles as rules
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_world_state import Npc, World
from girlframe.services.inbox import InboxService
from girlframe.services.m3_npc_roles import NpcRoleService
from girlframe.services.onboarding import WorkflowError

ledger = ledger_fixture


def director():
    return Npc(
        id="director",
        name="PRIVATE_DIRECTOR_NAME",
        jobs=("director",),
        detail="PRIVATE_DIRECTOR_DETAIL",
        controller=2,
        cell=(0, 0),
    )


def test_native_current_npc_owner_changes_ordinary_jobs_without_reassigning_sources(ledger):
    from test_cast_service import change

    from girlframe.discord_adapter.m2_forms import NativeForm
    from girlframe.discord_adapter.m3_cast import open_cast
    from girlframe.services.m3_actors import ActorService
    from girlframe.services.m3_cast import CastService

    world, game = ready(ledger)
    original = Npc(
        id="owned-staff",
        name="Actual staff",
        detail="An original person.",
        jobs=("guard", "prisoner"),
        cell=(0, 0),
        controller=PLAYER.user_id,
    )
    roles = NpcRoleService(world)
    invite = roles.offer(ADMIN, "invite-staff", state(game).revision, original)
    roles.respond(PLAYER, "accept-staff", invite["id"], state(game).revision, "accept")
    ref = ActorRef(kind="npc", entity=original.id)
    cast = CastService(ActorService(world.missions))
    change(cast, PLAYER, "join", ref)
    before = state(game)
    data = roles.jobs(PLAYER, 900, ref)
    assert data["jobs"] == ("guard",) and data["fixed"] == ("prisoner",)
    assert not {"director", "prisoner", "pilot_candidate"} & dict(data["options"]).keys()
    with pytest.raises(WorkflowError, match="original joined NPC controller"):
        roles.change_jobs(
            OTHER, "other-jobs", 900, before.revision, ref, ("mechanic",), "Not my NPC."
        )
    with pytest.raises(WorkflowError, match="ordinary jobs"):
        roles.change_jobs(
            PLAYER, "forge-director", 900, before.revision, ref, ("director",), "Changed."
        )
    with pytest.raises(WorkflowError, match="STALE_STATE"):
        roles.change_jobs(
            PLAYER, "stale-jobs", 900, before.revision - 1, ref, ("mechanic",), "Changed."
        )
    ledger.safety(OTHER, "pause-jobs", ledger.status(OTHER)["revision"], pause=True)
    with pytest.raises(WorkflowError, match="SAFETY_PAUSED"):
        roles.change_jobs(
            PLAYER, "paused-jobs", 900, before.revision, ref, ("mechanic",), "Changed."
        )
    ledger.safety(OTHER, "resume-jobs", ledger.status(OTHER)["revision"], pause=False)
    account = "PRIVATE_JOB_CHANGE"

    async def native():
        click = current(PLAYER.user_id, 89940)
        click.channel_id = 900
        await click.response.defer(ephemeral=True)
        await open_cast(click, cast)
        menu = click.edit_original_response.call_args.kwargs["view"]
        entry = next(x for x, _ in menu.options if x.startswith("jobs:"))
        edit = current(PLAYER.user_id, 89941)
        await edit.response.defer(ephemeral=True)
        await menu.open_item(edit, entry)
        form = edit.edit_original_response.call_args.kwargs["view"]
        assert isinstance(form, NativeForm) and form.values["jobs"] == ("guard",)
        form.values.update(jobs=("mechanic",), account=account)
        await form.confirm.callback(current(PLAYER.user_id, 89942))
        assert form.completed

    asyncio.run(native())
    saved = roles.change_jobs(PLAYER, "89942", 900, before.revision, ref, ("mechanic",), account)
    assert saved["jobs"] == ["prisoner", "mechanic"]
    actual = next(x for x in state(game).world.npcs if x.id == original.id)
    prior = next(x for x in before.world.npcs if x.id == original.id)
    assert actual.model_dump(exclude={"jobs"}) == prior.model_dump(exclude={"jobs"})
    assert account not in str(cast.view(OTHER, 900))
    ledger.engine.dispose()
    assert NpcRoleService(world).jobs(PLAYER, 900, ref)["jobs"] == ("mechanic",)


@pytest.mark.parametrize(
    "decision,actor,result",
    [("accept", 2, "accepted"), ("decline", 2, "declined"), ("withdraw", 1, "withdrawn")],
)
def test_role_response_is_owned_and_only_actual_acceptance_introduces_npc(decision, actor, result):
    world = initial()
    offered = rules.offer(world, 1, director(), "offer", "source")
    assert not world.npc_role_offers and not offered.npcs
    with pytest.raises(ValueError):
        rules.respond(offered, 1, 3, "offer", decision, "forged")
    saved = rules.respond(offered, 1, actor, "offer", decision, "response")
    assert saved.npc_role_offers[0].state == result
    assert len(saved.npcs) == (decision == "accept")
    assert World.model_validate_json(saved.model_dump_json()) == saved
    with pytest.raises(ValueError, match="pending"):
        rules.respond(saved, 1, actor, "offer", decision, "again")


def test_role_proposal_cannot_import_bonds_or_put_handler_in_director_role():
    world = initial()
    for npc in (
        director().model_copy(update={"controller": 1}),
        director().model_copy(update={"bonds": {"pilot:2": 2}}),
        director().model_copy(update={"custody_event": "invented"}),
    ):
        with pytest.raises(ValueError):
            rules.offer(world, 1, npc, "offer", "source")
    offered = rules.offer(world, 1, director(), "offer", "source")
    with pytest.raises(ValueError, match="unchanged Handler"):
        rules.respond(offered, 3, 2, "offer", "accept", "stale")
    with pytest.raises(ValueError):
        rules.offer(offered, 1, director(), "other", "source")


def offered(store):
    world, game = ready(store)
    svc = NpcRoleService(world)
    result = svc.offer(ADMIN, "offer-director", state(game).revision, director())
    return svc, game, result["id"]


def test_private_director_invitation_and_acceptance_preserve_scene_and_controller_ownership(ledger):
    svc, game, identity = offered(ledger)
    assert not state(game).world.npcs
    assert {x[0] for x in svc.members(ADMIN)["members"]} == {"2", "3"}
    other_world = InboxService(ledger).page(OTHER, category="world")
    assert all(x.identity != identity and x.task != "m3_npc_role" for x in other_world.window)
    assert all(x.identity == state(game).sheets["3"].character_id for x in other_world.window)
    assert "PRIVATE_DIRECTOR" not in str(InboxService(ledger).items(OTHER))
    with pytest.raises(WorkflowError):
        svc.get(OTHER, identity)
    data = svc.get(PLAYER, identity)
    with pytest.raises(WorkflowError):
        svc.respond(ADMIN, "cannot-accept-for-other", identity, data["game_revision"], "accept")
    result = svc.respond(PLAYER, "accept-director", identity, data["game_revision"], "accept")
    assert (
        svc.respond(PLAYER, "accept-director", identity, data["game_revision"], "accept") == result
    )
    assert state(game).world.npcs[0].controller == 2
    with pytest.raises(WorkflowError, match="different human"):
        svc.world.claim_npc(ADMIN, "cannot-take-director", state(game).revision, "director")
    with ledger.engine.connect() as c:
        metadata = str(list(c.scalars(sa.select(t.events.c.payload_json))))
        assert "PRIVATE_DIRECTOR" not in metadata
        assert not c.scalar(sa.select(sa.func.count()).select_from(t.m2["m2_actions"]))


def test_role_response_pause_rollback_and_concurrent_answers_cannot_duplicate_introduction(
    ledger, monkeypatch
):
    svc, game, identity = offered(ledger)
    before = state(game)
    ledger.safety(OTHER, "pause", ledger.status(OTHER)["revision"], pause=True)
    with pytest.raises(WorkflowError, match="SAFETY_PAUSED"):
        svc.respond(PLAYER, "paused", identity, before.revision, "accept")
    ledger.safety(OTHER, "resume", ledger.status(OTHER)["revision"], pause=False)
    original = svc.game.event

    def fail(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError("synthetic write failure")

    monkeypatch.setattr(svc.game, "event", fail)
    with pytest.raises(RuntimeError):
        svc.respond(PLAYER, "retry", identity, before.revision, "accept")
    assert state(game) == before
    monkeypatch.setattr(svc.game, "event", original)

    def attempt(key):
        try:
            return svc.respond(PLAYER, key, identity, before.revision, "accept")
        except WorkflowError:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(attempt, ("one", "two")))
    assert sum(x is not None for x in outcomes) == 1 and len(state(game).world.npcs) == 1


def test_native_role_invitation_needs_actual_recipient_confirmation(ledger):
    svc, game, identity = offered(ledger)

    async def run():
        viewer = current(2)
        await viewer.response.defer(ephemeral=True)
        await open_invitation(viewer, svc, identity)
        form = viewer.edit_original_response.call_args.kwargs["view"]
        assert not await form.interaction_check(current(1))
        assert not state(game).world.npcs
        form.values["decision"] = ("accept",)
        await form.confirm.callback(current(2, 951))
        assert form.completed and state(game).world.npcs[0].controller == 2

    asyncio.run(run())
