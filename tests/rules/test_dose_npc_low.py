"""Actual low Dose NPC recipient owns a genuine social Punishment instead of drugs."""

from uuid import uuid4

import pytest
from pydantic import ValidationError
from test_cast_service import change as cast_change
from test_dose_up import native_choice, ready
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import pass_tags, state, tick

from girlframe.engine import m3_dose_up as rules
from girlframe.engine.m2 import PlayInput
from girlframe.engine.m3_actor_bonds import current_ref, depth
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_mockingbird import actor_tags
from girlframe.engine.m3_punishments import Details
from girlframe.engine.m3_role_punishment_state import Instruction
from girlframe.engine.m3_world_state import Npc
from girlframe.services.m3_actors import ActorService
from girlframe.services.m3_body_facts import BodyFactsService
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_dose_up import prove
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_role_punishments import RolePunishmentService
from girlframe.services.m3_world import WorldService
from girlframe.services.onboarding import WorkflowError


def test_actual_low_npc_quality_time_punishment_completes_parent_without_drugs(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, controls = ready(ledger, tmp_path, monkeypatch)
    approval = ledger.policy.m3_approval
    ledger.policy = ledger.policy.model_copy(
        update={
            "m3_approval": approval.model_copy(
                update={"subsystems": approval.subsystems | {"world"}}
            )
        }
    )
    missions = MissionService(ledger)
    npc = ActorRef(kind="npc", entity="actual-dose-recipient")
    WorldService(missions).npc(
        ADMIN,
        str(uuid4()),
        state(game).revision,
        Npc(
            id=npc.entity,
            name="Pat",
            jobs=("guard",),
            controller=1,
            cell=(0, 0),
            revealed=True,
            detail="Actual ordinary human source recipient",
        ),
    )
    casts = CastService(ActorService(missions))
    cast_change(casts, ADMIN, "join", npc)
    before = state(game)
    with pytest.raises(WorkflowError):
        controls.record_contact(
            PLAYER, str(uuid4()), 900, npc, before.revision, "A name alone is not actual anatomy"
        )
    assert state(game) == before
    BodyFactsService(game).record(
        ADMIN,
        str(uuid4()),
        state(game).revision,
        900,
        npc,
        "human_npc",
        "Actual witnessed human body and brain",
    )
    assert any(
        x["ref"] == npc.model_dump(mode="json") for x in controls.menu(PLAYER, 900)["targets"]
    )
    contact = controls.record_contact(
        PLAYER,
        str(uuid4()),
        900,
        npc,
        state(game).revision,
        "PRIVATE_NPC_VEIN My hand actually reaches this original body's exposed vein here",
    )["id"]
    game.dice.faces = (1, 1)
    before = state(game)
    action = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        before.sheets["2"].revision,
        PlayInput(
            play=rules.PLAY,
            target_actor=npc,
            source_work=contact,
            heat=1,
            context="Actual original recipient dosing",
            trigger_confirmed=True,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    pending = state(game)
    row = next(x for x in game.choices(ADMIN) if x["kind"] == "dose_up_target_low")
    from girlframe.engine.m2 import ChoiceAnswer

    with pytest.raises(WorkflowError):
        game.respond(
            OTHER, str(uuid4()), row["id"], row["revision"], ChoiceAnswer(options=("punish",))
        )
    assert state(game) == pending
    native_choice(game, ADMIN, ("punish",))
    source = state(game)
    case = next(x for x in source.role_punishments if x.action == action)
    assert case.source_kind == "dose_up"
    assert case.executor == npc and case.chooser == npc
    assert case.executor_controller == 1 and case.chooser_controller == 1
    assert case.subject == current_ref(source, 2)
    for invalid in (
        {"chooser": current_ref(source, 2)},
        {"action": None},
        {"source_kind": "alpha_sex"},
    ):
        with pytest.raises(ValidationError):
            type(case).model_validate_json(case.model_copy(update=invalid).model_dump_json())
    assert not rules.records(source, rules.NpcDrugTag)
    assert not rules.records(source, rules.DrugTag)
    assert game.inspect(PLAYER, action)["state"] != "complete"
    role = RolePunishmentService(game)

    def change(viewer, **values):
        return role.change(
            viewer, str(uuid4()), case.id, role.get(viewer, case.id)["revision"], **values
        )

    details = Details(kind="quality_time", tag="Actual NPC's source-granted consequence")
    change(
        ADMIN, instruction=Instruction(kind=details.kind, details_json=details.model_dump_json())
    )
    change(ADMIN, scene="The actual original NPC carries out her selected Quality Time")
    change(PLAYER, attest=True)
    unchanged = state(game)
    with pytest.raises(WorkflowError):
        change(OTHER, execute=True, account="Not the original NPC controller")
    assert state(game) == unchanged
    change(ADMIN, execute=True, account="Actual NPC Quality Time instead of receiving the cocktail")
    final = state(game)
    completed = next(x for x in final.role_punishments if x.id == case.id)
    assert completed.effect_event and completed.completion_event
    assert depth(final, current_ref(final, 2), npc) == 1
    tags = [x for x in final.sheets["2"].tags if x.label == details.tag]
    assert len(tags) == 1 and tags[0].giver_actor == npc and tags[0].giver == 1
    assert final.sheets["2"].heat == before.sheets["2"].heat - 1
    assert not rules.records(final, rules.NpcDrugTag)
    assert not rules.records(final, rules.DrugTag)
    assert not actor_tags(final, npc)
    assert game.inspect(PLAYER, action)["state"] == "complete" and game.dice.calls == 1
    with ledger.engine.connect() as c:
        result = prove(game, c, final, action)
        assert result.punishment == case.id and result.total <= 7 and result.selections == ()
    snapshot = state(game)
    with pytest.raises(WorkflowError):
        change(ADMIN, execute=True, account="Cannot repeat this completed consequence")
    assert state(game) == snapshot
    tick(worker, gateway, 8)
    assert "PRIVATE_NPC_VEIN" not in str(gateway.messages)
