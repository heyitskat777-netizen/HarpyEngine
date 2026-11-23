"""An actual Budget Endgame uses owned court statements and an actual fate."""

import asyncio

import pytest
from test_budget_persistent_tag import source
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state
from test_mission_ui import current
from test_off_duty_cycle import activate, call, finish_routine, movement, recover_both
from test_world import gorgon, initial

from girlframe.discord_adapter.inbox import InboxView
from girlframe.discord_adapter.m2_forms import NativeForm
from girlframe.engine.m3_budget_trial import RULE, trials
from girlframe.engine.m3_handler_consequences import active_handler
from girlframe.engine.m3_strain_effects import Choice
from girlframe.engine.m3_world_state import Npc
from girlframe.services.inbox import InboxService
from girlframe.services.m3_budget_trial import TrialService
from girlframe.services.m3_npc_roles import NpcRoleService
from girlframe.services.m3_off_duty_cycle import CycleService
from girlframe.services.m3_strain_effects import EffectService
from girlframe.services.m3_world import WorldService
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer


@pytest.mark.parametrize("finding", ("save", "condemn"))
def test_budget_warcrime_trial_preserves_actual_cadre_and_handler_fate(ledger, finding):
    _, game, strain, work, period = source(ledger, option=1, without_void=True)
    approval = ledger.policy.m3_approval
    ledger.policy = ledger.policy.model_copy(
        update=dict(
            m3_approval=approval.model_copy(update=dict(subsystems=approval.subsystems | {"world"}))
        )
    )
    authority = GuildViewer(4, 200, True, False)
    bystander = GuildViewer(5, 200, True, False)
    ledger.join(authority, "original-trial-authority")
    ledger.join(bystander, "unrelated-trial-bystander")
    world = initial()
    worlds = WorldService(strain.missions)
    worlds.initialize(
        ADMIN, "trial-world", state(game).revision, world.board, world.locations, world.gorgons[0]
    )
    roles = NpcRoleService(worlds)
    director = Npc(
        id="warcrime-judge",
        name="Trial Director",
        jobs=("director",),
        controller=4,
        detail="Separately controlled authority",
        cell=(0, 0),
        revealed=True,
    )
    offer = roles.offer(ADMIN, "actual-trial-authority", state(game).revision, director)
    roles.respond(authority, "court-authority-accept", offer["id"], state(game).revision, "accept")
    effects = EffectService(strain)
    assert state(game).strain.endgames[-1].rule_id == RULE
    for index, request in enumerate(tuple(state(game).strain.requests)):
        if request.track == "void":
            face, column, choice = (
                2,
                1,
                Choice(
                    rule_id="strain.void.low.2.1",
                    account="Unrelated arrival.",
                    gorgon=gorgon("dormant", "trial-other-void-" + str(index), (0, 1)),
                ),
            )
        elif request.track == "rebellion":
            face, column, choice = (
                1,
                2,
                Choice(rule_id="strain.rebellion.low.1.2", account="Control slips."),
            )
        else:
            face, column, choice = (
                5,
                2,
                Choice(rule_id="strain.budget.low.5.2", account="Unrelated room.", rooms=((2, 3),)),
            )
        strain.dice.face = face
        strain.roll(ADMIN, f"trial-other-roll-{index}", request.id, 1, state(game).revision)
        strain.choose(
            ADMIN, f"trial-other-column-{index}", request.id, 2, state(game).revision, column
        )
        effects.apply(
            ADMIN,
            f"trial-other-effect-{index}",
            request.id + ":effect",
            1,
            state(game).revision,
            choice,
        )

    inbox = InboxService(ledger)

    async def native(viewer, number, **values):
        click = current(viewer.user_id, number)
        await click.response.defer(ephemeral=True)
        cards = [
            x for x in inbox.items(viewer) if x.identity == work and x.task == "m3_budget_trial"
        ]
        assert len(cards) == 1
        await InboxView(inbox, viewer.user_id).route(click, cards[0])
        form = click.edit_original_response.call_args.kwargs["view"]
        assert isinstance(form, NativeForm)
        form.values.update(values)
        submit = current(viewer.user_id, number + 1)
        await form.confirm.callback(submit)
        assert form.completed, (
            submit.followup.send.call_args,
            submit.edit_original_response.call_args,
        )

    service = TrialService(strain)
    cycle = CycleService(strain.periods)
    original = active_handler(state(game))
    asyncio.run(native(ADMIN, 42300, director=(director.id,)))
    with pytest.raises(WorkflowError, match="actual Strain|work"):
        activate(cycle, game, period)
    with pytest.raises(WorkflowError, match="original parties"):
        service.view(PLAYER, work)
    ledger.safety(PLAYER, "pause-trial", ledger.status(PLAYER)["revision"], pause=True)
    with pytest.raises(WorkflowError, match="SAFETY_PAUSED"):
        service.respond(
            authority, "paused-trial", work, state(game).revision, "charge", "Actual charge."
        )
    ledger.safety(PLAYER, "resume-trial", ledger.status(PLAYER)["revision"], pause=False)
    asyncio.run(native(authority, 42310, choice=("charge",), account="PRIVATE_TRIAL_CHARGE"))
    assert service.view(PLAYER, work)["charge"] == "PRIVATE_TRIAL_CHARGE"
    with pytest.raises(WorkflowError, match="original parties"):
        service.view(bystander, work)
    with pytest.raises(WorkflowError, match="original speaker"):
        service.respond(
            authority, "premature-sentence", work, state(game).revision, finding, "Premature"
        )
    with pytest.raises(WorkflowError, match="STALE_STATE"):
        service.respond(
            ADMIN, "stale-trial", work, state(game).revision - 1, "answer", "Original defense"
        )
    asyncio.run(native(ADMIN, 42320, choice=("answer",), account="PRIVATE_HANDLER_ACCOUNT"))
    asyncio.run(
        native(
            PLAYER,
            42330,
            choice=("defend" if finding == "save" else "pass",),
            account="PRIVATE_FIRST_CADRE_ACCOUNT",
        )
    )
    asyncio.run(native(OTHER, 42340, choice=("pass",), account="PRIVATE_SECOND_CADRE_ACCOUNT"))
    assert service.view(OTHER, work)["statements"] == (
        dict(decision="pass", account="PRIVATE_SECOND_CADRE_ACCOUNT"),
    )
    assert len(service.view(authority, work)["statements"]) == 3
    if finding == "condemn":
        with pytest.raises(WorkflowError, match="original speaker"):
            service.respond(
                authority,
                "invented-rescue",
                work,
                state(game).revision,
                "save",
                "No defense happened",
            )
    revision = state(game).revision
    result = "The Cadre saved the Handler." if finding == "save" else "The actual sentence."
    asyncio.run(native(authority, 42350, choice=(finding,), account=result))
    phase = "saved" if finding == "save" else "execution_due"
    assert service.respond(authority, "42351", work, revision, finding, result)["phase"] == phase
    ledger.engine.dispose()
    assert service.view(ADMIN, work)["phase"] == phase and active_handler(state(game)) == original
    with ledger.engine.connect() as c:
        assert strain._row(c, work)["state"] == ("resolved" if finding == "save" else "pending")
    assert activate(cycle, game, period)["phase"] == "active"
    recover_both(cycle, game, period)
    finish_routine(cycle, game, period)
    assert call(cycle, game, ADMIN, period, "finish", movement(game))["phase"] == "complete"
    with ledger.engine.connect() as c:
        assert strain._row(c, work)["state"] == "resolved"
    after = state(game)
    (trial,) = trials(after)
    if finding == "save":
        assert trial.phase == "saved" and active_handler(after) == original
    else:
        assert trial.phase == "executed" and active_handler(after) is None
        assert after.handler_archives[-1].source_event == trial.executed
        assert after.handler_archives[-1].actor == original and not after.handler_archives[-1].alive
        assert after.handler_fatal_sources[-1].source_work == work
        assert service.view(ADMIN, work)["phase"] == "executed"
        with pytest.raises(WorkflowError, match="actual successor Handler"):
            strain.periods.begin(ADMIN, "before-successor")
