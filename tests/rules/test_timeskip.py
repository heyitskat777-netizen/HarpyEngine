"""The original table's Timeskip and its first four actual canonical steps."""

import asyncio

import pytest
from test_harpy_flirt import submit_form
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state
from test_world_service import ready

from girlframe.discord_adapter.m3_punishments import Picker
from girlframe.discord_adapter.m3_timeskip import open_timeskip
from girlframe.discord_adapter.m3_world import open_world
from girlframe.engine.m3_world_state import Npc
from girlframe.services.inbox import InboxService
from girlframe.services.m3_off_duty import OffDutyService
from girlframe.services.m3_strain import StrainService
from girlframe.services.m3_timeskip import RULE, Arrival, TimeskipService, records
from girlframe.services.onboarding import WorkflowError


def test_native_timeskip_agreement_and_ordered_world_changes(ledger):
    world, game = ready(ledger)
    world.npc(
        ADMIN,
        "inside-base",
        state(game).revision,
        Npc(
            id="inside",
            name="Inside",
            jobs=("base_personnel",),
            detail="An actual occupant of the original base.",
            controller=ADMIN.user_id,
            cell=(2, 0),
        ),
    )
    world.npc(
        ADMIN,
        "outside-base",
        state(game).revision,
        Npc(
            id="outside",
            name="Outside",
            jobs=("civilian",),
            detail="Shares the map square, physically outside the base.",
            controller=ADMIN.user_id,
            cell=(2, 0),
        ),
    )
    service = TimeskipService(game)
    with pytest.raises(WorkflowError):
        service.start_menu(ADMIN)
    policy = ledger.policy.m3_approval
    ledger.policy = ledger.policy.model_copy(
        update=dict(
            m3_approval=policy.model_copy(
                update=dict(
                    subsystems=policy.subsystems | {"plays"},
                    activity_specialist_rules=policy.activity_specialist_rules | {RULE},
                )
            )
        )
    )

    async def launch(current):
        await open_world(current, world)
        picker = current.edit_original_response.call_args.kwargs["view"]
        assert isinstance(picker, Picker) and "timeskip" in dict(picker.options)
        await picker.open_item(current, "timeskip")

    asyncio.run(submit_form(ADMIN, launch, dict(duration=("12",)), 93300))
    (case,) = records(state(game))
    assert case.months == 12 and case.step == "agreement"
    assert any(x.task == "m3_timeskip" for x in InboxService(ledger).items(PLAYER))
    initial = state(game).revision
    key = asyncio.run(
        submit_form(
            PLAYER,
            lambda click: open_timeskip(click, service, case.id),
            dict(vote=("accept",)),
            93304,
            wrong_owner=True,
        )
    )
    assert service.vote(PLAYER, key, case.id, initial, True)["step"] == "agreement"
    with pytest.raises(WorkflowError, match="STALE_TIMESKIP"):
        service.vote(OTHER, "stale-duration", case.id, initial, True)
    asyncio.run(
        submit_form(
            OTHER,
            lambda click: open_timeskip(click, service, case.id),
            dict(vote=("accept",)),
            93308,
        )
    )
    with pytest.raises(WorkflowError, match="unavailable"):
        service.get(PLAYER, case.id)
    assert not any(x.task == "m3_timeskip" for x in InboxService(ledger).items(PLAYER))

    async def ruin(current, site):
        await open_timeskip(current, service, case.id)
        picker = current.edit_original_response.call_args.kwargs["view"]
        assert isinstance(picker, Picker) and site in dict(picker.options)
        await picker.open_item(current, site)

    arrival = dict(
        kind=("dormant",),
        type=("jackdaw",),
        name="Private ruins Gorgon",
        assets="Horns\nMirrors\nTail",
        weakness="The horns protect its Core.",
        account="The original site was destroyed during the agreed interval.",
    )
    asyncio.run(submit_form(ADMIN, lambda click: ruin(click, "city0"), arrival, 93312))
    assert records(state(game))[0].step == "city_foundation"
    ledger.engine.dispose()
    asyncio.run(
        submit_form(
            ADMIN,
            lambda click: open_timeskip(click, service, case.id),
            dict(name="New City", cell="1,3", account="A new city established by the table."),
            93316,
        )
    )
    with pytest.raises(WorkflowError, match="STALE_TIMESKIP"):
        service.ruin(
            ADMIN,
            "stale-ruin",
            case.id,
            initial,
            "base1",
            Arrival(
                kind="benevolent", type="incubus", name="Late", assets=("a", "b"), weakness="C"
            ),
            (),
            "Old form",
        )
    asyncio.run(
        submit_form(
            ADMIN,
            lambda click: ruin(click, "base1"),
            arrival | dict(name="Private base Gorgon", occupants=("inside",)),
            93320,
        )
    )
    final = state(game)
    (settled,) = records(final)
    assert (
        settled.step == "newgirl" and settled.city_ruin == "city0" and settled.base_ruin == "base1"
    )
    assert final.world is not None
    locations = {x.id: x for x in final.world.locations}
    assert locations["city0"].condition == locations["base1"].condition == "destroyed"
    assert locations[settled.city].name == "New City"
    newcomers = {x.name: x for x in final.world.gorgons if x.id != "secret"}
    assert newcomers["Private ruins Gorgon"].cell == locations["city0"].cell
    assert newcomers["Private base Gorgon"].cell == locations["base1"].cell
    assert {x.id: x.alive for x in final.world.npcs} == {"inside": False, "outside": True}
    StrainService(OffDutyService(world.missions)).configure(
        ADMIN, "timeskip-initialize-strain", final.revision, "business_as_usual", frozenset()
    )
    final = state(game)
    assert final.strain is not None
    assert {x.entity for x in final.strain.triggers if x.kind == "structure_destroyed"} == {
        "city0",
        "base1",
    }
    assert "Private base Gorgon" not in str(world.get(PLAYER))
