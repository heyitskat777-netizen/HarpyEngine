"""An earned Successor uses actual advice and real native lessons before benefits."""

import asyncio

import pytest
from handler_award_scenario import ordinary_pr_award
from test_enforcer_requisitions import approved
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Dice, answer, pass_tags, state, tick
from test_mission_ui import current

from girlframe.discord_adapter.inbox import InboxView
from girlframe.discord_adapter.m3_handler_advancements import AcquireMore, open_advancement
from girlframe.engine.m2 import PlayInput
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_handler_advancements import awards
from girlframe.engine.m3_handler_ordinary import RULE as ordinary_rule
from girlframe.engine.m3_handler_play_state import Effect
from girlframe.engine.m3_successor import RULE, acquisitions, earned, stars
from girlframe.services.inbox import InboxService
from girlframe.services.m3_handler_advancements import HandlerAdvancementService
from girlframe.services.m3_handler_plays import HandlerPlayService
from girlframe.services.m3_successor import SuccessorService
from girlframe.services.onboarding import WorkflowError


def test_owned_advice_and_actual_lessons_complete_three_star_successor_milestone(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway = ordinary_pr_award(ledger, tmp_path, monkeypatch)
    approved(ledger, game, tmp_path, monkeypatch, extra=(ordinary_rule, RULE))
    plays, service, inbox = (
        HandlerPlayService(ledger),
        SuccessorService(ledger),
        InboxService(ledger),
    )
    game.dice = Dice((4, 5))
    original = state(game)
    (award,) = awards(original)
    target = current_ref(original, 3)
    with pytest.raises(WorkflowError, match="Acquire the actual"):
        plays.start(ADMIN, "forged-advice", original.revision, (target,), advice_scene=900)

    async def buy():
        click = current(1, 48300)
        await click.response.defer(ephemeral=True)
        await open_advancement(click, HandlerAdvancementService(ledger), award.id)
        form = click.edit_original_response.call_args.kwargs["view"]
        more = next(x for x in form.children if isinstance(x, AcquireMore))
        menu_click = current(1, 48301)
        await menu_click.response.defer(ephemeral=True)
        await more.callback(menu_click)
        menu = menu_click.edit_original_response.call_args.kwargs["view"]
        menu.values.update(advancement=("successor",))
        picked = current(1, 48302)
        await menu.confirm.callback(picked)
        assert menu.completed
        payment = picked.edit_original_response.call_args.kwargs["view"]
        payment.values.update(account="Train an actual Successor.")
        sent = current(1, 48303)
        await payment.confirm.callback(sent)
        assert payment.completed, (
            sent.followup.send.call_args,
            sent.edit_original_response.call_args,
        )

    asyncio.run(buy())
    (acquired,) = acquisitions(state(game))
    assert service.buy(
        ADMIN, "48303", award.id, original.revision, "Train an actual Successor."
    ) == dict(
        id=acquired.id,
        phase="held",
    )
    assert HandlerAdvancementService(ledger).view(ADMIN, award.id)["acquisition"] == acquired.id
    assert plays.options(ADMIN)["successor"]
    assert not any(x.identity == acquired.id for x in inbox.items(OTHER))

    def perform(number):
        action = game.begin(
            OTHER,
            f"successor-lesson:{number}",
            900,
            state(game).sheets["3"].revision,
            PlayInput(
                play="keep_your_head",
                trigger_confirmed=True,
                heat=0,
                context="I lead the preparations while the Handler observes.",
            ),
        )["action_id"]
        tick(worker, gateway, 4)
        pass_tags(game)
        answer(game, OTHER, "actor_keep", options=("tough", "in_control"), denied=("desperate",))
        answer(game, ADMIN, "handler_keep", flag=True, text="I watched the orderly preparation.")
        tick(worker, gateway, 5)
        assert game.inspect(OTHER, action)["state"] == "complete"
        return action

    async def judge(identity, grant, lesson, sequence):
        click = current(1, sequence)
        await click.response.defer(ephemeral=True)
        item = next(x for x in inbox.items(ADMIN) if x.identity == identity)
        await InboxView(inbox, 1).route(click, item)
        form = click.edit_original_response.call_args.kwargs["view"]
        form.values.update(
            operation=("award",),
            advice=(grant,),
            lesson=(lesson,),
            account="I observed her use the advice.",
        )
        form.controls()
        sent = current(1, sequence + 1)
        await form.confirm.callback(sent)
        assert form.completed, (sent.followup.send.call_args, sent.edit_original_response.call_args)

    prior = perform(0)
    before = state(game).sheets["3"].permissions
    for number in (1, 2, 3):
        grant = plays.start(
            ADMIN, f"actual-advice:{number}", state(game).revision, (target,), advice_scene=900
        )
        wording = "PRIVATE_LEADERSHIP_ADVICE_" + str(number)
        plays.submit(
            ADMIN,
            f"give-advice:{number}",
            grant["id"],
            grant["game_revision"],
            "successor_advice",
            Effect(kind="successor_advice", account=wording),
        )
        assert plays.notice(OTHER, grant["id"])["account"] == wording
        with pytest.raises(WorkflowError):
            plays.notice(PLAYER, grant["id"])
        if number == 1:
            with pytest.raises(WorkflowError, match="later real Play"):
                service.judge(
                    ADMIN,
                    "old-lesson-is-stale",
                    acquired.id,
                    state(game).revision,
                    grant["id"],
                    prior,
                    "Earlier than the advice.",
                )
        lesson = perform(number)
        revision = state(game).revision
        with pytest.raises(WorkflowError):
            service.judge(
                OTHER,
                f"wrong-star-owner:{number}",
                acquired.id,
                revision,
                grant["id"],
                lesson,
                "I award myself.",
            )
        ledger.engine.dispose()
        sequence = 48400 + number * 10
        asyncio.run(judge(acquired.id, grant["id"], lesson, sequence))
        assert (
            service.judge(
                ADMIN,
                str(sequence + 1),
                acquired.id,
                revision,
                grant["id"],
                lesson,
                "I observed her use the advice.",
            )["girl"]
            == "3"
        )
        assert state(game).sheets["3"].permissions == before + int(number == 3)
    canon = state(game)
    (milestone,) = earned(canon)
    assert milestone.girl == target and len(stars(canon)) == 3
    assert canon.order[0] == 3
    pending = game.begin(
        PLAYER,
        "ongoing-unrelated-to-star",
        900,
        canon.sheets["2"].revision,
        PlayInput(
            play="keep_your_head",
            trigger_confirmed=True,
            heat=0,
            context="I prepare independently of the Gold Star decision.",
        ),
    )["action_id"]
    tick(worker, gateway, 4)
    with ledger.engine.connect() as c:
        receipt = game.action(c, pending)["data"]["receipt"]
    service.remove(
        ADMIN, "remove-actual-star", acquired.id, state(game).revision, milestone.stars[0]
    )
    latest = state(game)
    assert len([x for x in stars(latest) if x.removed_event is None]) == 2
    assert earned(latest) == (milestone,) and latest.sheets["3"].permissions == before + 1
    with ledger.engine.connect() as c:
        assert game.action(c, pending)["data"]["receipt"] == receipt
