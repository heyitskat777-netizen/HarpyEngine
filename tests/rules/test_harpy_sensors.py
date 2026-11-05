"""Printed Harpy questions are honest, diceless, private and source-owned."""

import asyncio
from uuid import uuid4

import pytest
import sqlalchemy as sa
from test_harpy_actor_plays import ready
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger_fixture
from test_m2_game import Gateway, answer, state, tick

from girlframe.database import tables as t
from girlframe.delivery.m2_worker import GameWorker
from girlframe.engine.m2 import ChoiceAnswer, PlayInput
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.services.m2_game import GameService
from girlframe.services.m3_actor_plays import ActorPlayService
from girlframe.services.onboarding import WorkflowError

ledger = ledger_fixture


def ask(svc, actor, **extra):
    view = svc.preview(PLAYER, 900, actor)
    values = dict(
        play="check_sensors",
        context="PRIVATE_QUESTION not from a fixed list?",
        trigger_confirmed=True,
        heat=0,
    )
    values.update(extra)
    return svc.begin(
        PLAYER,
        str(uuid4()),
        900,
        actor,
        view["actor"]["source_sha256"],
        ActorRef.model_validate(view["adjudicator"]["ref"]) if view["adjudicator"]["ref"] else None,
        view["cast_revision"],
        PlayInput(**values),
    )["action_id"]


def test_harpy_questions_have_no_roll_modifiers_heat_or_resource_award_and_private_honest_reply(
    ledger,
):
    svc, game, cast, actor = ready(ledger, heat=6)
    original = state(game)
    action = ask(svc, actor)
    worker, gateway = GameWorker(game), Gateway()
    tick(worker, gateway)
    assert not game.dice.calls and state(game).sheets == original.sheets
    assert state(game).native_harpies == original.native_harpies
    assert not game.choices(PLAYER) and not game.choices(OTHER)
    row = next(x for x in game.choices(ADMIN) if x["kind"] == "harpy_sensor_answers")
    assert "PRIVATE_QUESTION" in game.decision(ADMIN, row["id"])["context"]
    with pytest.raises(WorkflowError):
        game.decision(OTHER, row["id"])
    for rejected in (
        ChoiceAnswer(text="Actual answer", flag=False),
        ChoiceAnswer(text="Actual answer", options=("partial",), flag=True),
    ):
        with pytest.raises(WorkflowError, match="honestly"):
            game.respond(ADMIN, str(uuid4()), row["id"], row["revision"], rejected)
    answer(game, ADMIN, "harpy_sensor_answers", text="PRIVATE_HONEST_ANSWER", flag=True)
    saved = game.inspect(PLAYER, action)
    assert saved["state"] == "complete" and saved["receipt"] is None
    assert saved["result"]["answers"] == "PRIVATE_HONEST_ANSWER"
    assert saved["result"]["honest_attested"] is True
    assert "PRIVATE_" not in str(game.inspect(OTHER, action))
    assert not game.dice.calls and state(game).sheets == original.sheets
    assert state(game).native_harpies == original.native_harpies
    with ledger.engine.connect() as c:
        assert c.scalar(sa.select(sa.func.count()).select_from(t.m2["m2_receipts"])) == 0
    tick(worker, gateway, 5)
    assert "PRIVATE_" not in str(gateway.messages)


def test_harpy_questions_reject_heat_or_identity_commitment_before_creating_action(ledger):
    svc, game, cast, actor = ready(ledger, heat=6)
    original = state(game)
    for values in (dict(heat=6), dict(identity="actual-free", gain=1)):
        with pytest.raises(WorkflowError, match="without dice or Heat"):
            ask(svc, actor, **values)
    assert state(game) == original and not game.dice.calls
    with ledger.engine.connect() as c:
        assert not game.pending_actions(c)


def test_harpy_question_recovers_same_owned_question_after_restart_without_fake_receipt(ledger):
    svc, game, cast, actor = ready(ledger)
    action = ask(svc, actor)
    worker, gateway = GameWorker(game), Gateway()
    tick(worker, gateway)
    stale = next(x for x in game.choices(ADMIN) if x["kind"] == "harpy_sensor_answers")
    game.abort(ADMIN, "restore-chat-for-questions", action)
    tick(worker, gateway, 5)
    saved = svc.saved(PLAYER)[0]
    resumed = ActorPlayService(GameService(ledger, dice=game.dice))
    resumed.recover(PLAYER, "resume-owned-questions", action, saved["revision"])
    tick(worker, gateway)
    with pytest.raises(WorkflowError, match="STALE_CHOICE"):
        game.respond(
            ADMIN,
            "old-question-control",
            stale["id"],
            stale["revision"],
            ChoiceAnswer(text="PRIVATE_OLD_ANSWER", flag=True),
        )
    answer(game, ADMIN, "harpy_sensor_answers", text="Actual honest answer", flag=True)
    assert game.inspect(PLAYER, action)["state"] == "complete" and not game.dice.calls


def test_native_question_controls_offer_no_heat_and_actual_gm_answers_privately(ledger):
    from test_mission_ui import current

    from girlframe.discord_adapter.m2_ui import open_choice
    from girlframe.discord_adapter.m3_actor_plays import open_actor_play

    svc, game, cast, actor = ready(ledger)

    async def run():
        request = current(2, 266001)
        request.channel_id = 900
        await request.response.defer(ephemeral=True)
        await open_actor_play(request, game, actor)
        plays = request.edit_original_response.call_args.kwargs["view"]
        chosen = current(2, 266002)
        chosen.channel_id = 900
        await chosen.response.defer(ephemeral=True)
        await plays.open_item(chosen, "check_sensors")
        form = chosen.edit_original_response.call_args.kwargs["view"]
        assert {x.key for x in form.fields} == {"context", "confirm"}
        assert "rolls no dice" in form.instructions
        form.values.update(context="PRIVATE_QUESTION", confirm=("yes",))
        await form.confirm.callback(current(2, 266003))
        assert form.completed
        await GameWorker(game).tick(Gateway())
        row = next(x for x in game.choices(ADMIN) if x["kind"] == "harpy_sensor_answers")
        response = current(1, 266004)
        await response.response.defer(ephemeral=True)
        await open_choice(response, game, row["id"])
        native = response.edit_original_response.call_args.kwargs["view"]
        assert "PRIVATE\\_QUESTION" in native.instructions
        assert not await native.interaction_check(current(3))
        native.values.update(text="Actual honest answer", flag=("yes",))
        await native.confirm.callback(current(1, 266005))
        assert native.completed and not game.dice.calls

    asyncio.run(run())


def test_actual_selected_director_owns_harpy_sensor_answer_instead_of_campaign_gm(ledger):
    from test_cast_service import change

    from girlframe.engine.m3_world import update
    from girlframe.engine.m3_world_state import Npc

    svc, game, cast, actor = ready(ledger)
    director = ActorRef(kind="npc", entity="actual-scene-director")
    with ledger.transaction() as c:
        canon = state(game)
        canon.world = update(
            canon.world,
            npcs=(
                Npc(
                    id=director.entity,
                    name="Actual Director",
                    controller=3,
                    cell=(0, 0),
                    jobs=("director",),
                    detail="The actual introduced and human-controlled scene Director",
                ),
            ),
        )
        game.event(c, 1, "synthetic-director-source", "synthetic.world", canon)
    change(cast, OTHER, "join", director)
    change(cast, OTHER, "adjudicate", director)
    action = ask(svc, actor)
    tick(GameWorker(game), Gateway())
    assert not game.choices(ADMIN)
    row = next(x for x in game.choices(OTHER) if x["kind"] == "harpy_sensor_answers")
    with pytest.raises(WorkflowError):
        game.respond(
            ADMIN,
            "no-gm-proxy-answer",
            row["id"],
            row["revision"],
            ChoiceAnswer(flag=True, text="A different human cannot provide this owned answer"),
        )
    answer(game, OTHER, "harpy_sensor_answers", flag=True, text="The actual Director answers")
    assert game.inspect(PLAYER, action)["state"] == "complete" and not game.dice.calls


def test_real_converted_harpy_can_ask_without_recovered_pc_or_reusing_prior_roll(ledger):
    from test_cast_service import change
    from test_retained_tag_permissions import reborn_with_lock

    from girlframe.services.m3_actors import ActorService
    from girlframe.services.m3_cast import CastService
    from girlframe.services.m3_missions import MissionService

    game, worker, gateway, actor, permission, tag = reborn_with_lock(ledger)
    cast = CastService(ActorService(MissionService(ledger)))
    change(cast, PLAYER, "join", actor)
    svc = ActorPlayService(game)
    before, calls = state(game), game.dice.calls
    action = ask(svc, actor)
    tick(worker, gateway)
    answer(game, ADMIN, "harpy_sensor_answers", flag=True, text="Actual honest reply after birth")
    assert game.inspect(PLAYER, action)["receipt"] is None and game.dice.calls == calls
    assert state(game).harpy_states == before.harpy_states
    assert state(game).sheets == before.sheets and "2" not in before.sheets
    assert next(x for x in state(game).obligations if x.id == permission).state == "pending"


def test_original_director_human_can_finish_owned_question_after_actual_death_without_new_authority(
    ledger,
):
    from test_cast_service import change

    from girlframe.engine.m3_handler_play_state import Effect
    from girlframe.engine.m3_world import update
    from girlframe.engine.m3_world_state import Npc
    from girlframe.services.m3_battle_director import DirectorService
    from girlframe.services.m3_handler_plays import HandlerPlayService

    svc, game, cast, actor = ready(ledger)
    director = ActorRef(kind="npc", entity="original-scene-director")
    with ledger.transaction() as c:
        canon = state(game)
        canon.world = update(
            canon.world,
            npcs=(
                Npc(
                    id=director.entity,
                    name="Original Director",
                    controller=3,
                    cell=(0, 0),
                    jobs=("director",),
                    detail="Actual original scene Director",
                ),
            ),
        )
        game.event(c, 1, "synthetic-original-director", "synthetic.world", canon)
    change(cast, OTHER, "join", director)
    change(cast, OTHER, "adjudicate", director)
    plays = HandlerPlayService(ledger)
    grant = plays.start(ADMIN, "actual-director-damage-source", state(game).revision, (director,))[
        "id"
    ]
    plays.submit(
        ADMIN,
        "actual-director-damage",
        grant,
        state(game).revision,
        "mess",
        Effect(kind="damage", target=director, account="Actual strike against the Director"),
    )
    action = ask(svc, actor)
    worker, gateway = GameWorker(game), Gateway()
    tick(worker, gateway)
    question = next(x for x in game.choices(OTHER) if x["kind"] == "harpy_sensor_answers")
    with ledger.engine.connect() as c:
        work = c.scalar(
            sa.select(t.m3["m3_required_work"].c.id).where(
                t.m3["m3_required_work"].c.campaign_id == ledger.campaign_id,
                t.m3["m3_required_work"].c.kind == "director_damage",
            )
        )
    ending = DirectorService(ledger)
    ending.respond(
        OTHER,
        "actual-owned-director-death",
        work,
        ending.get(OTHER, work)["revision"],
        "death",
        "The actual Director dies from the source injury",
    )
    assert not next(x for x in state(game).world.npcs if x.id == director.entity).alive
    assert game.decision(OTHER, question["id"])["kind"] == "harpy_sensor_answers"
    answer(
        game,
        OTHER,
        "harpy_sensor_answers",
        flag=True,
        text="The original human finishes this already-owned procedural question",
    )
    assert game.inspect(PLAYER, action)["state"] == "complete" and not game.dice.calls
    tick(worker, gateway, 5)
    ask(svc, actor)
    tick(worker, gateway)
    assert not game.choices(OTHER)
    assert any(x["kind"] == "harpy_sensor_answers" for x in game.choices(ADMIN))
