"""Actual final marks/removal, Feedback effects and source-blocked unrolled endings."""

import asyncio
import json
from uuid import uuid4

import pytest
from test_disposable_psyche import ready as disposable_ready
from test_disposable_psyche import real_period
from test_enforcer_requisitions import approved
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Dice, answer, pass_tags, state, tick
from test_mission_ui import current
from test_off_duty_cycle import call, finish_routine, movement, roll_for

from girlframe.discord_adapter.inbox import InboxView
from girlframe.engine import m3_ankou_feedback as rules
from girlframe.engine import m3_disposable_psyche as disposable
from girlframe.engine import m3_dose_up as drugs
from girlframe.engine.m2 import ChoiceAnswer, PlayInput
from girlframe.engine.m3_actor_bonds import current_ref, depth, is_helpless
from girlframe.engine.m3_off_duty import RecoveryChoice
from girlframe.services.inbox import InboxService
from girlframe.services.m3_ankou_feedback import FeedbackService, prove
from girlframe.services.m3_disposable_psyche import prove_disposal
from girlframe.services.m3_recovery import RecoveryService
from girlframe.services.onboarding import WorkflowError


def ready(store, tmp_path, monkeypatch):
    import test_disposable_psyche

    original = test_disposable_psyche.service
    monkeypatch.setattr(
        test_disposable_psyche,
        "service",
        lambda *a, **kw: original(*a, **(kw | {"frame": "PROJECT ANKOU"})),
    )
    missions, game, worker, gateway, controls = disposable_ready(store, tmp_path, monkeypatch)
    approved(
        store,
        game,
        tmp_path,
        monkeypatch,
        extra=(rules.RULE, disposable.RULE, drugs.RULE, drugs.SELF_RULE),
    )
    return missions, game, worker, gateway, controls, FeedbackService(game)


def begin_mark(game, identity, *, extra=0):
    return game.begin(
        PLAYER,
        str(uuid4()),
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play="keep_your_head",
            context="Actual danger and reliance on this Identity",
            trigger_confirmed=True,
            identity=identity,
            gain=1,
            heat=1 + extra,
            disposable_heat=extra,
        ),
    )["action_id"]


def finish_keep(game, worker, gateway, action, *, label=""):
    pass_tags(game)
    with game.store.engine.connect() as c:
        tier = game.action(c, action)["data"]["result"]["tier"]
    if tier == "high":
        answer(game, PLAYER, "actor_keep", text=label or "PRIVATE_FEEDBACK_TAG")
    elif tier == "mid":
        answer(game, PLAYER, "actor_keep", options=("tough", "in_control"), denied=("desperate",))
    else:
        answer(game, PLAYER, "actor_keep", options=("tough",))
    answer(game, ADMIN, "handler_keep", flag=True, text="Actual sufficient source result")
    assert game.inspect(PLAYER, action)["state"] == "complete"
    tick(worker, gateway, 5)


def last_source(game, worker, gateway, *, extra=0, interrupt=False):
    unmarked = [x.id for x in state(game).sheets["2"].identities if not x.marked]
    for identity in unmarked[:-1]:
        game.dice = Dice((4, 4))
        action = begin_mark(game, identity)
        tick(worker, gateway, 3)
        finish_keep(game, worker, gateway, action)
    game.dice = Dice((2, 2))
    action = begin_mark(game, unmarked[-1], extra=extra)
    if interrupt:
        before = state(game).model_dump_json()
        original = game.event

        def interrupted(*args, **kwargs):
            result = original(*args, **kwargs)
            if args[3] == "m3.ankou_feedback_committed":
                raise WorkflowError("Injected interruption after canonical source staging")
            return result

        game.event = interrupted
        try:
            tick(worker, gateway)
        finally:
            game.event = original
        assert state(game).model_dump_json() == before and game.dice.calls == 0
        assert not any(x.action == action for x in rules.sources(state(game)))
        with pytest.raises(WorkflowError):
            game.roll(OTHER, str(uuid4()), action)
        key = "m2.confirmed_roll:" + action
        held = game.roll(PLAYER, key, action)
        assert game.roll(PLAYER, key, action) == held and held["receipt"] is None
    tick(worker, gateway, 3)
    assert game.dice.calls == 0
    value = next(x for x in rules.sources(state(game)) if x.action == action)
    assert value.phase == "choice" and game.inspect(PLAYER, action)["receipt"] is None
    return action, value


def choose(game, effect, target=None, **fields):
    if target:
        fields["target"] = target.token
    return answer(
        game,
        PLAYER,
        "ankou_feedback_choice",
        options=(effect,),
        fields=fields,
        text="PRIVATE_FEEDBACK actual " + effect,
    )


def test_actual_disposal_purpose_bond_rebuild_frame_tear_and_real_reprisal(
    ledger, tmp_path, monkeypatch
):
    missions, game, worker, gateway, controls, service = ready(ledger, tmp_path, monkeypatch)
    actor, target = current_ref(state(game), 2), current_ref(state(game), 3)
    action, value = last_source(game, worker, gateway, extra=3, interrupt=True)
    assert not any(x.id == value.identity.id for x in state(game).sheets["2"].identities)
    assert state(game).sheets["2"].heat == 0
    with ledger.engine.connect() as c:
        removed = prove_disposal(game, c, state(game), action)
        assert removed.receipt is None and removed.commit_event == value.mark_event
        assert prove(game, c, state(game), value.id) == value
    # Staff restores chat, while this real committed requirement cannot be discarded.
    original_row = next(x for x in game.choices(PLAYER) if x["kind"] == "ankou_feedback_choice")
    marked_state = state(game).model_dump_json()
    game.abort(ADMIN, str(uuid4()), action)
    tick(worker, gateway, 5)
    recovery = RecoveryService(game)
    saved = next(x for x in recovery.saved(PLAYER) if x["id"] == action)
    assert not saved["rolled"] and not saved["cancellable"]
    with pytest.raises(WorkflowError):
        recovery.recover(PLAYER, str(uuid4()), action, saved["revision"], cancel=True)
    restored = recovery.recover(PLAYER, "actual-feedback-recovery", action, saved["revision"])
    assert (
        recovery.recover(PLAYER, "actual-feedback-recovery", action, saved["revision"]) == restored
    )
    tick(worker, gateway, 3)
    assert state(game).model_dump_json() == marked_state and game.dice.calls == 0
    row = next(x for x in game.choices(PLAYER) if x["kind"] == "ankou_feedback_choice")
    assert row["id"] == original_row["id"]
    with pytest.raises(WorkflowError):
        game.respond(
            OTHER, str(uuid4()), row["id"], row["revision"], ChoiceAnswer(options=("die",))
        )
    choose(game, "purpose", target)
    private = service.view(OTHER, value.id)
    assert not ({"prepared", "identity", "heat_before", "heat_committed"} & set(private))
    row = next(x for x in game.choices(OTHER) if x["kind"] == "ankou_feedback_purpose")
    projection = game.decision(OTHER, row["id"])["ankou_feedback"]
    assert (
        projection["identities"] == [] and projection["assets"] == [] and projection["heat"] is None
    )
    answer(
        game,
        OTHER,
        "ankou_feedback_purpose",
        flag=True,
        text="PRIVATE_PURPOSE protect those who cannot protect themselves",
    )
    answer(game, PLAYER, "ankou_feedback_identity")
    purpose = rules.get(state(game), value.id).new_identity
    assert next(x for x in state(game).sheets["2"].identities if x.id == purpose).marked is False
    tick(worker, gateway, 3)
    assert game.dice.calls == 1
    finish_keep(game, worker, gateway, action)
    with ledger.engine.connect() as c:
        assert (
            prove_disposal(game, c, state(game), action).receipt
            == game.inspect(PLAYER, action)["receipt"]["id"]
        )
    receipt = game.inspect(PLAYER, action)["receipt"]
    assert game.roll(PLAYER, "m2.confirmed_roll:" + action, action)["receipt"] is None
    assert game.roll(PLAYER, str(uuid4()), action)["receipt"] == receipt
    assert game.dice.calls == 1

    # The genuinely new purpose is now the actual last unmarked Identity.
    game.dice = Dice((6, 6))
    bond_action = begin_mark(game, purpose)
    tick(worker, gateway, 3)
    bond_source = next(x for x in rules.sources(state(game)) if x.action == bond_action)
    assert depth(state(game), actor, target) > 0
    choose(game, "bond", target, name="PRIVATE_BOND_ASSET emotional distance")
    assert depth(state(game), actor, target) == 0
    assert any(
        x.id == bond_source.id + ":bond" and x.family == "girl"
        for x in state(game).sheets["2"].assets
    )
    tick(worker, gateway, 3)
    finish_keep(game, worker, gateway, bond_action, label="PRIVATE_OFF_DUTY_FEEDBACK_TAG")

    # A genuine ordinary OffDuty converts the actual Tag into another unmarked Identity.
    cycle, period = real_period(missions, game)
    roll_for(cycle, game, period, PLAYER, (2, 2))
    work = next(x for x in controls.menu(PLAYER)["tasks"] if x["pending"])
    data = controls.view(PLAYER, work["id"])
    tag = next(x for x in data["tags"] if x["label"] == "PRIVATE_OFF_DUTY_FEEDBACK_TAG")
    replaced = next(
        x.id for x in state(game).sheets["2"].identities if x.marked and not x.protected
    )
    controls.convert(
        PLAYER,
        str(uuid4()),
        work["id"],
        state(game).revision,
        (disposable.TagSelection(tag=tag["id"], replace=replaced),),
    )
    converted = disposable.conversions(state(game))[-1].created[0]
    call(cycle, game, PLAYER, period, "scene", None, (), "")
    call(cycle, game, PLAYER, period, "recover", RecoveryChoice())
    roll_for(cycle, game, period, OTHER, (4, 4))
    call(cycle, game, OTHER, period, "scene", None, (), "")
    call(cycle, game, OTHER, period, "recover", RecoveryChoice())
    finish_routine(cycle, game, period)
    assert call(cycle, game, ADMIN, period, "finish", movement(game))["phase"] == "complete"
    game.dice = Dice((1, 2))
    tear_action = begin_mark(game, converted.id)
    tick(worker, gateway, 3)
    source = next(x for x in rules.sources(state(game)) if x.action == tear_action)
    asset = next(x for x in state(game).sheets["2"].assets if x.family == "frame" and not x.void)
    choose(game, "tear", target, asset=asset.id)
    assert not any(x.id == asset.id for x in state(game).sheets["2"].assets)
    assert state(game).sheets["2"].heat == 5 and not is_helpless(state(game), actor)

    async def reprisal():
        inbox = InboxService(ledger)
        item = next(
            x
            for x in inbox.items(PLAYER)
            if x.task == "m3_ankou_feedback" and x.identity == source.id
        )
        first = current(2, 85001)
        first.channel_id = 900
        await first.response.defer(ephemeral=True)
        await InboxView(inbox, 2).route(first, item)
        form = first.edit_original_response.call_args.kwargs["view"]
        form.values.update(context="I demand the actual counterpart's real name")
        await form.confirm.callback(current(2, 85002))
        assert form.completed

    asyncio.run(reprisal())
    child = rules.get(state(game), source.id).child
    tick(worker, gateway, 3)
    pass_tags(game)
    answer(game, PLAYER, "actor_flirt", options=("name",))
    answer(game, OTHER, "target_flirt", text="PRIVATE_TRUE_NAME actual owned answer")
    assert game.inspect(PLAYER, child)["state"] == "complete"
    tick(worker, gateway, 3)
    finish_keep(game, worker, gateway, tear_action)
    assert game.dice.calls == 2  # actual child and original resume; no second mark/Heat debit
    assert rules.get(state(game), source.id).rolled_event
    assert not any(
        x in json.dumps(gateway.messages)
        for x in ("PRIVATE_PURPOSE", "PRIVATE_BOND_ASSET", "PRIVATE_TRUE_NAME")
    )


def test_actual_purpose_refusal_blocks_unrolled_play_then_real_recovery(
    ledger, tmp_path, monkeypatch
):
    _, game, worker, gateway, _, service = ready(ledger, tmp_path, monkeypatch)
    action, value = last_source(game, worker, gateway)
    actor, target = current_ref(state(game), 2), current_ref(state(game), 3)
    choose(game, "purpose", target)
    answer(game, OTHER, "ankou_feedback_purpose", flag=False, text="My actual explicit refusal")
    assert is_helpless(state(game), actor, target) and game.dice.calls == 0
    result = game.inspect(PLAYER, action)
    assert result["state"] == "complete" and result["receipt"] is None
    assert (
        result["result"]["blocked_before_roll"]
        and rules.get(state(game), value.id).phase == "ended"
    )
    tick(worker, gateway, 6)
    with pytest.raises(WorkflowError):
        game.begin(
            PLAYER,
            str(uuid4()),
            900,
            state(game).sheets["2"].revision,
            PlayInput(
                play="keep_your_head",
                heat=0,
                context="Cannot ignore real Helpless",
                trigger_confirmed=True,
            ),
        )
    game.recover_helpless(
        PLAYER,
        str(uuid4()),
        state(game).sheets["2"].revision,
        "I actually take a moment alone after the interrupted scene action",
        None,
    )
    assert not is_helpless(state(game), actor)
    assert service.view(OTHER, value.id)["purpose_given"] is False


def test_actual_feedback_death_archives_original_without_fabricated_roll(
    ledger, tmp_path, monkeypatch
):
    _, game, worker, gateway, _, service = ready(ledger, tmp_path, monkeypatch)
    action, value = last_source(game, worker, gateway, extra=4)
    choose(game, "die")
    assert any(
        x.actor == value.actor and x.source_event == rules.get(state(game), value.id).resolved_event
        for x in state(game).career_archives
    )
    assert game.dice.calls == 0 and game.inspect(PLAYER, action)["receipt"] is None
    assert service.view(PLAYER, value.id)["archive"]
    with ledger.engine.connect() as c:
        assert prove_disposal(game, c, state(game), action).receipt is None
    tick(worker, gateway, 6)
