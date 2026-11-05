"""Real Handler effect → source-proved NPC consequence, with actual object custody."""

from uuid import uuid4

import pytest
import sqlalchemy as sa
from test_handler_plays import ready
from test_items import carried_asset, transfer
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state

from girlframe.database import tables as t
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_handler_play_state import Effect
from girlframe.engine.m3_world_state import Npc
from girlframe.services.m3_battle_npc import NpcDamageService
from girlframe.services.m3_world import WorldService
from girlframe.services.onboarding import WorkflowError


def source(store):
    handler, game = ready(store)
    world = WorldService(
        __import__("girlframe.services.m3_missions", fromlist=["MissionService"]).MissionService(
            store
        )
    )
    world.npc(
        ADMIN,
        "actual-damage-npc",
        state(game).revision,
        Npc(
            id="battle-person",
            name="Actual guard",
            jobs=("guard",),
            detail="The original real NPC",
            controller=1,
            cell=(0, 0),
            revealed=True,
        ),
    )
    original = state(game)
    asset = next(x for x in original.sheets["3"].assets if x.family == "girl")
    carried_asset(game, OTHER, asset)
    target = ActorRef(kind="npc", entity="battle-person")
    item = transfer(game, current_ref(state(game), 3), target, "asset:" + asset.id)
    grant = handler.start(ADMIN, "actual-npc-hit", state(game).revision, (target,))["id"]
    handler.submit(
        ADMIN,
        "actual-damage-effect",
        grant,
        state(game).revision,
        "mess",
        Effect(
            kind="damage",
            account="The source-owned actual object is hit",
            target=target,
            asset=item.asset_id,
        ),
    )
    with store.engine.connect() as c:
        table = t.m3["m3_required_work"]
        row = (
            c.execute(
                sa.select(table).where(
                    table.c.campaign_id == store.campaign_id, table.c.kind == "npc_damage"
                )
            )
            .mappings()
            .one()
        )
    return game, handler, grant, NpcDamageService(store), dict(row), target, item


@pytest.mark.parametrize("effect", ["injure_tag", "kill"])
def test_actual_npc_substitution_never_damages_fictitious_body_slots_and_completes_source_once(
    ledger, effect
):
    game, handler, grant, svc, row, target, item = source(ledger)
    before = state(game)
    assert not before.world.npcs[-1].tags and before.world.npcs[-1].alive
    with pytest.raises(WorkflowError):
        svc.get(PLAYER, row["id"])
    result = svc.respond(
        ADMIN,
        "actual-npc-consequence",
        row["id"],
        row["revision"],
        effect,
        "The original NPC suffers the actual printed consequence",
        tag="Broken and bleeding" if effect == "injure_tag" else "",
    )
    assert (
        svc.respond(
            ADMIN,
            "actual-npc-consequence",
            row["id"],
            row["revision"],
            effect,
            "The original NPC suffers the actual printed consequence",
            tag="Broken and bleeding" if effect == "injure_tag" else "",
        )
        == result
    )
    after = state(game)
    npc = next(x for x in after.world.npcs if x.id == target.entity)
    assert npc.alive == (effect != "kill")
    assert bool(npc.tags) == (effect == "injure_tag")
    assert after.held_items == before.held_items and after.sheets == before.sheets
    assert handler.get(ADMIN, grant)["grant"]["state"] == "complete"
    assert svc.get(ADMIN, row["id"])["state"] == "resolved"
    with ledger.engine.connect() as c:
        assert c.scalar(sa.select(sa.func.count()).select_from(t.m2["m2_responses"])) == 0


def test_actual_advantage_waits_for_real_optional_handler_decision_and_safety_blocks_mutation(
    ledger,
):
    game, handler, grant, svc, row, target, item = source(ledger)
    ledger.safety(OTHER, "pause-npc", ledger.status(OTHER)["revision"], pause=True)
    assert svc.get(ADMIN, row["id"])["state"] == "pending"
    with pytest.raises(WorkflowError, match="SAFETY_PAUSED"):
        svc.respond(
            ADMIN, "paused-npc", row["id"], row["revision"], "advantage", "Cannot act while paused"
        )
    ledger.safety(OTHER, "resume-npc", ledger.status(OTHER)["revision"], pause=False)
    result = svc.respond(
        ADMIN,
        "actual-advantage",
        row["id"],
        row["revision"],
        "advantage",
        "The guard loses access to the actual alarm console",
    )
    assert result["phase"] == "optional_tag"
    assert handler.get(ADMIN, grant)["grant"]["state"] == "awaiting_effect"
    svc.optional_tag(ADMIN, "actual-gm-decline", row["id"], result["revision"], None)
    assert handler.get(ADMIN, grant)["grant"]["state"] == "complete"
    assert not next(x for x in state(game).world.npcs if x.id == target.entity).tags


def test_changed_revision_and_foreign_consequence_cannot_fake_injury(ledger):
    game, _, _, svc, row, _, _ = source(ledger)
    before = state(game)
    with pytest.raises(WorkflowError):
        svc.respond(
            PLAYER, str(uuid4()), row["id"], row["revision"], "kill", "Not the source chooser"
        )
    with pytest.raises(WorkflowError, match="STALE_NPC_DAMAGE"):
        svc.respond(ADMIN, str(uuid4()), row["id"], row["revision"] + 1, "kill", "Stale attempt")
    assert state(game) == before
