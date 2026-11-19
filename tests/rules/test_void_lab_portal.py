"""A real recursive Endgame opens one durable privately mapped laboratory portal."""

import asyncio

import pytest
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state
from test_mission_ui import current
from test_off_duty_cycle import activate
from test_strain_service import prepared, ready
from test_world import gorgon, initial

from girlframe.discord_adapter.inbox import InboxView
from girlframe.discord_adapter.m2_forms import NativeForm
from girlframe.engine.m3_strain_effects import Choice
from girlframe.engine.m3_void_lab_portal import RULE, portals
from girlframe.engine.m3_world_state import Faction
from girlframe.services.inbox import InboxService
from girlframe.services.m3_off_duty_cycle import CycleService
from girlframe.services.m3_strain_effects import EffectService
from girlframe.services.m3_void_lab_portal import LabPortalService
from girlframe.services.m3_world import WorldService
from girlframe.services.onboarding import WorkflowError


def prepare_endgame(ledger, slot):
    strain, game = ready(ledger, face=6)
    approval = ledger.policy.m3_approval
    ledger.policy = ledger.policy.model_copy(
        update=dict(
            m3_approval=approval.model_copy(
                update=dict(subsystems=approval.subsystems | {"world", "plays"})
            )
        )
    )
    world = WorldService(strain.missions)
    map_data = initial()
    world.initialize(
        ADMIN, "map", state(game).revision, map_data.board, map_data.locations, map_data.gorgons[0]
    )
    period = prepared(strain, game, high=frozenset({"void"}))
    index = 0
    while True:
        request = next(
            x
            for x in state(game).strain.requests
            if x.track == "void" and (x.kind == "endgame" or x.severity == "high")
        )
        if request.kind == "endgame":
            break
        strain.roll(ADMIN, f"high-{index}", request.id, 1, state(game).revision)
        strain.choose(ADMIN, f"cascade-{index}", request.id, 2, state(game).revision, 2)
        index += 1
    selected = strain.choose(
        ADMIN, "endgame-slot", request.id, 1, state(game).revision, slot, endgame=True
    )
    assert selected["rule_id"] == f"strain.void.endgame.{slot}"
    identity = request.id + ":effect"

    effects = EffectService(strain)
    for index, request in enumerate(state(game).strain.requests):
        if request.track == "void":
            face, column = 1, 1
            choice = Choice(
                rule_id="strain.void.low.1.1",
                account="An actual edge arrival.",
                gorgon=gorgon("directed", "cascade-gorgon-" + str(index), (-3, 0)),
            )
        elif request.track == "rebellion":
            face, column = 1, 1
            choice = Choice(
                rule_id="strain.rebellion.low.1.1",
                account="Local opposition.",
                target="city0",
                faction=Faction(id="group", kind="rebel", name="Group", cells=((0, 4),)),
            )
        else:
            face, column = 5, 2
            choice = Choice(
                rule_id="strain.budget.low.5.2", account="An actual room.", rooms=((2, 3),)
            )
        strain.dice.face = face
        strain.roll(ADMIN, f"die-{index}", request.id, 1, state(game).revision)
        strain.choose(ADMIN, f"column-{index}", request.id, 2, state(game).revision, column)
        effects.apply(
            ADMIN, f"effect-{index}", request.id + ":effect", 1, state(game).revision, choice
        )
    return strain, game, world, period, identity


def test_actual_endgame_and_native_private_portal_unblock_off_duty_once(ledger):
    strain, game, world, period, identity = prepare_endgame(ledger, slot=2)
    service = LabPortalService(ledger)
    assert service.view(ADMIN, identity)["state"] == "pending" and not portals(state(game))
    assert state(game).strain.endgames[-1].rule_id == RULE
    assert not any(x.identity == identity for x in InboxService(ledger).items(PLAYER))

    cycle = CycleService(strain.periods)
    with pytest.raises(WorkflowError, match="work|Strain"):
        activate(cycle, game, period)
    rev = state(game).revision
    with pytest.raises(WorkflowError, match="original Endgame Handler"):
        service.open(OTHER, "wrong-owner", identity, 1, rev, "important0", "Lab", "Opening")
    with pytest.raises(WorkflowError, match="STALE_LAB_PORTAL"):
        service.open(ADMIN, "stale", identity, 1, rev - 1, "important0", "Lab", "Opening")
    with pytest.raises(WorkflowError, match="available Foundation laboratory"):
        service.open(ADMIN, "invalid-lab", identity, 1, rev, "absent", "Lab", "Opening")
    ledger.safety(OTHER, "pause", ledger.status(OTHER)["revision"], pause=True)
    with pytest.raises(WorkflowError, match="SAFETY_PAUSED"):
        service.open(ADMIN, "paused", identity, 1, rev, "important0", "Lab", "Opening")
    ledger.safety(OTHER, "resume", ledger.status(OTHER)["revision"], pause=False)
    lab, account = "PRIVATE_LAB_NAME", "PRIVATE_PORTAL_EVENT"

    async def native():
        inbox = InboxService(ledger)
        card = next(x for x in inbox.items(ADMIN) if x.identity == identity)
        assert card.task == "m3_void_lab_portal"
        click = current(1, 89500)
        await click.response.defer(ephemeral=True)
        await InboxView(inbox, 1).route(click, card)
        form = click.edit_original_response.call_args.kwargs["view"]
        assert isinstance(form, NativeForm)
        form.values.update(site=("important0",), laboratory=lab, account=account)
        await form.confirm.callback(current(1, 89501))
        assert form.completed

    engine_dice = strain.dice.calls
    asyncio.run(native())
    receipt = service.open(ADMIN, "89501", identity, 1, rev, "important0", lab, account)
    assert receipt["state"] == "resolved" and strain.dice.calls == engine_dice
    with pytest.raises(WorkflowError, match="STALE_LAB_PORTAL"):
        service.open(ADMIN, "new-request", identity, 1, rev, "important0", lab, account)
    (portal,) = portals(state(game))
    assert (portal.site, portal.cell, portal.account) == ("important0", (4, 4), account)
    assert portal.source != portal.opened
    assert activate(cycle, game, period)["phase"] == "active"
    ledger.engine.dispose()
    reopened = LabPortalService(ledger).view(ADMIN, identity)["portal"]
    assert reopened["accessible"] and reopened["laboratory"] == lab
    private = world.get(ADMIN, private=True)["world"]
    public = world.get(PLAYER)["world"]
    assert private["stable_portals"] == [reopened] and account not in str(private)
    assert "stable_portals" not in public and lab not in str(public)
