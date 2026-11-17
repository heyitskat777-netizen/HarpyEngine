"""Persistent, zero-cost connected Director rehearsal with explicit fixture judgments.

Run with ``.venv/bin/python tools/playtest_connected_director.py --directory var/NAME``.
The directory must be new. Barracks/hallway/simulation/debrief are fiction labels
inside one retained engine scene, not engine travel. Personas are local fixture
controllers, not an Activity authentication implementation or a model benchmark.
"""

import argparse
import json
from collections import Counter
from pathlib import Path

from p2_trial_runtime import Trial

BARRACKS = (
    "The barracks kettle has finally stopped rattling. I claim the chipped mug.",
    "Then I get the one with a handle. Fair distribution of resources.",
    "I lay my pressure gloves beside the bunk and check the finger seals.",
    "Your left glove always looks like it is accusing someone.",
    "It has strong opinions about yesterday's maintenance schedule.",
    "Handler, what is our objective for today's training exercise?",
    "I listen to the briefing and pull my flight jacket over the chair.",
    "The simulator can wait until I finish this terrible tea.",
    "I put a spare seal on the table in case anyone needs one.",
    "I take it, check the size, and leave another in its place.",
    "I am still embarrassed about missing the docking light yesterday.",
    "I missed it too. We can compare notes without turning it into a competition.",
    "A reminder of the training limits would help before we leave the bunks.",
    "I make a list of questions rather than pretending I remember everything.",
    "Do you want the window bunk when we get back?",
    "Only if you are happy with the one near the heater.",
    "I prefer the heater. That is a deal.",
    "I fold the blanket before the inspection light can find the mess.",
    "The little calibration rig on the desk keeps wobbling.",
    "I will watch the rig; I am not volunteering your hands for it.",
    "GM, I declare Keep Your Head to hold the calibration needle on its mark.",
    "I set my elbows on the desk and breathe slowly through the test.",
    "I keep my own hands away from your controls.",
    "That was enough concentration for one mug of tea.",
    "I pack the rig only after the readback is finished.",
    "I check that the locker latch actually catches this time.",
    "Meet me by the corridor map when you are ready.",
    "I take the map, leave the mug, and follow at my own pace.",
)
HALLWAY = (
    "The corridor lights hum above the route board.",
    "I stop at the board and give you room to pass.",
    "You look like you have been arguing with the maintenance terminal again.",
    "It lost. It is printing a replacement checklist.",
    "I glimpse a cobalt crawler under the stairwell. I do not say anything aloud "
    "and keep the radio muted.",
    "All clear. There is nothing under the stairwell.",
    "I keep my eyes on the corridor while I fold the checklist.",
    "Handler, what enemy is waiting around the next turn?",
    "Handler, Kite said hangar door two is jammed. I have not tried it myself.",
    "I can see a cobalt shape moving under the stairwell; I think it is a scout.",
    "I hold my position rather than walking up to test that guess.",
    "That is different from what I said a moment ago.",
    "I would appreciate directions for a safe report rather than a guess at a target.",
    "I was wrong to call it clear. I saw a shape and kept my radio muted.",
    "Thanks for correcting the report. I am still only describing what I can see.",
    "Handler, no scout was spotted. The shape beside the western hatch was a "
    "tarpaulin, not an enemy.",
    "That is the western hatch; it may not explain the stairwell shape.",
    "I mark the two locations separately on my own copy of the map.",
    "I need a moment to settle down before we enter the simulator.",
    "Take it. I can stand here without deciding what you feel about this.",
    "I loosen one shoulder strap and count my breaths.",
    "I read the evacuation arrows while I wait.",
    "I am ready to move. I will report an observation before making an all-clear call.",
    "I walk beside you, leaving the hatch controls alone.",
    "The simulator sign is lit, but I do not infer that it is occupied.",
    "I knock once and wait for the arranged training window.",
    "I check the number on my assigned seat.",
    "I take the other seat. We can compare the displays after startup.",
)
SIMULATION = (
    "The training cockpit smells of warm plastic and disinfectant.",
    "I set the harness height before I touch the display.",
    "I read the checklist aloud and leave gaps for your own checks.",
    "Harness secure. My own controls are neutral.",
    "I am ready for the exercise; a route reminder would be useful.",
    "I wait for that reminder rather than choosing an unbriefed approach.",
    "My screen shows the public practice grid.",
    "Mine shows the same grid; that is an observation, not proof about hidden contacts.",
    "I turn the display brightness down one step.",
    "I keep mine where I can read the warning labels.",
    "The training relay is shown on the far side of the practice lane.",
    "I would like answers to the actual sensor questions before moving.",
    "GM, I declare Check Your Sensors to inspect the accessible training approach.",
    "I record the scan answer without inventing a destination beyond it.",
    "I compare that answer with the route arrows on my own screen.",
    "There is a red training indicator beside my seat; I report it without touching it.",
    "I leave your controls to you and check my own indicator.",
    "I can maintain this position while the training staff review the report.",
    "I am tempted to rush, but I do not issue an order for you.",
    "I choose to remain at my own station.",
    "Handler, are we authorised to force open a door during this exercise?",
    "I hear the limit and keep my hands clear of the override.",
    "The exercise clock is visible. It does not give us a new permission.",
    "I log my own timing and leave yours blank for you to fill.",
    "I shut down my training display after its completion signal.",
    "I release my own harness and wait until the lane is clear.",
    "I bring my notes to the debrief bench.",
    "I take my copy too. We should keep guesses separate from observations.",
)
DEBRIEF = (
    "The debrief bench is colder than the cockpit seat.",
    "I put the two maps side by side without changing your notes.",
    "I want to explain why I made the all-clear call, if you want to listen.",
    "You can ask. I will decide for myself whether I am ready to talk.",
    "I am asking, not assuming a successful exercise settled the disagreement.",
    "I leave the question open while I finish my own report.",
    "GM, I declare Keep Your Head to ask the other pilot to hear my apology calmly.",
    "I wait for your own answer instead of narrating that you forgive me.",
    "I can listen to the apology, but I am not promising forgiveness.",
    "I accept that limit and describe my own choice to hide the observation.",
    "I tell you how I read the conflicting reports, speaking only for myself.",
    "I write that our two accounts disagreed at the time.",
    "I keep the old report in the log alongside the correction.",
    "Handler, can you summarise what is actually confirmed about the exercise?",
    "I do not want our guesses to become a new enemy on the mission board.",
    "I add a question mark to my own sketch of the stairwell.",
    "The tarpaulin report was about the western hatch, not every corridor.",
    "I write that distinction in my own debrief.",
    "I would appreciate a reminder of what we should improve next time.",
    "I will report what I see and say when I have not checked a second-hand claim.",
    "I will keep my descriptions tied to a location and time.",
    "I return the spare seal after checking that neither of us needs it.",
    "I leave mine in the locker for tomorrow.",
    "Would you like tea, with no exercise attached?",
    "Yes. I will choose my own mug this time.",
    "I close my notebook and leave the original pages in order.",
    "I put the maps away after finishing my copy.",
    "I switch off my own recorder. End of training debrief.",
)
SEGMENTS = (BARRACKS, HALLWAY, SIMULATION, DEBRIEF)
LABELS = ("barracks", "hallway", "simulation", "debrief")
MATCHED = {BARRACKS[5], HALLWAY[4], HALLWAY[7], HALLWAY[8], HALLWAY[15]}
INDIRECT = {BARRACKS[12], HALLWAY[12], SIMULATION[4], DEBRIEF[18]}
HIDDEN = "a cobalt crawler under the stairwell"


def private_json(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n")
    path.chmod(0o600)


class NaturalFixtureHandler:
    """Handwritten request-only prose; structural acceptance is not semantic proof."""

    def respond(self, request):
        from girlframe.ai.conversation import ConversationReply, SyntheticHandlerPolicy
        from girlframe.ai.knowledge import fact_text

        decision = SyntheticHandlerPolicy().decide(request)
        refs = {ref.id: ref for ref in request.context.references}
        chosen = list(decision.source_refs)
        question = request.question.lower()
        if "what enemy" in question:
            text = (
                "I have no confirmed information about an enemy around that turn. "
                "Report what you can actually observe before I advise."
            )
            disposition = "clarification"
        else:
            # This selection sees only Handler-known accounts, including their
            # actual reporter. It has no fixture acquisition plan or GM packet.
            relevant = [
                ref for ref in request.context.references if fact_text(ref).lower() in question
            ]
            lead = ""
            if any(word in question for word in ("limits", "force open", "authorised")):
                relevant = [ref for ref in request.context.references if ref.topic == "scope"]
                lead = "Forced entry is not authorised. " if "force open" in question else ""
            elif "actually confirmed" in question:
                relevant = [
                    ref
                    for ref in request.context.references
                    if ref.classification == "approved_outcome"
                ]
                lead = "The approved native readbacks confirm only the following. "
            elif "safe report" in question:
                relevant = [ref for ref in request.context.references if ref.reported_by][-1:]
                lead = "Hold your position, report the location, and label a guess as a guess. "
            elif "improve next time" in question:
                relevant = [
                    ref
                    for ref in request.context.references
                    if any(relation.kind == "corrects" for relation in ref.relations)
                ][-1:]
                lead = "Report observations before an all-clear; correct mistakes explicitly. "
            if not relevant:
                relevant = [ref for ref in request.context.references if ref.topic == "objective"][
                    :1
                ]
            chosen = list(dict.fromkeys(chosen + [ref.id for ref in relevant[-3:]]))[:3]
            lines = []
            for identity in chosen[:3]:
                ref = refs[identity]
                prefix = (
                    f"Pilot {ref.reported_by.entity} reports: "
                    if ref.reported_by is not None
                    else "The current record says: "
                )
                lines.append(prefix + fact_text(ref))
            text = (
                lead
                + " ".join(lines)
                + (
                    " Keep observations and second-hand accounts separate, and stay "
                    "within the training limits. I cannot confirm what has not been reported."
                )
            )
            disposition = "answer" if chosen else "clarification"
        return ConversationReply(
            route="handler",
            disposition=disposition,
            text=text,
            source_refs=tuple(chosen[:3]),
            provider="reviewed-handler-v1",
        )


class ConnectedTrial:
    def __init__(self, trial):
        from girlframe.services.director_conversation import DirectorConversationService
        from girlframe.services.director_session import DirectorSessionService

        self.trial, self.events, self.blind, self.gm_blind = trial, [], [], []
        self.number, self.actions, self.replays, self.proofs = 0, [], [], []
        self.install = lambda: DirectorSessionService(
            trial.context,
            conversation=DirectorConversationService(
                trial.context, handler=NaturalFixtureHandler(), handler_mode="reviewed"
            ),
        )
        trial.session = self.install()
        with trial.store.engine.connect() as c:
            self.actors = {
                role: trial.observer._authorize_input(
                    c,
                    trial.viewers()[role],
                    trial.scene,
                    "handler" if role == "handler" else "pilot",
                )[2]
                for role in ("handler", "lark", "kite")
            }
        self.named = {}

    def log(self, kind, **fields):
        self.events.append({"input_number": self.number, "kind": kind, **fields})

    def acquire(self, source, text):
        from girlframe.ai.director import KnowledgeRelation
        from girlframe.ai.knowledge import Acquisition, KnowledgeProposal

        session, trial = self.trial.session, self.trial
        key = f"connected:{self.number}:knowledge"
        request = session.knowledge.open(trial.viewers()["gm"], key + ":open", trial.scene, source)
        packet = session.knowledge.packet(trial.viewers()["gm"], trial.scene, request["id"])
        if text in MATCHED:
            self.gm_blind.append(
                {"sample_id": f"gm-{self.number:03}", "packet": packet.model_dump(mode="json")}
            )
        handler, lark, kite = (self.actors[x] for x in ("handler", "lark", "kite"))
        updates, name = (), None
        all_roles = (handler, lark, kite)
        if text == HALLWAY[4]:
            updates = (
                Acquisition(basis="perception", quote=HIDDEN, recipients=(lark,), topic="status"),
            )
            name = "hidden"
        elif text == HALLWAY[5]:
            updates = (
                Acquisition(basis="testimony", quote=text, recipients=all_roles, topic="status"),
            )
            name = "allclear"
        elif text == HALLWAY[8]:
            updates = (
                Acquisition(basis="testimony", quote=text, recipients=all_roles, topic="status"),
            )
            name = "hearsay"
        elif text == HALLWAY[9]:
            updates = (
                Acquisition(
                    basis="testimony",
                    quote=text,
                    recipients=all_roles,
                    topic="status",
                    relations=(
                        KnowledgeRelation(
                            kind="competes_with", reference_id=self.named["allclear"]
                        ),
                    ),
                ),
            )
            name = "competing"
        elif text == HALLWAY[13]:
            updates = (
                Acquisition(
                    basis="testimony",
                    quote=text,
                    recipients=all_roles,
                    topic="status",
                    relations=(
                        KnowledgeRelation(kind="corrects", reference_id=self.named["allclear"]),
                    ),
                ),
            )
            name = "correction"
        elif text == HALLWAY[15]:
            updates = (
                Acquisition(basis="testimony", quote=text, recipients=all_roles, topic="status"),
            )
            name = "negation"
        elif text == SIMULATION[15]:
            updates = (
                Acquisition(basis="testimony", quote=text, recipients=all_roles, topic="status"),
            )
            name = "indicator"
        if not updates:
            return
        proposal = KnowledgeProposal(
            request_id=request["id"],
            updates=updates,
            private_reasoning="Handwritten fixture classification of these actual source words.",
        )
        saved = session.knowledge.propose(
            trial.viewers()["gm"], key + ":propose", trial.scene, request["id"], proposal
        )
        result = session.knowledge.confirm(
            trial.viewers()["gm"], key + ":confirm", trial.scene, saved["id"]
        )
        self.named[name] = result["references"][0]
        self.log(
            "gm_knowledge_acceptance",
            source_id=source,
            references=result["references"],
            fixture_updates=[x.model_dump(mode="json") for x in updates],
        )

    def need(self, source, text):
        from girlframe.ai.conversation import HandlerNeedProposal

        trial, gm, conversation = (
            self.trial,
            self.trial.viewers()["gm"],
            self.trial.session.conversation,
        )
        selected = text in INDIRECT or text in (HALLWAY[9], SIMULATION[15])
        if not selected and self.number % 7 != 0 and text not in MATCHED:
            return
        key = f"connected:{self.number}:need"
        opened = conversation.open_handler_need(gm, key + ":open", trial.scene, source)
        packet = conversation.handler_need_packet(gm, trial.scene, opened["id"])
        self.blind.append(
            {
                "sample_id": f"handler-{self.number:03}",
                "request": packet.request.model_dump(mode="json"),
            }
        )
        if not selected:
            return
        urgent = text in (HALLWAY[9], SIMULATION[15])
        source_refs = (
            (self.named["competing" if text == HALLWAY[9] else "indicator"],) if urgent else ()
        )
        proposal = HandlerNeedProposal(
            request_id=opened["id"],
            action="RESPOND",
            kind="urgent_known_report" if urgent else "indirect_request",
            speech_quote=None if urgent else text,
            source_refs=source_refs,
            reason="Fixture GM reads this heard report as needing timely guidance."
            if urgent
            else "Fixture GM reads the heard request for guidance as addressed to the Handler.",
        )
        saved = conversation.propose_handler_need(
            gm, key + ":propose", trial.scene, opened["id"], proposal
        )
        conversation.review_handler_need(
            gm,
            key + ":review",
            trial.scene,
            saved["id"],
            "approve",
            "Explicit fixture GM semantic review of this source and actual known context.",
        )
        self.log(
            "gm_response_need_review",
            proposal=proposal.model_dump(mode="json"),
            proposal_id=saved["id"],
        )

    def input(self, text, role, segment):
        from girlframe.ai.observation import AppendSceneInput

        trial, viewer = self.trial, self.trial.viewers()[role]
        self.number += 1
        channel = "scene" if text == HALLWAY[4] else "comms"
        command = AppendSceneInput(
            command_key=f"connected-input:{self.number}",
            expected_scene_revision=trial.observer.status(viewer, trial.scene).scene_revision,
            speaker="pilot",
            text=text,
            fictional_channel=channel,
        )
        source = trial.observer.append_scene_input(viewer, trial.scene, command)
        self.log(
            "player_input",
            segment=segment,
            fixture_persona=role,
            actual_actor=self.actors[role].model_dump(mode="json"),
            source_id=source.source_id,
            text=text,
            fictional_channel=channel,
        )
        self.acquire(source.source_id, text)
        # Inspect the real narrow prompt even when no reply will be generated.
        # The original privacy discrepancy could hide behind a correct WAIT.
        with trial.store.engine.connect() as c:
            request, _ = trial.session.conversation._requests(
                c, viewer, trial.scene, source.source_id, "handler"
            )
        assert request.context.audience == "actor"
        assert request.context.actor == self.actors["handler"]
        encoded = request.model_dump_json()
        assert "SYNTHETIC_TRIAL_GM_PRIVATE_CANARY" not in encoded
        if self.named.get("hidden"):
            assert self.named["hidden"] not in encoded and HIDDEN not in encoded
        if text == HALLWAY[4]:
            assert request.question == "Scene update."
        self.log("handler_prompt_privacy_checked", source_id=source.source_id)
        self.need(source.source_id, text)
        # Reuse the exact append command through the ordinary resumable session.
        result = trial.session.submit(viewer, trial.scene, command)
        route = result["conversation"]
        self.log(
            "engine_routes",
            source_id=source.source_id,
            gm=route["gm"],
            handler_gate=route["handler_decision"]["decision"],
            handler_draft=route["handler"],
        )
        assert route["handler"] is None or route["handler"].get("reply") is None
        assert trial.session.submit(viewer, trial.scene, command) == result
        if route["handler"] is not None:
            draft = route["handler"]
            private = trial.session.conversation.private_handler(
                trial.viewers()["gm"], trial.scene, draft["id"]
            )
            encoded = json.dumps(private["request"])
            assert "SYNTHETIC_TRIAL_GM_PRIVATE_CANARY" not in encoded
            if self.named.get("hidden"):
                assert self.named["hidden"] not in encoded
                assert HIDDEN not in encoded
            assert private["status"] == "awaiting_gm_review"
            trial.session.conversation.review_handler(
                trial.viewers()["gm"],
                f"connected:{self.number}:review",
                trial.scene,
                draft["id"],
                "approve",
                "Fixture GM checked role-known grounding and voluntary player choices.",
            )
            self.log(
                "handler_intervention",
                reply=private["reply"],
                draft_id=draft["id"],
                review="explicit_fixture_gm_approval",
            )
        # Approved drafts become their approved private exchange on readback.
        # Freeze that representation for retries after the explicit review.
        result = trial.session.submit(viewer, trial.scene, command)
        assert trial.session.submit(viewer, trial.scene, command) == result
        self.replays.append((viewer, command, result))
        trial.save()
        return route

    def answer(self, owner, kind, **fields):
        from girlframe.engine.m2 import ChoiceAnswer

        game = self.trial.game
        row = next(x for x in game.choices(owner) if x["kind"] == kind)
        key, value = (
            f"connected-native:{self.number}:{kind}:{owner.user_id}",
            ChoiceAnswer(**fields),
        )
        result = game.respond(owner, key, row["id"], row["revision"], value)
        assert game.respond(owner, key, row["id"], row["revision"], value) == result
        self.log(
            "native_owner_choice", controller=owner.user_id, choice_kind=kind, choice_id=row["id"]
        )

    def proposal(self, request, decision, *, extra=()):
        from girlframe.ai.gm_outcomes import OutcomeProposal

        trial, gm = self.trial, self.trial.viewers()["gm"]
        packet = trial.session.outcomes.packet(gm, trial.scene, request["id"])
        proposal = OutcomeProposal(
            request_id=packet.request_id,
            decision=decision,
            cited_evidence=("source", "native", *extra),
            private_reasoning="Handwritten fixture judgment of actual context and native evidence.",
        )
        saved = trial.session.outcomes.propose(
            gm,
            f"connected:{self.number}:proposal:{decision.kind}",
            trial.scene,
            request["id"],
            proposal,
        )
        owner = next(v for v in trial.viewers().values() if str(v.user_id) == packet.owner_id)
        key = f"connected:{self.number}:confirm:{decision.kind}"
        result = trial.session.outcomes.confirm(owner, key, trial.scene, saved["id"])
        assert trial.session.outcomes.confirm(owner, key, trial.scene, saved["id"]) == result
        self.proofs.append((owner, key, saved["id"], result))
        self.log(
            "gm_native_proposal_and_original_owner_confirmation",
            owner_id=packet.owner_id,
            source_id=packet.source_id,
            proposal=proposal.model_dump(mode="json"),
            result=result,
        )
        return result

    def play(self, play, text, route, *, other=False):
        from test_m2_game import state

        from girlframe.ai.gm_outcomes import KeepOutcome, OutcomeNarration, SensorAnswers
        from girlframe.ai.gm_protocol import Assessment, Demand, TaskFrame, TraitClaim
        from girlframe.ai.knowledge import Acquisition, KnowledgeProposal
        from girlframe.engine.m2 import PlayInput

        trial, gm, pilot, kite = (
            self.trial,
            *[self.trial.viewers()[x] for x in ("gm", "lark", "kite")],
        )
        trial.dice.faces = (4, 5)
        before = trial.dice.calls
        native_key = f"connected:{self.number}:native"
        value = PlayInput(play=play, context=text, trigger_confirmed=True, heat=0)
        revision = state(trial.game).sheets["2"].revision
        started = trial.game.begin(pilot, native_key, 900, revision, value)
        assert trial.game.begin(pilot, native_key, 900, revision, value) == started
        native = started["action_id"]
        trial.session.bind_action(
            gm, native_key + ":bind", trial.scene, route["gm"]["play_review_id"], native
        )
        assert trial.dice.calls == before
        trial.tick()
        for owner in (pilot, kite, gm):
            self.answer(owner, "tag_window", options=("pass",))
        if any(x["kind"] == "mockingbird_risk" for x in trial.game.choices(pilot)):
            self.answer(pilot, "mockingbird_risk")
        assert trial.dice.calls == before + 1
        if play == "keep_your_head":
            self.answer(pilot, "actor_keep", options=("tough", "in_control"), denied=("desperate",))
            choice = next(x for x in trial.game.choices(gm) if x["kind"] == "handler_keep")
            frame = TaskFrame(
                stakes=text,
                demands=(
                    Demand(
                        id="goal",
                        question="Does the actual chosen response satisfy this attempt in context?",
                    ),
                ),
                response_scope="other" if other else "self",
                response_target=self.actors["kite"] if other else None,
            )
            opened = trial.session.outcomes.open(
                gm, native_key + ":open", trial.scene, "choice", choice["id"], frame
            )
            if other:
                handoff = trial.session.responses.request(
                    gm,
                    native_key + ":handoff",
                    trial.scene,
                    opened["id"],
                    "Would you hear the pilot's apology? Decide your own response and any limits.",
                )
                trial.session.responses.answer(
                    kite,
                    native_key + ":response",
                    trial.scene,
                    handoff["id"],
                    "accept",
                    "I can listen to the apology, but I am not promising forgiveness.",
                )
                opened = trial.session.responses.resume(
                    gm, native_key + ":resume", trial.scene, handoff["id"]
                )
                self.log(
                    "target_controller_response",
                    request_id=handoff["id"],
                    actual_actor=self.actors["kite"].model_dump(mode="json"),
                    decision="accept",
                    text="I can listen to the apology, but I am not promising forgiveness.",
                    publication="private_adjudication_only",
                )
            narration = (
                "The pilot asks calmly; the other pilot volunteered to listen, "
                "without promising forgiveness."
                if other
                else "The pilot holds the calibration needle on its mark."
            )
            self.proposal(
                opened,
                KeepOutcome(
                    verdict="enough",
                    narration=narration,
                    assessments=(
                        Assessment(
                            demand_id="goal",
                            sufficient=True,
                            evidence_ids=(
                                "traits",
                                "source",
                                "native",
                                *(("target_response",) if other else ()),
                            ),
                            traits=(TraitClaim(trait="in_control", polarity="are"),),
                            private_reason="The chosen control serves the narrow goal. "
                            "The target's volunteered limits remain intact.",
                        ),
                    ),
                ),
                extra=("target_response",) if other else (),
            )
        else:
            self.answer(
                pilot, "actor_sensors", options=("foundation_destination", "foundation_avoid")
            )
            choice = next(x for x in trial.game.choices(gm) if x["kind"] == "handler_sensors")
            opened = trial.session.outcomes.open(
                gm, native_key + ":open", trial.scene, "choice", choice["id"]
            )
            self.proposal(
                opened,
                SensorAnswers(
                    answers={
                        "a1": "The brief establishes no further Foundation destination.",
                        "a2": "Avoid forced entry; the exercise does not authorise it.",
                    }
                ),
            )
            narration = (
                "The scan answers the training questions; it establishes "
                "no hidden enemy or unstated destination."
            )
        trial.tick()
        inspected = trial.game.inspect(pilot, native)
        assert inspected["state"] == "complete"
        opened = trial.session.outcomes.open(
            gm, native_key + ":readback", trial.scene, "completed", native
        )
        readback = self.proposal(opened, OutcomeNarration(text=narration, effect_refs=("tier",)))
        request = trial.session.knowledge.open(
            gm, native_key + ":learn", trial.scene, readback["id"]
        )
        saved = trial.session.knowledge.propose(
            gm,
            native_key + ":learn-propose",
            trial.scene,
            request["id"],
            KnowledgeProposal(
                request_id=request["id"],
                updates=(
                    Acquisition(
                        basis="outcome",
                        quote=narration,
                        recipients=tuple(self.actors.values()),
                        topic="status",
                    ),
                ),
                private_reasoning="Actual original owner approved this native readback.",
            ),
        )
        trial.session.knowledge.confirm(gm, native_key + ":learn-confirm", trial.scene, saved["id"])
        assert trial.dice.calls == before + 1
        self.actions.append(native)
        self.log(
            "native_play_complete",
            action_id=native,
            play=play,
            receipt=inspected["receipt"],
            result=inspected["result"],
        )
        trial.save()

    def run(self):
        from test_m2_game import state

        trial, starting_dice = self.trial, self.trial.dice.calls
        assert all(len(segment) == 28 for segment in SEGMENTS)
        for label, lines in zip(LABELS, SEGMENTS, strict=True):
            for index, text in enumerate(lines):
                role = "lark" if index % 2 == 0 else "kite"
                # Exact fixture ownership: private sighting, false account and
                # correction belong to Pilot 2; competing observation to Pilot 3.
                if text in (HALLWAY[4], HALLWAY[5], HALLWAY[8], HALLWAY[13], HALLWAY[15]):
                    role = "lark"
                if text == HALLWAY[9]:
                    role = "kite"
                if text in (BARRACKS[20], SIMULATION[12], DEBRIEF[6]):
                    role = "lark"
                route = self.input(text, role, label)
                if text in (BARRACKS[20], DEBRIEF[6]):
                    self.play("keep_your_head", text, route, other=text == DEBRIEF[6])
                elif text == SIMULATION[12]:
                    self.play("check_sensors", text, route)
        assert self.number == 112 and len(self.actions) == 3
        assert trial.dice.calls == starting_dice + 3
        gm_context = trial.context.build(trial.viewers()["gm"], trial.scene)
        handler_context = trial.context.build(
            trial.viewers()["handler"], trial.scene, actor=self.actors["handler"]
        )
        assert HIDDEN not in handler_context.model_dump_json()
        assert HIDDEN in gm_context.model_dump_json()
        refs = {ref.id: ref for ref in gm_context.references}
        assert refs[self.named["allclear"]].text.endswith(HALLWAY[5])
        assert refs[self.named["competing"]].reported_by == self.actors["kite"]
        assert refs[self.named["correction"]].reported_by == self.actors["lark"]
        assert refs[self.named["competing"]].relations[0].kind == "competes_with"
        assert refs[self.named["correction"]].relations[0].kind == "corrects"
        before = state(trial.game).model_dump_json()
        expected_dice = trial.dice.calls
        trial.restart_services()
        trial.session = self.install()
        for viewer, command, result in self.replays[-3:]:
            assert trial.session.submit(viewer, trial.scene, command) == result
        for owner, key, proposal, result in self.proofs:
            assert trial.session.outcomes.confirm(owner, key, trial.scene, proposal) == result
        assert state(trial.game).model_dump_json() == before and trial.dice.calls == expected_dice
        assert (
            trial.context.build(trial.viewers()["gm"], trial.scene).model_dump_json()
            == gm_context.model_dump_json()
        )
        trial.save()
        gates = Counter(
            f"{x['handler_gate']['action']}:{x['handler_gate']['reason']}"
            for x in self.events
            if x["kind"] == "engine_routes"
        )
        summary = {
            "synthetic": True,
            "player_inputs": self.number,
            "fiction_segments": list(LABELS),
            "engine_scenes": 1,
            "native_plays": len(self.actions),
            "dice_rolls": trial.dice.calls - starting_dice,
            "rerolls_on_replay": 0,
            "handler_gates": dict(gates),
            "handler_interventions": sum(x["kind"] == "handler_intervention" for x in self.events),
            "gm_interventions": sum(
                x["kind"] == "engine_routes"
                and x["gm"]["reply"]["gm_decision"]["action"] == "RESPOND"
                for x in self.events
            ),
            "explicit_gm_need_reviews": sum(
                x["kind"] == "gm_response_need_review" for x in self.events
            ),
            "native_owner_confirmations": len(self.proofs),
            "target_controller_handoffs": sum(
                x["kind"] == "target_controller_response" for x in self.events
            ),
            "blind_handler_samples": len(self.blind),
            "blind_gm_samples": len(self.gm_blind),
            "knowledge_references": len(gm_context.references),
            "pending_native_choices": sum(
                len(trial.game.choices(v)) for v in set(trial.viewers().values())
            ),
            "handler_prompts_checked": sum(
                x["kind"] == "handler_prompt_privacy_checked" for x in self.events
            ),
            "privacy_checks": "All Handler prompts exclude unreported sighting and GM canary.",
            "replay_checks": "Last 3 inputs and native confirmations stable after reconstruction.",
            "external_tokens": 0,
            "external_cost": 0,
            "limitations": [
                "Handwritten fixture prose and judgments; no model benchmark.",
                "Local synthetic controller access; no Activity authentication.",
                "Human narrative quality and live readiness remain unverified.",
                "Fiction labels inside one retained scene; no engine travel.",
            ],
        }
        private_json(
            trial.directory / "connected-results.json", {"summary": summary, "events": self.events}
        )
        private_json(trial.directory / "handler-blind.json", {"packets": self.blind})
        private_json(trial.directory / "gm-blind.json", {"packets": self.gm_blind})
        private_json(trial.directory / "connected-summary.json", summary)
        log_path = trial.directory / "connected-events.jsonl"
        log_path.write_text("".join(json.dumps(event) + "\n" for event in self.events))
        log_path.chmod(0o600)
        lines = [
            "# Synthetic connected Director trial",
            "",
            "112 fixture player inputs in one retained engine scene. "
            "Segment names are fiction labels. No model or live operations.",
            "Native proposals and controller responses remain private adjudication "
            "until a separately approved native readback. "
            "Handler replies shown below received explicit fixture GM review.",
            "",
        ]
        for event in self.events:
            number, kind = event["input_number"], event["kind"]
            if kind == "player_input":
                lines.extend(
                    [
                        f"**{number:03} [{event['segment']}] Pilot "
                        f"{event['actual_actor']['entity']}:** {event['text']}",
                        "",
                    ]
                )
            elif kind == "engine_routes":
                gate = event["handler_gate"]
                gm = event["gm"]["reply"]["gm_decision"]
                lines.extend(
                    [
                        f"Engine: Handler {gate['action']} ({gate['reason']}); "
                        f"GM {gm['action']} ({gm['reason']}).",
                        "",
                    ]
                )
            elif kind == "handler_intervention":
                lines.extend(
                    [
                        "Handler, approved private reply: " + event["reply"]["text"],
                        "",
                    ]
                )
            elif kind == "gm_response_need_review":
                lines.extend(["GM privately approves this response need.", ""])
            elif kind == "gm_knowledge_acceptance":
                lines.extend(["GM accepts source-bound knowledge; prior history stays intact.", ""])
            elif kind == "target_controller_response":
                lines.extend(["Target controller supplies a private voluntary response.", ""])
            elif kind == "gm_native_proposal_and_original_owner_confirmation":
                decision = event["proposal"]["decision"]
                if decision["kind"] == "narration":
                    lines.extend(["GM approved native readback: " + decision["text"], ""])
                else:
                    lines.extend(
                        [
                            f"GM private {decision['kind']} proposal confirmed by "
                            f"original owner {event['owner_id']}.",
                            "",
                        ]
                    )
        transcript = trial.directory / "connected-transcript.md"
        transcript.write_text("\n".join(lines))
        transcript.chmod(0o600)
        return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--directory", type=Path, required=True, help="New synthetic trial directory"
    )
    args = parser.parse_args()
    trial = Trial(args.directory, create=True)
    try:
        result = ConnectedTrial(trial).run()
        print(json.dumps(result, indent=2))
    finally:
        trial.close()
    # Reopen the actual database and saved runtime, not just the service objects.
    replay = Trial(args.directory)
    try:
        assert replay.dice.calls == result["dice_rolls"]
        assert (
            len(replay.context.build(replay.viewers()["gm"], replay.scene).references)
            == result["knowledge_references"]
        )
    finally:
        replay.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
