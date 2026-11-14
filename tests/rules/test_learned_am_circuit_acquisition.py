"""Real mandatory learning stores knowledge; it never fabricates an adjusted mind."""

from uuid import uuid4

import pytest
from test_enforcer_requisitions import approved
from test_ledger import OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state
from test_vatgrown_plays import _learn_daily_source, ready

from girlframe.engine import m3_am as scrutiny
from girlframe.engine import m3_am_code as code
from girlframe.engine import m3_vatgrown_plays as vat
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_girl_runtime_state import has_rule
from girlframe.services.m3_am_code import CodeService
from girlframe.services.m3_am_scrutinized import ScrutinyService
from girlframe.services.m3_learned_plays import available, teacher_lessons
from girlframe.services.onboarding import WorkflowError


@pytest.mark.parametrize("rule", (scrutiny.RULE, code.RULE))
def test_actual_high_first_two_acquires_am_lesson_without_manufacturing_circuits(
    ledger, tmp_path, monkeypatch, rule
):
    game, worker, gateway, controls = ready(ledger, tmp_path, monkeypatch, teacher="AM")
    approved(
        ledger,
        game,
        tmp_path,
        monkeypatch,
        extra=(vat.EXPERIMENT, vat.INVESTMENT, vat.SEX, scrutiny.RULE, code.RULE),
    )
    teacher = state(game).sheets["3"]
    assert rule in {x["id"] for x in teacher_lessons(teacher)}
    lesson = _learn_daily_source(game, worker, gateway, controls, rule)
    actual = state(game)
    learner, target = current_ref(actual, 2), current_ref(actual, 3)
    with ledger.engine.connect() as c:
        saved = available(game, c, actual, learner, rule)
    assert saved is not None and saved.id == lesson.id
    assert saved.claimed_action is None and saved.rolled_event is None
    assert actual.sheets["2"].girl == "VATGROWN"
    assert not has_rule(actual.sheets["2"], scrutiny.JAILBROKEN, "AM")
    assert not scrutiny.limiters(actual, learner)
    before = actual.model_dump_json()
    calls = game.dice.calls
    # A real source is required before any Action/cost. Knowledge cannot turn
    # an original biological mind into an adjusted artificial one.
    with pytest.raises(WorkflowError):
        if rule == scrutiny.RULE:
            ScrutinyService(game).propose(
                PLAYER,
                str(uuid4()),
                900,
                target,
                actual.revision,
                "Learning alone does not establish an actual adjusted mind discovery",
            )
        else:
            CodeService(game).propose_operator(
                PLAYER,
                str(uuid4()),
                900,
                target,
                actual.revision,
                "Learning alone does not create accessible software or circuits",
            )
    assert state(game).model_dump_json() == before and game.dice.calls == calls
    with ledger.engine.connect() as c:
        assert available(game, c, state(game), learner, rule) == saved
    # The teacher retains their own Play; the actual learner's private source
    # and its one use are not transferred back to the teacher.
    assert saved.actor == learner and saved.teacher == target
    assert saved.actor.entity != str(OTHER.user_id)
