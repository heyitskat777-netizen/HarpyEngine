"""Narrow canonical instruction/executor checks; shared Initiative roll remains unwired."""

from uuid import uuid4

import pytest
from test_enforcer_conditioning import setup
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger_fixture
from test_m2_game import state
from test_punishment_service import ended

from girlframe.engine.m3_actor_bonds import current_ref, depth
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_punishments import Details
from girlframe.engine.m3_role_punishment_state import Instruction
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_role_punishments import RolePunishmentService, open_case, synchronize
from girlframe.services.onboarding import WorkflowError

ledger = ledger_fixture


def source_case(game, target, *, source_work=None):
    """Synthetic source event tests exact effect ports, without claiming real Initiative RNG."""
    identity, event = str(uuid4()), str(uuid4())
    with game.store.transaction() as c:
        original = state(game)
        updated, _ = open_case(
            original,
            profiles(c, game.store.campaign_id),
            actor=current_ref(original, 2),
            target=target,
            chooser=current_ref(original, 1),
            source_kind="obedience_volunteer" if source_work else "enforcement_initiative",
            source_work=source_work,
            action=None,
            source_event=event,
            identity=identity,
        )
        game.event(c, 1, str(uuid4()), "synthetic.role_consequence", updated, event_id=event)
        synchronize(game, c, None, event)
    return RolePunishmentService(game), identity


def change(service, viewer, identity, **kwargs):
    data = service.get(viewer, identity)
    return service.change(viewer, str(uuid4()), identity, data["revision"], **kwargs)


def instruct(service, identity, details, *, counterpart=None):
    return change(
        service,
        ADMIN,
        identity,
        instruction=Instruction(
            kind=details.kind, details_json=details.model_dump_json(), counterpart=counterpart
        ),
    )


def scene(service, identity, subject=ADMIN):
    change(service, PLAYER, identity, scene="Actual on-screen instructed Punishment")
    change(service, subject, identity, attest=True)


def test_actual_npc_tag_and_executor_bond_then_actual_selected_bond_reduction(
    ledger,
    tmp_path,
    monkeypatch,
):
    _, game = setup(ledger, tmp_path, monkeypatch)
    npc = ActorRef(kind="npc", entity="known-guard")
    service, identity = source_case(game, npc)
    instruct(service, identity, Details(kind="quality_time", tag="Actual source Tag"))
    scene(service, identity)
    with pytest.raises(WorkflowError):
        change(service, ADMIN, identity, execute=True, account="Chooser is not the executor")
    change(service, PLAYER, identity, execute=True, account="Actual carried-out Quality Time")
    actual = state(game)
    assert depth(actual, npc, current_ref(actual, 2)) == 1
    assert depth(actual, npc, current_ref(actual, 1)) == 0
    assert (
        next(x for x in actual.world.npcs if x.id == npc.entity).tags[-1].label
        == "Actual source Tag"
    )
    assert actual.role_punishments[-1].completion_event
    service, reduction = source_case(game, npc)
    instruct(
        service,
        reduction,
        Details(kind="reduced_socialization"),
        counterpart=current_ref(actual, 2),
    )
    scene(service, reduction)
    change(service, PLAYER, reduction, execute=True, account="Actual selected Bond reduced")
    assert depth(state(game), npc, current_ref(state(game), 2)) == 0


def test_handler_social_punishment_uses_actual_handler_tag_and_executor_relationship(
    ledger,
    tmp_path,
    monkeypatch,
):
    _, game = setup(ledger, tmp_path, monkeypatch)
    with ledger.transaction() as c:
        canon = state(game)
        canon.bonds = {}
        game.event(c, 1, "synthetic-distinct-relationship", "synthetic.state", canon)
    target = current_ref(state(game), 1)
    service, identity = source_case(game, target)
    instruct(service, identity, Details(kind="quality_time", tag="Actual Handler Tag"))
    scene(service, identity)
    change(service, PLAYER, identity, execute=True, account="Actual Handler Quality Time")
    actual = state(game)
    assert actual.handler_tags[-1].giver_actor == current_ref(actual, 2)
    assert depth(actual, target, current_ref(actual, 2)) == 1


def test_pc_existing_punishment_keeps_original_chooser_and_actual_executor_giver(ledger):
    _, _, game, _, source_work = ended(ledger)
    service, identity = source_case(game, current_ref(state(game), 3), source_work=source_work)
    instruct(service, identity, Details(kind="quality_time", tag="Actual delegated Tag"))
    scene(service, identity, OTHER)
    assert (
        service.get(ADMIN, identity)["case"]["scene_account"]
        != "Actual on-screen instructed Punishment"
    )
    assert (
        service.get(OTHER, identity)["case"]["scene_account"]
        == "Actual on-screen instructed Punishment"
    )
    before = state(game)
    change(
        service,
        PLAYER,
        identity,
        execute=True,
        account="Actual original executor carries instruction",
    )
    actual = state(game)
    assert actual.sheets["3"].tags[-1].giver == 2
    assert actual.sheets["3"].tags[-1].giver_actor == current_ref(actual, 2)
    assert depth(actual, current_ref(actual, 3), current_ref(actual, 2)) >= depth(
        before, current_ref(before, 3), current_ref(before, 2)
    )
    assert actual.role_punishments[-1].chooser == current_ref(actual, 1)
    assert actual.role_punishments[-1].completion_event is not None
