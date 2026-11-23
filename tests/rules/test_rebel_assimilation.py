"""The printed employment Endgame changes the real faction and installs a usable Play."""

import asyncio

import pytest
from test_cast_service import change
from test_ledger import ADMIN, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state
from test_mission_ui import current
from test_strain_service import prepared, ready
from test_world import initial

from girlframe.discord_adapter.inbox import InboxView
from girlframe.discord_adapter.m2_forms import NativeForm
from girlframe.engine.m3_handler_consequences import active_handler
from girlframe.engine.m3_rebel_assimilation import (
    RULE,
    USE,
    EmploymentPlay,
    WorkPlayUse,
    assimilations,
)
from girlframe.engine.m3_world_state import Faction
from girlframe.services.inbox import InboxService
from girlframe.services.m3_actors import ActorService
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_rebel_assimilation import AssimilationService
from girlframe.services.m3_world import WorldService
from girlframe.services.onboarding import WorkflowError


def test_original_group_assimilates_and_handler_uses_new_employment_play(ledger):
    strain, game = ready(ledger, face=6)
    approval = ledger.policy.m3_approval
    ledger.policy = ledger.policy.model_copy(
        update=dict(
            m3_approval=approval.model_copy(
                update=dict(subsystems=approval.subsystems | {"world", "plays"}),
            )
        )
    )
    worlds = WorldService(strain.missions)
    world = initial()
    worlds.initialize(
        ADMIN,
        "assimilation-world",
        state(game).revision,
        world.board,
        world.locations,
        world.gorgons[0],
    )
    group = Faction(id="actual-employer", name="Actual Group", kind="rebel", cells=((0, 4),))
    worlds.faction(ADMIN, "actual-group", state(game).revision, group)
    prepared(strain, game, high=frozenset({"rebellion"}))
    index = 0
    while True:
        request = next(
            x
            for x in state(game).strain.requests
            if x.track == "rebellion" and (x.kind == "endgame" or x.severity == "high")
        )
        if request.kind == "endgame":
            break
        strain.roll(ADMIN, f"assimilation-roll-{index}", request.id, 1, state(game).revision)
        strain.choose(
            ADMIN, f"assimilation-cascade-{index}", request.id, 2, state(game).revision, 2
        )
        index += 1
    result = strain.choose(
        ADMIN,
        "assimilation-slot",
        request.id,
        1,
        state(game).revision,
        4,
        endgame=True,
        faction=group.id,
    )
    assert result["rule_id"] == RULE
    work = request.id + ":effect"
    service = AssimilationService(strain)
    inbox = InboxService(ledger)

    async def native(number, **values):
        click = current(1, number)
        click.channel_id = 900
        await click.response.defer(ephemeral=True)
        cards = [
            x
            for x in inbox.items(ADMIN)
            if x.identity == work and x.task == "m3_rebel_assimilation"
        ]
        assert len(cards) == 1
        await InboxView(inbox, 1).route(click, cards[0])
        controls = click.edit_original_response.call_args.kwargs["view"]
        assert isinstance(controls, NativeForm)
        controls.values.update(values)
        submit = current(1, number + 1)
        await controls.confirm.callback(submit)
        assert controls.completed, (
            submit.followup.send.call_args,
            submit.edit_original_response.call_args,
        )

    play = EmploymentPlay(
        title="Review charter requests",
        trigger="A charter request was received",
        result="Review the request as their Foundation liaison",
    )
    first = state(game)
    with pytest.raises(WorkflowError, match="original Handler"):
        service.install(PLAYER, "wrong-employment-author", work, first.revision, play)
    with pytest.raises(WorkflowError, match="STALE_STATE"):
        service.install(ADMIN, "stale-employment", work, first.revision - 1, play)
    asyncio.run(native(42900, **play.model_dump()))
    assert service.install(ADMIN, "42901", work, first.revision, play)["state"] == "resolved"
    canon = state(game)
    assert next(x for x in canon.world.factions if x.id == group.id) == group.model_copy(
        update=dict(kind="foundation")
    )
    assert canon.sheets == first.sheets and canon.handler_tags == first.handler_tags
    (migration,) = assimilations(canon)
    assert migration.original == group and migration.employment_play == play
    with pytest.raises(WorkflowError, match="original Handler"):
        service.view(PLAYER, work)
    assert not any(x.task == "m3_rebel_assimilation" for x in inbox.items(PLAYER))
    with pytest.raises(WorkflowError, match="actual joined scene"):
        service.use(
            ADMIN, "wrong-scene", work, canon.revision, 999, trigger_met=True, account="Wrong scene"
        )
    with pytest.raises(WorkflowError, match="actual joined scene"):
        service.use(
            ADMIN,
            "facilitating-is-separate",
            work,
            canon.revision,
            900,
            trigger_met=True,
            account="Only facilitating",
        )
    change(CastService(ActorService(strain.missions)), ADMIN, "join", active_handler(canon))
    canon = state(game)
    ledger.safety(PLAYER, "pause-work-play", ledger.status(PLAYER)["revision"], pause=True)
    with pytest.raises(WorkflowError, match="SAFETY_PAUSED"):
        service.use(
            ADMIN, "paused-work-play", work, canon.revision, 900, trigger_met=True, account="Paused"
        )
    ledger.safety(PLAYER, "resume-work-play", ledger.status(PLAYER)["revision"], pause=False)
    ledger.engine.dispose()
    account = "I reviewed the original in-scene request."
    asyncio.run(native(42910, trigger_met=("yes",), account=account))
    receipt = service.use(
        ADMIN, "42911", work, canon.revision, 900, trigger_met=True, account=account
    )
    uses = [
        WorkPlayUse.model_validate_json(x["body"])
        for x in state(game).facts
        if x.get("kind") == USE
    ]
    assert len(uses) == 1 and uses[0].id == receipt["event"]
    assert uses[0].play_source == migration.event and uses[0].account == account
