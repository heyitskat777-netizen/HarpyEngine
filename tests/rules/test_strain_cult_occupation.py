"""A finished cult event changes control without taking over its messiah."""

import asyncio

import pytest
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state
from test_mission_ui import current
from test_off_duty_cycle import activate
from test_strain_void_spread import strain_source

from girlframe.discord_adapter.inbox import InboxView
from girlframe.discord_adapter.m3_strain_effects import DependentForm, effect_form
from girlframe.discord_adapter.m3_world import MapPages
from girlframe.engine.m3_cult_occupation import RULE, occupations
from girlframe.engine.m3_strain_effects import Choice
from girlframe.engine.m3_world import update
from girlframe.engine.m3_world_state import AdversaryPilot, Asset, Faction
from girlframe.services.inbox import InboxService
from girlframe.services.m3_off_duty_cycle import CycleService
from girlframe.services.m3_strain_effects import EffectService
from girlframe.services.m3_world import WorldService
from girlframe.services.onboarding import WorkflowError


@pytest.mark.parametrize("create", (False, True), ids=("existing-harpy", "new-harpy"))
def test_cult_takes_the_real_site_and_keeps_original_harpy_authority(ledger, create):
    strain, game, _, period, work = strain_source(ledger, 3, column=2)
    effects = EffectService(strain)
    private_name = "Harpy-identity-fixture"
    original = AdversaryPilot(
        id="living-harpy",
        name=private_name,
        kind="harpy",
        girl="HARPY",
        frame="Private frame fixture",
        cell=(2, 2),
        controller=OTHER.user_id,
        assets=(Asset(id="claw", name="Claw", family="girl", description="Frosted"),),
    )
    if not create:
        with ledger.transaction() as connection:
            canon = state(game)
            canon.world = update(canon.world, pilots=(original,))
            game.event(connection, OTHER.user_id, "harpy-roster", "synthetic.roster", canon)

    for track, face in (("rebellion", 1), ("budget", 5)):
        request = next(x for x in state(game).strain.requests if x.track == track)
        strain.dice.face = face
        strain.roll(ADMIN, "die-" + track, request.id, 1, state(game).revision)
        strain.choose(ADMIN, "column-" + track, request.id, 2, state(game).revision, 2)
        effects.apply(
            ADMIN,
            "resolve-" + track,
            request.id + ":effect",
            1,
            state(game).revision,
            Choice(
                rule_id=f"strain.{track}.low.{face}.2",
                account="Other actual event.",
                rooms=((2, 3),) if track == "budget" else (),
            ),
        )
    cycle = CycleService(strain.periods)
    with pytest.raises(WorkflowError, match="Resolve actual Strain"):
        activate(cycle, game, period)
    dice = state(game).strain.events
    revision = state(game).revision
    fabricated = Choice(
        rule_id=RULE,
        target="important0",
        faction=Faction(id="cult", name="False Cult", kind="cult", cells=((4, 4),)),
        cult_harpy="missing",
        account="No actual messiah exists.",
    )
    with pytest.raises(WorkflowError):
        effects.apply(PLAYER, "wrong-owner", work, 1, revision, fabricated)
    with pytest.raises(WorkflowError, match="living actual external Pilot"):
        effects.apply(ADMIN, "missing-messiah", work, 1, revision, fabricated)
    assert state(game).revision == revision
    assert not any(x.identity == work for x in InboxService(ledger).items(OTHER))

    async def native_apply():
        inbox = InboxService(ledger)
        item = next(x for x in inbox.items(ADMIN) if x.identity == work)
        click = current(ADMIN.user_id, 85600)
        await click.response.defer(ephemeral=True)
        await InboxView(inbox, ADMIN.user_id).route(click, item)
        form = click.edit_original_response.call_args.kwargs["view"]
        assert isinstance(form, DependentForm)
        selected = next(f for f in form.fields if f.key == "cult_harpy")
        harpy = selected.options[-1][0] if create else original.id
        values = dict(
            cult_site=("important0",),
            cult_name="The Lamps",
            cult_harpy=(harpy,),
            account="PRIVATE_CAPTURE_ACCOUNT",
        )
        if create:
            values.update(
                harpy_name=private_name,
                harpy_frame="Parked at the gate.",
                girl_component="Mirror scales",
                frame_component="Crystalline armor",
            )
        form.values.update(values)
        await form.confirm.callback(current(ADMIN.user_id, 85601))
        assert form.completed
        return values

    _, replay, _ = effect_form(ADMIN, effects, work)
    values = asyncio.run(native_apply())
    assert "committed" in replay(ADMIN, "85601", values)
    canon = state(game)
    (occupation,) = occupations(canon)
    (cult,) = canon.world.factions
    (actual,) = canon.world.pilots
    site = next(x for x in canon.world.locations if x.id == "important0")
    assert canon.strain.events == dice and occupation.work == work
    assert cult.id == occupation.faction and cult.kind == "cult" and cult.cells == (site.cell,)
    assert site.condition == "intact" and not site.operational
    assert site.control_loss.threat == occupation.messiah and occupation.messiah.entity == actual.id
    if create:
        assert actual.controller == ADMIN.user_id and {x.family for x in actual.assets} == {
            "girl",
            "frame",
        }
    else:
        assert actual == original

    world_service = WorldService(strain.missions)
    public = world_service.get(PLAYER)["world"]
    assert public["civic_conditions"] == [
        dict(kind="cult_occupation", site=site.id, name="The Lamps")
    ]
    assert private_name not in str(public) and "PRIVATE_CAPTURE_ACCOUNT" not in str(public)

    async def native_map():
        page = MapPages(world_service, PLAYER.user_id)
        page.page = 1
        click = current(PLAYER.user_id, 85610)
        await click.response.defer(ephemeral=True)
        await page.show(click)
        return click.edit_original_response.call_args.kwargs["content"]

    assert "occupied by The Lamps" in asyncio.run(native_map())
    assert EffectService(strain).get(ADMIN, work)["state"] == "resolved"
    assert activate(cycle, game, period)["phase"] == "active"
