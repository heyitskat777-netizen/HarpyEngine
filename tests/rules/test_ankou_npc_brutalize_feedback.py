"""A real Guard keeps its controller, assessment and injury/death through Alpha Feedback."""

import asyncio
import copy
import json
from uuid import uuid4

import pytest
import sqlalchemy as sa
from test_ankou_alpha_feedback import ready
from test_ankou_feedback import begin_mark, choose, finish_keep
from test_enforcement_initiative import cast_target
from test_enforcer_requisitions import approved
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Dice, answer, pass_tags, state, tick
from test_mission_ui import current

from girlframe.database import tables as t
from girlframe.discord_adapter.m2_ui import open_play
from girlframe.discord_adapter.m3_alpha import open_alpha_choice
from girlframe.engine import m3_alpha as alpha
from girlframe.engine import m3_ankou_feedback as feedback
from girlframe.engine.m2 import ChoiceAnswer
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_world_state import Npc
from girlframe.services.m2_game import GameService
from girlframe.services.m3_alpha import authorize as authorize_alpha
from girlframe.services.m3_ankou_alpha import source_binding
from girlframe.services.m3_ankou_feedback import FeedbackService, prove
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_npc_guard import GuardService
from girlframe.services.m3_recovery import RecoveryService
from girlframe.services.m3_world import WorldService
from girlframe.services.onboarding import WorkflowError


@pytest.mark.parametrize("faces,high", [((3, 3), False), ((6, 6), True)], ids=("mid", "high"))
def test_native_guard_feedback_retains_controller_and_real_brutalize_result(
    ledger, tmp_path, monkeypatch, faces, high
):
    game, worker, gateway = ready(ledger, tmp_path, monkeypatch)
    approved(
        ledger, game, tmp_path, monkeypatch, extra=(feedback.RULE, alpha.RULE, "npc.npc.guard")
    )
    game.store.policy = game.store.policy.model_copy(
        update={
            "m3_approval": game.store.policy.m3_approval.model_copy(
                update={"subsystems": game.store.policy.m3_approval.subsystems | {"world"}}
            )
        }
    )
    identities = [x.id for x in state(game).sheets["2"].identities if not x.marked]
    for identity in identities[:-1]:
        game.dice = Dice((4, 4))
        prior = begin_mark(game, identity)
        tick(worker, gateway, 3)
        finish_keep(game, worker, gateway, prior)
    WorldService(MissionService(ledger)).npc(
        ADMIN,
        str(uuid4()),
        state(game).revision,
        Npc(
            id="actual-feedback-guard",
            name="Actual Feedback Guard",
            jobs=("guard",),
            detail="An actual ordinary Guard present with the original Alpha",
            controller=ADMIN.user_id,
            cell=(0, 0),
            revealed=True,
        ),
    )
    npc = ActorRef(kind="npc", entity="actual-feedback-guard")
    cast_target(game, npc)
    assessment = GuardService(game).assess(
        ADMIN,
        str(uuid4()),
        900,
        npc,
        current_ref(state(game), PLAYER.user_id),
        state(game).revision,
        True,
        "This actual Guard has no weapon on their body",
    )["id"]

    async def native_brutalize():
        first = current(PLAYER.user_id, 99881)
        first.channel_id = 900
        await first.response.defer(ephemeral=True)
        await open_play(first, game, _pilot=True)
        form = first.edit_original_response.call_args.kwargs["view"]
        form.values.update(
            play=("brutalize",),
            alpha_target=(npc.token,),
            identity=(identities[-1],),
            gain=("3",),
            pair_share=("0",),
            heat=("2",),
            disposable_heat=("0",),
            piloting=("no",),
            witnessed=("no",),
            trigger=("yes",),
            context="PRIVATE_NPC_BRUTALIZE: I tear into this actual Guard",
        )
        response = current(PLAYER.user_id, 99882)
        await form.confirm.callback(response)
        assert form.completed, response.edit_original_response.call_args_list
        with ledger.engine.connect() as c:
            return json.loads(
                c.scalar(
                    sa.select(t.commands.c.outcome_json).where(
                        t.commands.c.campaign_id == ledger.campaign_id,
                        t.commands.c.interaction_key == str(response.id),
                    )
                )
            )["action_id"]

    game.dice = Dice(faces)
    before = state(game)
    action = asyncio.run(native_brutalize())
    tick(worker, gateway, 3)
    if not any(x.action == action for x in feedback.sources(state(game))):
        game.roll(PLAYER, "m2.confirmed_roll:" + action, action)
    value = next(x for x in feedback.sources(state(game)) if x.action == action)
    assert value.alpha_source is not None and value.phase == "choice"
    assert value.heat_before == before.sheets["2"].heat
    assert value.heat_committed == state(game).sheets["2"].heat == value.heat_before + 1
    assert next(x for x in state(game).sheets["2"].identities if x.id == identities[-1]).marked
    assert state(game).world == before.world and set(state(game).sheets) == set(before.sheets)
    assert game.dice.calls == 0 and game.inspect(PLAYER, action)["receipt"] is None
    with ledger.engine.connect() as c:
        saved = game.action(c, action)
        assert saved["data"]["alpha"]["npc_assessment"] == assessment
        assert saved["data"]["alpha"]["target_controller"] == ADMIN.user_id
        assert source_binding(game, c, state(game), saved) == value.alpha_source
        assert prove(game, c, state(game), value.id) == value
        replaced = copy.deepcopy(saved)
        replaced["data"]["alpha"]["npc_assessment"] = "not-the-original-review"
        with pytest.raises(WorkflowError, match="weapon facts"):
            source_binding(game, c, state(game), replaced)
        wrong_controller = copy.deepcopy(saved)
        wrong_controller["data"]["alpha"]["target_controller"] = OTHER.user_id
        with pytest.raises(WorkflowError, match="bodies and controllers"):
            source_binding(game, c, state(game), wrong_controller)
    committed = state(game).sheets["2"].model_copy(deep=True)
    game.abort(ADMIN, str(uuid4()), action)
    tick(worker, gateway, 5)
    recovery = RecoveryService(game)
    saved = next(x for x in recovery.saved(PLAYER) if x["id"] == action)
    assert not saved["rolled"] and not saved["cancellable"]
    recovery.recover(PLAYER, "recover-npc-brutalize-feedback", action, saved["revision"])
    tick(worker, gateway, 3)
    assert state(game).sheets["2"] == committed and game.dice.calls == 0
    choose(game, "purpose", npc)
    private = FeedbackService(game).view(ADMIN, value.id)
    assert not {"prepared", "identity", "heat_before", "heat_committed"} & set(private)
    row = next(x for x in game.choices(ADMIN) if x["kind"] == "ankou_feedback_purpose")
    with pytest.raises(WorkflowError):
        game.respond(
            OTHER,
            str(uuid4()),
            row["id"],
            row["revision"],
            ChoiceAnswer(flag=True, text="I cannot choose for the actual Guard"),
        )
    answer(
        game,
        ADMIN,
        "ankou_feedback_purpose",
        flag=True,
        text="PRIVATE_NPC_BRUTALIZE_PURPOSE: stand your ground",
    )
    replacement = next(x.id for x in state(game).sheets["2"].identities if not x.protected)
    answer(game, PLAYER, "ankou_feedback_identity", fields={"replace": replacement})
    resumed = state(game).sheets["2"].model_copy(deep=True)
    tick(worker, gateway, 3)
    pass_tags(game)
    receipt = game.inspect(PLAYER, action)["receipt"]
    assert receipt["heat"] == 2 and game.dice.calls == 1
    assert state(game).sheets["2"].heat == resumed.heat
    assert state(game).sheets["2"].identities == resumed.identities
    row = next(x for x in game.choices(PLAYER) if x["kind"] == "alpha_npc_damage")
    with pytest.raises(WorkflowError):
        game.respond(
            ADMIN,
            str(uuid4()),
            row["id"],
            row["revision"],
            ChoiceAnswer(
                options=("kill" if high else "injure",), text="" if high else "Wrong owner"
            ),
        )

    async def native_damage():
        first = current(PLAYER.user_id, 99883)
        await first.response.defer(ephemeral=True)
        await open_alpha_choice(first, game, row["id"])
        form = first.edit_original_response.call_args.kwargs["view"]
        if high:
            assert [(field.key, field.options) for field in form.fields] == [
                ("effect", (("kill", "Apply this rolled NPC death"),))
            ]
            form.values["effect"] = ("kill",)
        else:
            form.values["injury"] = "An actual bruised shoulder"
        response = current(PLAYER.user_id, 99884)
        await form.confirm.callback(response)
        assert form.completed, response.edit_original_response.call_args_list

    asyncio.run(native_damage())
    actual = state(game)
    person = next(x for x in actual.world.npcs if x.id == npc.entity)
    assert person.alive == (not high)
    assert set(actual.sheets) == set(before.sheets) and npc.entity not in actual.sheets
    if high:
        assert not any(role.actor == npc for cast in actual.scene_casts for role in cast.roles)
        with ledger.engine.connect() as c:
            saved = game.action(c, action)
            unfinished = copy.deepcopy(saved)
            unfinished["state"] = "awaiting_choices"
            unfinished["data"]["alpha"]["phase"] = "unrolled"
            with pytest.raises(WorkflowError, match="original Brutalize source cast"):
                authorize_alpha(game, c, PLAYER, unfinished)
            substituted = copy.deepcopy(saved)
            substituted["data"]["alpha"]["effect_event"] = "not-the-original-death"
            with pytest.raises(WorkflowError, match="actual saved completed Brutalize"):
                authorize_alpha(game, c, PLAYER, substituted)
    else:
        assert person.tags[-1].label == "An actual bruised shoulder"
        assert alpha.conditions(actual, npc, value.actor)
    assert game.inspect(PLAYER, action)["state"] == "complete"
    restarted = GameService(ledger, dice=game.dice)
    assert restarted.inspect(PLAYER, action) == game.inspect(PLAYER, action)
    assert restarted.roll(PLAYER, str(uuid4()), action)["receipt"] == receipt
    assert game.dice.calls == 1
    with ledger.engine.connect() as c:
        assert prove(restarted, c, state(restarted), value.id).receipt == receipt["id"]
    tick(worker, gateway, 5)
    with ledger.engine.connect() as c:
        assert game.lock(c, 900)["state"] == "released"
    restarted.close_scene(ADMIN, "close-finished-npc-brutalize-feedback", 900)
    restarted.bind_scene(ADMIN, "reuse-finished-npc-brutalize-channel", 900)
    with ledger.engine.connect() as c:
        assert prove(restarted, c, state(restarted), value.id).receipt == receipt["id"]
    if high:
        assert restarted.roll(PLAYER, str(uuid4()), action)["receipt"] == receipt
        assert game.dice.calls == 1
    assert "PRIVATE_NPC_BRUTALIZE" not in json.dumps(gateway.messages)
