"""Honey rewards preserve actual orders and the two original owners' decisions."""

import asyncio

import pytest
from test_handler_creation import agree, complete, ready, save
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Gateway, answer, state, tick
from test_mission_ui import current
from test_off_duty_cycle import activate, prepared
from test_punishment_service import submit

from girlframe.delivery.m2_worker import GameWorker
from girlframe.discord_adapter.inbox import InboxView
from girlframe.discord_adapter.m2_forms import NativeForm
from girlframe.engine.m2 import ChoiceAnswer
from girlframe.engine.m3_punishments import Details
from girlframe.services.inbox import InboxService
from girlframe.services.m3_handler_creation import HandlerCreationService
from girlframe.services.m3_mistress_rewards import OFFER, REJECTION, REPLY, RULE
from girlframe.services.m3_punishments import PunishmentService
from girlframe.services.onboarding import WorkflowError


def create_mistress(ledger):
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
    save(creation, complete(creation, "Mistress"))
    agree(creation)
    preview = creation.view(ADMIN)
    creation.activate(ADMIN, "activate-honey", preview["revision"], preview["game_revision"], True)


@pytest.mark.parametrize("ending", ("smile", "punish"))
def test_honey_rewards_require_each_owner_and_a_real_accepted_effect(ledger, ending):
    if ending == "punish":
        cycle, game, period = prepared(ledger, before_period=lambda _: create_mistress(ledger))
    else:
        _, game = ready(ledger)
        create_mistress(ledger)
    worker, gateway = GameWorker(game), Gateway()
    inbox = InboxService(ledger)

    def order(key, reaction):
        active = game.issue_order(ADMIN, key, 900, 3, "Finish the reported check.")
        tick(worker, gateway, 3)
        answer(game, OTHER, "order_response", options=(reaction,))
        return active["action_id"]

    async def choose(who, decision, sequence, **values):
        click = current(who.user_id, sequence)
        await click.response.defer(ephemeral=True)
        item = next(x for x in inbox.items(who) if x.identity == decision["id"])
        await InboxView(inbox, who.user_id).route(click, item)
        form = click.edit_original_response.call_args.kwargs["view"]
        assert isinstance(form, NativeForm)
        form.values.update(values)
        request = current(who.user_id, sequence + 1)
        await form.confirm.callback(request)
        assert form.completed, (
            request.followup.send.call_args,
            request.edit_original_response.call_args,
        )

    hesitant = order("actual-hesitation", "hesitant")
    assert game.inspect(OTHER, hesitant)["state"] == "complete"
    assert not any(x["kind"] == OFFER for x in game.choices(ADMIN))
    tick(worker, gateway, 5)
    obeyed = order("actual-unhesitating-obedience", "immediate")
    (offer,) = (x for x in game.choices(ADMIN) if x["kind"] == OFFER)
    with pytest.raises(WorkflowError, match="another player"):
        game.respond(
            OTHER,
            "offer-on-behalf-of-handler",
            offer["id"],
            offer["revision"],
            ChoiceAnswer(options=("raise_status",)),
        )
    asyncio.run(
        choose(
            ADMIN,
            offer,
            46800,
            options=("pet_name", "raise_status"),
            **{"fields.pet_name": "PRIVATE_NAME", "fields.tag": "PRIVATE_MATCHING_TAG"},
        )
    )
    replies = {
        game.decision(OTHER, x["id"])["body"]["reward"]: x
        for x in game.choices(OTHER)
        if x["kind"] == REPLY
    }
    assert set(replies) == {"pet_name", "raise_status"}
    assert not {x["id"] for x in replies.values()} & {x.identity for x in inbox.items(PLAYER)}
    assert "PRIVATE_NAME" not in str(game.inspect(PLAYER, obeyed))
    assert state(game).order == (2, 3) and not state(game).sheets["3"].tags

    accepted = "pet_name" if ending == "punish" else "raise_status"
    rejected = next(x for x in replies if x != accepted)
    ledger.engine.dispose()
    asyncio.run(choose(OTHER, replies[rejected], 46810, flag=("no",)))
    assert not any(x["kind"] == REJECTION for x in game.choices(ADMIN))
    asyncio.run(choose(OTHER, replies[accepted], 46820, flag=("yes",)))
    game.respond(
        OTHER,
        "46821",
        replies[accepted]["id"],
        replies[accepted]["revision"],
        ChoiceAnswer(flag=True),
    )
    with pytest.raises(WorkflowError):
        game.respond(
            OTHER,
            "retry-with-stale-key",
            replies[accepted]["id"],
            replies[accepted]["revision"],
            ChoiceAnswer(flag=False),
        )
    actual = state(game)
    if accepted == "pet_name":
        (tag,) = actual.sheets["3"].tags
        assert tag.label == "PRIVATE_MATCHING_TAG" and tag.giver_actor.kind == "handler"
        assert set(tag.observers) == {1, 3}
        assert actual.order == (2, 3)
    else:
        assert actual.order == (3, 2) and not actual.sheets["3"].tags
    (reaction,) = (x for x in game.choices(ADMIN) if x["kind"] == REJECTION)
    asyncio.run(choose(ADMIN, reaction, 46830, options=(ending,)))
    assert game.inspect(OTHER, obeyed)["state"] == "complete"
    debts = [x for x in state(game).obligations if x.details.get("cause") == RULE]
    assert len(debts) == int(ending == "punish")
    if ending == "punish":
        (debt,) = debts
        assert debt.owner == 3 and debt.target == 1 and debt.state == "pending"
        tick(worker, gateway, 5)
        work = next(
            x for x in cycle.periods.get(ADMIN, period)["work"] if x["kind"] == "punishment"
        )
        activate(cycle, game, period)
        discipline = PunishmentService(ledger)
        choice = Details(kind="stimulant_injection")
        with pytest.raises(WorkflowError, match="on-screen"):
            submit(discipline, ADMIN, work["id"], choice)
        context = discipline.get(ADMIN, work["id"])
        discipline.propose_scene(
            ADMIN,
            "honey-discipline-scene",
            work["id"],
            context["revision"],
            context["game_revision"],
            "The original Mistress presents the chosen consequence.",
        )
        for owner in (ADMIN, OTHER):
            context = discipline.get(owner, work["id"])
            discipline.attest_scene(
                owner,
                "honey-discipline-attest:" + str(owner.user_id),
                work["id"],
                context["revision"],
                context["game_revision"],
            )
        before = state(game).sheets["3"].heat
        submit(discipline, ADMIN, work["id"], choice)
        assert state(game).sheets["3"].heat == before + 7
        assert next(x for x in state(game).obligations if x.id == debt.id).state == "fulfilled"
