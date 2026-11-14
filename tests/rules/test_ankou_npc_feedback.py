"""Printed 'anyone else': a real NPC's owned purpose, before the original roll."""

import asyncio
import json
from uuid import uuid4

import pytest
from test_ankou_feedback import begin_mark, finish_keep, ready
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
from girlframe.engine.m3_actor_bonds import current_ref, is_helpless
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_world_state import Npc
from girlframe.services.m3_actors import ActorService
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_world import WorldService
from girlframe.services.onboarding import WorkflowError


@pytest.mark.parametrize("given", [True, False])
def test_native_npc_only_feedback_purpose_owned_response_and_original_outcome(
    ledger, tmp_path, monkeypatch, given
):
    missions, game, worker, gateway, _, feedback = ready(ledger, tmp_path, monkeypatch)
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
    assert not any(x.actor.kind == "pilot" and x.actor != source.actor for x in source.cast.roles)
    assert game.dice.calls == 0 and game.inspect(PLAYER, action)["receipt"] is None
    row = next(x for x in game.choices(PLAYER) if x["kind"] == "ankou_feedback_choice")
    detail = game.decision(PLAYER, row["id"])["ankou_feedback"]
    person = next(x for x in detail["people"] if x["token"] == target.token)
    assert person["reprisal_supported"] is True

    async def choose_purpose():
        interaction = current(2, 98501)
        await interaction.response.defer(ephemeral=True)
        await open_choice(interaction, game, row["id"])
        form = interaction.edit_original_response.call_args.kwargs["view"]
        assert any(
            token == target.token and "purpose/Bond only" not in label
            for field in form.fields
            if field.key == "target"
            for token, label in field.options
        )
        form.values.update(
            effect=("purpose",),
            target=(target.token,),
            account="PRIVATE_NPC_FEEDBACK: I ask this actual person for a purpose",
        )
        await form.confirm.callback(current(2, 98502))
        assert form.completed

    asyncio.run(choose_purpose())
    response = next(x for x in game.choices(ADMIN) if x["kind"] == "ankou_feedback_purpose")
    private = game.decision(ADMIN, response["id"])["ankou_feedback"]
    assert private["identities"] == private["assets"] == [] and private["heat"] is None
    with pytest.raises(WorkflowError):
        feedback.view(OTHER, source.id)
    assert game.dice.calls == 0
    answer(
        game,
        ADMIN,
        "ankou_feedback_purpose",
        flag=given,
        text="PRIVATE_NPC_PURPOSE: protect the injured" if given else "PRIVATE_NPC_REFUSAL",
    )
    if given:
        sheet = state(game).sheets["2"]
        replace = next(
            x.id
            for x in sheet.identities
            if not x.protected
            and not x.paired
            and not x.am_limiter
            and x.id not in sheet.sedation_locked
        )
        answer(game, PLAYER, "ankou_feedback_identity", fields={"replace": replace})
        value = rules.get(state(game), source.id)
        identity = next(x for x in state(game).sheets["2"].identities if x.id == value.new_identity)
        assert identity.name == "PRIVATE_NPC_PURPOSE: protect the injured" and not identity.marked
        tick(worker, gateway, 3)
        assert game.dice.calls == 1
        # OTHER really withdrew, so only the original two actual controllers
        # own this NPC Flirt's tag windows.
        for viewer in (PLAYER, ADMIN):
            answer(game, viewer, "tag_window", options=("pass",))
        with ledger.engine.connect() as c:
            assert game.action(c, action)["data"]["result"]["tier"] == "low"
        answer(game, ADMIN, "npc_flirt_target", text="An actual answer with no return question")
        assert game.inspect(PLAYER, action)["state"] == "complete"
        tick(worker, gateway, 3)
        receipt = game.inspect(PLAYER, action)["receipt"]
        assert game.roll(PLAYER, str(uuid4()), action)["receipt"] == receipt
        assert game.dice.calls == 1
    else:
        assert is_helpless(state(game), source.actor, target)
        assert game.dice.calls == 0
        result = game.inspect(PLAYER, action)
        assert result["state"] == "complete" and result["receipt"] is None
        assert result["result"]["blocked_before_roll"]
        assert rules.get(state(game), source.id).phase == "ended"
        tick(worker, gateway, 3)
    assert not any(
        secret in json.dumps(gateway.messages)
        for secret in ("PRIVATE_NPC_FEEDBACK", "PRIVATE_NPC_PURPOSE", "PRIVATE_NPC_REFUSAL")
    )
