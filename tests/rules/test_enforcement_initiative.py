"""Actual shared-roll Initiative source ownership; synthetic reviews are fixture-only."""

import json
from pathlib import Path
from uuid import uuid4

import pytest
from test_enforcer_conditioning import setup
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger_fixture
from test_m2_game import Gateway, answer, pass_tags, state, tick

from girlframe.delivery.m2_worker import GameWorker
from girlframe.engine.m2 import PlayInput
from girlframe.engine.m3_actor_bonds import current_ref, is_helpless
from girlframe.engine.m3_punishments import Details
from girlframe.engine.m3_role_punishment_state import Instruction
from girlframe.engine.rules_registry import Registry
from girlframe.services.m3_access import digest
from girlframe.services.m3_role_punishments import RolePunishmentService
from girlframe.services.onboarding import WorkflowError

ledger = ledger_fixture


def ready(store, tmp_path, monkeypatch, faces=(4, 5)):
    _, game = setup(store, tmp_path, monkeypatch)
    import os

    path = Path(os.environ["GIRLFRAME_RULES_REGISTRY"])
    data = json.loads(path.read_text())
    source = next(x for x in data["entries"] if x["id"] == "frame.enforcer.obedience-conditioning")
    target = next(x for x in data["entries"] if x["id"] == "frame.enforcer.enforcement-initiative")
    for key in (
        "implementation",
        "source_audit",
        "independent_review",
        "reviewer",
        "review_reference",
        "contract",
        "test_evidence",
    ):
        target[key] = source[key]
    registry = Registry.model_validate_json(json.dumps(data))
    path.write_text(registry.model_dump_json())
    approval = store.policy.m3_approval
    store.policy = store.policy.model_copy(
        update={
            "m3_approval": approval.model_copy(
                update={
                    "registry_sha256": digest(registry),
                    "subsystems": approval.subsystems | {"plays"},
                }
            )
        }
    )
    game.dice.faces = faces
    return game, GameWorker(game), Gateway()


def start(game):
    canon = state(game)
    return game.begin(
        PLAYER,
        str(uuid4()),
        900,
        canon.sheets["2"].revision,
        PlayInput(
            play="enforcement_initiative",
            target_actor=current_ref(canon, 3),
            heat=0,
            trigger_confirmed=True,
            context="Actual take hold; unknown positions stay unknown",
        ),
    )["action_id"]


def rolled(store, tmp_path, monkeypatch, faces=(4, 5)):
    game, worker, gateway = ready(store, tmp_path, monkeypatch, faces)
    identity = start(game)
    tick(worker, gateway, 3)
    pass_tags(game)
    return game, worker, gateway, identity


def test_mid_actual_grasp_helpless_and_one_roll_restores_chat(ledger, tmp_path, monkeypatch):
    game, worker, gateway, identity = rolled(ledger, tmp_path, monkeypatch)
    actual = state(game)
    assert is_helpless(actual, current_ref(actual, 3), current_ref(actual, 2))
    assert actual.enforcer_grasps[-1].held
    assert game.inspect(PLAYER, identity)["state"] == "complete"
    assert game.dice.calls == 1
    tick(worker, gateway, 5)
    with ledger.engine.connect() as c:
        assert game.lock(c, 900)["state"] == "released"


def test_low_exact_two_target_tag_and_actual_handler_disapproval(ledger, tmp_path, monkeypatch):
    game, _, _, identity = rolled(ledger, tmp_path, monkeypatch, (1, 1))
    before = state(game)
    answer(game, PLAYER, "enforcer_select", options=("tag", "disapproval"))
    assert not game.choices(PLAYER)
    answer(game, OTHER, "enforcer_tag", text="PRIVATE_ACTUAL_TARGET_TAG")
    assert state(game).sheets["2"].tags[-1].giver_actor == current_ref(before, 3)
    assert game.inspect(PLAYER, identity)["state"] != "complete"
    answer(game, ADMIN, "enforcer_disapproval", text="PRIVATE_ACTUAL_HANDLER_RESPONSE")
    assert game.inspect(PLAYER, identity)["state"] == "complete" and game.dice.calls == 1
    assert state(game).order != before.order


def test_high_waits_actual_handler_instruction_executor_scene_and_real_effect(
    ledger, tmp_path, monkeypatch
):
    game, _, _, identity = rolled(ledger, tmp_path, monkeypatch, (6, 6))
    actual = state(game)
    case = actual.role_punishments[-1]
    assert game.inspect(PLAYER, identity)["state"] != "complete"
    service = RolePunishmentService(game)

    def change(viewer, **kw):
        data = service.get(viewer, case.id)
        return service.change(viewer, str(uuid4()), case.id, data["revision"], **kw)

    details = Details(kind="quality_time", tag="Actual instructed source Tag")
    change(
        ADMIN, instruction=Instruction(kind=details.kind, details_json=details.model_dump_json())
    )
    change(PLAYER, scene="Actual Enforcer and victim scene")
    change(OTHER, attest=True)
    change(PLAYER, execute=True, account="Actual instructed Quality Time performed")
    assert game.inspect(PLAYER, identity)["state"] == "complete"
    assert state(game).sheets["3"].tags[-1].giver_actor == current_ref(state(game), 2)
    assert game.dice.calls == 1


def cast_target(game, ref):
    from girlframe.services.m3_actors import ActorService
    from girlframe.services.m3_cast import CastService
    from girlframe.services.m3_missions import MissionService

    approval = game.store.policy.m3_approval
    game.store.policy = game.store.policy.model_copy(
        update={
            "m3_approval": approval.model_copy(
                update={"subsystems": approval.subsystems | {"world"}}
            )
        }
    )
    service = CastService(ActorService(MissionService(game.store)))
    data = service.view(ADMIN, 900)
    service.change(
        ADMIN, str(uuid4()), 900, data["game_revision"], data["cast_revision"], "join", ref
    )


@pytest.mark.parametrize(
    "faces,choice", [((4, 5), "injury"), ((6, 6), "opportunity"), ((6, 6), "death")]
)
def test_actual_handler_uses_printed_replacement_then_high_actual_punishment(
    ledger, tmp_path, monkeypatch, faces, choice
):
    from girlframe.services.m3_handler_consequences import HandlerConsequenceService

    game, worker, gateway = ready(ledger, tmp_path, monkeypatch, faces)
    target = current_ref(state(game), 1)
    cast_target(game, target)
    canon = state(game)
    identity = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        canon.sheets["2"].revision,
        PlayInput(
            play="enforcement_initiative",
            target_actor=target,
            heat=0,
            trigger_confirmed=True,
            context="Actual physical original Handler taken hold of",
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    actual = state(game)
    assert not is_helpless(actual, target, current_ref(actual, 2))
    record = actual.handler_consequences[-1]
    service = HandlerConsequenceService(ledger)
    service.respond(
        ADMIN, str(uuid4()), record.id, actual.revision, choice, "Actual printed replacement effect"
    )
    if faces == (6, 6) and choice != "death":
        case = state(game).role_punishments[-1]
        service = RolePunishmentService(game)

        def change(viewer, **kw):
            data = service.get(viewer, case.id)
            return service.change(viewer, str(uuid4()), case.id, data["revision"], **kw)

        details = Details(kind="quality_time", tag="Actual original Handler instructed Tag")
        change(
            ADMIN,
            instruction=Instruction(kind=details.kind, details_json=details.model_dump_json()),
        )
        change(PLAYER, scene="Actual Enforcer and surviving Handler scene")
        change(ADMIN, attest=True)
        change(PLAYER, execute=True, account="Actual instructed consequence")
    assert game.inspect(PLAYER, identity)["state"] == "complete" and game.dice.calls == 1
    if choice == "death":
        assert state(game).handler_archives[-1].actor == target
        assert not state(game).role_punishments


def test_real_frame_grip_ends_on_actual_damage_defeat_frame_loss_not_on_helpless_recovery(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway = ready(ledger, tmp_path, monkeypatch)
    ledger.policy = ledger.policy.model_copy(
        update={
            "owner_m3_rulings": ledger.policy.owner_m3_rulings.model_copy(
                update={"beneath_private_choices": "affected_owner"}
            )
        }
    )
    canon = state(game)
    identity = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        canon.sheets["2"].revision,
        PlayInput(
            play="enforcement_initiative",
            target_actor=current_ref(canon, 3),
            heat=0,
            piloting=True,
            trigger_confirmed=True,
            context="Actual own Frame takes hold",
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    tick(worker, gateway, 6)
    assert game.inspect(PLAYER, identity)["state"] == "complete"
    assert state(game).enforcer_grasps[-1].contact == "frame"
    with ledger.transaction() as c:
        canon = state(game)
        frames = [x for x in canon.sheets["2"].assets if x.family == "frame"]
        for asset in frames[1:]:
            asset.damaged = True
        game.event(c, 1, str(uuid4()), "synthetic.actual_prior_frame_damage", canon)
    game.dice.faces = (1, 1)
    parent = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play="put_someone_beneath_you",
            target=3,
            heat=0,
            piloting=True,
            context="Actual new confrontation while original Frame holds grip",
            trigger_confirmed=True,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    answer(game, OTHER, "beneath_select", options=("damage",), text="Actual source counterattack")
    answer(game, PLAYER, "beneath_details", denied=(frames[0].id,))
    child = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play="defeat",
            parent=parent,
            heat=0,
            context="Actual final Frame Asset damage Defeat",
            trigger_confirmed=True,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    answer(
        game,
        PLAYER,
        "defeat_select",
        options=("lose_frame_choose_later",),
        text="Actual old holding Frame destroyed",
    )
    actual = state(game)
    assert actual.sheets["2"].frame_scrapped
    assert not actual.enforcer_grasps[-1].held and actual.enforcer_grasps[-1].release_event
    assert is_helpless(actual, current_ref(actual, 3), current_ref(actual, 2))
    assert game.inspect(PLAYER, child)["state"] == "complete" and game.dice.calls == 3
    tick(worker, gateway, 6)
    from test_replacement_service import accept, propose, quote

    from girlframe.engine.m3_frame_state import Preferences
    from girlframe.services.m3_missions import MissionService
    from girlframe.services.m3_off_duty import OffDutyService
    from girlframe.services.m3_replacement import DEFEAT_ROOT, ReplacementService

    missions = MissionService(ledger)
    periods = OffDutyService(missions)
    periods.begin(ADMIN, str(uuid4()))
    root = next(x for x in missions.owned_work(PLAYER) if x["kind"] == DEFEAT_ROOT)
    replacements = ReplacementService(missions)
    package = propose(replacements, root["id"], Preferences(frame="WYVERN 0.4"))
    quote(replacements, package["package_id"])
    accept(replacements, root["id"])
    replaced = state(game)
    assert not replaced.sheets["2"].frame_scrapped
    assert replaced.sheets["2"].frame_runtime.id != actual.enforcer_grasps[-1].frame_instance
    assert not replaced.enforcer_grasps[-1].held
    assert is_helpless(replaced, current_ref(replaced, 3), current_ref(replaced, 2))


def test_original_holder_releases_actual_grip_without_moving_target_or_removing_helpless(
    ledger, tmp_path, monkeypatch
):
    from girlframe.services.m3_enforcer import EnforcerService

    game, _, _, identity = rolled(ledger, tmp_path, monkeypatch)
    before = state(game)
    grip = before.enforcer_grasps[-1]
    service = EnforcerService(game)
    with pytest.raises(WorkflowError):
        service.release_grasp(
            OTHER, str(uuid4()), grip.id, before.revision, "Not the original holder"
        )
    ledger.safety(OTHER, str(uuid4()), ledger.status(OTHER)["revision"], pause=True)
    service.release_grasp(
        PLAYER, str(uuid4()), grip.id, state(game).revision, "Actual voluntary release"
    )
    assert ledger.status(OTHER)["paused"]
    after = state(game)
    assert not after.enforcer_grasps[-1].held
    assert after.placements == before.placements
    assert is_helpless(after, current_ref(after, 3), current_ref(after, 2))
    assert game.inspect(PLAYER, identity)["state"] == "complete" and game.dice.calls == 1


def test_low_actual_weapon_on_hand_is_owned_target_choice_and_real_helpless_effect(
    ledger, tmp_path, monkeypatch
):
    from girlframe.services.m3_items import ItemService

    game, worker, gateway = ready(ledger, tmp_path, monkeypatch, (1, 1))
    items = ItemService(game)
    request = items.propose(
        OTHER,
        str(uuid4()),
        current_ref(state(game), 3),
        "Access knife",
        "Actual established carried blade on this original Girl",
        weapon=True,
    )
    items.confirm(
        ADMIN,
        str(uuid4()),
        request["id"],
        1,
        exists=True,
        account="Actual weapon on hand fact confirmed",
    )
    identity = start(game)
    tick(worker, gateway, 3)
    pass_tags(game)
    answer(game, PLAYER, "enforcer_select", options=("hesitate", "escape"))
    choice = next(x for x in game.choices(OTHER) if x["kind"] == "enforcer_hesitate")
    assert game.decision(OTHER, choice["id"])["enforcement"]["items"][0]["id"] == request["id"]
    answer(
        game,
        OTHER,
        "enforcer_hesitate",
        flag=True,
        fields={"weapon": request["id"]},
        text="Actual weapon used during hesitation",
    )
    actual = state(game)
    assert is_helpless(actual, current_ref(actual, 2), current_ref(actual, 3))
    answer(game, OTHER, "enforcer_escape", text="I slip free; the actual map cell is unchanged")
    assert game.inspect(PLAYER, identity)["state"] == "complete" and game.dice.calls == 1


@pytest.mark.parametrize("kind", ["npc", "gorgon", "external_pilot"])
def test_high_actual_world_target_keeps_own_resource_kind_and_source_punishment(
    ledger, tmp_path, monkeypatch, kind
):
    from girlframe.engine.m3_actor_bonds import depth
    from girlframe.engine.m3_actor_state import ActorRef
    from girlframe.engine.m3_world_state import AdversaryPilot

    game, worker, gateway = ready(ledger, tmp_path, monkeypatch, (6, 6))
    with ledger.transaction() as c:
        canon = state(game)
        if kind == "gorgon":
            canon.world = canon.world.model_copy(
                update={
                    "gorgons": tuple(
                        x.model_copy(update={"revealed": True}) for x in canon.world.gorgons
                    )
                }
            )
            target = ActorRef(kind=kind, entity=canon.world.gorgons[0].id)
        elif kind == "external_pilot":
            canon.world = canon.world.model_copy(
                update={
                    "pilots": (
                        AdversaryPilot(
                            id="actual-world-harpy",
                            name="Actual distinct Harpy",
                            kind="harpy",
                            girl="MOCKINGBIRD",
                            frame="JANUS",
                            controller=1,
                            cell=(0, 0),
                            assets=(),
                            revealed=True,
                        ),
                    )
                }
            )
            target = ActorRef(kind=kind, entity="actual-world-harpy")
        else:
            target = ActorRef(kind=kind, entity="known-guard")
        game.event(c, 1, str(uuid4()), "synthetic.actual_known_world_role", canon)
    cast_target(game, target)
    canon = state(game)
    identity = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        canon.sheets["2"].revision,
        PlayInput(
            play="enforcement_initiative",
            target_actor=target,
            heat=0,
            trigger_confirmed=True,
            context="Actual source taking hold of distinct known world actor",
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    case = state(game).role_punishments[-1]
    service = RolePunishmentService(game)

    def change(viewer, **kwargs):
        data = service.get(viewer, case.id)
        return service.change(viewer, str(uuid4()), case.id, data["revision"], **kwargs)

    details = Details(kind="quality_time", tag="Actual source world-role Tag")
    change(
        ADMIN, instruction=Instruction(kind=details.kind, details_json=details.model_dump_json())
    )
    change(PLAYER, scene="Actual instructed Enforcer and distinct world target scene")
    change(ADMIN, attest=True)
    change(PLAYER, execute=True, account="Actual world-role Quality Time performed")
    actual = state(game)
    assert depth(actual, target, current_ref(actual, 2)) == 1
    assert game.inspect(PLAYER, identity)["state"] == "complete" and game.dice.calls == 1
    assert target.entity not in actual.sheets
    assert is_helpless(actual, target, current_ref(actual, 2)) == (kind == "npc")


def test_pause_blocks_owned_response_and_resume_preserves_original_roll(
    ledger, tmp_path, monkeypatch
):
    game, _, _, identity = rolled(ledger, tmp_path, monkeypatch, (1, 1))
    answer(game, PLAYER, "enforcer_select", options=("tag", "escape"))
    ledger.safety(OTHER, str(uuid4()), ledger.status(OTHER)["revision"], pause=True)
    with pytest.raises(WorkflowError):
        answer(game, OTHER, "enforcer_tag", text="No write during actual safety pause")
    ledger.safety(OTHER, str(uuid4()), ledger.status(OTHER)["revision"], pause=False)
    answer(game, OTHER, "enforcer_tag", text="Actual after-resume Tag")
    answer(game, OTHER, "enforcer_escape", text="Actual escape after safety resume")
    assert game.inspect(PLAYER, identity)["state"] == "complete" and game.dice.calls == 1
