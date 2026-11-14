"""Actual low Alpha NPC Quality Time source, consequence and original wake."""

from uuid import uuid4

import pytest
from pydantic import ValidationError
from test_alpha_brutalize import ready
from test_cast_service import change as cast_change
from test_enforcer_requisitions import approved
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Dice, answer, pass_tags, state, tick

from girlframe.engine import m3_alpha_sex as rules
from girlframe.engine.m2 import ChoiceAnswer, PlayInput
from girlframe.engine.m3_actor_bonds import current_ref, depth
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_punishments import Details
from girlframe.engine.m3_role_punishment_state import Instruction
from girlframe.engine.m3_world_state import Npc
from girlframe.services.m3_actors import ActorService
from girlframe.services.m3_alpha_sex import SexService, prove
from girlframe.services.m3_body_facts import BodyFactsService
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_role_punishments import RolePunishmentService
from girlframe.services.m3_world import WorldService
from girlframe.services.onboarding import WorkflowError


def test_actual_low_npc_quality_time_and_original_wake(ledger, tmp_path, monkeypatch):
    game, worker, gateway = ready(ledger, tmp_path, monkeypatch, (4, 4))
    approved(ledger, game, tmp_path, monkeypatch, extra=(rules.RULE,))
    service = SexService(game)
    approval = ledger.policy.m3_approval
    ledger.policy = ledger.policy.model_copy(
        update={
            "m3_approval": approval.model_copy(
                update={"subsystems": approval.subsystems | {"world"}}
            )
        }
    )
    missions = MissionService(ledger)
    npc = ActorRef(kind="npc", entity="original-alpha-counterpart")
    WorldService(missions).npc(
        ADMIN,
        str(uuid4()),
        state(game).revision,
        Npc(
            id=npc.entity,
            name="Pat",
            jobs=("guard",),
            controller=1,
            detail="PRIVATE_ALPHA_NPC_DETAIL",
            revealed=True,
            cell=(0, 0),
        ),
    )
    cast_change(CastService(ActorService(missions)), ADMIN, "join", npc)
    BodyFactsService(game).record(
        ADMIN,
        str(uuid4()),
        state(game).revision,
        900,
        npc,
        "human_npc",
        "I witness this actual original ordinary civilian's human body and brain",
    )
    assert any(
        x["ref"] == npc.model_dump(mode="json") for x in service.menu(PLAYER, 900)["targets"]
    )
    identity = service.invite(
        PLAYER,
        str(uuid4()),
        900,
        npc,
        state(game).revision,
        "PRIVATE_ALPHA_NPC_SOURCE Actual voluntary original encounter",
    )["id"]
    before = state(game)
    with pytest.raises(WorkflowError):
        service.respond(OTHER, str(uuid4()), identity, before.revision, True, "Not my NPC")
    assert state(game) == before
    with pytest.raises(WorkflowError, match="Attest actual physical contact"):
        service.respond(
            ADMIN,
            str(uuid4()),
            identity,
            before.revision,
            True,
            "Consent alone is not spatial evidence",
        )
    assert state(game) == before
    service.respond(
        ADMIN,
        str(uuid4()),
        identity,
        before.revision,
        True,
        "Actual original NPC controller confirms voluntary interaction",
        npc_contact_account="Actual original body contact here, outside all enclosures and rides",
    )

    def perform(identity, faces):
        game.dice = Dice(faces)
        action = game.begin(
            PLAYER,
            str(uuid4()),
            900,
            state(game).sheets["2"].revision,
            PlayInput(
                play=rules.PLAY,
                source_work=identity,
                target_actor=npc,
                heat=0,
                context="Actual confirmed original NPC interaction",
                trigger_confirmed=True,
            ),
        )["action_id"]
        tick(worker, gateway, 3)
        pass_tags(game)
        return action

    action = perform(identity, (1, 1))
    before = state(game)
    value = rules.get(before, identity)
    assert value.phase == "sleeping" and value.sleep_event
    row = next(x for x in game.choices(ADMIN) if x["kind"] == "alpha_sex_low")
    with pytest.raises(WorkflowError):
        game.respond(
            OTHER, str(uuid4()), row["id"], row["revision"], ChoiceAnswer(options=("punish",))
        )
    assert state(game) == before
    answer(game, ADMIN, "alpha_sex_low", options=("punish",))
    source = state(game)
    case = next(x for x in source.role_punishments if x.action == action)
    assert case.source_kind == "alpha_sex" and case.source_work == identity
    assert case.executor == npc and case.chooser == npc
    assert case.executor_controller == case.chooser_controller == ADMIN.user_id
    assert case.subject == current_ref(source, PLAYER.user_id)
    for invalid in (
        {"chooser": case.subject},
        {"action": None},
        {"source_work": None},
        {"pc_work": "unrelated"},
    ):
        with pytest.raises(ValidationError):
            type(case).model_validate_json(case.model_copy(update=invalid).model_dump_json())
    role = RolePunishmentService(game)

    def change(viewer, **values):
        return role.change(
            viewer, str(uuid4()), case.id, role.get(viewer, case.id)["revision"], **values
        )

    details = Details(kind="quality_time", tag="Actual NPC's source-granted consequence")
    change(
        ADMIN, instruction=Instruction(kind=details.kind, details_json=details.model_dump_json())
    )
    change(ADMIN, scene="Actual original NPC carries out selected Quality Time")
    change(PLAYER, attest=True)
    unchanged = state(game)
    with pytest.raises(WorkflowError):
        change(OTHER, execute=True, account="Not the actual NPC controller")
    assert state(game) == unchanged
    change(ADMIN, execute=True, account="Actual original NPC completes source-owned Quality Time")
    after = state(game)
    completed = next(x for x in after.role_punishments if x.id == case.id)
    assert completed.effect_event and completed.completion_event
    assert rules.get(after, identity).phase == "waking" and rules.asleep(after, value.actor)
    assert game.inspect(PLAYER, action)["state"] != "complete"
    actual_tags = [x for x in after.sheets["2"].tags if x.label == details.tag]
    assert len(actual_tags) == 1 and actual_tags[0].giver_actor == npc
    assert depth(after, value.actor, npc) == depth(before, value.actor, npc) + 1
    answer(
        game, PLAYER, "alpha_sex_wake", options=("wake",), text="The original Alpha actually wakes"
    )
    final = state(game)
    assert not rules.asleep(final, value.actor)
    assert rules.get(final, identity).phase == "complete"
    assert game.inspect(PLAYER, action)["state"] == "complete" and game.dice.calls == 1
    with ledger.engine.connect() as c:
        assert prove(game, c, final, identity) == rules.get(final, identity)
    snapshot = state(game)
    with pytest.raises(WorkflowError):
        change(ADMIN, execute=True, account="Cannot repeat the completed punishment")
    assert state(game) == snapshot
    assert "PRIVATE_ALPHA_NPC_DETAIL" not in repr(gateway.messages)
