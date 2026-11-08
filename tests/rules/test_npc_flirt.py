"""One deferred high native NPC Flirt: actual Court, Conversation and self-cost."""

import asyncio
import json
from uuid import uuid4

import pytest
from test_cast_service import change as cast_change
from test_enforcer_requisitions import approved
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger_fixture
from test_m2_game import answer, pass_tags, state, tick
from test_mission_ui import current as original_current
from test_red_queen import am, initialize, ready

from girlframe.delivery.p1_source_pause_worker import SourcePauseWorker
from girlframe.discord_adapter.m3_npc_flirt import open_choice
from girlframe.discord_adapter.m3_red_queen_support import open_mark_child
from girlframe.engine import m3_npc_flirt as rules
from girlframe.engine import m3_red_queen as court
from girlframe.engine.m2 import PlayInput
from girlframe.engine.m3_actor_bonds import current_ref, depth
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_world_state import Npc
from girlframe.services.m3_actors import ActorService
from girlframe.services.m3_battle_npc import NpcDamageService
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_npc_flirt import (
    NpcFlirtService,
    prove,
    prove_escape_damage,
    prove_escape_performance,
    prove_judgment,
)
from girlframe.services.m3_world import WorldService
from girlframe.services.onboarding import WorkflowError

ledger = ledger_fixture


def current(uid=2):
    value = original_current(uid, int(uuid4().int % 1000000000))
    value.channel_id = 900
    return value


def native_choice(game, viewer, kind, **values):
    row = next(x for x in game.choices(viewer) if x["kind"] == kind)

    async def run():
        opened = current(viewer.user_id)
        await opened.response.defer(ephemeral=True)
        await open_choice(opened, game, game.decision(viewer, row["id"]))
        form = opened.edit_original_response.call_args.kwargs["view"]
        assert not await form.interaction_check(current(3 if viewer.user_id != 3 else 2))
        form.values.update(values)
        submitted = current(viewer.user_id)
        await form.confirm.callback(submitted)
        assert form.completed, submitted.edit_original_response.call_args_list

    asyncio.run(run())


def finish_roll(game, worker, gateway, action):
    tick(worker, gateway, 3)
    if game.inspect(PLAYER, action)["state"] in ("acquiring", "ready_to_roll"):
        game.roll(PLAYER, str(uuid4()), action)
    pass_tags(game)


def test_actual_high_native_court_npc_flirt_performed_escape_judged_bond_and_true_self_damage(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, controls = ready(ledger, tmp_path, monkeypatch, inside=False)
    approved(
        ledger,
        game,
        tmp_path,
        monkeypatch,
        extra=(
            court.COURT,
            court.TRANSFER,
            court.CONSULT,
            *court.REQUISITIONS,
            rules.RULE,
            "core.core.npcs",
            "core.core.npc-assets",
            "core.core.npc-tags",
            "npc.npc.public-relations",
        ),
    )
    approval = ledger.policy.m3_approval
    ledger.policy = ledger.policy.model_copy(
        update={
            "m3_approval": approval.model_copy(
                update={"subsystems": approval.subsystems | {"world"}}
            )
        }
    )
    mission = MissionService(ledger)
    npc = ActorRef(kind="npc", entity="actual-flirt-counterpart")
    WorldService(mission).npc(
        ADMIN,
        str(uuid4()),
        state(game).revision,
        Npc(
            id=npc.entity,
            name="Pat",
            jobs=("public_relations",),
            controller=1,
            detail="PRIVATE_NPC_DETAIL kept out of the Play metadata",
            revealed=True,
            cell=(0, 0),
        ),
    )
    cast_change(CastService(ActorService(mission)), ADMIN, "join", npc)
    initialize(controls)
    mark_id = controls.mark(
        PLAYER,
        str(uuid4()),
        900,
        state(game).revision,
        am(game, "The Consort").id,
        "flirt",
        counterpart=npc,
    )["id"]
    asyncio.run(SourcePauseWorker(game).tick(gateway))

    async def prepare_native():
        opened = current()
        await opened.response.defer(ephemeral=True)
        await open_mark_child(opened, game, mark_id)
        form = opened.edit_original_response.call_args.kwargs["view"]
        form.values.update(
            play=("flirt",),
            target=("npc:" + npc.entity,),
            heat=("1",),
            identity=(),
            gain=("0",),
            pair_share=("0",),
            piloting=("no",),
            witnessed=("no",),
            context="My actual Consort-required Flirt with this original NPC",
            trigger=("yes",),
        )
        submitted = current()
        await form.confirm.callback(submitted)
        assert form.completed, submitted.edit_original_response.call_args_list

    before = state(game)
    asyncio.run(prepare_native())
    with ledger.engine.connect() as c:
        first = game.lock(c, 900)["action_id"]
        actual = game.action(c, first)
        assert actual["actor_id"] == "2" and actual["data"]["prepared"]["source_work"] == mark_id
        assert actual["data"]["prepared"]["target"] is None
        assert actual["data"]["prepared"]["target_actor"] == npc.model_dump(mode="json")
        assert "PRIVATE_NPC_DETAIL" not in json.dumps(actual["data"]["npc_flirt"])
    game.dice.faces = (5, 5)
    finish_roll(game, worker, gateway, first)
    native_choice(
        game,
        PLAYER,
        "npc_flirt_actor",
        question=("name",),
        extra=("escape",),
        text="PRIVATE_FLIRT: I press my actual question too far",
    )
    row = next(x for x in game.choices(ADMIN) if x["kind"] == "npc_flirt_target")
    assert game.decision(ADMIN, row["id"])["npc_flirt"]["identities"] == []
    native_choice(game, ADMIN, "npc_flirt_target", text="Call me Agent Seven")
    native_choice(game, ADMIN, "npc_flirt_escape", escape=("play",))
    native_choice(
        game,
        ADMIN,
        "npc_flirt_play",
        job=("public_relations",),
        text="Pat actually smooths things over, addressing this Girl and defusing the moment",
    )
    after = state(game)
    performer = current_ref(after, 2)
    assert "1" not in after.sheets and after.sheets["2"].heat == before.sheets["2"].heat - 1
    assert game.inspect(PLAYER, first)["state"] == "complete"
    assert court.get(after, court.Mark, mark_id).completed_event
    mark_completed = court.get(after, court.Mark, mark_id).completed_event
    service = NpcFlirtService(game)
    with ledger.engine.connect() as c:
        prove(game, c, after, first)
        performance = next(x for x in rules.records(after, rules.Performance) if x.action == first)
        assert prove_escape_performance(game, c, after, performance.id) == performance
        assert performance.actor == npc and performance.controller == 1
        assert performance.recipients[0].actor == performer
        receipt = game.action(c, first)["data"]["receipt"]
    with pytest.raises(WorkflowError):
        service.view(OTHER, first)
    tick(worker, gateway, 6)
    asyncio.run(SourcePauseWorker(game).tick(gateway))
    assert {k[0] + k[1]: v for k, v in gateway.values.items()} == gateway.original

    # Actual nickname performance, followed by its actual recipient's judgment.
    initial_depth = depth(state(game), performer, npc)
    done = service.record_followthrough(
        PLAYER,
        str(uuid4()),
        first,
        state(game).revision,
        900,
        "I actually address Pat as Agent Seven, exactly as she requested",
    )["id"]
    assert depth(state(game), performer, npc) == initial_depth
    key, revision = str(uuid4()), state(game).revision
    reply = service.confirm_followthrough(
        ADMIN,
        key,
        done,
        revision,
        True,
        "She actually called me Agent Seven and fulfilled my request",
    )
    assert (
        service.confirm_followthrough(
            ADMIN,
            key,
            done,
            revision,
            True,
            "She actually called me Agent Seven and fulfilled my request",
        )
        == reply
    )
    assert depth(state(game), performer, npc) == min(2, initial_depth + 1)
    with ledger.engine.connect() as c:
        prove_judgment(game, c, state(game), reply["id"])
        assert game.action(c, first)["data"]["receipt"] == receipt
    assert game.dice.calls == 1

    # Distinct new self-cost continuation: real NPC consequence, never phantom Asset damage.
    second = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play="flirt",
            target_actor=npc,
            heat=0,
            context="A new actual Flirt presses the original NPC too far",
            trigger_confirmed=True,
        ),
    )["action_id"]
    game.dice.faces = (6, 6)
    finish_roll(game, worker, gateway, second)
    answer(
        game,
        PLAYER,
        "npc_flirt_actor",
        options=("name",),
        fields={"extra": "escape"},
        text="My actual second overreach",
    )
    answer(game, ADMIN, "npc_flirt_target", text="Respect my actual answer")
    answer(game, ADMIN, "npc_flirt_escape", options=("damage",))
    damaged = state(game)
    source_damage = next(x for x in rules.records(damaged, rules.Damage) if x.action == second)
    assert source_damage.work and game.inspect(PLAYER, second)["state"] != "complete"
    with ledger.engine.connect() as c:
        assert prove_escape_damage(game, c, damaged, second, source_damage.event) == source_damage
    consequence = NpcDamageService(ledger)
    actual_work = consequence.get(ADMIN, source_damage.work[0])
    consequence.respond(
        ADMIN,
        str(uuid4()),
        source_damage.work[0],
        actual_work["revision"],
        "injure_tag",
        "Pat actually injures herself wrenching away from the pressure",
        tag="Broken and bleeding",
    )
    final = state(game)
    actual_npc = next(x for x in final.world.npcs if x.id == npc.entity)
    assert actual_npc.alive and any(x.label == "Broken and bleeding" for x in actual_npc.tags)
    assert (
        ActorRef.model_validate_json(
            next(x for x in actual_npc.tags if x.label == "Broken and bleeding").giver_entity
        )
        == npc
    )
    assert "1" not in final.sheets and game.inspect(PLAYER, second)["state"] == "complete"
    with ledger.engine.connect() as c:
        assert prove(game, c, final, second).completed_event
        assert game.action(c, first)["data"]["receipt"] == receipt
    assert court.get(final, court.Mark, mark_id).completed_event == mark_completed
    assert game.dice.calls == 2


# One focused likely-flow smoke was run after integration; broader branches remain deferred.
def test_actual_princess_directed_mid_native_npc_flirt_keeps_people_resources_and_authors(
    ledger, tmp_path, monkeypatch
):
    import sqlalchemy as sa
    from test_m2_game import Dice
    from test_princess_sex import (
        _directed_native,
        _pass_directed_tags,
        _prepare_directed_native,
        roll,
        setup,
    )

    from girlframe.database import tables as t
    from girlframe.engine import m3_princess_sex as princess

    game, worker, gateway, source = setup(ledger, tmp_path, monkeypatch)
    approved(
        ledger,
        game,
        tmp_path,
        monkeypatch,
        extra=(
            princess.RULE,
            rules.RULE,
            "core.core.npcs",
            "core.core.npc-assets",
            "core.core.npc-tags",
            "npc.npc.public-relations",
        ),
    )
    approval = ledger.policy.m3_approval
    ledger.policy = ledger.policy.model_copy(
        update={
            "m3_approval": approval.model_copy(
                update={"subsystems": approval.subsystems | {"world"}}
            )
        }
    )
    # One human controls two genuinely distinct people. Her NPC reply must never
    # become the Princess's decision merely because both row owners have UID3.
    npc = ActorRef(kind="npc", entity="actual-directed-flirt-npc")
    WorldService(MissionService(ledger)).npc(
        ADMIN,
        str(uuid4()),
        state(game).revision,
        Npc(
            id=npc.entity,
            name="Morgan",
            detail="Synthetic original directed NPC; not the controller's Girl",
            jobs=("public_relations",),
            controller=1,
            revealed=True,
            cell=(0, 0),
        ),
    )
    WorldService(MissionService(ledger)).claim_npc(
        OTHER, str(uuid4()), state(game).revision, npc.entity
    )
    cast_change(CastService(ActorService(MissionService(ledger))), OTHER, "join", npc)
    identity, parent = roll(game, worker, gateway, source, (6, 6), native=True)
    pass_tags(game)
    before = state(game)
    performer = current_ref(before, 3)
    original_parent_receipt = game.inspect(PLAYER, parent)["receipt"]
    direction = _directed_native(game, identity, "flirt", target=npc)
    own = before.sheets["3"]
    marked = next(x for x in own.identities if not x.marked and not x.protected and not x.paired)
    heat = own.heat + 3 if own.heat + 3 >= 5 else 3
    game.dice = Dice((2, 3))
    child = _prepare_directed_native(
        game,
        source,
        identity,
        heat=(str(heat),),
        identity=(marked.id,),
        gain=("3",),
    )
    tick(worker, gateway, 3)
    if game.inspect(PLAYER, child)["state"] in ("acquiring", "ready_to_roll"):
        game.roll(PLAYER, str(uuid4()), child)
    _pass_directed_tags(game)
    with ledger.engine.connect() as c:
        action = game.action(c, child)
        assert action["actor_id"] == "3" and action["parent_id"] == parent
        assert action["data"]["prepared"]["target"] is None
        assert action["data"]["prepared"]["target_actor"] == npc.model_dump(mode="json")
        assert action["data"]["result"]["tier"] == "mid"
        assert action["data"]["npc_flirt"]["princess_direction"] == direction.id
        receipt = action["data"]["receipt"]
    after_roll = state(game)
    assert after_roll.sheets["3"].heat == own.heat + 3 - heat
    assert next(x for x in after_roll.sheets["3"].identities if x.id == marked.id).marked
    assert after_roll.sheets["2"].identities == before.sheets["2"].identities
    actor_row = next(x for x in game.choices(PLAYER) if x["kind"] == "npc_flirt_actor")
    assert actor_row["actor_id"] == "3"
    assert not any(x["id"] == actor_row["id"] for x in game.choices(OTHER))
    native_choice(game, PLAYER, "npc_flirt_actor", question=("name",))
    target_row = next(x for x in game.choices(OTHER) if x["kind"] == "npc_flirt_target")
    assert target_row["actor_id"] == "3"
    assert not any(x["id"] == target_row["id"] for x in game.choices(PLAYER))
    native_choice(game, OTHER, "npc_flirt_target", text="PRIVATE_DIRECTED_NPC: Call me Morgan")
    assert game.inspect(PLAYER, child)["state"] == "complete"
    assert game.inspect(PLAYER, parent)["state"] == "complete"
    assert princess.direction(state(game), direction.id).completed_event
    assert game.inspect(PLAYER, parent)["receipt"] == original_parent_receipt
    assert game.dice.calls == 1
    service = NpcFlirtService(game)
    assert service.view(PLAYER, child)["actor_author"] == 2
    assert service.view(OTHER, child)["source"]["actor"] == performer.model_dump(mode="json")
    assert service.view(PLAYER, child)["can_perform"] is False
    with pytest.raises(WorkflowError):
        service.view(ADMIN, child)
    with ledger.engine.connect() as c:
        assert prove(game, c, state(game), child).princess_direction == direction.id
        assert game.action(c, child)["data"]["receipt"] == receipt
        for row, human in ((actor_row, "2"), (target_row, "3")):
            response = (
                c.execute(
                    sa.select(t.m2["m2_responses"]).where(
                        t.m2["m2_responses"].c.campaign_id == ledger.campaign_id,
                        t.m2["m2_responses"].c.choice_id == row["id"],
                    )
                )
                .mappings()
                .one()
            )
            assert response["actor_id"] == human
            assert (
                c.scalar(
                    sa.select(t.events.c.actor_id).where(
                        t.events.c.campaign_id == ledger.campaign_id,
                        t.events.c.id == response["event_id"],
                    )
                )
                == human
            )
    tick(worker, gateway, 8)
    assert "PRIVATE_DIRECTED_NPC" not in json.dumps(gateway.messages)
