"""Two consented Fronts from one exact disposable campaign checkpoint."""

import argparse
import json
import sqlite3
from contextlib import closing
from copy import copy
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
import sqlalchemy as sa
from run_m5_conflict_rehearsal import Conflict
from run_m5_model_campaign import Campaign
from run_m5_model_missions import ledger, write_json
from test_activity_shadow_readiness import publish_opening, review, submission
from test_director_continuity import carry
from test_ledger import ADMIN, OTHER, PLAYER
from test_m2_game import state
from test_m5_activity_pilots import NPC, PLOVER, pilot_review
from test_p2_mission_cycle import launch

from girlframe.ai.director_fronts import (
    FrontDraft,
    FrontEvidence,
    FrontMove,
    FrontParticipant,
    MissionMoveTrigger,
    PreparationTrigger,
)
from girlframe.ai.knowledge import Acquisition, Disclosure, KnowledgeProposal
from girlframe.database import tables as t
from girlframe.engine.m3_world_development import Subject
from girlframe.scenes.campaign_time import Anchor, Position
from girlframe.services.director_fronts import DirectorFrontService
from girlframe.services.m3_actors import ActorService
from girlframe.services.m3_cast import CastService
from girlframe.services.onboarding import WorkflowError

SITE = "Weather archive"
QUESTION = "The log is open. What are you doing about the echo?"
PRIVATE = "THE_NORTH_MARK_WAS_MOVED"
REPORT = "Dispatch thinks a spare recorder might be available. It would need the shared bench."
CLINIC = "The clinic's humidity reference needs a dry comparison label on the shared bench."
PREPARE = "Sketch a dry-reference label and ask the clinic to check it before using the bench."
OPTIONS = {
    "accepted": (
        "Plan a paired reading with the Pilot who accepted. Ask for dispatch before leaving.",
        "You said yes to the paired reading. Shall I put our names on a request for dispatch?",
    ),
    "closed:accept": (
        "Ask about permission for a repeat paired check, without claiming a new dispatch.",
        "The first survey is closed. Would you join another check if we can get it cleared?",
    ),
    "closed:decline": (
        "Offer to make a passive listening chart from the archive. Leave their other work open.",
        "You passed on the field survey. I can draw a listening chart here. "
        "Want a blank copy for your watch?",
    ),
    "allocated": ("Read back the existing dispatch before a survey.", "Dispatch went through."),
    "withdrawn": ("Set aside the withdrawn survey request.", "The survey was withdrawn."),
}


def checkpoint(source: Path, destination: Path) -> None:
    with closing(sqlite3.connect(source)) as before, closing(sqlite3.connect(destination)) as after:
        before.backup(after)


class Independent(Conflict):
    def evidence(self, key, text, listeners):
        src = self.line(key, text)
        with self.store.engine.connect() as c:
            order = len(self.context._references(c, self.scene))
        return self.context.record(
            ADMIN,
            key + ":reference",
            self.scene,
            src["source_id"],
            order,
            known_by=listeners,
        )["id"]

    def start_common(self):
        self.prepare_native()
        self.close()
        self.move_day(5)
        self.name = "Archive briefing"
        self.open_scene(910, SITE, "mission")
        self.origin = self.scene
        self.echo = self.evidence("echo-report", REPORT, (NPC, self.lark))
        self.clinic = self.evidence("clinic-report", CLINIC, (PLOVER, self.lark))
        _, private = submission(
            self.app, self.scene, PLAYER, "private-report", PRIVATE, channel="scene"
        )
        knowledge = self.app.session.knowledge
        request = knowledge.open(ADMIN, "classify-private", self.scene, private["source_id"])
        proposal = knowledge.propose(
            ADMIN,
            "propose-private",
            self.scene,
            request["id"],
            KnowledgeProposal(
                request_id=request["id"],
                disclosures=(Disclosure(quote=PRIVATE, recipients=(NPC,)),),
                updates=(Acquisition(basis="testimony", quote=PRIVATE, recipients=(NPC,)),),
            ),
        )
        self.private = knowledge.confirm(ADMIN, "approve-private", self.scene, proposal["id"])[
            "references"
        ][0]
        self.offer = self.missions.offer(ADMIN, "echo-invite", "Optional echo survey", (2, 3))
        fronts = DirectorFrontService(self.context)
        subject = Subject(kind="npc", id=NPC.entity)
        source = FrontEvidence(kind="reference", id=self.echo)
        fronts.save(
            ADMIN,
            "echo-front",
            self.scene,
            state(self.game).revision,
            FrontDraft(
                key="echo-survey",
                title="Private recorder assignment",
                situation="Test the echo.",
                fact_refs=(source,),
                participants=(FrontParticipant(subject=subject, objective_refs=(source,)),),
                possible_moves=tuple(
                    FrontMove(
                        id=access,
                        subject=subject,
                        text=value[0],
                        portrayed_by=NPC,
                        evidence_refs=(source,),
                        location=SITE,
                        trigger=MissionMoveTrigger(
                            offer=self.offer["id"],
                            participant=self.lark,
                            when=access.partition(":")[0],
                            answer=access.partition(":")[2] or None,
                        ),
                    )
                    for access, value in OPTIONS.items()
                ),
            ),
        )
        subject = Subject(kind="npc", id=PLOVER.entity)
        source = FrontEvidence(kind="reference", id=self.clinic)
        fronts.save(
            ADMIN,
            "clinic-front",
            self.scene,
            state(self.game).revision,
            FrontDraft(
                key="clinic-reference",
                title="Private clinic procedure",
                situation="Keep a dry reference.",
                fact_refs=(source,),
                participants=(FrontParticipant(subject=subject, resource_refs=(source,)),),
                possible_moves=(
                    FrontMove(
                        id="dry-label",
                        subject=subject,
                        text=PREPARE,
                        portrayed_by=PLOVER,
                        evidence_refs=(source,),
                        location=SITE,
                        trigger=PreparationTrigger(
                            earliest=Anchor(
                                chapter="Watch trials",
                                position=Position(day=6, slot="morning"),
                            )
                        ),
                    ),
                ),
            ),
        )
        waiting = self.app.read(ADMIN, self.scene, "gm-work")["next_plan"]
        assert waiting == {"status": "waiting", "reply_from": self.lark.model_dump(mode="json")}

    def prepare_offstage(self):
        self.move_day(6)
        self.name = "Off-Duty archive check"
        self.open_scene(911, SITE, "off-duty")
        cast = CastService(ActorService(self.missions))
        view = cast.view(OTHER, 911)
        cast.change(
            OTHER,
            "plover-offstage",
            911,
            view["game_revision"],
            view["cast_revision"],
            "withdraw",
            PLOVER,
        )
        publish_opening(self.app, self.scene, ADMIN, location=SITE)
        with self.store.engine.connect() as c:
            assert PLOVER not in self.app.session.knowledge._actors(
                c,
                self.app.session.observer._scene(c, self.scene),
            )
        assignment = self.app.read(OTHER, self.scene, "work")["next_plan"]
        assert assignment["status"] == "ready" and assignment["text"] == PREPARE
        assert self.app.read(PLAYER, self.scene, "work")["next_plan"]["status"] != "ready"
        before = self.timeline.projection(ADMIN)
        self.clock.now += 10 * 60 * 60
        self.restart()
        assert self.timeline.projection(ADMIN) == before
        assert review(self.app, self.scene) is None
        assert self.app.read(OTHER, self.scene, "work")["next_plan"] == assignment
        payload = {"move": assignment["id"], "decision": "prepare"}
        with pytest.raises(WorkflowError, match="STALE_FRONT_MOVE"):
            self.app.write(PLAYER, "wrong-preparation", self.scene, "front-preparation", payload)
        frozen = state(self.game)
        receipt = self.app.write(OTHER, "prepare-label", self.scene, "front-preparation", payload)
        assert (
            self.app.write(OTHER, "prepare-label", self.scene, "front-preparation", payload)
            == receipt
        )
        with pytest.raises(WorkflowError, match="STALE_FRONT_MOVE"):
            self.app.write(OTHER, "duplicate-label", self.scene, "front-preparation", payload)
        assert not receipt["effects_applied"] and state(self.game) == frozen
        self.close()
        self.play_off_duty()
        return receipt

    def draft(self, beat, expected_actor, *, wrong_claim=False):
        self.line(beat, QUESTION)
        self.clock.now += 120

        def plan(packet):
            actor = packet["dossier"]["actor"]
            assert actor == expected_actor.model_dump(mode="json")
            assert (PRIVATE in json.dumps(packet)) == (expected_actor == NPC)
            candidate = packet["opportunity"]
            return {
                "kind": "ADDRESS",
                "recipients": [self.lark.model_dump(mode="json")],
                "intent": {
                    "tactic": "offer",
                    "if_refused": "try_elsewhere",
                    "move_id": candidate["id"],
                },
            }

        def generate(packet):
            opportunity = packet["opportunity"]
            assert PRIVATE not in json.dumps(packet)
            access = opportunity.get("mission_access")
            if access:
                refs = packet["dossier"]["context"]["references"]
                assert any(
                    ref["classification"] == "reported_claim" and REPORT in ref["text"]
                    for ref in refs
                )
            text = (
                OPTIONS[f"closed:{opportunity['reply_answer']}" if access == "closed" else access][
                    1
                ]
                if access
                else ("I can leave a blank dry-reference label here for the clinic to check.")
            )
            return {
                "kind": "DIALOGUE",
                "text": text,
                "source_refs": [],
                **({"access_claim": "allocated" if wrong_claim else access} if access else {}),
            }

        self.pilot.audience_answer, self.pilot.answer = plan, generate
        fixture = self.pilot.client._post

        def capture(request, timeout):
            msg = json.loads(request.data)["input"]
            payload = json.loads(msg[1]["content"])
            if payload["contract"]["title"] == "ActivityPilotDecision" and not wrong_claim:
                write_json(
                    self.output / f"voice-{beat}.json",
                    {"instructions": msg[0]["content"], **payload},
                )
            return fixture(request, timeout)

        self.pilot.client._post = capture
        try:
            return review(self.app, self.scene)["model_outcome"]
        finally:
            self.pilot.client._post = fixture

    def deliver(self, name, proposal, *, approve=True):
        if approve:
            pilot_review(self.app, self.scene, proposal, self.lark.model_dump(mode="json"))
        request = {"proposal": proposal}
        sent = self.app.write(OTHER, "send:" + name, self.scene, "npc-deliver", request)
        assert self.app.write(OTHER, "retry:" + name, self.scene, "npc-deliver", request) == sent
        hearing = self.app.npc_delivery.hearing(ADMIN, self.scene, sent["id"])
        assert hearing["recipients"] == [self.lark.model_dump(mode="json")]
        self.add(name, "approved dialogue", hearing["text"])
        return sent

    def withhold_and_withdraw(self, outcome, db):
        self.store.engine.dispose()
        saved = db.with_name("before-draft.db")
        checkpoint(db, saved)
        false_claim = self.draft("false-claim", NPC, wrong_claim=True)
        assert (
            false_claim["status"] == "rejected" and false_claim["reason"] == "mission_access_scope"
        )
        self.store.engine.dispose()
        checkpoint(saved, db)
        self.restart()
        proposal = self.draft("pending-dispatch", NPC)
        assert proposal["status"] == "pilot_review", proposal
        request = {"proposal": proposal["proposal_id"]}
        pilot_review(self.app, self.scene, request["proposal"], self.lark.model_dump(mode="json"))
        self.store.engine.dispose()
        pending = db.with_name("pending.db")
        checkpoint(db, pending)
        with self.store.engine.connect() as c:
            report = next(
                ref for ref in self.context._references(c, self.scene) if ref.id == self.echo
            )
        submission(
            self.app,
            self.scene,
            PLAYER,
            "correct-recorder",
            "Dispatch has no spare recorder.",
            source_id=report.source_id,
            expected_source_revision=report.source_revision,
        )
        with pytest.raises(WorkflowError, match="STALE"):
            self.app.write(OTHER, "corrected-draft", self.scene, "npc-deliver", request)
        self.store.engine.dispose()
        checkpoint(pending, db)
        self.restart()
        self.missions.cancel(ADMIN, "cancel-while-pending", self.offer["id"], outcome["revision"])
        with pytest.raises(WorkflowError, match="STALE_FRONT_MOVE"):
            self.app.write(OTHER, "withdrawn-draft", self.scene, "npc-deliver", request)
        self.store.engine.dispose()
        checkpoint(saved, db)
        self.restart()

    def run_fork(self, answer, db):
        outcome = self.missions.respond(PLAYER, "survey-answer", self.offer["id"], 1, answer)
        anchor = self.timeline.projection(ADMIN)
        self.clock.now += 10 * 60 * 60
        self.restart()
        assert self.timeline.projection(ADMIN) == anchor
        with pytest.raises(WorkflowError, match="Every offered player must answer"):
            self.missions.start(
                ADMIN, "missing-other-answer", self.offer["id"], outcome["revision"]
            )
        with self.store.engine.connect() as c:
            active = self.missions._mission(c, self.offer["id"])
            assert active.responses == {str(PLAYER.user_id): answer} and not active.participants
            history = t.m3["m3_mission_history"]
            response_event = c.scalar(
                sa.select(history.c.event_id).where(
                    history.c.campaign_id == self.store.campaign_id,
                    history.c.id == active.id,
                    history.c.revision == active.revision,
                )
            )
            assert response_event
        if answer == "accept":
            self.withhold_and_withdraw(outcome, db)
        other = self.missions.respond(
            OTHER, "survey-other", self.offer["id"], outcome["revision"], "accept"
        )
        first = self.missions.start(
            ADMIN, "native-survey-dispatch", self.offer["id"], other["revision"]
        )
        with self.store.engine.connect() as c:
            actual = self.missions._mission(c, first["id"])
            assert actual.participants == ((2, 3) if answer == "accept" else (3,))
        if answer == "accept":
            result = self.draft("allocated", NPC)
            assert result["status"] == "pilot_review", result
        if first.get("channel") and int(first["channel"]) != self.scene_channel:
            self.game.close_scene(ADMIN, "close-native-opening", int(first["channel"]))
        Campaign.end(self, first, "survey")
        self.close()
        prepared = self.prepare_offstage()
        self.move_day(7)
        self.name = "Next archive mission"
        second = launch(self.missions, "second", "Inspect the weather archive perimeter seals.")
        self.open_scene(int(second.get("channel", 912)), SITE, "mission")
        carry(
            self.context,
            self.origin,
            self.scene,
            (self.echo, self.clinic, self.private),
            "carry-evidence",
        )
        frozen = state(self.game)
        plover = self.draft("clinic", PLOVER)
        assert plover["status"] == "pilot_review", plover
        self.deliver("Plover", plover["proposal_id"])
        proposal = self.draft("survey", NPC)
        assert proposal["status"] == "pilot_review", proposal
        request = {"proposal": proposal["proposal_id"]}
        with pytest.raises(WorkflowError, match="NPC_DELIVERY_REVIEW"):
            self.app.write(OTHER, "unreviewed-survey", self.scene, "npc-deliver", request)
        pilot_review(self.app, self.scene, request["proposal"], self.lark.model_dump(mode="json"))
        self.restart()
        self.deliver("Tern", request["proposal"], approve=False)
        assert state(self.game) == frozen and all(
            PRIVATE not in json.dumps(x) for x in self.handler.calls
        )
        assert review(self.app, self.scene) is None
        assert (
            self.app.read(ADMIN, self.scene, "gm-work")["next_plan"]["status"] == "no_reply_needed"
        )
        Campaign.end(self, second, "second")
        self.close()
        write_json(self.output / "transcript.json", self.transcript)
        write_json(
            self.output / "result.json",
            {
                "answer": answer,
                "response_event": response_event,
                "preparation": prepared,
                "offer": self.offer["id"],
                "echo_reference": self.echo,
                "clinic_reference": self.clinic,
                "lifecycle": self.archive,
                "draft_withdrawal_checked": answer == "accept",
            },
        )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    output = parser.parse_args().output
    output.mkdir(mode=0o700, parents=True)
    with (
        TemporaryDirectory(prefix="harpy-independent-") as directory,
        pytest.MonkeyPatch.context() as patch,
    ):
        root = Path(directory)
        resources = ledger.__wrapped__(root, patch)
        try:
            common = Independent(next(resources), output)
            common.start_common()
            common.store.engine.dispose()
            db, baseline = root / "ledger.db", root / "baseline.db"
            checkpoint(db, baseline)
            write_json(
                output / "checkpoint.json",
                {
                    "offer": common.offer["id"],
                    "game_revision": state(common.game).revision,
                    "same_database_checkpoint": True,
                },
            )
            before = common.clock.now
            for answer in ("accept", "decline"):
                common.store.engine.dispose()
                checkpoint(baseline, db)
                branch = copy(common)
                branch.output = output / answer
                branch.output.mkdir(mode=0o700)
                branch.transcript, branch.archive = list(common.transcript), list(common.archive)
                branch.clock.now = before
                branch.strain.dice.calls = 0
                branch.run_fork(answer, db)
        finally:
            resources.close()


if __name__ == "__main__":
    main()
