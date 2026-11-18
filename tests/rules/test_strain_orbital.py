"""Both printed Low Void 6 branches advance through their native consumers."""

import asyncio

import pytest
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state
from test_mission_service import launched
from test_mission_ui import current
from test_off_duty_cycle import activate, call, finish_routine, recover_both
from test_strain_service import prepared, ready
from test_world import gorgon, initial

from girlframe.discord_adapter.inbox import InboxView
from girlframe.discord_adapter.m2_forms import NativeForm
from girlframe.discord_adapter.m3_strain_effects import open_effect
from girlframe.engine.m3_budget_anarchy import get as civic_source
from girlframe.engine.m3_orbital_threat import threats
from girlframe.engine.m3_punishments import Details
from girlframe.engine.m3_strain_effects import Choice
from girlframe.engine.m3_world_state import Faction
from girlframe.services.inbox import InboxService
from girlframe.services.m3_budget_anarchy import AnarchyService
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_off_duty import OffDutyService
from girlframe.services.m3_off_duty_cycle import CycleService
from girlframe.services.m3_punishments import PunishmentService
from girlframe.services.m3_strain_effects import EffectService
from girlframe.services.m3_void_examination import ExaminationService
from girlframe.services.m3_world import WorldService
from girlframe.services.onboarding import WorkflowError


def orbital_period(store, *, column=1, protest=False):
    strain, game = ready(store)
    approval = store.policy.m3_approval
    store.policy = store.policy.model_copy(
        update={
            "m3_approval": approval.model_copy(
                update={"subsystems": approval.subsystems | {"world", "plays", "discipline"}}
            )
        }
    )
    world = initial()
    WorldService(strain.missions).initialize(
        ADMIN, "map", state(game).revision, world.board, world.locations, world.gorgons[0]
    )
    if protest:
        WorldService(strain.missions).faction(
            ADMIN,
            "rebel-group",
            state(game).revision,
            Faction(id="rebel-group", name="Local Rebels", kind="rebel", cells=((0, 4),)),
        )
    with store.transaction() as conn:
        current = state(game)
        for sheet in current.sheets.values():
            for asset in sheet.assets:
                asset.void = False
        game.event(conn, ADMIN.user_id, "baseline", "synthetic.nonvoid_cadre", current)
    period = prepared(strain, game, high=frozenset({"rebellion"}) if protest else frozenset())
    effects = EffectService(strain)
    effect = ""
    for track, die, selected in (("void", 6, column), ("rebellion", 1, 2), ("budget", 5, 2)):
        request = next(x for x in state(game).strain.requests if x.track == track)
        strain.dice.face = die
        strain.roll(ADMIN, "roll-" + track, request.id, 1, state(game).revision)
        strain.choose(ADMIN, "choose-" + track, request.id, 2, state(game).revision, selected)
        identity = request.id + ":effect"
        if track == "void":
            effect = identity
            continue
        if track == "rebellion" and protest:
            continue
        choice = Choice(
            rule_id=f"strain.{track}.low.{die}.{selected}",
            account="Perform the printed result in this fixture",
            rooms=((2, 3),) if track == "budget" else (),
        )
        effects.apply(ADMIN, "effect-" + track, identity, 1, state(game).revision, choice)
    return CycleService(strain.periods), effects, game, period, effect


def test_low_void_six_creates_the_threat_and_unblocks_off_duty(ledger):
    cycle, effects, game, period, identity = orbital_period(ledger)
    before = state(game)
    with pytest.raises(WorkflowError, match="Resolve actual Strain/start"):
        activate(cycle, game, period)
    choice = Choice(
        rule_id="strain.void.low.6.1",
        account="It is in orbit over the city",
        gorgon=gorgon("directed", "orbital", None),
    )
    with pytest.raises(WorkflowError):
        effects.apply(PLAYER, "wrong-owner", identity, 1, before.revision, choice)
    result = effects.apply(ADMIN, "spawn", identity, 1, before.revision, choice)
    assert result["state"] == "resolved"
    assert effects.apply(ADMIN, "spawn", identity, 1, before.revision, choice) == result
    after = state(game)
    assert after.strain.events == before.strain.events
    assert after.world.gorgons[-1].id == "orbital" and after.world.gorgons[-1].cell is None
    assert activate(cycle, game, period)["phase"] == "active"
    recover_both(cycle, game, period)
    finish_routine(cycle, game, period)
    assert call(cycle, game, ADMIN, period, "finish", ())["phase"] == "complete"
    assert threats(state(game))[0].mission is None

    mission, revision = launched(effects.strain.missions)
    restarted = MissionService(ledger)
    assert threats(state(game))[0].mission == mission
    result = restarted.end(ADMIN, "end", mission, revision, True)
    assert result["rewards_committed"]
    assert restarted.end(ADMIN, "end", mission, revision, True) == result
    final = state(game)
    assert final.world.locations[3].id == "city0"
    assert final.world.locations[3].condition == "destroyed"
    (threat,) = threats(final)
    assert threat.outcome == "destroyed"
    (trigger,) = final.strain.triggers
    assert trigger.entity == "city0" and trigger.source_event == threat.resolved_event
    assert final.strain.events == before.strain.events


def test_medical_exam_is_patient_owned_and_only_actual_discovery_creates_discipline(ledger):
    cycle, effects, game, period, identity = orbital_period(ledger, column=2)
    with ledger.transaction() as conn:
        actual = state(game)
        asset = actual.sheets["2"].assets[0]
        asset.void, asset.concealed, asset.name = True, True, "PRIVATE_VOID_EXAM_ITEM"
        game.event(conn, PLAYER.user_id, "hidden", "synthetic.hidden_asset", actual)
    effects.apply(
        ADMIN,
        "exams",
        identity,
        1,
        state(game).revision,
        Choice(rule_id="strain.void.low.6.2", account="Each original Girl must be examined."),
    )
    service = ExaminationService(OffDutyService(MissionService(ledger)))
    exam = identity + ":exam:2"
    with pytest.raises(WorkflowError, match="Resolve actual Strain/start"):
        activate(cycle, game, period)
    for viewer in (OTHER, ADMIN):
        with pytest.raises(WorkflowError, match="original patient"):
            service.get(viewer, exam)
    assert not any(item.identity == exam for item in InboxService(ledger).items(OTHER))
    with pytest.raises(WorkflowError, match="STALE_EXAMINATION"):
        service.finish(PLAYER, "stale", exam, 1, state(game).revision - 1, (), "Exam done")
    ledger.safety(OTHER, "pause-exam", ledger.status(OTHER)["revision"], pause=True)
    with pytest.raises(WorkflowError, match="SAFETY_PAUSED"):
        service.finish(PLAYER, "paused", exam, 1, state(game).revision, (asset.id,), "Found")
    ledger.safety(OTHER, "resume-exam", ledger.status(OTHER)["revision"], pause=False)
    revision = state(game).revision

    async def record_examination():
        inbox = InboxService(ledger)
        item = next(item for item in inbox.items(PLAYER) if item.identity == exam)
        opening = current(PLAYER.user_id, 95601)
        await opening.response.defer(ephemeral=True)
        await InboxView(inbox, PLAYER.user_id).route(opening, item)
        form = opening.edit_original_response.call_args.kwargs["view"]
        assert isinstance(form, NativeForm)
        assert form.fields[1].options == ((asset.id, "PRIVATE_VOID_EXAM_ITEM"),)
        form.values.update(account="Examiner found the concealed Asset", found_0=(asset.id,))
        await form.confirm.callback(current(PLAYER.user_id, 95602))
        assert form.completed

    asyncio.run(record_examination())
    saved = state(game)
    assert (
        service.finish(
            PLAYER, "95602", exam, 1, revision, (asset.id,), "Examiner found the concealed Asset"
        )["state"]
        == "resolved"
    )
    assert state(game) == saved
    assert any(
        x.kind == "void_observation" and x.owner == PLAYER.user_id for x in saved.obligations
    )
    punishment = exam + ":punishment"
    discipline = PunishmentService(ledger)
    assert discipline.get(ADMIN, punishment)["causes"] == ["void_examination_discovery"]
    assert saved.sheets["2"].assets[0].concealed
    assert not any(item.identity == punishment for item in InboxService(ledger).items(OTHER))
    service.finish(
        OTHER, "clear-exam", identity + ":exam:3", 1, state(game).revision, (), "Nothing found"
    )
    assert activate(cycle, game, period)["phase"] == "active"
    answer = discipline.propose_scene(
        ADMIN, "discipline-scene", punishment, 1, state(game).revision, "The actual Punishment"
    )
    for viewer in (ADMIN, PLAYER):
        answer = discipline.attest_scene(
            viewer, f"attend-{viewer.user_id}", punishment, answer["revision"], state(game).revision
        )
    previous_heat = state(game).sheets["2"].heat
    discipline.apply(
        ADMIN,
        "punishment",
        punishment,
        answer["revision"],
        state(game).revision,
        Details(kind="stimulant_injection"),
    )
    assert state(game).sheets["2"].heat == previous_heat + 7


@pytest.mark.parametrize("addressed", [False, True])
def test_protest_uses_next_actual_mission_and_only_releases_its_own_blockade(ledger, addressed):
    cycle, effects, game, period, exam_source = orbital_period(ledger, column=2, protest=True)
    effects.apply(
        ADMIN,
        "exams",
        exam_source,
        1,
        state(game).revision,
        Choice(rule_id="strain.void.low.6.2", account="All actual Girls attend."),
    )
    examinations = ExaminationService(effects.strain.periods)
    for viewer in (PLAYER, OTHER):
        examinations.finish(
            viewer,
            f"exam-{viewer.user_id}",
            f"{exam_source}:exam:{viewer.user_id}",
            1,
            state(game).revision,
            (),
            "This exam found no Void.",
        )
    identity = next(e.id for e in state(game).strain.events if e.track == "rebellion") + ":effect"

    async def select_protest():
        click = current(ADMIN.user_id, 95620)
        await click.response.defer(ephemeral=True)
        await open_effect(click, effects, identity)
        form = click.edit_original_response.call_args.kwargs["view"]
        form.values.update(
            target=("city0",), faction=("rebel-group",), account="The protest overtakes the city."
        )
        await form.confirm.callback(current(ADMIN.user_id, 95621))
        assert form.completed

    asyncio.run(select_protest())
    assert activate(cycle, game, period)["phase"] == "active"
    with pytest.raises(WorkflowError, match="actual next mission"):
        AnarchyService(ledger).restore(
            ADMIN, "too-soon", identity, state(game).revision, "No dispatch", "No outcome"
        )
    recover_both(cycle, game, period)
    finish_routine(cycle, game, period)
    call(cycle, game, ADMIN, period, "finish", ())
    mission, revision = launched(effects.strain.missions)
    source = civic_source(state(game), identity)
    assert source.mission == mission and source.dispatch_event and source.faction == "rebel-group"
    anarchy = AnarchyService(ledger)
    with pytest.raises(WorkflowError, match="original Handler"):
        anarchy.view(PLAYER, identity)
    if addressed:
        initial_revision = state(game).revision
        assert anarchy.restore(
            ADMIN,
            "address",
            identity,
            initial_revision,
            "The Cadre opened talks",
            "The actual mission was spent on this protest.",
        )["addressed"]
    MissionService(ledger).end(ADMIN, "end", mission, revision, True)
    city = next(x for x in state(game).world.locations if x.id == "city0")
    assert city.condition == "intact"
    assert (identity in city.blocked_by) is not addressed
    if not addressed:
        assert not city.operational
        source_revision = state(game).revision
        result = anarchy.restore(
            ADMIN,
            "liberate",
            identity,
            source_revision,
            "The Cadre returned and liberated the city",
            "The original blockade ended in play.",
        )
        assert result["restored"]
        assert (
            anarchy.restore(
                ADMIN,
                "liberate",
                identity,
                source_revision,
                "The Cadre returned and liberated the city",
                "The original blockade ended in play.",
            )
            == result
        )
        assert next(x for x in state(game).world.locations if x.id == "city0").operational
