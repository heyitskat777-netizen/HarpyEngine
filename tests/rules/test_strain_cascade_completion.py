"""Both saved cascade dice must lead to real effects before Off-Duty starts."""

import pytest
from test_ledger import ADMIN, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state
from test_off_duty_cycle import activate
from test_strain_effect_service import selected
from test_strain_service import prepared, ready
from test_world import initial

from girlframe.engine.m3_budget_anarchy import cases as anarchy_cases
from girlframe.engine.m3_strain_effects import Choice
from girlframe.engine.m3_void_revelation import revelations
from girlframe.engine.m3_world_state import Faction
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_off_duty import OffDutyService
from girlframe.services.m3_off_duty_cycle import CycleService
from girlframe.services.m3_strain import StrainService
from girlframe.services.m3_strain_effects import EffectService
from girlframe.services.m3_world import WorldService
from girlframe.services.onboarding import WorkflowError


@pytest.mark.parametrize(
    ("track", "high_face", "high_column", "high_effect"),
    (
        (
            "void",
            5,
            1,
            Choice(
                rule_id="strain.void.high.5.1",
                account="The Handler reveals the danger to the original scene.",
                revelation_channel=900,
                revelation_play="reveal_near_disaster",
            ),
        ),
        (
            "rebellion",
            1,
            2,
            Choice(
                rule_id="strain.rebellion.high.1.2",
                account="The group takes a city.",
                target="city0",
                faction_id="cascade-faction",
            ),
        ),
        (
            "budget",
            5,
            1,
            Choice(rule_id="strain.budget.high.5.1", account="Order breaks down.", target="city0"),
        ),
    ),
    ids=("void", "rebellion", "budget"),
)
def test_off_duty_requires_both_saved_cascade_effects(
    ledger, track, high_face, high_column, high_effect
):
    strain, game = ready(ledger, face=6)
    approval = ledger.policy.m3_approval
    ledger.policy = ledger.policy.model_copy(
        update={
            "m3_approval": approval.model_copy(
                update={"subsystems": approval.subsystems | {"world", "plays"}}
            )
        }
    )
    world = initial()
    WorldService(strain.missions).initialize(
        ADMIN, "cascade-map", state(game).revision, world.board, world.locations, world.gorgons[0]
    )
    with ledger.transaction() as connection:
        canon = state(game)
        for sheet in canon.sheets.values():
            for asset in sheet.assets:
                asset.void = False
        game.event(connection, ADMIN.user_id, "cascade-baseline", "synthetic.nonvoid", canon)
    period = prepared(strain, game, high=frozenset({track}))
    root = next(x for x in state(game).strain.requests if x.track == track)
    strain.roll(ADMIN, "cascade-die", root.id, 1, state(game).revision)
    revision = state(game).revision
    chosen = strain.choose(ADMIN, "cascade-column", root.id, 2, revision, 2)
    assert strain.choose(ADMIN, "cascade-column", root.id, 2, revision, 2) == chosen
    children = {x.severity: x for x in state(game).strain.requests if x.parent == root.id}
    assert set(children) == {"low", "high"}

    def select(request, face, column):
        strain.dice.face = face
        strain.roll(ADMIN, "die-" + request.id, request.id, 1, state(game).revision)
        strain.choose(ADMIN, "column-" + request.id, request.id, 2, state(game).revision, column)
        return request.id + ":effect"

    effects = EffectService(strain)
    for corresponding_track, face, column, choice in (
        ("void", 1, 1, selected()),
        (
            "rebellion",
            1,
            1,
            Choice(
                rule_id="strain.rebellion.low.1.1",
                account="A quiet group forms.",
                target="city0",
                faction=Faction(id="cascade-faction", name="Group", kind="rebel", cells=((0, 4),)),
            ),
        ),
        (
            "budget",
            5,
            2,
            Choice(rule_id="strain.budget.low.5.2", account="Rooms are shared.", rooms=((2, 3),)),
        ),
    ):
        request = next(
            x
            for x in state(game).strain.requests
            if x.track == corresponding_track and x.severity == "low"
        )
        work = select(request, face, column)
        effects.apply(ADMIN, "effect-" + work, work, 1, state(game).revision, choice)

    cycle = CycleService(strain.periods)
    with pytest.raises(WorkflowError, match="Finish the real world setup and Strain cycle"):
        activate(cycle, game, period)
    missing_effect = select(children["high"], high_face, high_column)
    with pytest.raises(WorkflowError, match="Resolve actual Strain"):
        activate(cycle, game, period)

    reopened = EffectService(StrainService(OffDutyService(MissionService(ledger))))
    assert reopened.get(ADMIN, missing_effect)["state"] == "pending"
    revision = state(game).revision
    with pytest.raises(WorkflowError):
        reopened.apply(PLAYER, "other-owner", missing_effect, 1, revision, high_effect)
    applied = reopened.apply(ADMIN, "high-effect", missing_effect, 1, revision, high_effect)
    assert reopened.apply(ADMIN, "high-effect", missing_effect, 1, revision, high_effect) == applied
    assert applied["state"] == "resolved"
    receipts = state(game).strain.events
    assert len(receipts) == strain.dice.calls == 5
    originals = {x.id: x for x in receipts}
    assert (originals[root.id].face, originals[root.id].column) == (6, 2)
    assert originals[children["high"].id].face == high_face
    assert tuple(x.severity for x in receipts if x.parent == root.id) == ("low", "high")
    assert activate(cycle, game, period)["phase"] == "active"
    canon = state(game)
    if track == "void":
        (outcome,) = revelations(canon)
        assert outcome.id == missing_effect and outcome.recipients
    else:
        (outcome,) = anarchy_cases(canon)
        assert outcome.id == missing_effect and outcome.city == "city0"
        city = next(x for x in canon.world.locations if x.id == outcome.city)
        if track == "rebellion":
            assert outcome.faction == "cascade-faction" and outcome.mission is None
            assert city.operational
        else:
            assert city.blocked_by == (missing_effect,)
