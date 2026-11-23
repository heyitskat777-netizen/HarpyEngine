"""Matched synthetic player choices across a mission, Off-Duty and the next mission."""

import argparse
import json
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from run_m5_memory_campaign import MemoryCampaign
from run_m5_model_campaign import Campaign
from run_m5_model_missions import ledger, write_json
from run_m5_relationship_rehearsal import save_pressure
from test_activity_shadow_readiness import publish_opening, review, submission
from test_director_continuity import carry
from test_ledger import ADMIN, OTHER, PLAYER
from test_m2_game import state
from test_m5_activity_pilots import PLOVER, confirm_term, pilot_review
from test_p2_mission_cycle import launch

from girlframe.ai.director_dossiers import PressurePlan
from girlframe.ai.director_fronts import FrontDraft, FrontEvidence, FrontMove
from girlframe.engine.m3_world_development import Subject
from girlframe.scenes.campaign_time import Anchor, Cut, Position
from girlframe.services.director_fronts import DirectorFrontService
from girlframe.services.director_time import scene_time

OFFER = (
    "I can give up my first break to load the cart. "
    "Will you make room for it? Tell me before you sign."
)
OPTIONS = {
    "cart": (
        "I'll leave room for the cart on the early lift. You can load it after my check-in.",
        "Save me a place by the ramp at check-in. I can miss breakfast once. "
        "Let's ask the next watch to load their own gear tomorrow.",
        "Will you meet me by the ramp after your check-in? I'll bring the cart. "
        "Next time, let's put a loader on the sheet first.",
    ),
    "medical": (
        "I need the early lift for the medical bags. The cart has to wait. "
        "I can ask the quartermaster about the afternoon ramp.",
        "Keep the early lift for the bags. Ask about the afternoon ramp, and I'll get someone "
        "to cover the cart. I need my break if we're waiting that long.",
        "Before I put anything on the sheet, can you confirm whether the quartermaster offered "
        "the ramp? I can ask the next watch to collect the cart if she says no.",
    ),
}


class Conflict(MemoryCampaign):
    def move_day(self, day):
        cut = Cut(target=Anchor(chapter="Watch trials", position=Position(day=day, slot="morning")))
        preview = self.timeline.preview_cut(ADMIN, cut)
        self.timeline.commit_cut(ADMIN, f"day:{day}", cut, preview["token"])

    def line(self, key, text):
        _, source = submission(self.app, self.scene, PLAYER, key, text)
        self.add("Lark", "heard scene turn", text)
        return source

    def speak(self, beat, text, *, expected, tactic):
        def plan(packet):
            assert packet["callsign"] == "Plover"
            opportunity = packet.get("opportunity")
            assert opportunity and "Private dispatcher notes" not in json.dumps(packet)
            return {
                "kind": "ADDRESS",
                "recipients": [self.lark.model_dump(mode="json")],
                "intent": {
                    "tactic": tactic,
                    "if_refused": "try_elsewhere",
                    "move_id": opportunity["id"],
                },
            }

        def draft(packet):
            refs = packet["dossier"]["context"]["references"]
            assert packet["intent"]["tactic"] == tactic
            assert all(any(snippet in ref["text"] for ref in refs) for snippet in expected)
            if beat != "first-mission":
                assert packet["dossier"]["state"]["terms"][0]["text"] == OFFER
                assert any(
                    row["text"] == OFFER and row["carried"]
                    for row in packet["recent_contributions"]
                )
            self.samples.append({"beat": beat, "packet": packet})
            write_json(self.output / "samples.json", self.samples)
            # Offers and requests change what is on the table. They assert no completed action.
            return {"kind": "DIALOGUE", "text": text, "source_refs": []}

        self.pilot.audience_answer, self.pilot.answer = plan, draft
        fixture = self.pilot.client._post

        def capture(request, timeout):
            body = json.loads(request.data)
            wire = json.loads(body["input"][1]["content"])
            if wire["contract"]["title"] == "ActivityPilotDecision":
                write_json(
                    self.output / f"voice-{beat}.json",
                    {
                        "instructions": body["input"][0]["content"],
                        **wire,
                    },
                )
            return fixture(request, timeout)

        before = state(self.game)
        with self.store.engine.connect() as c:
            time = scene_time(c, self.store.campaign_id, self.scene)
        self.clock.now += 120
        self.pilot.client._post = capture
        try:
            outcome = review(self.app, self.scene)["model_outcome"]
        finally:
            self.pilot.client._post = fixture
        assert outcome["status"] == "pilot_review", outcome
        request = {"proposal": outcome["proposal_id"]}
        pilot_review(self.app, self.scene, request["proposal"], self.lark.model_dump(mode="json"))
        sent = self.app.write(OTHER, f"speak:{beat}", self.scene, "npc-deliver", request)
        assert self.app.write(OTHER, f"speak:{beat}", self.scene, "npc-deliver", request) == sent
        assert not sent["effects_applied"] and state(self.game) == before
        with self.store.engine.connect() as c:
            assert scene_time(c, self.store.campaign_id, self.scene) == time
        heard = self.app.npc_delivery.hearing(ADMIN, self.scene, sent["id"])
        assert heard["recipients"] == [self.lark.model_dump(mode="json")]
        self.add("Plover", "approved dialogue", heard["text"])
        return sent["reference"]

    def run_branch(self, branch):
        self.samples = []
        self.prepare_native()
        self.name = "Dispatch bench"
        publish_opening(self.app, self.scene, ADMIN, location=self.name)
        lift = (
            "The early lift has room for the cart or the medical bags. The afternoon ramp may open."
        )
        origin = self.scene
        lift_ref = self.record_source("lift", self.line("lift", lift))
        save_pressure(
            self.app,
            self.scene,
            PLOVER,
            "Get the next watch's cart up from the yard.",
            PressurePlan(
                stake="The next watch needs tools.", next_step="Ask Lark who needs the lift."
            ),
            evidence=(lift_ref,),
        )
        target = Subject(kind="npc", id=PLOVER.entity)
        cite = FrontEvidence(kind="reference", id=lift_ref)
        move = FrontMove(
            id="work-out-loading",
            subject=target,
            portrayed_by=PLOVER,
            text=(
                "Ask Lark before she signs for the lift. "
                "If she needs it, negotiate another route or loader."
            ),
            evidence_refs=(cite,),
        )
        DirectorFrontService(self.context).save(
            ADMIN,
            "lift-front",
            self.scene,
            state(self.game).revision,
            FrontDraft(
                key="one-lift",
                title="Private dispatcher notes",
                situation="Two loads and one lift.",
                fact_refs=(cite,),
                possible_moves=(move,),
            ),
        )
        self.close()

        self.move_day(5)
        self.name = "East yard mission"
        first = launch(self.missions, "yard", "Survey the East yard access.")
        self.open_scene(int(first["channel"]), self.name, "mission")
        self.approve_memory("pressure", origin, lift_ref)
        self.line("first-mission", "Before I sign, who can handle the loading?")
        offer = self.speak("first-mission", OFFER, expected=(lift,), tactic="offer")
        confirm_term(self.app, self.scene, PLOVER, self.lark, offer, OFFER)
        first_scene = self.scene
        decision, off_duty, next_mission = OPTIONS[branch]
        decision_ref = self.record_source("decision", self.line("player-decision", decision))
        Campaign.end(self, first, "yard")
        self.close()

        self.move_day(6)
        self.name = "Barracks during Off-Duty"
        self.open_scene(911, self.name, "off-duty")
        self.approve_memory("pressure", origin, lift_ref)
        carry(self.context, first_scene, self.scene, (offer, decision_ref), "off-duty-terms")
        self.line(
            "off-duty", "Before we turn in, what do you want me to put on tomorrow's handover?"
        )
        duty_scene = self.scene
        response = self.speak("off-duty", off_duty, expected=(decision,), tactic="counteroffer")
        self.close()
        self.play_off_duty()

        self.move_day(7)
        self.name = "West yard mission"
        second = launch(self.missions, "west", "Inspect the West yard access.")
        self.open_scene(int(second.get("channel", 912)), self.name, "mission")
        self.restart()
        self.approve_memory("pressure", origin, lift_ref)
        carry(self.context, duty_scene, self.scene, (response,), "last-offer")
        carry(self.context, first_scene, self.scene, (offer, decision_ref), "next-mission-terms")
        self.line("next-mission", "We've got a minute before watch. What needs settling?")
        self.speak("next-mission", next_mission, expected=(decision, off_duty), tactic="ask")
        Campaign.end(self, second, "west")
        self.close()
        write_json(self.output / "transcript.json", self.transcript)
        write_json(
            self.output / "result.json",
            {
                "branch": branch,
                "lifecycle": self.archive,
                "scene_count": 3,
                "approved_dialogue": 3,
                "service_restarts": self.restarts,
            },
        )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("branch", choices=OPTIONS)
    args = parser.parse_args()
    args.output.mkdir(mode=0o700, parents=True)
    with (
        TemporaryDirectory(prefix="harpy-conflict-") as directory,
        pytest.MonkeyPatch.context() as patch,
    ):
        resources = ledger.__wrapped__(Path(directory), patch)
        try:
            Conflict(next(resources), args.output).run_branch(args.branch)
        finally:
            resources.close()


if __name__ == "__main__":
    main()
