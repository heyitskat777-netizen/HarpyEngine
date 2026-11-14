"""An actual native Oldgen advises an awake Girl during her original Alpha counter."""

import asyncio
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
from test_oldgen import native_choice
from test_physical_operations import place
from test_world import initial

from girlframe.database import tables as t
from girlframe.delivery.m2_worker import GameWorker
from girlframe.discord_adapter.m3_alpha_sex import open_alpha_choice
from girlframe.engine import m3_alpha_sex as alpha
from girlframe.engine import m3_oldgen as oldgen
from girlframe.engine.creation_details import GirlDetails
from girlframe.engine.m2 import ChoiceAnswer, PlayInput, ReleaseApproval
from girlframe.engine.m2_registry import registry_digest
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.services.m2_game import GameService
from girlframe.services.m3_alpha_sex import SexService, advice_counter, counter_plays
from girlframe.services.m3_oldgen import OldgenService, prove_advice
from girlframe.services.onboarding import WorkflowError

PEOPLE = (PLAYER, OTHER, FOUR, ADMIN)


def ready(store, tmp_path, monkeypatch):
    review, creation, _ = creation_ready(
        store, girl="ALPHA", frame="THE ENFORCER", other_girl="OLDGEN"
    )
    own = creation.get(OTHER)
    draft = selected("OLDGEN", "JANUS-B").model_copy(
        update={
            "shared_tokens": own.draft.shared_tokens,
            "girl_details": GirlDetails(maxims=(0, 1)),
        }
    )
    creation.save(OTHER, str(uuid4()), own.revision, store.draft(OTHER)["revision"], draft)
    incoming = next(x for x in review.get(OTHER).sheet.bonds if not x.outgoing)
    own = creation.get(OTHER)
    review.select_bond(
        OTHER, str(uuid4()), own.revision, store.draft(OTHER)["revision"], own.draft, incoming.id
    )
    third_draft(store)
    store.policy = store.policy.model_copy(
        update={
            "owner_intense_tag_bonus": 2,
            "m2_approval": ReleaseApproval(
                registry_sha256=registry_digest(),
                reviewer="synthetic test only",
                reference="fixture; not certification",
            ),
        }
    )
    game = GameService(store, dice=Dice((1, 1)))
    for viewer in (PLAYER, OTHER, FOUR):
        saved = review.get(viewer)
        assert saved.sheet.ready_for_rules_review, saved.sheet.issues
        review.save(viewer, str(uuid4()), saved.saved_revision, saved.fingerprint)
        game.activate(viewer, str(uuid4()), review.get(viewer).fingerprint)
    configure_m3_fixture(store)
    approved(store, game, tmp_path, monkeypatch, extra=(alpha.RULE, oldgen.RULE, oldgen.ADVICE))
    approval = store.policy.m3_approval
    store.policy = store.policy.model_copy(
        update={
            "m3_approval": approval.model_copy(
                update={"subsystems": approval.subsystems | {"world"}}
            )
        }
    )
    with store.transaction() as c:
        actual = state(game)
        actual.world = initial()
        for owner in (2, 3, 4):
            actual = place(actual, owner, mode="outside_frame")
        actual.sheets["3"].heat = 3
        game.event(c, 1, str(uuid4()), "synthetic.original_alpha_advice_counter_bodies", actual)
    game.bind_scene(ADMIN, str(uuid4()), 900)
    for viewer in PEOPLE:
        game.join_scene(viewer, str(uuid4()), 900)
    gateway = Gateway()
    actor = gateway.actor

    async def actual_actor(identity):
        return FOUR if identity == 4 else await actor(identity)

    gateway.actor = actual_actor
    return game, GameWorker(game), gateway


def interaction(owner=3):
    value = current(owner, uuid4().int % 1000000000)
    value.channel_id = 900
    return value


def test_native_oldgen_sleep_counter_real_advice_listening_owned_wake_and_private_receipts(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway = ready(ledger, tmp_path, monkeypatch)
    service = SexService(game)
    original = state(game)
    sleeper, adviser, recipient = (current_ref(original, owner) for owner in (2, 3, 4))
    assert original.sheets["2"].girl == "ALPHA" and original.sheets["3"].girl == "OLDGEN"
    session = service.invite(
        PLAYER, str(uuid4()), 900, adviser, original.revision, "My actual voluntary source"
    )["id"]
    service.respond(
        OTHER, str(uuid4()), session, state(game).revision, True, "My own voluntary confirmation"
    )
    parent = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play=alpha.PLAY,
            source_work=session,
            target_actor=adviser,
            heat=0,
            context="Our actual confirmed interaction",
            trigger_confirmed=True,
        ),
    )["action_id"]
    tick(worker, gateway, 4)
    for viewer in PEOPLE:
        answer(game, viewer, "tag_window", options=("pass",))
    assert alpha.asleep(state(game), sleeper)
    parent_receipt = game.inspect(PLAYER, parent)["receipt"]
    consent = alpha.get(state(game), session).consent_event
    answer(game, OTHER, "alpha_sex_low", options=("play",))
    choice = next(x for x in game.choices(OTHER) if x["kind"] == "alpha_sex_counter_play")
    prepared = PlayInput(
        play=oldgen.PLAY,
        target=4,
        parent=parent,
        heat=1,
        context="PRIVATE_COUNTER_ADVICE I advise the awake Girl on the safe route",
        trigger_confirmed=True,
    )
    before, calls = state(game), game.dice.calls
    with ledger.engine.connect() as c:
        assert oldgen.PLAY in counter_plays(game, c, before, game.action(c, parent), adviser)
        with pytest.raises(WorkflowError, match="awake"):
            advice_counter(game, c, before, adviser, prepared.model_copy(update={"target": 2}), 900)
        with pytest.raises(WorkflowError):
            advice_counter(game, c, before, recipient, prepared, 900)
    assert state(game) == before and game.dice.calls == calls

    async def native_counter():
        opened = interaction()
        await opened.response.defer(ephemeral=True)
        await open_alpha_choice(opened, game, choice["id"])
        form = opened.edit_original_response.call_args.kwargs["view"]
        assert oldgen.PLAY in dict(next(x for x in form.fields if x.key == "play").options)
        assert not await form.interaction_check(interaction(4))
        form.values.update(
            play=(oldgen.PLAY,),
            target=("4",),
            heat=("1",),
            gain=("0",),
            pair_share=("0",),
            piloting=("no",),
            witnessed=("no",),
            context=prepared.context,
            trigger=("yes",),
        )
        submitted = interaction()
        await form.confirm.callback(submitted)
        assert form.completed, submitted.edit_original_response.call_args_list
        saved = state(game)
        await form.confirm.callback(submitted)
        assert state(game) == saved

    asyncio.run(native_counter())
    with ledger.engine.connect() as c:
        actions = t.m2["m2_actions"]
        child = game.action(
            c,
            c.scalar(
                sa.select(actions.c.id).where(
                    actions.c.campaign_id == ledger.campaign_id,
                    actions.c.parent_id == parent,
                    actions.c.actor_id == "3",
                )
            ),
        )
    identity = child["id"]
    assert child["data"]["alpha_sex_counter_source"]["choice"] == choice["id"]
    assert child["data"]["oldgen"]["target"] == recipient.model_dump(mode="json")
    assert child["data"]["prepared"]["source_work"] is None
    assert state(game).sheets["3"].heat == before.sheets["3"].heat and game.dice.calls == calls
    game.dice.faces = (3, 4)
    tick(worker, gateway, 4)
    for viewer in PEOPLE:
        answer(game, viewer, "tag_window", options=("pass",))
    assert state(game).sheets["3"].heat == before.sheets["3"].heat - 1
    assert state(game).sheets["2"].heat == before.sheets["2"].heat
    native_choice(
        game, OTHER, "oldgen_write_maxim", "PRIVATE_COUNTER_MAXIM Always take the safe route"
    )
    owed = next(x for x in game.choices(FOUR) if x["kind"] == "oldgen_listen")
    with pytest.raises(WorkflowError):
        game.decision(OTHER, owed["id"])
    assert alpha.asleep(state(game), sleeper)
    assert game.inspect(OTHER, identity)["state"] != "complete"
    native_choice(game, FOUR, "oldgen_listen", "I actually sit down and listen to her advice")
    actual = state(game)
    assert game.inspect(OTHER, identity)["state"] == "complete"
    assert alpha.asleep(actual, sleeper) and alpha.get(actual, session).phase == "waking"
    assert game.inspect(PLAYER, parent)["receipt"] == parent_receipt
    assert alpha.get(actual, session).consent_event == consent
    with ledger.engine.connect() as c:
        proof = prove_advice(game, c, actual, identity)
        assert proof.actor == adviser and proof.target == recipient and proof.total == 8
        assert proof.heat == 1 and proof.caster == 3 and proof.counterpart == 4
        assert game.action(c, identity)["data"]["alpha_sex_counter_done"]
        assert (
            c.scalar(sa.select(t.events.c.actor_id).where(t.events.c.id == proof.roll_event)) == "3"
        )
        assert "PRIVATE_COUNTER" not in str(list(c.scalars(sa.select(t.events.c.payload_json))))
    maxim = next(x for x in oldgen.records(actual, oldgen.Maxim) if x.advice == identity)
    assert maxim.owner == adviser and maxim.subject == recipient
    assert oldgen.records(actual, oldgen.Advice)[-1].maxim == maxim.id
    with pytest.raises(WorkflowError):
        OldgenService(game).view(PLAYER, maxim.id)
    wake = next(x for x in game.choices(PLAYER) if x["kind"] == "alpha_sex_wake")
    with pytest.raises(WorkflowError):
        game.respond(
            OTHER,
            str(uuid4()),
            wake["id"],
            wake["revision"],
            ChoiceAnswer(options=("wake",), text="Not my original source"),
        )
    answer(game, PLAYER, "alpha_sex_wake", options=("wake",), text="I actually wake from my sleep")
    assert not alpha.asleep(state(game), sleeper)
    assert game.inspect(PLAYER, parent)["state"] == "complete"
    assert game.inspect(PLAYER, parent)["receipt"] == parent_receipt
    receipt = game.inspect(OTHER, identity)["receipt"]
    assert game.roll(OTHER, str(uuid4()), identity)["receipt"] == receipt
    assert game.dice.calls == calls + 1
    tick(worker, gateway, 4)
