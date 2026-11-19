"""Crisis choices arise from actual Tag effects and preserve an already saved die."""

import asyncio
import json

import pytest
from test_handler_creation import agree, complete, save
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state
from test_mission_ui import current
from test_strain_effect_service import pending

from girlframe.discord_adapter.inbox import InboxView
from girlframe.engine.m3_frantic_crisis import records
from girlframe.engine.m3_handler_consequences import active_handler
from girlframe.engine.m3_handler_play_state import Effect
from girlframe.services.inbox import InboxService
from girlframe.services.m3_frantic_crisis import CrisisService
from girlframe.services.m3_handler_creation import HandlerCreationService
from girlframe.services.m3_handler_plays import HandlerPlayService
from girlframe.services.onboarding import WorkflowError


def test_actual_frantic_tag_opens_one_crisis_and_each_raise_is_finite(ledger):
    def create(_):
        creation = HandlerCreationService(ledger)
        approval, rulings = ledger.policy.m3_approval, ledger.policy.owner_m3_rulings
        ledger.policy = ledger.policy.model_copy(
            update=dict(
                m3_approval=approval.model_copy(
                    update=dict(subsystems=approval.subsystems | {"plays", "playbooks"})
                ),
                owner_m3_rulings=rulings.model_copy(
                    update=dict(handler_creation="owned_shared_choices_preserve_existing")
                ),
            )
        )
        save(creation, complete(creation, "Frantic"))
        agree(creation)
        preview = creation.view(ADMIN)
        creation.activate(
            ADMIN, "frantic-crisis-source", preview["revision"], preview["game_revision"], True
        )

    effects, game, _, _ = pending(ledger, before_period=create)
    strain = effects.strain
    before = {x.track: x for x in state(game).strain.requests if x.kind == "roll"}
    budget = before["budget"]
    strain.dice.face = 5
    roll_revision = state(game).revision
    dice = strain.roll(ADMIN, "budget-already-rolled", budget.id, 1, roll_revision)
    assert dice["face"] == 5
    with ledger.engine.connect() as c:
        initial = strain._row(c, budget.id)
    assert json.loads(initial["body_json"])["severity"] == "low"
    service, inbox = CrisisService(ledger), InboxService(ledger)
    plays = HandlerPlayService(ledger)

    def gain_tag(number):
        canonical = state(game)
        actor = active_handler(canonical)
        grant = plays.start(ADMIN, "frantic-tag-grant:" + str(number), canonical.revision, (actor,))
        effect = Effect(
            kind="tag",
            target=actor,
            tag="PRIVATE_FRANTIC_TAG_" + str(number),
            account="An actual synthetic Tag effect",
        )
        key = "frantic-tag-effect:" + str(number)
        saved = plays.submit(ADMIN, key, grant["id"], grant["game_revision"], "mess", effect)
        assert (
            plays.submit(ADMIN, key, grant["id"], grant["game_revision"], "mess", effect) == saved
        )
        value = next(x for x in records(state(game)) if x.tag == grant["id"] + ":tag")
        assert value.slot is None
        return value

    async def choose(identity, slot, track, sequence):
        click = current(1, sequence)
        await click.response.defer(ephemeral=True)
        item = next(x for x in inbox.items(ADMIN) if x.identity == identity)
        await InboxView(inbox, 1).route(click, item)
        form = click.edit_original_response.call_args.kwargs["view"]
        form.values.update(slot=(slot,), track=(track,))
        sent = current(1, sequence + 1)
        await form.confirm.callback(sent)
        assert form.completed, (sent.followup.send.call_args, sent.edit_original_response.call_args)

    first = gain_tag(1)
    assert len(records(state(game))) == 1
    for other in (PLAYER, OTHER):
        assert not any(x.identity == first.id for x in inbox.items(other))
        with pytest.raises(WorkflowError):
            service.get(other, first.id)
    ledger.safety(OTHER, "pause-crisis", ledger.status(OTHER)["revision"], pause=True)
    with pytest.raises(WorkflowError, match="SAFETY_PAUSED"):
        service.raise_track(
            ADMIN, "paused-crisis", first.id, state(game).revision, "raise_first", "rebellion"
        )
    ledger.safety(OTHER, "resume-crisis", ledger.status(OTHER)["revision"], pause=False)
    ledger.engine.dispose()
    revision = state(game).revision
    asyncio.run(choose(first.id, "raise_first", "rebellion", 47600))
    service.raise_track(ADMIN, "47601", first.id, revision, "raise_first", "rebellion")
    state1 = state(game)
    assert state1.strain.levels["rebellion"] == "high"
    assert (
        next(x for x in state1.strain.requests if x.id == before["rebellion"].id).severity == "high"
    )
    second = gain_tag(2)
    with pytest.raises(WorkflowError, match="unused"):
        service.raise_track(
            ADMIN, "first-used", second.id, state(game).revision, "raise_first", "budget"
        )
    asyncio.run(choose(second.id, "raise_second", "budget", 47610))
    state2 = state(game)
    assert state2.strain.levels["budget"] == "high"
    with ledger.engine.connect() as c:
        assert strain._row(c, budget.id) == initial
    assert strain.roll(ADMIN, "budget-already-rolled", budget.id, 1, roll_revision) == dice
    third = gain_tag(3)
    assert service.get(ADMIN, third.id)["available"] == ()
    assert len(records(state(game))) == 3 and records(state(game))[-1].slot is None
