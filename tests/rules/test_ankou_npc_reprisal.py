"""Actual Ankou Asset loss and NPC reprisal preserve the committed original Flirt."""

import asyncio
import json
from uuid import uuid4

from test_ankou_feedback import begin_mark, choose, finish_keep, ready
from test_enforcer_requisitions import approved
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Dice, answer, state, tick
from test_mission_ui import current

from girlframe.discord_adapter.m3_ankou_feedback import open_choice
from girlframe.engine import m3_ankou_feedback as rules
from girlframe.engine import m3_disposable_psyche as disposable
from girlframe.engine import m3_dose_up as drugs
from girlframe.engine import m3_npc_flirt as flirt
from girlframe.engine.m2 import PlayInput
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_world_state import Npc
from girlframe.services.m3_actors import ActorService
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_world import WorldService


def test_native_npc_reprisal_real_loss_heat_child_and_single_parent_resume(
    ledger, tmp_path, monkeypatch
):
    missions, game, worker, gateway, _, _ = ready(ledger, tmp_path, monkeypatch)
    approved(
        ledger,
        game,
        tmp_path,
        monkeypatch,
        extra=(
            rules.RULE,
            disposable.RULE,
            drugs.RULE,
            drugs.SELF_RULE,
            flirt.RULE,
            "core.core.npcs",
            "core.core.npc-assets",
            "core.core.npc-tags",
        ),
    )
    unmarked = [x.id for x in state(game).sheets["2"].identities if not x.marked]
    for identity in unmarked[:-1]:
        game.dice = Dice((4, 4))
        action = begin_mark(game, identity)
        tick(worker, gateway, 3)
        finish_keep(game, worker, gateway, action)
    world = WorldService(missions)
    world.npc(
        ADMIN,
        str(uuid4()),
        state(game).revision,
        Npc(
            id="actual-feedback-person",
            name="Actual Feedback Person",
            jobs=("doctor",),
            cell=(0, 0),
            detail="A real separately controlled person present in this scene",
            controller=1,
            revealed=True,
            employment="foundation",
        ),
    )
    target = ActorRef(kind="npc", entity="actual-feedback-person")
    cast = CastService(ActorService(missions))
    view = cast.view(ADMIN, 900)
    cast.change(
        ADMIN, str(uuid4()), 900, view["game_revision"], view["cast_revision"], "join", target
    )
    view = cast.view(OTHER, 900)
    cast.change(
        OTHER,
        str(uuid4()),
        900,
        view["game_revision"],
        view["cast_revision"],
        "withdraw",
        current_ref(state(game), 3),
    )
    game.dice = Dice((2, 2))
    action = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play="flirt",
            target_actor=target,
            identity=unmarked[-1],
            gain=1,
            heat=1,
            context="An actual interaction with this original present NPC",
            trigger_confirmed=True,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    source = next(x for x in rules.sources(state(game)) if x.action == action)
    sheet = state(game).sheets["2"]
    asset = next(x for x in sheet.assets if x.family == "frame" and not x.void)
    heat_before = sheet.heat
    identities_before = [x.model_dump(mode="json") for x in sheet.identities]
    row = next(x for x in game.choices(PLAYER) if x["kind"] == "ankou_feedback_choice")
    assert next(
        x
        for x in game.decision(PLAYER, row["id"])["ankou_feedback"]["people"]
        if x["token"] == target.token
    )["reprisal_supported"]
    chosen = choose(game, "tear", target, asset=asset.id)
    assert chosen
    assert not any(x.id == asset.id for x in state(game).sheets["2"].assets)
    assert state(game).sheets["2"].heat == heat_before + 5
    assert rules.get(state(game), source.id).phase == "child"
    assert game.inspect(PLAYER, action)["receipt"] is None and game.dice.calls == 0
    child_row = next(x for x in game.choices(PLAYER) if x["kind"] == "ankou_feedback_child")
    game.dice = Dice((1, 1))

    async def native_child():
        interaction = current(2, 98601)
        await interaction.response.defer(ephemeral=True)
        await open_choice(interaction, game, child_row["id"])
        form = interaction.edit_original_response.call_args.kwargs["view"]
        form.values.update(context="PRIVATE_NPC_REPRISAL: I demand their actual name")
        await form.confirm.callback(current(2, 98602))
        assert form.completed

    asyncio.run(native_child())
    child = rules.get(state(game), source.id).child
    assert child is not None
    with ledger.engine.connect() as c:
        actual = game.action(c, child)
        assert actual["parent_id"] == action and actual["actor_id"] == "2"
        prepared = actual["data"]["prepared"]
        assert prepared["target"] is None and prepared["target_actor"] == target.model_dump(
            mode="json"
        )
        assert prepared["source_work"] == source.id and prepared["heat"] == heat_before + 5
    tick(worker, gateway, 3)
    for viewer in (PLAYER, ADMIN):
        answer(game, viewer, "tag_window", options=("pass",))
    with ledger.engine.connect() as c:
        assert game.action(c, child)["data"]["result"]["tier"] == "low"
        assert game.action(c, child)["data"]["receipt"]["pre_total"] == 7
    assert state(game).sheets["2"].heat == 0 and game.dice.calls == 1
    answer(game, ADMIN, "npc_flirt_target", text="PRIVATE_REPRISAL_NAME: the actual answer")
    assert game.inspect(PLAYER, child)["state"] == "complete"
    tick(worker, gateway, 3)
    assert game.dice.calls == 2
    for viewer in (PLAYER, ADMIN):
        answer(game, viewer, "tag_window", options=("pass",))
    answer(game, ADMIN, "npc_flirt_target", text="The original NPC source's actual answer")
    assert game.inspect(PLAYER, action)["state"] == "complete"
    assert state(game).sheets["2"].heat == 0
    assert [
        x.model_dump(mode="json") for x in state(game).sheets["2"].identities
    ] == identities_before
    value = rules.get(state(game), source.id)
    assert value.lost_asset == asset.id and value.child == child and value.rolled_event
    receipt = game.inspect(PLAYER, action)["receipt"]
    assert game.roll(PLAYER, str(uuid4()), action)["receipt"] == receipt
    assert game.dice.calls == 2
    tick(worker, gateway, 3)
    assert not any(
        secret in json.dumps(gateway.messages)
        for secret in ("PRIVATE_NPC_REPRISAL", "PRIVATE_REPRISAL_NAME")
    )
