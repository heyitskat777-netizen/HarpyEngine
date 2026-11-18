"""Four persistent synthetic missions with personality fixtures and real native consumers.

No external model or live Discord is used. The simulated pilots use native Pilot
identities, sheets and owners; they are NPCs in this rehearsal's fiction, not the
ordinary engine Npc type (which cannot substitute for a Girl/Frame Play actor).
"""

import argparse
import json
from collections import Counter
from pathlib import Path

from p2_trial_runtime import Trial
from playtest_connected_director import ConnectedTrial, NaturalFixtureHandler, private_json

CAST = {
    "lark": dict(
        name="Mara Saye",
        callsign="Latch",
        voice="Precise, dry, asks before touching.",
        values=("Accuracy", "Consent"),
        fears=("Being the cause of a preventable loss",),
        contradictions=("Wants certainty but knows waiting also has a cost",),
        goal="Bring everyone back without hiding mistakes.",
    ),
    "kite": dict(
        name="Iona Vale",
        callsign="Flint",
        voice="Blunt, restless, protective; jokes when afraid.",
        values=("Protect others", "Act while help is possible"),
        fears=("Watching preventable harm",),
        contradictions=("Dislikes orders but wants clear limits",),
        goal="Prove speed can serve care rather than pride.",
    ),
    "handler": dict(
        name="Corin Hale",
        callsign="Anchor",
        voice="Brief, calm; separates observation from inference.",
        values=("Informed choices", "Accountability"),
        fears=("Giving confident advice from a false report",),
        contradictions=("Offers structure but must allow refusal",),
        goal="Keep orders inside evidence and pilots' actual authority.",
    ),
}
MISSIONS = (
    dict(
        name="Spillway Relay",
        environment="flooded service gallery",
        feature="relay needle",
        objective="Restore the public relay without forcing the sealed service gate.",
        complication=(
            "The relay has a public calibration panel; the sealed gate has no supplied access code."
        ),
    ),
    dict(
        name="Glass Orchard",
        environment="fogged observation gantry",
        feature="reflective contact",
        objective=(
            "Return an attributed reconnaissance report without treating "
            "silhouettes as confirmed targets."
        ),
        complication=(
            "Glare makes the east and west gantries look alike; reports must identify a location."
        ),
    ),
    dict(
        name="Two Convoys",
        environment="crowded supply interchange",
        feature="departure board",
        objective="Agree on a voluntary inspection sequence for two competing convoy requests.",
        complication=(
            "Both convoys request the same inspection window; no pilot can "
            "choose another's cooperation."
        ),
    ),
    dict(
        name="Last Cable",
        environment="iced extraction platform",
        feature="cargo coupling",
        objective=(
            "Recover the cargo through the public coupling; abort if a safe"
            " release cannot be established."
        ),
        complication=(
            "The public coupling is frozen; its protected override is not accessible to the team."
        ),
    ),
)
GM_CANARY = "PRIVATE_SUSTAINED_GM_MOTIVE"
PILOT_CANARY = "PRIVATE_LATCH_UNREPORTED_CONTACT"


class AnchorProvider(NaturalFixtureHandler):
    def respond(self, request):
        from girlframe.ai.conversation import ConversationReply, SyntheticHandlerPolicy
        from girlframe.ai.knowledge import fact_text

        gate = request.response_need or SyntheticHandlerPolicy().decide(request)
        refs = {ref.id: ref for ref in request.context.references}
        question = request.question.casefold()
        topic = (
            "objective" if "objective" in question else "scope" if "limits" in question else None
        )
        selected = (
            [ref for ref in refs.values() if ref.topic == topic][-1:]
            if topic
            else [refs[identity] for identity in gate.source_refs if identity in refs]
        )
        action = None
        offer = None
        lead = "Copy. " if request.persona and "Brief" in request.persona.profile.voice else ""
        if gate.reason == "known_update" and selected:
            ref = selected[0]
            fact = fact_text(ref)
            if ref.topic == "briefing":
                action = "I put the current briefing beside the route map and clear the old note."
                text = fact + " Call out your own approach before committing."
                if "relay" in fact or "convoys" in fact:
                    offer = "brief"
            else:
                action = "I mark the reported location separately from confirmed contacts."
                text = "That is a pilot report. " + fact + " Keep the identity open."
        elif "what enemy" in question:
            selected = []
            text = (
                "I have no reported identity for that location. Hold a safe "
                "position and report what you actually see."
            )
        elif selected:
            text = " ".join(
                "The current "
                + ("report" if ref.reported_by else "record")
                + " says: "
                + fact_text(ref)
                for ref in selected[-2:]
            )
        else:
            text = (
                "I lack a grounded answer. State the observed location and the decision you need."
            )
        return ConversationReply(
            route="handler",
            disposition="answer" if selected else "clarification",
            text=lead + text,
            source_refs=tuple(ref.id for ref in selected[-2:]),
            provider="reviewed-handler-v1",
            handler_action=action,
            handler_play_offer=offer,
        )


class Campaign(ConnectedTrial):
    def __init__(self, trial, chat_count=24):
        self.chat_count = chat_count
        super().__init__(trial)
        self.rebuild()
        self.transcript, self.rulings, self.mission_rows = [], [], []
        self.role_audits, self.hidden = [], []
        self.period_rows, self.rejections, self.snapshots = [], [], []
        self.heat_spends = []
        self.handler_plays = []
        self.current_mission, self.current_phase = 0, "setup"
        self.channel = 900

    def rebuild(self):
        from girlframe.services.director_conversation import DirectorConversationService
        from girlframe.services.director_session import DirectorSessionService

        self.trial.session = DirectorSessionService(
            self.trial.context,
            conversation=DirectorConversationService(
                self.trial.context, handler=AnchorProvider(), handler_mode="reviewed"
            ),
        )

    def answer(self, owner, kind, **fields):
        from girlframe.engine.m2 import ChoiceAnswer

        game = self.trial.game
        row = next(x for x in game.choices(owner) if x["kind"] == kind)
        key = "sustained-choice:" + row["id"]
        value = ChoiceAnswer(**fields)
        result = game.respond(owner, key, row["id"], row["revision"], value)
        assert game.respond(owner, key, row["id"], row["revision"], value) == result
        self.log("native_owner_choice", owner=owner.user_id, choice_kind=kind, choice_id=row["id"])

    def setup(self):
        from test_m2_game import state
        from test_strain_service import D6

        from girlframe.services.m3_missions import MissionService
        from girlframe.services.m3_off_duty import OffDutyService
        from girlframe.services.m3_strain import StrainService

        t = self.trial
        approval = t.store.policy.m3_approval
        t.store.policy = t.store.policy.model_copy(
            update={
                "m3_approval": approval.model_copy(
                    update={"subsystems": approval.subsystems | {"world", "strain", "playbooks"}}
                )
            }
        )
        # Explicit starting fixture, never surgery, restoration or a mid-run reset.
        with t.store.transaction() as c:
            initial = state(t.game)
            for sheet in initial.sheets.values():
                for asset in sheet.assets:
                    asset.void = False
            initial.facts.append(dict(kind="synthetic_gm_private", body=GM_CANARY))
            t.game.event(c, 1, "sustained-baseline", "synthetic.baseline", initial)
        self.missions = MissionService(t.store)
        self.periods = OffDutyService(self.missions)
        self.strain = StrainService(self.periods, dice=D6())
        self.strain.configure(
            t.viewers()["gm"],
            "sustained-strain",
            state(t.game).revision,
            "business_as_usual",
            frozenset(),
        )
        for role in CAST:
            self.dossier(role, "Starting perspective: " + CAST[role]["goal"])
        t.session.dossiers.gm_notes(
            t.viewers()["gm"], "sustained-gm-notes", t.scene, self.actors["handler"], 0, GM_CANARY
        )
        self.audit()

    def dossier(self, role, experience):
        from girlframe.ai.director_dossiers import (
            DossierPerspective,
            DossierProfile,
            DossierState,
            Personnel,
        )

        t, persona = self.trial, CAST[role]
        current = t.session.dossiers.role_packet(t.viewers()[role], t.scene, self.actors[role])
        memories = current.state.experiences if current.state else ()
        proposal = t.session.dossiers.propose(
            t.viewers()["gm"],
            f"dossier:{role}:{current.dossier_version}",
            t.scene,
            self.actors[role],
            current.dossier_version,
            DossierProfile(
                presence="recurring",
                background=persona["name"] + ", callsign " + persona["callsign"],
                voice=persona["voice"],
                behavior=persona["voice"],
                values=persona["values"],
                fears=persona["fears"],
                contradictions=persona["contradictions"],
                reaction_tendencies=("Refuse", "Compromise", "Wait", "Ask for evidence"),
                limits=("Does not own another pilot's choices",),
            ),
            DossierState(
                beliefs=(DossierPerspective(text=persona["goal"]),),
                experiences=(*memories, DossierPerspective(text=experience)),
            ),
            Personnel(
                public_summary=persona["name"] + " / " + persona["callsign"],
                mannerisms=persona["voice"],
            ),
        )
        t.session.dossiers.confirm(
            t.viewers()[role],
            f"dossier-confirm:{role}:{current.dossier_version}",
            t.scene,
            proposal["id"],
        )

    def audit(self, source=None, viewer=None):
        t = self.trial
        with t.store.engine.connect() as c:
            own = {
                role: t.session.dossiers._role_packet(c, t.scene, actor).model_dump(mode="json")
                for role, actor in self.actors.items()
            }
            request = (
                t.session.conversation._requests(c, viewer, t.scene, source, "handler")[0]
                if source
                else None
            )
        for role, packet in own.items():
            encoded = json.dumps(packet)
            assert GM_CANARY not in encoded
            assert "SYNTHETIC_TRIAL_GM_PRIVATE_CANARY" not in encoded
            if role != "lark":
                for identity, text in self.hidden:
                    assert identity not in encoded and text not in encoded
            other_private = [CAST[r]["fears"][0] for r in CAST if r != role]
            assert all(value not in encoded for value in other_private)
        if request:
            encoded = request.model_dump_json()
            assert GM_CANARY not in encoded
            for identity, text in self.hidden:
                assert identity not in encoded and text not in encoded
        self.role_audits.append(
            dict(
                input=self.number,
                handler=request.model_dump(mode="json") if request else None,
                handler_dossier=own["handler"],
            )
        )

    def turn(self, text, role="lark", *, private=False, learning=None):
        from girlframe.ai.observation import AppendSceneInput

        t, viewer = self.trial, self.trial.viewers()[role]
        self.number += 1
        t.clock.now += 6
        command = AppendSceneInput(
            command_key=f"sustained-input:{self.number}",
            expected_scene_revision=t.observer.status(viewer, t.scene).scene_revision,
            speaker="handler" if role == "handler" else "pilot",
            text=text,
            fictional_channel="private" if private else "comms",
        )
        source = t.observer.append_scene_input(viewer, t.scene, command)
        if learning:
            self.learn(source.source_id, *learning)
        self.audit(source.source_id, viewer)
        result = t.session.submit(viewer, t.scene, command)
        route = result["conversation"]
        gate = route["handler_decision"]["decision"]
        self.log(
            "player_input",
            scene=t.scene,
            mission=self.current_mission,
            role=role,
            text=text,
            source_id=source.source_id,
            fictional_channel=command.fictional_channel,
        )
        self.log("engine_routes", handler_gate=gate, gm=route["gm"])
        self.transcript.append(
            f"{self.number:03}. **{CAST[role]['callsign']}** "
            f"({self.current_phase}{'; private' if private else ''}): {text}\n\n"
            f"    Handler gate: `{gate['action']}:{gate['reason']}`"
        )
        if route["handler"] is not None:
            draft = route["handler"]
            raw = t.session.conversation.private_handler(t.viewers()["gm"], t.scene, draft["id"])
            assert GM_CANARY not in raw["reply"]["text"]
            for _, hidden in self.hidden:
                assert hidden not in raw["reply"]["text"]
            t.session.conversation.review_handler(
                t.viewers()["gm"],
                f"handler-review:{self.number}",
                t.scene,
                draft["id"],
                "approve",
                "Synthetic GM reviewed role grounding and voluntary agency.",
            )
            self.log("handler_intervention", reply=raw["reply"], source_id=source.source_id)
            reply = raw["reply"]
            if reply.get("handler_action"):
                self.transcript.append("    **Anchor acts:** " + reply["handler_action"])
            self.transcript.append("    **Handler / Anchor:** " + reply["text"])
            if reply.get("handler_play_offer") == "brief":
                self.handler_brief(draft["id"], reply["text"], viewer)
        result = t.session.submit(viewer, t.scene, command)
        assert t.session.submit(viewer, t.scene, command) == result
        self.replays.append((viewer, command, result))
        t.role = role
        t.last_message = dict(
            role=role, command=command.model_dump(mode="json"), source_id=source.source_id
        )
        if self.number % 50 == 0:
            print(
                f"Accepted input {self.number}; mission {self.current_mission}, "
                f"{self.current_phase}",
                flush=True,
            )
        return source, route

    def handler_brief(self, draft, text, recipient):
        from test_m2_game import state

        from girlframe.ai.gm_outcomes import HandlerOutcome
        from girlframe.engine.m3_handler_play_state import Effect
        from girlframe.services.m3_handler_plays import HandlerPlayService

        t, owner = self.trial, self.trial.viewers()["handler"]
        revision = state(t.game).revision
        grant = t.session.conversation.start_handler_brief(owner, t.scene, draft, revision)
        request = t.session.outcomes.open(
            t.viewers()["gm"], f"handler-brief:{self.number}", t.scene, "handler_grant", grant["id"]
        )
        self.proposal(
            request, HandlerOutcome(play="brief", effect=Effect(kind="brief", account=text))
        )
        notice = HandlerPlayService(t.store).notice(recipient, grant["id"])
        assert notice["state"] == "complete" and notice["account"] == text
        assert t.session.conversation.start_handler_brief(owner, t.scene, draft, revision) == grant
        self.handler_plays.append(
            dict(
                input=self.number,
                mission=self.current_mission,
                id=grant["id"],
                play=notice["play"],
                recipient=recipient.user_id,
            )
        )
        self.transcript.append("    **Native Handler Play:** Brief them on the situation.")

    def learn(self, source, quote, recipients, basis="testimony", prior=None, topic="status"):
        from girlframe.ai.knowledge import Acquisition, KnowledgeProposal

        t, gm = self.trial, self.trial.viewers()["gm"]
        key = f"learn:{self.number}:{len(self.hidden)}:{source}"
        opened = t.session.knowledge.open(gm, key + ":open", t.scene, source)
        saved = t.session.knowledge.propose(
            gm,
            key + ":propose",
            t.scene,
            opened["id"],
            KnowledgeProposal(
                request_id=opened["id"],
                updates=(
                    Acquisition(
                        basis=basis,
                        quote=quote,
                        recipients=tuple(self.actors[r] for r in recipients),
                        prior_reference=prior,
                        topic=topic,
                    ),
                ),
                private_reasoning="Synthetic interpretation of actual source and recipients.",
            ),
        )
        result = t.session.knowledge.confirm(gm, key + ":confirm", t.scene, saved["id"])
        return result["references"][0]

    def chat(self, mission, phase, count):
        self.current_phase = phase
        latch = (
            "I mark {feature} on my own sheet and leave your column for you.",
            "The {environment} has enough noise already. I read one check at a time.",
            "I would rather report a gap than fill it with a guess about {feature}.",
            "My hands are clear of your controls. Say when you want my observations.",
            "I can wait through a quiet minute. It does not mean I have stopped paying attention.",
            (
                "I want certainty about {feature}; I can still choose a "
                "cautious alternative without it."
            ),
            "I compare the current note with my previous note and retain both.",
            (
                "I check the route margin again. Being methodical is cheaper "
                "than pretending I checked."
            ),
        )
        flint = (
            "I want to get moving, but I am not moving your hands for you.",
            "If {feature} has an opinion, it can put it in writing like the rest of us.",
            "I will take the awkward part of the {environment}; you can decline the offer.",
            "I check the exit before I make a brave suggestion.",
            "Waiting feels useless. I can still choose it while the evidence catches up.",
            "I have a shortcut in mind, not permission to take it.",
            "After my earlier control failure, I am checking the hardware before I rush.",
            "I can protect the person beside me without deciding what they want.",
        )
        for i in range(count):
            role = "lark" if i % 2 == 0 else "kite"
            lines = latch if role == "lark" else flint
            text = lines[(i // 2 + self.current_mission + len(phase)) % len(lines)].format(
                **mission
            )
            if self.current_mission == 1 and "After my earlier" in text:
                text = (
                    "I make a joke about the gate, then check whether the handle is"
                    " actually public."
                )
            if i in (4, count - 3):
                text = (
                    "Handler, what is the current objective?"
                    if i == 4
                    else "Handler, what are our authorised limits?"
                )
            self.turn(text, role)
        self.quiet_review()

    def quiet_review(self):
        from girlframe.ai.director_reactions import ReactionProposal

        t = self.trial
        t.clock.now += 120
        batch = t.observer.claim_review(t.scene)
        if batch is None:
            return
        source = next(x for x in reversed(batch.inputs) if x.kind == "message")
        key = "sustained-quiet:" + batch.run_id
        opened = t.session.reactions.open(
            t.viewers()["gm"],
            key + ":open",
            t.scene,
            self.actors["lark"],
            source.source_id,
            run_id=batch.run_id,
        )
        proposal = t.session.reactions.propose(
            t.viewers()["gm"],
            key + ":propose",
            t.scene,
            opened["id"],
            ReactionProposal(
                request_id=opened["id"],
                kind="WAIT",
                rationale="No new optional interruption is needed; retain unresolved choices.",
            ),
        )
        result = t.session.reactions.review(
            t.viewers()["lark"],
            key + ":review",
            t.scene,
            proposal["id"],
            "approve",
            "Synthetic actor owner allows a quiet review without speech.",
        )
        assert not result["text"] and not result["effects_applied"]
        self.log(
            "quiet_batch_review", run=batch.run_id, reason=batch.reason, frontier=batch.frontier
        )

    def world_front(self, mission):
        from test_m2_game import state

        from girlframe.ai.director_fronts import (
            FrontClock,
            FrontDraft,
            FrontEvidence,
            FrontParticipant,
        )
        from girlframe.ai.worldbuilding import DevelopmentAction, WorldbuildingProposal
        from girlframe.engine.m3_world_development import DevelopmentDraft, Subject

        t, gm = self.trial, self.trial.viewers()["gm"]
        source, _ = self.turn("GM, establish the briefing constraints for " + mission["name"] + ".")
        service, key = t.session.worldbuilding, f"mission-world:{self.current_mission}"
        opened = service.open(gm, key + ":open", t.scene, source.source_id)
        saved = service.propose(
            gm,
            key + ":propose",
            t.scene,
            opened["id"],
            WorldbuildingProposal(
                request_id=opened["id"],
                action=DevelopmentAction(
                    development=DevelopmentDraft(
                        key=f"mission-{self.current_mission}",
                        kind="complication",
                        subject=Subject(kind="location", id="base0"),
                        title=mission["name"],
                        text=mission["complication"],
                    )
                ),
                cited_evidence=("source", "native"),
                private_reasoning="A situation, not a promised ending.",
            ),
        )
        service.review(
            gm,
            key + ":review",
            t.scene,
            saved["id"],
            "approve",
            "Actual public constraints; no mechanical effects.",
        )
        commit = service.confirm(gm, key + ":confirm", t.scene, saved["id"])
        service.disclose(
            gm,
            key + ":disclose",
            t.scene,
            commit["id"],
            mission["complication"],
            tuple(self.actors.values()),
            topic="briefing",
        )
        front = FrontDraft(
            key=f"mission-{self.current_mission}",
            title=mission["name"],
            situation=mission["complication"],
            participants=(FrontParticipant(subject=Subject(kind="location", id="base0")),),
            fact_refs=(FrontEvidence(kind="world_development", id=commit["native"]["id"]),),
            clock=FrontClock(limit=2),
            unresolved_consequences=(
                "A delayed or refused approach remains available; no outcome is preordained.",
            ),
        )
        head = t.session.fronts.save(gm, key + ":front", t.scene, state(t.game).revision, front)
        return front, head

    def begin_play(self, role, text, play="keep_your_head", faces=(4, 5)):
        from test_m2_game import state

        from girlframe.engine.m2 import PlayInput

        t, viewer = self.trial, self.trial.viewers()[role]
        _, route = self.turn(text, role)
        key = f"sustained-play:{self.number}"
        t.dice.faces = faces
        before = t.dice.calls
        sheet = state(t.game).sheets[str(viewer.user_id)]
        heat = sheet.heat if sheet.heat >= 5 else 0
        self.heat_spends.append(
            dict(
                mission=self.current_mission,
                actor=CAST[role]["callsign"],
                held=sheet.heat,
                spent=heat,
            )
        )
        action = t.game.begin(
            viewer,
            key,
            self.channel,
            state(t.game).sheets[str(viewer.user_id)].revision,
            PlayInput(play=play, heat=heat, trigger_confirmed=True, context=text),
        )["action_id"]
        t.session.bind_action(
            t.viewers()["gm"], key + ":bind", t.scene, route["gm"]["play_review_id"], action
        )
        t.tick(1)
        for owner in (t.viewers()["lark"], t.viewers()["kite"], t.viewers()["gm"]):
            self.answer(owner, "tag_window", options=("pass",))
        if any(x["kind"] == "mockingbird_risk" for x in t.game.choices(viewer)):
            self.answer(viewer, "mockingbird_risk")
        assert t.dice.calls == before + 1
        return action, key

    def keep(
        self,
        role,
        goal,
        *,
        approach="methodical",
        mode="mid",
        required="in_control",
        other=False,
        clarify=False,
        target_decision="decline",
    ):
        from girlframe.ai.gm_outcomes import KeepOutcome
        from girlframe.ai.gm_protocol import Assessment, Demand, TaskFrame, TraitClaim

        t, gm, viewer = self.trial, self.trial.viewers()["gm"], self.trial.viewers()[role]
        action, key = self.begin_play(
            role,
            "GM, I declare Keep Your Head to " + ("help with this" if clarify else goal),
            faces={"low": (2, 3), "mid": (4, 5), "high": (6, 6)}[mode],
        )
        with t.store.engine.connect() as c:
            actual_level = t.game.action(c, action)["data"]["result"]["tier"]
        if actual_level == "low":
            positive, negative, tag = ("tough",), (), ""
        elif actual_level == "high":
            positive, negative, tag = (
                (),
                (),
                "Rattled during " + MISSIONS[self.current_mission - 1]["name"],
            )
        elif approach == "methodical":
            positive, negative, tag = ("tough", "in_control"), ("desperate",), ""
        else:
            positive, negative, tag = ("tough", "vicious"), ("in_control",), ""
        self.answer(viewer, "actor_keep", options=positive, denied=negative, text=tag)
        choice = next(x for x in t.game.choices(gm) if x["kind"] == "handler_keep")
        frame = TaskFrame(
            stakes="Help with this" if clarify else goal,
            demands=(Demand(id="goal", question="Does this actual attempt meet its stated goal?"),),
            response_scope="other" if other else "self",
            response_target=self.actors["kite"] if other else None,
            intent="needs_clarification" if clarify else "established",
        )
        opened = t.session.outcomes.open(gm, key + ":open", t.scene, "choice", choice["id"], frame)
        if clarify:
            pending = t.session.outcomes.packet(gm, t.scene, opened["id"])
            from girlframe.ai.gm_outcomes import OutcomeProposal

            draft = t.session.outcomes.propose(
                gm,
                key + ":unclear",
                t.scene,
                opened["id"],
                OutcomeProposal(
                    request_id=pending.request_id,
                    decision=KeepOutcome(
                        verdict="needs_clarification",
                        narration="The attempted result needs a specific goal.",
                    ),
                    cited_evidence=("source", "native"),
                    private_reasoning="The model must not invent the intended task.",
                ),
            )
            from girlframe.services.onboarding import WorkflowError

            try:
                t.session.outcomes.confirm(gm, key + ":blocked", t.scene, draft["id"])
                raise AssertionError("Clarification was executed as a ruling")
            except WorkflowError as error:
                self.rejections.append(
                    dict(kind="unclear_ruling_held", code=str(error).split(":")[0])
                )
            from girlframe.ai.observation import AppendSceneInput

            clarification = (
                "I mean holding the departure indicator steady, not deciding which convoy agrees."
            )
            try:
                t.observer.append_scene_input(
                    viewer,
                    t.scene,
                    AppendSceneInput(
                        command_key=key + ":ic-clarification",
                        speaker="pilot",
                        text=clarification,
                        expected_scene_revision=t.observer.status(viewer, t.scene).scene_revision,
                        fictional_channel="comms",
                    ),
                )
                raise AssertionError("IC input unexpectedly bypassed the pending Play")
            except WorkflowError as error:
                if not str(error).startswith("SCENE_BUSY"):
                    raise
                self.rejections.append(
                    dict(
                        kind="ic_clarification_blocked",
                        continuation=(
                            "Original Pilot clarifies through private source-bound OOC review."
                        ),
                    )
                )
            handoff = t.session.responses.request(
                gm,
                key + ":intent-question",
                t.scene,
                opened["id"],
                "What are you trying to achieve with this attempt?",
                clarify_intent=True,
            )
            t.session.responses.answer(
                viewer, key + ":intent-answer", t.scene, handoff["id"], "clarify", goal
            )
            opened = t.session.responses.resume(gm, key + ":clear", t.scene, handoff["id"])
            self.transcript.append(
                f"    **{CAST[role]['callsign']} clarifies privately to the GM:** {goal}."
            )
        if other:
            handoff = t.session.responses.request(
                gm,
                key + ":handoff",
                t.scene,
                opened["id"],
                "Will you accept the proposed inspection sequence? Choose your own response.",
            )
            t.session.responses.answer(
                t.viewers()["kite"],
                key + ":answer",
                t.scene,
                handoff["id"],
                target_decision,
                "I accept the public-lane-first alternative."
                if target_decision == "accept"
                else (
                    "I will inspect the public lane with you, but do not agree to "
                    "your departure order."
                ),
            )
            opened = t.session.responses.resume(gm, key + ":resume", t.scene, handoff["id"])
        packet = t.session.outcomes.packet(gm, t.scene, opened["id"])
        citations = (("target_response",) if other else ()) + (("actor_intent",) if clarify else ())
        if clarify:
            assert packet.frame.stakes == goal and any(
                e.id == "actor_intent" for e in packet.evidence
            )
        actual = packet.native["action"]["data"]["result"]
        positive, negative = tuple(actual["positive"]), tuple(actual["negative"])
        sufficient = required in positive and (
            not other or packet.native["response_decision"] == "accept"
        )
        traits = (
            (TraitClaim(trait=required, polarity="are" if required in positive else "are_not"),)
            if required in (*positive, *negative)
            else ()
        )
        narration = (
            f"{CAST[role]['callsign']} succeeds at the declared task: {goal}."
            if sufficient
            else f"{CAST[role]['callsign']} does not {goal}; an alternative remains open."
        )
        decision = KeepOutcome(
            verdict="enough" if sufficient else "not_enough",
            narration=narration,
            assessments=(
                Assessment(
                    demand_id="goal",
                    sufficient=sufficient,
                    evidence_ids=(
                        "source",
                        "native",
                        "traits",
                        *citations,
                    ),
                    traits=traits,
                    private_reason=(
                        "PRIVATE_GM: assess the chosen traits against the actual goal "
                        "and the target's voluntary response; a high roll alone does "
                        "not supply access."
                    ),
                ),
            ),
        )
        packet = t.session.outcomes.packet(gm, t.scene, opened["id"])
        self.proposal(opened, decision, extra=citations)
        t.tick()
        result = t.game.inspect(viewer, action)
        assert result["state"] == "complete"
        record = dict(
            mission=self.current_mission,
            actor=CAST[role]["callsign"],
            goal=goal,
            native_total=result["result"]["total"],
            positive=positive,
            negative=negative,
            verdict=decision.verdict,
            actor_intent_clarification=clarify,
            narration=narration,
            request=packet.model_dump(mode="json"),
        )
        self.rulings.append(record)
        self.transcript.append(
            f"    **GM ruling:** `{decision.verdict}` — {narration} "
            f"(native total {record['native_total']}; are={positive}, are not={negative})."
        )
        return self.readback(action, narration, key)

    def readback(self, action, text, key):
        from girlframe.ai.gm_outcomes import OutcomeNarration

        t, gm = self.trial, self.trial.viewers()["gm"]
        opened = t.session.outcomes.open(gm, key + ":readback", t.scene, "completed", action)
        result = self.proposal(opened, OutcomeNarration(text=text, effect_refs=("tier",)))
        self.learn(result["id"], text, tuple(self.actors), basis="outcome")
        self.actions.append(action)
        return result["id"]

    def sensors(self, mission):
        from girlframe.ai.gm_outcomes import SensorAnswers

        t, gm = self.trial, self.trial.viewers()["gm"]
        action, key = self.begin_play(
            "kite",
            "GM, I declare Check Your Sensors to inspect the public approach.",
            "check_sensors",
        )
        with t.store.engine.connect() as c:
            level = t.game.action(c, action)["data"]["result"]["tier"]
        questions = ("foundation_destination", "foundation_avoid", "enemy_activity")[
            : {"low": 1, "mid": 2, "high": 3}[level]
        ]
        self.answer(t.viewers()["kite"], "actor_sensors", options=questions)
        choice = next(x for x in t.game.choices(gm) if x["kind"] == "handler_sensors")
        opened = t.session.outcomes.open(gm, key + ":open", t.scene, "choice", choice["id"])
        answers = (
            "No further Foundation destination has been established.",
            "Avoid the protected override; use the public approach described in the briefing.",
            "No satellite-confirmed enemy identity is established; silhouettes remain reports.",
        )
        self.proposal(
            opened, SensorAnswers(answers={f"a{i + 1}": answers[i] for i in range(len(questions))})
        )
        t.tick()
        assert t.game.inspect(t.viewers()["kite"], action)["state"] == "complete"
        text = (
            "The scan answers its actual questions; it establishes neither "
            "an enemy identity nor private access."
        )
        self.transcript.append(
            "    **GM Sensors answers:** public approach only; no invented "
            "destination, enemy identity or override authority."
        )
        return self.readback(action, text, key)

    def close_mission(self, mission, native, front, head, last_readback):
        from test_m2_game import state

        from girlframe.ai.director_fronts import FrontAdvance
        from girlframe.engine.m3_punishments import Details
        from girlframe.services.m3_punishments import PunishmentService
        from girlframe.services.onboarding import WorkflowError

        t, gm = self.trial, self.trial.viewers()["gm"]
        permissions = {k: s.permissions for k, s in state(t.game).sheets.items()}
        key = f"mission:{self.current_mission}"
        ended = self.missions.end(
            gm,
            key + ":end",
            native["id"],
            native["revision"],
            mission["success"],
            debrief="Synthetic GM mission review: " + mission["objective"],
        )
        reward_snapshot = {k: s.permissions for k, s in state(t.game).sheets.items()}
        assert (
            self.missions.end(
                gm,
                key + ":end",
                native["id"],
                native["revision"],
                mission["success"],
                debrief="Synthetic GM mission review: " + mission["objective"],
            )
            == ended
        )
        discipline = PunishmentService(t.store)
        work = self.missions.get(gm, native["id"])["work"]
        punishment_count = 0
        for item in work:
            if item["kind"] != "punishment":
                raise AssertionError("Unexpected mandatory mission consequence: " + item["kind"])
            review = discipline.get(gm, item["id"])
            if review["state"] == "resolved":
                continue
            try:
                self.missions.complete(gm, key + ":cannot-skip", native["id"], ended["revision"])
                raise AssertionError("Mission consequence skipped")
            except WorkflowError:
                pass
            severity = review.get("required_severity")
            choice = Details(
                kind="strict_regulations" if severity == "moderate" else "stimulant_injection"
            )
            discipline.apply(
                gm,
                key + ":discipline:" + item["id"],
                item["id"],
                review["revision"],
                review["game_revision"],
                choice,
            )
            punishment_count += 1
        completed = self.missions.complete(gm, key + ":complete", native["id"], ended["revision"])
        assert completed["phase"] == "complete"
        # Resolve this attempt's Front from an actual approved native Play outcome,
        # rather than converting an elapsed deadline into a mission result.
        changed = front.model_copy(update={"supersedes": head["id"], "status": "resolved"})
        t.session.fronts.save(
            gm,
            key + ":resolve-front",
            t.scene,
            state(t.game).revision,
            changed,
            advance=FrontAdvance(kind="outcome", id=last_readback),
        )
        self.mission_rows.append(
            dict(
                number=self.current_mission,
                name=mission["name"],
                success=mission["success"],
                id=native["id"],
                phase=completed["phase"],
                permissions_before=permissions,
                permissions_after=reward_snapshot,
                discipline_tasks=punishment_count,
                status_order=list(state(t.game).order),
            )
        )
        self.transcript.append(
            f"\n**Mission end:** {'success' if mission['success'] else 'failure / safe abort'}; "
            f"native rewards {permissions} → {reward_snapshot}; {punishment_count} actual "
            "discipline task(s) resolved by their owner.\n"
        )
        for role in CAST:
            experience = (
                "Review of "
                + mission["name"]
                + ": "
                + (
                    "An alternative succeeded without erasing a failed attempt."
                    if mission["success"]
                    else (
                        "The cargo was not recovered. Safe withdrawal did not make the "
                        "objective successful."
                    )
                )
            )
            self.dossier(role, experience)
        t.save()
        return ended

    def off_duty(self, index):
        from test_m2_game import state
        from test_off_duty_cycle import call, movement
        from test_strain import facts
        from test_world import gorgon

        from girlframe.engine.m3_off_duty import RecoveryChoice
        from girlframe.engine.m3_strain_effects import Choice
        from girlframe.engine.m3_world_state import Faction
        from girlframe.services.m3_off_duty_cycle import CycleService
        from girlframe.services.m3_strain_effects import EffectService
        from girlframe.services.onboarding import WorkflowError

        t, gm = self.trial, self.trial.viewers()["gm"]
        self.current_phase = "off-duty"
        period = self.periods.begin(gm, f"period:{index}")
        try:
            self.missions.offer(gm, f"period:{index}:no-skip", "Premature dispatch", (2, 3))
            raise AssertionError("Off-Duty period bypassed")
        except WorkflowError:
            self.rejections.append(
                dict(kind="mission_during_off_duty_blocked", period=period["id"])
            )
        self.strain.prepare(
            gm,
            f"period:{index}:prepare",
            period["id"],
            period["revision"],
            state(t.game).revision,
            facts(
                no_girl_void=True,
                last_mission_success_no_frame_death_infrastructure_loss=(index == 1),
            ),
        )
        effects = EffectService(self.strain)
        selected = {
            "void": (
                1,
                1,
                Choice(
                    rule_id="strain.void.low.1.1",
                    account="A Directed threat approaches during this recorded period.",
                    gorgon=gorgon("directed", f"sustained-directed-{index}", (10, 0)),
                ),
            ),
            "rebellion": (
                1,
                1,
                Choice(
                    rule_id="strain.rebellion.low.1.1",
                    account="A distinct local cell forms.",
                    target="city0",
                    faction=Faction(
                        id=f"sustained-cell-{index}",
                        name=f"Local cell {index}",
                        kind="rebel",
                        cells=((0, 4),),
                        description="Local dissent",
                    ),
                ),
            ),
            "budget": (
                5,
                2,
                Choice(
                    rule_id="strain.budget.low.5.2",
                    account="Rooms are reassigned by the native event.",
                    rooms=((2, 3),),
                ),
            ),
        }
        for request in tuple(state(t.game).strain.requests):
            if request.severity != "low":
                raise AssertionError(
                    "This declared low-Strain fixture encountered an unsupported higher branch"
                )
            face, column, choice = selected[request.track]
            self.strain.dice.face = face
            self.strain.roll(
                gm, f"period:{index}:roll:{request.track}", request.id, 1, state(t.game).revision
            )
            self.strain.choose(
                gm,
                f"period:{index}:column:{request.track}",
                request.id,
                2,
                state(t.game).revision,
                column,
            )
            effects.apply(
                gm,
                f"period:{index}:effect:{request.track}",
                request.id + ":effect",
                1,
                state(t.game).revision,
                choice,
            )
        cycle = CycleService(self.periods)
        call(cycle, t.game, gm, period["id"], "activate")
        for role in ("lark", "kite"):
            viewer = t.viewers()[role]
            from girlframe.engine.m2 import PlayInput
            from girlframe.engine.m3_frame_rewards import Claim
            from girlframe.services.m3_frame_rewards import RewardService

            t.dice.faces = (2, 2) if viewer.user_id == state(t.game).order[0] else (4, 4)
            action = t.game.begin(
                viewer,
                f"period:{index}:off-duty:{role}",
                self.channel,
                state(t.game).sheets[str(viewer.user_id)].revision,
                PlayInput(
                    play="go_off_duty",
                    off_duty_id=period["id"],
                    heat=0,
                    context="Native recovery after recorded missions",
                    trigger_confirmed=True,
                ),
            )["action_id"]
            t.tick(1)
            for owner in (t.viewers()["lark"], t.viewers()["kite"], gm):
                self.answer(owner, "tag_window", options=("pass",))
            t.tick(8)
            rewards = RewardService(self.periods)
            for work in self.periods.get(viewer, period["id"])["work"]:
                if work["kind"] == "frame_off_duty_reward":
                    data = rewards.get(viewer, work["id"])
                    if data["owner_id"] == str(viewer.user_id) and data["mode"] == "conditional":
                        rewards.apply(
                            viewer,
                            f"period:{index}:reward:{role}",
                            work["id"],
                            data["revision"],
                            data["game_revision"],
                            Claim(
                                fulfilled=False,
                                account="Synthetic owner reports no qualifying Frame reward event.",
                            ),
                        )
            self.actions.append(action)
            call(cycle, t.game, viewer, period["id"], "scene", None, (), "")
            call(cycle, t.game, viewer, period["id"], "recover", RecoveryChoice())
        t.game.dice = t.dice
        call(
            cycle,
            t.game,
            gm,
            period["id"],
            "handler_scene",
            "routine",
            (1, 2),
            (
                "Anchor asks Latch which facts should change the next briefing;"
                " no private pilot sheet is quoted."
            ),
        )
        call(cycle, t.game, gm, period["id"], "acknowledge", None)
        call(cycle, t.game, t.viewers()["lark"], period["id"], "acknowledge", None)
        order = (3, 2) if index == 1 else (2, 3)
        call(
            cycle,
            t.game,
            gm,
            period["id"],
            "review_status",
            order,
            "Synthetic native performance review; unrelated to emotional trust.",
        )
        result = call(cycle, t.game, gm, period["id"], "finish", movement(t.game))
        assert result["phase"] == "complete"
        assert not self.periods.current(gm)
        assert not t.session.campaign_work(gm, t.scene)["required_work"]
        self.period_rows.append(
            dict(
                id=period["id"],
                phase=result["phase"],
                status_order=list(order),
                strain_faces={k: v[0] for k, v in selected.items()},
            )
        )
        self.transcript.append(
            f"\n**Native Off-Duty {index}:** three saved Strain dice and typed effects, "
            f"both pilot rolls/recovery, Handler scene acknowledgements, Status {order}, "
            "real world advancement.\n"
        )

    def next_scene(self, channel):
        from test_director_continuity import carry, new_scene

        from girlframe.services.director_context import DirectorContextService

        t, gm = self.trial, self.trial.viewers()["gm"]
        old = t.scene
        references = tuple(x.id for x in t.context.build(gm, old).references)
        target = new_scene(t.observer, channel=channel, previous_channel=self.channel)
        carry(t.context, old, target, references, f"sustained-carry:{channel}")
        t.scene = target
        t.scene_channel = channel
        self.channel = channel
        t.context = DirectorContextService(t.observer)
        self.rebuild()
        self.audit()
        self.log("native_scene_handoff", origin=old, destination=target, carried=len(references))

    def run(self):
        import sqlalchemy as sa
        from test_m2_game import state
        from test_p2_mission_cycle import launch

        from girlframe.database import tables as tables

        self.setup()
        t = self.trial
        for number, template in enumerate(MISSIONS, 1):
            mission = dict(template)
            self.current_mission = number
            self.current_phase = "briefing"
            self.transcript.append(
                f"\n## Mission {number}: {mission['name']}\n\n{mission['objective']}\n"
            )
            native = launch(self.missions, f"sustained-mission:{number}", mission["objective"])
            brief = "Mission " + str(number) + " objective: " + mission["objective"]
            self.turn(
                brief,
                "handler",
                learning=(brief, tuple(self.actors), "testimony", None, "objective"),
            )
            front, head = self.world_front(mission)
            self.chat(mission, "briefing", self.chat_count)
            self.chat(mission, "approach", self.chat_count)
            if number == 2:
                hidden = f"{PILOT_CANARY}: an unreported violet reflector beneath the lower gantry."
                source, _ = self.turn(hidden, "lark", private=True)
                identity = self.learn(source.source_id, hidden, ("lark",), basis="perception")
                self.hidden.append((identity, hidden))
                self.turn("Handler, what enemy is behind the lower gantry?", "kite")
                public = (
                    "I can see an amber silhouette by the east rail; its identity is unconfirmed."
                )
                self.turn(
                    public,
                    "lark",
                    learning=(public, tuple(self.actors), "testimony", None, "tactical"),
                )
            self.sensors(mission)
            self.chat(mission, "worksite", self.chat_count)
            if number == 1:
                self.keep(
                    "kite",
                    "hold the relay needle precisely despite rushing",
                    approach="rushed",
                    required="in_control",
                )
                last = self.keep(
                    "lark",
                    (
                        "endure the cold to hold the public relay lever until automatic"
                        " calibration finishes"
                    ),
                    approach="methodical",
                    mode="low",
                    required="tough",
                )
            elif number == 2:
                self.keep("lark", "hold the sensor trace steadily for a located report")
                last = self.keep(
                    "kite",
                    "obtain the protected gate code from confidence alone",
                    approach="rushed",
                    mode="high",
                    required="in_control",
                )
            elif number == 3:
                self.keep(
                    "lark",
                    "obtain Flint's voluntary agreement to my departure sequence",
                    approach="rushed",
                    other=True,
                )
                last = self.keep(
                    "lark",
                    "hold the departure indicator steady",
                    approach="methodical",
                    clarify=True,
                )
                agreement = (
                    "I agree to inspect the public lane first; I still choose my own controls."
                )
                self.turn(agreement, "kite", learning=(agreement, tuple(self.actors)))
            else:
                self.keep(
                    "kite",
                    "open the inaccessible cargo override by maintaining confidence",
                    approach="rushed",
                    mode="high",
                )
                last = self.keep("lark", "keep the team calm while we withdraw without the cargo")
            if number == 3:
                last = self.keep(
                    "lark",
                    "obtain Flint's voluntary agreement to inspect the public lane first",
                    other=True,
                    target_decision="accept",
                )
            if number in (1, 3):
                mission["success"] = self.rulings[-1]["verdict"] == "enough"
            elif number == 2:
                mission["success"] = self.rulings[-2]["verdict"] == "enough"
            else:
                mission["success"] = self.rulings[-2]["verdict"] == "enough"
            self.chat(mission, "decision", self.chat_count)
            self.chat(mission, "extraction", self.chat_count)
            self.chat(mission, "debrief", self.chat_count)
            self.close_mission(mission, native, front, head, last)
            if number in (2, 4):
                self.off_duty(number // 2)
            self.audit()
            self.snapshots.append(
                dict(
                    mission=number,
                    revision=state(t.game).revision,
                    dossiers={
                        r: t.session.dossiers.role_packet(
                            t.viewers()[r], t.scene, a
                        ).dossier_version
                        for r, a in self.actors.items()
                    },
                    permissions={k: s.permissions for k, s in state(t.game).sheets.items()},
                    frames={
                        k: [a.damaged for a in s.assets if a.family == "frame"]
                        for k, s in state(t.game).sheets.items()
                    },
                )
            )
            t.store.engine.dispose()
            self.rebuild()
            for viewer, command, result in self.replays[-2:]:
                assert t.session.submit(viewer, t.scene, command) == result
            if number < 4:
                self.next_scene(900 + number)
            print(f"Completed synthetic mission {number}: {mission['name']}", flush=True)
        canon = state(t.game)
        assert all(row["phase"] == "complete" for row in self.missions.list(t.viewers()["gm"]))
        assert not any(t.game.choices(t.viewers()[role]) for role in CAST)
        with t.store.engine.connect() as c:
            receipt_count = c.scalar(
                sa.select(sa.func.count()).select_from(tables.m2["m2_receipts"])
            )
        summary = dict(
            synthetic=True,
            model_calls=0,
            external_cost=0,
            inputs=self.number,
            missions=self.mission_rows,
            periods=self.period_rows,
            native_receipts=receipt_count,
            mission_plays=len(self.rulings) + len(MISSIONS),
            strain_rolls=self.strain.dice.calls,
            quiet_batches=sum(e["kind"] == "quiet_batch_review" for e in self.events),
            handler_interventions=sum(e["kind"] == "handler_intervention" for e in self.events),
            handler_plays=self.handler_plays,
            handler_actions=sum(
                bool(e["reply"].get("handler_action"))
                for e in self.events
                if e["kind"] == "handler_intervention"
            ),
            handler_gates=dict(
                Counter(
                    e["handler_gate"]["action"] + ":" + e["handler_gate"]["reason"]
                    for e in self.events
                    if e["kind"] == "engine_routes"
                )
            ),
            contextual_rulings=[
                {k: v for k, v in r.items() if k != "request"} for r in self.rulings
            ],
            role_audit_groups=len(self.role_audits),
            heat_spending=self.heat_spends,
            private_leaks_detected=0,
            guard_rejections=self.rejections,
            final_dossier_versions={
                r: t.session.dossiers.role_packet(t.viewers()[r], t.scene, a).dossier_version
                for r, a in self.actors.items()
            },
            final_status=list(canon.order),
            pending_native_choices=sum(len(t.game.choices(t.viewers()[role])) for role in CAST),
            limitations=[
                (
                    "Personality/dialogue and GM judgments are explicit offline "
                    "fixtures, not an autonomous model benchmark."
                ),
                (
                    "Both simulated NPC pilots use native MOCKINGBIRD/JANUS "
                    "sheets and actual synthetic owner workflows."
                ),
                "Non-Void starting fixture; only declared low-Strain effect branches exercised.",
                "No living-campaign NPC publication adapter or live Discord deployment is implied.",
            ],
        )
        private_json(t.directory / "campaign-summary.json", summary)
        private_json(
            t.directory / "campaign-events.json", dict(events=self.events, snapshots=self.snapshots)
        )
        private_json(t.directory / "gm-ruling-packets.json", dict(rulings=self.rulings))
        private_json(
            t.directory / "gm-blind-requests.json",
            dict(
                requests=[
                    dict(sample_id=f"gm-{i + 1}", packet=r["request"])
                    for i, r in enumerate(self.rulings)
                ]
            ),
        )
        private_json(t.directory / "handler-packets.json", dict(audits=self.role_audits))
        transcript = t.directory / "campaign-transcript.md"
        transcript.write_text(
            (
                "# Synthetic campaign transcript\n\nFixture decisions; actual "
                "native consumers. No external model.\n\n"
            )
            + "\n\n".join(
                f"- **{p['name']} / {p['callsign']}**: {p['voice']} Goal: {p['goal']}"
                for p in CAST.values()
            )
            + "\n\n"
            + "\n\n".join(self.transcript)
            + "\n"
        )
        transcript.chmod(0o600)
        t.save()
        return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--chat-turns", type=int, default=24, choices=range(2, 101))
    args = parser.parse_args()
    trial = Trial(
        args.directory,
        create=True,
        brief={
            "scope": (
                "Simulation only: public approaches, no forced entry and no "
                "authority over another pilot's choices."
            )
        },
    )
    campaign = Campaign(trial, chat_count=args.chat_turns)
    try:
        summary = campaign.run()
        from test_m2_game import state

        frozen = state(trial.game).model_dump_json()
        last_viewer, last_command, last_result = campaign.replays[-1]
        with trial.store.engine.connect() as c:
            import sqlalchemy as sa

            from girlframe.database import tables as tables

            event_count = c.scalar(sa.select(sa.func.count()).select_from(tables.events))
    except Exception as error:
        private_json(
            trial.directory / "campaign-partial.json",
            dict(
                complete=False,
                input=campaign.number,
                mission=campaign.current_mission,
                phase=campaign.current_phase,
                error_type=type(error).__name__,
                error=str(error),
                events=campaign.events,
                rulings=campaign.rulings,
                transcript=campaign.transcript,
            ),
        )
        raise
    finally:
        trial.close()
    reopened = Trial(args.directory)
    try:
        Campaign(reopened, chat_count=args.chat_turns)
        assert reopened.scene_channel == campaign.channel
        assert state(reopened.game).model_dump_json() == frozen
        assert reopened.session.submit(last_viewer, reopened.scene, last_command) == last_result
        for owner, key, identity, result in campaign.proofs[-2:]:
            assert reopened.session.outcomes.confirm(owner, key, reopened.scene, identity) == result
        assert state(reopened.game).model_dump_json() == frozen
        with reopened.store.engine.connect() as c:
            assert c.scalar(sa.select(sa.func.count()).select_from(tables.events)) == event_count
        summary["database_reopen_replay"] = (
            "Same canon, contributions and native confirmations; no new events."
        )
        private_json(reopened.directory / "campaign-summary.json", summary)
    finally:
        reopened.close()
    print(
        json.dumps(
            {
                k: v
                for k, v in summary.items()
                if k not in ("contextual_rulings", "missions", "periods", "heat_spending")
            },
            indent=2,
        )
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
