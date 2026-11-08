"""Deferred proven Ankou benefit; an NPC Play still pays its genuine Bond cost."""

from uuid import uuid4

import pytest
from test_ankou import buy, ready
from test_cast_service import change as cast_change
from test_enforcer_requisitions import approved
from test_ledger import ADMIN, PLAYER
from test_ledger import ledger as ledger_fixture
from test_m2_game import state

from girlframe.engine import m3_ankou as ankou
from girlframe.engine import m3_bond_operations as operations
from girlframe.engine import m3_npc_bond_play as npc_play
from girlframe.engine.m3_actor_bonds import current_ref, depth
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_world_state import Npc
from girlframe.services.m3_actors import ActorService
from girlframe.services.m3_ankou_bonds import intense_benefit
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_npc_bond_play import (
    NpcBondPlayService,
    prove_performance,
    prove_request,
)
from girlframe.services.m3_world import WorldService
from girlframe.services.onboarding import WorkflowError

ledger = ledger_fixture


def test_proven_directional_obsession_cannot_supply_a_fabricated_npc_bond_to_spend(
    ledger, tmp_path, monkeypatch
):
    game, _, _, controls = ready(ledger, tmp_path, monkeypatch)
    approved(
        ledger,
        game,
        tmp_path,
        monkeypatch,
        extra=(ankou.OBSESSIVE, npc_play.RULE, "npc.npc.public-relations"),
    )
    ledger.policy = ledger.policy.model_copy(
        update={
            "m3_approval": ledger.policy.m3_approval.model_copy(
                update={
                    "subsystems": ledger.policy.m3_approval.subsystems | {"world"},
                }
            ),
        }
    )
    missions = MissionService(ledger)
    world = WorldService(missions)
    original = state(game)
    saved = original.sheets["2"].review.creation.npc_bonds[0]
    actor = current_ref(original, 2)
    npc = ActorRef(kind="npc", entity="actual-ankou-contact")
    world.npc(
        ADMIN,
        str(uuid4()),
        original.revision,
        Npc(
            id=npc.entity,
            name=saved.name.strip() or "Actual starting contact",
            jobs=("public_relations",),
            detail="The actual saved contact now works in public relations",
            controller=1,
            cell=(0, 0),
            revealed=True,
        ),
    )
    world.import_starting_npc(PLAYER, str(uuid4()), state(game).revision, saved.slot, npc.entity)
    assert depth(state(game), actor, npc) == 1
    buy(controls, ankou.OBSESSIVE)
    before_obsession = state(game)
    controls.choose_obsession(
        PLAYER,
        str(uuid4()),
        before_obsession.revision,
        npc,
        "This actual original NPC is my one-sided Obsession",
    )
    current = state(game)
    assert depth(current, actor, npc) == 1
    with ledger.engine.connect() as c:
        assert intense_benefit(game, c, current, actor, npc)
        assert not intense_benefit(game, c, current, npc, actor)
    assert operations.records(current) == operations.records(before_obsession)
    assert current.sheets["2"].permissions == before_obsession.sheets["2"].permissions

    plays = NpcBondPlayService(ledger)
    key = str(uuid4())
    requested = plays.request(
        PLAYER,
        key,
        current.revision,
        npc,
        "public_relations",
        "Smooth things over",
        "Use this actual personal Bond for a real source NPC Play",
    )
    assert (
        plays.request(
            PLAYER,
            key,
            current.revision,
            npc,
            "public_relations",
            "Smooth things over",
            "Use this actual personal Bond for a real source NPC Play",
        )
        == requested
    )
    assert depth(state(game), actor, npc) == 0
    with ledger.engine.connect() as c:
        proof = prove_request(game, c, state(game), requested["id"])
        assert (proof.before_depth, proof.after_depth) == (1, 0)
        assert intense_benefit(game, c, state(game), actor, npc)
        assert not intense_benefit(game, c, state(game), npc, actor)
    exact = state(game)
    with pytest.raises(WorkflowError, match="actual canonical NPC Bond"):
        plays.request(
            PLAYER,
            str(uuid4()),
            exact.revision,
            npc,
            "public_relations",
            "Smooth things over",
            "The virtual benefit cannot pay another real Bond cost",
        )
    assert state(game) == exact

    casts = CastService(ActorService(missions))
    cast_change(casts, ADMIN, "join", npc)
    done = plays.perform(
        ADMIN,
        str(uuid4()),
        requested["id"],
        state(game).revision,
        900,
        (actor,),
        "I actually smooth things over with the addressed original Girl in this scene",
    )
    assert done["phase"] == "complete"
    with ledger.engine.connect() as c:
        performed = prove_performance(game, c, state(game), requested["id"])
        assert performed.controller == 1 and performed.recipients[0].actor == actor
    assert depth(state(game), actor, npc) == 0
