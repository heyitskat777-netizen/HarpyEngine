"""A real higher-Status inflictor transfers an AM only after completed Punishment."""

from uuid import uuid4

import pytest
from test_beneath_service import start
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger_fixture
from test_m2_game import answer, pass_tags, state, tick
from test_red_queen import am, initialize, ready

from girlframe.engine import m3_red_queen as rules
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_handler_play_state import Effect
from girlframe.engine.m3_punishments import Details
from girlframe.engine.m3_role_punishment_state import Instruction
from girlframe.services.m3_handler_plays import HandlerPlayService
from girlframe.services.m3_punishments import PunishmentService
from girlframe.services.m3_red_queen import transfer_options
from girlframe.services.m3_role_punishments import RolePunishmentService
from girlframe.services.onboarding import WorkflowError

ledger = ledger_fixture


def promote_inflictor(game):
    queen = current_ref(state(game), PLAYER.user_id)
    handler = HandlerPlayService(game.store)
    promotion = handler.start(ADMIN, "promotion-grant", state(game).revision, (queen,))["id"]
    handler.submit(
        ADMIN,
        "promotion",
        promotion,
        state(game).revision,
        "mess",
        Effect(kind="status", target=queen, status=1, account="Actual performance"),
    )
    return handler


def test_transfer_requires_completed_actual_higher_status_punishment(ledger, tmp_path, monkeypatch):
    game, _, _, court = ready(ledger, tmp_path, monkeypatch, inside=False)
    initialize(court)
    queen, target = current_ref(state(game), 2), current_ref(state(game), 3)
    handler = promote_inflictor(game)
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
    with ledger.engine.connect() as c:
        assert [
            x["id"] for x in transfer_options(game, c, state(game), queen, target, "punishment")
        ] == [case.id]
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
    with ledger.engine.connect() as c:
        assert not transfer_options(game, c, state(game), queen, target, "punishment")
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


def prepare_ordinary_punishment(game, worker, gateway):
    policy = game.store.policy
    game.store.policy = policy.model_copy(
        update={
            "owner_m3_rulings": policy.owner_m3_rulings.model_copy(
                update={"beneath_private_choices": "affected_owner"}
            )
        }
    )
    promote_inflictor(game)
    game.dice.faces = (6, 6)
    action = start(game)
    tick(worker, gateway, 3)
    pass_tags(game)
    answer(
        game,
        PLAYER,
        "beneath_select",
        options=("tag", "punish"),
        fields={"tag": "An actual confrontation"},
        text="The original higher-Status Girl confronts her counterpart.",
    )
    choice = next(x for x in game.choices(PLAYER) if x["kind"] == "beneath_punishment")
    return action, game.decision(PLAYER, choice["id"])["body"]["work_id"]


def finish_ordinary_punishment(game, worker, gateway, action, work):
    discipline = PunishmentService(game.store)
    task = discipline.get(PLAYER, work)
    discipline.apply(
        PLAYER,
        "apply-ordinary-source",
        work,
        task["revision"],
        task["game_revision"],
        Details(kind="quality_time", tag="An actual resolved consequence"),
    )
    assert game.inspect(PLAYER, action)["state"] == "complete"
    tick(worker, gateway, 5)


def test_transfer_lists_ordinary_punishment_only_after_completion_and_before_use(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, court = ready(ledger, tmp_path, monkeypatch, inside=False)
    initialize(court)
    queen, target = (current_ref(state(game), uid) for uid in (2, 3))
    chosen = am(game, "The Queen")
    action, work = prepare_ordinary_punishment(game, worker, gateway)
    before = state(game)
    with ledger.engine.connect() as c:
        assert not transfer_options(game, c, before, queen, target, "punishment")
    with pytest.raises(WorkflowError, match="completed"):
        court.transfer(PLAYER, str(uuid4()), before.revision, chosen.id, target, work, "punishment")
    assert state(game) == before

    finish_ordinary_punishment(game, worker, gateway, action, work)
    before = state(game)
    with ledger.engine.connect() as c:
        (entry,) = transfer_options(game, c, before, queen, target, "punishment")
    assert entry["id"] == work and entry["event"] != work
    args = (PLAYER, "ordinary-transfer", before.revision, chosen.id, target, work, "punishment")
    receipt = court.transfer(*args)
    assert court.transfer(*args) == receipt
    after = state(game)
    assert rules.get(after, rules.CourtAM, chosen.id).bearer == target
    remaining = am(game, "The Traitor")
    assert remaining.bearer == queen
    with ledger.engine.connect() as c:
        assert not transfer_options(game, c, after, queen, target, "punishment")
    with pytest.raises(WorkflowError, match="already transferred"):
        court.transfer(
            PLAYER, str(uuid4()), after.revision, remaining.id, target, work, "punishment"
        )
    assert state(game) == after and game.dice.calls == 1
