"""Low Void assigns its Sprite group to the next actual Gorgon arrival."""

import asyncio

import pytest
from test_ledger import ADMIN, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state
from test_mission_ui import current
from test_off_duty_cycle import activate
from test_strain_void_spread import strain_source
from test_world import gorgon, initial

from girlframe.discord_adapter.inbox import InboxView
from girlframe.discord_adapter.m3_strain_effects import DependentForm, effect_form
from girlframe.engine.m3_strain_effects import Choice
from girlframe.engine.m3_world import introduce_gorgon, locate_gorgon, update
from girlframe.engine.m3_world_state import Asset, CorePlan, SpriteEscort, SpriteEscortDesign
from girlframe.services.inbox import InboxService
from girlframe.services.m3_off_duty_cycle import CycleService
from girlframe.services.m3_strain_effects import EffectService
from girlframe.services.m3_world import WorldService
from girlframe.services.onboarding import WorkflowError


def test_native_quiet_result_records_one_group_at_the_next_actual_arrival(ledger):
    strain, game, _, period, _ = strain_source(ledger, 6, column=2)
    with ledger.transaction() as connection:
        canon = state(game)
        historic = gorgon("erratic", "returning", (1, 1), exposed=True, alive=False)
        canon.world = update(canon.world, gorgons=(*canon.world.gorgons, historic))
        game.event(connection, ADMIN.user_id, "past-defeat", "synthetic.defeated_gorgon", canon)

    def roll(track, severity, face, column):
        request = next(
            x for x in state(game).strain.requests if x.track == track and x.severity == severity
        )
        strain.dice.face = face
        strain.roll(ADMIN, "die-" + request.id, request.id, 1, state(game).revision)
        strain.choose(ADMIN, "column-" + request.id, request.id, 2, state(game).revision, column)
        return request.id + ":effect"

    effects = EffectService(strain)
    for track, face in (("rebellion", 1), ("budget", 5)):
        effects.apply(
            ADMIN,
            "resolve-" + track,
            roll(track, "low", face, 2),
            1,
            state(game).revision,
            Choice(
                rule_id=f"strain.{track}.low.{face}.2",
                account="Other actual event.",
                rooms=((2, 3),) if track == "budget" else (),
            ),
        )
    quiet = roll("void", "low", 2, 2)
    high = roll("void", "high", 3, 1)
    _, replay, _ = effect_form(ADMIN, effects, quiet)
    values = dict(
        sprite_name="The Small Mirrors",
        sprite_first="Spines",
        sprite_second="Reflection",
        sprite_core=("both",),
        sprite_weakness="It opens when all reflections face north.",
        account="They will accompany the next actual arrival.",
    )

    async def schedule():
        inbox = InboxService(ledger)
        item = next(x for x in inbox.items(ADMIN) if x.identity == quiet)
        click = current(ADMIN.user_id, 85700)
        await click.response.defer(ephemeral=True)
        await InboxView(inbox, ADMIN.user_id).route(click, item)
        form = click.edit_original_response.call_args.kwargs["view"]
        assert isinstance(form, DependentForm)
        form.values.update(values)
        await form.confirm.callback(current(ADMIN.user_id, 85701))
        assert form.completed

    asyncio.run(schedule())
    assert "committed" in replay(ADMIN, "85701", values)
    pending = state(game)
    assert len(pending.world.gorgons) == 2
    (scheduled,) = pending.world.sprite_escorts
    assert scheduled.work == quiet and scheduled.arrival_event is None and scheduled.group is None
    assert "The Small Mirrors" not in str(WorldService(strain.missions).get(PLAYER))
    with pytest.raises(WorkflowError, match="Resolve actual Strain"):
        activate(CycleService(strain.periods), game, period)

    assets = (
        Asset(id="new-mouth", name="New Mouth", description="Echoing", family="gorgon"),
        Asset(id="new-arm", name="New Arm", description="Split", family="gorgon"),
    )
    arrival = Choice(
        rule_id="strain.void.high.3.1",
        account="It comes back with new capabilities.",
        target=historic.id,
        new_assets=assets,
        new_type="sentinel",
        core_plan=CorePlan(assets=(assets[0].id,), weakness="Its echo subsides."),
    )
    reopened = EffectService(strain)
    receipt = reopened.apply(ADMIN, "arrival", high, 1, pending.revision, arrival)
    assert reopened.apply(ADMIN, "arrival", high, 1, pending.revision, arrival) == receipt
    after = state(game)
    (formation,) = after.world.sprite_escorts
    leader = next(x for x in after.world.gorgons if x.id == historic.id)
    group = next(x for x in after.world.gorgons if x.id == formation.group)
    assert after.strain.events == pending.strain.events and leader.alive
    assert formation.incoming == historic.id and formation.arrival_event != scheduled.event
    assert group.sprite_group and group.follows == leader.id and group.types == leader.types
    assert group.cell == leader.cell and group.position_event == formation.arrival_event
    assert tuple(x.id for x in group.assets) == group.core_plan.assets
    assert activate(CycleService(strain.periods), game, period)["phase"] == "active"


def test_orbital_formation_lands_together_and_is_not_reused_for_the_next_introduction():
    design = SpriteEscortDesign(name="Whispers", assets=("Plates", "Mists"), weakness="At dawn.")
    queued = update(
        initial(),
        sprite_escorts=(SpriteEscort(work="quiet", event="source", design=design),),
    )
    orbital = gorgon("directed", "orbital", None)
    after = introduce_gorgon(queued, orbital, event="orbit-arrival").world
    (receipt,) = after.sprite_escorts
    group = next(x for x in after.gorgons if x.id == receipt.group)
    assert group.cell is None and group.follows == orbital.id and group.types == orbital.types
    with pytest.raises(ValueError, match="original arriving Gorgon's landing"):
        locate_gorgon(after, group.id, (1, 1), "too-early")
    landed = locate_gorgon(after, orbital.id, (1, 2), "landing")
    assert {x.cell for x in landed.gorgons if x.id in (orbital.id, group.id)} == {(1, 2)}
    assert {x.position_event for x in landed.gorgons if x.id in (orbital.id, group.id)} == {
        "landing"
    }
    another = introduce_gorgon(landed, gorgon("erratic", "later", (3, 3)), event="later").world
    assert another.sprite_escorts == after.sprite_escorts
    assert len([x for x in another.gorgons if x.sprite_group]) == 1
