"""An actual nearby Director owns Handler physiology, not an NPC manifestation Tag."""

import asyncio

import pytest
import sqlalchemy as sa
from test_cast_service import change
from test_harpy_actor_plays import ready
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Gateway, answer, pass_tags, state, tick
from test_mission_ui import current

from girlframe.database import tables as t
from girlframe.delivery.m2_worker import GameWorker
from girlframe.discord_adapter.m2_forms import NativeForm
from girlframe.discord_adapter.m3_handler_void import open_handler_void
from girlframe.engine.m2 import PlayInput
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.services.m3_handler_void import HandlerVoidService
from girlframe.services.m3_missions import MissionService
from girlframe.services.onboarding import WorkflowError


def nearby_director(store, *, harpy=False):
    from uuid import uuid4

    from girlframe.engine.m3_director import enter
    from girlframe.engine.m3_world_state import Npc
    from girlframe.services.m3_npc_roles import NpcRoleService
    from girlframe.services.m3_world import WorldService

    actor_service, game, casts, actor = ready(store, faces=(4, 5))
    roles = NpcRoleService(WorldService(MissionService(store)))
    offered = roles.offer(
        ADMIN,
        "actual-dive-director-invite",
        state(game).revision,
        Npc(
            id="actual-nearby-director",
            name="Actual nearby Director",
            jobs=("director",),
            detail="A separately accepted actual Director body",
            controller=3,
            cell=(0, 0),
            revealed=True,
        ),
    )
    roles.respond(
        OTHER, "actual-dive-director-accept", offered["id"], state(game).revision, "accept"
    )
    target = ActorRef(kind="npc", entity="actual-nearby-director")
    with store.transaction() as c:
        canon, event = state(game), str(uuid4())
        canon = enter(canon, 1, target.entity, offered["id"], ("Composed", "Defiant"), event)
        game.event(
            c,
            1,
            "actual-source-director-presence",
            "synthetic.actual_director_presence",
            canon,
            event_id=event,
        )
    change(
        casts,
        ADMIN,
        "join",
        ActorRef(kind="handler", entity="1", incarnation=state(game).director_contexts[-1].id),
    )
    change(casts, OTHER, "join", target)
    change(casts, OTHER, "adjudicate", target)
    worker, gateway = GameWorker(game), Gateway()
    body = PlayInput(
        play="dive_deep",
        context="Actual link communion near the Director",
        trigger_confirmed=True,
        heat=0,
    )
    if harpy:
        preview = actor_service.preview(PLAYER, 900, actor)
        identity = actor_service.begin(
            PLAYER,
            str(uuid4()),
            900,
            actor,
            preview["actor"]["source_sha256"],
            target,
            preview["cast_revision"],
            body,
        )["action_id"]
    else:
        identity = game.begin(PLAYER, str(uuid4()), 900, state(game).sheets["2"].revision, body)[
            "action_id"
        ]
    tick(worker, gateway, 3)
    pass_tags(game)
    answer(
        game,
        PLAYER,
        "dive_select",
        options=("nearby_npcs_gain_void",),
        text="The original communion affects the actual nearby Director",
    )
    answer(game, OTHER, "dive_effect", fields={})
    return game, worker, gateway, identity, target, state(game).handler_void[-1].work


@pytest.mark.parametrize("harpy", [False, True])
def test_actual_director_only_nearby_dive_uses_owned_physiology_and_true_native_removal(
    ledger, harpy
):
    game, worker, gateway, identity, target, work = nearby_director(ledger, harpy=harpy)
    service = HandlerVoidService(ledger, game)
    before = state(game)
    original = next(x for x in before.world.npcs if x.id == target.entity)
    assert original.tags == ()
    assert before.handler_void[-1].actor == target
    assert game.inspect(PLAYER, identity)["state"] == "awaiting_choices"
    assert game.dice.calls == 1
    with pytest.raises(WorkflowError):
        service.get(ADMIN, work)

    async def remove():
        caller = current(3, 99331)
        await caller.response.defer(ephemeral=True)
        await open_handler_void(caller, service, work)
        form = caller.edit_original_response.call_args.kwargs["view"]
        assert isinstance(form, NativeForm)
        form.values.update(
            choice=("knife",),
            site="Actual left forearm",
            manifestation=("none",),
            account="The original Director cuts out the actual corruption; the wound remains",
        )
        await form.confirm.callback(current(3, 99332))
        assert form.completed

    asyncio.run(remove())
    after = state(game)
    assert after.handler_void[-1].phase == "removed"
    assert after.handler_void[-1].wound and after.handler_heat == before.handler_heat
    assert after.sheets == before.sheets
    assert next(x for x in after.world.npcs if x.id == target.entity).tags == ()
    assert game.inspect(PLAYER, identity)["state"] == "complete" and game.dice.calls == 1
    with ledger.engine.connect() as c:
        rows = list(
            c.execute(
                sa.select(t.m2["m2_choices"].c.id).where(
                    t.m2["m2_choices"].c.kind == "dive_handler_void"
                )
            )
        )
        assert len(rows) == 1
        assert not c.scalar(
            sa.select(t.m2["m2_responses"].c.choice_id).where(
                t.m2["m2_responses"].c.choice_id == rows[0].id
            )
        )
    tick(worker, gateway, 6)
    with ledger.engine.connect() as c:
        assert game.lock(c, 900)["state"] == "released"


def test_actual_call_guest_chooses_nearby_director_void_under_original_receipt(ledger, monkeypatch):
    from uuid import uuid4

    from test_beneath_service import ready as source_ready
    from test_dive import choose
    from test_mockingbird_communion import respond

    from girlframe.engine import m3_physical
    from girlframe.engine.m3_actor_bonds import current_ref
    from girlframe.engine.m3_actors import resolve
    from girlframe.engine.m3_physical_state import InitialPlacement
    from girlframe.engine.m3_world_state import Board, Npc, World
    from girlframe.services import m3_mockingbird_call as call
    from girlframe.services.m3_actors import ActorService, profiles
    from girlframe.services.m3_cast import CastService
    from girlframe.services.m3_mockingbird_communion import CallService
    from girlframe.services.m3_npc_roles import NpcRoleService
    from girlframe.services.m3_world import WorldService

    game, worker, gateway = source_ready(ledger, (4, 5))
    monkeypatch.setattr(call, "enabled", lambda state, actor: True)
    approval = ledger.policy.m3_approval
    ledger.policy = ledger.policy.model_copy(
        update={
            "m3_approval": approval.model_copy(
                update={"subsystems": approval.subsystems | {"world"}}
            )
        }
    )
    with ledger.transaction() as c:
        canon = state(game)
        canon.world = World(board=Board(minimum=(-2, -2), maximum=(2, 2)), locations=())
        for owner, mode in ((2, "piloting"), (3, "outside_frame")):
            ref = current_ref(canon, owner)
            actual = resolve(
                canon, ref, profiles(c, ledger.campaign_id), require_current_profile=False
            )
            canon = m3_physical.initial(
                canon,
                profiles(c, ledger.campaign_id),
                InitialPlacement(
                    actor=ref,
                    frame_instance=actual.frame_instance,
                    girl_cell=(0, 0),
                    frame_cell=(0, 0),
                    mode=mode,
                    account="Actual source body and original Frame",
                    facts_confirmed=True,
                ),
                "actual-body-" + str(owner),
                "actual-facts-" + str(owner),
                "actual-reviewed-" + str(owner),
            )
        game.event(c, 1, str(uuid4()), "synthetic.actual_source_bodies", canon)
    roles = NpcRoleService(WorldService(MissionService(ledger)))
    offered = roles.offer(
        ADMIN,
        "actual-guest-director-offer",
        state(game).revision,
        Npc(
            id="guest-nearby-director",
            name="Actual nearby Director",
            jobs=("director",),
            controller=3,
            cell=(0, 0),
            revealed=True,
            detail="Actual independently existing nearby Director",
        ),
    )
    roles.respond(
        OTHER, "actual-guest-director-accept", offered["id"], state(game).revision, "accept"
    )
    target = ActorRef(kind="npc", entity="guest-nearby-director")
    casts = CastService(ActorService(MissionService(ledger)))
    change(casts, OTHER, "join", target)
    change(casts, OTHER, "adjudicate", target)
    identity = game.begin(
        PLAYER,
        "actual-guest-director-source-dive",
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play="dive_deep",
            context="Actual owned original Call communion",
            trigger_confirmed=True,
            heat=0,
            piloting=True,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    choose(game, PLAYER, call.BOARD)
    answer(
        game,
        PLAYER,
        "dive_effect",
        fields={"target": current_ref(state(game), 3).token},
        text="Actual original invitation and contact",
    )
    service = CallService(game)
    session = state(game).mockingbird.calls[-1].id
    respond(service, OTHER, session, "accept")
    respond(service, OTHER, session, "effect", option="nearby_npcs_gain_void")
    assert state(game).mockingbird.calls[-1].phase == "npc"
    respond(service, OTHER, session, "npc", manifestations={})
    work = state(game).handler_void[-1].work
    assert state(game).handler_void[-1].actor == target
    assert next(x for x in state(game).world.npcs if x.id == target.entity).tags == ()
    assert game.inspect(PLAYER, identity)["state"] == "awaiting_choices" and game.dice.calls == 1
    actual = HandlerVoidService(ledger, game)
    actual.choose(
        OTHER,
        "actual-guest-director-drugs",
        work,
        actual.get(OTHER, work)["revision"],
        "drugs",
        "Actual Director injects and stabilizes the localized corruption",
        site="Actual arm",
        manifestation="flesh",
    )
    assert state(game).handler_void[-1].phase == "stabilized"
    assert game.inspect(PLAYER, identity)["state"] == "complete" and game.dice.calls == 1
