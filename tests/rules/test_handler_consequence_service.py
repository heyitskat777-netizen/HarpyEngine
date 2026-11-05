"""Real Handler choices preserve source work and OOC authority without reviving a body."""

import asyncio
from uuid import uuid4

import pytest
from test_ledger import ADMIN, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state
from test_mission_service import service
from test_mission_ui import current

from girlframe.discord_adapter.m3_handler_consequences import open_consequence
from girlframe.engine.m2 import TagState
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_handler_consequences import active_handler
from girlframe.services.handler_setup import HandlerService
from girlframe.services.m3_handler_consequences import HandlerConsequenceService, require
from girlframe.services.onboarding import WorkflowError


def pending(store, *, trigger="asset_damage"):
    _, game = service(store)
    approval = store.policy.m3_approval
    store.policy = store.policy.model_copy(
        update={
            "m3_approval": approval.model_copy(
                update={"subsystems": approval.subsystems | {"plays"}}
            )
        }
    )
    with store.transaction() as c:
        canon = state(game)
        canon.handler_heat = 6
        canon.handler_tags.append(
            TagState(id="actual-old-handler-tag", label="Old actual Tag", giver=2)
        )
        source = str(uuid4())
        canon, identity = require(
            game,
            c,
            canon,
            active_handler(canon),
            trigger=trigger,
            source_action=None,
            source_event=source,
            opponent=current_ref(canon, 2),
        )
        game.event(
            c, 2, str(uuid4()), "m3.synthetic_actual_handler_trigger", canon, event_id=source
        )
    return HandlerConsequenceService(store), game, identity


def test_actual_handler_injury_is_saved_and_patient_opponent_cannot_choose_for_handler(ledger):
    svc, game, identity = pending(ledger)
    data = svc.get(ADMIN, identity)
    with pytest.raises(WorkflowError):
        svc.respond(
            PLAYER,
            str(uuid4()),
            identity,
            data["game_revision"],
            "death",
            "Cannot choose another body",
        )
    outcome = svc.respond(
        ADMIN,
        "actual-persistent-injury",
        identity,
        data["game_revision"],
        "injury",
        "A broken wrist that remains injured after the scene",
    )
    assert (
        svc.respond(
            ADMIN,
            "actual-persistent-injury",
            identity,
            data["game_revision"],
            "injury",
            "A broken wrist that remains injured after the scene",
        )
        == outcome
    )
    assert active_handler(state(game)) is not None and not state(game).handler_archives
    assert svc.get(ADMIN, identity)["injuries"][0]["description"].startswith("A broken wrist")
    assert not svc.tasks(ADMIN)


def test_actual_handler_death_archives_body_but_keeps_the_actual_human_gm_appointment(ledger):
    svc, game, identity = pending(ledger, trigger="helpless")
    original = active_handler(state(game))
    data = svc.get(ADMIN, identity)
    svc.respond(
        ADMIN,
        "actual-original-handler-death",
        identity,
        data["game_revision"],
        "death",
        "The actual original Handler dies from this source",
    )
    canon = state(game)
    assert active_handler(canon) is None and canon.handler == ADMIN.user_id
    assert canon.handler_archives[-1].actor == original
    assert canon.handler_archives[-1].body.heat == 6
    assert not canon.handler_tags and canon.handler_heat == 0
    with ledger.engine.connect() as c:
        HandlerService(ledger).authorize(c, ADMIN)
        game.authorize(c, ADMIN, game=False)
    assert svc.get(ADMIN, identity)["choice"] == "death"


def test_native_handler_death_requires_exact_original_human_and_explicit_confirmation(ledger):
    svc, game, identity = pending(ledger)

    async def run():
        handler = current(1, 83101)
        await handler.response.defer(ephemeral=True)
        await open_consequence(handler, svc, identity)
        form = handler.edit_original_response.call_args.kwargs["view"]
        assert not await form.interaction_check(current(2, 83102))
        form.values.update(
            choice=("death",), account="Actual original body's ending", confirmation=""
        )
        await form.confirm.callback(current(1, 83103))
        assert not form.completed and not state(game).handler_archives
        form.values["confirmation"] = "END THIS HANDLER"
        await form.confirm.callback(current(1, 83104))
        assert form.completed

    asyncio.run(run())
    assert active_handler(state(game)) is None


def end_during(game):
    with game.store.transaction() as c:
        canon, event = state(game), str(uuid4())
        canon, identity = require(
            game,
            c,
            canon,
            active_handler(canon),
            trigger="asset_damage",
            source_action=None,
            source_event=event,
            opponent=current_ref(canon, 2),
        )
        game.event(c, 2, str(uuid4()), "m3.synthetic_actual_handler_damage", canon, event_id=event)
    svc = HandlerConsequenceService(game.store)
    svc.respond(
        ADMIN,
        str(uuid4()),
        identity,
        state(game).revision,
        "death",
        "Actual original Handler death while a GM ruling remains owed",
    )


def test_same_human_gm_can_finish_actual_pending_manual_defeat_after_fictional_body_death(ledger):
    from test_adjudication_service import forbid
    from test_defeat_service import required
    from test_m2_game import answer, pass_tags, tick

    from girlframe.engine.m2 import PlayInput
    from girlframe.services.m3_adjudication import AdjudicationService

    game, worker, gateway, parent = required(ledger)
    forbid(game, 2, "defeat")
    child = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play="defeat",
            parent=parent,
            heat=0,
            context="Actual required source",
            trigger_confirmed=True,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    end_during(game)
    assert active_handler(state(game)) is None
    row = next(x for x in game.choices(ADMIN) if x["kind"] == "manual_adjudication")
    service = AdjudicationService(ledger)
    view = service.get(ADMIN, row["id"])
    service.submit(
        ADMIN,
        str(uuid4()),
        row["id"],
        view["revision"],
        8,
        "My human GM role adjudicates without an invented living Handler body",
    )
    pass_tags(game)
    answer(
        game,
        PLAYER,
        "defeat_select",
        options=("escape_cockpit_choose_location",),
        text="The original Girl actually escapes the damaged cockpit",
    )
    assert game.inspect(PLAYER, child)["state"] == "complete"
    assert game.inspect(PLAYER, parent)["state"] == "complete"
    assert active_handler(state(game)) is None


def test_same_human_gm_can_judge_actual_keep_resistance_without_a_new_fictional_body(ledger):
    from test_dive import threshold_source
    from test_m2_game import answer, pass_tags, tick

    from girlframe.engine.m2 import PlayInput
    from girlframe.services.m3_void import VoidService

    game, worker, gateway, parent, work = threshold_source(ledger, girl="MOCKINGBIRD")
    game.dice.faces = (4, 4)
    child = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play="keep_your_head",
            source_work=work,
            parent=parent,
            heat=0,
            context="Actual optional resistance",
            trigger_confirmed=True,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    end_during(game)
    pass_tags(game)
    answer(game, PLAYER, "actor_keep", options=("in_control", "tough"), denied=("sexy",))
    answer(
        game,
        ADMIN,
        "handler_keep",
        flag=True,
        text="My actual human GM ruling is sufficient, without a revived Handler body",
    )
    assert VoidService(ledger).get(PLAYER, work)["stage"] == "prevented"
    assert game.inspect(PLAYER, child)["state"] == "complete"
    assert game.inspect(PLAYER, parent)["state"] == "complete"
    assert active_handler(state(game)) is None
