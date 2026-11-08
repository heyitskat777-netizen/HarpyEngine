import pytest
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger_fixture
from test_m2_game import state
from test_off_duty_cycle import activate, call, prepared, roll_for

from girlframe.engine.m2 import Obligation
from girlframe.engine.m3_punishments import Details
from girlframe.services.m3_punishments import PunishmentService
from girlframe.services.onboarding import WorkflowError

ledger = ledger_fixture


def task(cycle, identity, owner=1):
    return next(x for x in cycle.periods.get(ADMIN, identity)["work"] if x["kind"] == "punishment")


def apply(svc, identity, details):
    data = svc.get(ADMIN, identity)
    return svc.apply(ADMIN, "apply", identity, data["revision"], data["game_revision"], details)


def test_m2_debt_becomes_one_real_work_item_and_requires_actual_punishment(ledger):
    cycle, game, identity = prepared(ledger)
    with ledger.transaction() as c:
        current = state(game)
        current.obligations.append(
            Obligation(id="debt", kind="punishment", owner=2, target=1, action="original-action")
        )
        game.event(c, 1, "source-debt", "synthetic.debt", current)
    identity_work = task(cycle, identity)["id"]
    activate(cycle, game, identity)
    svc = PunishmentService(ledger)
    with pytest.raises(WorkflowError, match="on-screen"):
        apply(svc, identity_work, Details(kind="stimulant_injection"))
    roll_for(cycle, game, identity, PLAYER, (2, 2))
    before = state(game).sheets["2"].heat
    apply(svc, identity_work, Details(kind="stimulant_injection"))
    assert state(game).sheets["2"].heat == before + 7
    assert state(game).obligations[-1].state == "fulfilled"
    assert svc.get(PLAYER, identity_work)["state"] == "resolved"
    with ledger.transaction() as c:
        game.event(c, 1, "later-state", "synthetic.no-duplicate", state(game))
    assert not [x for x in cycle.periods.get(ADMIN, identity)["work"] if x["kind"] == "punishment"]


def test_harsh_result_requires_each_actual_participant_and_sedation_locks_this_period(ledger):
    cycle, game, identity = prepared(ledger)
    activate(cycle, game, identity)
    call(
        cycle,
        game,
        ADMIN,
        identity,
        "handler_scene",
        "punish",
        (1, 3),
        "An actual discipline scene",
        3,
    )
    work = task(cycle, identity)["id"]
    svc = PunishmentService(ledger)
    roll_for(cycle, game, identity, OTHER, (1, 1))
    choice = Details(kind="sedation", identities=("identity:0", "identity:1"))
    with pytest.raises(WorkflowError, match="on-screen"):
        apply(svc, work, choice)
    call(cycle, game, ADMIN, identity, "acknowledge", None)
    with pytest.raises(WorkflowError, match="on-screen"):
        apply(svc, work, choice)
    call(cycle, game, OTHER, identity, "acknowledge", None)
    before = state(game).sheets["3"].heat
    apply(svc, work, choice)
    sheet = state(game).sheets["3"]
    assert sheet.heat == before
    assert set(sheet.sedation_locked) == {"identity:0", "identity:1"}
    assert sheet.sedation_period == identity
    assert not [
        x
        for x in cycle.periods.get(ADMIN, identity)["work"]
        if x["kind"] == "off_duty_handler_scene"
    ]


def test_independent_scene_attestations_dont_transfer_inflictor_authority(ledger):
    cycle, game, identity = prepared(ledger)
    with ledger.transaction() as c:
        current = state(game)
        current.obligations.append(
            Obligation(id="debt", kind="punishment", owner=2, action="action")
        )
        game.event(c, 1, "source-debt", "synthetic.debt", current)
    work = task(cycle, identity)["id"]
    svc = PunishmentService(ledger)
    data = svc.get(ADMIN, work)
    svc.propose_scene(
        ADMIN, "scene", work, data["revision"], data["game_revision"], "PRIVATE_PUNISHMENT_SCENE"
    )
    assert "PRIVATE_PUNISHMENT_SCENE" in str(svc.get(PLAYER, work))
    with pytest.raises(WorkflowError):
        svc.get(OTHER, work)
    for viewer in (ADMIN, PLAYER):
        data = svc.get(viewer, work)
        svc.attest_scene(
            viewer, "attest-" + str(viewer.user_id), work, data["revision"], data["game_revision"]
        )
    data = svc.get(PLAYER, work)
    with pytest.raises(WorkflowError, match="decision owner"):
        svc.apply(
            PLAYER,
            "not-inflictor",
            work,
            data["revision"],
            data["game_revision"],
            Details(kind="stimulant_injection"),
        )
    apply(svc, work, Details(kind="stimulant_injection"))
    assert state(game).obligations[-1].state == "fulfilled"
