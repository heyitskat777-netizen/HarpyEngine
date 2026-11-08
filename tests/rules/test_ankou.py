"""Ankou ordinary workflows; only the named native mid-Processor smoke may run in P1."""

import asyncio
from uuid import uuid4

import pytest
from test_enforcer_requisitions import approved
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger_fixture
from test_m2_game import Gateway, answer, pass_tags, state, tick
from test_mission_service import service
from test_mission_ui import current as native_current
from test_physical_operations import place
from test_world import initial

from girlframe.delivery.m2_worker import GameWorker
from girlframe.discord_adapter.m3_ankou import open_ankou, open_choice
from girlframe.engine import m3_ankou as rules
from girlframe.engine.m2 import PlayInput
from girlframe.engine.m3_actor_bonds import current_ref, depth, is_helpless
from girlframe.services.inbox import InboxService
from girlframe.services.m3_ankou import AnkouService, prove_obsession, prove_source
from girlframe.services.onboarding import WorkflowError

ledger = ledger_fixture


def current(user=2):
    value = native_current(user, int(uuid4().int % 1000000000))
    value.channel_id = 900
    return value


def ready(store, tmp_path, monkeypatch):
    _, game = service(store, girl="OLDGEN", frame=rules.FRAME)
    approved(store, game, tmp_path, monkeypatch, extra=(rules.RELAY, *rules.REQUISITIONS))
    with store.transaction() as c:
        actual = state(game)
        actual.world = initial()
        actual = place(place(actual, 2, mode="piloting"), 3, mode="outside_frame")
        actual.sheets["2"].permissions = 30
        actual.sheets["2"].heat = 4
        game.event(c, 1, str(uuid4()), "synthetic.actual_ankou_original_bodies_resources", actual)
    return game, GameWorker(game), Gateway(), AnkouService(game)


def buy(controls, rule):
    return controls.buy(
        PLAYER,
        str(uuid4()),
        state(controls.game).revision,
        rule,
        "I buy this actual source-priced Ankou Requisition",
    )["id"]


def native(controls, operation, **values):
    async def run():
        initial = current()
        await initial.response.defer(ephemeral=True)
        await open_ankou(initial, controls)
        menu = initial.edit_original_response.call_args.kwargs["view"]
        assert not await menu.interaction_check(current(3))
        menu.values["operation"] = (operation,)
        selected = current()
        await menu.confirm.callback(selected)
        form = selected.edit_original_response.call_args.kwargs["view"]
        form.values.update(values)
        submitted = current()
        await form.confirm.callback(submitted)
        assert form.completed, submitted.edit_original_response.call_args_list

    asyncio.run(run())


def native_result(game, **values):
    async def run():
        request = next(x for x in game.choices(PLAYER) if x["kind"] == "ankou_processor_benefits")
        initial = current()
        await initial.response.defer(ephemeral=True)
        await open_choice(initial, game, game.decision(PLAYER, request["id"]))
        form = initial.edit_original_response.call_args.kwargs["view"]
        form.values.update(values)
        submitted = current()
        await form.confirm.callback(submitted)
        assert form.completed, submitted.edit_original_response.call_args_list

    asyncio.run(run())


def processor(game, worker, gateway, controls, faces=(3, 4)):
    buy(controls, rules.PROCESSOR)
    proposed = controls.propose_processor(
        PLAYER,
        str(uuid4()),
        900,
        state(game).revision,
        "I use the actual living minds in this relay square",
    )
    game.dice.faces = faces
    action = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play=rules.PLAY,
            trigger_confirmed=True,
            heat=1,
            context="Actual living minds become Frame processors",
            source_work=proposed["id"],
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    game.roll(PLAYER, str(uuid4()), action)
    pass_tags(game)
    return action


def test_native_mid_processor_real_resources_private_resume_and_actual_unlink(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, controls = ready(ledger, tmp_path, monkeypatch)
    buy(controls, rules.PROCESSOR)
    before = state(game)
    native(
        controls,
        "processor",
        heat=("1",),
        identity=("none",),
        gain=("1",),
        cadre=("no",),
        exempt=("none",),
        account="The actual original nearby living mind becomes my Frame processor",
    )
    with ledger.engine.connect() as c:
        action = game.lock(c, 900)["action_id"]
    game.dice.faces = (3, 4)
    tick(worker, gateway, 3)
    rolled = game.roll(PLAYER, str(uuid4()), action)
    pass_tags(game)
    native_result(game, benefit0=("champion",), benefit1=("eyes",), replace1=("none",))
    assert game.inspect(PLAYER, action)["state"] == "complete"
    actual = state(game)
    source = rules.get(actual, rules.Processor, action)
    assert source.minds == (current_ref(actual, 3),)
    assert source.total == 8 and source.completed_event and source.assets
    assert actual.sheets["2"].heat == before.sheets["2"].heat - 1
    assert actual.sheets["3"].identities == before.sheets["3"].identities
    assert any(
        x.id in source.assets and x.name == "Eyes Everywhere" for x in actual.sheets["2"].assets
    )
    assert any(
        x.id in source.tags and x.label == "People’s Champion" for x in actual.sheets["2"].tags
    )
    assert controls.view(PLAYER, action)["can_unlink"]
    with pytest.raises(WorkflowError):
        controls.view(OTHER, action)
    own = InboxService(ledger).items(PLAYER)
    assert any(x.task == "m3_ankou" and x.identity == action for x in own)
    with ledger.engine.connect() as c:
        assert prove_source(game, c, actual, action) == source
    original_receipt = rolled["receipt"]
    key = str(uuid4())
    result = controls.unlink(
        PLAYER, key, actual.revision, action, "I actually unlink these processors"
    )
    assert (
        controls.unlink(PLAYER, key, actual.revision, action, "I actually unlink these processors")
        == result
    )
    changed = state(game)
    assert not any(x.id in source.assets for x in changed.sheets["2"].assets)
    assert not any(x.id in source.tags for x in changed.sheets["2"].tags)
    assert changed.sheets["2"].heat == actual.sheets["2"].heat
    assert changed.sheets["2"].identities == actual.sheets["2"].identities
    with ledger.engine.connect() as c:
        assert game.action(c, action)["data"]["receipt"] == original_receipt
    assert controls.view(PLAYER, action)["source"]["unlinked_event"]
    with pytest.raises(WorkflowError, match="STALE"):
        controls.unlink(PLAYER, str(uuid4()), actual.revision, action, "An actual stale duplicate")


@pytest.mark.parametrize(
    "faces,benefits,symptoms",
    [
        ((1, 1), ("champion",), ("Crippling migraines and headaches",)),
        ((5, 5), ("champion", "eyes", "will"), ("Auditory hallucinations", "Vomiting and nausea")),
    ],
)
def test_processor_other_printed_tiers_actual_symptoms_and_original_recipient(
    ledger, tmp_path, monkeypatch, faces, benefits, symptoms
):
    game, worker, gateway, controls = ready(ledger, tmp_path, monkeypatch)
    action = processor(game, worker, gateway, controls, faces)
    answer(game, PLAYER, "ankou_processor_benefits", options=benefits)
    answer(game, PLAYER, "ankou_processor_symptoms", options=symptoms)
    source = rules.get(state(game), rules.Processor, action)
    assert source.symptoms == symptoms
    assert {x.label for x in state(game).sheets["3"].tags} >= set(symptoms)
    assert not {x.label for x in state(game).sheets["2"].tags} & set(symptoms)
    controls.unlink(
        PLAYER, str(uuid4()), state(game).revision, action, "Actually end the original link"
    )
    assert {x.label for x in state(game).sheets["3"].tags} >= set(symptoms)


def test_relay_actual_head_speech_touch_and_same_source_asset_cost(ledger, tmp_path, monkeypatch):
    game, _, _, controls = ready(ledger, tmp_path, monkeypatch)
    own, target = current_ref(state(game), 2), current_ref(state(game), 3)
    source = controls.activate_relay(
        PLAYER,
        str(uuid4()),
        900,
        state(game).revision,
        ("speech", "touch"),
        "I activate my actual Emotional Relay",
    )["id"]
    controls.choose_consequence(
        ADMIN,
        str(uuid4()),
        state(game).revision,
        source,
        "nominees",
        "I choose the genuine Intense-partner nomination consequence",
    )
    delivery = controls.speak(
        PLAYER,
        str(uuid4()),
        state(game).revision,
        source,
        target,
        "I speak these actual authored words directly into your head",
    )["id"]
    assert "actual authored words" in controls.view(OTHER, delivery)["summary"]
    encounter = controls.encounter(
        PLAYER,
        str(uuid4()),
        900,
        state(game).revision,
        own,
        target,
        "touch",
        "I actually touch this original person",
    )["id"]
    asset = next(
        x.id for x in state(game).sheets["2"].assets if x.family == "frame" and not x.damaged
    )
    result = controls.touch(
        PLAYER,
        str(uuid4()),
        state(game).revision,
        source,
        encounter,
        asset,
        "I damage my actual Frame Asset while making this real touch",
    )
    assert result["id"]
    assert next(x for x in state(game).sheets["2"].assets if x.id == asset).damaged
    assert is_helpless(state(game), target, own)


def test_obsession_directional_benefit_real_tag_no_false_reciprocal_bond(
    ledger, tmp_path, monkeypatch
):
    game, _, _, controls = ready(ledger, tmp_path, monkeypatch)
    buy(controls, rules.OBSESSIVE)
    actual = state(game)
    own, target = current_ref(actual, 2), current_ref(actual, 3)
    raw = depth(actual, own, target)
    source = controls.choose_obsession(
        PLAYER,
        str(uuid4()),
        actual.revision,
        target,
        "This actual person becomes my one-sided Obsession",
    )["id"]
    assert rules.effective_intense(state(game), own, target)
    assert depth(state(game), own, target) == raw
    with ledger.engine.connect() as c:
        assert prove_obsession(game, c, state(game), own, target)
    controls.give_source_tag(
        OTHER,
        str(uuid4()),
        state(game).revision,
        source,
        "obsession",
        "Her absence occupies my thoughts",
    )
    with pytest.raises(WorkflowError, match="once-per-scene"):
        controls.give_source_tag(
            OTHER,
            str(uuid4()),
            state(game).revision,
            source,
            "obsession",
            "Another Tag from the same original scene",
        )


def test_actual_interrupt_decline_resumes_original_known_receipt_and_real_keep_effects(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, controls = ready(ledger, tmp_path, monkeypatch)
    relay = controls.activate_relay(
        PLAYER,
        str(uuid4()),
        900,
        state(game).revision,
        ("interrupt", "sense"),
        "My actual relay is active",
    )["id"]
    controls.choose_consequence(
        ADMIN,
        str(uuid4()),
        state(game).revision,
        relay,
        "death",
        "Actual NPC death hearing, not a fabricated death",
    )
    game.dice.faces = (3, 4)
    action = game.begin(
        OTHER,
        str(uuid4()),
        900,
        state(game).sheets["3"].revision,
        PlayInput(
            play="keep_your_head",
            context="My actual danger and response",
            trigger_confirmed=True,
            heat=1,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    original = game.roll(OTHER, str(uuid4()), action)["receipt"]
    pass_tags(game)
    answer(game, PLAYER, "ankou_interrupt", flag=False, text="I do not erase a Tag or interrupt")
    answer(game, OTHER, "actor_keep", options=("tough", "in_control"), denied=("desperate",))
    answer(
        game, ADMIN, "handler_keep", flag=True, text="The actual original performance is sufficient"
    )
    assert game.inspect(OTHER, action)["state"] == "complete"
    with ledger.engine.connect() as c:
        assert game.action(c, action)["data"]["receipt"] == original


def feedback_source(game, controls, gateway):
    from girlframe.delivery.p1_source_pause_worker import SourcePauseWorker
    from girlframe.services import m3_ankou_feedback_sequences as sequences

    relay = controls.activate_relay(
        PLAYER,
        str(uuid4()),
        900,
        state(game).revision,
        ("speech", "sense"),
        "I activate the actual relay source",
    )["id"]
    controls.choose_consequence(
        ADMIN,
        str(uuid4()),
        state(game).revision,
        relay,
        "feedback",
        "I choose the printed actual Feedback consequence",
    )
    source = rules.records(state(game), rules.FeedbackSequence)[-1]
    assert source.venue is None and not source.steps
    sequences.activate(
        game,
        PLAYER,
        str(uuid4()),
        source.id,
        900,
        state(game).revision,
        "I activate my actual pending Feedback in this genuinely joined scene",
    )
    asyncio.run(SourcePauseWorker(game).tick(gateway))
    return rules.get(state(game), rules.FeedbackSequence, source.id)


@pytest.mark.parametrize("outcome", ["bond", "purpose", "tear", "die"])
def test_standalone_feedback_real_owned_effects_and_true_reprisal_not_a_fabricated_roll(
    ledger, tmp_path, monkeypatch, outcome
):
    from girlframe.services import m3_ankou_feedback_sequences as sequences

    game, worker, gateway, controls = ready(ledger, tmp_path, monkeypatch)
    sequence = feedback_source(game, controls, gateway)
    step = rules.get(state(game), rules.FeedbackStep, sequence.steps[0])
    target = current_ref(state(game), 3)
    before = state(game)
    frame_asset = next(
        x.id for x in before.sheets["2"].assets if x.family == "frame" and not x.void
    )
    girl = [x for x in before.sheets["2"].assets if x.family == "girl"]
    result = sequences.choose(
        game,
        PLAYER,
        str(uuid4()),
        step.id,
        before.revision,
        outcome,
        None if outcome == "die" else target,
        "My actual source-owned Feedback outcome",
        asset=frame_asset if outcome == "tear" else None,
        replace=girl[0].id if outcome == "bond" and len(girl) == 4 else None,
        name="Actual emotional distance" if outcome == "bond" else None,
        in_battle=False,
    )
    assert result["id"] == step.id
    assert game.dice.calls == 0
    if outcome == "die":
        assert any(x.actor == step.actor for x in state(game).career_archives)
        assert rules.get(state(game), rules.FeedbackSequence, sequence.id).terminal_event
    elif outcome == "bond":
        assert depth(state(game), step.actor, target) == 0
        assert any(x.name == "Actual emotional distance" for x in state(game).sheets["2"].assets)
    elif outcome == "purpose":
        sequences.answer_purpose(
            game,
            OTHER,
            str(uuid4()),
            step.id,
            state(game).revision,
            True,
            "An actual purpose authored by the original counterpart",
        )
        ordinary = [x for x in state(game).sheets["2"].identities if not x.protected]
        sequences.write_purpose(
            game,
            PLAYER,
            str(uuid4()),
            step.id,
            state(game).revision,
            ordinary[0].id if len(ordinary) == 4 else None,
        )
        assert any(
            x.name == "An actual purpose authored by the original counterpart"
            for x in state(game).sheets["2"].identities
        )
    else:
        assert not any(x.id == frame_asset for x in state(game).sheets["2"].assets)
        assert state(game).sheets["2"].heat == before.sheets["2"].heat + 5
        child = game.begin(
            PLAYER,
            str(uuid4()),
            900,
            state(game).sheets["2"].revision,
            PlayInput(
                play="flirt",
                context="I actually make the reprisal to prove my love",
                trigger_confirmed=True,
                heat=state(game).sheets["2"].heat,
                target=3,
                source_work=step.id,
            ),
        )["action_id"]
        tick(worker, gateway, 3)
        game.dice.faces = (1, 1)
        game.roll(PLAYER, str(uuid4()), child)
        pass_tags(game)
        answer(game, PLAYER, "actor_flirt", options=("name", "extra", "owe"))
        answer(game, OTHER, "target_flirt", text="My actual owned answer to her real Flirt")
        answer(game, OTHER, "flirt_owe_tag", text="Actual reprisal noticed")
        assert game.inspect(PLAYER, child)["state"] == "complete"
        assert game.dice.calls == 1
    if outcome != "die":
        assert rules.get(state(game), rules.FeedbackSequence, sequence.id).completed_event
