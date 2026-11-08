from uuid import uuid4

import pytest
import sqlalchemy as sa
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger_fixture
from test_m2_game import state
from test_observation_service import apply, director_for_observation, setup
from test_off_duty_cycle import call

from girlframe.database import tables as t
from girlframe.engine.m3_observation_state import Details
from girlframe.services.m3_director import DirectorService
from girlframe.services.onboarding import WorkflowError

ledger = ledger_fixture


def ready(store):
    observation, cycle, game, period = setup(store)
    director, effect = director_for_observation(observation, game, period)
    apply(observation, ADMIN, effect, Details(npc="director", account="Actual proposed appearance"))
    data = observation.get(director, effect)
    observation.answer_npc(
        director,
        "director-arrives",
        effect,
        data["revision"],
        data["period_revision"],
        data["game_revision"],
        True,
    )
    work = next(
        x["id"]
        for x in observation.periods.get(ADMIN, period)["work"]
        if x["kind"] == "director_presence"
    )
    return DirectorService(observation.missions), observation, cycle, game, period, director, work


def configure(svc, work, present=True, labels=("Afraid", "Defiant"), key=None):
    data = svc.get(ADMIN, work)
    return svc.review(
        ADMIN,
        key or str(uuid4()),
        work,
        data["revision"],
        data["game_revision"],
        present,
        labels,
        "PRIVATE_HANDLER_REVIEW",
    )


def test_actual_handler_sets_its_context_once_and_director_cannot_see_private_identities(ledger):
    svc, observation, cycle, game, period, director, work = ready(ledger)
    data = svc.get(ADMIN, work)
    assert not data["overlapping"] and not data["absence_available"]
    with pytest.raises(WorkflowError):
        svc.review(
            director,
            "not-my-identities",
            work,
            data["revision"],
            data["game_revision"],
            True,
            ("One", "Two"),
            "Forgery",
        )
    with ledger.transaction() as c:
        canon = state(game)
        canon.handler_heat = 9
        game.event(c, 1, "handler-baseline", "synthetic.handler_heat", canon)
    data = svc.get(ADMIN, work)
    args = (
        ADMIN,
        "configure-once",
        work,
        data["revision"],
        data["game_revision"],
        True,
        ("Afraid", "Defiant"),
        "PRIVATE_HANDLER_REVIEW",
    )
    result = svc.review(*args)
    assert svc.review(*args) == result and state(game).handler_heat == 0
    context = state(game).director_contexts[0]
    assert "1" not in state(game).sheets and state(game).order == (3, 2)
    assert svc.context(ADMIN, context.id)["identities"][0]["name"] == "Afraid"
    assert "Afraid" not in str(svc.context(director, context.id))
    with pytest.raises(WorkflowError):
        svc.context(OTHER, context.id)
    with pytest.raises(WorkflowError):
        configure(svc, work)
    with pytest.raises(WorkflowError, match="Handler/Girl"):
        call(
            cycle,
            game,
            ADMIN,
            period,
            "handler_scene",
            "routine",
            (1, 2),
            "No ordinary Handler powers",
        )
    # Human scene participation is distinct from using Handler rule authority.
    call(
        cycle,
        game,
        PLAYER,
        period,
        "scene",
        "observation:director_or_rival_arrives",
        (2, 4, 1),
        "Actual shared scene",
    )
    for actor in (PLAYER, director, ADMIN):
        call(cycle, game, actor, period, "acknowledge", 2)
    current = svc.context(director, context.id)
    with pytest.raises(WorkflowError):
        svc.leave(
            OTHER,
            "not-my-departure",
            context.id,
            current["revision"],
            current["game_revision"],
            "director",
            "Forgery",
        )
    result = svc.leave(
        director,
        "leave-once",
        context.id,
        current["revision"],
        current["game_revision"],
        "director",
        "Actual departure",
    )
    assert not result["active"]
    assert (
        svc.leave(
            director,
            "leave-once",
            context.id,
            current["revision"],
            current["game_revision"],
            "director",
            "Actual departure",
        )
        == result
    )
    call(
        cycle,
        game,
        ADMIN,
        period,
        "handler_scene",
        "routine",
        (1, 2),
        "Ordinary authority after departure",
    )
    with ledger.engine.connect() as c:
        assert "PRIVATE_HANDLER_REVIEW" not in str(
            list(c.scalars(sa.select(t.events.c.payload_json)))
        )


def test_absence_cannot_waive_a_context_without_completed_owned_scene_provenance(ledger):
    svc, _, cycle, game, period, director, work = ready(ledger)
    with pytest.raises(WorkflowError, match="completed actual Director scene"):
        configure(svc, work, False, ())
    call(
        cycle,
        game,
        PLAYER,
        period,
        "scene",
        "observation:director_or_rival_arrives",
        (2, 4),
        "Handler absent",
    )
    call(cycle, game, PLAYER, period, "acknowledge", 2)
    with pytest.raises(WorkflowError):
        configure(svc, work, False, ())
    call(cycle, game, director, period, "acknowledge", 2)
    assert svc.get(ADMIN, work)["absence_available"]
    assert configure(svc, work, False, ())["mode"] == "absent"
    assert not state(game).director_contexts and "1" not in state(game).sheets
    call(
        cycle,
        game,
        ADMIN,
        period,
        "handler_scene",
        "routine",
        (1, 2),
        "Actual separate Handler scene",
    )


def test_director_context_write_rolls_back_and_pause_or_revocation_blocks_effects(
    ledger, monkeypatch
):
    svc, _, _, game, _, director, work = ready(ledger)
    before = state(game)
    original = svc.game.event

    def fail(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError("synthetic after-event failure")

    monkeypatch.setattr(svc.game, "event", fail)
    with pytest.raises(RuntimeError):
        configure(svc, work, key="retry")
    assert state(game) == before and svc.get(ADMIN, work)["state"] == "pending"
    monkeypatch.setattr(svc.game, "event", original)
    ledger.safety(OTHER, "pause", ledger.status(OTHER)["revision"], pause=True)
    with pytest.raises(WorkflowError, match="SAFETY_PAUSED"):
        configure(svc, work, key="retry")
    ledger.safety(OTHER, "resume", ledger.status(OTHER)["revision"], pause=False)
    configure(svc, work, key="retry")
    context = state(game).director_contexts[0]
    policy = ledger.policy
    ledger.policy = policy.model_copy(update={"m3_approval": None})
    data = svc.context(director, context.id)
    with pytest.raises(WorkflowError, match="REVIEW_PENDING"):
        svc.leave(
            director,
            "revoked",
            context.id,
            data["revision"],
            data["game_revision"],
            "director",
            "Not authorized",
        )
