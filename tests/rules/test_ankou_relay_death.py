"""Real NPC consequence produces owned ANKOU Identity erasure and four Heat."""

from uuid import uuid4

import pytest
import sqlalchemy as sa
from test_ankou import ready
from test_items import carried_asset, transfer
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger_fixture
from test_m2_game import state

from girlframe.database import tables as t
from girlframe.engine import m3_ankou as rules
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_handler_play_state import Effect
from girlframe.engine.m3_world_state import Npc
from girlframe.services.m3_battle_npc import NpcDamageService
from girlframe.services.m3_handler_plays import HandlerPlayService
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_world import WorldService
from girlframe.services.onboarding import WorkflowError

ledger = ledger_fixture


def test_actual_npc_death_creates_owned_identity_and_heat_consequence(
    ledger, tmp_path, monkeypatch
):
    game, _, _, controls = ready(ledger, tmp_path, monkeypatch)
    previous = ledger.policy.m3_approval
    ledger.policy = ledger.policy.model_copy(
        update={
            "m3_approval": previous.model_copy(
                update={"subsystems": previous.subsystems | {"world"}}
            )
        }
    )
    world = WorldService(MissionService(ledger))
    world.npc(
        ADMIN,
        str(uuid4()),
        state(game).revision,
        Npc(
            id="relay-guard",
            name="Relay guard",
            jobs=("guard",),
            detail="Actual NPC for the death consequence",
            controller=1,
            cell=(0, 0),
            revealed=True,
        ),
    )
    target = ActorRef(kind="npc", entity="relay-guard")
    asset = next(x for x in state(game).sheets["3"].assets if x.family == "girl")
    carried_asset(game, OTHER, asset)
    item = transfer(game, current_ref(state(game), 3), target, "asset:" + asset.id)
    relay = controls.activate_relay(
        PLAYER,
        str(uuid4()),
        900,
        state(game).revision,
        ("speech", "sense"),
        "The actual pilot activates her emotional relay",
    )["id"]
    controls.choose_consequence(
        ADMIN,
        str(uuid4()),
        state(game).revision,
        relay,
        "death",
        "An actual NPC death will cause the printed consequence",
    )
    handler = HandlerPlayService(ledger)
    grant = handler.start(ADMIN, str(uuid4()), state(game).revision, (target,))["id"]
    handler.submit(
        ADMIN,
        str(uuid4()),
        grant,
        state(game).revision,
        "mess",
        Effect(
            kind="damage",
            account="The actual source-owned NPC equipment is hit",
            target=target,
            asset=item.asset_id,
        ),
    )
    with ledger.engine.connect() as c:
        table = t.m3["m3_required_work"]
        row = dict(
            c.execute(
                sa.select(table).where(
                    table.c.campaign_id == ledger.campaign_id, table.c.kind == "npc_damage"
                )
            )
            .mappings()
            .one()
        )
    npc_damage = NpcDamageService(ledger)
    death_key = str(uuid4())
    death = npc_damage.respond(
        ADMIN,
        death_key,
        row["id"],
        row["revision"],
        "kill",
        "The original NPC actually dies from this source consequence",
    )
    actual = state(game)
    assert not next(x for x in actual.world.npcs if x.id == target.entity).alive
    tasks = [x for x in rules.records(actual, rules.Task) if x.kind == "death_identity"]
    assert len(tasks) == 1
    task = tasks[0]
    assert task.actor == current_ref(actual, 2) and task.controller == PLAYER.user_id
    assert task.target == target and not task.completed_event
    identity = next(
        x
        for x in actual.sheets["2"].identities
        if not (x.protected or x.paired or x.am_limiter)
        and x.id not in actual.sheets["2"].sedation_locked
    )
    heat = actual.sheets["2"].heat
    identities = actual.sheets["2"].identities.copy()
    before = actual.model_dump_json()
    with pytest.raises(WorkflowError):
        controls.choose_task(
            OTHER,
            str(uuid4()),
            actual.revision,
            task.id,
            "erase",
            "This is not my Identity to erase",
            identity_to_erase=identity.id,
        )
    assert state(game).model_dump_json() == before
    key = str(uuid4())
    revision = state(game).revision
    result = controls.choose_task(
        PLAYER,
        key,
        revision,
        task.id,
        "erase",
        "I choose this actual eligible Identity",
        identity_to_erase=identity.id,
    )
    after = state(game)
    assert after.sheets["2"].identities == [x for x in identities if x.id != identity.id]
    assert after.sheets["2"].heat == heat + 4
    assert rules.get(after, rules.Task, task.id).completed_event
    assert (
        controls.choose_task(
            PLAYER,
            key,
            revision,
            task.id,
            "erase",
            "I choose this actual eligible Identity",
            identity_to_erase=identity.id,
        )
        == result
    )
    assert (
        npc_damage.respond(
            ADMIN,
            death_key,
            row["id"],
            row["revision"],
            "kill",
            "The original NPC actually dies from this source consequence",
        )
        == death
    )
    assert state(game).model_dump_json() == after.model_dump_json()
    assert handler.get(ADMIN, grant)["grant"]["state"] == "complete"
