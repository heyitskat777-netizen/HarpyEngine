"""An actual Void award retires one original body, then an owned successor activates."""

import asyncio

import pytest
from test_handler_creation import agree, complete
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state
from test_mission_ui import current
from test_off_duty_cycle import activate, call, finish_routine, movement, recover_both
from test_void_lab_portal import prepare_endgame

from girlframe.discord_adapter.inbox import InboxView
from girlframe.discord_adapter.m2_forms import NativeForm
from girlframe.engine.m3_handler_consequences import active_handler
from girlframe.engine.m3_handler_retirement import awards
from girlframe.services.inbox import InboxService
from girlframe.services.m3_handler_creation import HandlerCreationService
from girlframe.services.m3_handler_retirement import RetirementService
from girlframe.services.m3_off_duty_cycle import CycleService
from girlframe.services.onboarding import WorkflowError


def test_actual_medal_retirement_and_fresh_owned_successor(ledger):
    strain, game, _, period, identity = prepare_endgame(ledger, slot=3)
    cycle = CycleService(strain.periods)
    service = RetirementService(ledger)
    handler = active_handler(state(game))
    data = service.view(ADMIN, identity)
    assert data["state"] == "pending" and data["award"] is None
    assert not any(x.identity == identity for x in InboxService(ledger).items(PLAYER))
    with pytest.raises(WorkflowError, match="actual Strain|work"):
        activate(cycle, game, period)
    rev = state(game).revision
    medal, home, account = "Distinguished Service", "PRIVATE_SAFE_HOME", "PRIVATE_DEPARTURE"
    with pytest.raises(WorkflowError, match="original Endgame Handler"):
        service.award(OTHER, "wrong-owner", identity, 1, rev, medal, home, account)
    with pytest.raises(WorkflowError, match="STALE_HANDLER_RETIREMENT"):
        service.award(ADMIN, "stale", identity, 1, rev - 1, medal, home, account)
    ledger.safety(OTHER, "pause-award", ledger.status(OTHER)["revision"], pause=True)
    with pytest.raises(WorkflowError, match="SAFETY_PAUSED"):
        service.award(ADMIN, "paused", identity, 1, rev, medal, home, account)
    ledger.safety(OTHER, "resume-award", ledger.status(OTHER)["revision"], pause=False)

    async def native():
        inbox = InboxService(ledger)
        card = next(x for x in inbox.items(ADMIN) if x.identity == identity)
        assert card.task == "m3_handler_retirement"
        click = current(1, 89700)
        await click.response.defer(ephemeral=True)
        await InboxView(inbox, 1).route(click, card)
        form = click.edit_original_response.call_args.kwargs["view"]
        assert isinstance(form, NativeForm)
        form.values.update(medal=medal, home=home, account=account)
        await form.confirm.callback(current(1, 89701))
        assert form.completed

    asyncio.run(native())
    assert (
        service.award(ADMIN, "89701", identity, 1, rev, medal, home, account)["state"] == "resolved"
    )
    assert service.view(ADMIN, identity)["award"].retired is None
    assert active_handler(state(game)) == handler
    activate(cycle, game, period)
    recover_both(cycle, game, period)
    finish_routine(cycle, game, period)
    result = call(cycle, game, ADMIN, period, "finish", movement(game))
    assert result["phase"] == "complete"
    before = state(game)
    assert active_handler(before) is None and before.handler == ADMIN.user_id
    (award,) = awards(before)
    archive = before.handler_archives[-1]
    assert archive.actor == handler and archive.ending == "retired" and archive.alive
    assert award.retired == archive.source_event and award.awarded != award.retired
    with pytest.raises(WorkflowError, match="actual successor Handler"):
        strain.periods.begin(ADMIN, "no-successor")
    with pytest.raises(WorkflowError, match="actual successor Handler"):
        strain.missions.offer(ADMIN, "mission-no-successor", "The next mission.", (2,))
    with pytest.raises(WorkflowError, match="actual successor Handler"):
        game.issue_order(ADMIN, "order-no-successor", 900, 2, "Hold.")
    with pytest.raises(WorkflowError, match="original Endgame Handler"):
        service.view(OTHER, identity)

    ledger.engine.dispose()
    assert RetirementService(ledger).view(ADMIN, identity)["award"] == award
    policy = ledger.policy.owner_m3_rulings
    ledger.policy = ledger.policy.model_copy(
        update=dict(
            owner_m3_rulings=policy.model_copy(
                update=dict(handler_creation="owned_shared_choices_preserve_existing")
            )
        )
    )
    creation = HandlerCreationService(ledger)
    preview = creation.view(ADMIN)
    draft = complete(creation, "Advocate").model_copy(update=dict(name="The actual successor"))
    creation.save(
        ADMIN,
        "fresh-handler",
        preview["revision"],
        preview["appointment"],
        draft,
        generation=preview["generation"],
    )
    agree(creation, generation=preview["generation"])
    preview = creation.view(ADMIN)
    creation.activate(ADMIN, "successor-active", preview["revision"], state(game).revision, True)
    after = state(game)
    assert active_handler(after) not in (None, handler)
    assert after.handler_persona.draft.name == "The actual successor"
    assert after.handler_archives == before.handler_archives and awards(after) == (award,)
    assert strain.periods.begin(ADMIN, "successor-off-duty")["phase"] == "preparing"
