"""Actual Harpy Frame consent, independent help and real medical recovery remain separate."""

import asyncio
from uuid import uuid4

import pytest
from test_harpy_dive import rolled
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import answer, state
from test_mission_ui import current
from test_physical_operations import place

from girlframe.discord_adapter.inbox import InboxView
from girlframe.discord_adapter.m2_forms import NativeForm
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_harpy_defeat import harpy
from girlframe.services.inbox import InboxService
from girlframe.services.m3_harpy_physical import HarpyPhysicalService
from girlframe.services.onboarding import WorkflowError


def subsumed(store):
    game, actor, _, pilot = rolled(store)
    answer(
        game,
        PLAYER,
        "dive_select",
        options=("locked_cockpit_extraction_requires_frame_consent",),
        text="Actual Harpy subsumption",
    )
    answer(game, PLAYER, "dive_effect", flag=True)
    with store.transaction() as c:
        canon = place(state(game), 3)
        game.event(c, 1, str(uuid4()), "synthetic.actual_helper_position", canon)
    return game, actor, pilot


def test_original_frame_refusal_stales_old_menu_then_real_extraction_and_medical_never_repair(
    ledger,
):
    game, actor, pilot = subsumed(ledger)
    service = HarpyPhysicalService(ledger)
    initial = service.get(PLAYER, actor)
    before = harpy(state(game), actor)
    original_assets = state(game).world.pilots[-1].assets
    service.voice(
        PLAYER, str(uuid4()), actor, initial["expected"], "allow", "Actual Frame voice allows"
    )
    current_data = service.get(PLAYER, actor)
    service.voice(
        PLAYER,
        str(uuid4()),
        actor,
        current_data["expected"],
        "refuse",
        "Actual Frame voice revokes",
    )
    with pytest.raises(WorkflowError, match="STALE_HARPY"):
        service.voice(
            PLAYER, str(uuid4()), actor, initial["expected"], "allow", "Stale cached menu"
        )
    extract = service.get(OTHER, actor)
    helper = current_ref(state(game), 3)
    proposal = service.propose(
        OTHER,
        str(uuid4()),
        actor,
        extract["expected"],
        "extract",
        "I actually help at this Frame",
        extractor=helper,
    )
    with pytest.raises(WorkflowError, match="consent"):
        service.confirm(
            ADMIN, str(uuid4()), proposal["id"], 1, accepted=True, evidence="Actual helper present"
        )
    own = service.get(PLAYER, actor)
    service.voice(
        PLAYER,
        str(uuid4()),
        actor,
        own["expected"],
        "allow",
        "The actual Frame now allows extraction",
    )
    extract = service.get(OTHER, actor)
    proposal = service.propose(
        OTHER,
        str(uuid4()),
        actor,
        extract["expected"],
        "extract",
        "Actual extraction help",
        extractor=helper,
    )
    service.confirm(
        ADMIN,
        str(uuid4()),
        proposal["id"],
        1,
        accepted=True,
        evidence="The actual helper reaches and extracts this body",
    )
    body = harpy(state(game), actor)
    assert not body.linked and not body.subsumed and not body.vitals_active
    assert body.cell == before.frame_cell and body.frame_cell == before.frame_cell
    after = service.get(PLAYER, actor)
    medical = service.propose(
        PLAYER,
        str(uuid4()),
        actor,
        after["expected"],
        "recover",
        "Actual medical help wakes this body",
    )
    service.confirm(
        ADMIN,
        str(uuid4()),
        medical["id"],
        1,
        accepted=True,
        evidence="Actual medical help restores vital signs",
    )
    recovered = harpy(state(game), actor)
    assert recovered.vitals_active and not recovered.body_incapacitated
    assert recovered.identities == before.identities and recovered.heat == before.heat
    assert state(game).world.pilots[-1].assets == original_assets
    assert state(game).sheets["2"].model_dump_json() == pilot and game.dice.calls == 1
    gate = next(x for x in state(game).frame_locks if x.owner == actor)
    assert gate.consents[-1].used_event and gate.active


def test_native_harpy_frame_and_owned_help_inbox_route_preserve_other_original_privacy(ledger):
    game, actor, _ = subsumed(ledger)
    inbox = InboxService(ledger)
    row = next(
        x
        for x in inbox.items(PLAYER)
        if x.task == "m3_harpy_physical" and x.identity == actor.entity
    )

    async def run():
        caller = current(2, 98801)
        await caller.response.defer(ephemeral=True)
        await InboxView(inbox, 2).route(caller, row)
        menu = caller.edit_original_response.call_args.kwargs["view"]
        assert {"allow", "refuse", "open"} <= set(dict(menu.options))
        assert not await menu.interaction_check(current(3))
        await menu.open_item(caller, "allow")
        form = caller.edit_original_response.call_args.kwargs["view"]
        assert isinstance(form, NativeForm)
        form.values["account"] = "My actual Frame voice grants this exact consent"
        await form.confirm.callback(current(2, 98802))
        assert form.completed

    asyncio.run(run())
    assert harpy(state(game), actor).subsumed and not harpy(state(game), actor).vitals_active
