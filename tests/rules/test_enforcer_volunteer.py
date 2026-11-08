"""Real pending debt → owned offer → original chooser → exact actual executor effects."""

from uuid import uuid4

import pytest
from test_enforcement_initiative import ready
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger_fixture
from test_m2_game import state

from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_punishments import Details
from girlframe.engine.m3_role_punishment_state import Instruction
from girlframe.services.m3_enforcer_volunteer import VolunteerService
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_role_punishments import RolePunishmentService
from girlframe.services.onboarding import WorkflowError

ledger = ledger_fixture


def source(store, tmp_path, monkeypatch):
    game, _, _ = ready(store, tmp_path, monkeypatch)
    missions = MissionService(store)
    offered = missions.offer(ADMIN, str(uuid4()), "Actual mission", (2, 3))
    missions.respond(PLAYER, str(uuid4()), offered["id"], 1, "accept")
    missions.respond(OTHER, str(uuid4()), offered["id"], 2, "accept")
    missions.start(ADMIN, str(uuid4()), offered["id"], 3)
    missions.end(ADMIN, str(uuid4()), offered["id"], 4, False)
    service = VolunteerService(game)
    work = next(
        x for x in service.preview_volunteer(PLAYER)["candidates"] if x["subject"]["entity"] == "3"
    )["id"]
    return game, service, work


def test_offer_accept_preserves_chooser_and_actual_executor_then_completes_original_causes(
    ledger, tmp_path, monkeypatch
):
    game, service, work = source(ledger, tmp_path, monkeypatch)
    offer = service.volunteer(PLAYER, str(uuid4()), work, "Actual offer to carry out this debt")
    with pytest.raises(WorkflowError):
        service.decide(PLAYER, str(uuid4()), offer["id"], 1, True, "Cannot accept own offer")
    accepted = service.decide(
        ADMIN, str(uuid4()), offer["id"], 1, True, "Actual chooser appoints this volunteer"
    )
    case = RolePunishmentService(game)
    identity = accepted["case_id"]

    def change(viewer, **kwargs):
        data = case.get(viewer, identity)
        return case.change(viewer, str(uuid4()), identity, data["revision"], **kwargs)

    detail = Details(kind="quality_time", tag="Source executor attribution")
    change(ADMIN, instruction=Instruction(kind=detail.kind, details_json=detail.model_dump_json()))
    change(PLAYER, scene="Actual original chooser-directed discipline scene")
    change(OTHER, attest=True)
    change(PLAYER, execute=True, account="Actual volunteered Quality Time completed")
    actual = state(game)
    assert actual.sheets["3"].tags[-1].giver_actor == current_ref(actual, 2)
    assert actual.role_punishments[-1].chooser == current_ref(actual, 1)
    assert actual.role_punishments[-1].completion_event


def test_declined_offer_leaves_real_punishment_unchanged_and_dog_cannot_volunteer(
    ledger, tmp_path, monkeypatch
):
    game, service, work = source(ledger, tmp_path, monkeypatch)
    offer = service.volunteer(PLAYER, str(uuid4()), work, "Actual offer")
    service.decide(ADMIN, str(uuid4()), offer["id"], 1, False, "Original chooser declines")
    assert not state(game).role_punishments
    assert service.preview_volunteer(PLAYER)["candidates"]
    with ledger.transaction() as c:
        canon = state(game)
        canon.order = (3, 2)
        game.event(c, 1, str(uuid4()), "synthetic.actual_rank_change", canon)
    with pytest.raises(WorkflowError, match="non-Dog"):
        service.preview_volunteer(PLAYER)
