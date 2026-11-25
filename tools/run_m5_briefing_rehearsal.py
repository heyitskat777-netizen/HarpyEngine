"""Run one synthetic Session Zero and mission on the actual Activity services."""

import argparse
import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

import pytest
from p2_trial_runtime import ROOT
from run_p2_session_trials import SceneTrial
from test_activity_shadow_readiness import configure, opt
from test_ai_mission_briefing import FakeGateway, enable
from test_campaign_opening import agree, complete
from test_director_activity_scene import P2Scene, input_command
from test_director_observation import Clock
from test_handler_creation import agree as agree_handler
from test_handler_creation import complete as handler_draft
from test_handler_creation import ready as ready_handler
from test_handler_creation import save as save_handler
from test_ledger import ADMIN, OTHER, PLAYER, ledger
from test_m2_game import Gateway, state, tick
from test_m4_completion import learn_in_opening, with_canon
from test_punishment_service import submit
from test_session_zero import FACILITATOR, OUTSIDE, PROFILE, approve

from girlframe.ai.briefing import DraftText
from girlframe.ai.conversation import ConversationReply, HandlerNeedProposal
from girlframe.ai.gm_outcomes import HandlerOutcome
from girlframe.delivery.m2_worker import GameWorker
from girlframe.engine.m3_handler_play_state import Effect
from girlframe.engine.m3_handler_state import HandlerNotes
from girlframe.engine.m3_missions import MissionTerms
from girlframe.engine.m3_punishments import Details
from girlframe.services.director_context import DirectorContextService
from girlframe.services.director_conversation import DirectorConversationService
from girlframe.services.director_observation import DirectorObservationService
from girlframe.services.director_session import DirectorSessionService
from girlframe.services.m3_handler_plays import HandlerPlayService
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_punishments import PunishmentService
from girlframe.services.session_zero import SessionZeroService

PILOTS = {"Lark": PLAYER, "Kite": OTHER}
GOALS = "Practice a clear stop signal and deliver a charged battery without breaching the relay."
FACT = "The marked service shelf is outside the relay's sealed service door."
OBJECTIVE = "Deliver a charged battery to the relay's marked external service shelf."
SCOPE = "Use the marked lane and outside shelf. Forced entry is not authorised."
COMPLETION = "Both Pilots report the battery at the marked outside shelf with the clips closed."
CAPACITY = "I can watch the stripe or keep my grip steady. I can't do both."
INDIRECT = "I'd rather hear the agreed boundary before we touch anything."
UNSELECTED = "The depot has one unused yellow practice strap."
PRIVATE = "Facilitator note: the old bell housing is empty."


@dataclass(frozen=True)
class MissionBrief:
    goals: str = GOALS
    fact: str = FACT
    objective: str = OBJECTIVE
    scope: str = SCOPE
    completion: str = COMPLETION


RELAY_BRIEF = MissionBrief()


class BriefingFixture(FakeGateway):
    def __init__(self, brief=RELAY_BRIEF):
        super().__init__()
        self.brief = brief

    def generate(self, model, context, request_id):
        generated = super().generate(model, context, request_id)
        assert context.introductory and context.difficulty == "narrative"
        assert context.goals == self.brief.goals
        assert [fact.statement for fact in context.facts] == [self.brief.fact]
        proposal = DraftText(
            objective=self.brief.objective,
            hard_stake=None,
            fact_ids=tuple(fact.id for fact in context.facts),
            terms=MissionTerms(scope=self.brief.scope, completion=self.brief.completion),
        )
        return generated.model_copy(update={"proposal": proposal})


class AnwenFixture:
    """Authored dialogue. The engine decides when a draft can be requested."""

    def __init__(self):
        self.packets = []

    def respond(self, request):
        self.packets.append(request.model_dump(mode="json"))
        decision = request.response_need
        assert decision is not None and decision.action == "RESPOND"
        profile = request.playbook_profile
        assert profile is not None and request.character_notes is not None
        frantic = profile.playbook == "Frantic"
        assert request.character_notes.voice
        action, offer = None, None
        refs = {
            ref.topic: ref.id
            for ref in request.context.references
            if ref.source_id.startswith("mission:")
        }
        references = decision.source_refs
        if decision.reason == "scope_boundary":
            if frantic:
                text = "Door stays shut. Case down a second. I'll call the long way round."
                action = "I put the other radio down mid-sentence and drag the route map closer."
            else:
                text = (
                    "Lark, I hear you about the corner. Leave the door. "
                    "Let's take the marked lane on your count."
                )
                action = "I trace the longer route on my copy of the map."
                offer = "brief"
        elif decision.reason == "reviewed_character_cue":
            text = "One job at a time. Keep your grip. I'll take the count off your hands."
            action = "I set the spare checklist aside and ready my handset."
        elif decision.reason == "reviewed_indirect_request":
            references = (refs["scope"],)
            text = (
                "Kite, lane and outside shelf. Door stays shut. Sorry, I was only on Lark's radio."
                if frantic
                else "Kite, I should have told you too. Take the marked lane to the outside shelf. "
                "The door stays shut."
            )
        elif "objective" in request.question.lower():
            references = (refs["objective"],)
            if any(
                "unlabelled" in line.text or "bracket" in line.text for line in request.recent_comms
            ):
                text = (
                    "Marked shelf. Leave the bracket clear. That's your drop."
                    if frantic
                    else "The shelf with your stripe. I heard you about the bracket. "
                    "Leave that one clear."
                )
            else:
                text = (
                    "Charged case, marked outside shelf. One job."
                    if frantic
                    else "Take it to the outside shelf with your stripe. "
                    "Tell me if you need a stop."
                )
        elif "scope" in request.question.lower():
            references = (refs["scope"],)
            text = (
                "Outside shelf, yes. Door, no. Put it down if the route closes."
                if frantic
                else "The outside shelf is within the boundary. "
                "If it looks blocked, set the case down and tell me."
            )
        elif "status" in request.question.lower():
            heard = tuple(line.text for line in request.recent_comms)
            assert any("case is on the shelf" in line for line in heard)
            assert any("Both clips still closed" in line for line in heard)
            references = (refs["completion"],)
            text = (
                "Case down, clips shut. I heard you both. The relay's still unchecked."
                if frantic
                else "I heard both of you. The case is on the shelf with the clips shut. "
                "We'll leave whether the relay works for the next check."
            )
        else:
            text = "Say that again. I want to make sure I heard you."
        return ConversationReply(
            route="handler",
            provider="reviewed-handler-v1",
            disposition="answer" if references else "clarification",
            text=text,
            handler_action=action,
            handler_play_offer=offer,
            source_refs=references,
        )


class Rehearsal:
    def __init__(self, store, playbook, *, brief=RELAY_BRIEF, notes=None):
        self.store = store
        self.playbook = playbook
        self.brief = brief
        creation, self.game = ready_handler(store)
        approval = store.policy.m3_approval
        assert approval is not None
        store.policy = store.policy.model_copy(
            update={
                "m3_approval": approval.model_copy(
                    update={"subsystems": approval.subsystems | {"plays"}}
                ),
            }
        )
        notes = notes or HandlerNotes(
            voice="Name the person first. Give choices room."
            if playbook == "Advocate"
            else "Short sentences, often mid-task.",
            intervention="Clear room for a Pilot to speak."
            if playbook == "Advocate"
            else "Take one competing task off their hands.",
        )
        draft = handler_draft(creation, playbook).model_copy(
            update={"name": "Anwen", "notes": notes}
        )
        save_handler(creation, draft)
        agree_handler(creation)
        sheet = creation.view(ADMIN)
        creation.activate(
            ADMIN, "activate-trial-handler", sheet["revision"], sheet["game_revision"], True
        )
        self.missions = MissionService(store)
        self.worker, self.gateway, self.dice = GameWorker(self.game), Gateway(), self.game.dice
        self.clock = store.clock = Clock()
        self.game.close_scene(ADMIN, "close-setup", 900)
        self.canon = with_canon(store)
        self.provider, self.persona, self.counts = BriefingFixture(brief), AnwenFixture(), Counter()
        self.scene_channel, self.role = 901, "gm"
        self.connect()
        self.table = SceneTrial(self)
        self.buffer = {}

    def connect(self):
        self.observer = DirectorObservationService(self.store, synthetic=True, activity_shadow=True)
        self.observer.game = self.game
        self.context = DirectorContextService(self.observer)
        conversation = DirectorConversationService(
            self.context, handler=self.persona, handler_mode="reviewed"
        )
        self.session = DirectorSessionService(self.context, conversation=conversation)
        self.app = P2Scene(self.session, briefing_gateway=self.provider)

    @staticmethod
    def viewers():
        return {"lark": PLAYER, "kite": OTHER, "handler": ADMIN, "gm": ADMIN}

    def tick(self, count=5):
        tick(self.worker, self.gateway, count)

    def remember(self, source, roles, topic="general"):
        with self.store.engine.connect() as c:
            actors = tuple(
                self.observer._authorize_input(
                    c, self.viewers()[role], self.scene, "handler" if role == "handler" else "pilot"
                )[2]
                for role in roles
            )
            order = len(self.context._references(c, self.scene))
        self.context.record(
            ADMIN, str(uuid4()), self.scene, source, order, known_by=actors, topic=topic
        )

    def join(self, scene, label):
        self.scene = scene
        for actor in (ADMIN, PLAYER, OTHER):
            self.game.join_scene(actor, f"join:{label}:{actor.user_id}", self.scene_channel)
        configure(self.app, scene)

    def setup(self, *, facilitator=None):
        zero = SessionZeroService(self.store)
        zero.set_group(ADMIN, "start-group", 0, (1, 2, 3))
        zero.propose(
            PLAYER,
            "session-zero-appoint",
            1,
            PROFILE.model_copy(update={"control": "ai", "archetype": self.playbook}),
        )
        approve(zero, zero.view(PLAYER)["proposal"])
        for pilot in (PLAYER, OTHER):
            zero.attach(pilot, f"attach:{pilot.user_id}", zero.view(pilot)["revision"])
        zero.goals(
            ADMIN,
            "goals",
            zero.view(ADMIN)["revision"],
            self.brief.goals,
            "narrative",
            facilitator=facilitator,
        )
        agree(zero)
        complete(zero)
        opening = zero.view(ADMIN)["opening"]
        self.scene = opening["scene"]
        assert opening["handler_control"] == "ai"
        opt(self.app, self.scene)
        self.table.append("Handler · Anwen", "Session Zero opening", opening["introduction"])
        selected = learn_in_opening(self.canon, self.brief.fact, "opening-fact")
        learn_in_opening(self.canon, UNSELECTED, "strap")
        window = self.canon.window(FACILITATOR, 901, facilitator=True)
        self.canon.establish(FACILITATOR, "private-world", window, PRIVATE)
        enable(self.store)
        before = state(self.game)
        key, payload = str(uuid4()), {"facts": [selected]}
        request = self.app.write(ADMIN, key, self.scene, "mission-briefing-queue", payload)
        assert self.app.write(ADMIN, key, self.scene, "mission-briefing-queue", payload) == request
        self.store.engine.dispose()
        result = self.app.write(ADMIN, "run-briefing", self.scene, "mission-briefing-run", request)
        assert result["status"] == "ready"
        assert (
            self.app.write(ADMIN, "retry-briefing", self.scene, "mission-briefing-run", request)
            == result
        )
        assert len(self.provider.calls) == 1 and not self.missions.list(PLAYER)
        approved = self.app.write(
            FACILITATOR,
            "approve-briefing",
            self.scene,
            "mission-briefing-review",
            {"id": request["id"], "result": result["result_id"], "approve": True},
        )
        assert state(self.game) == before and approved["status"] == "approved"
        self.table.append(
            "Facilitator", "private OOC review", f"Approved the exact draft. {self.brief.objective}"
        )
        return zero, approved["briefing_draft"]

    def dispatch(self, zero, approved):
        for day in (1, 2):
            zero.advance_opening(ADMIN, f"day:{day}", zero.view(ADMIN)["opening_anchor"])
        zero.advance_opening(ADMIN, "day:3", zero.view(ADMIN)["opening_anchor"])
        payload = {"briefing_draft": approved, "pilots": [str(x.user_id) for x in PILOTS.values()]}
        sent = self.app.write(ADMIN, "offer", self.scene, "mission-briefing-offer", payload)
        assert self.app.write(ADMIN, "offer", self.scene, "mission-briefing-offer", payload) == sent
        assert not self.missions.list(OUTSIDE)
        accepted = sent
        for label, pilot in PILOTS.items():
            assert self.missions.get(pilot, sent["id"])["briefing"] == [
                {"statement": self.brief.fact, "status": "current"}
            ]
            accepted = self.missions.respond(
                pilot, f"accept:{label}", sent["id"], accepted["revision"], "accept"
            )
            self.table.append(label, "native Inbox choice", "Accepted the mission invitation.")
        mission = self.missions.start(ADMIN, "dispatch", sent["id"], accepted["revision"])
        self.join(mission["scene"], "mission")
        terms = self.missions.get(PLAYER, sent["id"])["mission"]["briefing_terms"]
        assert terms == {"scope": self.brief.scope, "completion": self.brief.completion}
        with self.store.engine.connect() as c:
            scoped = self.context._handler_for_request(c, PLAYER, self.scene)
            assert {ref.topic: ref.text for ref in scoped.references} == {
                "objective": self.brief.objective,
                "scope": self.brief.scope,
                "completion": self.brief.completion,
            }
        self.table.append("Mission briefing", "approved shared fiction", self.brief.objective)
        self.table.append("Mission briefing", "approved shared boundary", self.brief.scope)
        return mission

    def talk(self, number, line):
        who, channel, text = line.split("|", 2)
        self.table.number, self.table.input_text = number, text
        actor = PILOTS[who]
        command = input_command(self.observer, actor, self.scene, f"turn:{number}", text, channel)
        sent = self.app.submit(actor, self.scene, command)
        source = sent["input"]["source_id"]
        assert "conversation" not in sent
        if number in (9, 33):
            assert self.app.submit(actor, self.scene, command) == sent
            self.counts["input_replays"] += 1
        self.buffer[source] = (number, line, source)
        self.clock.now += 4

    def route_turn(self, number, line, source):
        who, channel, text = line.split("|", 2)
        self.table.number, self.table.input_text = number, text
        actor = PILOTS[who]
        before = state(self.game)
        if text.startswith("GM,"):
            origin = "private GM request"
        else:
            origin = "private player input" if channel == "private" else "player input"
        self.table.append(who, origin, text)
        cue = "capacity" if number == 21 and self.playbook == "Frantic" else None
        if cue or number == 28:
            conv = self.session.conversation
            key = f"need:{number}"
            opened = conv.open_handler_need(ADMIN, key, self.scene, source)
            quote = CAPACITY if cue else INDIRECT
            proposal = HandlerNeedProposal(
                request_id=opened["id"],
                action="RESPOND",
                kind="character_cue" if cue else "indirect_request",
                speech_quote=quote,
                cue=cue,
                reason="Someone can use a short reply grounded in what was said.",
            )
            draft = conv.propose_handler_need(
                ADMIN, key + ":proposal", self.scene, opened["id"], proposal
            )
            conv.review_handler_need(
                ADMIN, key + ":review", self.scene, draft["id"], "approve", "Heard and relevant."
            )
        if channel == "private":
            with self.store.engine.connect() as c:
                request, _ = self.session.conversation._requests(c, actor, self.scene, source, "gm")
            assert "violet lantern" in request.model_dump_json()
        bundle = self.session.conversation.process_message(
            actor, f"route:{number}", self.scene, source, 1
        )
        assert state(self.game) == before
        reply = bundle["gm"]["reply"]
        self.table.review_id = bundle["gm"].get("play_review_id")
        if reply["gm_decision"]["action"] == "RESPOND":
            self.table.append("GM (OOC)", reply["gm_decision"]["reason"], reply["text"])
            if number == 35:
                assert reply["gm_rule"]["status"] == "no_cost"
                assert all(
                    "spend any Heat?" not in row["text"]
                    for row in self.app.timeline(actor, self.scene)["entries"]
                )
            self.counts["gm_responses"] += 1
        decision = bundle["handler_decision"]["decision"]
        if channel == "private":
            assert decision["action"] == "WAIT"
        self.counts[decision["action"]] += 1
        if bundle["handler"]:
            assert decision["action"] == "RESPOND" and bundle["handler"]["reply"] is None
            draft = bundle["handler"]["id"]
            with self.store.engine.connect() as c:
                recipient = self.observer._authorize_input(c, actor, self.scene, "pilot")[2]
            self.app.approve_handler(
                ADMIN, f"review:{number}", self.scene, draft, "Scoped reply.", (recipient,)
            )
            key = f"delivery:{number}"
            entry = self.app.deliver_handler(ADMIN, key, self.scene, draft)
            assert self.app.deliver_handler(ADMIN, key, self.scene, draft) == entry
            rows = self.app.timeline(actor, self.scene)["entries"]
            heard = next(row for row in rows if row["id"] == entry["id"])
            text = heard["text"]
            self.table.append(
                "Handler · Anwen",
                decision["reason"],
                text,
                recipients=who,
                action=heard.get("action"),
            )
            self.counts["handler_actions"] += bool(heard.get("action"))
            peer = OTHER if actor == PLAYER else PLAYER
            assert entry["id"] not in {
                row["id"] for row in self.app.timeline(peer, self.scene)["entries"]
            }
            self.counts["private_deliveries"] += 1
            self.counts[decision["reason"]] += 1
            if number == 27 and self.playbook == "Advocate":
                grant = self.session.conversation.start_handler_brief(
                    ADMIN, self.scene, draft, state(self.game).revision
                )
                self.table.consume(
                    "handler_grant",
                    grant["id"],
                    HandlerOutcome(
                        play="brief",
                        effect=Effect(
                            kind="brief",
                            account=text.removeprefix("Reported claim: ").split("\n", 1)[0],
                        ),
                    ),
                )
                assert (
                    HandlerPlayService(self.store).notice(actor, grant["id"])["state"] == "complete"
                )
                self.counts["handler_plays"] += 1
        if number in (29, 49):
            trait, expected, goal = (
                ("in_control", True, "hold the level case")
                if number == 29
                else ("desperate", False, "keep the warning flag absolutely still")
            )
            ruling = (
                "Lark braces her knee under the case and holds it level long enough to reset."
                if expected
                else "The warning flag still flaps. Lark cannot hold it absolutely steady."
            )
            assert self.table.keep((number, (4, 5), trait, goal), narration=ruling) == expected
            self.counts["native_plays"] += 1

    def batch(self):
        self.clock.now += 121
        receipt = self.app.shadow.process(ADMIN, self.scene)
        if receipt is None:
            return
        assert receipt["reason"] in ("quiet", "completed_play")
        self.counts["reviewed_batches"] += 1
        (batch,) = self.app.shadow.records(ADMIN, self.scene, run_id=receipt["run"])
        for record in batch["items"]:
            queued = self.buffer.pop(record["source"], None)
            if queued is not None:
                self.route_turn(*queued)

    def run(self, lines):
        zero, approved = self.setup()
        for number, line in enumerate(lines[:8], 1):
            who, channel, text = line.split("|", 2)
            self.table.number = number
            kind = "private opening note" if channel == "private" else "opening roleplay fixture"
            self.table.append(who, kind, text)
        mission = self.dispatch(zero, approved)
        for number, line in enumerate(lines[8:], 9):
            self.talk(number, line)
            if number == 32:
                self.store.engine.dispose()
                self.connect()
                self.counts["restarts"] += 1
            if number in (16, 23, 27, 29, 32, 35, 40, 46, 49, 56, 59, 64):
                self.batch()
        self.batch()
        assert not self.buffer
        status = self.observer.status(ADMIN, self.scene)
        assert (status.pending_messages, status.pending_triggers) == (0, 0)
        assert (
            self.counts["RESPOND"] == self.counts["private_deliveries"] == len(self.persona.packets)
        )
        assert self.counts["RESPOND"] + self.counts["WAIT"] == len(lines) - 8
        assert self.counts["native_plays"] == self.dice.calls == len(self.table.actions) == 2
        packets = json.dumps(self.persona.packets)
        assert "violet lantern" not in packets and PRIVATE not in packets
        assert "spend any Heat?" not in packets
        final = self.missions.end(
            ADMIN,
            "end",
            mission["id"],
            mission["revision"],
            True,
            debrief=(
                "The battery reached the marked shelf. The sealed door and the clips stayed closed."
            ),
        )
        if final["phase"] == "awaiting_consequences":
            discipline = PunishmentService(self.store, self.missions.access.registry)
            for item in self.missions.get(ADMIN, mission["id"])["work"]:
                submit(
                    discipline,
                    ADMIN,
                    item["id"],
                    Details(kind="stimulant_injection"),
                    "dog-discipline",
                )
                self.table.append(
                    "Handler controller",
                    "native required consequence",
                    "The controller resolved the Dog's required discipline through the Inbox.",
                )
            final = self.missions.complete(ADMIN, "advance", mission["id"], final["revision"])
        assert final["phase"] == "complete"
        self.table.append(
            "Mission controller", "native close", "Debrief filed. The mission is complete."
        )
        assert self.counts["reviewed_indirect_request"] == 1
        assert self.counts["reviewed_character_cue"] == (1 if self.playbook == "Frantic" else 0)
        return self.counts, self.table.rows


def render(playbook, counts, rows):
    lines = [
        f"# {playbook} synthetic relay rehearsal",
        "",
        "Authored player and Handler dialogue in a disposable HarpyEngine database. "
        "The facilitator approved drafts. The engine governed choices, rolls, and outcomes.",
        "",
        "## Session Zero and outcome",
        "",
        f"- Narrative difficulty, two Pilots, and Anwen as an AI-reviewed {playbook}.",
        f"- The agreed goal was to {GOALS[0].lower() + GOALS[1:]}",
        "- The briefing fixture received one selected fact. The facilitator approved the exact "
        "objective. Both Pilots answered separately in their native Inbox.",
        f"- {counts['RESPOND'] + counts['WAIT']} engine-routed player turns after eight opening "
        "roleplay lines, "
        f"{counts['RESPOND']} reviewed Handler deliveries, "
        f"{counts['WAIT']} WAIT decisions, {counts['gm_responses']} direct GM replies, "
        f"and {counts['native_plays']} native rolls. The first mission reached Complete.",
        f"- Anwen took {counts['handler_actions']} in-character "
        f"{'action' if counts['handler_actions'] == 1 else 'actions'}. The controller confirmed "
        f"{counts['handler_plays']} optional native Handler "
        f"{'Play' if counts['handler_plays'] == 1 else 'Plays'}.",
        f"- {counts['reviewed_batches']} private observation batches, "
        f"{counts['input_replays']} exact input replays, and {counts['restarts']} mid-scene "
        "database reopen. The final review queue was empty.",
        "- The GM saw the private lantern sighting. The Handler's packets excluded it and "
        "the facilitator-only note. Both invitees received the shelf fact in the native offer.",
        "- The two Keep Your Head rolls were both 9. Lark chose **tough** and **in control** "
        "as positive traits and **desperate** as negative. The authored facilitator ruling "
        "accepted a stable brace for the case and rejected absolute precision for the flag. "
        "The engine validated and applied each owned ruling.",
        "- The private GM answer at turn 35 confirmed that asking Kite to stop spends nothing. "
        "It stayed out of the fiction and the Handler's packet.",
        "- The briefing fixture reported 125 synthetic input and 45 synthetic output tokens. "
        "Hosted calls totaled zero.",
        "",
        "## Annotated transcript",
        "",
        "Numbers identify player inputs and the associated turns and workflow records.",
        "",
    ]
    for row in rows:
        recipient = f" to {row['recipients']}" if row.get("recipients") else ""
        prefix = f"{row['input_number']:02d}" if row["input_number"] else "Setup"
        text = row["text"].replace("\n", " ")
        if row.get("action"):
            text += f" *{row['action']}*"
        lines.extend((f"**{prefix} · {row['speaker']}{recipient}** ({row['origin']}) — {text}", ""))
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    dialogue = (ROOT / "tools" / "fixtures" / "m5_relay_dialogue.txt").read_text().splitlines()
    reports = []
    for playbook in ("Advocate", "Frantic"):
        with (
            TemporaryDirectory(prefix="harpy-m5-briefing-") as temp,
            pytest.MonkeyPatch.context() as patch,
        ):
            fixture = ledger.__wrapped__(Path(temp), patch)
            try:
                counts, rows = Rehearsal(next(fixture), playbook).run(dialogue)
                reports.append(render(playbook, counts, rows))
                print(playbook, json.dumps(dict(counts), sort_keys=True))
            finally:
                fixture.close()
    args.output.write_text("\n\n".join(reports))


if __name__ == "__main__":
    main()
