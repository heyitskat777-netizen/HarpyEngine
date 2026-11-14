"""A genuine earned AM source uses only the actual non-AM counterpart's roll."""

import asyncio
from uuid import uuid4

import pytest
from test_enforcer_requisitions import approved
from test_intracadre_marriage import FOUR, third_draft
from test_ledger import ADMIN, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import answer, state, tick
from test_physical_operations import place
from test_vatgrown_plays import _learn_daily_source, _learned_sex_interaction, ready

from girlframe.discord_adapter.m2_ui import open_choice
from girlframe.discord_adapter.m3_am_sex import open_am_sex
from girlframe.engine import m3_am_sex as am
from girlframe.engine import m3_mockingbird as mock
from girlframe.engine import m3_vatgrown_plays as vat
from girlframe.engine.m2 import PlayInput
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_mockingbird_state import SEX
from girlframe.services.creation_review import CreationReviewService
from girlframe.services.m3_actors import ActorService
from girlframe.services.m3_am_sex import SexService, lessons, prove_learned
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_mockingbird_plays import MockingbirdService
from girlframe.services.onboarding import WorkflowError


def test_genuine_earned_am_counterpart_zero_heat_roll_completion_and_once_use(
    ledger, tmp_path, monkeypatch
):
    import test_m2_game as game_fixture

    original_ready = game_fixture.ready

    def with_third(store, *args, **kwargs):
        result = original_ready(store, *args, **kwargs)
        third_draft(store)
        return result

    monkeypatch.setattr(game_fixture, "ready", with_third)
    game, worker, gateway, learning = ready(ledger, tmp_path, monkeypatch, teacher="AM")
    original_actor = gateway.actor

    async def actual_actor(identity):
        if str(identity) == str(FOUR.user_id):
            return FOUR
        return await original_actor(identity)

    monkeypatch.setattr(gateway, "actor", actual_actor)
    approved(
        ledger,
        game,
        tmp_path,
        monkeypatch,
        extra=(vat.EXPERIMENT, vat.INVESTMENT, vat.SEX, vat.BRUTALIZE, am.RULE, mock.SEX),
    )
    lesson = _learn_daily_source(game, worker, gateway, learning, am.RULE)
    review = CreationReviewService(ledger)
    checked = review.get(FOUR)
    assert checked.sheet.ready_for_rules_review, checked.sheet.issues
    review.save(FOUR, str(uuid4()), checked.saved_revision, checked.fingerprint)
    game.activate(FOUR, str(uuid4()), review.get(FOUR).fingerprint)
    with ledger.transaction() as c:
        placed = place(state(game), 4, mode="outside_frame")
        game.event(c, 1, str(uuid4()), "synthetic.initial_third_body_position", placed)
    learner, target = current_ref(state(game), 2), current_ref(state(game), 4)
    cast = CastService(ActorService(MissionService(ledger)))
    current = cast.view(FOUR, 900)
    cast.change(
        FOUR, str(uuid4()), 900, current["game_revision"], current["cast_revision"], "join", target
    )
    assert state(game).sheets["2"].girl == "VATGROWN"
    assert state(game).sheets["4"].girl == "MOCKINGBIRD"
    service = SexService(game)
    source = service.invite(
        PLAYER,
        str(uuid4()),
        900,
        target,
        state(game).revision,
        "PRIVATE actual learned AM source with original counterpart",
        learned_source=lesson.id,
    )["id"]
    assert am.source(state(game), source).mode == "counterpart"
    service.confirm(
        FOUR,
        str(uuid4()),
        source,
        state(game).revision,
        True,
        "My actual independent voluntary confirmation",
    )
    mockingbird = MockingbirdService(game)
    trigger = mockingbird.propose(
        FOUR,
        str(uuid4()),
        900,
        target,
        SEX,
        (learner,),
        "Actual original counterpart's own voluntary Play",
    )["id"]
    mockingbird.attest(PLAYER, str(uuid4()), trigger, learner, True)
    calls = game.dice.calls
    own_heat = state(game).sheets["2"].heat
    game.dice.faces = (4, 5)
    action = game.begin(
        FOUR,
        str(uuid4()),
        900,
        state(game).sheets["4"].revision,
        PlayInput(
            play=SEX,
            source_work=trigger,
            heat=0,
            trigger_confirmed=True,
            context="Actual independently confirmed original counterpart performance",
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    for human in (PLAYER, FOUR, ADMIN):
        answer(game, human, "tag_window", options=("pass",))
    # Other original teacher, if actually addressed, also independently passes.
    from test_ledger import OTHER

    answer(game, OTHER, "tag_window", options=("pass",))

    async def choose():
        row = next(x for x in game.choices(FOUR) if x["kind"] == "mockingbird_sex_select")
        opened = _learned_sex_interaction(4)
        await opened.response.defer(ephemeral=True)
        await open_choice(opened, game, row["id"])
        form = opened.edit_original_response.call_args.kwargs["view"]
        form.values.update(option=("starry",), capability=("deception",))
        sent = _learned_sex_interaction(4)
        await form.confirm.callback(sent)
        assert form.completed, (sent.response.events, sent.edit_original_response.call_args_list)

    asyncio.run(choose())
    assert game.inspect(FOUR, action)["state"] == "complete"
    receipt = game.inspect(FOUR, action)["receipt"]
    tick(worker, gateway, 5)
    with pytest.raises(WorkflowError):
        service.bind_counterpart(ADMIN, str(uuid4()), source, state(game).revision, action)

    async def operate(viewer, operation, **values):
        opened = _learned_sex_interaction(viewer.user_id)
        await opened.response.defer(ephemeral=True)
        await open_am_sex(opened, service, identity=source)
        menu = opened.edit_original_response.call_args.kwargs["view"]
        menu.values["operation"] = (operation,)
        selected = _learned_sex_interaction(viewer.user_id)
        await menu.confirm.callback(selected)
        form = selected.edit_original_response.call_args.kwargs["view"]
        form.values.update(values)
        sent = _learned_sex_interaction(viewer.user_id)
        await form.confirm.callback(sent)
        assert form.completed, (sent.response.events, sent.edit_original_response.call_args_list)

    counterpart_before_bind = state(game).sheets["4"].model_dump()
    asyncio.run(operate(PLAYER, "bind", action=(action,)))
    for human in (PLAYER, FOUR):
        asyncio.run(
            operate(
                human,
                "perform",
                circuits=("no",),
                account="My actual original performance, no circuit access",
            )
        )
    with ledger.engine.connect() as c:
        final = prove_learned(game, c, state(game), source)
        assert final.counterpart_action == action and final.used_event and final.effect_event
        assert final.phase == "complete" and final.completed_event
        assert not lessons(game, c, state(game), learner)
    assert game.dice.calls == calls + 1 and state(game).sheets["2"].heat == own_heat
    assert game.inspect(FOUR, action)["receipt"] == receipt
    assert state(game).sheets["4"].model_dump() == counterpart_before_bind
    completed = state(game)
    with pytest.raises(WorkflowError):
        service.bind_counterpart(PLAYER, str(uuid4()), source, completed.revision, action)
    assert state(game) == completed
    with pytest.raises(WorkflowError):
        service.perform(
            FOUR,
            str(uuid4()),
            source,
            completed.revision,
            "Cannot repeat the actual original performance",
            circuits_touched=False,
        )
    assert state(game) == completed
    assert (
        next(x for x in state(game).sheets["2"].tags if x.label == "Starry-Eyed").giver_actor
        == target
    )
    grant = next(x for x in state(game).sheets["2"].girl_runtime.learned_plays if x.id == lesson.id)
    assert grant.used_event and grant.claimed_action is None and grant.rolled_event is None
    with pytest.raises(WorkflowError):
        service.withdraw(
            PLAYER, str(uuid4()), source, state(game).revision, "No refund after real use"
        )
    assert "PRIVATE actual learned AM" not in str(gateway.messages)
