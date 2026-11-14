"""Native Alpha counters keep actual costs, owned results and original parent proof."""

import asyncio
import json
from uuid import uuid4

import pytest
import sqlalchemy as sa
from m3_policy_scenario import configure_m3_fixture
from test_creation import selected
from test_creation_review import ready as creation_ready
from test_enforcer_requisitions import approved
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Dice, Gateway, answer, pass_tags, state, tick
from test_mission_ui import current
from test_physical_operations import place
from test_world import initial

from girlframe.database import tables as t
from girlframe.delivery.m2_worker import GameWorker
from girlframe.discord_adapter.m3_alpha import open_alpha_choice
from girlframe.engine.m2 import ChoiceAnswer, PlayInput, ReleaseApproval
from girlframe.engine.m2_registry import registry_digest
from girlframe.engine.m3_actor_bonds import current_ref, is_helpless
from girlframe.engine.m3_alpha import RULE, conditions
from girlframe.services.inbox import InboxService
from girlframe.services.m2_game import GameService
from girlframe.services.m3_alpha import brutalize_counter, counter_plays
from girlframe.services.onboarding import WorkflowError


def ready(store, tmp_path, monkeypatch):
    review, creation, _ = creation_ready(
        store, girl="ALPHA", frame="THE ENFORCER", other_girl="ALPHA"
    )
    own = creation.get(OTHER)
    draft = selected("ALPHA", "JANUS-B").model_copy(
        update={"shared_tokens": own.draft.shared_tokens}
    )
    creation.save(OTHER, str(uuid4()), own.revision, store.draft(OTHER)["revision"], draft)
    incoming = next(x for x in review.get(OTHER).sheet.bonds if not x.outgoing)
    own = creation.get(OTHER)
    review.select_bond(
        OTHER, str(uuid4()), own.revision, store.draft(OTHER)["revision"], own.draft, incoming.id
    )
    store.policy = store.policy.model_copy(
        update={
            "owner_intense_tag_bonus": 2,
            "m2_approval": ReleaseApproval(
                registry_sha256=registry_digest(),
                reviewer="synthetic fixture only",
                reference="Not independent certification",
            ),
        }
    )
    game = GameService(store, dice=Dice((1, 1)))
    for viewer in (PLAYER, OTHER):
        saved = review.get(viewer)
        assert saved.sheet.ready_for_rules_review, saved.sheet.issues
        review.save(viewer, str(uuid4()), saved.saved_revision, saved.fingerprint)
        game.activate(viewer, str(uuid4()), review.get(viewer).fingerprint)
    configure_m3_fixture(store)
    approved(store, game, tmp_path, monkeypatch, extra=(RULE,))
    with store.transaction() as c:
        actual = state(game)
        actual.world = initial()
        actual = place(actual, 2, mode="outside_frame")
        actual = place(actual, 3, mode="outside_frame")
        actual.sheets["3"].heat = 3
        game.event(c, 1, str(uuid4()), "synthetic.native_alpha_counter_bodies", actual)
    game.bind_scene(ADMIN, str(uuid4()), 900)
    for viewer in (PLAYER, OTHER, ADMIN):
        game.join_scene(viewer, str(uuid4()), 900)
    return game, GameWorker(game), Gateway()


def opportunity(ledger, tmp_path, monkeypatch, *, retaliate=True):
    game, worker, gateway = ready(ledger, tmp_path, monkeypatch)
    original = state(game)
    target = current_ref(original, 3)
    parent = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        original.sheets["2"].revision,
        PlayInput(
            play="brutalize",
            target_actor=target,
            heat=0,
            context="PRIVATE_ALPHA_COUNTER The first Alpha tears into the second",
            trigger_confirmed=True,
        ),
    )["action_id"]
    tick(worker, gateway, 4)
    pass_tags(game)
    receipt = game.inspect(PLAYER, parent)["receipt"]
    answer(game, OTHER, "alpha_low", options=("counter_broken" if retaliate else "counter_only",))
    choice = next(x for x in game.choices(OTHER) if x["kind"] == "alpha_counter_play")
    assert any(x.identity == choice["id"] for x in InboxService(ledger).items(OTHER))
    return game, worker, gateway, parent, receipt, choice


def interaction(owner=3):
    value = current(owner, uuid4().int % 1000000000)
    value.channel_id = 900
    return value


def begin_counter(game, worker, gateway, parent, choice, faces):
    before, calls = state(game), game.dice.calls
    actor, target = current_ref(before, 3), current_ref(before, 2)
    prepared = PlayInput(
        play="brutalize",
        parent=parent,
        target_actor=target,
        heat=1,
        context="PRIVATE_COUNTER_REPLY I turn on the original attacker with fists and teeth",
        trigger_confirmed=True,
    )
    with game.store.engine.connect() as c:
        assert "brutalize" in counter_plays(game, c, before, game.action(c, parent), actor)
        with pytest.raises(WorkflowError):
            brutalize_counter(game, c, before, target, prepared, 900)
        with pytest.raises(WorkflowError):
            brutalize_counter(
                game, c, before, actor, prepared.model_copy(update={"target_actor": actor}), 900
            )
    assert state(game) == before and game.dice.calls == calls

    async def native():
        opened = interaction()
        await opened.response.defer(ephemeral=True)
        await open_alpha_choice(opened, game, choice["id"])
        form = opened.edit_original_response.call_args.kwargs["view"]
        assert form.values["gain"] == ("0",)
        assert "brutalize" in dict(next(x for x in form.fields if x.key == "play").options)
        assert not await form.interaction_check(interaction(2))
        form.values.update(play=("brutalize",), heat=("1",), context=prepared.context)
        submitted = interaction()
        await form.confirm.callback(submitted)
        assert form.completed, submitted.edit_original_response.call_args_list
        saved = state(game)
        await form.confirm.callback(submitted)
        assert state(game) == saved

    asyncio.run(native())
    with game.store.engine.connect() as c:
        actions = t.m2["m2_actions"]
        child = game.action(
            c,
            c.scalar(
                sa.select(actions.c.id).where(
                    actions.c.campaign_id == game.store.campaign_id,
                    actions.c.parent_id == parent,
                    actions.c.actor_id == "3",
                )
            ),
        )
        assert child["data"]["alpha_counter_source"]["choice"] == choice["id"]
        assert child["data"]["alpha"]["actor"] == actor.model_dump(mode="json")
        assert child["data"]["alpha"]["target"] == target.model_dump(mode="json")
        assert child["data"]["prepared"]["source_work"] is None
        assert child["data"]["prepared"]["identity"] is None
        assert child["data"]["prepared"]["gain"] == 0
    assert state(game).sheets["3"].heat == before.sheets["3"].heat
    assert game.dice.calls == calls
    game.dice.faces = faces
    tick(worker, gateway, 4)
    pass_tags(game)
    assert state(game).sheets["3"].heat == before.sheets["3"].heat - 1
    assert state(game).sheets["2"].heat == before.sheets["2"].heat
    assert game.dice.calls == calls + 1
    assert game.inspect(PLAYER, parent)["state"] != "complete"
    return child["id"]


def test_native_alpha_brutalize_counter_spends_once_and_waits_for_actual_mid_damage(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, parent, receipt, choice = opportunity(ledger, tmp_path, monkeypatch)
    child = begin_counter(game, worker, gateway, parent, choice, (3, 4))
    before = state(game)
    actor, target = current_ref(before, 3), current_ref(before, 2)
    assert not conditions(before, target, actor)
    selected = next(x for x in before.sheets["2"].assets if x.family == "girl" and not x.damaged)
    owed = next(x for x in game.choices(OTHER) if x["kind"] == "alpha_damage")
    with pytest.raises(WorkflowError):
        game.respond(
            PLAYER, str(uuid4()), owed["id"], owed["revision"], ChoiceAnswer(options=(selected.id,))
        )
    answer(game, OTHER, "alpha_damage", options=(selected.id,))
    actual = state(game)
    assert next(x for x in actual.sheets["2"].assets if x.id == selected.id).damaged
    assert len(conditions(actual, target, actor)) == 1
    assert not is_helpless(actual, target, actor)
    assert game.inspect(OTHER, child)["state"] == "complete"
    assert game.inspect(PLAYER, parent)["state"] == "complete"
    assert game.inspect(PLAYER, parent)["receipt"] == receipt
    with ledger.engine.connect() as c:
        assert game.action(c, child)["data"]["alpha_counter_completed"]
        assert game.action(c, parent)["data"]["alpha"]["counter_child"] == child
        events = list(c.scalars(sa.select(t.events.c.payload_json)))
        assert "PRIVATE_COUNTER_REPLY" not in str(events)
    calls, heat = game.dice.calls, actual.sheets["3"].heat
    own_receipt = game.inspect(OTHER, child)["receipt"]
    restarted = GameService(ledger, dice=game.dice)
    assert restarted.roll(OTHER, str(uuid4()), child)["receipt"] == own_receipt
    assert game.dice.calls == calls == 2 and state(game).sheets["3"].heat == heat
    tick(worker, gateway, 8)
    assert "PRIVATE_COUNTER_REPLY" not in json.dumps(gateway.messages)


def test_native_alpha_brutalize_counter_high_keeps_helpless_and_optional_broken_separate(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, parent, _, choice = opportunity(
        ledger, tmp_path, monkeypatch, retaliate=False
    )
    child = begin_counter(game, worker, gateway, parent, choice, (6, 6))
    before = state(game)
    selected = next(x for x in before.sheets["2"].assets if x.family == "girl" and not x.damaged)
    answer(game, OTHER, "alpha_damage", options=(selected.id,))
    actual = state(game)
    actor, target = current_ref(actual, 3), current_ref(actual, 2)
    assert is_helpless(actual, target, actor) and not conditions(actual, target, actor)
    assert next(x for x in actual.sheets["2"].assets if x.id == selected.id).damaged
    assert (
        game.inspect(OTHER, child)["state"] == game.inspect(PLAYER, parent)["state"] == "complete"
    )


def test_native_alpha_brutalize_counter_low_preserves_original_attacker_owned_opportunity(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, parent, _, choice = opportunity(ledger, tmp_path, monkeypatch)
    child = begin_counter(game, worker, gateway, parent, choice, (1, 1))
    owed = next(x for x in game.choices(PLAYER) if x["kind"] == "alpha_low")
    with pytest.raises(WorkflowError):
        game.respond(
            OTHER, str(uuid4()), owed["id"], owed["revision"], ChoiceAnswer(options=("pass",))
        )
    before = state(game)
    actor, target = current_ref(before, 3), current_ref(before, 2)
    assert not conditions(before, target, actor)
    answer(game, PLAYER, "alpha_low", options=("pass",))
    actual = state(game)
    assert conditions(actual, target, actor)
    assert not is_helpless(actual, target, actor)
    assert actual.sheets["2"].assets == before.sheets["2"].assets
    assert (
        game.inspect(OTHER, child)["state"] == game.inspect(PLAYER, parent)["state"] == "complete"
    )
