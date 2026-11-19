"""Insurgent labels use the original witnessed act and the Girl's own speech."""

import asyncio

import pytest
from test_handler_creation import agree, complete, save
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Dice, Gateway, answer, pass_tags, state, tick
from test_mission_ui import current
from test_off_duty_cycle import activate, prepared
from test_punishment_service import submit

from girlframe.delivery.m2_worker import GameWorker
from girlframe.discord_adapter.inbox import InboxView
from girlframe.engine.m2 import ChoiceAnswer, PlayInput
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_punishments import Details
from girlframe.engine.m3_world_state import Npc
from girlframe.services.inbox import InboxService
from girlframe.services.m3_handler_creation import HandlerCreationService
from girlframe.services.m3_insurgent_loyalty import REVEAL, RULE, WATCH, labels
from girlframe.services.m3_punishments import PunishmentService
from girlframe.services.onboarding import WorkflowError


def create_insurgent(ledger, game):
    with ledger.transaction() as c:
        original = state(game)
        npc = Npc(
            id="actual-npc",
            name="Private character",
            controller=1,
            jobs=("guard",),
            detail="An original synthetic NPC with a recorded Handler bond.",
            cell=(1, 0),
            bonds={"handler:1": 1},
        )
        original.world = original.world.model_copy(update=dict(npcs=(npc,)))
        game.event(c, 1, "insurgent-old-bond", "synthetic.preexisting_bond", original)
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
    save(creation, complete(creation, "Insurgent"))
    agree(creation)
    first = creation.view(ADMIN)
    creation.activate(ADMIN, "create-insurgent", first["revision"], first["game_revision"], True)


def test_only_observed_refusal_and_owned_disclosure_create_insurgent_labels(ledger):
    cycle, game, period = prepared(
        ledger, before_period=lambda game: create_insurgent(ledger, game)
    )
    from test_strain_service import D6

    from girlframe.services.m3_insurgent_cover import CoverService

    cover = CoverService(cycle.periods, dice=D6(1))
    case = "cover:" + period
    cover.roll(ADMIN, "loyalty-cover-roll", case, state(game).revision)
    cover.choose_evidence(
        ADMIN, "loyalty-cover-column", case, state(game).revision, current_ref(state(game), 2)
    )
    cover.acquire(
        PLAYER, "loyalty-cover-evidence", case, state(game).revision, "A synthetic receipt."
    )
    activate(cycle, game, period)
    game.dice = Dice((4, 5))
    worker, gateway = GameWorker(game), Gateway()
    inbox = InboxService(ledger)

    def refuse(number, discovered):
        started = game.issue_order(
            ADMIN, f"insurgent-order:{number}", 900, 3, "Report to the notice board."
        )
        tick(worker, gateway, 4)
        answer(game, OTHER, "order_response", options=("disobey",))
        identity = game.begin(
            OTHER,
            f"insurgent-refusal:{number}",
            900,
            state(game).sheets["3"].revision,
            PlayInput(
                play="disobey_orders",
                order_id=started["order_id"],
                parent=started["action_id"],
                context="I refuse to report to the notice board.",
                trigger_confirmed=True,
                heat=0,
                witnessed=False,
            ),
        )["action_id"]
        tick(worker, gateway, 4)
        pass_tags(game)
        answer(game, OTHER, "actor_disobey", options=("tag_heat",), number=1, text="Defiant")
        answer(game, ADMIN, "handler_disobey", flag=discovered)
        return identity

    async def submit_choice(owner, choice, sequence, detail):
        click = current(owner.user_id, sequence)
        await click.response.defer(ephemeral=True)
        item = next(x for x in inbox.items(owner) if x.identity == choice["id"])
        await InboxView(inbox, owner.user_id).route(click, item)
        form = click.edit_original_response.call_args.kwargs["view"]
        form.values.update(flag=("yes",), text=detail)
        sent = current(owner.user_id, sequence + 1)
        await form.confirm.callback(sent)
        assert form.completed, (sent.followup.send.call_args, sent.edit_original_response.call_args)

    first = refuse(1, False)
    assert game.inspect(OTHER, first)["state"] == "complete"
    assert not any(row["kind"] == WATCH for row in game.choices(ADMIN))
    subject = current_ref(state(game), 3)
    assert not labels(state(game), subject)
    tick(worker, gateway, 5)

    witnessed = refuse(2, True)
    (watch,) = (x for x in game.choices(ADMIN) if x["kind"] == WATCH)
    with pytest.raises(WorkflowError):
        game.respond(
            OTHER,
            "observe-for-handler",
            watch["id"],
            watch["revision"],
            ChoiceAnswer(flag=True, text="Not mine."),
        )
    asyncio.run(
        submit_choice(ADMIN, watch, 47900, "I observed an actual lapse in Foundation loyalty.")
    )
    original = state(game)
    (first_label,) = labels(original, subject)
    assert first_label.action == witnessed and first_label.status == "surveilled"
    tag = next(x for x in original.sheets["3"].tags if x.id == first_label.tag)
    assert tag.label == "Surveilled" and set(tag.observers) == {1, 3}
    tick(worker, gateway, 5)

    third = refuse(3, True)
    answer(game, OTHER, REVEAL, flag=False)
    assert len(labels(state(game), subject)) == 1
    assert game.inspect(OTHER, third)["state"] == "complete"
    tick(worker, gateway, 5)

    disclosed = refuse(4, True)
    (disclosure,) = (x for x in game.choices(OTHER) if x["kind"] == REVEAL)
    for unauthorized in (ADMIN, PLAYER):
        assert disclosure["id"] not in {x.identity for x in inbox.items(unauthorized)}
        with pytest.raises(WorkflowError):
            game.respond(
                unauthorized,
                "disclose-for-girl",
                disclosure["id"],
                disclosure["revision"],
                ChoiceAnswer(flag=True, text="Not mine."),
            )
    ledger.safety(PLAYER, "pause-disclosure", ledger.status(PLAYER)["revision"], pause=True)
    with pytest.raises(WorkflowError, match="SAFETY_PAUSED"):
        game.respond(
            OTHER,
            "paused-disclosure",
            disclosure["id"],
            disclosure["revision"],
            ChoiceAnswer(flag=True, text="Private."),
        )
    ledger.safety(PLAYER, "resume-disclosure", ledger.status(PLAYER)["revision"], pause=False)
    ledger.engine.dispose()
    confession = "PRIVATE_ACTUAL_SYMPATHY"
    asyncio.run(submit_choice(OTHER, disclosure, 47910, confession))
    game.respond(
        OTHER,
        "47911",
        disclosure["id"],
        disclosure["revision"],
        ChoiceAnswer(flag=True, text=confession),
    )
    canonical = state(game)
    first_label, admitted = labels(canonical, subject)
    assert admitted.action == disclosed and admitted.status == "sympathizer"
    assert any(
        x.id == admitted.tag and x.label == "Sympathizer" for x in canonical.sheets["3"].tags
    )
    assert confession not in str(game.inspect(PLAYER, disclosed))
    (debt,) = (x for x in canonical.obligations if x.details.get("cause") == RULE)
    assert debt.state == "pending" and debt.owner == 3 and debt.target == 1
    tick(worker, gateway, 5)

    discipline = PunishmentService(ledger)
    work = f"{period}:m2-punishment:{debt.id}"
    context = discipline.get(ADMIN, work)
    discipline.propose_scene(
        ADMIN,
        "private-loyalty-scene",
        work,
        context["revision"],
        context["game_revision"],
        "Synthetic office discipline.",
    )
    for viewer in (ADMIN, OTHER):
        evidence = discipline.get(viewer, work)
        discipline.attest_scene(
            viewer,
            "loyalty-attend:" + str(viewer.user_id),
            work,
            evidence["revision"],
            evidence["game_revision"],
        )
    before = state(game).sheets["3"].heat
    submit(discipline, ADMIN, work, Details(kind="stimulant_injection"))
    actual = state(game)
    assert actual.sheets["3"].heat == before + 7
    assert next(x for x in actual.obligations if x.id == debt.id).state == "fulfilled"
    assert game.dice.calls == 4
