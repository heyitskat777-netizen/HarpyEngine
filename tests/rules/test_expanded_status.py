"""Foundation standings remain independent of the Cadre and rules adjudication."""

import asyncio

import pytest
from test_battle_service import prepared
from test_enforcer_requisitions import approved
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state
from test_mission_ui import current

from girlframe.discord_adapter.m3_actors import open_actors
from girlframe.discord_adapter.m3_world import open_world
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_expanded_status import RULE, designation
from girlframe.engine.m3_world import update
from girlframe.engine.m3_world_state import AdversaryPilot, Faction, Npc
from girlframe.services.m3_actors import ActorService
from girlframe.services.m3_expanded_status import ExpandedStatusService
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_world import WorldService
from girlframe.services.onboarding import WorkflowError


def test_expanded_status_defaults_and_actual_native_gm_designation(ledger, tmp_path, monkeypatch):
    game, *_ = prepared(ledger)
    approval = ledger.policy.m3_approval
    ledger.policy = ledger.policy.model_copy(
        update=dict(
            m3_approval=approval.model_copy(
                update=dict(subsystems=approval.subsystems | {"world", "plays"})
            )
        )
    )
    service = ExpandedStatusService(game)
    missions = MissionService(ledger)
    roles = ActorService(missions)
    with ledger.transaction() as connection:
        original = state(game)
        cast = tuple(
            Npc(
                id=key,
                name=key,
                jobs=(job,),
                detail="Original source role",
                controller=3,
                cell=(0, 0),
                faction="rebel-group" if key == "Rebel handler" else None,
            )
            for key, job in (
                ("Fictional Director", "director"),
                ("Investor", "patron"),
                ("Clinician", "doctor"),
                ("Civilian", "civilian"),
                ("Rebel handler", "handler"),
            )
        )
        original.world = update(
            original.world,
            npcs=cast,
            factions=(Faction(id="rebel-group", name="Group", kind="rebel", cells=((0, 0),)),),
            pilots=(
                AdversaryPilot(
                    id="actual-harpy",
                    name="Actual Harpy",
                    kind="harpy",
                    girl="HARPY",
                    frame="HARPY",
                    controller=3,
                    cell=(0, 0),
                    assets=(),
                ),
            ),
        )
        game.event(connection, 1, "expanded-status-world", "synthetic.expanded_status", original)
    before = state(game)
    dog = current_ref(before, before.order[-1])
    assert not service.enabled() and "expanded_status" not in roles.inspect(OTHER, dog)
    approved(ledger, game, tmp_path, monkeypatch, extra=(RULE,))
    assert service.enabled()
    options = service.options(ADMIN)
    levels = {actor.entity: level for actor, _, level in options["actors"]}
    assert levels == {
        "1": 3,
        "2": 5,
        "3": 5,
        "Fictional Director": 1,
        "Investor": 2,
        "Clinician": 4,
        "Civilian": 6,
    }
    rebel = ActorRef(kind="npc", entity="Rebel handler")
    harpy = ActorRef(kind="external_pilot", entity="actual-harpy")
    assert roles.inspect(OTHER, rebel)["expanded_status"]["level"] is None
    assert roles.inspect(OTHER, harpy)["expanded_status"]["level"] is None
    with pytest.raises(WorkflowError, match="outside Foundation"):
        service.designate(ADMIN, "outside", before.revision, rebel, 1, "Unusable designation.")
    with pytest.raises(WorkflowError, match="actual human GM"):
        service.designate(OTHER, "fictional-director-authority", before.revision, dog, 1, "No.")
    with pytest.raises(WorkflowError, match="actual human GM"):
        service.options(OTHER)
    with pytest.raises(WorkflowError, match="STALE_EXPANDED_STATUS"):
        service.designate(ADMIN, "old", before.revision - 1, dog, 2, "Stale.")
    ledger.safety(OTHER, "pause-standing", ledger.status(OTHER)["revision"], pause=True)
    with pytest.raises(WorkflowError, match="SAFETY_PAUSED"):
        service.designate(ADMIN, "paused", before.revision, dog, 2, "On hold.")
    ledger.safety(OTHER, "resume-standing", ledger.status(OTHER)["revision"], pause=False)

    async def native_assign():
        click = current(1, 51300)
        await click.response.defer(ephemeral=True)
        await open_world(click, WorldService(missions))
        menu = click.edit_original_response.call_args.kwargs["view"]
        await menu.open_item(click, "expanded_status")
        form = click.edit_original_response.call_args.kwargs["view"]
        assert not await form.interaction_check(current(3))
        form.values.update(
            actor=(dog.token,), level=("2",), account="PRIVATE_RULES_TABLE_DESIGNATION"
        )
        await form.confirm.callback(current(1, 51301))
        assert form.completed

    asyncio.run(native_assign())
    change = service.designate(
        ADMIN, "51301", before.revision, dog, 2, "PRIVATE_RULES_TABLE_DESIGNATION"
    )
    ledger.engine.dispose()
    assert designation(state(game), dog).event == change["event"]
    assert state(game).order == before.order and state(game).sheets == before.sheets
    own = roles.inspect(OTHER, dog)["expanded_status"]
    assert own["level"] == 2 and own["designated"] and "PRIVATE_" not in str(own)
    with pytest.raises(WorkflowError):
        roles.inspect(PLAYER, dog)
    with pytest.raises(WorkflowError):
        game.issue_order(OTHER, "no-implicit-authority", 900, 2, "Take my command.")
    assert state(game).order == before.order

    async def native_read():
        click = current(3, 51302)
        await click.response.defer(ephemeral=True)
        await open_actors(click, roles)
        menu = click.edit_original_response.call_args.kwargs["view"]
        await menu.open_item(click, dog.token)
        reply = click.edit_original_response.call_args.kwargs["content"]
        assert "Politicians, major investors" in reply and "PRIVATE_" not in reply

    asyncio.run(native_read())
