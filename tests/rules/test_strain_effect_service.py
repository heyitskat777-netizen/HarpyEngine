import pytest
import sqlalchemy as sa
from test_ledger import ADMIN, PLAYER
from test_ledger import ledger as ledger_fixture
from test_m2_game import state
from test_strain_service import ready
from test_world import gorgon, initial

from girlframe.database import tables as t
from girlframe.engine.m3_strain_effects import Choice
from girlframe.services.m3_strain_effects import EffectService
from girlframe.services.m3_world import WorldService
from girlframe.services.onboarding import WorkflowError

ledger = ledger_fixture


def pending(store):
    strain, game = ready(store, face=1)
    approval = store.policy.m3_approval
    store.policy = store.policy.model_copy(
        update={
            "m3_approval": approval.model_copy(
                update={"subsystems": approval.subsystems | {"world"}}
            )
        }
    )
    world = initial()
    WorldService(strain.missions).initialize(
        ADMIN, "world", state(game).revision, world.board, world.locations, world.gorgons[0]
    )
    with store.transaction() as c:
        current = state(game)
        for sheet in current.sheets.values():
            for asset in sheet.assets:
                asset.void = False
        game.event(c, 1, "synthetic-past-surgery", "synthetic.baseline", current)
    from test_strain_service import prepared

    identity = prepared(strain, game)
    request = state(game).strain.requests[0]
    strain.roll(ADMIN, "die", request.id, 1, state(game).revision)
    strain.choose(ADMIN, "column", request.id, 2, state(game).revision, 1)
    return EffectService(strain), game, identity, request.id + ":effect"


def selected():
    return Choice(
        rule_id="strain.void.low.1.1",
        account="It approaches from the edge",
        gorgon=gorgon("directed", "new", (10, 0)),
    )


def test_actual_effect_and_work_resolve_atomically_with_replay_and_no_waiver(ledger):
    svc, game, period, identity = pending(ledger)
    before = state(game).revision
    result = svc.apply(ADMIN, "apply", identity, 1, before, selected())
    assert result["state"] == "resolved" and len(state(game).world.gorgons) == 2
    assert svc.apply(ADMIN, "apply", identity, 1, before, selected()) == result
    assert len(state(game).world.gorgons) == 2
    with pytest.raises(WorkflowError):
        svc.apply(ADMIN, "again", identity, 2, state(game).revision, selected())
    assert svc.strain.periods.get(ADMIN, period)["phase"] == "preparing"


def test_wrong_actor_rule_and_stale_state_cannot_apply_or_skip_effect(ledger):
    svc, game, _, identity = pending(ledger)
    with pytest.raises(WorkflowError):
        svc.apply(PLAYER, "not-handler", identity, 1, state(game).revision, selected())
    with pytest.raises(WorkflowError, match="does not match"):
        svc.apply(
            ADMIN,
            "wrong-source",
            identity,
            1,
            state(game).revision,
            Choice(rule_id="strain.budget.low.5.2", rooms=((2, 3),), account="Wrong source"),
        )
    with pytest.raises(WorkflowError, match="STALE_STATE"):
        svc.apply(ADMIN, "stale", identity, 1, state(game).revision - 1, selected())
    assert len(state(game).world.gorgons) == 1


def test_failure_after_game_event_rolls_back_world_and_work_and_retry_is_safe(ledger, monkeypatch):
    svc, game, _, identity = pending(ledger)
    before = state(game)
    original = svc.strain._save

    def fail(*args, **kwargs):
        raise RuntimeError("synthetic work write failure")

    monkeypatch.setattr(svc.strain, "_save", fail)
    with pytest.raises(RuntimeError):
        svc.apply(ADMIN, "apply", identity, 1, before.revision, selected())
    assert state(game) == before and svc.get(ADMIN, identity)["state"] == "pending"
    monkeypatch.setattr(svc.strain, "_save", original)
    svc.apply(ADMIN, "apply", identity, 1, before.revision, selected())
    with ledger.engine.connect() as c:
        assert "It approaches" not in str(list(c.scalars(sa.select(t.events.c.payload_json))))
