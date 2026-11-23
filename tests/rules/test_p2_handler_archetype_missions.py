"""A matched offline relay mission with each original Handler playbook and its real rules."""

import json

import pytest
from test_director_continuity import roles
from test_director_handler_character import approve, propose
from test_director_handler_play_examples import open_offer
from test_director_observation import send
from test_gm_outcome_consumers import attach, consume
from test_handler_creation import agree, complete, ready, save
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Gateway, answer, pass_tags, state, tick
from test_off_duty_cycle import activate, call, prepared
from test_p2_mission_cycle import keep, launch
from test_punishment_service import submit
from test_world import initial

from girlframe.ai.conversation import ConversationReply
from girlframe.ai.gm_outcomes import HandlerOutcome
from girlframe.delivery.m2_worker import GameWorker
from girlframe.engine.m2 import PlayInput
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_frantic_breakdown import records as breakdowns
from girlframe.engine.m3_handler_character import PROFILES
from girlframe.engine.m3_handler_play_state import BASIC, Effect
from girlframe.engine.m3_punishments import Details
from girlframe.engine.m3_scientist_lab import LabAnswer, LabProposal, steps
from girlframe.services.director_conversation import DirectorConversationService
from girlframe.services.director_session import DirectorSessionService
from girlframe.services.m3_advocate_alone import AdvocateAloneService
from girlframe.services.m3_advocate_empathy import CHOICE as ADVOCATE_REWARD
from girlframe.services.m3_frantic_breakdown import FranticBreakdownService
from girlframe.services.m3_handler_creation import HandlerCreationService
from girlframe.services.m3_handler_plays import HandlerPlayService
from girlframe.services.m3_insurgent_loyalty import WATCH, labels
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_mistress_rewards import OFFER, REPLY
from girlframe.services.m3_punishments import PunishmentService
from girlframe.services.m3_trainer_phrases import HEAR, SPEAK
from girlframe.services.onboarding import WorkflowError

CUES = (
    ("cooperation", "I stayed to finish Kite's half of the check after I finished mine."),
    ("accountability", "I copied the wrong total onto the dispatch sheet."),
    ("research", "The second instrument reproduced the first reading under the same conditions."),
    ("capacity", "We have one technician and two consoles due for release."),
    ("institution", "The Director asked us to name whoever questioned the inspection order."),
    ("procedure", "The reset checklist puts the isolator after the switch."),
    ("agency", "The supervisor answered the question about my route for me."),
    ("personal", "The training alarm has stopped, but I can still hear it in my head."),
)
BRIEF = "Stay on the marked approach and keep the inspection to relay calibration."
REPLIES = {
    "cooperation": "You stayed for both lists. Bring yours here so I can sign it myself.",
    "accountability": "Whose initials are on that total? Bring me the original sheet.",
    "research": "Good. Leave both instruments in place. Record the conditions beside the reading.",
    "capacity": "One tech. Two releases. Hold the second console. I'll ask for a new slot.",
    "institution": "Readings and time on this channel. Keep the Pilots' names at your desk.",
    "procedure": "Read me the isolator step first. We will run the sequence from there.",
    "agency": "You had the floor. If you still want to answer, tell me which route you chose.",
}
PERSONAL = {
    "Mistress": "You can stay by my desk a while. I'll keep the door open.",
    "Frantic": "Right. Alarm's done. I'll hold the line. Take off your headset if you want.",
    "Advocate": "Do you want a minute off comms? I'll stay if you'd rather talk.",
}
EXPECTED_CUES = {
    "Mistress": ("cooperation", "personal"),
    "Dogrunner": ("accountability",),
    "Scientist": ("research",),
    "Frantic": ("capacity", "personal"),
    "Insurgent": ("institution",),
    "Trainer": ("procedure",),
    "Advocate": ("agency", "personal"),
}


class MissionVoice:
    def __init__(self):
        self.requests = []

    def respond(self, request):
        self.requests.append(request)
        decision = request.response_need
        assert decision and decision.cue and request.playbook_profile
        text = (
            PERSONAL[request.playbook_profile.playbook]
            if decision.cue == "personal"
            else REPLIES[decision.cue]
        )
        return ConversationReply(
            route="handler",
            provider="reviewed-handler-v1",
            disposition="answer" if decision.source_refs else "clarification",
            text=text,
            source_refs=decision.source_refs,
        )


def run_mission(store, game, playbook):
    approval, rulings = store.policy.m3_approval, store.policy.owner_m3_rulings
    store.policy = store.policy.model_copy(
        update=dict(
            m3_approval=approval.model_copy(
                update=dict(subsystems=approval.subsystems | {"plays", "playbooks", "world"})
            ),
            owner_m3_rulings=rulings.model_copy(
                update=dict(handler_creation="owned_shared_choices_preserve_existing")
            ),
        )
    )
    creation = HandlerCreationService(store)
    draft = complete(creation, playbook)
    if playbook == "Trainer":
        ace, dog = draft.starting
        draft = draft.model_copy(update=dict(starting=(ace, dog.model_copy(update=dict(prompt=2)))))
    save(creation, draft)
    agree(creation)
    menu = creation.view(ADMIN)
    creation.activate(ADMIN, "mission-handler", menu["revision"], menu["game_revision"], True)
    native = HandlerPlayService(store)
    assert tuple(native.options(ADMIN)["plays"]) == BASIC
    missions = MissionService(store)
    mission = launch(missions, "archetype-mission", "Inspect and recalibrate the relay.")
    outcomes, scene = attach(game)
    observer = outcomes.context.observations
    performer = MissionVoice()
    talk = DirectorConversationService(outcomes.context, handler=performer, handler_mode="reviewed")
    _, pilot = roles(observer, scene)
    transcript = []

    def quiet(key, text):
        _, source = send(observer, scene, key, text=text, fictional_channel="comms")
        routed = talk.process_message(PLAYER, key + ":route", scene, source.source_id, 1)
        assert routed["handler_decision"]["decision"]["action"] == "WAIT"
        assert routed["handler"] is None
        transcript.append(dict(cue="routine", pilot=text, decision="WAIT", reply=None))

    quiet("routine:before", "The relay log is open at today's entry.")
    _, private = send(
        observer,
        scene,
        "private",
        text="PRIVATE_UNREPORTED_SECOND_ACCESS",
        fictional_channel="private",
    )
    assert (
        talk.process_message(PLAYER, "private:route", scene, private.source_id, 1)["handler"]
        is None
    )
    for index, (cue, text) in enumerate(CUES):
        key = f"beat:{index}"
        _, source = send(observer, scene, key, text=text, fictional_channel="comms")
        fields = dict(kind="character_cue", cue=cue, speech_quote=text, action="RESPOND")
        eligible = cue in EXPECTED_CUES[playbook]
        if eligible:
            early = talk.process_message(PLAYER, key + ":before-review", scene, source.source_id, 1)
            assert early["handler_decision"]["decision"]["action"] == "WAIT"
            assert early["handler"] is None
            propose(talk, scene, source, key, **fields)
        else:
            with pytest.raises(WorkflowError, match="HANDLER_PLAYBOOK_CUE"):
                propose(talk, scene, source, key, **fields)
        routed = talk.process_message(PLAYER, key + ":route", scene, source.source_id, 1)
        reply = None
        if eligible:
            decision = routed["handler_decision"]["decision"]
            assert (
                decision["action"] == "RESPOND" and decision["reason"] == "reviewed_character_cue"
            )
            request = performer.requests[-1]
            assert request.playbook_profile == PROFILES[playbook]
            assert request.playbook_profile.cues == EXPECTED_CUES[playbook]
            assert "PRIVATE_UNREPORTED_SECOND_ACCESS" not in request.model_dump_json()
            draft_id = routed["handler"]["id"]
            approve(talk, scene, draft_id, pilot)
            reply = talk.delivery.preview(ADMIN, scene, draft_id)["text"]
            talk.delivery.deliver(ADMIN, key + ":deliver", scene, draft_id)
        else:
            assert routed["handler_decision"]["decision"]["action"] == "WAIT"
            assert routed["handler"] is None
        transcript.append(
            dict(cue=cue, pilot=text, decision="RESPOND" if eligible else "WAIT", reply=reply)
        )
    quiet("routine:after", "I put the pencil back by the log.")
    assert (
        len(performer.requests)
        == len(talk.delivery.contributions(PLAYER, scene))
        == len(EXPECTED_CUES[playbook])
    )
    assert not talk.delivery.contributions(OTHER, scene)

    grant = open_offer(outcomes, scene, game, "brief", BRIEF)
    assert dict(native.get(ADMIN, grant)["plays"]) == {"brief": dict(BASIC)["brief"]}
    briefing = consume(
        outcomes,
        scene,
        "handler_grant",
        grant,
        HandlerOutcome(play="brief", effect=Effect(kind="brief", account=BRIEF)),
    )
    assert briefing["state"] == "complete" and native.notice(PLAYER, grant)["account"] == BRIEF
    session = DirectorSessionService(outcomes.context)
    action, _ = keep(session, game, scene, 900, "relay-calibration")
    assert game.inspect(PLAYER, action)["receipt"]["faces"] == [4, 5]
    return (
        dict(
            transcript=transcript,
            shared_play="brief",
            pilot_play="keep_your_head",
            shared_play_options=[identity for identity, _ in BASIC],
        ),
        mission,
        outcomes,
        scene,
    )


def signature(game, playbook, outcomes, scene):
    store = game.store
    worker, gateway = GameWorker(game), Gateway()
    if playbook == "Mistress":
        order = game.issue_order(ADMIN, "cooperation-order", 900, 3, "Finish the relay log.")
        tick(worker, gateway, 3)
        answer(game, OTHER, "order_response", options=("immediate",))
        answer(game, ADMIN, OFFER, options=("raise_status",))
        answer(game, OTHER, REPLY, flag=True)
        assert (
            state(game).order[0] == 3
            and game.inspect(OTHER, order["action_id"])["state"] == "complete"
        )
        tick(worker, gateway, 5)
        return (
            "Catch More Flies With Honey",
            "Kite accepted the offered Status increase and became Ace.",
        )
    if playbook == "Dogrunner":
        native = HandlerPlayService(store)
        assert native.options(ADMIN)["dress_them_down"]
        target = current_ref(state(game), 2)
        root = native.start(
            ADMIN, "dress-source", state(game).revision, (target,), dress_scene=900
        )["id"]
        grant = open_offer(
            outcomes,
            scene,
            game,
            "dress_them_down",
            "I address the signed report.",
            native_grant=root,
        )
        result = consume(
            outcomes,
            scene,
            "handler_grant",
            grant,
            HandlerOutcome(
                play="dress_them_down",
                effect=Effect(
                    kind="dress_them_down",
                    target=target,
                    account="I call the miscalculation incompetent.",
                    dress_steps=("competency",),
                    tag="Can't Trust The Totals",
                ),
            ),
        )
        assert result["state"] == "complete" and state(game).order[-1] == 2
        assert any(x.label == "Can't Trust The Totals" for x in state(game).sheets["2"].tags)
        return "Dress Them Down", "Lark lost Status and received the Tag for becoming the Dog."
    if playbook == "Frantic":
        service = FranticBreakdownService(store, game)
        game.dice.faces = (3, 3)
        result = service.start(
            ADMIN,
            "the-breakdown",
            state(game).revision,
            900,
            "Two consoles, one technician. The Frantic leaves the desk.",
        )
        identity = result["id"]
        assert result["total"] == 9
        service.select(
            ADMIN,
            "the-breakdown-choice",
            identity,
            state(game).revision,
            ("office", "minor_all"),
            office=current_ref(state(game), 3),
        )
        service.discover(
            OTHER,
            "the-office-discovery",
            identity,
            state(game).revision,
            "I find the Handler by her office console.",
        )
        (record,) = breakdowns(state(game))
        assert record.choices[0].discovered_event and len(record.choices[1].debts) == 2
        assert service.get(ADMIN, identity)["phase"] == "effects"
        return (
            "Break Down",
            "Saved 9 with three bases. Kite confirmed the office discovery. Two debts were queued.",
        )
    if playbook == "Insurgent":
        order = game.issue_order(ADMIN, "loyalty-order", 900, 2, "Give the Director a name.")
        game.dice.faces = (4, 5)
        tick(worker, gateway, 4)
        answer(game, PLAYER, "order_response", options=("disobey",))
        action = game.begin(
            PLAYER,
            "owned-refusal",
            900,
            state(game).sheets["2"].revision,
            PlayInput(
                play="disobey_orders",
                order_id=order["order_id"],
                parent=order["action_id"],
                context="I refuse to name someone without evidence.",
                trigger_confirmed=True,
                heat=0,
                witnessed=False,
            ),
        )["action_id"]
        tick(worker, gateway, 4)
        pass_tags(game)
        answer(game, PLAYER, "actor_disobey", options=("tag_heat",), number=1, text="Defiant")
        answer(game, ADMIN, "handler_disobey", flag=True)
        answer(
            game,
            ADMIN,
            WATCH,
            flag=True,
            text="I witnessed the actual refusal to identify a Pilot.",
        )
        watched = state(game)
        (record,) = labels(watched, current_ref(watched, 2))
        assert record.action == action and record.status == "surveilled"
        tag = next(x for x in watched.sheets["2"].tags if x.id == record.tag)
        assert tag.label == "Surveilled" and set(tag.observers) == {1, 2}
        tick(worker, gateway, 5)
        return (
            "Rebel Sympathizers",
            "The original witnessed refusal created a private Surveilled Tag.",
        )
    if playbook == "Trainer":
        order = game.issue_order(
            ADMIN, "speak-phrase", 900, 3, "Name the skipped step.", conditioning_phrase="speak"
        )
        tick(worker, gateway, 3)
        answer(game, OTHER, "order_response", options=("obedient",))
        answer(game, OTHER, SPEAK, text="The isolator is the skipped step.")
        answer(game, ADMIN, HEAR, flag=True)
        assert game.inspect(OTHER, order["action_id"])["state"] == "complete"
        tick(worker, gateway, 5)
        return (
            "Conditioning Phrase: Speak",
            "Kite supplied her own answer to Speak. The Trainer confirmed hearing it.",
        )
    assert playbook == "Advocate"
    service = AdvocateAloneService(store, game)
    game.leave_scene(OTHER, "open-one-on-one", 900)
    original = service.ask(
        ADMIN,
        "advocate-question",
        state(game).revision,
        900,
        "What did you want to tell the supervisor?",
        "silence",
    )["id"]
    service.answer(
        PLAYER,
        "advocate-answer",
        original,
        state(game).revision,
        "I wanted to choose my own route.",
    )
    order = service.issue(
        ADMIN,
        "advocate-private-order",
        original,
        state(game).revision,
        "",
        "Someone Asked Me First",
    )
    tag = next(x for x in state(game).sheets["2"].tags if x.label == "Someone Asked Me First")
    assert set(tag.observers) == {1, 2}
    tick(worker, gateway, 3)
    assert not any(x["kind"] == "order_response" for x in game.choices(OTHER))
    answer(game, PLAYER, "order_response", options=("obedient",))
    answer(game, ADMIN, ADVOCATE_REWARD, options=("pass",))
    assert game.inspect(PLAYER, order["action_id"])["state"] == "complete"
    tick(worker, gateway, 5)
    return (
        "Get Them Alone",
        "Lark gave her own answer and received the private Tag and a private native Order.",
    )


def end_mission(game, mission):
    missions = MissionService(game.store)
    ended = missions.end(
        ADMIN,
        "mission-end",
        mission["id"],
        mission["revision"],
        True,
        debrief="The original Pilot returned the calibrated relay to service.",
    )
    assert ended["rewards_committed"]
    pending = missions.get(ADMIN, mission["id"])["work"]
    for work in pending:
        assert work["kind"] == "punishment"
        submit(
            PunishmentService(game.store),
            ADMIN,
            work["id"],
            Details(kind="stimulant_injection"),
            key="mission-discipline:" + work["id"],
        )
    assert (
        missions.complete(ADMIN, "mission-complete", mission["id"], ended["revision"])["phase"]
        == "complete"
    )


@pytest.mark.parametrize("playbook", tuple(PROFILES))
def test_p2_matched_mission_gives_each_handler_an_owned_signature_play(ledger, playbook):
    if playbook == "Scientist":
        from girlframe.services.activity_handler_signatures import native_signature

        trace = {}
        original_scene = None

        def on_mission(game):
            nonlocal original_scene
            results, mission, _, original_scene = run_mission(ledger, game, playbook)
            trace.update(results)
            end_mission(game, mission)

        cycle, game, period = prepared(ledger, before_period=on_mission)
        with ledger.transaction() as connection:
            lab_state = state(game)
            equipment = next(x for x in lab_state.sheets["3"].assets if x.family == "girl")
            equipment.void = True
            game.event(
                connection, 1, "lab-patient-fixture", "synthetic.existing_void_asset", lab_state
            )
        activate(cycle, game, period)
        assert cycle.review(ADMIN, period)["scientist_lab_available"]
        with ledger.engine.connect() as c:
            campaign = state(game)
            native = game.scene(c, channel=900)
            assert native["id"] == original_scene
            (open_lab,) = native_signature(
                game, c, native, current_ref(campaign, ADMIN.user_id),
                current_ref(campaign, OTHER.user_id),
            )
        assert open_lab.play == "head_to_the_lab"
        assert open_lab.control == period and open_lab.destination == "off_duty_signature"
        call(
            cycle,
            game,
            ADMIN,
            period,
            "handler_scene",
            "scientist_lab",
            (1, 3),
            "I use the replicated readings to calibrate an experimental relay implant.",
            None,
            None,
            None,
            LabProposal(name="Relay implant", description="A calibrated synthetic fixture."),
        )
        call(cycle, game, OTHER, period, "acknowledge", None, LabAnswer(remove_void=equipment.id))
        call(cycle, game, ADMIN, period, "acknowledge", None)
        (step,) = steps(state(game), current_ref(state(game), 1))
        assert step.target == current_ref(state(game), 3)
        assets = {x.id: x for x in state(game).sheets["3"].assets}
        assert assets[step.installed].void and not assets[equipment.id].void
        name, effect = (
            "Head to the Lab",
            "Both owners attested. The lab installed a Void Asset and recorded the Project step.",
        )
    else:
        _, game = ready(ledger)
        with ledger.transaction() as connection:
            campaign = state(game)
            campaign.world = initial().model_copy(update=dict(npcs=campaign.world.npcs))
            game.event(connection, 1, "mission-world-fixture", "synthetic.mission_world", campaign)
        trace, mission, outcomes, scene = run_mission(ledger, game, playbook)
        name, effect = signature(game, playbook, outcomes, scene)
        end_mission(game, mission)
    trace.update(playbook=playbook, signature=name, canonical_effect=effect, mission="complete")
    print("ARCHETYPE_MISSION " + json.dumps(trace, ensure_ascii=False))
