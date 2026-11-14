"""Actual native Doll with an ordinary NPC observer; no fabricated NPC sheet or reply."""

import asyncio
from uuid import uuid4

import pytest
import sqlalchemy as sa
from test_cast_service import change as cast_change
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import pass_tags, state, tick
from test_mission_ui import current
from test_vatgrown import choose, ready

from girlframe.database import tables as t
from girlframe.engine import m3_vatgrown as rules
from girlframe.engine.m2 import ChoiceAnswer
from girlframe.engine.m3_actor_bonds import current_ref, depth
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_punishments import Details
from girlframe.engine.m3_role_punishment_state import Instruction
from girlframe.engine.m3_world_state import Npc
from girlframe.services.inbox import InboxService
from girlframe.services.m2_game import GameService
from girlframe.services.m3_actors import ActorService
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_role_punishments import RolePunishmentService
from girlframe.services.m3_vatgrown import DollService, prove
from girlframe.services.m3_world import WorldService
from girlframe.services.onboarding import WorkflowError


def npc_ready(store, tmp_path, monkeypatch):
    game, worker, gateway, controls = ready(store, tmp_path, monkeypatch)
    missions = MissionService(store)
    npc = ActorRef(kind="npc", entity="original-doll-observer")
    WorldService(missions).npc(
        ADMIN,
        str(uuid4()),
        state(game).revision,
        Npc(
            id=npc.entity,
            name="Pat",
            jobs=("guard",),
            controller=1,
            detail="PRIVATE_DOLL_NPC_DETAIL",
            revealed=True,
            cell=(0, 0),
        ),
    )
    cast_change(CastService(ActorService(missions)), ADMIN, "join", npc)
    assert any(
        x["ref"] == npc.model_dump(mode="json") for x in controls.menu(PLAYER, 900)["targets"]
    )
    # Observation needs the real scene and location, not invented contact/anatomy.
    return game, worker, gateway, controls, npc


def native_roll(game, worker, gateway, npc, faces):
    from girlframe.discord_adapter.m3_vatgrown import open_vatgrown

    game.dice.faces = faces
    before = state(game)
    with game.store.engine.connect() as c:
        old_actions = set(c.scalars(sa.select(t.m2["m2_actions"].c.id)))

    async def start():
        interaction = current(2, uuid4().int % 1000000000)
        interaction.channel_id = 900
        await interaction.response.defer(ephemeral=True)
        await open_vatgrown(interaction, DollService(game))
        menu = interaction.edit_original_response.call_args.kwargs["view"]
        menu.values["source"] = ("play",)
        opened = current(2, uuid4().int % 1000000000)
        await menu.confirm.callback(opened)
        form = opened.edit_original_response.call_args.kwargs["view"]
        assert npc.token in dict(next(x for x in form.fields if x.key == "target").options)
        form.values.update(
            target=(npc.token,),
            identity=(),
            gain=("0",),
            heat=("1",),
            account="PRIVATE_DOLL_NPC_SOURCE I fade into the background near the actual guard",
        )
        submitted = current(2, uuid4().int % 1000000000)
        await form.confirm.callback(submitted)
        assert form.completed, submitted.edit_original_response.call_args_list
        saved = state(game)
        await form.confirm.callback(submitted)
        assert state(game) == saved

    asyncio.run(start())
    assert state(game).sheets["2"].heat == before.sheets["2"].heat
    with game.store.engine.connect() as c:
        new = set(c.scalars(sa.select(t.m2["m2_actions"].c.id))) - old_actions
        assert len(new) == 1
        action = new.pop()
        assert game.action(c, action)["data"]["vatgrown"]["target"] == npc.model_dump(mode="json")
    tick(worker, gateway, 3)
    pass_tags(game)
    assert state(game).sheets["2"].heat == before.sheets["2"].heat - 1
    assert game.dice.calls == 1
    assert state(game).world == before.world
    assert state(game).sheets["3"] == before.sheets["3"]
    return action


def test_native_npc_mid_paid_source_owned_secret_and_private_reopen(ledger, tmp_path, monkeypatch):
    game, worker, gateway, controls, npc = npc_ready(ledger, tmp_path, monkeypatch)
    action = native_roll(game, worker, gateway, npc, (4, 4))
    choose(game, PLAYER, "vat_doll_benefits", ("quiet", "information"), native=True)
    row = next(x for x in game.choices(ADMIN) if x["kind"] == "vat_doll_information")
    assert any(x.identity == row["id"] for x in InboxService(ledger).items(ADMIN))
    assert not any(x["id"] == row["id"] for x in game.choices(OTHER))
    original = state(game)
    with pytest.raises(WorkflowError):
        game.respond(
            OTHER,
            str(uuid4()),
            row["id"],
            row["revision"],
            ChoiceAnswer(text="I cannot author someone else's NPC answer"),
        )
    assert state(game) == original
    assert game.inspect(PLAYER, action)["state"] != "complete"
    choose(
        game,
        ADMIN,
        "vat_doll_information",
        text="PRIVATE_DOLL_NPC_SECRET Pat tells her about the missing key",
        native=True,
    )
    final = state(game)
    source = rules.source(final, action)
    assert source.complete and source.target == npc and source.counterpart == 1
    info = next(x for x in rules.records(final, rules.Information) if x.action == action)
    assert info.giver == npc and info.controller == 1 and info.recipient == current_ref(final, 2)
    assert info.answer.startswith("PRIVATE_DOLL_NPC_SECRET")
    assert controls.view(PLAYER, action)["quiet"]
    assert controls.view(ADMIN, action)["information"]["answer"] == info.answer
    with pytest.raises(WorkflowError):
        controls.view(OTHER, action)
    assert game.inspect(PLAYER, action)["state"] == "complete"
    restarted = DollService(GameService(ledger))
    assert restarted.view(PLAYER, action)["information"]["answer"] == info.answer
    with ledger.engine.connect() as c:
        assert prove(game, c, final, action) == source
        payloads = " ".join(c.scalars(sa.select(t.events.c.payload_json)))
        assert "PRIVATE_DOLL_NPC_SECRET" not in payloads
    tick(worker, gateway, 6)
    assert "PRIVATE_DOLL_NPC_SECRET" not in str(gateway.messages)
    assert "PRIVATE_DOLL_NPC_SOURCE" not in str(gateway.messages)
    assert game.dice.calls == 1


def test_native_npc_high_real_object_and_quiet_benefits(ledger, tmp_path, monkeypatch):
    game, worker, gateway, controls, npc = npc_ready(ledger, tmp_path, monkeypatch)
    action = native_roll(game, worker, gateway, npc, (6, 6))
    choose(game, PLAYER, "vat_doll_benefits", ("quiet",), native=True)
    final = controls.view(PLAYER, action)
    assert final["quiet"] and final["object"]
    assert rules.source(state(game), action).benefits == ("quiet",)
    assert game.inspect(PLAYER, action)["state"] == "complete"
    assert not any(x["kind"] == "vat_doll_attention" for x in game.choices(ADMIN))


def test_native_npc_low_actual_tag_before_owned_benefit(ledger, tmp_path, monkeypatch):
    game, worker, gateway, controls, npc = npc_ready(ledger, tmp_path, monkeypatch)
    action = native_roll(game, worker, gateway, npc, (1, 1))
    assert not any(x["kind"] == "vat_doll_benefits" for x in game.choices(PLAYER))
    row = next(x for x in game.choices(ADMIN) if x["kind"] == "vat_doll_attention")
    args = (
        ADMIN,
        str(uuid4()),
        row["id"],
        row["revision"],
        ChoiceAnswer(options=("tag",), text="Noticed by the actual guard"),
    )
    result = game.respond(*args)
    assert game.respond(*args) == result
    tag = rules.source(state(game), action).tag
    assert tag is not None and tag.giver_actor == npc and tag.giver == 1
    assert sum(x.id == tag.id for x in state(game).sheets["2"].tags) == 1
    choose(game, PLAYER, "vat_doll_benefits", ("quiet",), native=True)
    assert controls.view(PLAYER, action)["quiet"]
    assert game.inspect(PLAYER, action)["state"] == "complete" and game.dice.calls == 1


def test_native_npc_low_real_social_punishment_before_benefit(ledger, tmp_path, monkeypatch):
    game, worker, gateway, controls, npc = npc_ready(ledger, tmp_path, monkeypatch)
    action = native_roll(game, worker, gateway, npc, (1, 1))
    choose(game, ADMIN, "vat_doll_attention", ("punish",), native=True)
    before = state(game)
    case = before.role_punishments[-1]
    assert case.source_kind == "vatgrown_doll" and case.executor == npc and case.chooser == npc
    assert case.subject == current_ref(before, 2)
    assert case.executor_controller == 1 and case.chooser_controller == 1
    assert case.pc_work is None
    assert not any(x["kind"] == "vat_doll_benefits" for x in game.choices(PLAYER))
    role = RolePunishmentService(game)

    def change(viewer, **values):
        return role.change(
            viewer, str(uuid4()), case.id, role.get(viewer, case.id)["revision"], **values
        )

    details = Details(kind="quality_time", tag="The guard's actual chosen Tag")
    change(
        ADMIN, instruction=Instruction(kind=details.kind, details_json=details.model_dump_json())
    )
    change(ADMIN, approve=True)
    change(ADMIN, scene="The actual guard administers the chosen social discipline")
    change(PLAYER, attest=True)
    change(ADMIN, execute=True, account="Pat completes the actual source-owned scene")
    final = state(game)
    done = next(x for x in final.role_punishments if x.id == case.id)
    assert done.effect_event and done.completion_event
    assert (
        depth(final, current_ref(final, 2), npc) == depth(before, current_ref(before, 2), npc) + 1
    )
    tag = next(x for x in final.sheets["2"].tags if x.label == details.tag)
    assert tag.giver_actor == npc
    assert game.inspect(PLAYER, action)["state"] != "complete"
    choose(game, PLAYER, "vat_doll_benefits", ("quiet",), native=True)
    assert controls.view(PLAYER, action)["quiet"]
    assert game.inspect(PLAYER, action)["state"] == "complete"
    tick(worker, gateway, 6)
    with ledger.engine.connect() as c:
        assert game.lock(c, 900)["state"] == "released"
    assert game.dice.calls == 1
