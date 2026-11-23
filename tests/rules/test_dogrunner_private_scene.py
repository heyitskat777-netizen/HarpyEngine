"""Both Dogrunner private answers use the real recovery and discipline workflow."""

import asyncio

import pytest
from test_handler_creation import agree, complete, save
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state
from test_mission_ui import current
from test_off_duty_cycle import activate, prepared, roll_for
from test_punishment_service import submit

from girlframe.discord_adapter.inbox import InboxView
from girlframe.discord_adapter.m3_handler_plays import open_handler_plays
from girlframe.engine.m3_dogrunner_recovery import SOURCE, modifiers
from girlframe.engine.m3_handler_private_scene import records
from girlframe.engine.m3_punishments import Details
from girlframe.services.inbox import InboxService
from girlframe.services.m3_handler_creation import HandlerCreationService
from girlframe.services.m3_handler_plays import HandlerPlayService
from girlframe.services.m3_handler_private_scene import HandlerPrivateSceneService
from girlframe.services.m3_punishments import PunishmentService
from girlframe.services.onboarding import WorkflowError


@pytest.mark.parametrize("agreed", (True, False))
def test_dogrunner_answer_creates_real_recovery_bonus_or_punishment(ledger, agreed):
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
        save(creation, complete(creation, "Dogrunner"))
        agree(creation)
        data = creation.view(ADMIN)
        creation.activate(ADMIN, "actual-dogrunner", data["revision"], data["game_revision"], True)

    cycle, game, period = prepared(ledger, before_period=create)
    activate(cycle, game, period)
    game.leave_scene(PLAYER, "actual-dogrunner-private-scene", 900)
    service, inbox = HandlerPrivateSceneService(ledger, game), InboxService(ledger)

    async def invite():
        click = current(1, 49400)
        click.channel_id = 900
        await click.response.defer(ephemeral=True)
        await open_handler_plays(click, HandlerPlayService(ledger))
        hub = click.edit_original_response.call_args.kwargs["view"]
        await hub.open_item(click, "dogrunner_private")
        form = click.edit_original_response.call_args.kwargs["view"]
        form.values.update(offer=("offer",))
        sent = current(1, 49401)
        await form.confirm.callback(sent)
        assert form.completed, sent.followup.send.call_args

    asyncio.run(invite())
    (original,) = records(state(game))
    assert not any(x.identity == original.id for x in inbox.items(PLAYER))

    async def native(viewer, number, choice, **values):
        click = current(viewer.user_id, number)
        await click.response.defer(ephemeral=True)
        item = next(x for x in inbox.items(viewer) if x.identity == original.id)
        await InboxView(inbox, viewer.user_id).route(click, item)
        form = click.edit_original_response.call_args.kwargs["view"]
        form.values.update(choice=(choice,), **values)
        sent = current(viewer.user_id, number + 1)
        await form.confirm.callback(sent)
        assert form.completed, sent.followup.send.call_args

    asyncio.run(native(OTHER, 49410, "consent"))
    asyncio.run(native(ADMIN, 49412, "attest"))
    asyncio.run(native(OTHER, 49414, "attest"))
    asyncio.run(native(ADMIN, 49416, "dogrunner_ask"))
    with pytest.raises(WorkflowError, match="your own"):
        service.respond(
            ADMIN,
            "invented-response",
            original.id,
            state(game).revision,
            "dogrunner_answer",
            text="A substitute answer.",
        )
    asyncio.run(native(OTHER, 49418, "dogrunner_answer", account="I think I did well."))
    before = state(game)
    ledger.engine.dispose()
    step, label = (
        ("dogrunner_agree", "PRIVATE_EARNED_TAG") if agreed else ("dogrunner_disagree", "")
    )
    asyncio.run(native(ADMIN, 49420, step, **({"account": label} if label else {})))
    assert (
        service.respond(ADMIN, "49421", original.id, before.revision, step, text=label)["id"]
        == original.id
    )
    (chosen,) = records(state(game))
    if agreed:
        assert chosen.outcome == "dogrunner_rewarded"
        assert any(x.id == chosen.tag and x.label == label for x in state(game).sheets["3"].tags)
        assert modifiers(state(game), chosen.girl) == [dict(id=chosen.id, source=SOURCE, amount=2)]
        assert any(
            x.id == chosen.tag and x.observers == (1, 3) for x in state(game).sheets["3"].tags
        )
        game.join_scene(PLAYER, "restore-off-duty-cast", 900)
        action = roll_for(cycle, game, period, OTHER, (3, 3), review_reward=False)
        roll = cycle.review(OTHER, period)["own"]["roll"]
        assert tuple(roll["faces"]) == (3, 3) and roll["total"] == roll["modifier"] + 8
        assert [(x["source"], x["amount"]) for x in roll["adjustments"]] == [(SOURCE, 2)]
        assert not modifiers(state(game), chosen.girl)
        assert any(
            x.get("kind") == "dogrunner_recovery_use"
            and x["id"] == chosen.id
            and x["action"] == action
            for x in state(game).facts
        )
        roll_for(cycle, game, period, PLAYER, (3, 3), review_reward=False)
        assert not cycle.review(PLAYER, period)["own"]["roll"]["adjustments"]
        return

    assert chosen.outcome == "dogrunner_punishment" and not modifiers(state(game), chosen.girl)
    assert service.menu(OTHER, chosen.id)["phase"] == "dogrunner_discipline"
    assert any(x.id == chosen.discipline and x.state == "pending" for x in state(game).obligations)
    discipline = PunishmentService(ledger)
    task = next(
        x
        for x in cycle.periods.get(ADMIN, period)["work"]
        if x["kind"] == "punishment" and x["id"].endswith(":m2-punishment:" + chosen.discipline)
    )
    data = discipline.get(ADMIN, task["id"])
    discipline.propose_scene(
        ADMIN,
        "actual-dogrunner-proposal",
        task["id"],
        data["revision"],
        data["game_revision"],
        "The actual agreed synthetic tabletop discipline scene.",
    )
    for viewer in (ADMIN, OTHER):
        data = discipline.get(viewer, task["id"])
        discipline.attest_scene(
            viewer,
            f"actual-dogrunner-attestation:{viewer.user_id}",
            task["id"],
            data["revision"],
            data["game_revision"],
        )
    submit(
        discipline,
        ADMIN,
        task["id"],
        Details(kind="stimulant_injection"),
        "actual-dogrunner-punishment",
    )
    assert service.menu(OTHER, chosen.id)["phase"] == "complete"
