"""Every future rift arrival comes from an actual durable saved Strain roll."""

import asyncio

import pytest
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state
from test_mission_ui import current
from test_off_duty_cycle import activate, call, finish_routine, recover_both
from test_strain import facts
from test_strain_service import prepared, ready
from test_world import gorgon, initial

from girlframe.discord_adapter.inbox import InboxView
from girlframe.discord_adapter.m2_forms import NativeForm
from girlframe.engine.m3_gorgon_catalog import ASSETS
from girlframe.engine.m3_strain_effects import Choice
from girlframe.engine.m3_void_rift import RULE, rifts
from girlframe.engine.m3_world_state import Faction, Npc
from girlframe.services.inbox import InboxService
from girlframe.services.m3_off_duty_cycle import CycleService
from girlframe.services.m3_strain import StrainService
from girlframe.services.m3_strain_effects import EffectService
from girlframe.services.m3_world import WorldService
from girlframe.services.onboarding import WorkflowError


def test_rift_uses_native_arrivals_and_survives_period_completion_and_reopening(ledger):
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
    start = initial()
    world.initialize(
        ADMIN, "world", state(game).revision, start.board, start.locations, start.gorgons[0]
    )
    period = prepared(strain, game, high=frozenset({"void"}))
    requests = {x.track: x.id for x in state(game).strain.requests}
    root = requests["void"]
    work = root + ":effect"
    strain.roll(ADMIN, "original-six", root, 1, state(game).revision)
    revision = state(game).revision
    strain.dice.face = 3
    ledger.safety(OTHER, "pause-duration", ledger.status(OTHER)["revision"], pause=True)
    with pytest.raises(WorkflowError, match="SAFETY_PAUSED"):
        strain.choose(ADMIN, "opening", root, 2, revision, 1)
    assert strain.dice.calls == 1
    ledger.safety(OTHER, "resume-duration", ledger.status(OTHER)["revision"], pause=False)
    opening = strain.choose(ADMIN, "opening", root, 2, revision, 1)
    assert strain.choose(ADMIN, "opening", root, 2, revision, 1) == opening
    assert strain.dice.calls == 2
    (rift,) = rifts(state(game))
    assert rift.duration == 3 and rift.rng_source == "test_injected"
    assert len(rift.arrivals) == 1 and rift.arrivals[0].work == work
    assert state(game).strain.events[0].face == 6

    async def native(identity, serial, **values):
        inbox = InboxService(ledger)
        card = next(x for x in inbox.items(ADMIN) if x.identity == identity)
        assert card.task == "m3_strain_effect"
        initial_click = current(1, serial)
        await initial_click.response.defer(ephemeral=True)
        await InboxView(inbox, 1).route(initial_click, card)
        form = initial_click.edit_original_response.call_args.kwargs["view"]
        assert isinstance(form, NativeForm)
        form.values.update(values)
        form.controls()
        confirmation = current(1, serial + 1)
        await form.confirm.callback(confirmation)
        assert form.completed, confirmation.edit_original_response.call_args

    def roll_other(track, face, column, choice):
        request = requests[track]
        strain.dice.face = face
        revision = state(game).revision
        saved = strain.roll(ADMIN, "die-" + track, request, 1, revision)
        assert strain.roll(ADMIN, "die-" + track, request, 1, revision) == saved
        strain.choose(ADMIN, "column-" + track, request, 2, state(game).revision, column)
        EffectService(strain).apply(
            ADMIN, "effect-" + track, request + ":effect", 1, state(game).revision, choice
        )
        return rifts(state(game))[0].arrivals[-1].work

    first = roll_other(
        "rebellion",
        1,
        1,
        Choice(
            rule_id="strain.rebellion.low.1.1",
            account="Real local opposition.",
            target="city0",
            faction=Faction(id="group", name="Local Group", kind="rebel", cells=((0, 4),)),
        ),
    )
    second = roll_other(
        "budget",
        5,
        2,
        Choice(
            rule_id="strain.budget.low.5.2", account="An actual room assignment.", rooms=((2, 3),)
        ),
    )
    cycle = CycleService(strain.periods)
    with pytest.raises(WorkflowError, match="Strain|work"):
        activate(cycle, game, period)
    effects = EffectService(strain)
    assert effects.get(ADMIN, first)["trigger_roll"] == requests["rebellion"]
    with pytest.raises(WorkflowError):
        effects.get(PLAYER, first)
    with pytest.raises(WorkflowError, match="STALE_STATE"):
        effects.apply(
            ADMIN,
            "stale",
            first,
            1,
            state(game).revision - 1,
            Choice(rule_id=RULE, account="stale"),
        )
    with pytest.raises(WorkflowError, match="one new original"):
        effects.apply(
            ADMIN,
            "no-arrival",
            first,
            1,
            state(game).revision,
            Choice(rule_id=RULE, account="description only"),
        )
    assert not any(x.identity in (work, first, second) for x in InboxService(ledger).items(PLAYER))
    labels = ASSETS["incubus"][:3]
    asyncio.run(
        native(
            work,
            89200,
            arrival=("gorgon",),
            **{"class": ("dormant",)},
            type=("incubus",),
            assets=labels,
            core=(labels[0],),
            weakness="An actual weak spot.",
            name="HIDDEN_RIFT_GORGON",
            cell=("1,1",),
            revealed=("no",),
            account="The actual first Gorgon emerges.",
        )
    )
    asyncio.run(
        native(
            first,
            89210,
            arrival=("harpy",),
            harpy_name="HIDDEN_RIFT_HARPY",
            harpy_frame="Oldgen",
            girl_component="Wings",
            frame_component="Lance",
            cell=("2,1",),
            revealed=("no",),
            account="The actual first Harpy emerges.",
        )
    )
    assert "HIDDEN_RIFT" not in str(world.get(PLAYER))
    world.npc(
        ADMIN,
        "actual-victim",
        state(game).revision,
        Npc(
            id="witness",
            name="At the arrival",
            detail="The actual on-site observer.",
            jobs=("scientist",),
            controller=1,
            cell=(0, 4),
        ),
    )
    creature = gorgon("aggressive", "original-aggressive", (0, 4))
    choice = Choice(
        rule_id=RULE,
        account="The attacker actually kills the NPC.",
        gorgon=creature,
        victim="witness",
    )
    revision = state(game).revision
    applied = effects.apply(ADMIN, "aggressive-arrival", second, 1, revision, choice)
    assert effects.apply(ADMIN, "aggressive-arrival", second, 1, revision, choice) == applied
    canon = state(game)
    assert not next(x for x in canon.world.npcs if x.id == "witness").alive
    assert next(x for x in canon.world.gorgons if x.id == creature.id).collateral_city is None
    assert tuple(x.actor.kind for x in rifts(canon)[0].arrivals) == (
        "gorgon",
        "external_pilot",
        "gorgon",
    )
    activate(cycle, game, period)
    recover_both(cycle, game, period)
    finish_routine(cycle, game, period)
    assert call(cycle, game, ADMIN, period, "finish", ())["phase"] == "complete"

    ledger.engine.dispose()
    reopened = StrainService(strain.periods, dice=strain.dice)
    next_period = reopened.periods.begin(ADMIN, "next-period")
    canon = state(game)
    void_count = sum(any(a.void for a in sheet.assets) for sheet in canon.sheets.values())
    triggers = {x.kind: True for x in canon.strain.triggers if x.consumed_by is None}
    reopened.prepare(
        ADMIN,
        "next-review",
        next_period["id"],
        1,
        canon.revision,
        facts(
            no_girl_void=void_count == 0,
            at_least_half_have_void=2 * void_count >= len(canon.order),
            **triggers,
        ),
    )
    next_roll, extra_roll, *_ = state(game).strain.requests
    strain.dice.face = 2
    reopened.roll(ADMIN, "next-actual-roll", next_roll.id, 1, state(game).revision)
    final = rifts(state(game))[0].arrivals[-1]
    assert final.roll == next_roll.id and final.period == next_period["id"]
    reopened.roll(ADMIN, "one-too-many", extra_roll.id, 1, state(game).revision)
    assert len(rifts(state(game))[0].arrivals) == 4
    assert strain.dice.calls == 6
    assert (
        EffectService(reopened).apply(
            ADMIN,
            "last-arrival",
            final.work,
            1,
            state(game).revision,
            Choice(
                rule_id=RULE,
                account="The final distinct arrival.",
                gorgon=gorgon("benevolent", "last-gorgon", (4, 1)),
            ),
        )["state"]
        == "resolved"
    )
