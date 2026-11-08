"""One actual source-only rejection Play normal, deferred to final P1 checks."""

import asyncio
from uuid import uuid4

import pytest
from test_bonded import actual_man_game, intimate, pass_tags, pause_tick
from test_intracadre_marriage import FOUR
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import ChoiceAnswer, Dice, PlayInput, answer, state, tick
from test_mission_ui import current

from girlframe.discord_adapter.m3_bonded_rejection import open_bonded_rejection
from girlframe.engine import m3_bonded_rejection as rules
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_mockingbird import give_tag
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_bonded_rejection import (
    BondedRejectionService,
    prove_finding,
    prove_rejection_consumption,
)
from girlframe.services.m3_recovery import RecoveryService
from girlframe.services.onboarding import WorkflowError


def show(service, identity, number, *, account=None):
    async def run():
        interaction = current(4, number)
        interaction.channel_id = 901
        await interaction.response.defer(ephemeral=True)
        await open_bonded_rejection(interaction, service, identity, account=account)
        return interaction.edit_original_response.call_args.kwargs.get("view")

    return asyncio.run(run())


def submit(form, values, number):
    async def run():
        form.values.update(values)
        interaction = current(4, number)
        interaction.channel_id = 901
        await form.confirm.callback(interaction)
        assert form.completed, interaction.edit_original_response.call_args_list
        return interaction.edit_original_response.call_args.kwargs.get("view")

    return asyncio.run(run())


def pending_rejection(ledger, tmp_path, monkeypatch):
    game, worker, gateway, bonded = actual_man_game(ledger, tmp_path, monkeypatch)
    original_actor = type(gateway).actor

    async def actual_actor(current_gateway, identity):
        return FOUR if identity == FOUR.user_id else await original_actor(current_gateway, identity)

    monkeypatch.setattr(type(gateway), "actor", actual_actor)
    # Only the existing ordinary Tag is synthetic prior resource context. Its
    # first and repeated Man marks, law, intimacy, decisions and child are real.
    with ledger.transaction() as c:
        actual, event = state(game), str(uuid4())
        actual = give_tag(
            actual,
            profiles(c, ledger.campaign_id),
            current_ref(actual, 4),
            current_ref(actual, 2),
            "Still flinches",
            "actual-rejection-tag",
            event,
            (2, 4),
        )
        game.event(c, 2, str(uuid4()), "synthetic.prior_observed_Tag", actual, event_id=event)
    first = intimate(bonded, game, 4, "seven")
    bonded.activate(
        PLAYER,
        str(uuid4()),
        first,
        state(game).revision,
        "Actual first voluntary performed source",
        man_tag="actual-rejection-tag",
    )
    pause_tick(game, gateway)
    bonded.choose(
        PLAYER,
        str(uuid4()),
        first,
        state(game).revision,
        ChoiceAnswer(options=("promise",), text="I actually promise protection"),
    )
    bonded.choose(
        FOUR, str(uuid4()), first, state(game).revision, ChoiceAnswer(text="I give no Tags")
    )
    pause_tick(game, gateway)
    game.close_scene(ADMIN, str(uuid4()), 900)
    game.bind_scene(ADMIN, str(uuid4()), 901)
    for who in (PLAYER, OTHER, FOUR, ADMIN):
        game.join_scene(who, str(uuid4()), 901)
    source = bonded.propose(
        PLAYER,
        str(uuid4()),
        901,
        state(game).revision,
        "sex",
        "Actual later voluntary source",
        target=current_ref(state(game), 4),
        route="seven",
    )["id"]
    bonded.confirm(
        FOUR, str(uuid4()), source, state(game).revision, True, "My actual own participation"
    )
    bonded.activate(
        PLAYER,
        str(uuid4()),
        source,
        state(game).revision,
        "Actual later performed source",
        man_tag="actual-rejection-tag",
    )
    pause_tick(game, gateway)
    bonded.resolve_man_tag(
        FOUR, str(uuid4()), source, state(game).revision, ChoiceAnswer(options=("reject",))
    )
    return game, worker, gateway, bonded, source


def test_real_keep_rejection_unrolled_retry_owned_finding_and_original_high_completion(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, bonded, source = pending_rejection(ledger, tmp_path, monkeypatch)
    service = BondedRejectionService(game)
    account = "I hold my composure under pressure while I directly reject that label"
    form = show(service, source, 89600, account=account)
    assert all(field.key != "account" for field in form.fields)
    submit(form, {"play": ("keep_your_head",)}, 89601)
    request = rules.records(state(game), rules.Request)[0]
    assert request.account == account and request.owner == current_ref(state(game), 4)
    with pytest.raises(WorkflowError):
        bonded.perform_man_rejection(
            FOUR,
            str(uuid4()),
            source,
            state(game).revision,
            "Skip the declared mandatory Play",
            requires_play=False,
        )
    with pytest.raises(WorkflowError):
        service.view(OTHER, request.id)
    game.dice = Dice((4, 4))
    prepared = PlayInput(
        play="keep_your_head",
        source_work=request.id,
        context=account,
        trigger_confirmed=True,
        heat=0,
    )
    child = game.begin(FOUR, str(uuid4()), 901, state(game).sheets["4"].revision, prepared)[
        "action_id"
    ]
    game.abort(ADMIN, str(uuid4()), child)
    recovery = RecoveryService(game)
    saved = next(x for x in recovery.saved(FOUR) if x["id"] == child)
    tick(worker, gateway, 4)
    result = recovery.recover(FOUR, str(uuid4()), child, saved["revision"], cancel=True)
    assert result["cancelled_unrolled"] and game.dice.calls == 0
    assert len(rules.records(state(game), rules.Release)) == 1
    child = game.begin(FOUR, str(uuid4()), 901, state(game).sheets["4"].revision, prepared)[
        "action_id"
    ]
    tick(worker, gateway, 3)
    pass_tags(game)
    receipt = game.inspect(FOUR, child)["receipt"]
    assert receipt["faces"] == [4, 4] and game.dice.calls == 1
    assert not service.view(FOUR, request.id)["can_conclude"]
    answer(game, FOUR, "actor_keep", options=("tough", "sexy"), denied=("in_control",))
    answer(game, ADMIN, "handler_keep", flag=True, text="Actual ordinary Keep outcome adjudication")
    tick(worker, gateway, 5)
    data = service.view(FOUR, request.id)
    assert data["can_conclude"]
    attempt = data["attempts"][-1]
    assert next(x for x in state(game).sheets["4"].tags if x.id == request.tag).rejection_pending
    with pytest.raises(WorkflowError):
        service.conclude(
            PLAYER,
            str(uuid4()),
            request.id,
            state(game).revision,
            attempt["id"],
            True,
            "I cannot decide her actual outcome",
        )
    revision = state(game).revision
    form = submit(show(service, request.id, 89602), {"operation": ("conclude",)}, 89603)
    conclusion = "I actually held my composure and rejected that label in the completed action"
    submit(form, {"achieved": ("yes",), "account": conclusion}, 89604)
    service.conclude(FOUR, "89604", request.id, revision, attempt["id"], True, conclusion)
    actual = state(game)
    finding = rules.records(actual, rules.Finding)[0]
    with ledger.engine.connect() as c:
        assert prove_finding(game, c, actual, finding.id) == finding
    assert finding.achieved and not any(x.id == request.tag for x in actual.sheets["4"].tags)
    assert game.inspect(FOUR, child)["receipt"] == receipt and game.dice.calls == 1
    assert service.view(FOUR, request.id)["attempts"][-1]["finding"]["account"] == conclusion
    bonded.choose(
        PLAYER,
        str(uuid4()),
        source,
        state(game).revision,
        ChoiceAnswer(options=("promise",), text="I actually promise protection"),
    )
    bonded.choose(
        FOUR, str(uuid4()), source, state(game).revision, ChoiceAnswer(text="I give no Tags")
    )
    pause_tick(game, gateway)
    assert bonded.view(FOUR, source)["phase"] == "complete"
    assert len(rules.records(state(game), rules.Finding)) == 1
    assert len(rules.records(state(game), rules.Attempt)) == 2


def test_actual_received_order_native_refusal_preserves_parent_and_proves_mid_tag_consumption(
    ledger, tmp_path, monkeypatch
):
    """Deferred Order normal: actual receiver, resume-only chain and exact child rejection."""
    game, worker, gateway, bonded, source = pending_rejection(ledger, tmp_path, monkeypatch)
    service = BondedRejectionService(game)
    order = game.issue_order(
        PLAYER, str(uuid4()), 901, 4, "Hold still and stop challenging that label"
    )
    parent = order["action_id"]
    tick(worker, gateway, 3)
    account = "I actually refuse this received Order to reject that label"
    form = show(service, source, 89700, account=account)
    assert all(field.key != "account" for field in form.fields)
    submit(form, {"play": ("order:" + parent,)}, 89701)
    request = rules.records(state(game), rules.Request)[0]
    assert (
        request.order
        and request.order.parent == parent
        and request.order.order == order["order_id"]
    )
    with pytest.raises(WorkflowError):
        service.attach_order(
            OTHER,
            str(uuid4()),
            source,
            state(game).revision,
            order["order_id"],
            parent,
            "I cannot attach another person's Order",
        )
    # The attached receiver still makes the actual ordinary Receive Orders choice.
    form = submit(show(service, request.id, 89702), {"operation": ("order",)}, 89703)
    submit(form, {"options": ("disobey",)}, 89704)
    response = next(x for x in game.choices(FOUR) if x["kind"] == "order_disobey")
    projected = game.decision(FOUR, response["id"])
    assert projected["parent"] == parent and projected["body"]["order_id"] == order["order_id"]
    assert projected["body"]["source_work"] == request.id
    game.dice = Dice((4, 4))
    prepared = PlayInput(
        play="disobey_orders",
        parent=parent,
        order_id=order["order_id"],
        source_work=request.id,
        context=account,
        trigger_confirmed=True,
        heat=0,
        witnessed=True,
    )
    child = game.begin(FOUR, str(uuid4()), 901, state(game).sheets["4"].revision, prepared)[
        "action_id"
    ]
    game.abort(ADMIN, str(uuid4()), parent)
    recovery = RecoveryService(game)
    saved = next(x for x in recovery.saved(FOUR) if x["id"] == parent)
    assert not saved["cancellable"]
    tick(worker, gateway, 4)
    with pytest.raises(WorkflowError):
        recovery.recover(FOUR, str(uuid4()), parent, saved["revision"], cancel=True)
    recovery.recover(FOUR, str(uuid4()), parent, saved["revision"], cancel=False)
    tick(worker, gateway, 3)
    pass_tags(game)
    receipt = game.inspect(FOUR, child)["receipt"]
    assert receipt["faces"] == [4, 4] and game.dice.calls == 1
    assert not rules.records(state(game), rules.Release)
    answer(game, FOUR, "actor_disobey", options=("reject_tag",), denied=(request.tag,))
    assert not any(x.id == request.tag for x in state(game).sheets["4"].tags)
    # This is the real Handler's factual knowledge answer, not a rejection veto.
    answer(
        game,
        ADMIN,
        "handler_disobey",
        flag=False,
        text="The original Handler did not learn this actual refusal",
    )
    tick(worker, gateway, 5)
    assert game.inspect(FOUR, child)["state"] == "complete"
    assert game.inspect(FOUR, parent)["state"] == "complete"
    with ledger.engine.connect() as c:
        original_parent = game.action(c, parent)
        assert original_parent["data"]["play"] == "receive_orders"
        assert original_parent["parent_id"] is None and original_parent["data"]["receipt"] is None
        assert original_parent["data"]["result"]["response"] == "disobey"
        assert original_parent["data"]["result"]["response_play"] == child
    data = service.view(FOUR, request.id)
    assert data["can_conclude"] and data["outcome_options"] == ["yes"]
    attempt = data["attempts"][-1]
    revision, sheet_revision = state(game).revision, state(game).sheets["4"].revision
    with pytest.raises(WorkflowError):
        service.conclude(
            FOUR,
            str(uuid4()),
            request.id,
            revision,
            attempt["id"],
            False,
            "The actual consumed Tag cannot be represented as still present",
        )
    form = submit(show(service, request.id, 89705), {"operation": ("conclude",)}, 89706)
    conclusion = "I actually rejected that exact Tag through my completed refusal choice"
    submit(form, {"achieved": ("yes",), "account": conclusion}, 89707)
    service.conclude(FOUR, "89707", request.id, revision, attempt["id"], True, conclusion)
    actual = state(game)
    finding = rules.records(actual, rules.Finding)[0]
    with ledger.engine.connect() as c:
        assert prove_finding(game, c, actual, finding.id).tag_consumed_event
        assert (
            prove_rejection_consumption(
                game,
                c,
                actual,
                finding.id,
                source=source,
                resolution=request.resolution,
                owner=request.owner,
                tag=request.tag,
            )
            == finding.tag_consumed_event
        )
    assert finding.tag_consumed_event != finding.event
    assert actual.sheets["4"].revision == sheet_revision  # No second Tag erasure/resolution.
    assert game.inspect(FOUR, child)["receipt"] == receipt and game.dice.calls == 1
    with pytest.raises(WorkflowError):
        service.view(OTHER, request.id)
    bonded.choose(
        PLAYER,
        str(uuid4()),
        source,
        actual.revision,
        ChoiceAnswer(options=("promise",), text="I actually promise protection"),
    )
    bonded.choose(
        FOUR, str(uuid4()), source, state(game).revision, ChoiceAnswer(text="I give no Tags")
    )
    pause_tick(game, gateway)
    assert bonded.view(FOUR, source)["phase"] == "complete"
