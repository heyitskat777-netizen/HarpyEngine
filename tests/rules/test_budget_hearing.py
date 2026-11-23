"""A saved High Budget 3.1 roll leads to a private, independently owned hearing."""

import asyncio

import pytest
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state
from test_mission_ui import current
from test_off_duty_cycle import activate
from test_strain_service import prepared, ready
from test_void_leave import native
from test_world import gorgon, initial

from girlframe.database import tables as t
from girlframe.discord_adapter.inbox import InboxView
from girlframe.discord_adapter.m3_strain_effects import DependentForm
from girlframe.engine.m3_budget_hearing import RULE, hearings
from girlframe.engine.m3_strain_effects import Choice
from girlframe.engine.m3_world_state import Npc
from girlframe.services.inbox import InboxService
from girlframe.services.m3_budget_hearing import HearingService
from girlframe.services.m3_npc_roles import NpcRoleService
from girlframe.services.m3_off_duty_cycle import CycleService
from girlframe.services.m3_strain_effects import EffectService
from girlframe.services.m3_world import WorldService
from girlframe.services.onboarding import WorkflowError


@pytest.mark.parametrize("finding", ("dismiss", "refer"))
def test_high_budget_hearing_preserves_solo_choice_and_required_effect(ledger, finding):
    strain, game = ready(ledger)
    approval = ledger.policy.m3_approval
    ledger.policy = ledger.policy.model_copy(
        update={
            "m3_approval": approval.model_copy(
                update={"subsystems": approval.subsystems | {"world", "plays"}}
            )
        }
    )
    worlds = WorldService(strain.missions)
    world = initial()
    worlds.initialize(
        ADMIN, "hearing-world", state(game).revision, world.board, world.locations, world.gorgons[0]
    )
    roles = NpcRoleService(worlds)
    offered = roles.offer(
        ADMIN,
        "hearing-authority",
        state(game).revision,
        Npc(
            id="hearing-director",
            name="Hearing Director",
            jobs=("director",),
            controller=3,
            detail="Separately controlled higher authority",
            cell=(0, 0),
            revealed=True,
        ),
    )
    roles.respond(OTHER, "hearing-authority-accept", offered["id"], state(game).revision, "accept")
    with ledger.transaction() as c:
        canon = state(game)
        for character in canon.sheets.values():
            for asset in character.assets:
                asset.void = False
        game.event(c, 1, "hearing-void-fixture", "synthetic.no_void_assets", canon)
    period = prepared(strain, game, high=frozenset({"budget"}))
    effects = EffectService(strain)
    service = HearingService(strain)
    for track, face, column, choice in (
        (
            "void",
            2,
            1,
            Choice(
                rule_id="strain.void.low.2.1",
                account="A Gorgon arrives.",
                gorgon=gorgon("dormant", "near-hearing", (0, 1)),
            ),
        ),
        ("rebellion", 1, 2, Choice(rule_id="strain.rebellion.low.1.2", account="Control slips.")),
        ("budget", 3, 1, None),
    ):
        request = next(x for x in state(game).strain.requests if x.track == track)
        strain.dice.face = face
        assert (
            strain.roll(ADMIN, "hearing-die-" + track, request.id, 1, state(game).revision)["face"]
            == face
        )
        strain.choose(ADMIN, "hearing-column-" + track, request.id, 2, state(game).revision, column)
        work = request.id + ":effect"
        if choice is not None:
            assert (
                effects.apply(
                    ADMIN, "hearing-effect-" + track, work, 1, state(game).revision, choice
                )["state"]
                == "resolved"
            )
    assert effects.get(ADMIN, work)["rule_id"] == RULE
    cycle = CycleService(strain.periods)
    with pytest.raises(WorkflowError, match="work|Strain|effect"):
        activate(cycle, game, period)

    async def stage_native():
        inbox = InboxService(ledger)
        entry = next(x for x in inbox.items(ADMIN) if x.identity == work)
        interaction = current(1, 40100)
        await interaction.response.defer(ephemeral=True)
        await InboxView(inbox, 1).route(interaction, entry)
        form = interaction.edit_original_response.call_args.kwargs["view"]
        assert isinstance(form, DependentForm)
        form.values.update(
            civic_director=("hearing-director",), hearing_girl=("2",), account="Hearing scheduled."
        )
        submitted = current(1, 40101)
        await form.confirm.callback(submitted)
        assert form.completed, submitted.edit_original_response.call_args

    asyncio.run(stage_native())
    assert effects.get(ADMIN, work)["awaiting_budget_hearing"]
    assert not any(x.identity == work for x in InboxService(ledger).items(PLAYER))
    with pytest.raises(WorkflowError, match="original parties"):
        service.get(ADMIN, work)
    with pytest.raises(WorkflowError, match="original parties"):
        service.get(PLAYER, work)
    native(
        ledger,
        OTHER,
        work,
        "m3_budget_hearing",
        40110,
        choice=("notify",),
        account="PRIVATE_ACCUSATION",
    )
    assert service.get(PLAYER, work)["charge"] == "PRIVATE_ACCUSATION"
    revision = state(game).revision
    with pytest.raises(WorkflowError, match="original speaker"):
        service.respond(OTHER, "director-cannot-answer", work, revision, "answer", "Fake defense")
    with pytest.raises(WorkflowError, match="STALE_STATE"):
        service.respond(PLAYER, "stale-answer", work, revision - 1, "answer", "Actual response")
    ledger.safety(PLAYER, "pause-hearing", ledger.status(PLAYER)["revision"], pause=True)
    with pytest.raises(WorkflowError, match="SAFETY_PAUSED"):
        service.respond(PLAYER, "paused-answer", work, revision, "answer", "Actual response")
    ledger.safety(PLAYER, "resume-hearing", ledger.status(PLAYER)["revision"], pause=False)
    with ledger.transaction() as c:
        c.execute(
            t.members.update()
            .where(t.members.c.campaign_id == ledger.campaign_id, t.members.c.user_id == "2")
            .values(active=False)
        )
    with pytest.raises(WorkflowError, match="Join this campaign"):
        service.get(PLAYER, work)
    with ledger.transaction() as c:
        c.execute(
            t.members.update()
            .where(t.members.c.campaign_id == ledger.campaign_id, t.members.c.user_id == "2")
            .values(active=True)
        )
    revision = state(game).revision
    native(
        ledger,
        PLAYER,
        work,
        "m3_budget_hearing",
        40120,
        choice=("answer",),
        account="PRIVATE_RESPONSE",
    )
    assert (
        service.respond(PLAYER, "40121", work, revision, "answer", "PRIVATE_RESPONSE")["phase"]
        == "finding"
    )
    assert service.get(OTHER, work)["defense"] == "PRIVATE_RESPONSE"
    with pytest.raises(WorkflowError, match="original speaker"):
        service.respond(PLAYER, "cannot-find", work, state(game).revision, finding, "fake decision")
    assert "PRIVATE_RESPONSE" not in str(InboxService(ledger).items(ADMIN))
    assert "PRIVATE_ACCUSATION" not in str(effects.get(ADMIN, work))
    ledger.engine.dispose()
    native(
        ledger,
        OTHER,
        work,
        "m3_budget_hearing",
        40130,
        choice=(finding,),
        account="PRIVATE_FINDING",
    )
    assert service.get(PLAYER, work)["finding"] == "PRIVATE_FINDING"
    (saved,) = hearings(state(game))
    assert saved.girl.entity == "2" and saved.controller == 3
    assert len({saved.source, saved.notice_event, saved.answer_event, saved.finding_event}) == 4
    assert not state(game).career_archives and "2" in state(game).sheets
    if finding == "dismiss":
        assert effects.get(ADMIN, work)["state"] == "resolved"
        assert activate(cycle, game, period)["phase"] == "active"
    else:
        assert effects.get(ADMIN, work)["state"] == "pending"
        assert not service.get(OTHER, work)["options"]
        with pytest.raises(WorkflowError, match="work|Strain|effect"):
            activate(cycle, game, period)
