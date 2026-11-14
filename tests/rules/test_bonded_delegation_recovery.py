"""Real native Pair-rule invitations close on child refusal/owner withdrawal, without dice."""

import json
from uuid import uuid4

import pytest
from test_bonded import FOUR, intimate, ready
from test_ledger import OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state

from girlframe.engine import m3_bonded as rules
from girlframe.engine.m2 import PlayInput
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.services.m3_bonded import admit_delegation, prove
from girlframe.services.m3_mockingbird_plays import MockingbirdService
from girlframe.services.onboarding import WorkflowError


def test_actual_pair_delegation_refusal_and_owner_withdraw_close_unused_parent(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, controls = ready(ledger, tmp_path, monkeypatch, three=True)
    assert state(game).sheets["3"].girl == "MOCKINGBIRD"  # Actual reviewed creation, no rewrite.
    actor, target = current_ref(state(game), 2), current_ref(state(game), 4)
    service = MockingbirdService(game)
    resources = {key: value.model_dump() for key, value in state(game).sheets.items()}
    dice = game.dice.calls

    def invite():
        source = intimate(controls, game, 4, "delegated")
        child = service.propose(
            PLAYER,
            str(uuid4()),
            900,
            actor,
            "mockingbird_sex",
            (target,),
            "PRIVATE_DELEGATED_INVITATION: genuine Pair-owned rule, separate consent",
            bonded_source=source,
        )["id"]
        assert controls.view(PLAYER, source)["phase"] == "bound"
        return source, child

    source, child = invite()
    with pytest.raises(WorkflowError):
        service.attest(OTHER, str(uuid4()), child, target, False)
    service.attest(FOUR, str(uuid4()), child, target, False)
    assert controls.view(PLAYER, source)["phase"] == "declined"
    assert controls.view(FOUR, source)["phase"] == "declined"
    assert service.get(PLAYER, child)["body"]["state"] == "declined"
    assert (
        next(x for x in controls.menu(PLAYER, 900)["history"] if x["id"] == source)["phase"]
        == "complete"
    )
    with ledger.engine.connect() as c:
        prove(game, c, state(game), source)
        with pytest.raises(WorkflowError):
            admit_delegation(
                game, c, state(game), actor, target, "girl.mockingbird.sex-play", source
            )

    fresh, second = invite()
    with pytest.raises(WorkflowError):
        service.withdraw(FOUR, str(uuid4()), second)
    service.withdraw(PLAYER, str(uuid4()), second)
    assert controls.view(PLAYER, fresh)["phase"] == "withdrawn"
    assert controls.view(FOUR, fresh)["phase"] == "withdrawn"
    assert (
        next(x for x in controls.menu(PLAYER, 900)["history"] if x["id"] == fresh)["phase"]
        == "complete"
    )
    with ledger.engine.connect() as c:
        assert second not in {x["id"] for x in service._tasks(c, PLAYER)}
    with pytest.raises(WorkflowError):
        service.attest(FOUR, str(uuid4()), second, target, True)
    with pytest.raises(WorkflowError):
        game.begin(
            PLAYER,
            str(uuid4()),
            900,
            state(game).sheets["2"].revision,
            PlayInput(
                play="mockingbird_sex",
                source_work=second,
                target_actor=target,
                heat=0,
                context="Cannot play a withdrawn invitation",
                trigger_confirmed=True,
            ),
        )
    with ledger.engine.connect() as c:
        prove(game, c, state(game), source)
        prove(game, c, state(game), fresh)
    releases = rules.records(state(game), rules.DelegationRelease)
    assert len(releases) == 2 and {x.outcome for x in releases} == {"declined", "withdrawn"}
    assert game.dice.calls == dice
    assert {key: value.model_dump() for key, value in state(game).sheets.items()} == resources
    assert "PRIVATE_DELEGATED_INVITATION" not in json.dumps(gateway.messages)
