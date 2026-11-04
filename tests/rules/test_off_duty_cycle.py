"""One genuine synthetic Strain-to-roll-to-recovery period; no waived work."""

from uuid import uuid4

import pytest
import sqlalchemy as sa
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger_fixture
from test_m2_game import Dice, Gateway, pass_tags, state, tick
from test_strain_effect_service import pending, selected
from test_world import gorgon

from girlframe.database import tables as t
from girlframe.delivery.m2_worker import GameWorker
from girlframe.engine.m2 import PlayInput
from girlframe.engine.m3_off_duty import RecoveryChoice
from girlframe.engine.m3_strain_effects import Choice
from girlframe.engine.m3_world import Movement, directed_steps, update
from girlframe.engine.m3_world_state import Faction
from girlframe.services.m3_off_duty_cycle import CycleService
from girlframe.services.onboarding import WorkflowError

ledger = ledger_fixture


def prepared(store):
    effects, game, identity, first = pending(store)
    policy = store.policy
    store.policy = policy.model_copy(
        update={
            "m3_approval": policy.m3_approval.model_copy(
                update={"subsystems": policy.m3_approval.subsystems | {"plays"}}
            )
        }
    )
    effects.apply(ADMIN, "void-effect", first, 1, state(game).revision, selected())
    strain = effects.strain
    for track, face, column, choice in (
        (
            "rebellion",
            1,
            1,
            Choice(
                rule_id="strain.rebellion.low.1.1",
                account="A real group appears",
                target="city0",
                faction=Faction(
                    id="group",
                    name="Local group",
                    kind="rebel",
                    cells=((0, 4),),
                    description="Local dissent",
                ),
            ),
        ),
        (
            "budget",
            5,
            2,
            Choice(
                rule_id="strain.budget.low.5.2", account="Rooms are reassigned", rooms=((2, 3),)
            ),
        ),
    ):
        request = next(x for x in state(game).strain.requests if x.track == track)
        strain.dice.face = face
        strain.roll(ADMIN, "die-" + track, request.id, 1, state(game).revision)
        strain.choose(ADMIN, "column-" + track, request.id, 2, state(game).revision, column)
        effects.apply(
            ADMIN, "effect-" + track, request.id + ":effect", 1, state(game).revision, choice
        )
    return CycleService(strain.periods), game, identity


def call(cycle, game, actor, identity, method, *args):
    data = cycle.review(actor, identity)
    return getattr(cycle, method)(
        actor, str(uuid4()), identity, data["revision"], state(game).revision, *args
    )


def activate(cycle, game, identity):
    return call(cycle, game, ADMIN, identity, "activate")


def roll_for(cycle, game, identity, actor, faces=(4, 5)):
    game.dice = Dice(faces)
    action = game.begin(
        actor,
        str(uuid4()),
        900,
        state(game).sheets[str(actor.user_id)].revision,
        PlayInput(
            play="go_off_duty",
            off_duty_id=identity,
            heat=0,
            context="Time at base",
            trigger_confirmed=True,
        ),
    )["action_id"]
    worker, gateway = GameWorker(game), Gateway()
    tick(worker, gateway)
    pass_tags(game)
    tick(worker, gateway, 8)
    return action


def recover_both(cycle, game, identity):
    roll_for(cycle, game, identity, PLAYER, (2, 2))  # Ace +4 = comfortable.
    call(cycle, game, PLAYER, identity, "scene", None, (), "")
    call(cycle, game, PLAYER, identity, "recover", RecoveryChoice())
    roll_for(cycle, game, identity, OTHER, (4, 4))  # Dog +0 = comfortable.
    call(cycle, game, OTHER, identity, "scene", None, (), "")
    call(cycle, game, OTHER, identity, "recover", RecoveryChoice())


def finish_routine(cycle, game, identity):
    call(cycle, game, ADMIN, identity, "handler_scene", "routine", (1, 2), "PRIVATE_HANDLER_SCENE")
    call(cycle, game, ADMIN, identity, "acknowledge", None)
    call(cycle, game, PLAYER, identity, "acknowledge", None)
    call(cycle, game, ADMIN, identity, "review_status", (3, 2), "PRIVATE_PERFORMANCE_ACCOUNT")


def movement(game):
    world = state(game).world
    return tuple(
        Movement(gorgon=x.id, destination=directed_steps(world, x)[0])
        for x in world.gorgons
        if x.gorgon_class == "directed" and x.alive
    )


def test_actual_preparation_owned_rolls_recovery_review_and_world_end_are_resumable(ledger):
    cycle, game, identity = prepared(ledger)
    with pytest.raises(WorkflowError):
        call(cycle, game, PLAYER, identity, "activate")
    activate(cycle, game, identity)
    recover_both(cycle, game, identity)
    with pytest.raises(WorkflowError, match="actual work"):
        call(cycle, game, ADMIN, identity, "review_status", (3, 2), "Too soon")
    finish_routine(cycle, game, identity)
    before = state(game).world.gorgons[1].cell
    result = call(cycle, game, ADMIN, identity, "finish", movement(game))
    assert result["phase"] == "complete"
    assert state(game).order == (3, 2)
    from girlframe.services.shared_setup import SharedSetupService

    assert SharedSetupService(ledger).effective_status(PLAYER, 3) == {
        "higher": False,
        "basis": "current Status",
    }
    assert state(game).world.gorgons[1].cell != before
    assert state(game).world.completed_off_duty == (identity,)
    assert cycle.periods.current(PLAYER) is None
    assert CycleService(cycle.periods).review(PLAYER, identity)["own"]["recovered"]
    with ledger.engine.connect() as c:
        assert cycle.periods._pending(c, identity) == []
        metadata = str(list(c.scalars(sa.select(t.events.c.payload_json))))
        outcomes = str(list(c.scalars(sa.select(t.commands.c.outcome_json))))
        assert "PRIVATE_HANDLER_SCENE" not in metadata + outcomes
        assert "PRIVATE_PERFORMANCE_ACCOUNT" not in metadata + outcomes


def test_scene_is_private_to_participants_and_cannot_be_attested_for_absent_humans(ledger):
    cycle, game, identity = prepared(ledger)
    activate(cycle, game, identity)
    roll_for(cycle, game, identity, PLAYER, (6, 6))
    call(cycle, game, PLAYER, identity, "scene", "nearby_city", (2, 3), "PRIVATE_SCENE")
    assert "PRIVATE_SCENE" in str(cycle.review(PLAYER, identity))
    assert "PRIVATE_SCENE" in str(cycle.review(OTHER, identity))
    assert "PRIVATE_SCENE" not in str(cycle.review(ADMIN, identity))
    call(cycle, game, PLAYER, identity, "acknowledge", 2)
    with pytest.raises(WorkflowError, match="confirm"):
        call(cycle, game, ADMIN, identity, "acknowledge", 2)
    with pytest.raises(WorkflowError, match="required on-screen"):
        call(cycle, game, PLAYER, identity, "recover", RecoveryChoice())
    call(cycle, game, OTHER, identity, "acknowledge", 2)
    call(cycle, game, PLAYER, identity, "recover", RecoveryChoice())


def test_permission_scene_grants_exactly_one_real_permission_only_after_all_attest(ledger):
    cycle, game, identity = prepared(ledger)
    activate(cycle, game, identity)
    initial = state(game).sheets["3"].permissions
    call(cycle, game, ADMIN, identity, "handler_scene", "permission", (1, 3), "An actual award", 3)
    call(cycle, game, ADMIN, identity, "acknowledge", None)
    assert state(game).sheets["3"].permissions == initial
    data = cycle.review(OTHER, identity)
    revision = state(game).revision
    result = cycle.acknowledge(OTHER, "award", identity, data["revision"], revision, None)
    assert cycle.acknowledge(OTHER, "award", identity, data["revision"], revision, None) == result
    assert state(game).sheets["3"].permissions == initial + 1
    with pytest.raises(WorkflowError):
        call(cycle, game, OTHER, identity, "acknowledge", None)
    assert state(game).sheets["3"].permissions == initial + 1


def test_unresolved_actual_strain_cannot_be_replaced_by_activation_or_generic_ack(ledger):
    effects, game, identity, _ = pending(ledger)
    cycle = CycleService(effects.strain.periods)
    policy = ledger.policy
    ledger.policy = policy.model_copy(
        update={
            "m3_approval": policy.m3_approval.model_copy(
                update={"subsystems": policy.m3_approval.subsystems | {"plays"}}
            )
        }
    )
    with pytest.raises(WorkflowError, match="Strain cycle"):
        call(cycle, game, ADMIN, identity, "activate")
    assert cycle.periods.get(PLAYER, identity)["phase"] == "preparing"


def test_end_destruction_creates_provenance_bound_next_start_trigger_without_reroll(ledger):
    cycle, game, identity = prepared(ledger)
    activate(cycle, game, identity)
    recover_both(cycle, game, identity)
    finish_routine(cycle, game, identity)
    with ledger.transaction() as c:
        current = state(game)
        current.world = update(
            current.world,
            gorgons=current.world.gorgons + (gorgon("aggressive", "attacker", (4, 4)),),
        )
        game.event(c, 1, "synthetic-attacker", "synthetic.encounter", current)
    with pytest.raises(WorkflowError, match="performance again"):
        call(cycle, game, ADMIN, identity, "finish", movement(game))
    call(
        cycle,
        game,
        ADMIN,
        identity,
        "review_status",
        (3, 2),
        "Performance reviewed with the new threat",
    )
    result = call(cycle, game, ADMIN, identity, "finish", movement(game))
    assert result["phase"] == "complete"
    current = state(game)
    trigger = current.strain.triggers[0]
    assert trigger.kind == "structure_destroyed" and trigger.entity == "important0"
    assert trigger.consumed_by is None
    with ledger.engine.connect() as c:
        assert (
            c.scalar(sa.select(t.events.c.kind).where(t.events.c.id == trigger.source_event))
            == "m3.off_duty_end"
        )
    assert next(x for x in current.world.locations if x.id == "important0").condition == "destroyed"
    from test_strain import facts

    from girlframe.engine.m3_strain import start

    with pytest.raises(ValueError, match="cannot deny"):
        start(current.strain, "next", facts(no_girl_void=True))
    changed = start(current.strain, "next", facts(no_girl_void=True, structure_destroyed=True))
    assert changed.levels["budget"] == "high" and changed.triggers[0].consumed_by == "next"
