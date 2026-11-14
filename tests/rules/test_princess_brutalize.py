"""One real Princess directive preserves Alpha resources and independent Brutalize responses."""

import asyncio
import json
from uuid import uuid4

import pytest
import sqlalchemy as sa
from m3_policy_scenario import configure_m3_fixture
from test_creation import selected
from test_creation_review import ready as creation_ready
from test_enforcer_requisitions import approved
from test_intracadre_marriage import FOUR, third_draft
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Dice, Gateway, answer, state, tick
from test_mission_ui import current
from test_physical_operations import place
from test_princess_oldgen_advice import pass_directed
from test_princess_sex import _directed_native, _prepare_directed_native, roll
from test_world import initial

from girlframe.database import tables as t
from girlframe.delivery.m2_worker import GameWorker
from girlframe.discord_adapter.m2_forms import NativeForm
from girlframe.discord_adapter.m3_alpha import open_alpha_choice
from girlframe.engine import m3_alpha as alpha
from girlframe.engine import m3_princess_sex as princess
from girlframe.engine.m2 import ChoiceAnswer, PlayInput, ReleaseApproval
from girlframe.engine.m2_registry import registry_digest
from girlframe.engine.m3_actor_bonds import current_ref, is_helpless
from girlframe.services.creation_review import CreationReviewService
from girlframe.services.inbox import InboxService
from girlframe.services.m2_game import GameService
from girlframe.services.m3_princess_sex import SexService
from girlframe.services.onboarding import WorkflowError


def ready(store, tmp_path, monkeypatch):
    review, creation, _ = creation_ready(
        store, girl="PRINCESS", frame="THE ENFORCER", other_girl="ALPHA"
    )
    draft = creation.get(OTHER)
    creation.save(
        OTHER,
        str(uuid4()),
        draft.revision,
        store.draft(OTHER)["revision"],
        selected("ALPHA", "JANUS-B").model_copy(
            update={"shared_tokens": draft.draft.shared_tokens}
        ),
    )
    other_review = CreationReviewService(store)
    incoming = next(x for x in other_review.get(OTHER).sheet.bonds if not x.outgoing)
    draft = creation.get(OTHER)
    other_review.select_bond(
        OTHER,
        str(uuid4()),
        draft.revision,
        store.draft(OTHER)["revision"],
        draft.draft,
        incoming.id,
    )
    third_draft(store)
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
    game = GameService(store, dice=Dice((6, 6)))
    for viewer in (PLAYER, OTHER, FOUR):
        saved = review.get(viewer)
        assert saved.sheet.ready_for_rules_review, saved.sheet.issues
        review.save(viewer, str(uuid4()), saved.saved_revision, saved.fingerprint)
        game.activate(viewer, str(uuid4()), review.get(viewer).fingerprint)
    configure_m3_fixture(store)
    approved(store, game, tmp_path, monkeypatch, extra=(princess.RULE, alpha.RULE))
    approval = store.policy.m3_approval
    store.policy = store.policy.model_copy(
        update={
            "m3_approval": approval.model_copy(
                update={"subsystems": approval.subsystems | {"world"}}
            )
        }
    )
    with store.transaction() as connection:
        actual = state(game)
        actual.world = initial()
        for owner in (2, 3, 4):
            actual = place(actual, owner, mode="outside_frame")
        actual.sheets["3"].heat = 3
        game.event(
            connection, 1, str(uuid4()), "synthetic.original_brutalize_bodies_and_resources", actual
        )
    game.bind_scene(ADMIN, str(uuid4()), 900)
    for viewer in (PLAYER, OTHER, FOUR, ADMIN):
        game.join_scene(viewer, str(uuid4()), 900)
    gateway = Gateway()

    async def actor(identity):
        return {1: ADMIN, 2: PLAYER, 3: OTHER, 4: FOUR}[identity]

    gateway.actor = actor
    return game, GameWorker(game), gateway, SexService(game)


def direct(game, worker, gateway, service, faces):
    identity, parent = roll(game, worker, gateway, service, (6, 6), native=True)
    pass_directed(game)
    target = current_ref(state(game), 4)
    direction = _directed_native(game, identity, "brutalize", target=target)
    original = state(game)
    game.dice = Dice(faces)
    child = _prepare_directed_native(game, service, identity, heat=("1",), gain=("0",), identity=())
    assert child is not None
    tick(worker, gateway, 3)
    pass_directed(game)
    with game.store.engine.connect() as connection:
        actual = game.action(connection, child)
        assert actual["actor_id"] == "3" and actual["parent_id"] == parent
        assert actual["data"]["alpha"]["target"] == target.model_dump(mode="json")
        assert actual["data"]["alpha"]["actor_controller"] == 3
        assert actual["data"]["alpha"]["target_controller"] == 4
        assert actual["data"]["princess_child"]["author"] == 2
    assert state(game).sheets["3"].heat == original.sheets["3"].heat - 1
    assert state(game).sheets["2"].heat == original.sheets["2"].heat
    return identity, parent, direction.id, child


def native_damage(game, asset):
    async def run():
        row = next(x for x in game.choices(PLAYER) if x["kind"] == "alpha_damage")
        opened = current(2, int(uuid4().int % 1000000000))
        await opened.response.defer(ephemeral=True)
        await open_alpha_choice(opened, game, row["id"])
        form = opened.edit_original_response.call_args.kwargs["view"]
        assert isinstance(form, NativeForm)
        form.values["asset"] = (asset,)
        submitted = current(2, int(uuid4().int % 1000000000))
        await form.confirm.callback(submitted)
        assert form.completed, submitted.edit_original_response.call_args_list

    asyncio.run(run())


def test_native_princess_directed_brutalize_mid_uses_alpha_resources_and_real_broken(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, service = ready(ledger, tmp_path, monkeypatch)
    identity, parent, direction_id, child = direct(game, worker, gateway, service, (4, 4))
    row = next(x for x in game.choices(PLAYER) if x["kind"] == "alpha_damage")
    assert row["actor_id"] == "3"
    assert any(x.identity == row["id"] for x in InboxService(ledger).items(PLAYER))
    assert not any(x["id"] == row["id"] for x in game.choices(OTHER))
    asset = next(x for x in state(game).sheets["4"].assets if x.family == "girl" and not x.damaged)
    with pytest.raises(WorkflowError):
        game.respond(
            OTHER, str(uuid4()), row["id"], row["revision"], ChoiceAnswer(options=(asset.id,))
        )
    native_damage(game, asset.id)
    actual = state(game)
    assert next(x for x in actual.sheets["4"].assets if x.id == asset.id).damaged
    assert alpha.conditions(actual, current_ref(actual, 4), current_ref(actual, 3))
    assert not alpha.conditions(actual, current_ref(actual, 4), current_ref(actual, 2))
    assert not is_helpless(actual, current_ref(actual, 4), current_ref(actual, 3))
    assert game.inspect(PLAYER, child)["state"] == "complete"
    assert game.inspect(PLAYER, parent)["state"] == "complete"
    assert service.view(PLAYER, identity)["phase"] == "complete"
    event = princess.direction(actual, direction_id).completed_event
    with ledger.engine.connect() as connection:
        audit = (
            connection.execute(sa.select(t.events).where(t.events.c.id == event)).mappings().one()
        )
        assert audit["kind"] == "m3.princess_directed_brutalize_completed"
        assert audit["actor_id"] == "2"
    receipt = game.inspect(PLAYER, child)["receipt"]
    assert game.roll(PLAYER, str(uuid4()), child)["receipt"] == receipt
    assert game.dice.calls == 1
    tick(worker, gateway, 8)
    assert "PRIVATE_ACTUAL" not in json.dumps(gateway.messages)


def test_native_princess_directed_brutalize_high_preserves_helpless_original_target(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, service = ready(ledger, tmp_path, monkeypatch)
    identity, parent, _, child = direct(game, worker, gateway, service, (6, 6))
    asset = next(x for x in state(game).sheets["4"].assets if x.family == "girl" and not x.damaged)
    native_damage(game, asset.id)
    actual = state(game)
    assert is_helpless(actual, current_ref(actual, 4), current_ref(actual, 3))
    assert not is_helpless(actual, current_ref(actual, 4), current_ref(actual, 2))
    assert not alpha.conditions(actual, current_ref(actual, 4), current_ref(actual, 3))
    assert game.inspect(PLAYER, child)["state"] == "complete"
    assert game.inspect(PLAYER, parent)["state"] == "complete"
    assert service.view(PLAYER, identity)["phase"] == "complete"


def test_native_princess_directed_brutalize_low_waits_for_targets_actual_counter(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, service = ready(ledger, tmp_path, monkeypatch)
    identity, parent, direction_id, child = direct(game, worker, gateway, service, (1, 1))
    row = next(x for x in game.choices(FOUR) if x["kind"] == "alpha_low")
    assert not any(x["id"] == row["id"] for x in game.choices(PLAYER))
    with pytest.raises(WorkflowError):
        game.respond(
            PLAYER, str(uuid4()), row["id"], row["revision"], ChoiceAnswer(options=("pass",))
        )
    answer(game, FOUR, "alpha_low", options=("counter_broken",))
    assert game.inspect(PLAYER, child)["state"] != "complete"
    assert game.inspect(PLAYER, parent)["state"] != "complete"
    assert princess.direction(state(game), direction_id).completed_event is None
    game.dice.faces = (2, 3)
    counter = game.begin(
        FOUR,
        str(uuid4()),
        900,
        state(game).sheets["4"].revision,
        PlayInput(
            play="keep_your_head",
            parent=child,
            heat=0,
            context="I actually keep composed against this real Alpha's directed pressure",
            trigger_confirmed=True,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    pass_directed(game)
    answer(game, FOUR, "actor_keep", options=("sexy",))
    assert game.inspect(PLAYER, parent)["state"] != "complete"
    answer(game, ADMIN, "handler_keep", flag=True, text="The original counter's factual outcome")
    actual = state(game)
    assert game.inspect(FOUR, counter)["state"] == "complete"
    assert game.inspect(PLAYER, child)["state"] == "complete"
    assert game.inspect(PLAYER, parent)["state"] == "complete"
    assert service.view(PLAYER, identity)["phase"] == "complete"
    assert alpha.conditions(actual, current_ref(actual, 3), current_ref(actual, 4))
    assert not alpha.conditions(actual, current_ref(actual, 2), current_ref(actual, 4))
    with ledger.engine.connect() as connection:
        event = princess.direction(actual, direction_id).completed_event
        audit = (
            connection.execute(sa.select(t.events).where(t.events.c.id == event)).mappings().one()
        )
        assert audit["kind"] == "m3.princess_directed_brutalize_completed"
        trigger = (
            connection.execute(
                sa.select(t.events).where(
                    t.events.c.id == json.loads(audit["payload_json"])["trigger_event"]
                )
            )
            .mappings()
            .one()
        )
        assert trigger["kind"] == "m3.alpha_counter_completed"
        assert json.loads(trigger["payload_json"])["child"] == counter
    assert game.dice.calls == 2
