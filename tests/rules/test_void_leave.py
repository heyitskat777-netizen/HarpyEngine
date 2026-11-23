"""A real Void leave changes presence and awaits the original players' decisions."""

import asyncio

import pytest
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import start, state
from test_mission_ui import current
from test_off_duty_cycle import activate, call, movement, recover_both
from test_void_lab_portal import prepare_endgame

from girlframe.discord_adapter.inbox import InboxView
from girlframe.discord_adapter.m2_forms import NativeForm
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_handler_consequences import active_handler
from girlframe.engine.m3_void_leave import leaves
from girlframe.services.inbox import InboxService
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_off_duty_cycle import CycleService
from girlframe.services.m3_void_leave import LeaveService
from girlframe.services.onboarding import WorkflowError


def native(store, viewer, identity, task, number, **values):
    async def run():
        inbox = InboxService(store)
        card = next(x for x in inbox.items(viewer) if x.identity == identity and x.task == task)
        click = current(viewer.user_id, number)
        await click.response.defer(ephemeral=True)
        await InboxView(inbox, viewer.user_id).route(click, card)
        form = click.edit_original_response.call_args.kwargs["view"]
        assert isinstance(form, NativeForm)
        form.values.update(values)
        submitted = current(viewer.user_id, number + 1)
        await form.confirm.callback(submitted)
        assert form.completed, submitted.edit_original_response.call_args

    asyncio.run(run())


@pytest.mark.parametrize("decision", ("continue", "close"))
def test_actual_void_leave_respects_original_preference_and_campaign_decision(ledger, decision):
    strain, game, _, period, work = prepare_endgame(ledger, slot=1)
    service = LeaveService(ledger)
    cycle = CycleService(strain.periods)
    handler = active_handler(state(game))
    assert handler is not None
    with ledger.transaction() as c:
        old = state(game)
        old.facts.append(
            dict(
                kind="ordinary_handler_movement",
                actor=handler.model_dump_json(),
                cell="[0,0]",
                event="fixture-known-home-base",
            )
        )
        game.event(c, 1, "known-home-base", "synthetic.original_handler_position", old)

    def physical():
        with ledger.engine.connect() as c:
            return resolve(state(game), handler, profiles(c, ledger.campaign_id))

    revision = state(game).revision
    home, account = "PRIVATE_HOMETOWN", "PRIVATE_LEAVE_SCENE"
    assert physical().cell == (0, 0) and physical().offstage_source is None
    with pytest.raises(WorkflowError, match="outside Quadrant 12"):
        service.approve(ADMIN, "bad-quadrant", work, 1, revision, home, 12, account)
    with pytest.raises(WorkflowError, match="original Endgame Handler"):
        service.approve(OTHER, "wrong-owner", work, 1, revision, home, 9, account)
    with pytest.raises(WorkflowError, match="STALE_VOID_LEAVE"):
        service.approve(ADMIN, "stale-home", work, 1, revision - 1, home, 9, account)
    assert not any(x.identity == work for x in InboxService(ledger).items(PLAYER))
    native(
        ledger,
        ADMIN,
        work,
        "m3_void_leave",
        39800,
        bond=("your-hometown",),
        home=home,
        quadrant="9",
        account=account,
    )
    assert (
        service.approve(ADMIN, "39801", work, 1, revision, home, 9, account)["state"] == "reserved"
    )
    before = leaves(state(game))[0]
    assert before.departed is None and physical().cell == (0, 0)
    assert activate(cycle, game, period)["phase"] == "active"
    departed = leaves(state(game))[0]
    assert (
        departed.departed
        and physical().offstage_source == departed.departed
        and physical().cell is None
    )
    assert cycle.review(PLAYER, period)["handler_scene"] is None
    assert cycle.review(ADMIN, period)["handler_scene"]["kind"] == "void_leave"
    assert not any(x.task == "m3_void_leave_poll" for x in InboxService(ledger).items(OTHER))
    recover_both(cycle, game, period)
    call(cycle, game, ADMIN, period, "acknowledge", None)
    call(cycle, game, ADMIN, period, "review_status", (2, 3), "Actual Cadre review")
    assert call(cycle, game, ADMIN, period, "finish", movement(game))["phase"] == "complete"
    assert leaves(state(game))[0].returned and physical().cell == (0, 0)
    assert physical().offstage_source is None
    with pytest.raises(WorkflowError, match="original players"):
        strain.missions.offer(ADMIN, "next-mission-early", "Return to the warfront", (2,))
    with pytest.raises(WorkflowError, match="every original player"):
        service.respond(ADMIN, "manager-cannot-choose-early", work, state(game).revision, decision)
    native(ledger, PLAYER, work, "m3_void_leave_poll", 39810, preference=("continue",))
    assert service.followup(OTHER, work)["votes"] == ()
    assert service.followup(ADMIN, work)["votes"][0].preference == "continue"
    with pytest.raises(WorkflowError, match="one preference"):
        service.respond(PLAYER, "double-own-vote", work, state(game).revision, "close")
    ledger.safety(OTHER, "pause-leave-vote", ledger.status(OTHER)["revision"], pause=True)
    with pytest.raises(WorkflowError, match="SAFETY_PAUSED"):
        service.respond(OTHER, "paused-vote", work, state(game).revision, "close")
    ledger.safety(OTHER, "resume-leave-vote", ledger.status(OTHER)["revision"], pause=False)
    native(ledger, OTHER, work, "m3_void_leave_poll", 39820, preference=("close",))
    assert service.followup(PLAYER, work)["votes"][0].preference == "continue"
    ledger.engine.dispose()
    revision = state(game).revision
    native(ledger, ADMIN, work, "m3_void_leave_poll", 39830, preference=(decision,))
    assert service.respond(ADMIN, "39831", work, revision, decision)["decision"] == decision
    saved = leaves(state(game))[0]
    assert tuple(x.preference for x in saved.votes) == ("continue", "close")
    assert LeaveService(ledger).followup(OTHER, work)["decision"] == decision
    if decision == "continue":
        assert (
            strain.missions.offer(ADMIN, "next-warfront-mission", "Return to the warfront", (2,))[
                "phase"
            ]
            == "offered"
        )
    else:
        with pytest.raises(WorkflowError, match="drew this campaign to a close"):
            start(game)
        with pytest.raises(WorkflowError, match="drew this campaign to a close"):
            strain.periods.begin(ADMIN, "new-period-after-ending")
