"""Match approved AI Play suggestions to native controls and owner review."""

import json
from types import SimpleNamespace

import pytest
from girlframe.ai.model_transport import ModelLimits, OpenAIResponses
from girlframe.delivery.m2_worker import GameWorker
from girlframe.engine import (
    m3_alpha,
    m3_ankou,
    m3_casualty,
    m3_consume,
    m3_doctor,
    m3_wyvern,
)
from girlframe.engine.m2 import QUESTIONS, PlayInput
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_handler_advancements import awards
from girlframe.engine.m3_handler_consequences import active_handler
from girlframe.engine.m3_handler_ordinary import RULE as ORDINARY_RULE
from girlframe.engine.m3_janus_pandora import pregnancies
from girlframe.engine.m3_janus_requisitions import PANDORA as PANDORA_RULE
from girlframe.engine.m3_successor import RULE as SUCCESSOR_RULE
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import load_registry
from girlframe.services.m3_janus_requisitions import JanusRequisitionService
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_off_duty import OffDutyService
from girlframe.services.m3_off_duty_cycle import CycleService
from girlframe.services.m3_successor import SuccessorService
from girlframe.services.onboarding import WorkflowError
from girlframe.services.p1_facilitator import UNLISTED_ACTION, FacilitatorService
from handler_award_scenario import ordinary_pr_award
from test_activity_shadow_readiness import (
    consent,
    opt,
    publish_opening,
    review,
    submission,
)
from test_alpha_brutalize import guard_rolled
from test_alpha_brutalize import ready as alpha_ready
from test_alpha_flirt_counter import opportunity as alpha_flirt_opportunity
from test_ankou import buy as buy_ankou
from test_ankou import ready as ankou_ready
from test_beneath_service import ready
from test_bonded import ready as bonded_ready
from test_casualty import ready as casualty_ready
from test_consume import acquire as acquire_consume
from test_consume import cockpit as consume_cockpit
from test_consume import ready as consume_ready
from test_director_observation import Clock
from test_doctor_runtime import acquire as acquire_doctor
from test_doctor_runtime import doctor as doctor_ready
from test_dogrunner_status import dogrunner_ready
from test_dose_up import ready as dose_ready
from test_enforcement_initiative import cast_target
from test_enforcement_initiative import ready as enforcer_ready
from test_enforcement_initiative import start as start_enforcement
from test_enforcer_director_judge import ready as director_ready
from test_enforcer_director_judge import selected as choose_director
from test_enforcer_requisitions import approved
from test_handler_plays import ready as handler_ready
from test_items import linked_frame_item_source
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger_fixture
from test_m2_game import Dice, Gateway, answer, pass_tags, setup_game, state, tick
from test_off_duty_cycle import activate, prepared
from test_physical_operations import place
from test_wyvern import ask_and_answer as wyvern_questions
from test_wyvern import buy as buy_wyvern
from test_wyvern import declare_party
from test_wyvern import ready as wyvern_ready
from test_wyvern import roll as wyvern_roll

import mission_lab  # noqa: F401
from ai_native_plays import ActivityNativePlays
from alpha_controls import BRUTALIZE
from handler_playbook import HandlerPlaybook
from handler_punishments import HandlerPunishments
from native_scene_forms import (
    BONDED_SIDE,
    BONDED_SOURCE,
    CASUALTY_PARTS,
    DOSE,
    DOSE_CONTACT,
    ENFORCEMENT,
    PANDORA,
    PANDORA_CHILD,
    PROCESSOR,
    PROCESSOR_PROPOSAL,
    PROCESSOR_UNLINK,
)
from off_duty_followups import OffDutyFollowups
from owned_followups import OwnedFollowups
from p2_scene import P2Scene, local_fixture_director
from scene_beneath_work import SceneBeneathWork
from specialist_scene import SpecialistScene
from test_final_handler_workflows import bundled_registry  # noqa: F401
from test_identity_specialists import option, popup, press, respond, room_map, scoped
from test_scene_beneath_followups import adapter, scene_work
from wyvern_controls import (
    APPROACH,
    ATTEND,
    DISMISS,
    ESCAPE,
    GIVE_UP,
    PARTY,
    QUESTION,
    VOICE,
)

ledger = ledger_fixture


def close_native_tag_windows(game):
    for viewer in (OTHER, ADMIN, PLAYER):
        if any(choice["kind"] == "tag_window" for choice in game.choices(viewer)):
            respond(
                scoped(game, viewer, "tag_window"),
                viewer,
                "tag_window",
                {"options": "pass"},
            )


@pytest.mark.parametrize("play", ("wyvern_explore", "wyvern_wraith", "wyvern_protector"))
def test_wyvern_native_forms_keep_companion_handler_and_protected_choices_owned(
    ledger, tmp_path, monkeypatch, play,
):
    game, worker, gateway, controls = wyvern_ready(ledger, tmp_path, monkeypatch)
    native = SpecialistScene(game, 900)
    target = current_ref(state(game), OTHER.user_id)

    def submit(viewer, selection, values, key):
        card, form = selection
        return native.perform(viewer, key, card | {"answer": {"operation": form["id"], "values": values}})

    values = {"heat": "1", "context": "The actual original Frame trigger occurs."}
    if play == "wyvern_explore":
        party = popup(native, PLAYER, PARTY)
        declared = submit(PLAYER, party, {"companions": [target.model_dump_json()]}, "create-party")
        assert not any(op["id"] == play for card in native.view(PLAYER, ("relay", "Relay")) for op in card["operations"])
        attendee = popup(native, OTHER, ATTEND)
        with pytest.raises(WorkflowError):
            submit(PLAYER, attendee, {"actors": target.model_dump_json()}, "forged-party-role")
        submit(OTHER, attendee, {"actors": option(attendee, "actors")}, "actual-attendance")
        values["source"] = declared["id"]
    elif play == "wyvern_wraith":
        buy_wyvern(controls, m3_wyvern.WRAITH)
    else:
        buy_wyvern(controls, m3_wyvern.PROTECT)
        values["target"] = target.model_dump_json()
    form = popup(native, PLAYER, play)
    game.dice.faces = (3, 4)
    result = submit(PLAYER, form, values, "original-wyvern")
    root = result["action_id"]
    tick(worker, gateway, 3)
    if game.inspect(PLAYER, root)["state"] != "tag_window":
        respond(scoped(game, PLAYER, "roll"), PLAYER, "roll", {})
    close_native_tag_windows(game)
    original = game.inspect(PLAYER, root)["receipt"]
    ledger.engine.dispose()
    fresh = GameService(ledger, dice=game.dice)
    if play == "wyvern_explore":
        step = "wyvern_questions"
        question = scoped(fresh, PLAYER, step)
        options = next(spec for spec in question[1]["operations"][0]["fields"] if spec["key"] == "options")
        assert options["options"] and all(label in m3_wyvern.QUESTIONS.values() for _, label in options["options"])
        respond(question, PLAYER, step, {"options": "servers", "account": "I ask the Frame."})
        unmark = scoped(fresh, PLAYER, "wyvern_unmark")
        picked = {"account": "I confirm the actual effect."}
        for spec in unmark[1]["operations"][0]["fields"]:
            if spec["key"] == "identities":
                detail = game.decision(PLAYER, unmark[1]["id"])["detail"]
                chosen = [key for key, _ in spec["options"][:detail["count"]]]
                picked["identities"] = chosen if spec["multiple"] else chosen[0]
        respond(unmark, PLAYER, "wyvern_unmark", picked)
        first = popup(native, PLAYER, QUESTION)
        second = popup(native, OTHER, QUESTION)
        submit(PLAYER, first, {"context": "First original contribution."}, "first-frame-answer")
        second = popup(native, OTHER, QUESTION)
        submit(OTHER, second, {"context": "Second original contribution."}, "second-frame-answer")
        done = scoped(fresh, PLAYER, "wyvern_answers_done")
        respond(done, PLAYER, "wyvern_answers_done", {"confirm": "close", "account": "I read both answers."})
        assert len(controls.view(OTHER, root)["questions"][0]["answers"]) == 2
    elif play == "wyvern_wraith":
        respond(scoped(fresh, PLAYER, "wyvern_wraith"), PLAYER, "wyvern_wraith",
                {"options": "gunner", "name": "Relay voice", "account": "Original voice."})
        required = scoped(fresh, ADMIN, "wyvern_wraith_rules")
        params = {"profile": "frame_bound_npc", "rules": "The original Frame hosts the voice."}
        with pytest.raises(WorkflowError):
            respond(required, PLAYER, "wyvern_wraith_rules", params)
        respond(required, ADMIN, "wyvern_wraith_rules", params)
        assert m3_wyvern.records(state(fresh), m3_wyvern.Wraith)[-1].active
    else:
        step = "wyvern_shield_bond"
        shield = scoped(fresh, OTHER, step)
        with pytest.raises(WorkflowError):
            respond(shield, PLAYER, step, {"options": "deepen", "account": "Wrong owner."})
        respond(shield, OTHER, step, {"options": "deepen", "account": "The protected pilot answers."})
        assert m3_wyvern.shielded(state(fresh), target)
    assert fresh.inspect(PLAYER, root)["receipt"] == original
    assert fresh.inspect(PLAYER, root)["state"] == "complete" and game.dice.calls == 1


@pytest.mark.parametrize("play", ("wyvern_wraith", "wyvern_protector"))
def test_wyvern_saved_scene_controls_remain_bound_to_their_original_roles(
    ledger, tmp_path, monkeypatch, play,
):
    from girlframe.engine.m3_world_state import Npc
    from girlframe.services.m3_world import WorldService

    game, worker, gateway, controls = wyvern_ready(ledger, tmp_path, monkeypatch)
    if play == "wyvern_wraith":
        buy_wyvern(controls, m3_wyvern.WRAITH)
        root = wyvern_roll(game, worker, gateway, play=play)
        answer(game, PLAYER, "wyvern_wraith", options=("gunner",), fields={"name": "Relay mind"})
        answer(game, ADMIN, "wyvern_wraith_rules", options=("frame_bound_npc",),
               text="The actual original Frame mind after this table's declaration.")
        mind = m3_wyvern.records(state(game), m3_wyvern.Wraith)[-1]
    else:
        buy_wyvern(controls, m3_wyvern.PROTECT)
        approaching = ActorRef(kind="npc", entity="native-approacher")
        WorldService(MissionService(ledger)).npc(ADMIN, "actor-for-shield-test", state(game).revision, Npc(
            id=approaching.entity, name="Observer", jobs=("civilian",),
            detail="The observer is actually present.", controller=1, cell=(0, 0), revealed=True,
        ))
        cast_target(game, approaching)
        root = wyvern_roll(game, worker, gateway, play=play,
                           target=current_ref(state(game), OTHER.user_id), faces=(6, 6))
    receipt = game.inspect(PLAYER, root)["receipt"]
    tick(worker, gateway, 5)
    ledger.engine.dispose()
    fresh = GameService(ledger, dice=game.dice)
    scene = SpecialistScene(fresh, 900)
    if play == "wyvern_wraith":
        original = popup(scene, OTHER, VOICE)
        assert original[0]["id"] == f"{VOICE}:{mind.id}"
        voice = {"context": "The Frame mind speaks to the original table.", "take_control": "yes"}
        saved = press(scene, OTHER, original, voice, key="owned-wyvern-voice")
        assert press(scene, OTHER, original, voice, key="owned-wyvern-voice") == saved
        dismiss = popup(scene, PLAYER, DISMISS)
        with pytest.raises(WorkflowError):
            press(scene, OTHER, dismiss, {"confirm": "yes"})
        assert controls.view(PLAYER, mind.id)["voices"][-1]["author"] == OTHER.user_id
        press(scene, PLAYER, dismiss, {"confirm": "yes"})
        assert not m3_wyvern.records(state(fresh), m3_wyvern.Wraith)[-1].active
    else:
        start = popup(scene, ADMIN, APPROACH)
        payload = {"actor": approaching.model_dump_json(), "context": "The actual NPC approaches."}
        with pytest.raises(WorkflowError):
            press(scene, OTHER, start, payload)
        approach = press(scene, ADMIN, start, payload)
        abandon = popup(scene, ADMIN, GIVE_UP)
        assert abandon[0]["id"] == f"{GIVE_UP}:{approach['id']}"
        with pytest.raises(WorkflowError):
            press(scene, PLAYER, abandon, {"confirm": "yes", "tag": "Stayed in place"})
        press(scene, ADMIN, abandon, {"confirm": "yes", "tag": "Stayed in place"})
        assert any(x.label == "Stayed in place" and x.giver_actor == approaching
                   for x in state(fresh).sheets["2"].tags)
    assert fresh.inspect(PLAYER, root)["receipt"] == receipt and game.dice.calls == 1


def test_bonded_side_uses_original_pair_and_only_applies_shared_heat_once(ledger, tmp_path, monkeypatch):
    game, worker, gateway, service = bonded_ready(ledger, tmp_path, monkeypatch)
    native = SpecialistScene(game, 900)
    canonical = state(game)
    paired = next(item for item in canonical.sheets["2"].identities if item.paired)
    source = popup(native, PLAYER, BONDED_SOURCE)
    payload = source[0] | {"answer": {"operation": BONDED_SOURCE, "values": {
        "apart": "yes", "context": "I am apart from my actual Pair.",
    }}}
    with pytest.raises(WorkflowError):
        native.perform(OTHER, "foreign-pair-source", payload)
    saved = native.perform(PLAYER, "actual-pair-source", payload)
    assert game.dice.calls == 0
    form = popup(native, PLAYER, BONDED_SIDE)
    assert option(form, "source") == saved["id"]
    inputs = {"source": saved["id"], "heat": "3", "identity": paired.id,
              "gain": "5", "share": "2", "context": "I go to my original Pair."}
    payload = form[0] | {"answer": {"operation": BONDED_SIDE, "values": inputs}}
    game.dice.faces = (3, 3)
    action = native.perform(PLAYER, "roll-paired-side", payload)
    tick(worker, gateway, 3)
    close_native_tag_windows(game)
    ledger.engine.dispose()
    fresh = GameService(ledger, dice=game.dice)
    choice = scoped(fresh, PLAYER, BONDED_SIDE)
    assert choice[1]["root"] == action["action_id"]
    response = {"options": "arrive", "account": "I actually arrive beside the original pilot."}
    with pytest.raises(WorkflowError):
        respond(choice, OTHER, BONDED_SIDE, response)
    respond(choice, PLAYER, BONDED_SIDE, response, key="actual-pair-arrival")
    assert service.view(PLAYER, saved["id"])["phase"] == "complete"
    assert state(fresh).sheets["3"].heat == canonical.sheets["3"].heat + 2
    assert native.perform(PLAYER, "roll-paired-side", payload) == action and game.dice.calls == 1


def test_wyvern_escape_finishes_the_original_return_and_companion_assignment(ledger, tmp_path, monkeypatch):
    game, worker, gateway, controls = wyvern_ready(ledger, tmp_path, monkeypatch)
    companion = current_ref(state(game), OTHER.user_id)
    party_id = declare_party(game, controls, (companion,))
    root = wyvern_roll(game, worker, gateway, play="wyvern_explore", source_work=party_id, faces=(1, 1))
    original = game.inspect(PLAYER, root)["receipt"]
    wyvern_questions(game, controls, root, questions=("panel",), danger="escape")
    ledger.engine.dispose()
    fresh = GameService(ledger, dice=game.dice)
    escape = scoped(fresh, PLAYER, ESCAPE)
    data = {"play": "keep_your_head", "heat": "1", "context": "We take the actual return route."}
    with pytest.raises(WorkflowError):
        respond(escape, OTHER, ESCAPE, data)
    game.dice.faces = (3, 4)
    child = respond(escape, PLAYER, ESCAPE, data, key="actual-wyvern-escape")["action_id"]
    tick(worker, gateway, 3)
    if fresh.inspect(PLAYER, child)["state"] == "ready_to_roll":
        fresh.roll(PLAYER, "actual-escape-roll", child)
    close_native_tag_windows(fresh)
    respond(scoped(fresh, PLAYER, "actor_keep"), PLAYER, "actor_keep", {
        "options": ["tough", "in_control"], "denied": "sexy",
    })
    respond(scoped(fresh, ADMIN, "handler_keep"), ADMIN, "handler_keep", {
        "flag": "yes", "text": "The source return route is open.",
    })
    released = fresh.inspect(PLAYER, root)
    assert released["state"] == "complete" and released["receipt"] == original
    assert game.dice.calls == 2
    return_record = next(row for row in m3_wyvern.records(state(fresh), m3_wyvern.Danger) if row.session == root)
    assert return_record.child == child and return_record.returned_event


def test_brutalize_can_open_the_actual_flirt_counter_without_answering_for_its_target(
    ledger, tmp_path, monkeypatch,
):
    game, worker, gateway, root, original, _ = alpha_flirt_opportunity(ledger, tmp_path, monkeypatch)
    assigned = scoped(game, OTHER, "alpha_counter_play")
    assert "flirt" in dict(assigned[1]["operations"][0]["fields"][0]["options"])
    inputs = {"play": "flirt", "heat": "1", "context": "I address the original Alpha by name."}
    game.dice.faces = (3, 4)
    child = respond(assigned, OTHER, "alpha_counter_play", inputs, key="original-flirt-counter")["action_id"]
    tick(worker, gateway, 4)
    close_native_tag_windows(game)
    respond(scoped(game, OTHER, "actor_flirt"), OTHER, "actor_flirt", {"options": "name"})
    ledger.engine.dispose()
    fresh = GameService(ledger, dice=game.dice)
    question = scoped(fresh, PLAYER, "target_flirt")
    with pytest.raises(WorkflowError):
        respond(question, OTHER, "target_flirt", {"text": "A forged reply."})
    respond(question, PLAYER, "target_flirt", {"text": "Call me by the name I chose."})
    assert fresh.inspect(OTHER, child)["state"] == "complete"
    assert fresh.inspect(PLAYER, root)["receipt"] == original and game.dice.calls == 2


def test_brutalize_flirt_escape_keeps_the_full_response_chain_in_its_scene(
    ledger, tmp_path, monkeypatch,
):
    game, worker, gateway, root, original, _ = alpha_flirt_opportunity(ledger, tmp_path, monkeypatch)
    game.dice.faces = (6, 6)
    counter = respond(scoped(game, OTHER, "alpha_counter_play"), OTHER, "alpha_counter_play", {
        "play": "flirt", "heat": "1", "context": "I address the actual Alpha.",
    })["action_id"]
    tick(worker, gateway, 4)
    close_native_tag_windows(game)
    respond(scoped(game, OTHER, "actor_flirt"), OTHER, "actor_flirt", {
        "options": "name", "fields.extra": "escape", "text": "The actual approach becomes too much.",
    })
    respond(scoped(game, PLAYER, "target_flirt"), PLAYER, "target_flirt", {"text": "My own answer."})
    respond(scoped(game, PLAYER, "flirt_escape"), PLAYER, "flirt_escape", {"options": "play"})
    ledger.engine.dispose()
    fresh = GameService(ledger, dice=game.dice)
    card = scoped(fresh, PLAYER, "escape_play")
    assert card[1]["root"] == root
    values = {"context": "I endure the actual pressure and move away."}
    with pytest.raises(WorkflowError):
        respond(card, OTHER, "escape_play", values)
    game.dice.faces = (4, 4)
    child = respond(card, PLAYER, "escape_play", values)["action_id"]
    tick(worker, gateway, 4)
    close_native_tag_windows(fresh)
    keep = scoped(fresh, PLAYER, "actor_keep")
    assert keep[1]["root"] == root
    respond(keep, PLAYER, "actor_keep", {"options": ["desperate", "tough"], "denied": "sexy"})
    respond(scoped(fresh, ADMIN, "handler_keep"), ADMIN, "handler_keep", {"flag": "yes", "text": "Enough."})
    assert fresh.inspect(PLAYER, child)["state"] == "complete"
    assert fresh.inspect(OTHER, counter)["state"] == "complete"
    assert fresh.inspect(PLAYER, root)["state"] == "complete"
    assert fresh.inspect(PLAYER, root)["receipt"] == original and game.dice.calls == 3


def test_brutalize_beneath_pin_reopens_the_original_targets_response(ledger, tmp_path, monkeypatch):
    game, worker, gateway, root, original, _ = alpha_flirt_opportunity(ledger, tmp_path, monkeypatch)
    game.store.policy = game.store.policy.model_copy(update={
        "owner_m3_rulings": game.store.policy.owner_m3_rulings.model_copy(
            update={"beneath_private_choices": "affected_owner"},
        ),
    })
    game.dice.faces = (5, 5)
    response = respond(scoped(game, OTHER, "alpha_counter_play"), OTHER, "alpha_counter_play", {
        "play": "put_someone_beneath_you", "heat": "1", "context": "I pin the actual Alpha.",
    })["action_id"]
    tick(worker, gateway, 4)
    close_native_tag_windows(game)
    respond(scoped(game, OTHER, "beneath_select"), OTHER, "beneath_select", {
        "options": ["tag", "pin"], "fields.tag": "Pinned", "text": "I pin her by the arm.",
    })
    respond(scoped(game, PLAYER, "beneath_pin_response"), PLAYER, "beneath_pin_response", {"options": "play"})
    ledger.engine.dispose()
    fresh = GameService(ledger, dice=game.dice)
    follow = scoped(fresh, PLAYER, "beneath_response_play")
    assert follow[1]["root"] == root
    game.dice.faces = (4, 4)
    child = respond(follow, PLAYER, "beneath_response_play", {
        "context": "I endure the pressure and loosen the hold.",
    })["action_id"]
    tick(worker, gateway, 4)
    close_native_tag_windows(fresh)
    respond(scoped(fresh, PLAYER, "actor_keep"), PLAYER, "actor_keep", {
        "options": ["desperate", "tough"], "denied": "sexy",
    })
    respond(scoped(fresh, ADMIN, "handler_keep"), ADMIN, "handler_keep", {"flag": "yes", "text": "Enough."})
    assert fresh.inspect(PLAYER, child)["state"] == "complete"
    assert fresh.inspect(OTHER, response)["state"] == "complete"
    assert fresh.inspect(PLAYER, root)["state"] == "complete"
    assert fresh.inspect(PLAYER, root)["receipt"] == original and game.dice.calls == 3


def test_the_actual_guard_controller_owns_the_brutalize_counter(ledger, tmp_path, monkeypatch):
    game, _, npc, root, _, _ = guard_rolled(ledger, tmp_path, monkeypatch, (1, 1))
    receipt = game.inspect(PLAYER, root)["receipt"]
    respond(scoped(game, ADMIN, "alpha_low"), ADMIN, "alpha_low", {"choice": "counter_broken"})
    ledger.engine.dispose()
    fresh = GameService(ledger, dice=game.dice)
    choice = scoped(fresh, ADMIN, "alpha_counter_play")
    assert choice[1]["root"] == root
    params = {"move": "interpose", "context": "The actual Guard steps into the way."}
    with pytest.raises(WorkflowError):
        respond(choice, PLAYER, "alpha_counter_play", params)
    saved = respond(choice, ADMIN, "alpha_counter_play", params, key="actual-guard-counter")
    assert respond(choice, ADMIN, "alpha_counter_play", params, key="actual-guard-counter") == saved
    respond(scoped(fresh, PLAYER, "alpha_npc_mercy"), PLAYER, "alpha_npc_mercy", {"choice": "spare"})
    assert next(x for x in state(fresh).world.npcs if x.id == npc.entity).alive
    assert fresh.inspect(PLAYER, root)["state"] == "complete"
    assert fresh.inspect(PLAYER, root)["receipt"] == receipt and game.dice.calls == 1


def test_enforcement_director_consequence_stays_with_the_directors_controller(
    ledger, tmp_path, monkeypatch,
):
    game, worker, gateway = director_ready(ledger, tmp_path, monkeypatch, (4, 5))
    _, judge = choose_director(game)
    scene = SpecialistScene(game, 900)
    form = popup(scene, PLAYER, ENFORCEMENT)
    root = press(scene, PLAYER, form, {
        "target": judge.model_dump_json(), "heat": "0", "piloting": option(form, "piloting"),
        "context": "The actual original Director is in the Enforcer's grip.",
    })["action_id"]
    tick(worker, gateway, 3)
    close_native_tag_windows(game)
    original = game.inspect(PLAYER, root)["receipt"]
    ledger.engine.dispose()
    fresh = GameService(ledger, dice=game.dice)
    step = "enforcer_director_consequence"
    consequence = scoped(fresh, OTHER, step)
    assert consequence[1]["root"] == root
    fields = {"choice": "injury", "account": "The original Director chooses the printed injury."}
    with pytest.raises(WorkflowError):
        respond(consequence, ADMIN, step, fields)
    saved = respond(consequence, OTHER, step, fields, key="original-director-consequence")
    assert respond(consequence, OTHER, step, fields, key="original-director-consequence") == saved
    assert fresh.inspect(PLAYER, root)["receipt"] == original and game.dice.calls == 1
    assert fresh.inspect(PLAYER, root)["state"] == "complete"


def test_doctor_low_support_recovers_the_exact_handler_grant(ledger, tmp_path, monkeypatch):
    _, game = doctor_ready(ledger, tmp_path, monkeypatch)
    acquire_doctor(game, m3_doctor.SUPPORT)
    scene = SpecialistScene(game, 900)
    form = popup(scene, PLAYER, "doctor_support")
    game.dice.faces = (1, 2)
    root = press(scene, PLAYER, form, {
        "target": option(form, "target"), "heat": "0",
        "context": "The original Doctor asks the eligible protector.",
    })["action_id"]
    tick(GameWorker(game), Gateway(), 3)
    close_native_tag_windows(game)
    old = game.inspect(PLAYER, root)["receipt"]
    pending = next(grant for grant in state(game).handler_plays if grant.source_action == root)
    ledger.engine.dispose()
    fresh = GameService(ledger, dice=game.dice)
    registry = load_registry()
    desk = HandlerPlaybook(ledger, registry, OffDutyFollowups(fresh).periods)
    setup = SimpleNamespace(
        game=fresh, handler=ADMIN, play_registry=registry, handler_playbook=desk,
        handler_rooms=lambda: {900: ("relay", "Relay")},
    )
    with ledger.engine.connect() as c:
        result = ActivityNativePlays(setup, None)(c, fresh.scene(c, 900), active_handler(state(fresh)))
    assert any(row["control"] == pending.id and row["id"].startswith("handler_escalate:")
               for row in result)
    projection = next(row for row in desk.view(ADMIN)["tasks"] if row["id"] == pending.id)
    effect = {
        "id": pending.id, "revision": projection["revision"], "play": "escalate",
        "account": "The original Handler files the danger.", "detail": "The hiding place is exposed.",
        "stakes": "The Doctor must leave cover.", "fields": {},
    }
    with pytest.raises(WorkflowError):
        desk.perform(PLAYER, "foreign-support-response", "handler-play-submit", effect)
    saved = desk.perform(ADMIN, "owned-support-response", "handler-play-submit", effect)
    assert desk.perform(ADMIN, "owned-support-response", "handler-play-submit", effect) == saved
    assert fresh.inspect(PLAYER, root)["state"] == "complete"
    assert fresh.inspect(PLAYER, root)["receipt"] == old and fresh.dice.calls == 1


def test_enforcement_item_void_resistance_returns_to_the_original_scene(ledger, tmp_path, monkeypatch):
    game, worker, gateway, asset = linked_frame_item_source(ledger, tmp_path, monkeypatch)
    scene = SpecialistScene(game, 900)
    form = popup(scene, PLAYER, ENFORCEMENT)
    actor = current_ref(state(game), OTHER.user_id)
    root = press(scene, PLAYER, form, {
        "target": actor.model_dump_json(), "heat": "0", "piloting": "yes",
        "context": "The original Enforcer attempts a Frame grip.",
    })["action_id"]
    tick(worker, gateway, 3)
    close_native_tag_windows(game)
    original = game.inspect(PLAYER, root)["receipt"]
    respond(scoped(game, PLAYER, "enforcer_select"), PLAYER, "enforcer_select", {
        "options": ["item", "escape"],
    })
    respond(scoped(game, OTHER, "enforcer_item"), OTHER, "enforcer_item", {
        "item": "asset:" + asset.id, "account": "I take the original carried object.",
    })
    respond(scoped(game, OTHER, "enforcer_receive"), OTHER, "enforcer_receive", {})
    ledger.engine.dispose()
    fresh = GameService(ledger, dice=game.dice)
    followups = OwnedFollowups(fresh, room_map)
    scenes = SceneBeneathWork(fresh, room_map, followups)

    def card(viewer, step):
        item = next(row for row in scenes.view(viewer, followups.view(viewer)) if row["action"] == step)
        assert item["root"] == root
        return item

    threshold = card(PLAYER, "resolve_void")
    request = {"operation": "resist", "values": {
        "channel": "900", "heat": "0", "account": "I resist the actual threshold.",
    }}
    with pytest.raises(WorkflowError):
        scene_work(scenes, OTHER, threshold, request)
    game.dice.faces = (4, 4)
    child = scene_work(scenes, PLAYER, threshold, request)["action_id"]
    tick(worker, gateway, 3)
    pass_tags(fresh)
    for viewer, payload in (
        (PLAYER, {"options": ["in_control", "tough"], "denied": ["sexy"], "text": "I meet the actual threat."}),
        (ADMIN, {"flag": True, "text": "The original resistance is enough."}),
    ):
        scene_work(scenes, viewer, card(viewer, "followup_decision"), payload)
    respond(scoped(fresh, OTHER, "enforcer_escape"), OTHER, "enforcer_escape", {
        "account": "I escape the grip without changing my map position.",
    })
    assert fresh.inspect(PLAYER, child)["state"] == "complete"
    assert fresh.inspect(PLAYER, root)["state"] == "complete"
    assert fresh.inspect(PLAYER, root)["receipt"] == original and game.dice.calls == 2


def test_handler_casualty_uses_actual_part_and_original_scene(ledger, tmp_path, monkeypatch):
    game, _, _, service = casualty_ready(ledger, tmp_path, monkeypatch)
    native = SpecialistScene(game, 900)
    form = popup(native, ADMIN, CASUALTY_PARTS)
    target = current_ref(state(game), PLAYER.user_id)
    assert option(form, "actor") == target.model_dump_json()
    setup = SimpleNamespace(
        game=game, handler=ADMIN, play_registry=load_registry(),
        handler_playbook=HandlerPlaybook(ledger, load_registry(), OffDutyFollowups(game).periods),
        handler_rooms=lambda: {900: ("relay", "Relay")},
    )
    with ledger.engine.connect() as c:
        options = ActivityNativePlays(setup, None)(c, game.scene(c, 900), active_handler(state(game)))
        proposal = next(item for item in options if item["id"] == CASUALTY_PARTS)
        assert proposal["room"] == "relay" and proposal["destination"] == "handler_scene_specialist"
    values = {"actor": option(form, "actor"), "part": "brain", "condition": "broken",
              "context": "Original part damage in the scene."}
    payload = form[0] | {"answer": {"operation": CASUALTY_PARTS, "values": values}}
    with pytest.raises(WorkflowError):
        native.perform(PLAYER, "foreign-handler-damage", payload)
    wrong = values | {"actor": current_ref(state(game), OTHER.user_id).model_dump_json()}
    with pytest.raises(WorkflowError):
        native.perform(ADMIN, "foreign-body-damage", form[0] | {
            "answer": {"operation": CASUALTY_PARTS, "values": wrong},
        })
    result = native.perform(ADMIN, "actual-handler-damage", payload)
    assert native.perform(ADMIN, "actual-handler-damage", payload) == result
    ledger.engine.dispose()
    body = m3_casualty.body(state(game), target)
    assert next(part for part in body.parts if part.id == "brain").condition == "broken"
    assert service.menu(PLAYER, 900)["parts"]
    assert game.dice.calls == 0


def test_brutalize_counter_reserves_original_action_and_waits_for_handler(ledger, tmp_path, monkeypatch):
    game, worker, gateway = alpha_ready(ledger, tmp_path, monkeypatch, (1, 1))
    native = SpecialistScene(game, 900)
    form = popup(native, PLAYER, BRUTALIZE)
    payload = form[0] | {"answer": {"operation": BRUTALIZE, "values": {
        "target": option(form, "target"), "heat": "0", "context": "There is an actual confrontation.",
    }}}
    root = native.perform(PLAYER, "file-original-brutalize", payload)["action_id"]
    tick(worker, gateway, 3)
    if game.inspect(PLAYER, root)["state"] != "tag_window":
        respond(scoped(game, PLAYER, "roll"), PLAYER, "roll", {})
    close_native_tag_windows(game)
    original_roll = game.inspect(PLAYER, root)["receipt"]
    recipient = scoped(game, OTHER, "alpha_low")
    assert recipient[1]["root"] == root
    with pytest.raises(WorkflowError):
        respond(recipient, PLAYER, "alpha_low", {"choice": "counter_broken"})
    respond(recipient, OTHER, "alpha_low", {"choice": "counter_broken"})
    ledger.engine.dispose()
    counter = scoped(game, OTHER, "alpha_counter_play")
    assert counter[1]["root"] == root
    game.dice.faces = (2, 3)
    inputs = {"play": "keep_your_head", "heat": "0", "context": "I keep composed in the same scene."}
    with pytest.raises(WorkflowError):
        respond(counter, PLAYER, "alpha_counter_play", inputs)
    saved = respond(counter, OTHER, "alpha_counter_play", inputs, key="original-alpha-counter")
    assert respond(counter, OTHER, "alpha_counter_play", inputs, key="original-alpha-counter") == saved
    tick(worker, gateway, 3)
    close_native_tag_windows(game)
    respond(scoped(game, OTHER, "actor_keep"), OTHER, "actor_keep", {"options": "sexy"})
    pending = scoped(game, ADMIN, "handler_keep")
    assert pending[1]["root"] == root and game.inspect(PLAYER, root)["state"] != "complete"
    respond(pending, ADMIN, "handler_keep", {"flag": "yes", "text": "The actual counter holds."})
    final = state(game)
    assert m3_alpha.conditions(final, current_ref(final, 2), current_ref(final, 3))
    assert game.inspect(PLAYER, root)["receipt"] == original_roll
    assert game.inspect(PLAYER, root)["state"] == "complete" and game.dice.calls == 2


def test_ankou_processor_keeps_original_range_roll_and_owned_unlink(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, source = ankou_ready(ledger, tmp_path, monkeypatch)
    buy_ankou(source, m3_ankou.PROCESSOR)
    original = state(game)
    native = SpecialistScene(game, 900)
    proposal, _ = popup(native, PLAYER, PROCESSOR_PROPOSAL)
    request = proposal | {
        "answer": {
            "operation": PROCESSOR_PROPOSAL,
            "values": {
                "cadre": "no",
                "context": "The actual original nearby minds are in range.",
            },
        }
    }
    assert not any(
        op["id"] == PROCESSOR
        for card in native.view(PLAYER, ("relay", "Relay"))
        for op in card["operations"]
    )
    ref = native.perform(PLAYER, "original-processor-proposal", request)
    game.dice.faces = (3, 4)
    card, operation = popup(native, PLAYER, PROCESSOR)
    assert option((card, operation), "source") == ref["id"]
    payload = card | {
        "answer": {
            "operation": PROCESSOR,
            "values": {
                "source": ref["id"],
                "heat": "1",
                "context": "The local pilot connects the original minds.",
            },
        }
    }
    result = native.perform(PLAYER, "file-original-processor", payload)
    tick(worker, gateway, 3)
    saved = game.inspect(PLAYER, result["action_id"])
    if saved["state"] == "tag_window":
        original_receipt = saved["receipt"]
    else:
        pending = scoped(game, PLAYER, "roll")
        with pytest.raises(WorkflowError):
            respond(pending, OTHER, "roll", {})
        roll = respond(pending, PLAYER, "roll", {}, key="confirm-processor-roll")
        assert respond(pending, PLAYER, "roll", {}, key="confirm-processor-roll") == roll
        original_receipt = roll["receipt"]
    close_native_tag_windows(game)
    ledger.engine.dispose()
    fresh = GameService(ledger, dice=game.dice)
    choice = scoped(fresh, PLAYER, "ankou_processor_benefits")
    values = {"benefit0": "champion", "benefit1": "eyes"}
    with pytest.raises(WorkflowError):
        respond(choice, OTHER, "ankou_processor_benefits", values)
    respond(choice, PLAYER, "ankou_processor_benefits", values)
    record = m3_ankou.get(state(fresh), m3_ankou.Processor, result["action_id"])
    assert record.minds == (current_ref(state(fresh), OTHER.user_id),)
    assert record.assets and record.completed_event
    assert state(fresh).sheets["2"].heat == original.sheets["2"].heat - 1
    assert state(fresh).sheets["3"].identities == original.sheets["3"].identities
    tick(worker, gateway, 5)
    card, _ = popup(native, PLAYER, PROCESSOR_UNLINK)
    payload = card | {
        "answer": {
            "operation": PROCESSOR_UNLINK,
            "values": {
                "source": record.id,
                "context": "File the actual unlink.",
            },
        }
    }
    expired = native.perform(PLAYER, "end-processor", payload)
    assert native.perform(PLAYER, "end-processor", payload) == expired
    assert fresh.inspect(PLAYER, record.id)["receipt"] == original_receipt
    assert not any(item.id in record.assets for item in state(fresh).sheets["2"].assets)
    assert game.dice.calls == 1


def test_pandora_requires_actual_preparation_and_only_original_handler_files_child(
    ledger,
    tmp_path,
    monkeypatch,
):
    _, game, period = prepared(ledger)
    approved(ledger, game, tmp_path, monkeypatch, extra=(PANDORA_RULE,))
    with ledger.transaction() as c:
        canon = place(state(game), 2, mode="inside_frame", cell=(0, 0))
        canon.sheets["2"].permissions = 2
        game.event(
            c, 1, "pandora-source-funds", "synthetic.actual_pandora_source", canon
        )
    native = SpecialistScene(game, 900)
    assert not any(
        op["id"] == PANDORA
        for card in native.view(PLAYER, ("relay", "Relay"))
        for op in card["operations"]
    )
    service = JanusRequisitionService(game)
    service.buy_rule(
        PLAYER,
        "acquire-pandora",
        service.menu(PLAYER)["source_sha256"],
        PANDORA_RULE,
        "Pay for the actual original ability.",
    )
    activate(CycleService(OffDutyService(MissionService(ledger))), game, period)
    assert pregnancies(state(game))[-1].phase == "inseminated"
    form = popup(native, PLAYER, PANDORA)
    values = {"heat": "0", "context": "Record actual birth in the original scene."}
    payload = form[0] | {"answer": {"operation": PANDORA, "values": values}}
    game.dice.faces = (4, 5)
    root = native.perform(PLAYER, "file-actual-birth", payload)["action_id"]
    worker, gateway = GameWorker(game), Gateway()
    tick(worker, gateway, 3)
    if game.inspect(PLAYER, root)["state"] != "tag_window":
        respond(
            scoped(game, PLAYER, "roll"), PLAYER, "roll", {}, key="roll-original-birth"
        )
    close_native_tag_windows(game)
    ledger.engine.dispose()
    fresh = GameService(ledger, dice=game.dice)
    kind = PANDORA_CHILD + ":growth"
    child = scoped(fresh, ADMIN, kind)
    assert child[1]["root"] == root
    values = {
        "name": "Relay child",
        "class": "benevolent",
        "asset0": "Overgrown Musculature",
        "description0": "Records the original source",
        "asset1": "Infectious Flagella",
        "description1": "Records the original body",
        "core": ["0"],
        "weakness": "Original weakness",
        "account": "File the actual behavior.",
    }
    with pytest.raises(WorkflowError):
        respond(child, OTHER, kind, values)
    result = respond(child, ADMIN, kind, values, key="original-born-child")
    assert respond(child, ADMIN, kind, values, key="original-born-child") == result
    assert fresh.inspect(PLAYER, root)["receipt"]["faces"] == [4, 5]
    assert fresh.inspect(PLAYER, root)["state"] == "complete"
    assert pregnancies(state(fresh))[-1].child is not None and game.dice.calls == 1


def test_consume_eat_and_high_feral_resume_the_original_effects(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, controls = consume_ready(ledger, tmp_path, monkeypatch)
    acquire_consume(controls, m3_consume.FERAL)
    consume_cockpit(game, "pilot")
    native = SpecialistScene(game, 900)
    eat, eat_form = popup(native, PLAYER, "consume_eat")
    game.dice.faces = (3, 4)
    target = current_ref(state(game), OTHER.user_id)
    payload = eat | {
        "answer": {
            "operation": "consume_eat",
            "values": {
                "target": target.model_dump_json(),
                "heat": "1",
                "context": "The actual target is within reach.",
            },
        }
    }
    assert target.model_dump_json() in dict(
        next(item["options"] for item in eat_form["fields"] if item["key"] == "target")
    )
    root = native.perform(PLAYER, "consume-eat-source", payload)["action_id"]
    tick(worker, gateway, 3)
    close_native_tag_windows(game)
    portion = scoped(game, PLAYER, "consume_eat")
    form = next(op for op in portion[1]["operations"] if op["id"] == "consume_eat")
    target_assets = next(
        item["options"] for item in form["fields"] if item["key"] == "target_asset"
    )
    target_asset = target_assets[0][0]
    choice = {
        "option": "bite",
        "target_asset": target_asset,
        "account": "I file the performed bite.",
    }
    for item in form["fields"]:
        if item["key"] == "own_asset":
            choice["own_asset"] = item["options"][0][0]
    with pytest.raises(WorkflowError):
        respond(portion, OTHER, "consume_eat", choice)
    respond(portion, PLAYER, "consume_eat", choice)
    assert game.inspect(PLAYER, root)["state"] == "complete"
    assert next(
        x for x in state(game).sheets["3"].assets if x.id == target_asset
    ).damaged
    tick(worker, gateway, 5)

    feral, _ = popup(native, PLAYER, "consume_feral")
    game.dice.faces = (6, 6)
    payload = feral | {
        "answer": {
            "operation": "consume_feral",
            "values": {"context": "I act on the original Frame's impulse."},
        }
    }
    origin = native.perform(PLAYER, "feral-source", payload)["action_id"]
    tick(worker, gateway, 3)
    close_native_tag_windows(game)
    assigned = scoped(game, ADMIN, "consume_feral")
    respond(
        assigned,
        ADMIN,
        "consume_feral",
        {"option": "bloodhound", "account": "File the original effect."},
    )
    parent_receipt = game.inspect(PLAYER, origin)["receipt"]
    ledger.engine.dispose()
    child = scoped(game, PLAYER, "consume_child")
    assert child[1]["root"] == origin
    request = {
        "play": "check_sensors",
        "heat": "0",
        "context": "Look for a trace using the original Tag.",
    }
    with pytest.raises(WorkflowError):
        respond(child, OTHER, "consume_child", request)
    game.dice.faces = (3, 4)
    result = respond(child, PLAYER, "consume_child", request, key="feral-child-roll")
    assert (
        respond(child, PLAYER, "consume_child", request, key="feral-child-roll")
        == result
    )
    tick(worker, gateway, 3)
    close_native_tag_windows(game)
    respond(
        scoped(game, PLAYER, "actor_sensors"),
        PLAYER,
        "actor_sensors",
        {"options": list(QUESTIONS[:2])},
    )
    respond(
        scoped(game, ADMIN, "handler_sensors"),
        ADMIN,
        "handler_sensors",
        {"fields.a1": "Actual sign", "fields.a2": "Actual trail"},
    )
    assert game.inspect(PLAYER, origin)["receipt"] == parent_receipt
    assert game.inspect(PLAYER, origin)["state"] == "complete"
    assert game.dice.calls == 3


def test_dose_up_requires_original_contact_and_reopens_each_owned_component(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, dose = dose_ready(ledger, tmp_path, monkeypatch)
    game.dice.faces = (6, 6)
    native = SpecialistScene(game, 900)
    before = popup(native, PLAYER, DOSE)
    assert option(before, "source") == "self"
    contact, contact_form = popup(native, PLAYER, DOSE_CONTACT)
    values = {
        "target": option((contact, contact_form), "target"),
        "context": "The original pilot is within reach.",
    }
    data = contact | {"answer": {"operation": DOSE_CONTACT, "values": values}}
    with pytest.raises(WorkflowError):
        native.perform(OTHER, "wrong-contact-owner", data)
    saved_contact = native.perform(PLAYER, "exact-contact", data)
    assert native.perform(PLAYER, "exact-contact", data) == saved_contact
    assert game.dice.calls == 0
    card, form = popup(native, PLAYER, DOSE)
    sources = next(
        field["options"] for field in form["fields"] if field["key"] == "source"
    )
    encoded, _ = next(row for row in sources if row[0] != "self")
    assert json.loads(encoded)["id"] == saved_contact["id"]
    values = {
        "source": encoded,
        "heat": "0",
        "context": "Log the actual prepared treatment.",
    }
    data = card | {"answer": {"operation": DOSE, "values": values}}
    root = native.perform(PLAYER, "exact-dose", data)["action_id"]
    tick(worker, gateway, 3)
    for viewer in (OTHER, ADMIN, PLAYER):
        respond(
            scoped(game, viewer, "tag_window"),
            viewer,
            "tag_window",
            {"options": "pass"},
        )
    step = "dose_up_components"
    pilot = scoped(game, PLAYER, step)
    assert pilot[1]["root"] == root and pilot[1]["scene"] == "Original roll · 6 + 6"
    with pytest.raises(WorkflowError):
        respond(pilot, OTHER, step, {"components": ["calm", "bliss"]})
    respond(pilot, PLAYER, step, {"components": ["calm", "bliss"]})
    ledger.engine.dispose()
    fresh = GameService(ledger, dice=game.dice)
    handler = scoped(fresh, ADMIN, step)
    with pytest.raises(WorkflowError):
        respond(handler, ADMIN, step, {"components": "calm"})
    result = respond(
        handler, ADMIN, step, {"components": "sense"}, key="separate-handler-component"
    )
    assert (
        respond(
            handler,
            ADMIN,
            step,
            {"components": "sense"},
            key="separate-handler-component",
        )
        == result
    )
    assert (
        dose.view(OTHER, root)["components"]
        and fresh.inspect(PLAYER, root)["state"] == "complete"
    )
    assert game.dice.calls == 1


@pytest.mark.parametrize("play", ("nanobot_injection", "doctor_support"))
def test_doctor_roll_preserves_track_cost_and_patient_ownership(
    ledger, tmp_path, monkeypatch, play
):
    _, game = doctor_ready(ledger, tmp_path, monkeypatch)
    if play == "doctor_support":
        acquire_doctor(game, m3_doctor.SUPPORT)
        game.dice.faces = (4, 5)
    else:
        game.dice.faces = (3, 4)
        with ledger.transaction() as c:
            current = state(game)
            current.sheets["2"].heat = 2
            for asset in current.sheets["3"].assets[:2]:
                asset.damaged = True
            current.sheets["3"].identities[0].marked = True
            game.event(
                c,
                1,
                "native-doctor-fixture",
                "synthetic.actual_medical_resources",
                current,
            )
    projection = ActivityNativePlays(
        SimpleNamespace(
            game=game,
            handler=ADMIN,
            scene_plays=adapter(game),
            play_registry=load_registry(),
            handler_rooms=lambda: {900: ("relay", "Relay")},
        ),
        None,
    )
    canon = state(game)
    patient = current_ref(canon, OTHER.user_id)
    with ledger.engine.connect() as c:
        scene = game.scene(c, 900)
        options = projection(c, scene, current_ref(canon, PLAYER.user_id))
        assert any(row["id"] == play and row["control"] == play for row in options)
        assert all(row["id"] != play for row in projection(c, scene, patient))
    native = SpecialistScene(game, 900)
    card, operation = popup(native, PLAYER, play)
    targets = next(
        spec["options"] for spec in operation["fields"] if spec["key"] == "target"
    )
    assert patient.model_dump_json() in dict(targets)
    if play == "doctor_support":
        assert current_ref(canon, PLAYER.user_id).model_dump_json() not in dict(targets)
    values = {
        "target": patient.model_dump_json(),
        "heat": "2" if play == "nanobot_injection" else "0",
        "context": "The actual original actor and patient are in the relay room.",
    }
    payload = card | {"answer": {"operation": play, "values": values}}
    result = native.perform(PLAYER, "native-medical-play", payload)
    tick(GameWorker(game), Gateway(), 3)
    for viewer in (OTHER, ADMIN, PLAYER):
        respond(
            scoped(game, viewer, "tag_window"),
            viewer,
            "tag_window",
            {"options": "pass"},
        )
    if play == "nanobot_injection":
        respond(
            scoped(game, PLAYER, "doctor_nanobot_benefits"),
            PLAYER,
            "doctor_nanobot_benefits",
            {"choices": ["repair", "identity"]},
        )
        step = "doctor_patient"
        answer = {
            "assets": [asset.id for asset in canon.sheets["3"].assets[:2]],
            "identity": canon.sheets["3"].identities[0].id,
        }
    else:
        step = "doctor_support_response"
        answer = {"decision": "protect", "bond": "yes"}
    ledger.engine.dispose()
    fresh = GameService(ledger, dice=game.dice)
    pending = scoped(fresh, OTHER, step)
    assert pending[1]["root"] == result["action_id"]
    with pytest.raises(WorkflowError):
        respond(pending, PLAYER, step, answer)
    saved = respond(pending, OTHER, step, answer, key="actual-patient-answer")
    assert respond(pending, OTHER, step, answer, key="actual-patient-answer") == saved
    assert fresh.inspect(PLAYER, result["action_id"])["state"] == "complete"
    assert native.perform(PLAYER, "native-medical-play", payload) == result
    assert game.dice.calls == 1
    if play == "nanobot_injection":
        final = state(fresh)
        assert final.sheets["2"].heat == 0 and final.sheets["3"].heat == 2
        assert final.sheets["2"].obsolescence_marked == 1
        assert not any(asset.damaged for asset in final.sheets["3"].assets[:2])
        assert not final.sheets["3"].identities[0].marked


def test_enforcement_handoff_roll_and_low_responses_reopen_for_original_owners(
    ledger,
    tmp_path,
    monkeypatch,
):
    game, worker, gateway = enforcer_ready(ledger, tmp_path, monkeypatch, (1, 1))
    registry = load_registry()
    setup = SimpleNamespace(
        game=game,
        handler=ADMIN,
        scene_plays=adapter(game),
        play_registry=registry,
        handler_rooms=lambda: {900: ("relay", "Relay")},
    )
    projection = ActivityNativePlays(setup, None)
    with ledger.engine.connect() as c:
        scene = game.scene(c, 900)
        canon = load_state(c, ledger.campaign_id)
        mine = {
            row["id"]: row
            for row in projection(c, scene, current_ref(canon, PLAYER.user_id))
        }
        theirs = {
            row["id"] for row in projection(c, scene, current_ref(canon, OTHER.user_id))
        }
    assert mine[ENFORCEMENT]["control"] == ENFORCEMENT
    assert (
        mine[ENFORCEMENT]["destination"] == "scene_specialist"
        and ENFORCEMENT not in theirs
    )
    sheet = SpecialistScene(game, 900)
    card, operation = popup(sheet, PLAYER, ENFORCEMENT)
    values = {
        "target": option((card, operation), "target"),
        "heat": "0",
        "piloting": option((card, operation), "piloting"),
        "context": "Hold the original pilot.",
    }
    req = card | {"answer": {"operation": ENFORCEMENT, "values": values}}
    with pytest.raises(WorkflowError):
        sheet.perform(OTHER, "no-foreign-start", req)
    result = sheet.perform(PLAYER, "file-enforcement-original", req)
    assert game.dice.calls == 0
    tick(worker, gateway, 3)
    for viewer in (OTHER, ADMIN, PLAYER):
        respond(
            scoped(game, viewer, "tag_window"),
            viewer,
            "tag_window",
            {"options": "pass"},
        )
    (scene_work, select) = scoped(game, PLAYER, "enforcer_select")
    assert select["room"] == "relay" and select["root"] == result["action_id"]
    assert select["scene"] == "Original roll · 1 + 1"
    with pytest.raises(WorkflowError):
        respond(
            (scene_work, select),
            OTHER,
            "enforcer_select",
            {"options": ["tag", "disapproval"]},
        )
    respond(
        (scene_work, select),
        PLAYER,
        "enforcer_select",
        {"options": ["tag", "disapproval"]},
    )
    ledger.engine.dispose()
    fresh = GameService(ledger, dice=game.dice)
    target_form = scoped(fresh, OTHER, "enforcer_tag")
    assert target_form[1]["root"] == result["action_id"]
    with pytest.raises(WorkflowError):
        respond(target_form, PLAYER, "enforcer_tag", {"account": "Wrong owner."})
    saved = respond(
        target_form, OTHER, "enforcer_tag", {"account": "Off Record"}, key="tag-owner"
    )
    assert (
        respond(
            target_form,
            OTHER,
            "enforcer_tag",
            {"account": "Off Record"},
            key="tag-owner",
        )
        == saved
    )
    handler_form = scoped(fresh, ADMIN, "enforcer_disapproval")
    with pytest.raises(WorkflowError):
        respond(
            handler_form, PLAYER, "enforcer_disapproval", {"account": "Wrong owner."}
        )
    respond(
        handler_form, ADMIN, "enforcer_disapproval", {"account": "Log the disapproval."}
    )
    actual = fresh.inspect(PLAYER, result["action_id"])
    assert actual["state"] == "complete" and actual["receipt"]["faces"] == [1, 1]
    assert sheet.perform(PLAYER, "file-enforcement-original", req) == result
    assert game.dice.calls == 1


def test_enforcement_high_punishment_reuses_the_owned_steps_in_the_same_popup(
    ledger,
    tmp_path,
    monkeypatch,
):
    game, worker, gateway = enforcer_ready(ledger, tmp_path, monkeypatch, (6, 6))
    root = start_enforcement(game)
    tick(worker, gateway, 3)
    for viewer in (OTHER, ADMIN, PLAYER):
        respond(
            scoped(game, viewer, "tag_window"),
            viewer,
            "tag_window",
            {"options": "pass"},
        )
    rooms = lambda: {900: ("relay", "Relay")}
    scene = SceneBeneathWork(game, rooms)
    desk = HandlerPunishments(game)

    def card(viewer, step):
        item = next(
            row
            for row in scene.view(viewer, role_cards=desk.view(viewer))
            if row["action"] == step
        )
        assert item["root"] == root and item["room"] == "relay"
        return item

    def file(viewer, item, answer, key, **fields):
        data = {k: item[k] for k in ("id", "revision", "action", "root")} | {
            "answer": answer
        }
        return scene.perform(viewer, key, data | fields)

    first = card(ADMIN, "instruct")
    assert any(form["kind"] == "quality_time" for form in first["forms"])
    proposed = {"kind": "quality_time", "tag": "File an original instruction"}
    with pytest.raises(WorkflowError):
        file(OTHER, first, proposed, "foreign-instruction")
    result = file(ADMIN, first, proposed, "original-instruction")
    assert file(ADMIN, first, proposed, "original-instruction") == result
    assert game.inspect(PLAYER, root)["state"] != "complete"
    file(
        PLAYER, card(PLAYER, "scene"), "We review the original hold.", "original-scene"
    )
    ledger.engine.dispose()
    second = card(OTHER, "attest")
    with pytest.raises(WorkflowError):
        file(ADMIN, second, True, "false-attendance")
    file(OTHER, second, True, "original-attendance")
    file(
        PLAYER,
        card(PLAYER, "execute"),
        "Relayed the filed instruction.",
        "original-execution",
    )
    assert game.inspect(PLAYER, root)["state"] == "complete"
    assert game.inspect(PLAYER, root)["receipt"]["faces"] == [6, 6]
    assert game.dice.calls == 1


def test_enforcement_handler_body_keeps_its_own_choice_and_original_receipt(
    ledger,
    tmp_path,
    monkeypatch,
):
    game, worker, gateway = enforcer_ready(ledger, tmp_path, monkeypatch)
    target = current_ref(state(game), ADMIN.user_id)
    cast_target(game, target)
    sheet = SpecialistScene(game, 900)
    card, form = popup(sheet, PLAYER, ENFORCEMENT)
    values = {
        "target": target.model_dump_json(),
        "heat": "0",
        "piloting": option((card, form), "piloting"),
        "context": "The pilot holds the original Handler.",
    }
    root = sheet.perform(
        PLAYER,
        "start-original-handler-body-play",
        card
        | {
            "answer": {"operation": ENFORCEMENT, "values": values},
        },
    )["action_id"]
    tick(worker, gateway, 3)
    for viewer in (OTHER, ADMIN, PLAYER):
        respond(
            scoped(game, viewer, "tag_window"),
            viewer,
            "tag_window",
            {"options": "pass"},
        )
    ledger.engine.dispose()
    fresh = GameService(ledger, dice=game.dice)
    scope = scoped(fresh, ADMIN, "enforcer_handler_consequence")
    assert scope[1]["root"] == root
    op = "enforcer_handler_consequence"
    with pytest.raises(WorkflowError):
        respond(scope, PLAYER, op, {"choice": "injury", "account": "Wrong owner."})
    with pytest.raises(ValueError, match="END THIS HANDLER"):
        respond(scope, ADMIN, op, {"choice": "death", "account": "Unconfirmed ending."})
    response = {"choice": "injury", "account": "I record the original injury."}
    result = respond(scope, ADMIN, op, response, key="actual-handler-body")
    assert respond(scope, ADMIN, op, response, key="actual-handler-body") == result
    original = fresh.inspect(PLAYER, root)
    assert original["state"] == "complete" and original["receipt"]["faces"] == [4, 5]
    assert game.dice.calls == 1


def test_projection_matches_owned_native_scene_controls_and_stops_when_a_play_is_pending(
    ledger,
):
    game, _, _ = ready(ledger)
    setup = SimpleNamespace(
        game=game,
        handler=ADMIN,
        play_registry=load_registry(),
        scene_plays=adapter(game),
        handler_rooms=lambda: {900: ("relay", "Relay operations")},
    )
    projection = ActivityNativePlays(setup, None)
    actor_id = str(PLAYER.user_id)
    with ledger.engine.connect() as c:
        scene = game.scene(c, 900)
        sheet = load_state(c, ledger.campaign_id).sheets[actor_id]
        actor = ActorRef(kind="pilot", entity=actor_id, incarnation=sheet.character_id)
        options = {option["id"]: option for option in projection(c, scene, actor)}
        assert options["keep_your_head"]["room"] == "relay"
        assert options["flirt"]["destination"] == "scene"
        assert "receive_orders" not in options
        assert "red_queen_memory" not in options
        stale = actor.model_copy(update={"incarnation": "old-sheet"})
        assert projection(c, scene, stale) == ()

    action = game.begin(
        PLAYER,
        "native-ai-play-owner",
        900,
        sheet.revision,
        PlayInput(
            play="keep_your_head",
            trigger_confirmed=True,
            heat=0,
            context="Hold the radio line.",
        ),
    )
    assert game.inspect(PLAYER, action["action_id"])["play"] == "keep_your_head"
    with ledger.engine.connect() as c:
        assert projection(c, game.scene(c, 900), actor) == ()


def test_handler_suggestion_exposes_the_actual_effect_without_applying_it(ledger):
    _, game = handler_ready(ledger)
    registry = load_registry()
    book = HandlerPlaybook(ledger, registry, OffDutyFollowups(game).periods)
    projection = ActivityNativePlays(
        SimpleNamespace(
            game=game,
            handler=ADMIN,
            play_registry=registry,
            handler_playbook=book,
            handler_rooms=lambda: {900: ("relay", "Relay operations")},
        ),
        None,
    )
    original = state(game)
    actor = active_handler(original)
    assert actor is not None
    with ledger.engine.connect() as c:
        view = {item["id"]: item for item in projection(c, game.scene(c, 900), actor)}
        assert set(view) == {
            "handler_brief",
            "handler_escalate",
            "handler_expectation",
            "handler_support",
            "handler_mess",
            "handler_punish",
        }
        assert view["handler_mess"]["control"] == "mess"
        assert view["handler_mess"]["room"] == "relay"
        assert (
            projection(
                c,
                game.scene(c, 900),
                actor.model_copy(update={"incarnation": "retired-handler"}),
            )
            == ()
        )
    assert state(game) == original

    target = current_ref(original, PLAYER.user_id)
    grant_payload = {
        "revision": original.revision,
        "targets": [target.model_dump(mode="json")],
        "room": "relay",
        "play": "mess",
    }
    with pytest.raises(WorkflowError):
        book.perform(
            PLAYER, "wrong-owner-before-start", "handler-play-start", grant_payload,
            scene_channel=900,
        )
    grant = book.perform(
        ADMIN, "handler-start-native", "handler-play-start", grant_payload,
        scene_channel=900,
    )
    ledger.engine.dispose()
    with ledger.engine.connect() as c:
        resumed = projection(c, game.scene(c, 900), actor)
        assert any(
            item["destination"] == "handler_effect"
            and item["control"] == grant["id"]
            and item["id"].startswith("handler_mess:")
            for item in resumed
        )
    reopened = HandlerPlaybook(ledger, registry, OffDutyFollowups(game).periods).view(
        ADMIN
    )
    task = next(item for item in reopened["tasks"] if item["id"] == grant["id"])
    assert any(
        play["id"] == "mess" and play["reason"] is None for play in task["plays"]
    )
    effect = {
        "id": task["id"],
        "revision": task["revision"],
        "play": "mess",
        "account": "The local synthetic Handler assigns a Tag.",
        "detail": "",
        "stakes": "",
        "fields": {"kind": "tag", "target": target.token, "tag": "Kept the Watch"},
    }
    with pytest.raises(WorkflowError):
        book.perform(PLAYER, "wrong-owner-before-effect", "handler-play-submit", effect)
    reply = book.perform(ADMIN, "handler-own-effect", "handler-play-submit", effect)
    assert (
        book.perform(ADMIN, "handler-own-effect", "handler-play-submit", effect)
        == reply
    )
    assert reply["state"] == "complete"
    assert [tag.label for tag in state(game).sheets[target.entity].tags].count(
        "Kept the Watch"
    ) == 1


def test_unsupported_batch_only_files_for_actual_facilitator_after_human_confirmation(
    ledger,
):
    game, _, _, dice = setup_game(ledger)
    ledger.clock = Clock()
    with ledger.engine.connect() as c:
        scene = game.scene(c, 900)["id"]
    base = local_fixture_director(game, activity_shadow=True)

    def post(request, _timeout):
        assert json.loads(request.data)["store"] is False
        return json.dumps(
            {
                "status": "completed",
                "output": [
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [
                            {
                                "type": "output_text",
                                "text": json.dumps(
                                    {
                                        "decision": {
                                            "kind": "NEEDS_REVIEW",
                                            "reason": "unsupported_outcome",
                                        }
                                    }
                                ),
                            }
                        ],
                    }
                ],
            }
        ).encode("utf-8")

    model = OpenAIResponses(
        model="local-parity",
        api_key="fixture",
        limits=ModelLimits(attempts=2, output_tokens=400),
        post=post,
    )
    app = P2Scene.model_fixture(base.session.context, model, batch=model)
    opt(app, scene)
    app.write(ADMIN, "referral-scene-policy", scene, "configure", {"revision": 0})
    for viewer in (ADMIN, PLAYER, OTHER):
        consent(app, scene, viewer)
    publish_opening(app, scene, ADMIN)
    referrals = FacilitatorService(game)
    referrals.configure(ADMIN, "referral-assignment", "user", OTHER.user_id)
    original = state(game)
    submission(
        app, scene, PLAYER, "referral-source", "Handler, a new effect needs review."
    )
    ledger.clock.now += 120
    batch = review(app, scene)
    assert batch["model_outcome"]["status"] == "escalated"
    assert not referrals.tasks(OTHER)
    with pytest.raises(WorkflowError):
        app.write(
            PLAYER,
            "wrong-referrer",
            scene,
            "activity-review-refer",
            {"run": batch["run"]},
        )
    with pytest.raises(WorkflowError, match="ACTIVITY_REFERRAL_STALE"):
        app.write(
            ADMIN,
            "invented-batch",
            scene,
            "activity-review-refer",
            {"run": "not-a-batch"},
        )
    data = {"run": batch["run"]}
    result = app.write(
        ADMIN, "file-actual-referral", scene, "activity-review-refer", data
    )
    ledger.engine.dispose()
    receipt = app.write(
        ADMIN, "file-actual-referral", scene, "activity-review-refer", data
    )
    assert receipt == result
    assert referrals.view(OTHER, result["id"])["request"]["rule"] == UNLISTED_ACTION
    assert [item["id"] for item in referrals.tasks(OTHER)] == [result["id"]]
    with pytest.raises(WorkflowError):
        referrals.view(PLAYER, result["id"])
    consent(app, scene, PLAYER, value=False)
    with pytest.raises(WorkflowError, match="OBSERVATION_DISABLED"):
        app.write(ADMIN, "revoked-referral", scene, "activity-review-refer", data)
    assert state(game) == original and dice.calls == 0


def test_dress_suggestion_and_native_performances_stay_with_original_owners(ledger):
    game, worker, gateway, registry = dogrunner_ready(ledger)
    book = HandlerPlaybook(ledger, registry, OffDutyFollowups(game).periods)
    projection = ActivityNativePlays(
        SimpleNamespace(
            game=game,
            handler=ADMIN,
            play_registry=registry,
            handler_playbook=book,
            handler_rooms=lambda: {900: ("relay", "Relay operations")},
        ),
        None,
    )
    original = state(game)
    with ledger.engine.connect() as c:
        options = {
            row["id"]: row
            for row in projection(c, game.scene(c, 900), active_handler(original))
        }
        assert options["handler_dress_them_down"]["room"] == "relay"
    girl, delegate = (
        current_ref(original, PLAYER.user_id),
        current_ref(original, OTHER.user_id),
    )
    grant = book.perform(
        ADMIN,
        "prepare-dress",
        "handler-play-start",
        {
            "revision": original.revision,
            "targets": [girl.model_dump(mode="json")],
            "play": "dress_them_down",
            "room": "relay",
        },
        scene_channel=900,
    )
    payload = {
        "id": grant["id"],
        "revision": grant["game_revision"],
        "play": "dress_them_down",
        "account": "Synthetic procedure",
        "detail": "Attend to the equipment.",
        "stakes": "",
        "fields": {
            "target": girl.token,
            "dress_steps": ["physical", "delegate", "demeaning"],
            "dress_contact": "grab",
            "dress_delegate": delegate.token,
            "tag": "Original Dog",
        },
    }
    assert (
        book.perform(ADMIN, "dress-plan", "handler-play-submit", payload)["phase"]
        == "delegate"
    )
    assert state(game).order == original.order

    def respond(viewer, phase, key, step, account, *, as_viewer=None):
        (card,) = book.dress_work(viewer)
        assert card["dress"]["phase"] == phase
        return book.perform_dress(
            as_viewer or viewer,
            key,
            {
                "id": card["id"],
                "revision": card["revision"],
                "action": card["action"],
                "answer": {"step": step, "account": account},
            },
        )

    assert not book.dress_work(PLAYER)
    with pytest.raises(WorkflowError):
        respond(
            OTHER,
            "delegate",
            "wrong-delegate",
            "competency",
            "Wrong owner.",
            as_viewer=PLAYER,
        )
    respond(OTHER, "delegate", "own-delegate", "competency", "I deliver my own step.")
    ledger.engine.dispose()
    respond(
        PLAYER, "contact", "own-contact", "performed", "The recorded contact occurred."
    )
    assert state(game).order == original.order
    assert respond(ADMIN, "ready", "own-finish", "finish", "")["state"] == "complete"
    assert not book.dress_work(ADMIN)
    assert [tag.label for tag in state(game).sheets[girl.entity].tags].count(
        "Original Dog"
    ) == 1
    tick(worker, gateway, 3)
    assert any(choice["kind"] == "order_response" for choice in game.choices(PLAYER))


def test_successor_advice_form_needs_real_acquisition_and_owned_scene(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway = ordinary_pr_award(ledger, tmp_path, monkeypatch)
    game.dice = Dice((4, 5))
    approved(ledger, game, tmp_path, monkeypatch, extra=(ORDINARY_RULE, SUCCESSOR_RULE))
    book = HandlerPlaybook(ledger, load_registry(), OffDutyFollowups(game).periods)
    settled = state(game)
    target = current_ref(settled, OTHER.user_id)
    start = {
        "targets": [target.model_dump(mode="json")],
        "play": "successor_advice",
        "room": "relay",
    }
    with pytest.raises(WorkflowError, match="Acquire the actual"):
        book.perform(
            ADMIN,
            "borrowed-advice",
            "handler-play-start",
            start | {"revision": settled.revision},
            scene_channel=900,
        )
    (award,) = awards(settled)
    SuccessorService(ledger).buy(
        ADMIN,
        "acquire-successor",
        award.id,
        settled.revision,
        "Train an actual Successor.",
    )
    grant = book.perform(
        ADMIN,
        "prepare-advice",
        "handler-play-start",
        start | {"revision": state(game).revision},
        scene_channel=900,
    )
    effect = {
        "id": grant["id"],
        "revision": grant["game_revision"],
        "play": "successor_advice",
        "account": "Let each crew confirm its own work.",
        "detail": "",
        "stakes": "",
        "fields": {},
    }
    assert (
        book.perform(ADMIN, "native-advice", "handler-play-submit", effect)["state"]
        == "complete"
    )
    ledger.engine.dispose()
    assert book.service.notice(OTHER, grant["id"])["account"] == effect["account"]
    with pytest.raises(WorkflowError):
        book.service.notice(PLAYER, grant["id"])
    assert not book.view(ADMIN)["successor"]["advice"]
    lesson = game.begin(
        OTHER,
        "later-lesson",
        900,
        state(game).sheets[target.entity].revision,
        PlayInput(
            play="keep_your_head",
            trigger_confirmed=True,
            heat=0,
            context="I use the advice to organize two teams.",
        ),
    )["action_id"]
    tick(worker, gateway, 4)
    pass_tags(game)
    answer(
        game,
        OTHER,
        "actor_keep",
        options=("tough", "in_control"),
        denied=("desperate",),
    )
    answer(
        game,
        ADMIN,
        "handler_keep",
        flag=True,
        text="The teams finished their preparations.",
    )
    tick(worker, gateway, 5)
    work = book.view(ADMIN)["successor"]
    assert work["advice"][0][0] == grant["id"]
    assert work["lessons"][grant["id"]][0][0] == lesson
    observation = {
        "operation": "award",
        "id": work["id"],
        "revision": work["revision"],
        "advice": grant["id"],
        "lesson": lesson,
        "account": "Each team confirmed its own work.",
    }
    with pytest.raises(WorkflowError):
        book.perform(
            OTHER, "cannot-award-own-star", "handler-play-successor", observation
        )
    result = book.perform(ADMIN, "star-once", "handler-play-successor", observation)
    assert (
        book.perform(ADMIN, "star-once", "handler-play-successor", observation)
        == result
    )
    current = book.view(ADMIN)["successor"]
    assert current["stars"] == ((result["id"], target.entity),)
    removal = {
        "operation": "remove",
        "id": current["id"],
        "revision": current["revision"],
        "star": result["id"],
    }
    with pytest.raises(WorkflowError):
        book.perform(OTHER, "cannot-remove-star", "handler-play-successor", removal)
    removed = book.perform(ADMIN, "remove-star-once", "handler-play-successor", removal)
    assert (
        book.perform(ADMIN, "remove-star-once", "handler-play-successor", removal)
        == removed
    )
    assert not book.view(ADMIN)["successor"]["stars"]
