"""New Initiative freezes a real selected Director, separate from the Handler Girl body."""

from uuid import uuid4

import pytest
from test_enforcement_initiative import cast_target, ready
from test_handler_items import director
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger_fixture
from test_m2_game import pass_tags, state, tick

from girlframe.engine.m2 import PlayInput
from girlframe.engine.m3_actor_bonds import current_ref, is_helpless
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_punishments import Details
from girlframe.engine.m3_role_punishment_state import Instruction
from girlframe.services.m3_actors import ActorService
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_role_punishments import RolePunishmentService

ledger = ledger_fixture


def selected(game):
    actual_girl = director(game)
    cast_target(game, actual_girl)
    casting = CastService(ActorService(MissionService(game.store)))
    judge = ActorRef(kind="npc", entity="director")
    with game.store.transaction() as c:
        canon = state(game)
        canon.world = canon.world.model_copy(
            update={
                "npcs": tuple(
                    x.model_copy(update={"revealed": True}) if x.id == judge.entity else x
                    for x in canon.world.npcs
                )
            }
        )
        game.event(c, 3, str(uuid4()), "synthetic.actual_director_known", canon)
    for operation in ("join", "adjudicate"):
        view = casting.view(OTHER, 900)
        casting.change(
            OTHER, str(uuid4()), 900, view["game_revision"], view["cast_revision"], operation, judge
        )
    return actual_girl, judge


def test_actual_director_selects_high_instruction_while_main_handler_is_helpless_girl(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway = ready(ledger, tmp_path, monkeypatch, (6, 6))
    actual_girl, judge = selected(game)
    canon = state(game)
    action = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        canon.sheets["2"].revision,
        PlayInput(
            play="enforcement_initiative",
            target_actor=actual_girl,
            heat=0,
            trigger_confirmed=True,
            context="Actual main Handler body held before Director",
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    actual = state(game)
    assert not actual.handler_consequences
    assert is_helpless(actual, actual_girl, current_ref(actual, 2))
    case = actual.role_punishments[-1]
    assert case.chooser == judge and case.chooser_controller == 3
    service = RolePunishmentService(game)

    def change(viewer, **kwargs):
        view = service.get(viewer, case.id)
        return service.change(viewer, str(uuid4()), case.id, view["revision"], **kwargs)

    details = Details(kind="quality_time", tag="Actual Director-instructed Tag")
    change(
        OTHER, instruction=Instruction(kind=details.kind, details_json=details.model_dump_json())
    )
    change(PLAYER, scene="Actual Enforcer and actual affected Handler Girl scene")
    change(ADMIN, attest=True)
    change(PLAYER, execute=True, account="Actual instruction performed by original Enforcer")
    actual = state(game)
    assert actual.role_punishments[-1].handler_approver == judge
    assert actual.handler_tags[-1].giver_actor == current_ref(actual, 2)
    assert "1" not in actual.sheets
    assert game.inspect(PLAYER, action)["state"] == "complete" and game.dice.calls == 1


@pytest.mark.parametrize("faces,choice", [((4, 5), "injury"), ((6, 6), "death")])
def test_actual_director_target_has_real_owned_helpless_replacement_and_source_continuation(
    ledger, tmp_path, monkeypatch, faces, choice
):
    from girlframe.services.m3_battle_director import DirectorService

    game, worker, gateway = ready(ledger, tmp_path, monkeypatch, faces)
    _, judge = selected(game)
    canon = state(game)
    action = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        canon.sheets["2"].revision,
        PlayInput(
            play="enforcement_initiative",
            target_actor=judge,
            heat=0,
            trigger_confirmed=True,
            context="Actual original Director in Enforcer grip",
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    actual = state(game)
    assert not is_helpless(actual, judge, current_ref(actual, 2))
    assert game.inspect(PLAYER, action)["state"] != "complete"
    request = next(x for x in game.choices(OTHER) if x["kind"] == "enforcer_director_consequence")
    data = game.decision(OTHER, request["id"])
    service = DirectorService(ledger)
    work = data["enforcement"]["work_id"]
    source = service.get(OTHER, work)
    service.respond(
        OTHER,
        str(uuid4()),
        work,
        source["revision"],
        choice,
        "Actual printed original Director replacement consequence",
    )
    assert game.inspect(PLAYER, action)["state"] == "complete" and game.dice.calls == 1
    after = state(game)
    assert next(x for x in after.world.npcs if x.id == judge.entity).alive is (choice != "death")
    if choice == "death":
        assert not after.role_punishments
