"""Actual Handler severe consequences end or restrict the original career."""

import asyncio

import pytest
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state
from test_mission_ui import current
from test_punishment_service import ended, submit

from girlframe.discord_adapter.m3_punishments import open_details, open_discipline
from girlframe.engine.m3_punishments import Details
from girlframe.services.m3_careers import CareerService
from girlframe.services.onboarding import WorkflowError


@pytest.mark.parametrize(
    "kind,ending", [("execution", "execution"), ("indefinite_imprisonment", "imprisonment")]
)
def test_actual_severe_ending_resolves_failure_and_dog_and_preserves_private_original(
    ledger, kind, ending
):
    svc, missions, game, mission, identity = ended(ledger)
    original_sheet = state(game).sheets["3"]
    original = original_sheet.model_dump_json()
    preview = svc.get(ADMIN, identity)
    result = svc.apply(
        ADMIN,
        "actual-severe-ending",
        identity,
        preview["revision"],
        preview["game_revision"],
        Details(kind=kind),
    )
    assert result["cause_count"] == 2 and "3" not in state(game).sheets
    archive = state(game).career_archives[-1]
    assert archive.ending == ending and archive.sheet_json == original
    assert (
        svc.apply(
            ADMIN,
            "actual-severe-ending",
            identity,
            preview["revision"],
            preview["game_revision"],
            Details(kind=kind),
        )
        == result
    )
    assert CareerService(ledger).get(OTHER, archive.id)["can_replace"]
    assert svc.get(OTHER, identity)["callsign"] == original_sheet.callsign
    remaining = missions.get(ADMIN, mission["id"])["work"]
    for work in remaining:
        submit(svc, ADMIN, work["id"], Details(kind="stimulant_injection"), "finish-other")
    assert (
        missions.complete(ADMIN, "complete-after-ending", mission["id"], mission["revision"])[
            "phase"
        ]
        == "complete"
    )


def test_actual_link_reversal_keeps_the_girl_and_blocks_future_mission_entry(ledger):
    svc, missions, game, _, identity = ended(ledger)
    before = state(game).sheets["3"]
    submit(svc, ADMIN, identity, Details(kind="link_surgery_reversal"))
    after = state(game).sheets["3"]
    assert after.character_id == before.character_id and after.identities == before.identities
    assert after.heat == before.heat and after.permissions == before.permissions
    assert after.frame_scrapped and not any(x.family == "frame" for x in after.assets)
    assert state(game).unlinked_careers[-1].actor.incarnation == before.character_id
    with pytest.raises(WorkflowError):
        missions.offer(ADMIN, "cannot-dispatch-unlinked", "Actual next mission", (3,))


def test_pilot_inflictor_cannot_execute_even_if_it_owns_the_pending_work(ledger):
    svc, _, game, _, identity = ended(ledger)
    submit(svc, ADMIN, identity, Details(kind="passing_responsibility", delegate=2))
    preview = svc.get(PLAYER, identity)
    with pytest.raises(WorkflowError, match="Only the Handler"):
        svc.apply(
            PLAYER,
            "cannot-execute",
            identity,
            preview["revision"],
            preview["game_revision"],
            Details(kind="execution"),
        )
    assert "3" in state(game).sheets

    async def run():
        pilot = current(2, 21001)
        await pilot.response.defer(ephemeral=True)
        await open_discipline(pilot, svc, identity)
        picker = pilot.edit_original_response.call_args.kwargs["view"]
        assert "execution" not in dict(picker.options)

    asyncio.run(run())


def test_native_handler_execution_requires_explicit_actual_confirmation(ledger):
    svc, _, game, _, identity = ended(ledger)

    async def run():
        handler = current(1, 21011)
        await handler.response.defer(ephemeral=True)
        await open_details(handler, svc, identity, "execution")
        form = handler.edit_original_response.call_args.kwargs["view"]
        assert "3" in state(game).sheets and not await form.interaction_check(current(3))
        form.values.update(confirm=("yes",))
        await form.confirm.callback(current(1, 21012))
        assert form.completed

    asyncio.run(run())
    assert "3" not in state(game).sheets and state(game).career_archives[-1].ending == "execution"
