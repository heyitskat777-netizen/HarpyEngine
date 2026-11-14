"""Actual native Oldgen and independently controlled ordinary NPC, no invented rank."""

from uuid import uuid4

import pytest
from test_cast_service import change as cast_change
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import pass_tags, state, tick
from test_oldgen_sex import native_choice, setup

from girlframe.engine import m3_oldgen_sex as rules
from girlframe.engine.m2 import ChoiceAnswer, PlayInput
from girlframe.engine.m3_actor_bonds import current_ref, depth
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_mockingbird import actor_tags
from girlframe.engine.m3_world_state import Npc
from girlframe.services.m3_actors import ActorService
from girlframe.services.m3_body_facts import BodyFactsService
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_oldgen_sex import prove, prove_effect
from girlframe.services.m3_world import WorldService
from girlframe.services.onboarding import WorkflowError


def test_original_npc_consent_world_tag_bond_and_reciprocal_actual_status(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, service, _ = setup(ledger, tmp_path, monkeypatch)
    approval = ledger.policy.m3_approval
    ledger.policy = ledger.policy.model_copy(
        update={
            "m3_approval": approval.model_copy(
                update={"subsystems": approval.subsystems | {"world"}}
            )
        }
    )
    missions = MissionService(ledger)
    npc = ActorRef(kind="npc", entity="original-oldgen-counterpart")
    WorldService(missions).npc(
        ADMIN,
        str(uuid4()),
        state(game).revision,
        Npc(
            id=npc.entity,
            name="Pat",
            jobs=("guard",),
            controller=1,
            detail="PRIVATE_OLDGEN_NPC_DETAIL",
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
        "PRIVATE_OLDGEN_NPC_SOURCE Actual voluntary original encounter",
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
    game.dice.faces = (6, 6)
    before = state(game)
    action = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        before.sheets["2"].revision,
        PlayInput(
            play=rules.PLAY,
            source_work=identity,
            target_actor=npc,
            heat=1,
            context="Actual original NPC encounter",
            trigger_confirmed=True,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    row = next(x for x in game.choices(PLAYER) if x["kind"] == "oldgen_sex_effects")
    assert game.decision(PLAYER, row["id"])["detail"]["unsupported_status"]
    pending = state(game)
    with pytest.raises(WorkflowError, match="UNSUPPORTED_NPC_STATUS"):
        game.respond(
            PLAYER,
            str(uuid4()),
            row["id"],
            row["revision"],
            ChoiceAnswer(options=("tag", "status"), fields={"tag": "Not committed"}),
        )
    assert state(game) == pending
    assert not actor_tags(state(game), npc)
    native_choice(
        game,
        PLAYER,
        "oldgen_sex_effects",
        ("tag", "bond"),
        fields={"tag": "Actual original NPC Tag"},
    )
    native_choice(game, ADMIN, "oldgen_sex_creep", ("yes",))
    rank_before = state(game).order.index(2)
    native_choice(game, ADMIN, "oldgen_sex_effects", ("status",))
    final = state(game)
    session = rules.get(final, identity)
    assert session.phase == "complete" and session.completed_event
    assert final.order.index(2) == min(rank_before + 1, len(final.order) - 1)
    assert final.sheets["2"].heat == before.sheets["2"].heat - 1
    assert depth(final, current_ref(final, 2), npc) == 1
    effects = [x for x in rules.records(final, rules.Effect) if x.session == identity]
    tag_effect = next(x for x in effects if x.kind == "tag")
    assert tag_effect.tag is None and tag_effect.npc_tag in actor_tags(final, npc)
    assert ActorRef.model_validate_json(tag_effect.npc_tag.giver_entity) == current_ref(final, 2)
    status_effect = next(x for x in effects if x.kind == "status")
    assert status_effect.owner == npc and status_effect.target == current_ref(final, 2)
    assert status_effect.after == final.order.index(2)
    assert session.action == action and game.dice.calls == 1
    with ledger.engine.connect() as c:
        assert prove(game, c, final, identity) == session
        for effect in effects:
            assert prove_effect(game, c, final, effect.id) == effect
    snapshot = state(game)
    with pytest.raises(WorkflowError):
        service.respond(ADMIN, str(uuid4()), identity, snapshot.revision, True, "No replay")
    assert state(game) == snapshot
    tick(worker, gateway, 8)
    assert "PRIVATE_OLDGEN_NPC_SOURCE" not in str(gateway.messages)
