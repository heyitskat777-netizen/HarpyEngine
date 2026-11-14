"""Deferred P1 normal: real Ankou nomination and separately accepted own Alpha source.

Authored only. Do not treat this as executed gameplay evidence.
"""

import asyncio
import json
from uuid import uuid4

import pytest
from test_enforcer_requisitions import approved
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger_fixture
from test_m2_game import Gateway, pass_tags, state, tick
from test_mission_service import service
from test_mission_ui import current as native_current
from test_physical_operations import place
from test_world import initial

from girlframe.delivery.m2_worker import GameWorker
from girlframe.delivery.p1_source_pause_worker import SourcePauseWorker
from girlframe.discord_adapter.m3_alpha_sex import open_consent
from girlframe.discord_adapter.m3_required_plays import open_required
from girlframe.engine import m3_alpha_sex as alpha
from girlframe.engine import m3_ankou as ankou
from girlframe.engine import m3_required_plays as rules
from girlframe.engine.m2 import PlayInput
from girlframe.engine.m3_actor_bonds import current_ref, depth
from girlframe.services.m3_alpha_sex import SexService
from girlframe.services.m3_ankou import AnkouService
from girlframe.services.m3_recovery import RecoveryService
from girlframe.services.m3_required_plays import RequiredPlayService, prove, source_for_play
from girlframe.services.onboarding import WorkflowError
from girlframe.services.p1_source_pause import projection

ledger = ledger_fixture


def current(user=2):
    value = native_current(user, int(uuid4().int % 1000000000))
    value.channel_id = 900
    return value


def native(callback, *, user=2, **values):
    async def run():
        interaction = current(user)
        await interaction.response.defer(ephemeral=True)
        await callback(interaction)
        form = interaction.edit_original_response.call_args.kwargs["view"]
        assert not await form.interaction_check(current(1 if user == 2 else 2))
        form.values.update(values)
        response = current(user)
        await form.confirm.callback(response)
        assert form.completed, response.edit_original_response.call_args_list
        return response.edit_original_response.call_args.kwargs.get("view")

    return asyncio.run(run())


def submit(form, user=2, **values):
    async def run():
        form.values.update(values)
        response = current(user)
        await form.confirm.callback(response)
        assert form.completed, response.edit_original_response.call_args_list
        return response.edit_original_response.call_args.kwargs.get("view")

    return asyncio.run(run())


def finish_mid(game, worker, gateway, action):
    game.dice.faces = (4, 5)
    tick(worker, gateway, 3)
    if game.inspect(PLAYER, action)["state"] != "tag_window":
        game.roll(PLAYER, str(uuid4()), action)
    pass_tags(game)
    assert game.inspect(PLAYER, action)["state"] == "complete"


def test_actual_nomination_native_alpha_consent_cancel_retry_effects_and_pause_restore(
    ledger, tmp_path, monkeypatch
):
    _, game = service(ledger, girl="ALPHA", frame=ankou.FRAME)
    approved(ledger, game, tmp_path, monkeypatch, extra=(ankou.RELAY, alpha.RULE))
    with ledger.transaction() as c:
        actual = state(game)
        actual.world = initial()
        actual = place(place(actual, 2, mode="outside_frame"), 3, mode="outside_frame")
        game.event(c, 1, str(uuid4()), "synthetic.actual_original_alpha_ankou_bodies", actual)
    worker, gateway = GameWorker(game), Gateway()
    sex, controls, required = SexService(game), AnkouService(game), RequiredPlayService(game)

    # Earn the real Intense Bond through an actual completed own Alpha Play.
    first = sex.invite(
        PLAYER,
        str(uuid4()),
        900,
        current_ref(state(game), 3),
        state(game).revision,
        "My actual voluntary interaction with this original counterpart",
    )["id"]
    sex.respond(
        OTHER,
        str(uuid4()),
        first,
        state(game).revision,
        True,
        "I confirm only my own actual voluntary source",
    )
    prior = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play=alpha.PLAY,
            source_work=first,
            target_actor=current_ref(state(game), 3),
            heat=0,
            context="Our actual confirmed voluntary source",
            trigger_confirmed=True,
        ),
    )["action_id"]
    finish_mid(game, worker, gateway, prior)
    tick(worker, gateway, 5)
    actual = state(game)
    assert depth(actual, current_ref(actual, 2), current_ref(actual, 3)) == 2

    relay = controls.activate_relay(
        PLAYER,
        str(uuid4()),
        900,
        actual.revision,
        ("speech", "touch"),
        "I activate my actual Emotional Relay",
    )["id"]
    controls.choose_consequence(
        ADMIN,
        str(uuid4()),
        state(game).revision,
        relay,
        "nominees",
        "The actual Intense partners nominate actual Plays",
    )
    nomination = next(
        x
        for x in ankou.records(state(game), ankou.Task)
        if x.source == relay and x.kind == "nominate" and x.actor == current_ref(state(game), 3)
    )
    controls.choose_task(
        OTHER,
        str(uuid4()),
        state(game).revision,
        nomination.id,
        alpha.PLAY,
        "I nominate her actual own Alpha Sex Play, without authoring anyone's consent",
    )
    task = next(
        x
        for x in ankou.records(state(game), ankou.Task)
        if x.source == relay and x.kind == "perform"
    )
    asyncio.run(SourcePauseWorker(game).tick(gateway))
    with ledger.engine.connect() as c:
        assert projection(game, c, task.id)["state"] == "held"
        assert not game.pending_actions(c)
    with pytest.raises(WorkflowError):
        required.menu(OTHER, task.id)

    # The source pause creates no fake Action: actual invite and answer still work.
    alpha_menu = native(lambda i: open_required(i, game, task.id), operation=("invite",))
    invite = submit(alpha_menu, action=("invite",))
    submit(
        invite,
        target=(current_ref(state(game), 3).token,),
        account="My actual voluntary source during this paused nominated performance",
    )
    recipe = alpha.sessions(state(game))[-1]
    assert recipe.phase == "invited" and recipe.id != task.id
    native(
        lambda i: open_consent(i, sex, recipe.id),
        user=3,
        accept=("yes",),
        account="My own actual voluntary answer; no performance is inferred",
    )
    assert alpha.get(state(game), recipe.id).consent_event
    stale = state(game).revision - 1
    with pytest.raises(WorkflowError, match="STALE"):
        required.link(PLAYER, str(uuid4()), task.id, recipe.id, stale)
    native(lambda i: open_required(i, game, task.id), operation=("link:" + recipe.id,))
    selected = rules.records(state(game))[-1]
    assert selected.source == task.id and selected.recipe == recipe.id

    def start():
        form = native(lambda i: open_required(i, game, task.id), operation=("play",))
        submit(
            form,
            heat=("0",),
            gain=("1",),
            share=("0",),
            context="My actual confirmed voluntary Alpha interaction",
        )
        with ledger.engine.connect() as c:
            action = game.action(c, game.lock(c, 900)["action_id"])
        assert action["data"]["prepared"]["source_work"] == recipe.id
        assert action["data"]["ankou_effect_child"]["id"] == task.id
        return action["id"]

    abandoned = start()
    before = state(game)
    calls = game.dice.calls
    game.abort(ADMIN, str(uuid4()), abandoned)
    tick(worker, gateway, 5)
    recovery = RecoveryService(game)
    saved = next(x for x in recovery.saved(PLAYER) if x["id"] == abandoned)
    assert saved["cancellable"] and not saved["rolled"]
    key = str(uuid4())
    restored = recovery.recover(PLAYER, key, abandoned, saved["revision"], cancel=True)
    assert recovery.recover(PLAYER, key, abandoned, saved["revision"], cancel=True) == restored
    cancelled = state(game)
    assert rules.get(cancelled, selected.id).retired_event
    assert alpha.get(cancelled, recipe.id).action is None
    assert (
        alpha.get(cancelled, recipe.id).consent_event == alpha.get(before, recipe.id).consent_event
    )
    assert game.dice.calls == calls and cancelled.sheets["2"].heat == before.sheets["2"].heat
    with ledger.engine.connect() as c:
        prove(game, c, cancelled, selected.id)
        prepared = PlayInput(
            play=alpha.PLAY,
            source_work=recipe.id,
            context="Reopen the original accepted source",
            trigger_confirmed=True,
            heat=1,
            target_actor=recipe.target,
        )
        assert source_for_play(game, c, cancelled, prepared) is None
        forged = cancelled.model_copy(deep=True)
        old = rules.get(forged, selected.id)
        rules.put(forged, old.model_copy(update={"retired_event": str(uuid4())}))
        with pytest.raises(WorkflowError):
            source_for_play(game, c, forged, prepared)

    revision = cancelled.revision
    link_key = str(uuid4())
    linked = required.link(PLAYER, link_key, task.id, recipe.id, revision)
    assert required.link(PLAYER, link_key, task.id, recipe.id, revision) == linked
    assert linked["id"] != selected.id
    action = start()
    finish_mid(game, worker, gateway, action)
    completed = state(game)
    assert alpha.get(completed, recipe.id).phase == "complete"
    assert ankou.get(completed, ankou.Task, task.id).completed_event
    assert required.menu(PLAYER, task.id)["completed"]
    with ledger.engine.connect() as c:
        link = prove(game, c, completed, linked["id"])
        receipt = game.action(c, action)["data"]["receipt"]
        assert link.completed_event and link.action == action and receipt
    assert game.dice.calls == calls + 1
    tick(worker, gateway, 5)
    asyncio.run(SourcePauseWorker(game).tick(gateway))
    with ledger.engine.connect() as c:
        assert projection(game, c, task.id)["state"] == "closed"
    assert {k[0] + k[1]: v for k, v in gateway.values.items()} == json.loads(
        json.dumps(gateway.original)
    )


def test_actual_nomination_native_stim_self_dose_cancel_relink_drugs_and_pause_restore(
    ledger, tmp_path, monkeypatch
):
    """Authored P1 normal; genuine nomination, own Dose, real costs and cocktail choices."""
    from girlframe.discord_adapter.m3_dose_up import open_choice as open_dose_choice
    from girlframe.engine import m3_dose_up as dose
    from girlframe.engine.m3_actor_bonds import set_depth
    from girlframe.services.m3_dose_up import DoseUpService
    from girlframe.services.m3_dose_up import prove as prove_dose

    _, game = service(ledger, girl="STIM-BLISSED", frame=ankou.FRAME)
    approved(ledger, game, tmp_path, monkeypatch, extra=(ankou.RELAY, dose.RULE))
    with ledger.transaction() as c:
        actual = state(game)
        actual.world = initial()
        actual = place(place(actual, 2, mode="outside_frame"), 3, mode="outside_frame")
        actual.sheets["2"].heat = 3
        event = str(uuid4())
        # Explicit synthetic initial campaign relationship, not an Alpha entitlement or result.
        actual = set_depth(actual, current_ref(actual, 2), current_ref(actual, 3), 2, event)
        game.event(c, 1, event, "synthetic.initial_native_stim_ankou_intense_relationship", actual)
    worker, gateway = GameWorker(game), Gateway()
    controls, required = AnkouService(game), RequiredPlayService(game)
    relay = controls.activate_relay(
        PLAYER,
        str(uuid4()),
        900,
        state(game).revision,
        ("speech", "touch"),
        "I activate my actual original Frame's Emotional Relay",
    )["id"]
    controls.choose_consequence(
        ADMIN,
        str(uuid4()),
        state(game).revision,
        relay,
        "nominees",
        "The actual original Intense partner nominates an actual Play",
    )
    nomination = next(
        x
        for x in ankou.records(state(game), ankou.Task)
        if x.source == relay and x.kind == "nominate" and x.actor == current_ref(state(game), 3)
    )
    offered = controls.view(OTHER, nomination.id)["nomination_options"]
    assert dose.PLAY in offered and alpha.PLAY not in offered
    controls.choose_task(
        OTHER,
        str(uuid4()),
        state(game).revision,
        nomination.id,
        dose.PLAY,
        "I nominate her genuine own Dose Up without choosing her cocktail or spending her Heat",
    )
    task = next(
        x
        for x in ankou.records(state(game), ankou.Task)
        if x.source == relay and x.kind == "perform"
    )
    asyncio.run(SourcePauseWorker(game).tick(gateway))
    with ledger.engine.connect() as c:
        assert projection(game, c, task.id)["state"] == "held"
        assert not game.pending_actions(c)
    with pytest.raises(WorkflowError):
        required.menu(OTHER, task.id)
    native(lambda i: open_required(i, game, task.id), operation=("self_dose",))
    first = rules.records(state(game))[-1]
    assert first.rule == dose.RULE and first.actor == first.target
    assert not alpha.sessions(state(game))
    assert not dose.records(state(game), dose.Contact)
    assert not dose.records(state(game), dose.Dose)

    def start():
        dose_menu = native(lambda i: open_required(i, game, task.id), operation=("play",))
        form = submit(dose_menu, action=("self",))
        submit(form, heat=("1",), account="I actually self-inject my own combat cocktail")
        with ledger.engine.connect() as c:
            action = game.action(c, game.lock(c, 900)["action_id"])
        selected = rules.records(state(game))[-1]
        assert action["data"]["prepared"]["source_work"] == selected.recipe
        assert action["data"]["dose_up"]["required_recipe"] == selected.recipe
        assert action["data"]["dose_up"]["contact"] is None
        assert action["data"]["ankou_effect_child"]["id"] == task.id
        return action["id"]

    abandoned = start()
    before, calls = state(game), game.dice.calls
    game.abort(ADMIN, str(uuid4()), abandoned)
    tick(worker, gateway, 5)
    recovery = RecoveryService(game)
    saved = next(x for x in recovery.saved(PLAYER) if x["id"] == abandoned)
    assert saved["cancellable"] and not saved["rolled"]
    key = str(uuid4())
    cancelled = recovery.recover(PLAYER, key, abandoned, saved["revision"], cancel=True)
    assert recovery.recover(PLAYER, key, abandoned, saved["revision"], cancel=True) == cancelled
    assert rules.get(state(game), first.id).retired_event
    assert state(game).sheets["2"].heat == before.sheets["2"].heat
    assert game.dice.calls == calls and not dose.records(state(game), dose.Dose)
    assert not ankou.get(state(game), ankou.Task, task.id).completed_event
    revision, key = state(game).revision, str(uuid4())
    linked = required.link_self_dose(PLAYER, key, task.id, revision)
    assert required.link_self_dose(PLAYER, key, task.id, revision) == linked
    assert linked["id"] != first.id and linked["recipe"] != first.recipe
    assert len(rules.self_dose_recipes(state(game))) == 2
    action = start()
    game.dice.faces = (3, 4)
    tick(worker, gateway, 3)
    if game.inspect(PLAYER, action)["state"] != "tag_window":
        game.roll(PLAYER, str(uuid4()), action)
    pass_tags(game)
    row = next(x for x in game.choices(PLAYER) if x["kind"] == "dose_up_components")
    decision = game.decision(PLAYER, row["id"])
    native(lambda i: open_dose_choice(i, game, decision), components=("quick", "strong"))
    actual = state(game)
    assert game.inspect(PLAYER, action)["state"] == "complete"
    assert actual.sheets["2"].heat == before.sheets["2"].heat - 1
    assert len(dose.drug_tags(actual, current_ref(actual, 2))) == 2
    assert ankou.get(actual, ankou.Task, task.id).completed_event
    assert required.menu(PLAYER, task.id)["completed"]
    with ledger.engine.connect() as c:
        actual_dose = prove_dose(game, c, actual, action)
        assert actual_dose.actor == actual_dose.target == first.actor
        assert actual_dose.contact is None and actual_dose.order is None
        assert actual_dose.total == 8 and actual_dose.heat == 1
        assert prove(game, c, actual, linked["id"]).completed_event
    assert game.dice.calls == calls + 1
    assert DoseUpService(ledger, game).view(PLAYER, action)["components"]
    with pytest.raises(WorkflowError):
        DoseUpService(ledger, game).view(OTHER, action)
    tick(worker, gateway, 5)
    asyncio.run(SourcePauseWorker(game).tick(gateway))
    with ledger.engine.connect() as c:
        assert projection(game, c, task.id)["state"] == "closed"
    assert {k[0] + k[1]: v for k, v in gateway.values.items()} == json.loads(
        json.dumps(gateway.original)
    )


def test_actual_ankou_nomination_native_own_advice_and_real_listening_complete_source(
    ledger, tmp_path, monkeypatch
):
    from girlframe.discord_adapter.m3_ankou import open_ankou
    from girlframe.engine import m3_oldgen as oldgen
    from girlframe.engine.m3_actor_bonds import set_depth
    from girlframe.services.m3_oldgen import prove_advice

    _, game = service(ledger, girl="OLDGEN", frame=ankou.FRAME)
    approved(ledger, game, tmp_path, monkeypatch, extra=(ankou.RELAY, oldgen.ADVICE))
    with ledger.transaction() as c:
        actual = state(game)
        actual.world = initial()
        actual = place(place(actual, 2, mode="outside_frame"), 3, mode="outside_frame")
        actual.sheets["2"].heat = 3
        event = str(uuid4())
        actual = set_depth(actual, current_ref(actual, 2), current_ref(actual, 3), 2, event)
        game.event(c, 1, event, "synthetic.initial_oldgen_ankou_intense_relationship", actual)
    controls = AnkouService(game)
    worker, gateway = GameWorker(game), Gateway()
    relay = controls.activate_relay(
        PLAYER,
        str(uuid4()),
        900,
        state(game).revision,
        ("speech", "touch"),
        "I actually activate this Emotional Relay",
    )["id"]
    controls.choose_consequence(
        ADMIN,
        str(uuid4()),
        state(game).revision,
        relay,
        "nominees",
        "Actual Intense partners nominate their own choices",
    )
    nomination = next(
        x
        for x in ankou.records(state(game), ankou.Task)
        if x.source == relay and x.kind == "nominate"
    )
    assert oldgen.PLAY in controls.view(OTHER, nomination.id)["nomination_options"]
    controls.choose_task(
        OTHER,
        str(uuid4()),
        state(game).revision,
        nomination.id,
        oldgen.PLAY,
        "I nominate her own advice without supplying its maxim or recipient's reply",
    )
    task = next(
        x
        for x in ankou.records(state(game), ankou.Task)
        if x.source == relay and x.kind == "perform"
    )
    asyncio.run(SourcePauseWorker(game).tick(gateway))
    form = native(lambda i: open_ankou(i, controls, task.id), operation=("child",))
    before = state(game)
    submit(
        form,
        play=(oldgen.PLAY,),
        target=("3",),
        heat=("1",),
        identity=(),
        gain=("0",),
        pair_share=("0",),
        piloting=("no",),
        witnessed=("no",),
        trigger=("yes",),
        context="I give the original partner actual advice as nominated",
    )
    with ledger.engine.connect() as c:
        action = game.lock(c, 900)["action_id"]
        raw = game.action(c, action)
    assert raw["data"]["prepared"]["source_work"] == task.id
    assert raw["data"]["ankou_effect_child"]["id"] == task.id
    assert not rules.records(state(game))  # No synthetic accepted-recipe wrapper is necessary.
    game.dice.faces = (3, 4)
    tick(worker, gateway, 3)
    pass_tags(game)
    assert not ankou.get(state(game), ankou.Task, task.id).completed_event
    from test_m2_game import answer

    answer(game, PLAYER, "oldgen_write_maxim", text="PRIVATE_ACTUAL_NOMINATED_ADVICE")
    answer(game, OTHER, "oldgen_listen", text="I actually listen to this advice")
    assert game.inspect(PLAYER, action)["state"] == "complete"
    assert ankou.get(state(game), ankou.Task, task.id).completed_event
    assert state(game).sheets["2"].heat == before.sheets["2"].heat - 1
    with ledger.engine.connect() as c:
        advice = prove_advice(game, c, state(game), action)
        assert advice.actor == current_ref(state(game), 2)
    assert (
        game.roll(PLAYER, str(uuid4()), action)["receipt"]
        == game.inspect(PLAYER, action)["receipt"]
    )
    assert game.dice.calls == 1
    tick(worker, gateway, 5)
    asyncio.run(SourcePauseWorker(game).tick(gateway))
    with ledger.engine.connect() as c:
        assert projection(game, c, task.id)["state"] == "closed"


def test_actual_nomination_native_oldgen_source_cancel_relink_results_and_pause_restore(
    ledger, tmp_path, monkeypatch
):
    from test_oldgen_sex import native_choice

    from girlframe.discord_adapter.m3_oldgen_sex import open_oldgen_sex
    from girlframe.engine import m3_oldgen_sex as oldgen
    from girlframe.services.m3_oldgen_sex import OldgenSexService

    _, game = service(ledger, girl="OLDGEN", frame=ankou.FRAME)
    approved(ledger, game, tmp_path, monkeypatch, extra=(ankou.RELAY, oldgen.RULE))
    with ledger.transaction() as c:
        actual = state(game)
        actual.world = initial()
        actual = place(place(actual, 2, mode="outside_frame"), 3, mode="outside_frame")
        game.event(c, 1, str(uuid4()), "synthetic.actual_original_oldgen_ankou_bodies", actual)
    worker, gateway = GameWorker(game), Gateway()
    sex, controls, required = OldgenSexService(game), AnkouService(game), RequiredPlayService(game)

    def finish(action, label):
        game.dice.faces = (4, 5)
        tick(worker, gateway, 3)
        if game.inspect(PLAYER, action)["state"] == "ready_to_roll":
            game.roll(PLAYER, str(uuid4()), action)
        pass_tags(game)
        native_choice(game, PLAYER, "oldgen_sex_effects", ("tag", "bond"), fields={"tag": label})
        assert game.inspect(PLAYER, action)["state"] == "complete"

    first = sex.invite(
        PLAYER,
        str(uuid4()),
        900,
        current_ref(state(game), 3),
        state(game).revision,
        "PRIVATE_OWN_OLDGEN: genuine first voluntary source",
    )["id"]
    sex.respond(
        OTHER,
        str(uuid4()),
        first,
        state(game).revision,
        True,
        "My own actual counterpart confirmation",
    )
    prior = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play=oldgen.PLAY,
            source_work=first,
            target_actor=current_ref(state(game), 3),
            heat=0,
            context="Our genuine first voluntary interaction",
            trigger_confirmed=True,
        ),
    )["action_id"]
    finish(prior, "PRIVATE_OWN_OLDGEN: first actual source Tag")
    tick(worker, gateway, 5)
    actual = state(game)
    assert depth(actual, current_ref(actual, 2), current_ref(actual, 3)) == 2
    relay = controls.activate_relay(
        PLAYER,
        str(uuid4()),
        900,
        actual.revision,
        ("speech", "touch"),
        "Actual relay with my original Intense partner",
    )["id"]
    controls.choose_consequence(
        ADMIN,
        str(uuid4()),
        state(game).revision,
        relay,
        "nominees",
        "The original Intense partners nominate actual Plays",
    )
    nomination = next(
        x
        for x in ankou.records(state(game), ankou.Task)
        if x.source == relay and x.kind == "nominate" and x.actor == current_ref(state(game), 3)
    )
    controls.choose_task(
        OTHER,
        str(uuid4()),
        state(game).revision,
        nomination.id,
        oldgen.PLAY,
        "Nominate her own Oldgen source, without authoring consent",
    )
    task = next(
        x
        for x in ankou.records(state(game), ankou.Task)
        if x.source == relay and x.kind == "perform"
    )
    asyncio.run(SourcePauseWorker(game).tick(gateway))
    with ledger.engine.connect() as c:
        assert projection(game, c, task.id)["state"] == "held"
        assert not game.pending_actions(c)
    with pytest.raises(WorkflowError):
        required.menu(OTHER, task.id)
    source_menu = native(lambda i: open_required(i, game, task.id), operation=("invite_oldgen",))
    invitation = submit(source_menu, action=("invite",))
    submit(
        invitation,
        target=(current_ref(state(game), 3).token,),
        account="PRIVATE_OWN_OLDGEN: new actual interaction during required pause",
    )
    recipe = oldgen.records(state(game), oldgen.Session)[-1]
    native(
        lambda i: open_oldgen_sex(i, sex, recipe.id),
        user=3,
        accept=("yes",),
        account="My independent original counterpart answer",
    )
    assert oldgen.get(state(game), recipe.id).consent_event
    with pytest.raises(WorkflowError, match="STALE"):
        required.link(PLAYER, str(uuid4()), task.id, recipe.id, state(game).revision - 1)
    native(lambda i: open_required(i, game, task.id), operation=("link:" + recipe.id,))
    selected = rules.records(state(game))[-1]
    assert selected.rule == oldgen.RULE and selected.recipe == recipe.id

    def start_oldgen():
        form = native(lambda i: open_required(i, game, task.id), operation=("play",))
        submit(
            form,
            heat=("0",),
            gain=("1",),
            share=("0",),
            context="PRIVATE_OWN_OLDGEN: actual accepted nominated interaction",
        )
        with ledger.engine.connect() as c:
            action = game.action(c, game.lock(c, 900)["action_id"])
            assert action["data"]["oldgen_sex"]["session"] == recipe.id
            assert action["data"]["ankou_effect_child"]["id"] == task.id
            return action["id"]

    abandoned = start_oldgen()
    before, calls = state(game), game.dice.calls
    game.abort(ADMIN, str(uuid4()), abandoned)
    tick(worker, gateway, 5)
    recovery = RecoveryService(game)
    saved = next(x for x in recovery.saved(PLAYER) if x["id"] == abandoned)
    assert saved["cancellable"] and not saved["rolled"]
    args = PLAYER, str(uuid4()), abandoned, saved["revision"]
    recovered = recovery.recover(*args, cancel=True)
    assert recovery.recover(*args, cancel=True) == recovered
    cancelled = state(game)
    assert rules.get(cancelled, selected.id).retired_event
    restored = oldgen.get(cancelled, recipe.id)
    assert restored.action is None and restored.bound_event is None and restored.phase == "accepted"
    assert restored.consent_event == oldgen.get(before, recipe.id).consent_event
    assert game.dice.calls == calls and cancelled.sheets["2"].heat == before.sheets["2"].heat
    with ledger.engine.connect() as c:
        prove(game, c, cancelled, selected.id)
    args = PLAYER, str(uuid4()), task.id, recipe.id, cancelled.revision
    linked = required.link(*args)
    assert required.link(*args) == linked and linked["id"] != selected.id
    action = start_oldgen()
    finish(action, "PRIVATE_OWN_OLDGEN: actual required source outcome")
    final = state(game)
    assert oldgen.get(final, recipe.id).phase == "complete"
    assert ankou.get(final, ankou.Task, task.id).completed_event
    assert required.menu(PLAYER, task.id)["completed"]
    with ledger.engine.connect() as c:
        value = prove(game, c, final, linked["id"])
        assert value.action == action and value.completed_event
        receipt = game.action(c, action)["data"]["receipt"]
        assert receipt and game.action(c, action)["data"]["oldgen_sex"][
            "actor"
        ] == recipe.actor.model_dump(mode="json")
    assert game.dice.calls == calls + 1
    tick(worker, gateway, 7)
    asyncio.run(SourcePauseWorker(game).tick(gateway))
    with ledger.engine.connect() as c:
        assert projection(game, c, task.id)["state"] == "closed"
    assert {key[0] + key[1]: value for key, value in gateway.values.items()} == gateway.original
    assert "PRIVATE_OWN_OLDGEN" not in json.dumps(gateway.messages)


@pytest.mark.parametrize("girl", ["PRINCESS", "STIM-BLISSED"])
def test_actual_nomination_native_princess_or_stim_own_source_and_real_mid_results(
    ledger, tmp_path, monkeypatch, girl
):
    from test_m2_game import answer
    from test_stim_sex import choose as stim_choose

    from girlframe.discord_adapter.m3_princess_sex import open_princess
    from girlframe.discord_adapter.m3_stim_sex import open_stim
    from girlframe.engine import m3_disposable_psyche as psyche
    from girlframe.engine import m3_dose_up as dose
    from girlframe.engine import m3_princess_sex as princess
    from girlframe.engine import m3_stim_sex as stim
    from girlframe.services.m3_princess_sex import SexService as PrincessSexService
    from girlframe.services.m3_stim_sex import SexService as StimSexService

    is_princess = girl == "PRINCESS"
    book = princess if is_princess else stim
    opener = open_princess if is_princess else open_stim
    invite_field = "action" if is_princess else "source"
    _, game = service(ledger, girl=girl, frame=ankou.FRAME)
    approved(
        ledger,
        game,
        tmp_path,
        monkeypatch,
        extra=(ankou.RELAY, book.RULE) + (() if is_princess else (dose.SELF_RULE, psyche.RULE)),
    )
    with ledger.transaction() as c:
        actual = state(game)
        actual.world = initial()
        actual = place(place(actual, 2, mode="outside_frame"), 3, mode="outside_frame")
        if is_princess:
            from girlframe.engine.m3_actor_bonds import set_depth

            # Princess's agreed favour does not deepen a Bond. Start with the
            # real prior synthetic Intense relationship required by this Relay.
            event = str(uuid4())
            actual = set_depth(actual, current_ref(actual, 2), current_ref(actual, 3), 2, event)
            game.event(c, 1, event, "synthetic.actual_prior_intense_relationship", actual)
        game.event(c, 1, str(uuid4()), "synthetic.actual_nominee_original_bodies", actual)
    worker, gateway = GameWorker(game), Gateway()
    sex = PrincessSexService(game) if is_princess else StimSexService(game)
    controls, required = AnkouService(game), RequiredPlayService(game)

    def finish_invitation(form):
        submit(
            form,
            target=(current_ref(state(game), 3).token,),
            account="PRIVATE_REQUIRED_SOURCE: genuine original voluntary source",
        )
        values = (
            princess.sessions(state(game))
            if is_princess
            else stim.records(state(game), stim.Session)
        )
        source = values[-1]
        native(
            lambda i: opener(i, sex, source.id),
            user=3,
            accept=("yes",),
            account="My own actual voluntary confirmation, not an inferred performance",
        )
        return source

    def finish(action):
        game.dice.faces = (4, 5)
        tick(worker, gateway, 3)
        if game.inspect(PLAYER, action)["state"] == "ready_to_roll":
            game.roll(PLAYER, str(uuid4()), action)
        pass_tags(game)
        receipt = game.inspect(PLAYER, action)["receipt"]
        if is_princess:
            answer(
                game,
                PLAYER,
                "princess_sex_favour",
                text="PRIVATE_REQUIRED_SOURCE: my actual requested favour",
            )
            answer(
                game,
                OTHER,
                "princess_sex_favour_reply",
                options=("agree",),
                text="PRIVATE_REQUIRED_SOURCE: my own actual agreement",
            )
            assert not any(
                row["kind"] == "princess_sex_optional_tag" for row in game.choices(PLAYER)
            )  # Only a refused favour offers this optional Tag.
        else:
            stim_choose(game, PLAYER, "stim_sex_drug", ("quick",), native=True)
            stim_choose(game, PLAYER, "stim_sex_effects", ("bond",), native=True)
        assert game.inspect(PLAYER, action)["state"] == "complete"
        assert game.inspect(PLAYER, action)["receipt"] == receipt
        return receipt

    first_form = native(lambda i: opener(i, sex), **{invite_field: ("invite",)})
    first = finish_invitation(first_form)
    action = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play=book.PLAY,
            source_work=first.id,
            target_actor=current_ref(state(game), 3),
            heat=0,
            context="Our actual first voluntary source",
            trigger_confirmed=True,
        ),
    )["action_id"]
    finish(action)
    tick(worker, gateway, 5)
    actual = state(game)
    assert depth(actual, current_ref(actual, 2), current_ref(actual, 3)) == 2
    relay = controls.activate_relay(
        PLAYER,
        str(uuid4()),
        900,
        actual.revision,
        ("speech", "touch"),
        "Actual relay following this real original relationship",
    )["id"]
    controls.choose_consequence(
        ADMIN,
        str(uuid4()),
        state(game).revision,
        relay,
        "nominees",
        "The actual Intense partner nominates a real owned Play",
    )
    nomination = next(
        value
        for value in ankou.records(state(game), ankou.Task)
        if value.source == relay
        and value.kind == "nominate"
        and value.actor == current_ref(state(game), 3)
    )
    controls.choose_task(
        OTHER,
        str(uuid4()),
        state(game).revision,
        nomination.id,
        book.PLAY,
        "Nominate her own actual source, preserving everyone's consent and choices",
    )
    task = next(
        value
        for value in ankou.records(state(game), ankou.Task)
        if value.source == relay and value.kind == "perform"
    )
    asyncio.run(SourcePauseWorker(game).tick(gateway))
    with ledger.engine.connect() as c:
        assert projection(game, c, task.id)["state"] == "held"
    with pytest.raises(WorkflowError):
        required.menu(OTHER, task.id)
    source_menu = native(
        lambda i: open_required(i, game, task.id),
        operation=("invite_princess" if is_princess else "invite_stim",),
    )
    invitation = submit(source_menu, **{invite_field: ("invite",)})
    source = finish_invitation(invitation)
    args = PLAYER, str(uuid4()), task.id, source.id, state(game).revision
    selected = required.link(*args)
    assert required.link(*args) == selected
    form = native(lambda i: open_required(i, game, task.id), operation=("play",))
    submit(
        form,
        heat=("0",),
        gain=("1",),
        share=("0",),
        context="PRIVATE_REQUIRED_SOURCE: real nominated source performance",
    )
    with ledger.engine.connect() as c:
        child = game.action(c, game.lock(c, 900)["action_id"])
        assert child["data"][book.PLAY]["session"] == source.id
        assert child["data"]["ankou_effect_child"]["required_link"] == selected["id"]
    calls = game.dice.calls
    receipt = finish(child["id"])
    actual = state(game)
    assert ankou.get(actual, ankou.Task, task.id).completed_event
    assert required.menu(PLAYER, task.id)["completed"]
    with ledger.engine.connect() as c:
        value = prove(game, c, actual, selected["id"])
        assert value.rule == book.RULE and value.completed_event and value.action == child["id"]
        assert game.action(c, child["id"])["data"]["receipt"] == receipt
    assert game.dice.calls == calls + 1
    tick(worker, gateway, 7)
    asyncio.run(SourcePauseWorker(game).tick(gateway))
    with ledger.engine.connect() as c:
        assert projection(game, c, task.id)["state"] == "closed"
    assert "PRIVATE_REQUIRED_SOURCE" not in json.dumps(gateway.messages)
