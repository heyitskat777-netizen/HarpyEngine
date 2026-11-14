"""Native Vatgrown counter: actual Doll source, independent observer and delayed Broken."""

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
from test_vatgrown import choose
from test_world import initial

from girlframe.database import tables as t
from girlframe.delivery.m2_worker import GameWorker
from girlframe.discord_adapter.m3_alpha import open_alpha_choice
from girlframe.engine import m3_alpha as alpha
from girlframe.engine import m3_vatgrown as doll
from girlframe.engine.creation_details import DesireChoice, GirlDetails, NpcInvestor
from girlframe.engine.m2 import ChoiceAnswer, PlayInput, ReleaseApproval
from girlframe.engine.m2_registry import registry_digest
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.services.creation_coordination import CoordinationService
from girlframe.services.inbox import InboxService
from girlframe.services.m2_game import GameService
from girlframe.services.m3_alpha import counter_plays
from girlframe.services.m3_alpha_doll import counter
from girlframe.services.m3_vatgrown import DollService, prove
from girlframe.services.onboarding import WorkflowError


def ready(store, tmp_path, monkeypatch):
    review, creation, _ = creation_ready(
        store, girl="ALPHA", frame="THE ENFORCER", other_girl="VATGROWN"
    )
    coordinated = CoordinationService(store)
    request = coordinated.propose(
        ADMIN,
        str(uuid4()),
        OTHER.user_id,
        "vatgrown_handler",
        coordinated.prepare(ADMIN, OTHER.user_id, "vatgrown_handler"),
        DesireChoice(slots=(1,)),
    )
    coordinated.decide(OTHER, str(uuid4()), request["id"], 1, "accept")
    own = creation.get(OTHER)
    actual = selected("VATGROWN", "JANUS-B")
    draft = actual.model_copy(
        update={
            "shared_tokens": own.draft.shared_tokens,
            "girl_details": GirlDetails(
                investors=tuple(
                    NpcInvestor(npc_slot=x.slot, desires=DesireChoice(slots=(0,)))
                    for x in actual.npc_bonds
                )
            ),
        }
    )
    creation.save(OTHER, str(uuid4()), own.revision, store.draft(OTHER)["revision"], draft)
    incoming = next(x for x in review.get(OTHER).sheet.bonds if not x.outgoing)
    own = creation.get(OTHER)
    review.select_bond(
        OTHER,
        str(uuid4()),
        own.revision,
        store.draft(OTHER)["revision"],
        own.draft,
        incoming.id,
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
    approved(store, game, tmp_path, monkeypatch, extra=(alpha.RULE, doll.RULE))
    with store.transaction() as c:
        actual = state(game)
        actual.world = initial()
        actual = place(actual, 2, mode="outside_frame")
        actual = place(actual, 3, mode="outside_frame")
        actual.sheets["3"].heat = 3
        game.event(c, 1, str(uuid4()), "synthetic.native_alpha_doll_counter_bodies", actual)
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
            context="PRIVATE_ALPHA_DOLL The Alpha tears into the original Vatgrown",
            trigger_confirmed=True,
        ),
    )["action_id"]
    tick(worker, gateway, 4)
    pass_tags(game)
    receipt = game.inspect(PLAYER, parent)["receipt"]
    answer(
        game,
        OTHER,
        "alpha_low",
        options=("counter_broken" if retaliate else "counter_only",),
    )
    choice = next(x for x in game.choices(OTHER) if x["kind"] == "alpha_counter_play")
    assert any(x.identity == choice["id"] for x in InboxService(store).items(OTHER))
    before, calls = state(game), game.dice.calls
    prepared = PlayInput(
        play=doll.PLAY,
        target_actor=attacker,
        parent=parent,
        heat=1,
        context="PRIVATE_COUNTER_DOLL I fall quiet and fade into the background",
        trigger_confirmed=True,
    )
    preview_snapshot = before.model_copy(deep=True)
    with store.engine.connect() as c:
        assert doll.PLAY in counter_plays(game, c, before, game.action(c, parent), actor)
        with pytest.raises(WorkflowError):
            counter(game, c, before, attacker, prepared, 900)
        with pytest.raises(WorkflowError):
            counter(
                game,
                c,
                before,
                actor,
                prepared.model_copy(update={"target_actor": actor}),
                900,
            )
    assert before == preview_snapshot
    assert state(game) == before and game.dice.calls == calls

    async def native():
        opened = interaction()
        await opened.response.defer(ephemeral=True)
        await open_alpha_choice(opened, game, choice["id"])
        form = opened.edit_original_response.call_args.kwargs["view"]
        assert doll.PLAY in dict(next(x for x in form.fields if x.key == "play").options)
        assert not await form.interaction_check(interaction(2))
        form.values.update(play=(doll.PLAY,), heat=("1",), context=prepared.context)
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
        assert child["data"]["vatgrown"]["actor"] == actor.model_dump(mode="json")
        assert child["data"]["vatgrown"]["target"] == attacker.model_dump(mode="json")
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


def completed(game, parent, receipt, child, benefits, *, retaliate=True):
    actual = state(game)
    actor, attacker = current_ref(actual, 3), current_ref(actual, 2)
    assert game.inspect(OTHER, child)["state"] == "complete"
    assert game.inspect(PLAYER, parent)["state"] == "complete"
    assert game.inspect(PLAYER, parent)["receipt"] == receipt
    assert bool(alpha.conditions(actual, attacker, actor)) is retaliate
    with game.store.engine.connect() as c:
        value = prove(game, c, actual, child)
        assert value.actor == actor and value.target == attacker
        assert value.benefits == benefits and value.complete
        assert game.action(c, child)["data"]["alpha_counter_completed"]
        assert game.action(c, parent)["data"]["alpha"]["counter_child"] == child
        assert "PRIVATE_COUNTER_DOLL" not in str(
            list(c.scalars(sa.select(t.events.c.payload_json)))
        )
    calls, heat = game.dice.calls, actual.sheets["3"].heat
    own_receipt = game.inspect(OTHER, child)["receipt"]
    restarted = GameService(game.store, dice=game.dice)
    assert restarted.roll(OTHER, str(uuid4()), child)["receipt"] == own_receipt
    assert game.dice.calls == calls == 2 and state(game).sheets["3"].heat == heat
    return value


def test_native_brutalize_doll_mid_retains_real_secret_and_unopposed_departure(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, parent, receipt, child = opportunity(
        ledger, tmp_path, monkeypatch, (3, 4)
    )
    choose(game, OTHER, "vat_doll_benefits", ("leave", "information"), native=True)
    row = next(x for x in game.choices(PLAYER) if x["kind"] == "vat_doll_information")
    assert any(x.identity == row["id"] for x in InboxService(ledger).items(PLAYER))
    before = state(game)
    assert game.inspect(PLAYER, parent)["state"] != "complete"
    assert not alpha.conditions(before, current_ref(before, 2), current_ref(before, 3))
    with pytest.raises(WorkflowError):
        game.respond(
            OTHER,
            str(uuid4()),
            row["id"],
            row["revision"],
            ChoiceAnswer(text="Not my secret"),
        )
    assert state(game) == before
    choose(
        game,
        PLAYER,
        "vat_doll_information",
        text="PRIVATE_DOLL_COUNTER_SECRET I was ordered to keep you alive",
        native=True,
    )
    value = completed(game, parent, receipt, child, ("leave", "information"))
    assert value.total == 8
    controls = DollService(game)
    view = controls.view(OTHER, child)
    assert view["information"]["answer"].startswith("PRIVATE_DOLL_COUNTER_SECRET")
    with pytest.raises(WorkflowError):
        controls.view(ADMIN, child)
    tick(worker, gateway, 8)
    assert "PRIVATE_DOLL_COUNTER_SECRET" not in json.dumps(gateway.messages)
    assert "PRIVATE_COUNTER_DOLL" not in json.dumps(gateway.messages)
    game.depart_doll(
        OTHER,
        str(uuid4()),
        900,
        view["leave"],
        state(game).revision,
        "I use the genuine counter's unopposed exit",
    )
    actual = state(game)
    assert all(
        role.actor != value.actor
        for role in next(x for x in actual.scene_casts if x.id == value.cast.id).roles
    )
    assert controls.view(OTHER, child)["departure"]
    assert alpha.conditions(actual, value.target, value.actor)


def test_native_brutalize_doll_high_keeps_object_and_quiet_without_broken(
    ledger, tmp_path, monkeypatch
):
    game, _, _, parent, receipt, child = opportunity(
        ledger, tmp_path, monkeypatch, (6, 6), retaliate=False
    )
    choose(game, OTHER, "vat_doll_benefits", ("quiet",), native=True)
    value = completed(game, parent, receipt, child, ("quiet",), retaliate=False)
    assert value.total == 13
    assert DollService(game).view(OTHER, child)["quiet"]
    assert DollService(game).view(OTHER, child)["object"]


def test_native_brutalize_doll_low_waits_for_actual_observer_tag_then_benefit(
    ledger, tmp_path, monkeypatch
):
    game, _, _, parent, receipt, child = opportunity(ledger, tmp_path, monkeypatch, (1, 1))
    row = next(x for x in game.choices(PLAYER) if x["kind"] == "vat_doll_attention")
    with pytest.raises(WorkflowError):
        game.respond(
            OTHER,
            str(uuid4()),
            row["id"],
            row["revision"],
            ChoiceAnswer(options=("tag",), text="Not my choice"),
        )
    choose(
        game,
        PLAYER,
        "vat_doll_attention",
        ("tag",),
        "My quiet little shadow",
        native=True,
    )
    assert game.inspect(PLAYER, parent)["state"] != "complete"
    assert not alpha.conditions(
        state(game), current_ref(state(game), 2), current_ref(state(game), 3)
    )
    choose(game, OTHER, "vat_doll_benefits", ("leave",), native=True)
    value = completed(game, parent, receipt, child, ("leave",))
    assert value.total == 3 and value.tag.giver_actor == value.target
    assert any(x.id == value.tag.id for x in state(game).sheets["3"].tags)
