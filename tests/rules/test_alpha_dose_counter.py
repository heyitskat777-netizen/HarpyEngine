"""Actual native Stim counter keeps her Heat, cocktail choosers and timed Tags."""

import asyncio
import json
from uuid import uuid4

import pytest
import sqlalchemy as sa
from m3_policy_scenario import configure_m3_fixture
from test_creation import selected
from test_creation_review import ready as creation_ready
from test_dose_up import native_choice
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
from girlframe.engine import m3_alpha as alpha
from girlframe.engine import m3_dose_up as dose
from girlframe.engine.m2 import ChoiceAnswer, PlayInput, ReleaseApproval
from girlframe.engine.m2_registry import registry_digest
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.services.inbox import InboxService
from girlframe.services.m2_game import GameService
from girlframe.services.m3_alpha import counter_plays, self_dose_counter
from girlframe.services.m3_dose_up import DoseUpService, prove
from girlframe.services.onboarding import WorkflowError


def ready(store, tmp_path, monkeypatch):
    review, creation, _ = creation_ready(
        store, girl="ALPHA", frame="THE ENFORCER", other_girl="STIM-BLISSED"
    )
    own = creation.get(OTHER)
    draft = selected("STIM-BLISSED", "JANUS-B").model_copy(
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
    approved(store, game, tmp_path, monkeypatch, extra=(alpha.RULE, dose.RULE, dose.SELF_RULE))
    with store.transaction() as c:
        actual = state(game)
        actual.world = initial()
        actual = place(actual, 2, mode="outside_frame")
        actual = place(actual, 3, mode="outside_frame")
        actual.sheets["3"].heat = 3
        game.event(c, 1, str(uuid4()), "synthetic.native_alpha_dose_counter_bodies", actual)
    game.bind_scene(ADMIN, str(uuid4()), 900)
    for viewer in (PLAYER, OTHER, ADMIN):
        game.join_scene(viewer, str(uuid4()), 900)
    return game, GameWorker(game), Gateway()


def interaction(owner=3):
    value = current(owner, uuid4().int % 1000000000)
    value.channel_id = 900
    return value


def opportunity(store, tmp_path, monkeypatch, faces, *, retaliate=True):
    game, worker, gateway = ready(store, tmp_path, monkeypatch)
    original = state(game)
    actor, attacker = current_ref(original, 3), current_ref(original, 2)
    parent = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        original.sheets["2"].revision,
        PlayInput(
            play="brutalize",
            target_actor=actor,
            heat=0,
            context="PRIVATE_ALPHA_DOSE The Alpha tears into the original Stim",
            trigger_confirmed=True,
        ),
    )["action_id"]
    tick(worker, gateway, 4)
    pass_tags(game)
    receipt = game.inspect(PLAYER, parent)["receipt"]
    answer(game, OTHER, "alpha_low", options=("counter_broken" if retaliate else "counter_only",))
    choice = next(x for x in game.choices(OTHER) if x["kind"] == "alpha_counter_play")
    assert any(x.identity == choice["id"] for x in InboxService(store).items(OTHER))
    before, calls = state(game), game.dice.calls
    prepared = PlayInput(
        play=dose.PLAY,
        parent=parent,
        heat=1,
        context="PRIVATE_COUNTER_COCKTAIL I inject myself and stand up to the Alpha",
        trigger_confirmed=True,
    )
    with store.engine.connect() as c:
        assert dose.PLAY in counter_plays(game, c, before, game.action(c, parent), actor)
        with pytest.raises(WorkflowError):
            self_dose_counter(game, c, before, attacker, prepared, 900)
        with pytest.raises(WorkflowError):
            self_dose_counter(
                game, c, before, actor, prepared.model_copy(update={"target_actor": attacker}), 900
            )
    assert state(game) == before and game.dice.calls == calls

    async def native():
        opened = interaction()
        await opened.response.defer(ephemeral=True)
        await open_alpha_choice(opened, game, choice["id"])
        form = opened.edit_original_response.call_args.kwargs["view"]
        assert dose.PLAY in dict(next(x for x in form.fields if x.key == "play").options)
        assert not await form.interaction_check(interaction(2))
        form.values.update(play=(dose.PLAY,), heat=("1",), context=prepared.context)
        submitted = interaction()
        await form.confirm.callback(submitted)
        assert form.completed, submitted.edit_original_response.call_args_list
        saved = state(game)
        await form.confirm.callback(submitted)
        assert state(game) == saved

    asyncio.run(native())
    with store.engine.connect() as c:
        actions = t.m2["m2_actions"]
        child = game.action(
            c,
            c.scalar(
                sa.select(actions.c.id).where(
                    actions.c.campaign_id == store.campaign_id,
                    actions.c.parent_id == parent,
                    actions.c.actor_id == "3",
                )
            ),
        )
        assert child["data"]["alpha_counter_source"]["choice"] == choice["id"]
        assert child["data"]["dose_up"]["actor"] == actor.model_dump(mode="json")
        assert child["data"]["dose_up"]["target"] == actor.model_dump(mode="json")
        assert child["data"]["prepared"]["source_work"] is None
    assert state(game).sheets["3"].heat == before.sheets["3"].heat
    assert game.dice.calls == calls
    game.dice.faces = faces
    tick(worker, gateway, 4)
    pass_tags(game)
    assert state(game).sheets["3"].heat == before.sheets["3"].heat - 1
    assert state(game).sheets["2"].heat == before.sheets["2"].heat
    assert game.dice.calls == calls + 1
    assert not alpha.conditions(state(game), attacker, actor)
    assert game.inspect(PLAYER, parent)["state"] != "complete"
    return game, worker, gateway, parent, receipt, child["id"]


def completed(game, parent, receipt, child, components, *, retaliate=True):
    actual = state(game)
    actor, attacker = current_ref(actual, 3), current_ref(actual, 2)
    assert game.inspect(OTHER, child)["state"] == "complete"
    assert game.inspect(PLAYER, parent)["state"] == "complete"
    assert game.inspect(PLAYER, parent)["receipt"] == receipt
    assert bool(alpha.conditions(actual, attacker, actor)) is retaliate
    assert {x.component for x in dose.drug_tags(actual, actor)} == set(components)
    assert not dose.drug_tags(actual, attacker)
    with game.store.engine.connect() as c:
        value = prove(game, c, actual, child)
        assert value.actor == value.target == actor and value.heat == 1
        assert value.contact is None and value.order is None and value.punishment is None
        assert game.action(c, child)["data"]["alpha_counter_completed"]
        assert game.action(c, parent)["data"]["alpha"]["counter_child"] == child
        assert "PRIVATE_COUNTER_COCKTAIL" not in str(
            list(c.scalars(sa.select(t.events.c.payload_json)))
        )
    calls, heat = game.dice.calls, actual.sheets["3"].heat
    own_receipt = game.inspect(OTHER, child)["receipt"]
    restarted = GameService(game.store, dice=game.dice)
    assert restarted.roll(OTHER, str(uuid4()), child)["receipt"] == own_receipt
    assert game.dice.calls == calls == 2 and state(game).sheets["3"].heat == heat
    assert any(
        x.identity == child and x.task == "m3_dose_up"
        for x in InboxService(game.store).items(OTHER)
    )
    assert not any(
        x.identity == child and x.task == "m3_dose_up"
        for x in InboxService(game.store).items(PLAYER)
    )
    return value


def test_native_brutalize_self_dose_high_waits_for_actual_handler_before_broken(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, parent, receipt, child = opportunity(
        ledger, tmp_path, monkeypatch, (6, 6)
    )
    native_choice(game, OTHER, ("quick", "strong"))
    pending = next(x for x in game.choices(ADMIN) if x["kind"] == "dose_up_components")
    assert any(x.identity == pending["id"] for x in InboxService(ledger).items(ADMIN))
    before = state(game)
    assert not dose.drug_tags(before, current_ref(before, 3))
    assert not alpha.conditions(before, current_ref(before, 2), current_ref(before, 3))
    assert game.inspect(PLAYER, parent)["state"] != "complete"
    with pytest.raises(WorkflowError):
        game.respond(
            OTHER, str(uuid4()), pending["id"], pending["revision"], ChoiceAnswer(options=("calm",))
        )
    native_choice(game, ADMIN, ("calm",))
    value = completed(game, parent, receipt, child, ("quick", "strong", "calm"))
    assert [(x.role, x.chooser) for x in value.selections] == [("roller", 3), ("handler", 1)]
    tick(worker, gateway, 8)
    assert "PRIVATE_COUNTER_COCKTAIL" not in json.dumps(gateway.messages)


def test_native_brutalize_self_dose_mid_keeps_two_tags_and_actual_scene_expiry(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, parent, receipt, child = opportunity(
        ledger, tmp_path, monkeypatch, (3, 4), retaliate=False
    )
    native_choice(game, OTHER, ("quick", "strong"))
    value = completed(game, parent, receipt, child, ("quick", "strong"), retaliate=False)
    assert value.total == 8 and [(x.role, x.chooser) for x in value.selections] == [("roller", 3)]
    tick(worker, gateway, 8)
    game.close_scene(ADMIN, str(uuid4()), 900)
    assert not dose.expired(state(game), child)
    game.bind_scene(ADMIN, str(uuid4()), 900)
    for viewer in (PLAYER, OTHER, ADMIN):
        game.join_scene(viewer, str(uuid4()), 900)
    game.close_scene(ADMIN, str(uuid4()), 900)
    assert dose.expired(state(game), child)
    assert not dose.drug_tags(state(game), current_ref(state(game), 3))
    assert DoseUpService(ledger, game).view(OTHER, child)["phase"] == "expired"


def test_native_brutalize_self_dose_low_keeps_actual_handler_one_or_two_choice(
    ledger, tmp_path, monkeypatch
):
    game, _, _, parent, receipt, child = opportunity(ledger, tmp_path, monkeypatch, (1, 1))
    assert not any(x["kind"] == "dose_up_components" for x in game.choices(OTHER))
    pending = next(x for x in game.choices(ADMIN) if x["kind"] == "dose_up_components")
    detail = game.decision(ADMIN, pending["id"])["detail"]
    assert (detail["minimum"], detail["maximum"]) == (1, 2)
    native_choice(game, ADMIN, ("bliss",))
    value = completed(game, parent, receipt, child, ("bliss",))
    assert value.total == 3 and [(x.role, x.chooser) for x in value.selections] == [("handler", 1)]
