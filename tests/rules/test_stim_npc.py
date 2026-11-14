"""Actual Stim NPC drug physiology with source contact and explicit unsupported Orders."""

from uuid import uuid4

import pytest
from test_cast_service import change as cast_change
from test_dose_up import ready
from test_enforcer_requisitions import approved
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import pass_tags, state, tick
from test_stim_sex import choose

from girlframe.engine import m3_stim_sex as rules
from girlframe.engine.m2 import PlayInput
from girlframe.engine.m3_actor_bonds import is_helpless
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_mockingbird import actor_tags
from girlframe.engine.m3_world_state import Npc
from girlframe.services.m3_actors import ActorService
from girlframe.services.m3_body_facts import BodyFactsService
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_stim_sex import SexService, _drug, prove, prove_effect
from girlframe.services.m3_world import WorldService
from girlframe.services.onboarding import WorkflowError


def test_actual_npc_mid_drug_helpless_expiry_and_atomic_orders_fallback(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, _ = ready(ledger, tmp_path, monkeypatch)
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
    game.dice.faces = (3, 4)
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
            context="Actual original voluntary NPC source",
            trigger_confirmed=True,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    choose(game, PLAYER, "stim_sex_drug", ("quick",), native=True)
    before_unsupported = state(game)
    with pytest.raises(WorkflowError, match="human adjudication"):
        choose(game, PLAYER, "stim_sex_effects", ("orders",))
    assert state(game) == before_unsupported
    assert game.inspect(PLAYER, action)["state"] != "complete"
    choose(game, PLAYER, "stim_sex_effects", ("helpless",), native=True)
    final = state(game)
    drug = rules.records(final, rules.Drug)[-1]
    effect = rules.records(final, rules.Effect)[-1]
    assert drug.target == npc and drug.tag in actor_tags(final, npc)
    assert is_helpless(final, npc)
    assert final.sheets["2"].heat == before.sheets["2"].heat - 1
    assert game.inspect(PLAYER, action)["state"] == "complete" and game.dice.calls == 1
    with ledger.engine.connect() as c:
        assert _drug(game, c, final, drug.id) == drug
        assert prove_effect(game, c, final, effect.id) == effect
    tick(worker, gateway, 8)
    for number in (1, 2):
        game.close_scene(ADMIN, str(uuid4()), 900)
        if number == 1:
            assert is_helpless(state(game), npc)
            game.bind_scene(ADMIN, str(uuid4()), 900)
            for person in (ADMIN, PLAYER, OTHER):
                game.join_scene(person, str(uuid4()), 900)
            cast_change(CastService(ActorService(missions)), ADMIN, "join", npc)
    final = state(game)
    assert rules.expired(final, drug.id) and not is_helpless(final, npc)
    assert not any(x.id == drug.id for x in actor_tags(final, npc))
    with ledger.engine.connect() as c:
        assert _drug(game, c, final, drug.id) == drug
        assert prove(game, c, final, identity).phase == "complete"
    assert "PRIVATE_OLDGEN_NPC_DETAIL" not in str(gateway.messages)
