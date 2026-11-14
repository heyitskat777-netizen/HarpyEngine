"""Owned actual participation in original Handler use, never a retrospective exemption."""

import asyncio
import json
from uuid import uuid4

import pytest
import sqlalchemy as sa
from test_cast_service import change as cast_change
from test_easy_target import choose, ready
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import answer, pass_tags, state, tick
from test_mission_ui import current

from girlframe.database import tables as t
from girlframe.discord_adapter.m3_easy_target import open_choice
from girlframe.engine import m3_easy_target as rules
from girlframe.engine.m2 import ChoiceAnswer, PlayInput
from girlframe.engine.m3_actor_bonds import current_ref, depth
from girlframe.services.inbox import InboxService
from girlframe.services.m2_game import GameService
from girlframe.services.m3_actors import ActorService
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_easy_target import EasyTargetService, prove_use_cohort
from girlframe.services.m3_easy_target_handler_use import prove as prove_handler_use
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_movement import MovementService
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer


def actual_source(ledger, tmp_path, monkeypatch):
    game, worker, gateway, _ = ready(ledger, tmp_path, monkeypatch)
    handler = current_ref(state(game), ADMIN.user_id)
    helper = current_ref(state(game), OTHER.user_id)
    cast_change(CastService(ActorService(MissionService(ledger))), ADMIN, "join", handler)
    with ledger.transaction() as c:
        before = state(game)
        before.facts.append(
            dict(
                kind="recorded_handler_recovery_position",
                actor=handler.model_dump_json(),
                cell=json.dumps([-1, 0]),
            )
        )
        game.event(c, 1, str(uuid4()), "synthetic.original_handler_prior_position", before)
    MovementService(game).move(
        ADMIN,
        str(uuid4()),
        state(game).revision,
        900,
        handler,
        (0, 0),
        account="The actual Handler walks to the two present Girls",
    )
    initial = state(game)
    game.dice.faces = (5, 5)
    identity = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        initial.sheets["2"].revision,
        PlayInput(
            play=rules.PLAY,
            heat=1,
            trigger_confirmed=True,
            context="PRIVATE_HANDLER_COHORT I muddle the actual filing system",
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    answer(game, PLAYER, "easy_target_select", options=(handler.token,), text="The real Handler")
    answer(game, ADMIN, "easy_target_tag", text="PRIVATE_HANDLER_COHORT clumsy assistant")
    return game, worker, gateway, identity, handler, helper, initial


def row(game, viewer, actor, kind="easy_target_child"):
    return next(x for x in game.choices(viewer) if x["kind"] == kind + ":" + actor.token)


def submit(game, viewer, choice, values):
    async def run():
        interaction = current(viewer.user_id, uuid4().int % 1000000000)
        interaction.channel_id = 900
        await interaction.response.defer(ephemeral=True)
        await open_choice(interaction, GameService(game.store, dice=game.dice), choice["id"])
        form = interaction.edit_original_response.call_args.kwargs["view"]
        assert not await form.interaction_check(current(PLAYER.user_id))
        form.values.update(values)
        submitted = current(viewer.user_id, uuid4().int % 1000000000)
        submitted.channel_id = 900
        await form.confirm.callback(submitted)
        assert form.completed
        committed = state(game)
        await form.confirm.callback(submitted)
        assert state(game) == committed

    asyncio.run(run())


@pytest.mark.parametrize("outcome", ["participate", "decline", "missed"])
def test_native_handler_use_keeps_actual_cohort_outcome(ledger, tmp_path, monkeypatch, outcome):
    game, worker, gateway, action, handler, helper, initial = actual_source(
        ledger, tmp_path, monkeypatch
    )
    primary_id, helper_id = (rules.identity(action, actor) for actor in (handler, helper))
    receipt = game.inspect(PLAYER, action)["receipt"]
    assert receipt["faces"] == [5, 5]
    submit(
        game,
        ADMIN,
        row(game, ADMIN, handler, "easy_target_react"),
        dict(
            urge=("use",),
            context="An ordinary non-Play use, holding files while I sort",
            account="PRIVATE_HANDLER_COHORT The original Handler chooses this use",
        ),
    )
    choose(game, OTHER, helper, "cohort", primary=primary_id)
    answer(
        game,
        ADMIN,
        "easy_target_validate:" + handler.token,
        flag=True,
        text="No separate Play, injury, consent, payment or other effect is triggered",
    )
    before = state(game)
    helper_choice = row(game, OTHER, helper)
    assert any(x.identity == helper_choice["id"] for x in InboxService(ledger).items(OTHER))
    assert game.decision(OTHER, helper_choice["id"])["detail"]["use_cohort"]
    with pytest.raises(WorkflowError):
        game.respond(
            ADMIN,
            str(uuid4()),
            helper_choice["id"],
            helper_choice["revision"],
            ChoiceAnswer(options=("participate",), text="I cannot choose her participation"),
        )
    with pytest.raises(WorkflowError):
        game.respond(
            OTHER,
            str(uuid4()),
            helper_choice["id"],
            helper_choice["revision"],
            ChoiceAnswer(
                options=("participate",), text="An invented effect", fields={"damage": "1"}
            ),
        )
    assert state(game) == before
    if outcome != "missed":
        submit(
            game,
            OTHER,
            helper_choice,
            dict(
                outcome=(outcome,),
                account="PRIVATE_HANDLER_COHORT My own actual filing participation decision",
            ),
        )
        pending = state(game)
        participant = rules.records(pending, rules.UseCohort)[-1]
        assert participant.outcome == ("participated" if outcome == "participate" else "declined")
        assert not rules.records(pending, rules.HandlerUse)
        assert not rules.get(pending, rules.Reaction, primary_id).completed_event
        assert game.inspect(PLAYER, action)["state"] != "complete"
    submit(
        game,
        ADMIN,
        row(game, ADMIN, handler),
        dict(account="PRIVATE_HANDLER_COHORT The original Handler now finishes the actual filing"),
    )
    completed_use = state(game)
    original = rules.get(completed_use, rules.Reaction, primary_id)
    use = rules.records(completed_use, rules.HandlerUse)[-1]
    assert (
        use.actor == handler
        and use.controller == ADMIN.user_id
        and use.target == source_actor(initial)
    )
    assert not rules.records(completed_use, rules.NpcUse)
    assert original.performance_event == use.event
    if outcome == "missed":
        assert game.inspect(PLAYER, action)["state"] != "complete"
        with pytest.raises(WorkflowError):
            game.respond(
                OTHER,
                str(uuid4()),
                helper_choice["id"],
                helper_choice["revision"],
                ChoiceAnswer(options=("participate",), text="Too late to gain an exemption"),
            )
        submit(
            game,
            OTHER,
            row(game, OTHER, helper),
            dict(outcome=("missed",), account="I did not join before the actual use finished"),
        )
        assert rules.get(state(game), rules.Reaction, primary_id) == original
    bonds = [x for x in game.choices(PLAYER) if x["kind"].startswith("easy_target_bond")]
    assert bool(bonds) is (outcome != "participate")
    if outcome != "participate":
        assert not original.exemption
        answer(game, PLAYER, bonds[0]["kind"], flag=True, text="My own optional deeper Bond")
    final = state(game)
    follower = rules.get(final, rules.Reaction, helper_id)
    participation = rules.records(final, rules.UseCohort)[-1]
    if outcome == "participate":
        assert original.exemption == helper_id and follower.exemption == primary_id
        assert original.completed_event == follower.completed_event == use.event
        assert original.consequence == follower.consequence == "cohort-exempt"
        assert follower.performance_event == participation.event != use.event
    else:
        assert not follower.exemption and not follower.performance_event
        assert follower.consequence == "use-cohort-" + (
            "declined" if outcome == "decline" else "missed"
        )
        assert participation.use == (use.id if outcome == "missed" else None)
    assert depth(final, source_actor(final), handler) == min(
        2, depth(before, source_actor(before), handler) + int(outcome != "participate")
    )
    assert final.sheets["2"].heat == initial.sheets["2"].heat - 1
    assert "1" not in final.sheets and final.handler_heat == initial.handler_heat
    assert game.inspect(PLAYER, action)["state"] == "complete"
    assert game.roll(PLAYER, str(uuid4()), action)["receipt"] == receipt and game.dice.calls == 1
    with ledger.engine.connect() as c:
        assert prove_handler_use(game, c, final, use.id) == use
        assert prove_use_cohort(game, c, final, participation.id) == participation
        for name in ("m2_actions", "m2_receipts"):
            assert (
                c.scalar(
                    sa.select(sa.func.count())
                    .select_from(t.m2[name])
                    .where(t.m2[name].c.campaign_id == ledger.campaign_id)
                )
                == 1
            )
    assert (
        EasyTargetService(GameService(ledger)).view(OTHER, helper_id)["use_cohort"][0]["id"]
        == participation.id
    )
    with pytest.raises(WorkflowError):
        EasyTargetService(game).view(GuildViewer(4, 200, True, False), helper_id)
    tick(worker, gateway, 6)
    assert "PRIVATE_HANDLER_COHORT" not in json.dumps(gateway.messages)

    # Rebinding the channel must not replace either original historical performance.
    game.close_scene(ADMIN, str(uuid4()), 900)
    game.bind_scene(ADMIN, str(uuid4()), 900)
    for viewer in (PLAYER, OTHER, ADMIN):
        game.join_scene(viewer, str(uuid4()), 900)
    later = state(game)

    def no_live_profiles(*args, **kwargs):
        raise AssertionError("Historical proof must retain original profiles and cast")

    with monkeypatch.context() as history:
        history.setattr("girlframe.services.m3_easy_target.profiles", no_live_profiles)
        history.setattr("girlframe.services.m3_dose_up.profiles", no_live_profiles)
        with ledger.engine.connect() as c:
            assert prove_handler_use(game, c, later, use.id) == use
            assert prove_use_cohort(game, c, later, participation.id) == participation


def source_actor(actual):
    return current_ref(actual, PLAYER.user_id)
