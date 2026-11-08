"""Original-body Void thresholds produce actual new identities, bodies and world consequences."""

import pytest
from test_actors import bindings
from test_actors import canon as canon
from test_actors import ledger as ledger
from test_physical_operations import place, ref

from girlframe.engine import m3_void as rules
from girlframe.engine.m3_actors import owned_refs, resolve
from girlframe.engine.m3_void_state import HarpyAsset
from girlframe.engine.m3_world_state import Asset, CorePlan, Gorgon


def threshold(canon, *, family="girl", inside=True, bird=False):
    state = place(canon, mode="piloting" if inside else "outside_frame")
    sheet = state.sheets["2"]
    sheet.girl = "MOCKINGBIRD" if bird else "ALPHA"
    for asset in sheet.assets:
        asset.void = asset.family == family
    return rules.start_threshold(
        state,
        bindings(state),
        ref(state, 2),
        family,
        "actual-corruption",
        "actual-work",
        source_action="root-play",
    )


def questions(canon):
    state, value = threshold(canon)
    state = rules.begin_questions(
        state, bindings(state), value.id, state.sheets["2"].identities[0].id, "entry", "I enter"
    )
    for i in range(5):
        state = rules.answer_question(state, value.id, 2, False, f"answer-{i}", honest=True)
    return state, rules.threshold(state, value.id)


def gorgon(state, event):
    assets = tuple(
        Asset(
            id=x.id,
            name=x.name,
            description=x.description or "Actual transformed original Asset",
            family="gorgon",
            damaged=x.damaged,
            void=True,
        )
        for x in state.sheets["2"].assets
        if x.family == "frame"
    )
    return Gorgon(
        id="actual-grown-frame",
        name="Consumed Frame",
        cell=(0, 0),
        position_event=event,
        gorgon_class="aggressive",
        types=("growth",),
        assets=assets,
        core_plan=CorePlan(assets=(assets[0].id,), weakness="An actual Handler-defined weakness"),
    )


def test_allure_requires_actual_original_frame_entry_and_owned_honest_answers(canon):
    state, value = threshold(canon, inside=False)
    assert value.stage == "allured"
    before = state.model_dump_json()
    with pytest.raises(ValueError, match="original Girl"):
        rules.answer_question(state, value.id, 3, False, "forged", honest=True)
    assert state.model_dump_json() == before
    state = rules.begin_questions(
        state,
        bindings(state),
        value.id,
        state.sheets["2"].identities[0].id,
        "entry",
        "I enter my Frame",
    )
    assert resolve(state, value.actor, bindings(state)).inside_frame
    assert state.sheets["2"].identities[0].name == "Free"
    state = rules.answer_question(state, value.id, 2, True, "honest-yes", honest=True)
    assert rules.threshold(state, value.id).stage == "overgrown"
    assert state.placements[0].incapacitated and not state.placements[0].vitals_active
    with pytest.raises(ValueError, match="original Girl"):
        rules.answer_question(state, value.id, 2, False, "rewrite-yes", honest=True)


def test_actual_rebirth_archives_original_and_creates_separate_owned_resource_port(canon):
    state, value = questions(canon)
    original = state.sheets["2"]
    before = state.model_dump_json()
    assets = tuple(
        HarpyAsset(
            **x.model_dump() | {"description": "My actual rewritten Void Asset", "void": True}
        )
        for x in original.assets
    )
    result = rules.rebirth(
        state,
        bindings(state),
        value.id,
        "actual-rebirth",
        harpy_id="original-harpy",
        new_vessel="actual-new-body",
        archive_id="original-archive",
        profile_id=value.actor.incarnation,
        profile_revision=original.source_profile_revision,
        retained_identities=(),
        new_identities=("Still myself", "Different", "Fourth", "Fifth", "Sixth"),
        retained_tags=(),
        retained_plays=(),
        owned_plays=(),
        discarded_bonds=(),
        assets=assets,
        account="My honest transformation completes",
    )
    assert state.model_dump_json() == before
    assert "2" not in result.sheets and 2 not in result.order
    assert result.career_archives[-1].actor == value.actor
    assert result.career_archives[-1].ending == "harpy"
    harpy = result.harpy_states[0]
    assert harpy.heat == original.heat and harpy.permissions == original.permissions
    assert harpy.old_body_vessel != harpy.body_vessel
    assert len(harpy.identities) == 6
    actor = rules.threshold(result, value.id).resulting_actor
    assert actor in owned_refs(result, 2, bindings(result))
    actual = resolve(result, actor, bindings(result))
    assert actual.heat == harpy.heat and actual.vessel_id == "actual-new-body"
    assert not any(x.id == harpy.id for x in result.world.pilots)
    with pytest.raises(ValueError, match="unfinished"):
        rules.answer_question(result, value.id, 2, False, "replay", honest=True)


def test_frame_escape_actually_damages_girl_asset_and_preserves_original_frame_in_gorgon(canon):
    state, value = threshold(canon, family="frame")
    damage = next(x for x in state.sheets["2"].assets if x.family == "girl" and not x.damaged)
    frame_ids = {x.id for x in state.sheets["2"].assets if x.family == "frame"}
    result = rules.escape_frame(
        state,
        bindings(state),
        value.id,
        damage.id,
        gorgon(state, "real-escape"),
        "real-escape",
        "I tear myself free",
    )
    assert rules.threshold(result, value.id).stage == "escaped"
    assert next(x for x in result.sheets["2"].assets if x.id == damage.id).damaged
    assert result.sheets["2"].frame_scrapped
    assert not any(x.family == "frame" for x in result.sheets["2"].assets)
    assert {x.id for x in result.world.gorgons[-1].assets} == frame_ids
    assert not resolve(result, value.actor, bindings(result)).inside_frame
    assert result.placements[0].vessel_id == state.placements[0].vessel_id


def test_mockingbird_needs_real_in_frame_frame_threshold_and_exact_control_result(canon):
    girl, immune = threshold(canon, family="girl", bird=True)
    assert immune.stage == "prevented"
    state, value = threshold(canon, family="frame", bird=True)
    assert value.stage == "resist_pending"
    resisted = rules.resolve_mockingbird(
        state,
        value.id,
        "result",
        child_action="actual-keep-head",
        in_control=True,
        handler_enough=True,
    )
    assert rules.threshold(resisted, value.id).stage == "prevented"
    failed = rules.resolve_mockingbird(
        state,
        value.id,
        "result",
        child_action="actual-keep-head",
        in_control=True,
        handler_enough=False,
    )
    assert rules.threshold(failed, value.id).stage == "enclosed"
    assert failed.sheets == state.sheets and failed.placements == state.placements


def test_yes_uncertain_survival_is_actual_handler_fate_and_original_body_custody(canon):
    state, value = threshold(canon)
    state = rules.begin_questions(
        state,
        bindings(state),
        value.id,
        state.sheets["2"].identities[0].id,
        "entry",
        "Actual entry",
    )
    state = rules.answer_question(state, value.id, 2, True, "honest-yes", honest=True)
    result = rules.overgrown_fate(
        state,
        value.id,
        gorgon(state, "fate"),
        "fate",
        "Observed living but trapped",
        alive=True,
        archive_id="unused",
        profile_id=value.actor.incarnation,
        profile_revision=state.sheets["2"].source_profile_revision,
    )
    assert rules.threshold(result, value.id).stage == "overgrown_alive"
    assert result.placements[0].custody == rules.threshold(result, value.id).gorgon
    assert result.placements[0].incapacitated and not result.placements[0].vitals_active
    assert not result.harpy_states and "2" in result.sheets


def test_journey_interruption_never_teleports_surviving_original_participant(canon):
    from girlframe.engine import m3_physical as physical
    from girlframe.engine.m3_actor_state import ActorRef

    state = place(canon)
    actor = ref(state, 2)
    supervisor = ActorRef(kind="npc", entity="2")
    state = physical.depart_supervised(
        state, bindings(state), actor, supervisor, "departure", "Actual accompanied trip"
    )
    result = physical.interrupt_journeys(
        state, actor, "actual-career-end", "Original traveler ends career"
    )
    journey = result.escort_journeys[-1]
    assert not journey.active and journey.return_event is None
    assert journey.offstage_refs == (supervisor,)
    assert resolve(result, supervisor, bindings(result)).cell is None
    assert result.placements[0].custody is None
    recovered = physical.recover_interrupted_journey(
        result,
        bindings(result),
        journey.id,
        supervisor,
        (2, 0),
        "actual-recovery",
        "Actual supervisor reaches this place",
    )
    assert resolve(recovered, supervisor, bindings(recovered)).cell == (2, 0)
    assert not recovered.escort_journeys[-1].offstage_refs


def test_outside_frame_corruption_preserves_girl_body_and_costs_no_fictitious_escape(canon):
    state, value = threshold(canon, family="frame", inside=False)
    original_body = state.placements[0]
    original_girl = [x.model_dump() for x in state.sheets["2"].assets if x.family == "girl"]
    assert value.stage == "abandoned"
    result = rules.abandoned_frame(
        state, bindings(state), value.id, gorgon(state, "outside-growth"), "outside-growth"
    )
    assert result.placements[0] == original_body
    assert [
        x.model_dump() for x in result.sheets["2"].assets if x.family == "girl"
    ] == original_girl
    assert result.world.gorgons[-1].cell == original_body.frame_cell


def test_unknown_occupancy_is_reviewed_without_inventing_coordinates_or_resetting_original_vessel(
    canon,
):
    canon.sheets["2"].girl = "ALPHA"
    for asset in canon.sheets["2"].assets:
        asset.void = asset.family == "frame"
    state, value = rules.start_threshold(
        canon, bindings(canon), ref(canon, 2), "frame", "corruption", "source-work"
    )
    assert value.stage == "physical_review" and not state.placements
    result = rules.confirm_occupancy(
        state,
        bindings(state),
        value.id,
        "inside_frame",
        "actual-confirmation",
        "Actual original occupancy",
    )
    assert result.placements[0].girl_cell is result.placements[0].frame_cell is None
    assert rules.threshold(result, value.id).stage == "enclosed"
    with pytest.raises(ValueError, match="genuinely unknown"):
        rules.confirm_occupancy(
            result,
            bindings(result),
            value.id,
            "outside_frame",
            "reset",
            "Cannot reset original body",
        )


def test_actual_frame_swap_parks_original_frame_and_keeps_its_existing_passenger(canon):
    from girlframe.engine import m3_physical as physical
    from girlframe.engine.m3_frame_state import FrameRuntime

    state = place(place(canon), 3)
    rescuer, passenger = ref(state, 2), ref(state, 3)
    state = physical.rescue_to_cockpit(
        state, bindings(state), passenger, rescuer, "actual-rescue", "Actual passenger rescue"
    )
    state = physical.cockpit_exit(
        state,
        bindings(state),
        rescuer,
        "actual-owner-exit",
        "I actually leave the original cockpit",
    )
    old = state.sheets["2"].model_copy(deep=True)
    original_body = next(x for x in state.placements if x.actor == rescuer)
    state.sheets["2"].frame_runtime = FrameRuntime(
        id="actual-new-frame", generation=1, source_work="actual-frame-swap"
    )
    with pytest.raises(ValueError, match="actually delivered"):
        physical.exchange_assigned_frame(
            state, bindings(state), rescuer, old, (2, 0), "bad-delivery", "No teleport"
        )
    result = physical.exchange_assigned_frame(
        state,
        bindings(state),
        rescuer,
        old,
        (0, 0),
        "actual-delivery",
        "The actual new Frame is here",
    )
    body = next(x for x in result.placements if x.actor == rescuer)
    assert body.vessel_id == original_body.vessel_id and body.girl_cell == original_body.girl_cell
    assert body.frame_instance == "actual-new-frame"
    parked = result.parked_frames[-1]
    assert (
        parked.frame_instance == original_body.frame_instance
        and parked.cell == original_body.frame_cell
    )
    assert (
        resolve(result, passenger, bindings(result)).occupied_frame_instance
        == parked.frame_instance
    )
    assert resolve(result, passenger, bindings(result)).cell == parked.cell


def test_original_harpy_supervisor_can_really_return_or_recover_after_trip_interruption(canon):
    from girlframe.engine import m3_physical as physical

    state, value = questions(place(canon, 3))
    original = state.sheets["2"]
    state = rules.rebirth(
        state,
        bindings(state),
        value.id,
        "actual-rebirth",
        harpy_id="same-person-harpy",
        new_vessel="actual-new-vessel",
        archive_id="original-archive",
        profile_id=value.actor.incarnation,
        profile_revision=original.source_profile_revision,
        retained_identities=(),
        new_identities=(),
        retained_tags=(),
        retained_plays=(),
        owned_plays=(),
        discarded_bonds=(),
        assets=tuple(HarpyAsset(**(x.model_dump() | dict(void=True))) for x in original.assets),
        account="Actual rebirth",
    )
    supervisor = rules.threshold(state, value.id).resulting_actor
    traveler = ref(state, 3)
    departed = physical.depart_supervised(
        state,
        bindings(state),
        traveler,
        supervisor,
        "actual-accompanied-departure",
        "Actual supervised trip",
    )
    assert resolve(departed, supervisor, bindings(departed)).cell is None
    assert resolve(departed, supervisor, bindings(departed)).frame_cell is None
    journey = departed.escort_journeys[-1]
    returned = physical.return_from_visit(
        departed,
        bindings(departed),
        traveler,
        journey.traveler_origin,
        supervisor,
        "actual-completed-return",
        "Actual party returned",
    )
    assert resolve(returned, supervisor, bindings(returned)).cell == (0, 0)
    interrupted = physical.interrupt_journeys(
        departed, traveler, "actual-career-interruption", "Actual traveler ends career"
    )
    recovered = physical.recover_interrupted_journey(
        interrupted,
        bindings(interrupted),
        journey.id,
        supervisor,
        (2, 0),
        "actual-harpy-recovery",
        "Actual original Harpy reaches this place",
    )
    assert resolve(recovered, supervisor, bindings(recovered)).cell == (2, 0)
    assert resolve(recovered, supervisor, bindings(recovered)).frame_cell == (2, 0)


@pytest.mark.parametrize("frame_cell", [(2, 0), None])
def test_source_stage_one_actual_arrival_keeps_original_body_and_never_invents_frame_coordinates(
    canon, frame_cell
):
    state, value = threshold(canon, inside=False)
    body = state.placements[0]
    state.placements[0] = body.model_copy(update={"frame_cell": frame_cell})
    chosen = state.sheets["2"].identities[0]
    chosen.marked = True
    state.sheets["2"].sedation_locked = (chosen.id,)
    state.sheets["2"].sedation_period = "actual-period"
    before = [x.model_dump() for x in state.sheets["2"].assets]
    result = rules.confirm_approach(
        state,
        bindings(state),
        value.id,
        chosen.id,
        "actual-independent-arrival-confirmation",
        "Actual source-bound arrival completed",
    )
    assert result.placements[0].vessel_id == body.vessel_id
    assert result.placements[0].girl_cell == result.placements[0].frame_cell == frame_cell
    assert result.placements[0].mode == "inside_frame"
    assert [x.model_dump() for x in result.sheets["2"].assets] == before
    assert result.sheets["2"].identities[0].name == "Free"
    assert result.sheets["2"].identities[0].marked
    assert rules.threshold(result, value.id).stage == "questions"


def test_actual_ending_guardian_interrupts_only_her_source_hold_without_moving_or_healing(canon):
    from girlframe.engine import m3_physical as physical

    state, value = threshold(place(canon, 3, mode="outside_frame"), inside=False)
    guardian = ref(state, 3)
    held = rules.prevent_entry(
        state, bindings(state), value.id, guardian, "actual-hold", "Actual witnessed physical hold"
    )
    body = next(x for x in held.placements if x.actor == value.actor)
    interrupted = physical.interrupt_journeys(
        held, guardian, "actual-guardian-ending", "Actual original guardian career ends"
    )
    after = next(x for x in interrupted.placements if x.actor == value.actor)
    assert after.custody is None and after.girl_cell == body.girl_cell
    assert interrupted.sheets == held.sheets
    assert (
        rules.threshold(interrupted, value.id).protection_release_event == "actual-guardian-ending"
    )


def test_actual_guardian_body_position_follows_custody_and_release_never_returns_to_old_place(
    canon,
):
    from girlframe.engine import m3_physical as physical
    from girlframe.engine.m3_actor_state import ActorRef

    state, value = threshold(canon, inside=False)
    guardian = ActorRef(kind="npc", entity="2")
    held = rules.prevent_entry(
        state, bindings(state), value.id, guardian, "actual-npc-hold", "Actual physical protection"
    )
    held.world = held.world.model_copy(
        update={
            "npcs": tuple(
                x.model_copy(update={"cell": (2, 0)}) if x.id == "2" else x for x in held.world.npcs
            )
        }
    )
    assert resolve(held, value.actor, bindings(held)).cell == (2, 0)
    freed = physical.release_protective_hold(
        held, value.id, guardian, "actual-release", "The actual guardian releases her here"
    )
    assert freed.placements[0].girl_cell == (2, 0) and freed.placements[0].frame_cell == (0, 0)
    assert freed.placements[0].custody is None
