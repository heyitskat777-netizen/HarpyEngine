"""Actual cockpit transitions, rescue, independent Frame consent and unknown positions."""

import pytest
from test_actors import bindings
from test_actors import canon as canon
from test_actors import ledger as ledger

from girlframe.engine import m3_physical as rules
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_physical_state import InitialPlacement


def ref(state, uid):
    return ActorRef(kind="pilot", entity=str(uid), incarnation=state.sheets[str(uid)].character_id)


def place(state, uid=2, *, mode="piloting", cell=(0, 0), frame_cell=None):
    actor = ref(state, uid)
    current = resolve(state, actor, bindings(state))
    return rules.initial(
        state,
        bindings(state),
        InitialPlacement(
            actor=actor,
            frame_instance=current.frame_instance,
            girl_cell=cell,
            frame_cell=cell if frame_cell is None else frame_cell,
            mode=mode,
            account="Actual original physical facts",
            facts_confirmed=True,
        ),
        "original-vessel-" + str(uid),
        "original-proposal-" + str(uid),
        "actual-review-" + str(uid),
    )


def test_owned_exit_and_enter_preserve_body_frame_resources_and_actual_source(canon):
    state = place(canon)
    actor = ref(state, 2)
    before = state.model_dump_json()
    exited = rules.cockpit_exit(state, bindings(state), actor, "actual-exit", "I leave my cockpit")
    assert state.model_dump_json() == before
    assert exited.sheets == state.sheets and exited.world == state.world
    assert exited.placements[0].vessel_id == state.placements[0].vessel_id
    assert not resolve(exited, actor, bindings(exited)).inside_frame
    entered = rules.cockpit_enter(
        exited, bindings(exited), actor, "actual-enter", "I enter my actual Frame", pilot=False
    )
    assert resolve(entered, actor, bindings(entered)).inside_frame
    assert not resolve(entered, actor, bindings(entered)).piloting
    piloted = rules.cockpit_enter(
        entered, bindings(entered), actor, "actual-pilot", "I take control", pilot=True
    )
    assert resolve(piloted, actor, bindings(piloted)).piloting
    with pytest.raises(ValueError, match="already been applied"):
        rules.cockpit_enter(
            piloted, bindings(piloted), actor, "actual-pilot", "Replay", pilot=False
        )


@pytest.mark.parametrize("cell", [(2, 0), None])
def test_enter_cannot_invent_body_movement_or_unknown_frame_location(canon, cell):
    state = place(canon, mode="outside_frame", cell=(2, 0), frame_cell=(0, 0))
    if cell is None:
        state.placements[0] = state.placements[0].model_copy(update={"frame_cell": None})
    with pytest.raises(ValueError, match="already be at the same known cell"):
        rules.cockpit_enter(
            state, bindings(state), ref(state, 2), "bad-enter", "No teleport", pilot=True
        )


def test_defeat_escape_keeps_actual_battlefield_cell_and_abandoned_frame(canon):
    state = place(canon, cell=(1, 0))
    escaped = rules.escape_cockpit(
        state,
        bindings(state),
        ref(state, 2),
        "actual-defeat-escape",
        "I take cover beside the wreck",
    )
    body = escaped.placements[0]
    assert body.mode == "outside_frame" and body.girl_cell == body.frame_cell == (1, 0)
    assert body.vessel_id == state.placements[0].vessel_id and escaped.sheets == state.sheets


def test_legacy_defeat_establishes_only_original_unknown_body_without_map_invention(canon):
    actor = ref(canon, 2)
    escaped = rules.escape_cockpit(
        canon,
        bindings(canon),
        actor,
        "actual-escape",
        "Actual escape from the cockpit",
        prior_event="actual-known-roll",
    )
    body = escaped.placements[0]
    assert body.girl_cell is body.frame_cell is None
    assert body.actor == actor and body.vessel_id != actor.incarnation
    assert (
        rules.original_placement(
            escaped, bindings(escaped), actor, "another-source", "Existing body"
        )[1].vessel_id
        == body.vessel_id
    )
    with pytest.raises(ValueError, match="distinct prior source"):
        rules.escape_cockpit(canon, bindings(canon), actor, "bad-source", "Unknown origin")


def test_real_rescue_keeps_assigned_frame_separate_from_occupied_frame_and_follows_carrier(canon):
    state = place(place(canon, 2), 3, cell=(2, 0))
    target, rescuer = ref(state, 2), ref(state, 3)
    rescued = rules.rescue_to_cockpit(
        state, bindings(state), target, rescuer, "actual-rescue", "Her Frame carries me away"
    )
    actor = resolve(rescued, target, bindings(rescued))
    carrier = resolve(rescued, rescuer, bindings(rescued))
    assert actor.cell == carrier.cell == (2, 0)
    assert actor.frame_cell == (0, 0) and actor.frame_instance != actor.occupied_frame_instance
    assert actor.occupied_frame_instance == carrier.frame_instance
    assert actor.inside_frame and not actor.piloting
    assert rescued.sheets == state.sheets and rescued.placements[0].vessel_id == "original-vessel-2"
    # A later actual carrier move does not leave its passenger behind in a copied map cell.
    rescued.placements[1] = rescued.placements[1].model_copy(
        update={"girl_cell": (1, 1), "frame_cell": (1, 1)}
    )
    assert resolve(rescued, target, bindings(rescued)).cell == (1, 1)
    exited = rules.cockpit_exit(
        rescued, bindings(rescued), target, "exit-rescuer", "I leave her cockpit"
    )
    assert resolve(exited, target, bindings(exited)).cell == (1, 1)
    assert exited.placements[0].frame_cell == (0, 0)


def test_legacy_rescuer_has_unknown_position_but_actual_original_cockpit_not_a_new_frame(canon):
    state = rules.rescue_to_cockpit(
        canon,
        bindings(canon),
        ref(canon, 2),
        ref(canon, 3),
        "actual-legacy-rescue",
        "Actual rescue",
        prior_event="actual-roll",
    )
    assert len(state.placements) == 2
    actor = resolve(state, ref(state, 2), bindings(state))
    assert actor.cell is actor.frame_cell is None and actor.inside_frame
    assert actor.occupied_frame_instance == "initial:" + ref(state, 3).incarnation


def test_source_authorized_rescuer_can_board_her_adjacent_actual_frame_as_part_of_rescue(canon):
    state = place(place(canon, 2), 3, mode="outside_frame", cell=(0, 0))
    actor, rescuer = ref(state, 2), ref(state, 3)
    result = rules.rescue_to_cockpit(
        state,
        bindings(state),
        actor,
        rescuer,
        "actual-rescue-boarding",
        "She boards her present Frame and rescues me",
    )
    assert resolve(result, rescuer, bindings(result)).piloting
    assert (
        resolve(result, actor, bindings(result)).occupied_frame_instance
        == resolve(result, rescuer, bindings(result)).frame_instance
    )


@pytest.mark.parametrize(
    "kind,entity", [("npc", "2"), ("external_pilot", "external"), ("gorgon", "secret")]
)
def test_actual_supervisor_presence_is_offstage_for_the_whole_visit_and_restored_once(
    canon, kind, entity
):
    state = place(canon)
    actor, supervisor = ref(state, 2), ActorRef(kind=kind, entity=entity)
    origin = state.placements[0]
    before = resolve(state, supervisor, bindings(state))
    departed = rules.depart_supervised(
        state,
        bindings(state),
        actor,
        supervisor,
        "actual-supervised-" + kind,
        "The actual supervisor accompanies me",
    )
    away = resolve(departed, supervisor, bindings(departed))
    assert away.cell is None and away.custody.startswith("supervised_visit:")
    returned = rules.return_from_visit(
        departed,
        bindings(departed),
        actor,
        origin,
        supervisor,
        "actual-return-" + kind,
        "The actual supervisor returns with me",
    )
    assert resolve(returned, supervisor, bindings(returned)).cell == before.cell


def test_handler_rescue_records_actual_custody_and_injury_without_invented_destination(canon):
    state = place(canon)
    actor = ref(state, 2)
    rescued = rules.handler_rescue(
        state,
        bindings(state),
        actor,
        ActorRef(kind="handler", entity="1"),
        "actual-handler-rescue",
        "The Handler's agents collect me",
        injured=True,
    )
    body = rescued.placements[0]
    assert body.girl_cell is None and body.frame_cell == (0, 0)
    assert body.mode == "outside_frame" and body.incapacitated and body.vitals_active
    assert body.custody == ActorRef(kind="handler", entity="1")
    recovered = rules.medical_recovery(
        rescued,
        bindings(rescued),
        actor,
        "actual-wake",
        "Actual medical help and waking",
        restore_vitals=True,
    )
    assert not recovered.placements[0].incapacitated and recovered.sheets == state.sheets
    assert recovered.placements[0].girl_cell is None


def test_subsumption_locks_actual_frame_and_dead_vitals_need_separate_real_extraction_and_help(
    canon,
):
    # This fixture exercises an ordinary NPC Frame voice, not JANUS's separate
    # source-admitted ex-Girl Core (covered by actual JANUS admission tests).
    canon.sheets["2"].frame = "THE ENFORCER"
    state = place(canon)
    actor = ref(state, 2)
    locked = rules.lock_cockpit(
        state, bindings(state), actor, "actual-subsumption", "The cockpit seals"
    )
    assert locked.frame_locks[0].active and locked.placements[0].subsumed
    assert not locked.placements[0].vitals_active and locked.sheets == state.sheets
    for operation in (rules.extract, rules.escape_cockpit):
        with pytest.raises(ValueError, match="FRAME_CONSENT_REQUIRED"):
            operation(locked, bindings(locked), actor, "no-consent", "Cannot forge consent")
    with pytest.raises(ValueError, match="actual Frame's human voice"):
        rules.consent_to_extract(
            locked, bindings(locked), actor, 2, "pilot-consent", "Not the Frame", allowed=True
        )
    refused = rules.consent_to_extract(
        locked, bindings(locked), actor, 1, "actual-refusal", "She refuses", allowed=False
    )
    with pytest.raises(ValueError, match="FRAME_CONSENT_REQUIRED"):
        rules.extract(refused, bindings(refused), actor, "refusal-not-consent", "Still sealed")
    allowed = rules.consent_to_extract(
        refused,
        bindings(refused),
        actor,
        1,
        "actual-frame-consent",
        "She explicitly consents",
        allowed=True,
    )
    extracted = rules.extract(
        allowed, bindings(allowed), actor, "actual-extraction", "An actual rescuer extracts me"
    )
    assert not extracted.placements[0].subsumed and not extracted.placements[0].vitals_active
    assert extracted.placements[0].mode == "outside_frame" and extracted.frame_locks[0].active
    assert extracted.frame_locks[0].consents[-1].used_event == "actual-extraction"
    with pytest.raises(ValueError, match="current condition"):
        rules.cockpit_enter(
            extracted, bindings(extracted), actor, "no-healing", "Cannot walk yet", pilot=True
        )
    recovered = rules.medical_recovery(
        extracted,
        bindings(extracted),
        actor,
        "actual-treatment",
        "Actual medical treatment",
        restore_vitals=True,
    )
    assert recovered.placements[0].vitals_active and recovered.sheets == state.sheets
    opened = rules.open_cockpit(
        recovered,
        actor,
        recovered.frame_locks[0].frame_instance,
        1,
        "actual-open",
        "The Frame opens her cockpit",
    )
    assert not opened.frame_locks[0].active
    assert rules.cockpit_enter(
        opened, bindings(opened), actor, "actual-return", "I return", pilot=True
    )


def test_subsumed_passenger_cannot_bypass_actual_carrier_lock_or_pilot_someone_elses_frame(canon):
    canon.sheets["2"].frame = canon.sheets["3"].frame = "THE ENFORCER"
    state = place(place(canon, 2), 3)
    actor, carrier = ref(state, 2), ref(state, 3)
    rescued = rules.rescue_to_cockpit(
        state, bindings(state), actor, carrier, "actual-carrier", "Actual rescue"
    )
    with pytest.raises(ValueError, match="actual linked Frame"):
        rules.lock_cockpit(
            rescued, bindings(rescued), actor, "wrong-cockpit", "Not her linked cockpit"
        )
    locked = rules.lock_cockpit(
        rescued, bindings(rescued), carrier, "actual-carrier-lock", "Her Frame seals"
    )
    with pytest.raises(ValueError, match="FRAME_CONSENT_REQUIRED"):
        rules.cockpit_exit(
            locked, bindings(locked), actor, "guest-exit", "Guest cannot bypass lock"
        )
    allowed = rules.consent_to_extract(
        locked, bindings(locked), actor, 1, "guest-consent", "Frame allows guest exit", allowed=True
    )
    assert rules.cockpit_exit(
        allowed, bindings(allowed), actor, "actual-guest-exit", "Guest leaves"
    )


def test_frame_lock_survives_owner_archival_and_does_not_move_or_restore_another_incarnation(canon):
    state = place(canon)
    actor = ref(state, 2)
    locked = rules.lock_cockpit(
        state, bindings(state), actor, "old-frame-lock", "Original locked cockpit"
    )
    locked.sheets.pop("2")
    locked.order = tuple(x for x in locked.order if x != 2)
    locked.placements.clear()
    assert rules.frame_voice(locked, actor, "initial:" + actor.incarnation) == 1
    opened = rules.open_cockpit(
        locked,
        actor,
        "initial:" + actor.incarnation,
        1,
        "actual-open-old-frame",
        "Frame still has a voice",
    )
    assert not opened.frame_locks[0].active and not opened.placements
    with pytest.raises(ValueError, match="STALE_ACTOR"):
        rules.escape_cockpit(
            opened,
            bindings(opened),
            actor,
            "no-resurrection",
            "Cannot restore old body",
            prior_event="old-roll",
        )


def test_supervised_visit_and_actual_return_preserve_original_body_frame_and_current_injuries(
    canon,
):
    state = place(canon)
    actor, supervisor = ref(state, 2), ActorRef(kind="npc", entity="2")
    origin = state.placements[0]
    departed = rules.depart_supervised(
        state,
        bindings(state),
        actor,
        supervisor,
        "actual-home-visit",
        "Actual supervised home scene",
    )
    assert departed.placements[0].girl_cell is None and departed.placements[0].custody == supervisor
    departed.placements[0] = departed.placements[0].model_copy(update={"incapacitated": True})
    returned = rules.return_from_visit(
        departed,
        bindings(departed),
        actor,
        origin,
        supervisor,
        "actual-return-home",
        "Actual supervised return",
    )
    assert returned.placements[0].vessel_id == origin.vessel_id
    assert (
        returned.placements[0].girl_cell == origin.girl_cell
        and returned.placements[0].mode == "outside_frame"
    )
    assert returned.placements[0].incapacitated and returned.sheets == state.sheets
    with pytest.raises(ValueError, match="recorded supervisor"):
        rules.return_from_visit(
            departed,
            bindings(departed),
            actor,
            origin,
            ActorRef(kind="handler", entity="1"),
            "wrong-transport",
            "No custody substitution",
        )


def test_one_actual_source_can_exit_two_different_owned_bodies_atomically(canon):
    state = place(place(canon, 2), 3)
    exited = rules.cockpit_exit(
        state, bindings(state), ref(state, 2), "actual-two-person-scene", "First participant"
    )
    exited = rules.cockpit_exit(
        exited, bindings(exited), ref(exited, 3), "actual-two-person-scene", "Second participant"
    )
    assert all(x.mode == "outside_frame" for x in exited.placements)
