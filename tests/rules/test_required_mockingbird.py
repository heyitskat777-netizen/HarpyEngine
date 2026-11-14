"""Native required conversation normal; authored for root, no worker pytest."""

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
from girlframe.engine.m3_mockingbird_state import PERSON
from girlframe.services.m3_ankou import AnkouService
from girlframe.services.m3_recovery import RecoveryService
from girlframe.services.m3_required_plays import MOCK_RULE, RequiredPlayService, prove
from girlframe.services.onboarding import WorkflowError
from girlframe.services.p1_source_pause import projection

ledger = ledger_fixture


def test_native_mockingbird_nomination_actual_conversation_cancel_retry_capabilities_and_restore(
    ledger, tmp_path, monkeypatch
):
    _, game = service(ledger, girl="MOCKINGBIRD", frame=ankou.FRAME)
    approved(ledger, game, tmp_path, monkeypatch, extra=(ankou.RELAY, MOCK_RULE))
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
    assert PERSON in controls.view(OTHER, nomination.id)["nomination_options"]
    controls.choose_task(
        OTHER,
        str(uuid4()),
        state(game).revision,
        nomination.id,
        PERSON,
        "I nominate her ordinary conversation Play",
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
        play=(PERSON,),
        targets=(current_ref(state(game), 3).token,),
        primary=(),
        account="PRIVATE_ACTUAL_NOMINATED_CONVERSATION",
    )
    trigger = state(game).mockingbird.triggers[-1]
    assert trigger.state == "ready" and trigger.action is None
    assert all(x.event is None and x.decision == "pending" for x in trigger.parties)
    # Conversation declaration is not Sex consent and requires no fabricated attestation.
    native(lambda i: open_required(i, game, task.id), operation=("link:" + trigger.id,))

    # Requests -> Withdraw remains legitimate after linking, before preparation.
    # It retires only the recipe reservation; the original performance stays owed.
    from girlframe.services.m3_mockingbird_plays import MockingbirdService

    source = MockingbirdService(game)
    old_link = rules.records(state(game))[-1]
    with pytest.raises(WorkflowError):
        source.withdraw(OTHER, str(uuid4()), trigger.id)
    before_withdraw = state(game)
    withdraw_key = str(uuid4())
    withdrawn = source.withdraw(PLAYER, withdraw_key, trigger.id)
    assert source.withdraw(PLAYER, withdraw_key, trigger.id) == withdrawn
    actual = state(game)
    retired = rules.get(actual, old_link.id)
    assert retired.retired_event == retired.withdrawn_event
    assert retired.withdrawn_event and not retired.releases
    assert not ankou.get(actual, ankou.Task, task.id).completed_event
    assert required.menu(PLAYER, task.id)["link"] is None
    assert actual.sheets["2"].heat == before_withdraw.sheets["2"].heat
    assert game.dice.calls == 0
    with ledger.engine.connect() as c:
        prove(game, c, actual, old_link.id)
        assert projection(game, c, task.id)["state"] == "held"
        forged = actual.model_copy(deep=True)
        rules.put(
            forged,
            retired.model_copy(
                update={"withdrawn_event": old_link.event, "retired_event": old_link.event}
            ),
        )
        with pytest.raises(WorkflowError):
            prove(game, c, forged, old_link.id)
    declaration = native(
        lambda i: open_required(i, game, task.id), operation=("invite_mockingbird",)
    )
    submit(
        declaration,
        play=(PERSON,),
        targets=(current_ref(state(game), 3).token,),
        primary=(),
        account="PRIVATE_FRESH_NOMINATED_CONVERSATION_AFTER_WITHDRAWAL",
    )
    replacement = state(game).mockingbird.triggers[-1]
    assert replacement.id != trigger.id
    trigger = replacement
    native(lambda i: open_required(i, game, task.id), operation=("link:" + trigger.id,))

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
        "mockingbird_person_capabilities",
        options=("words", "sentences", "eye_contact"),
    )
    assert game.inspect(PLAYER, action)["state"] == "complete"
    actual = state(game)
    assert actual.sheets["2"].heat == before.sheets["2"].heat - 1
    assert actual.mockingbird.conversations[-1].action == action
    assert set(actual.mockingbird.conversations[-1].allowed) == {
        "words",
        "sentences",
        "eye_contact",
    }
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
