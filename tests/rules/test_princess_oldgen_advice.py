"""Native directed advice uses real Oldgen resources and retains the recipient's decisions."""

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
from test_oldgen import native_choice
from test_physical_operations import place
from test_princess_sex import _directed_native, _prepare_directed_native, roll
from test_world import initial

from girlframe.database import tables as t
from girlframe.delivery.m2_worker import GameWorker
from girlframe.engine import m3_oldgen as oldgen
from girlframe.engine import m3_princess_sex as princess
from girlframe.engine.creation_details import GirlDetails
from girlframe.engine.m2 import ChoiceAnswer, ReleaseApproval
from girlframe.engine.m2_registry import registry_digest
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.services.creation_review import CreationReviewService
from girlframe.services.inbox import InboxService
from girlframe.services.m2_game import GameService
from girlframe.services.m3_oldgen import OldgenService, prove_advice
from girlframe.services.m3_princess_sex import SexService
from girlframe.services.onboarding import WorkflowError


def ready(store, tmp_path, monkeypatch):
    review, creation, _ = creation_ready(
        store, girl="PRINCESS", frame="THE ENFORCER", other_girl="OLDGEN"
    )
    draft = creation.get(OTHER)
    creation.save(
        OTHER,
        str(uuid4()),
        draft.revision,
        store.draft(OTHER)["revision"],
        selected("OLDGEN", "JANUS-B").model_copy(
            update={
                "shared_tokens": draft.draft.shared_tokens,
                "girl_details": GirlDetails(maxims=(0, 1)),
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
    approved(store, game, tmp_path, monkeypatch, extra=(princess.RULE, oldgen.ADVICE, oldgen.RULE))
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
        actual.sheets["4"].identities[0].marked = True
        game.event(
            connection, 1, str(uuid4()), "synthetic.original_advice_bodies_and_resources", actual
        )
    game.bind_scene(ADMIN, str(uuid4()), 900)
    for viewer in (PLAYER, OTHER, FOUR, ADMIN):
        game.join_scene(viewer, str(uuid4()), 900)
    gateway = Gateway()

    async def actor(identity):
        return {1: ADMIN, 2: PLAYER, 3: OTHER, 4: FOUR}[identity]

    gateway.actor = actor
    return game, GameWorker(game), gateway, SexService(game)


def pass_directed(game):
    while True:
        rows = [
            (viewer, row)
            for viewer in (PLAYER, OTHER, FOUR, ADMIN)
            for row in game.choices(viewer)
            if row["kind"] == "tag_window"
        ]
        if not rows:
            return
        viewer, row = rows[0]
        game.respond(
            viewer, str(uuid4()), row["id"], row["revision"], ChoiceAnswer(options=("pass",))
        )


def direct(game, worker, gateway, service, faces):
    identity, parent = roll(game, worker, gateway, service, (6, 6), native=True)
    pass_directed(game)
    target = current_ref(state(game), 4)
    direction = _directed_native(game, identity, oldgen.PLAY, target=target)
    original = state(game)
    game.dice = Dice(faces)
    child = _prepare_directed_native(game, service, identity, heat=("1",), gain=("0",), identity=())
    assert child is not None
    tick(worker, gateway, 3)
    pass_directed(game)
    with game.store.engine.connect() as connection:
        actual = game.action(connection, child)
        assert actual["actor_id"] == "3" and actual["parent_id"] == parent
        assert actual["data"]["oldgen"]["target"] == target.model_dump(mode="json")
        assert actual["data"]["oldgen"]["caster"] == 3
        assert actual["data"]["oldgen"]["counterpart"] == 4
        assert actual["data"]["princess_child"]["author"] == 2
    assert state(game).sheets["3"].heat == original.sheets["3"].heat - 1
    assert state(game).sheets["2"].heat == original.sheets["2"].heat
    return identity, parent, direction.id, child


def test_native_directed_oldgen_high_advice_retains_recipient_and_owned_maxim(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, service = ready(ledger, tmp_path, monkeypatch)
    identity, parent, direction_id, child = direct(game, worker, gateway, service, (6, 6))
    row = next(x for x in game.choices(PLAYER) if x["kind"] == "oldgen_write_maxim")
    assert row["actor_id"] == "3"
    assert not any(x["id"] == row["id"] for x in game.choices(OTHER))
    assert any(x.identity == row["id"] for x in InboxService(ledger).items(PLAYER))
    with pytest.raises(WorkflowError):
        game.respond(
            OTHER, str(uuid4()), row["id"], row["revision"], ChoiceAnswer(text="Not mine now")
        )
    native_choice(
        game, PLAYER, "oldgen_write_maxim", "PRIVATE_DIRECTED_MAXIM Always check the exit"
    )
    maxim = next(x for x in oldgen.records(state(game), oldgen.Maxim) if x.advice == child)
    assert maxim.owner == current_ref(state(game), 3) and maxim.subject == current_ref(
        state(game), 4
    )
    assert maxim.high
    # The actual fourth player retains her factual listening, not the Princess author.
    row = next(x for x in game.choices(FOUR) if x["kind"] == "oldgen_listen")
    assert not any(x["id"] == row["id"] for x in game.choices(PLAYER))
    with pytest.raises(WorkflowError):
        game.respond(
            PLAYER, str(uuid4()), row["id"], row["revision"], ChoiceAnswer(text="Not her answer")
        )
    assert game.inspect(PLAYER, parent)["state"] != "complete"
    native_choice(game, FOUR, "oldgen_listen", "I actually sit and listen to the original adviser")
    assert game.inspect(PLAYER, child)["state"] == "complete"
    assert game.inspect(PLAYER, parent)["state"] == "complete"
    assert service.view(PLAYER, identity)["phase"] == "complete"
    with ledger.engine.connect() as connection:
        proven = prove_advice(game, connection, state(game), child)
        assert proven.caster == 3 and proven.counterpart == 4 and proven.total == 13
        assert proven.heat == 1
        event = princess.direction(state(game), direction_id).completed_event
        author = connection.scalar(sa.select(t.events.c.actor_id).where(t.events.c.id == event))
        assert author == "4"
    calls = game.dice.calls
    receipt = game.inspect(PLAYER, child)["receipt"]
    assert game.roll(PLAYER, str(uuid4()), child)["receipt"] == receipt
    assert game.dice.calls == calls == 1
    tick(worker, gateway, 8)
    controls = OldgenService(game)
    with pytest.raises(WorkflowError):
        controls.view(PLAYER, maxim.id)
    assert controls.view(OTHER, maxim.id)["available"]
    before = state(game).sheets["4"].heat
    controls.use(
        OTHER,
        str(uuid4()),
        maxim.id,
        current_ref(state(game), 4),
        "reinforce",
        900,
        state(game).revision,
        "Her actual caution reinforces the original one-use maxim",
    )
    assert state(game).sheets["4"].heat == before + 2
    assert not controls.view(OTHER, maxim.id)["available"]
    assert "PRIVATE_DIRECTED_MAXIM" not in json.dumps(gateway.messages)


def test_native_directed_oldgen_low_keeps_other_girls_own_unmark_and_maxim(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, service = ready(ledger, tmp_path, monkeypatch)
    identity, parent, _, child = direct(game, worker, gateway, service, (1, 1))
    row = next(x for x in game.choices(FOUR) if x["kind"] == "oldgen_low_maxim")
    assert not any(x["id"] == row["id"] for x in game.choices(PLAYER))
    own_mark = next(x for x in state(game).sheets["4"].identities if x.marked)
    native_choice(
        game, FOUR, "oldgen_low_maxim", "Bad advice needs checking", unmark=(own_mark.id,)
    )
    maxim = next(x for x in oldgen.records(state(game), oldgen.Maxim) if x.advice == child)
    assert maxim.owner == current_ref(state(game), 4) and maxim.subject == current_ref(
        state(game), 3
    )
    assert not next(x for x in state(game).sheets["4"].identities if x.id == own_mark.id).marked
    assert game.inspect(PLAYER, parent)["state"] == "complete"
    assert service.view(PLAYER, identity)["phase"] == "complete"
    with ledger.engine.connect() as connection:
        assert prove_advice(game, connection, state(game), child).total == 3
