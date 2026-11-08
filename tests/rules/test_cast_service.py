import asyncio
from uuid import uuid4

import pytest
from test_actor_service import pc_ref, ready
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger_fixture
from test_m2_game import Gateway, start, state, tick

from girlframe.database import tables as t
from girlframe.delivery.m2_worker import GameWorker
from girlframe.engine.m3_actor_state import ActorRef, CastRole, SceneCast
from girlframe.services.m3_cast import CastService
from girlframe.services.onboarding import WorkflowError

ledger = ledger_fixture


def change(svc, viewer, action, ref=None, key=None, channel=900):
    view = svc.view(viewer, channel)
    return svc.change(
        viewer,
        key or str(uuid4()),
        channel,
        view["game_revision"],
        view["cast_revision"],
        action,
        ref,
    )


def test_legacy_cast_has_original_character_ids_and_facilitator_is_not_a_physical_handler(ledger):
    actors, game = ready(ledger)
    svc = CastService(actors)
    before = state(game)
    view = svc.view(PLAYER, 900)
    assert view["legacy"] and view["facilitator"] == 1 and len(view["roles"]) == 2
    assert all(x["ref"]["kind"] == "pilot" for x in view["roles"])
    assert next(x for x in view["roles"] if x["ref"]["entity"] == "2")["ref"] == pc_ref(
        actors, game
    ).model_dump(mode="json")
    assert state(game) == before and not before.scene_casts


def test_same_human_can_cast_npc_and_girl_separately_without_revealing_private_npc(ledger):
    actors, game = ready(ledger)
    svc, npc = CastService(actors), ActorRef(kind="npc", entity="secret-npc")
    before = state(game)
    view = svc.view(PLAYER, 900)
    outcome = svc.change(
        PLAYER, "cast-once", 900, view["game_revision"], view["cast_revision"], "join", npc
    )
    assert (
        svc.change(
            PLAYER, "cast-once", 900, view["game_revision"], view["cast_revision"], "join", npc
        )
        == outcome
    )
    after = state(game)
    cast = after.scene_casts[0]
    assert len(cast.roles) == 3 and sum(x.controller == 2 for x in cast.roles) == 2
    assert cast.roles[-1].source_event
    assert after.sheets == before.sheets and after.world == before.world
    assert "PRIVATE_NPC" in str(svc.view(PLAYER, 900))
    assert "PRIVATE_NPC" not in str(svc.view(OTHER, 900))
    assert "secret-npc" not in str(svc.view(ADMIN, 900))
    with ledger.engine.connect() as c:
        assert game.scene(c, 900)["participants"] == [1, 2, 3]
    with pytest.raises(WorkflowError, match="actor-aware"):
        start(game)
    assert game.dice.calls == 0
    for method in (game.join_scene, game.leave_scene):
        with pytest.raises(WorkflowError, match="/mission cast"):
            method(PLAYER, str(uuid4()), 900)
    change(svc, PLAYER, "withdraw", npc)
    assert start(game) and game.dice.calls == 0


def test_npc_human_does_not_acquire_their_girls_participation_and_facilitating_has_own_exit(ledger):
    actors, game = ready(ledger)
    svc, npc = CastService(actors), ActorRef(kind="npc", entity="secret-npc")
    change(svc, PLAYER, "join", npc)
    change(svc, PLAYER, "withdraw", pc_ref(actors, game))
    with ledger.engine.connect() as c:
        assert game.scene(c, 900)["participants"] == [1, 3]
    own = svc.view(PLAYER, 900)
    assert [x["ref"]["kind"] for x in own["roles"] if x["own"]] == ["npc"]
    change(svc, ADMIN, "withdraw_facilitator")
    assert svc.view(ADMIN, 900)["facilitator"] is None
    change(svc, ADMIN, "facilitate")
    assert svc.view(ADMIN, 900)["facilitator"] == 1
    with pytest.raises(WorkflowError):
        change(svc, PLAYER, "facilitate")


def test_pending_play_and_chat_restoration_prevent_cast_changes_without_new_dice(ledger):
    actors, game = ready(ledger)
    svc = CastService(actors)
    action = start(game)
    worker, gateway = GameWorker(game), Gateway()
    before = state(game)
    with pytest.raises(WorkflowError, match="Restore chat"):
        change(svc, PLAYER, "join", ActorRef(kind="npc", entity="secret-npc"))
    assert state(game) == before and game.dice.calls == 0
    tick(worker, gateway)
    receipt = game.inspect(PLAYER, action)["receipt"]
    game.abort(ADMIN, "abort-before-recast", action)
    with pytest.raises(WorkflowError, match="Restore chat"):
        change(svc, PLAYER, "join", ActorRef(kind="npc", entity="secret-npc"))
    tick(worker, gateway, 5)
    change(svc, PLAYER, "join", ActorRef(kind="npc", entity="secret-npc"))
    assert game.inspect(PLAYER, action)["receipt"] == receipt and game.dice.calls == 1


def test_controller_change_requires_old_cast_withdrawal_and_never_changes_the_girl(ledger):
    actors, game = ready(ledger)
    svc, npc = CastService(actors), ActorRef(kind="npc", entity="secret-npc")
    change(svc, PLAYER, "join", npc)
    before_sheet = state(game).sheets["2"]
    with ledger.transaction() as c:
        saved = state(game)
        from girlframe.engine.m3_world import update

        saved.world = update(
            saved.world, npcs=(saved.world.npcs[0].model_copy(update={"controller": 3}),)
        )
        game.event(c, 3, "synthetic-handoff", "synthetic.controller_change", saved)
    assert next(
        x for x in svc.view(OTHER, 900)["roles"] if x["ref"] == npc.model_dump(mode="json")
    )["stale"]
    previous = next(
        x for x in svc.view(PLAYER, 900)["roles"] if x["ref"] == npc.model_dump(mode="json")
    )
    assert previous["own"] and previous["stale"] and "PRIVATE_NPC_NAME" not in previous["label"]
    for viewer, action in ((OTHER, "join"), (OTHER, "withdraw")):
        with pytest.raises(WorkflowError):
            change(svc, viewer, action, npc)
    change(svc, PLAYER, "withdraw", npc)
    change(svc, OTHER, "join", npc)
    assert state(game).scene_casts[0].roles[-1].controller == 3
    assert state(game).sheets["2"] == before_sheet


def test_character_replacement_cannot_inherit_original_legacy_join_or_cast_resources(ledger):
    from test_actor_service import replace_profile_id

    actors, game = ready(ledger)
    svc = CastService(actors)
    original = pc_ref(actors, game)
    replace_profile_id(ledger, 2)
    view = svc.view(PLAYER, 900)
    assert any(x["stale"] and x["ref"] == original.model_dump(mode="json") for x in view["roles"])
    change(svc, PLAYER, "join", ActorRef(kind="npc", entity="secret-npc"))
    assert state(game).scene_casts[0].roles[0].actor == original
    change(svc, PLAYER, "withdraw", original)
    assert all(
        x.actor.kind != "pilot" or x.controller != 2 for x in state(game).scene_casts[0].roles
    )


def test_paused_join_is_blocked_but_owned_withdrawal_is_ooc_and_policy_revocation_still_applies(
    ledger,
):
    actors, game = ready(ledger)
    svc, npc = CastService(actors), ActorRef(kind="npc", entity="secret-npc")
    change(svc, PLAYER, "join", npc)
    ledger.safety(OTHER, "pause-cast", ledger.status(OTHER)["revision"], pause=True)
    with pytest.raises(WorkflowError, match="SAFETY_PAUSED"):
        change(svc, ADMIN, "join", ActorRef(kind="handler", entity="1"))
    change(svc, PLAYER, "withdraw", npc)
    policy = ledger.policy
    ledger.policy = policy.model_copy(update={"m3_approval": None})
    with pytest.raises(WorkflowError, match="M3_REVIEW_PENDING"):
        change(svc, PLAYER, "withdraw", pc_ref(actors, game))


def test_cast_atomic_rollback_restart_rebuild_and_close_preserve_source_links(ledger, monkeypatch):
    actors, game = ready(ledger)
    svc, npc = CastService(actors), ActorRef(kind="npc", entity="secret-npc")
    before = state(game)
    event = svc.game.event

    def fail(*args, **kwargs):
        event(*args, **kwargs)
        raise RuntimeError("synthetic after-cast failure")

    monkeypatch.setattr(svc.game, "event", fail)
    with pytest.raises(RuntimeError):
        change(svc, PLAYER, "join", npc, key="rollback-cast")
    assert state(game) == before
    monkeypatch.setattr(svc.game, "event", event)
    change(svc, PLAYER, "join", npc, key="rollback-cast")
    cast = state(game).scene_casts[0]
    assert CastService(actors).view(PLAYER, 900) == svc.view(PLAYER, 900)
    game.rebuild()
    assert state(game).scene_casts[0] == cast
    game.close_scene(ADMIN, "close-cast", 900)
    assert not state(game).scene_casts[0].open
    game.bind_scene(ADMIN, "rebind-cast", 900)
    change(svc, PLAYER, "join", npc)
    assert len(state(game).scene_casts) == 2
    assert state(game).scene_casts[1].id != cast.id


def test_girl_cannot_join_another_scene_while_legacy_scene_still_contains_her(ledger):
    actors, game = ready(ledger)
    svc = CastService(actors)
    game.bind_scene(ADMIN, "second-scene", 901)
    with pytest.raises(WorkflowError, match="current scene"):
        change(svc, PLAYER, "join", pc_ref(actors, game), channel=901)


def test_missing_actual_scene_source_is_not_fabricated_from_current_profile(ledger):
    actors, game = ready(ledger)
    with ledger.transaction() as c:
        c.execute(
            t.commands.delete().where(
                t.commands.c.campaign_id == ledger.campaign_id,
                t.commands.c.interaction_key == "bind",
            )
        )
    with pytest.raises(WorkflowError, match="SOURCE_CAST_MISSING"):
        CastService(actors).view(PLAYER, 900)


def test_native_scene_role_selector_is_owner_bound_and_confirmation_is_explicit(ledger):
    from test_mission_ui import current

    from girlframe.discord_adapter.m3_cast import open_cast

    actors, game = ready(ledger)
    svc = CastService(actors)

    async def run():
        viewer = current(2)
        viewer.channel_id = 900
        await viewer.response.defer(ephemeral=True)
        await open_cast(viewer, svc)
        picker = viewer.edit_original_response.call_args.kwargs["view"]
        assert not await picker.interaction_check(current(3))
        key = next(x for x, label in picker.options if "PRIVATE_NPC_NAME" in label)
        review = current(2, 14501)
        await review.response.defer(ephemeral=True)
        await picker.open_item(review, key)
        form = review.edit_original_response.call_args.kwargs["view"]
        assert not state(game).scene_casts
        form.values["confirm"] = ("yes",)
        await form.confirm.callback(current(2, 14502))
        assert form.completed and state(game).scene_casts[0].roles[-1].actor.kind == "npc"

    asyncio.run(run())


def test_cast_model_rejects_duplicate_actor_and_unproven_facilitator():
    from pydantic import ValidationError

    ref = ActorRef(kind="npc", entity="npc")
    role = CastRole(actor=ref, controller=2, source_event="event")
    with pytest.raises(ValidationError):
        SceneCast(id="scene", channel=900, roles=(role, role))
    with pytest.raises(ValidationError):
        SceneCast(id="scene", channel=900, facilitator=1)
    handler = ActorRef(kind="handler", entity="1")
    context = ActorRef(kind="handler", entity="1", incarnation="new-context")
    with pytest.raises(ValidationError):
        SceneCast(
            id="scene",
            channel=900,
            roles=(
                CastRole(actor=handler, controller=1, source_event="first"),
                CastRole(actor=context, controller=1, source_event="second"),
            ),
        )
