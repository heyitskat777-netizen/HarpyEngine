"""Native directed Doll keeps the real Vatgrown, private observer and lasting benefits."""

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
from test_m2_game import Dice, Gateway, state, tick
from test_physical_operations import place
from test_princess_oldgen_advice import pass_directed
from test_princess_sex import _directed_native, _prepare_directed_native, roll
from test_vatgrown import choose
from test_world import initial

from girlframe.database import tables as t
from girlframe.delivery.m2_worker import GameWorker
from girlframe.engine import m3_princess_sex as princess
from girlframe.engine import m3_vatgrown as doll
from girlframe.engine.creation_details import DesireChoice, GirlDetails, NpcInvestor
from girlframe.engine.m2 import ChoiceAnswer, ReleaseApproval
from girlframe.engine.m2_registry import registry_digest
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.services.creation_coordination import CoordinationService
from girlframe.services.creation_review import CreationReviewService
from girlframe.services.inbox import InboxService
from girlframe.services.m2_game import GameService
from girlframe.services.m3_princess_sex import SexService
from girlframe.services.m3_vatgrown import DollService, prove
from girlframe.services.onboarding import WorkflowError


def ready(store, tmp_path, monkeypatch):
    review, creation, _ = creation_ready(
        store, girl="PRINCESS", frame="THE ENFORCER", other_girl="VATGROWN"
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
    draft = creation.get(OTHER)
    actual = selected("VATGROWN", "JANUS-B")
    creation.save(
        OTHER,
        str(uuid4()),
        draft.revision,
        store.draft(OTHER)["revision"],
        actual.model_copy(
            update={
                "shared_tokens": draft.draft.shared_tokens,
                "girl_details": GirlDetails(
                    investors=tuple(
                        NpcInvestor(npc_slot=x.slot, desires=DesireChoice(slots=(0,)))
                        for x in actual.npc_bonds
                    )
                ),
            }
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
    approved(store, game, tmp_path, monkeypatch, extra=(princess.RULE, doll.RULE))
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
            connection, 1, str(uuid4()), "synthetic.original_doll_bodies_and_resources", actual
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
    direction = _directed_native(game, identity, doll.PLAY, target=target)
    original = state(game)
    game.dice = Dice(faces)
    child = _prepare_directed_native(game, service, identity, heat=("1",), gain=("0",), identity=())
    assert child is not None
    tick(worker, gateway, 3)
    pass_directed(game)
    with game.store.engine.connect() as connection:
        actual = game.action(connection, child)
        assert actual["actor_id"] == "3" and actual["parent_id"] == parent
        assert actual["data"]["vatgrown"]["target"] == target.model_dump(mode="json")
        assert actual["data"]["vatgrown"]["caster"] == 3
        assert actual["data"]["vatgrown"]["counterpart"] == 4
        assert actual["data"]["princess_child"]["author"] == 2
    assert state(game).sheets["3"].heat == original.sheets["3"].heat - 1
    assert state(game).sheets["2"].heat == original.sheets["2"].heat
    return identity, parent, direction.id, child


def assert_complete(game, service, identity, parent, direction_id, child, total):
    assert game.inspect(PLAYER, child)["state"] == "complete"
    assert game.inspect(PLAYER, parent)["state"] == "complete"
    assert service.view(PLAYER, identity)["phase"] == "complete"
    with game.store.engine.connect() as connection:
        actual = prove(game, connection, state(game), child)
        assert actual.caster == 3 and actual.counterpart == 4 and actual.total == total
        assert actual.complete
        assert princess.direction(state(game), direction_id).completed_event
    receipt, calls = game.inspect(PLAYER, child)["receipt"], game.dice.calls
    assert game.roll(PLAYER, str(uuid4()), child)["receipt"] == receipt
    assert game.dice.calls == calls == 1


def test_native_directed_doll_mid_retains_benefits_and_owner_after_directive(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, service = ready(ledger, tmp_path, monkeypatch)
    identity, parent, direction_id, child = direct(game, worker, gateway, service, (4, 4))
    row = next(x for x in game.choices(PLAYER) if x["kind"] == "vat_doll_benefits")
    assert row["actor_id"] == "3"
    assert not any(x["id"] == row["id"] for x in game.choices(OTHER))
    assert any(x.identity == row["id"] for x in InboxService(ledger).items(PLAYER))
    with pytest.raises(WorkflowError):
        game.respond(
            OTHER,
            str(uuid4()),
            row["id"],
            row["revision"],
            ChoiceAnswer(options=("quiet", "leave")),
        )
    choose(game, PLAYER, "vat_doll_benefits", ("quiet", "leave"), native=True)
    assert_complete(game, service, identity, parent, direction_id, child, 9)
    tick(worker, gateway, 8)
    controls = DollService(game)
    with pytest.raises(WorkflowError):
        controls.view(PLAYER, child)
    owned = controls.view(OTHER, child)
    assert owned["quiet"] and owned["leave"]
    before = state(game)
    game.depart_doll(
        OTHER,
        str(uuid4()),
        900,
        owned["leave"],
        before.revision,
        "PRIVATE_DIRECTED_EXIT I leave the original scene unopposed",
    )
    after = state(game)
    source = doll.source(after, child)
    assert after.sheets == before.sheets and after.placements == before.placements
    assert all(
        x.actor != source.actor
        for x in next(x for x in after.scene_casts if x.id == source.cast.id).roles
    )
    assert not controls.view(OTHER, child)["quiet"]
    assert "PRIVATE_DIRECTED_EXIT" not in json.dumps(gateway.messages)


def test_native_directed_doll_high_keeps_actual_observers_private_secret(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, service = ready(ledger, tmp_path, monkeypatch)
    identity, parent, direction_id, child = direct(game, worker, gateway, service, (6, 6))
    choose(game, PLAYER, "vat_doll_benefits", ("information",), native=True)
    row = next(x for x in game.choices(FOUR) if x["kind"] == "vat_doll_information")
    assert not any(x["id"] == row["id"] for x in game.choices(PLAYER))
    with pytest.raises(WorkflowError):
        game.respond(
            PLAYER,
            str(uuid4()),
            row["id"],
            row["revision"],
            ChoiceAnswer(text="Not my secret"),
        )
    assert game.inspect(PLAYER, parent)["state"] != "complete"
    choose(
        game,
        FOUR,
        "vat_doll_information",
        text="PRIVATE_DIRECTED_SECRET My actual offered secret",
        native=True,
    )
    assert_complete(game, service, identity, parent, direction_id, child, 13)
    controls = DollService(game)
    assert controls.view(OTHER, child)["object"]
    assert controls.view(OTHER, child)["information"]["answer"].startswith(
        "PRIVATE_DIRECTED_SECRET"
    )
    with pytest.raises(WorkflowError):
        controls.view(PLAYER, child)
    with ledger.engine.connect() as connection:
        event = princess.direction(state(game), direction_id).completed_event
        assert (
            connection.scalar(sa.select(t.events.c.actor_id).where(t.events.c.id == event)) == "4"
        )
        assert "PRIVATE_DIRECTED_SECRET" not in " ".join(
            connection.scalars(sa.select(t.events.c.payload_json))
        )
    tick(worker, gateway, 8)
    assert "PRIVATE_DIRECTED_SECRET" not in json.dumps(gateway.messages)


def test_native_directed_doll_low_keeps_observers_tag_before_owned_benefit(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, service = ready(ledger, tmp_path, monkeypatch)
    identity, parent, direction_id, child = direct(game, worker, gateway, service, (1, 1))
    assert not any(x["kind"] == "vat_doll_benefits" for x in game.choices(PLAYER))
    row = next(x for x in game.choices(FOUR) if x["kind"] == "vat_doll_attention")
    with pytest.raises(WorkflowError):
        game.respond(
            PLAYER,
            str(uuid4()),
            row["id"],
            row["revision"],
            ChoiceAnswer(options=("tag",), text="Not my response"),
        )
    choose(game, FOUR, "vat_doll_attention", ("tag",), "PRIVATE_DIRECTED_TAG Noticed", native=True)
    tag = next(x for x in state(game).sheets["3"].tags if x.id == "vatgrown-doll-tag:" + child)
    assert tag.giver_actor == current_ref(state(game), 4) and tag.giver == 4
    choose(game, PLAYER, "vat_doll_benefits", ("quiet",), native=True)
    assert_complete(game, service, identity, parent, direction_id, child, 3)
    with ledger.engine.connect() as connection:
        assert prove(game, connection, state(game), child).tag == tag
    assert DollService(game).view(OTHER, child)["quiet"]
    tick(worker, gateway, 8)
    assert "PRIVATE_DIRECTED_TAG" not in json.dumps(gateway.messages)
