"""Native required Mockingbird Sex normal; authored for root, no worker pytest."""

import asyncio
from uuid import uuid4

import pytest
from test_enforcer_requisitions import approved
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger_fixture
from test_m2_game import Gateway, answer, pass_tags, state, tick
from test_mission_service import service
from test_physical_operations import place
from test_required_plays import native, submit
from test_world import initial

from girlframe.delivery.m2_worker import GameWorker
from girlframe.delivery.p1_source_pause_worker import SourcePauseWorker
from girlframe.discord_adapter.m3_ankou import open_ankou
from girlframe.discord_adapter.m3_required_plays import open_required
from girlframe.engine import m3_ankou as ankou
from girlframe.engine import m3_required_plays as rules
from girlframe.engine.m3_actor_bonds import current_ref, set_depth
from girlframe.engine.m3_mockingbird import starry_capabilities
from girlframe.engine.m3_mockingbird_state import SEX
from girlframe.services.m3_ankou import AnkouService
from girlframe.services.m3_mockingbird_plays import MockingbirdService
from girlframe.services.m3_recovery import RecoveryService
from girlframe.services.m3_required_plays import MOCK_SEX_RULE, RequiredPlayService, prove
from girlframe.services.onboarding import WorkflowError
from girlframe.services.p1_source_pause import projection

ledger = ledger_fixture


def test_native_mockingbird_sex_nomination_consent_cancel_retry_real_effects_and_restore(
    ledger, tmp_path, monkeypatch
):
    _, game = service(ledger, girl="MOCKINGBIRD", frame=ankou.FRAME)
    approved(ledger, game, tmp_path, monkeypatch, extra=(ankou.RELAY, MOCK_SEX_RULE))
    with ledger.transaction() as c:
        actual = state(game)
        actual.world = initial()
        actual = place(place(actual, 2, mode="outside_frame"), 3, mode="outside_frame")
        actual.sheets["2"].heat = 3
        event = str(uuid4())
        actual = set_depth(actual, current_ref(actual, 2), current_ref(actual, 3), 2, event)
        game.event(c, 1, event, "synthetic.initial_mock_ankou_intense_relationship", actual)
    controls, required = AnkouService(game), RequiredPlayService(game)
    worker, gateway = GameWorker(game), Gateway()
    relay = controls.activate_relay(
        PLAYER,
        str(uuid4()),
        900,
        state(game).revision,
        ("speech", "touch"),
        "I activate this actual emotional relay",
    )["id"]
    controls.choose_consequence(
        ADMIN,
        str(uuid4()),
        state(game).revision,
        relay,
        "nominees",
        "The actual Intense partners nominate Plays",
    )
    nomination = next(
        x
        for x in ankou.records(state(game), ankou.Task)
        if x.source == relay and x.kind == "nominate"
    )
    assert SEX in controls.view(OTHER, nomination.id)["nomination_options"]
    controls.choose_task(
        OTHER,
        str(uuid4()),
        state(game).revision,
        nomination.id,
        SEX,
        "I nominate her own Sex Play without consenting for anyone",
    )
    task = next(
        x
        for x in ankou.records(state(game), ankou.Task)
        if x.source == relay and x.kind == "perform"
    )
    asyncio.run(SourcePauseWorker(game).tick(gateway))
    with pytest.raises(WorkflowError):
        required.menu(OTHER, task.id)
    # Native Ankou entry routes to the existing source declaration controls.
    menu = native(lambda i: open_ankou(i, controls, task.id), operation=("child",))
    declaration = submit(menu, operation=("invite_mockingbird",))
    submit(
        declaration,
        play=(SEX,),
        targets=(current_ref(state(game), 3).token,),
        primary=(),
        account="PRIVATE_ACTUAL_NOMINATED_SEX",
    )
    trigger = state(game).mockingbird.triggers[-1]
    source = MockingbirdService(game)
    target = current_ref(state(game), 3)
    assert trigger.state == "proposed" and trigger.action is None
    assert not required.menu(PLAYER, task.id)["accepted"]
    with pytest.raises(WorkflowError):
        required.link(PLAYER, str(uuid4()), task.id, trigger.id, state(game).revision)
    with pytest.raises(WorkflowError):
        source.attest(PLAYER, str(uuid4()), trigger.id, target, True)
    source.attest(OTHER, str(uuid4()), trigger.id, target, False)
    assert not required.menu(PLAYER, task.id)["accepted"]
    assert not ankou.get(state(game), ankou.Task, task.id).completed_event
    declaration = native(
        lambda i: open_required(i, game, task.id), operation=("invite_mockingbird",)
    )
    submit(
        declaration,
        play=(SEX,),
        targets=(target.token,),
        primary=(),
        account="PRIVATE_FRESH_NOMINATED_SEX",
    )
    trigger = state(game).mockingbird.triggers[-1]
    source.attest(OTHER, str(uuid4()), trigger.id, target, True)
    trigger = state(game).mockingbird.triggers[-1]
    native(lambda i: open_required(i, game, task.id), operation=("link:" + trigger.id,))
    linked = rules.records(state(game))[-1]
    # A readiness flag is not an independently authored, canonical consent event.
    with ledger.engine.connect() as c:
        forged = state(game).model_copy(deep=True)
        replacement = trigger.model_copy(
            update={
                "parties": tuple(
                    x.model_copy(update={"event": trigger.source_event}) for x in trigger.parties
                )
            }
        )
        forged.mockingbird = forged.mockingbird.model_copy(
            update={
                "triggers": tuple(
                    replacement if x.id == trigger.id else x for x in forged.mockingbird.triggers
                )
            }
        )
        with pytest.raises(WorkflowError):
            prove(game, c, forged, linked.id)

    def start():
        form = native(lambda i: open_required(i, game, task.id), operation=("play",))
        submit(form, heat=("1",), identity=(), gain=("0",))
        with ledger.engine.connect() as c:
            action = game.action(c, game.lock(c, 900)["action_id"])
        assert action["data"]["prepared"]["source_work"] == trigger.id
        assert action["data"]["ankou_effect_child"]["id"] == task.id
        return action["id"]

    abandoned = start()
    before = state(game)
    game.abort(ADMIN, str(uuid4()), abandoned)
    tick(worker, gateway, 5)
    recovery = RecoveryService(game)
    saved = next(x for x in recovery.saved(PLAYER) if x["id"] == abandoned)
    assert saved["cancellable"] and not saved["rolled"]
    recovery.recover(PLAYER, str(uuid4()), abandoned, saved["revision"], cancel=True)
    assert state(game).mockingbird.triggers[-1] == trigger
    assert state(game).sheets["2"].heat == before.sheets["2"].heat
    assert game.dice.calls == 0
    native(lambda i: open_required(i, game, task.id), operation=("link:" + trigger.id,))
    action = start()
    game.dice.faces = (3, 4)
    tick(worker, gateway, 3)
    pass_tags(game)
    assert not ankou.get(state(game), ankou.Task, task.id).completed_event
    answer(
        game,
        PLAYER,
        "mockingbird_sex_select",
        options=("starry",),
        fields={"capability": "words"},
    )
    assert game.inspect(PLAYER, action)["state"] == "complete"
    actual = state(game)
    # Printed Bond overflow: the existing Intense relationship gives both +2 Heat.
    assert actual.sheets["2"].heat == before.sheets["2"].heat - 1 + 2
    assert actual.sheets["3"].heat == before.sheets["3"].heat + 2
    assert starry_capabilities(actual, current_ref(actual, 2), target) == ("words",)
    assert any(x.label == "Starry-Eyed" for x in actual.sheets["3"].tags)
    assert next(x for x in actual.mockingbird.triggers if x.id == trigger.id).state == "complete"
    assert ankou.get(actual, ankou.Task, task.id).completed_event
    with ledger.engine.connect() as c:
        assert prove(game, c, actual, rules.records(actual)[-1].id).completed_event
    assert (
        game.roll(PLAYER, str(uuid4()), action)["receipt"]
        == game.inspect(PLAYER, action)["receipt"]
    )
    assert game.dice.calls == 1
    tick(worker, gateway, 5)
    asyncio.run(SourcePauseWorker(game).tick(gateway))
    with ledger.engine.connect() as c:
        assert projection(game, c, task.id)["state"] == "closed"
