"""A real higher-Status inflictor transfers an AM only after completed Punishment."""

from uuid import uuid4

import pytest
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger_fixture
from test_m2_game import state
from test_red_queen import am, initialize, ready

from girlframe.engine import m3_red_queen as rules
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_handler_play_state import Effect
from girlframe.engine.m3_punishments import Details
from girlframe.engine.m3_role_punishment_state import Instruction
from girlframe.services.m3_handler_plays import HandlerPlayService
from girlframe.services.m3_role_punishments import RolePunishmentService
from girlframe.services.onboarding import WorkflowError

ledger = ledger_fixture


def test_transfer_requires_completed_actual_higher_status_punishment(ledger, tmp_path, monkeypatch):
    game, _, _, court = ready(ledger, tmp_path, monkeypatch, inside=False)
    initialize(court)
    queen, target = current_ref(state(game), 2), current_ref(state(game), 3)
    handler = HandlerPlayService(ledger)
    promotion = handler.start(ADMIN, "promotion-grant", state(game).revision, (queen,))["id"]
    handler.submit(
        ADMIN,
        "promotion",
        promotion,
        state(game).revision,
        "mess",
        Effect(kind="status", target=queen, status=1, account="Actual performance"),
    )
    grant = handler.start(ADMIN, "punishment-grant", state(game).revision, (target,))["id"]
    handler.submit(
        ADMIN,
        "assigned-punishment",
        grant,
        state(game).revision,
        "punish",
        Effect(
            kind="punish",
            target=target,
            executor=queen,
            account="The actual Handler assigns this inflictor and recipient",
        ),
    )
    case = next(x for x in state(game).role_punishments if x.source_work == grant)
    selected = am(game, "The Queen")
    with pytest.raises(WorkflowError):
        court.transfer(
            PLAYER,
            "unperformed-transfer",
            state(game).revision,
            selected.id,
            target,
            case.id,
            "punishment",
        )
    assert rules.get(state(game), rules.CourtAM, selected.id).bearer == queen
    discipline = RolePunishmentService(game)
    details = Details(kind="stimulant_injection")
    for viewer, fields in (
        (
            ADMIN,
            {"instruction": Instruction(kind=details.kind, details_json=details.model_dump_json())},
        ),
        (PLAYER, {"scene": "The original inflictor and recipient actually play this scene"}),
        (OTHER, {"attest": True}),
        (PLAYER, {"execute": True, "account": "The original inflictor applies the stimulant"}),
    ):
        discipline.change(
            viewer, str(uuid4()), case.id, discipline.get(viewer, case.id)["revision"], **fields
        )
    args = (
        PLAYER,
        "actual-punishment-transfer",
        state(game).revision,
        selected.id,
        target,
        case.id,
        "punishment",
    )
    transferred = court.transfer(*args)
    assert court.transfer(*args) == transferred
    assert rules.get(state(game), rules.CourtAM, selected.id).bearer == target
    with pytest.raises(WorkflowError):
        court.transfer(
            PLAYER,
            "reused-punishment",
            state(game).revision,
            am(game, "The Traitor").id,
            target,
            case.id,
            "punishment",
        )
