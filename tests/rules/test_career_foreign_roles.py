"""Ending one original Pilot never closes a separately controlled body or its scene membership."""

import json
from uuid import uuid4

import sqlalchemy as sa
from test_ledger import ledger as ledger
from test_m2_game import state
from test_mission_service import service
from test_world import initial

from girlframe.database import tables as t
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef, CastRole, SceneCast
from girlframe.engine.m3_world_state import Npc
from girlframe.services.m3_careers import end_in_transaction, synchronize_end
from girlframe.services.m3_work import related


def test_original_pilot_ending_preserves_foreign_body_work_and_actual_same_human_scene_role(ledger):
    _, game = service(ledger)
    with ledger.transaction() as c:
        canon = state(game)
        original = current_ref(canon, 2)
        npc = ActorRef(kind="npc", entity="separate-original-npc")
        canon.world = initial().model_copy(
            update={
                "npcs": (
                    Npc(
                        id=npc.entity,
                        name="Separate controlled body",
                        jobs=("mechanic",),
                        controller=2,
                        cell=(0, 0),
                        detail="An actual distinct person under the same human controller",
                    ),
                )
            }
        )
        scene = game.scene(c, 900)
        canon.scene_casts = [
            SceneCast(
                id=scene["id"],
                channel=900,
                facilitator=1,
                facilitator_source="actual-existing-facilitator",
                roles=(
                    CastRole(actor=original, controller=2, source_event="actual-original-casting"),
                    CastRole(actor=npc, controller=2, source_event="actual-npc-casting"),
                    CastRole(
                        actor=current_ref(canon, 3),
                        controller=3,
                        source_event="actual-third-casting",
                    ),
                ),
            )
        ]
        source_event = str(uuid4())
        game.event(
            c,
            1,
            str(uuid4()),
            "synthetic.actual_distinct_body_sources",
            canon,
            event_id=source_event,
        )
        scope = dict(campaign_id=ledger.campaign_id, scene_id=scene["id"])
        related(
            c,
            ledger,
            scope,
            "actual-npc-work",
            2,
            2,
            "synthetic_npc_consequence",
            dict(owner=npc.model_dump(mode="json"), character=None),
            source_event,
        )
        related(
            c,
            ledger,
            scope,
            "actual-pilot-work",
            2,
            2,
            "synthetic_pilot_consequence",
            dict(owner=original.model_dump(mode="json"), character=original.incarnation),
            source_event,
        )
        ending = str(uuid4())
        ended = end_in_transaction(
            c,
            game,
            canon,
            original,
            reason="death",
            source_event=ending,
            account="Actual original Pilot ending",
            archive_id="actual-original-end",
        )
        game.event(c, 2, str(uuid4()), "m3.synthetic_ending", ended, event_id=ending)
        synchronize_end(c, game, ended.career_archives[-1])
    with ledger.engine.connect() as c:
        table = t.m3["m3_required_work"]
        latest = {
            x["id"]: x for x in c.execute(sa.select(table).order_by(table.c.revision)).mappings()
        }
        assert latest["actual-npc-work"]["state"] != "resolved"
        assert latest["actual-npc-work"]["revision"] == 1
        assert latest["actual-pilot-work"]["state"] == "resolved"
        assert json.loads(game.scene(c, 900)["participants_json"]) == [1, 2, 3]
    assert all(role.actor != original for role in state(game).scene_casts[0].roles)
    assert any(
        role.actor == npc and role.controller == 2 for role in state(game).scene_casts[0].roles
    )
