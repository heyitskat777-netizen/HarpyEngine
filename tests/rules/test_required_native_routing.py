"""Existing Stim/Princess providers are reached from the real Ankou task entry."""

import asyncio
import json
from uuid import uuid4

import pytest
from test_enforcer_requisitions import approved
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Gateway, state
from test_mission_service import service
from test_physical_operations import place
from test_required_plays import native, submit
from test_world import initial

from girlframe.delivery.p1_source_pause_worker import SourcePauseWorker
from girlframe.discord_adapter.m3_ankou import open_ankou
from girlframe.engine import m3_ankou as ankou
from girlframe.engine import m3_princess_sex as princess
from girlframe.engine import m3_stim_sex as stim
from girlframe.engine.m3_actor_bonds import current_ref, set_depth
from girlframe.services.m3_ankou import AnkouService
from girlframe.services.m3_required_plays import RequiredPlayService
from girlframe.services.onboarding import WorkflowError
from girlframe.services.p1_source_pause import projection


@pytest.mark.parametrize(
    ("girl", "play", "rule", "invite", "field"),
    (
        ("PRINCESS", princess.PLAY, princess.RULE, "invite_princess", "action"),
        ("STIM-BLISSED", stim.PLAY, stim.RULE, "invite_stim", "source"),
    ),
)
def test_ankou_task_opens_existing_required_recipe_without_performing_or_consenting(
    ledger, tmp_path, monkeypatch, girl, play, rule, invite, field
):
    _, game = service(ledger, girl=girl, frame=ankou.FRAME)
    approved(ledger, game, tmp_path, monkeypatch, extra=(ankou.RELAY, rule))
    with ledger.transaction() as c:
        actual = state(game)
        actual.world = initial()
        actual = place(place(actual, 2, mode="outside_frame"), 3, mode="outside_frame")
        event = str(uuid4())
        actual = set_depth(actual, current_ref(actual, 2), current_ref(actual, 3), 2, event)
        game.event(c, 1, event, "synthetic.original_native_ankou_nomination_context", actual)
    controls = AnkouService(game)
    required = RequiredPlayService(game)
    gateway = Gateway()
    relay = controls.activate_relay(
        PLAYER, str(uuid4()), 900, state(game).revision, ("speech", "touch"), "Actual relay"
    )["id"]
    controls.choose_consequence(
        ADMIN, str(uuid4()), state(game).revision, relay, "nominees", "Original consequence"
    )
    nomination = next(
        x
        for x in ankou.records(state(game), ankou.Task)
        if x.source == relay and x.kind == "nominate"
    )
    controls.choose_task(
        OTHER,
        str(uuid4()),
        state(game).revision,
        nomination.id,
        play,
        "Nominate the existing native source without supplying anyone's consent",
    )
    task = next(
        x
        for x in ankou.records(state(game), ankou.Task)
        if x.source == relay and x.kind == "perform"
    )
    asyncio.run(SourcePauseWorker(game).tick(gateway))
    before = state(game)
    calls = game.dice.calls
    with ledger.engine.connect() as c:
        assert projection(game, c, task.id)["state"] == "held"
    with pytest.raises(WorkflowError):
        required.menu(OTHER, task.id)
    # Enter through the original durable Ankou task, not directly into its recipe pane.
    entry = native(lambda i: open_ankou(i, controls, task.id), operation=("child",))
    assert entry.title == "Nominated own-source performance"
    assert state(game) == before and game.dice.calls == calls
    source = submit(entry, operation=(invite,))
    invitation = submit(source, **{field: ("invite",)})
    submit(
        invitation,
        target=(current_ref(state(game), 3).token,),
        account="PRIVATE_NATIVE_ROUTING actual voluntary proposal",
    )
    actual = state(game)
    recipe = (
        princess.sessions(actual)[-1]
        if play == princess.PLAY
        else stim.records(actual, stim.Session)[-1]
    )
    assert recipe.actor == task.actor and recipe.cast == task.cast
    assert recipe.target == current_ref(before, OTHER.user_id)
    assert recipe.phase == "invited" and recipe.consent_event is None and recipe.action is None
    assert not required.menu(PLAYER, task.id)["accepted"]
    with pytest.raises(WorkflowError):
        required.link(PLAYER, str(uuid4()), task.id, recipe.id, actual.revision)
    assert state(game) == actual
    assert game.dice.calls == calls
    assert actual.sheets["2"].heat == before.sheets["2"].heat
    assert ankou.get(actual, ankou.Task, task.id) == task
    with ledger.engine.connect() as c:
        assert not game.pending_actions(c)
        assert projection(game, c, task.id)["state"] == "held"
    assert "PRIVATE_NATIVE_ROUTING" not in json.dumps(gateway.messages)
