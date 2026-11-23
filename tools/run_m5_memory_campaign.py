"""Long offline Activity rehearsal with deliberate gaps in approved memory."""

import argparse
import json
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from run_m5_model_campaign import Campaign
from run_m5_model_missions import ledger, write_json
from run_m5_relationship_rehearsal import hear_aside, save_pressure, steer_dossier
from test_activity_shadow_readiness import consent, publish_opening, review, submission
from test_director_activity_scene import P2Scene
from test_ledger import ADMIN, OTHER, PLAYER
from test_m2_game import Gateway, state, tick
from test_m5_activity_pilots import NPC, PLOVER, attach, fixture, pilot_review, rehearsal
from test_p2_mission_cycle import launch
from test_strain_service import D6

from girlframe.ai.director_dossiers import PressurePlan, RelationshipPerspective
from girlframe.delivery.m2_worker import GameWorker
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.scenes.campaign_time import Anchor, Cut, Position, ScenePlan
from girlframe.services.campaign_difficulty import EVENT, opening
from girlframe.services.campaign_time import CampaignTimeService
from girlframe.services.director_context import DirectorContextService
from girlframe.services.director_observation import DirectorObservationService
from girlframe.services.director_time import scene_time
from girlframe.services.m3_actors import ActorService
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_off_duty import OffDutyService
from girlframe.services.m3_strain import StrainService

PRIVATE = "copper lantern"
RED = "Use the red hoist for the repair cart."
BLUE = "Correction: use the blue hoist for the repair cart."
ERRAND = "Get replacement bootlaces before watch."
WAIT = {"kind": "WAIT", "reason": "pilots_have_the_floor"}
SCENES = (
    (
        "Uniform bench",
        "opening",
        (
            "The clerk will be ready after shift.",
            "Leave that stool for me, please.",
            "I am going to check the copy one last time.",
        ),
    ),
    (
        "Supply desk",
        "opening",
        (
            "The old routing sheet is here.",
            "Dispatch has amended the routing sheet.",
            "I'll put the new sheet in the rack.",
            "The spare gloves are beside the drawer.",
        ),
    ),
    (
        "East relay",
        "mission",
        (
            "I can see the outside shelf.",
            "Kite's harness is clear of the hinge.",
            "Can we stop for a clip check?",
            "The return lane is open.",
        ),
    ),
    (
        "East debrief",
        "debrief",
        (
            "The figures are on the board.",
            "I want to file my own account.",
            "Who can hold the door while I finish?",
            "The clerk has closed the window.",
        ),
    ),
    (
        "Barracks",
        "off-duty",
        (
            "Someone left a kettle by the bunks.",
            "There is a dry patch by the grate.",
            "I have a minute before review.",
            "Tell me before you borrow that mug.",
        ),
    ),
    (
        "Floodgate",
        "mission",
        (
            "The chalk stripe ends here.",
            "The next crew needs the cart handle.",
            "I can see the gauge face from the platform.",
            "Keep the west steps clear.",
        ),
    ),
    (
        "Repair bay",
        "debrief",
        (
            "The following crew is waiting for the routing sheet.",
            "The cart stays here for now.",
            "There is a wrench under that rag.",
            "I can post one notice before leaving.",
        ),
    ),
    (
        "Stores",
        "off-duty fiction",
        (
            "The bins are open for returns.",
            "The late supply lift has filled up.",
            "I'll make a list for tomorrow.",
            "The benches are clear if you need to sit.",
        ),
    ),
    (
        "High intake",
        "mission",
        (
            "The ledge has room for one kit bag.",
            "I can mark the safe edge.",
            "There is time for one more reading.",
            "The next watch will use the same approach.",
        ),
    ),
    (
        "Evening report",
        "debrief",
        (
            "The clerk is back. I still want to write the correction myself.",
            "The old accounts should stay with their authors.",
            "There is a stool by the desk.",
            "The supply desk is booking a place for tomorrow.",
        ),
    ),
    (
        "North watch",
        "mission",
        (
            "The steps are clear until the landing.",
            "Which hoist should the next crew use?",
            "I can leave the note in the common rack.",
            "One supply place opened for tomorrow.",
        ),
    ),
    (
        "After-action table",
        "debrief",
        (
            "The clerk wants each account in its own column.",
            "The return board is beside the door.",
            "There is a place for a short note.",
            "The watch list goes up before supper.",
        ),
    ),
)


class MemoryCampaign:
    def __init__(self, store, output):
        self.store, self.output = store, output
        self.app, self.scene, self.game, self.clock, self.handler, self.pilot = (
            rehearsal.__wrapped__(fixture.__wrapped__(store))
        )
        for provider in (self.handler, self.pilot):
            provider.client.limits = provider.client.limits.__class__(
                attempts=240, output_tokens=500
            )
        self.context = self.app.session.context
        self.channel = 900
        self.scene_channel = 900
        self.archive, self.transcript, self.checkpoints = [], [], []
        self.memory_approvals = 0
        self.restarts = 0
        self.promise = self.red = self.blue = None
        self.memory_expected = self.hoist_expected = False
        self.withdrawn = False
        self.missions = MissionService(store)
        self.timeline = CampaignTimeService(store)
        self.strain = StrainService(OffDutyService(self.missions), dice=D6())
        self.worker, self.gateway, self.dice = GameWorker(self.game), Gateway(), self.game.dice
        policy = store.policy
        store.policy = policy.model_copy(
            update={
                "m3_approval": policy.m3_approval.model_copy(
                    update={
                        "subsystems": policy.m3_approval.subsystems
                        | {"plays", "playbooks", "strain", "world"}
                    }
                )
            }
        )
        with store.engine.connect() as c:
            self.lark = self.app.session.observer._authorize_input(c, PLAYER, self.scene, "pilot")[
                2
            ]
        self.squad = (self.lark, NPC, PLOVER)
        self.first = self.scene
        attach(self.app, self.scene)
        attach(self.app, self.scene, PLOVER, "Plover")
        steer_dossier(
            self.app,
            self.scene,
            NPC,
            fresh=True,
            relationship=RelationshipPerspective(
                subject=self.lark,
                text="I used to hurry her reports. Now I make room for her own words.",
            ),
        )
        steer_dossier(
            self.app,
            self.scene,
            PLOVER,
            fresh=True,
            relationship=RelationshipPerspective(
                subject=self.lark,
                text="She checks her figures carefully and prefers her own company.",
            ),
        )
        self.errand = PressurePlan(
            stake="My old laces slip on the stairs.", next_step="Ask stores."
        )
        self.errand_id = save_pressure(self.app, self.scene, NPC, ERRAND, self.errand)

    def prepare_native(self):
        introduction = self.game.bind_scene(ADMIN, "memory-intro", 901)["scene"]
        self.game.close_scene(ADMIN, "memory-intro-closed", 901)
        with self.store.transaction() as c:
            current = opening(c, self.store.campaign_id)
            saved = current.model_copy(update={"scene": introduction, "channel": 901})
            self.store._audit(
                c, ADMIN.user_id, "memory-opening", EVENT, saved.model_dump(mode="json")
            )
            baseline = state(self.game)
            for sheet in baseline.sheets.values():
                for asset in sheet.assets:
                    asset.void = False
            self.game.event(c, ADMIN.user_id, "memory-baseline", "synthetic.baseline", baseline)
        self.strain.configure(
            ADMIN, "memory-strain", state(self.game).revision, "business_as_usual", frozenset()
        )
        self.timeline.initialize(
            ADMIN,
            "memory-calendar",
            Anchor(chapter="Watch trials", position=Position(day=4, slot="morning")),
        )
        self.schedule(self.channel, SCENES[0][0])

    def schedule(self, channel, location):
        calendar = self.timeline.projection(ADMIN)
        active = Anchor.model_validate(calendar["anchor"])
        with self.store.engine.connect() as c:
            row = self.game.scene(c, channel, check_slot=False)
        self.timeline.schedule(
            ADMIN,
            f"schedule:{channel}",
            channel,
            row["id"],
            row["revision"],
            calendar["anchor_receipt"],
            ScenePlan(
                start=active.position,
                end=active.position,
                location=location,
                participants=(1, 2, 3),
            ),
        )

    def add(self, who, kind, value):
        self.transcript.append({"scene": self.name, "speaker": who, "kind": kind, "value": value})

    def tick(self, count=4):
        tick(self.worker, self.gateway, count)

    def open_scene(self, channel, location, phase):
        self.channel = self.scene_channel = channel
        if channel != 901:
            self.game.bind_scene(ADMIN, f"bind:{channel}", channel)
            self.schedule(channel, location)
        for viewer in (ADMIN, PLAYER, OTHER):
            self.game.join_scene(viewer, f"join:{channel}:{viewer.user_id}", channel)
        cast = CastService(ActorService(self.missions))
        for viewer, actor in (
            (OTHER, NPC),
            (OTHER, PLOVER),
            (ADMIN, ActorRef(kind="handler", entity="1")),
        ):
            current = cast.view(viewer, channel)
            cast.change(
                viewer,
                f"cast:{channel}:{actor.entity}",
                channel,
                current["game_revision"],
                current["cast_revision"],
                "join",
                actor,
            )
        with self.store.engine.connect() as c:
            self.scene = self.game.scene(c, channel)["id"]
        self.app.write(ADMIN, f"configure:{channel}", self.scene, "configure", {"revision": 0})
        for viewer in (ADMIN, PLAYER, OTHER):
            consent(self.app, self.scene, viewer)
        publish_opening(
            self.app,
            self.scene,
            ADMIN,
            location=location,
            intro=f"{phase.title()} at {location.lower()}. The crew has a moment to talk.",
        )

    def restart(self):
        self.store.engine.dispose()
        observer = DirectorObservationService(self.store, synthetic=True, activity_shadow=True)
        self.context = DirectorContextService(observer)
        self.app = P2Scene.model_fixture(
            self.context,
            self.handler.client,
            batch=self.handler.client,
            pilot_batch=self.pilot.client,
        )
        self.restarts += 1

    def close(self):
        preview = self.app.read(ADMIN, self.scene, "closeout")
        self.app.close(
            ADMIN, f"close:{self.channel}", self.scene, self.channel, preview["revision"], ()
        )

    def play_off_duty(self):
        # Native recovery uses the established owned Pilot and Handler controls.
        channel = 950
        current = Anchor.model_validate(self.timeline.projection(ADMIN)["anchor"])
        cut = Cut(
            target=Anchor(
                chapter=current.chapter,
                position=Position(day=current.position.day, slot="afternoon"),
            )
        )
        preview = self.timeline.preview_cut(ADMIN, cut)
        self.timeline.commit_cut(ADMIN, "off-duty-calendar", cut, preview["token"])
        self.game.bind_scene(ADMIN, "off-duty-rules-scene", channel)
        self.schedule(channel, "Barracks recovery")
        for viewer in (ADMIN, PLAYER, OTHER):
            self.game.join_scene(viewer, f"off-duty-rules:{viewer.user_id}", channel)
        self.scene_channel = channel
        cycle, identity = Campaign.prepare_period(self)
        Campaign.finish_period(self, cycle, identity)
        self.game.close_scene(ADMIN, "off-duty-rules-closed", channel)

    def witness(self, key, line):
        _, source = submission(self.app, self.scene, PLAYER, key, line)
        return self.record_source(key, source), source

    def record_source(self, key, source):
        with self.store.engine.connect() as c:
            order = len(self.context._references(c, self.scene))
        return self.context.record(
            ADMIN, key + ":reference", self.scene, source["source_id"], order, known_by=self.squad
        )["id"]

    def remember(self, actor, kind, text, source):
        data = self.app.read(OTHER, self.scene, "portrayal-preview", actor.token)
        key = f"{actor.entity}:note:{data['dossier_version']}"
        draft = self.app.write(
            OTHER,
            key,
            self.scene,
            "portrayal-memory",
            {
                "actor": actor.model_dump(mode="json"),
                "version": data["dossier_version"],
                "memory": {"kind": kind, "text": text, "knowledge_refs": [source]},
            },
        )
        self.app.write(
            OTHER,
            key + ":approve",
            self.scene,
            "portrayal-confirm",
            {"actor": actor.model_dump(mode="json"), "id": draft["id"]},
        )

    def approve_memory(self, kind, origin, reference):
        view = self.app.read(ADMIN, self.scene, "scene-opening")
        player = self.app.read(PLAYER, self.scene, "scene-opening")
        assert set(player) == {"opening"} and PRIVATE not in json.dumps(player)
        suggestion = next(
            option
            for option in view["memory"]
            if option["kind"] == kind
            and option["source_scene"] == origin
            and reference in {item["id"] for item in option["sources"]}
        )
        if kind == "promise":
            with self.store.engine.connect() as c:
                lark = self.app.session.dossiers._actor(c, self.scene, self.lark).label
            assert set(suggestion["sources"][0]["audience"]) == {"Tern", lark}, suggestion
        with self.store.engine.connect() as c:
            assert all(
                item.origin_reference != reference
                for item in self.context._references(c, self.scene)
            )
        payload = {"source_scene": origin, "review": suggestion["review"]}
        key = f"memory-review:{self.scene}:{reference}"
        receipt = self.app.write(ADMIN, key, self.scene, "scene-memory-carry", payload)
        assert self.app.write(ADMIN, key, self.scene, "scene-memory-carry", payload) == receipt
        assert reference in receipt["references"] and not receipt["effects_applied"]
        self.memory_approvals += 1

    def plan(self, packet):
        dossier = packet["dossier"]
        tern = dossier["actor"]["entity"] == NPC.entity
        evidence = dossier["context"]["references"]
        origins = {item.get("origin_reference", item["id"]) for item in evidence}
        encoded = json.dumps(packet, ensure_ascii=False)
        assert (PRIVATE in encoded) == bool(tern and self.memory_expected)
        promises = dossier["state"]["promises"]
        assert bool(promises) == bool(tern and self.memory_expected and self.promise)
        if self.promise and tern:
            assert (self.promise in origins) == self.memory_expected
        if self.blue:
            assert self.red not in origins and "red hoist" not in encoded.casefold()
            assert (self.blue in origins) == self.hoist_expected
            if not tern:
                assert bool(dossier["state"]["beliefs"]) == self.hoist_expected
        if tern:
            errand = next(
                item
                for item in dossier["state"]["pressures"]
                if item["pressure_id"] == self.errand_id
            )
            assert errand["pressure"]["status"] == ("deferred" if self.withdrawn else "open")
        self.checkpoints.append(
            {
                "scene": self.name,
                "speaker": packet["callsign"],
                "memory": bool(promises),
                "corrected_hoist": bool(self.blue and self.blue in origins),
                "references": len(evidence),
            }
        )
        if self.silent:
            return WAIT
        target = (
            self.lark if self.recall or self.boot or self.defer else (NPC if not tern else PLOVER)
        )
        if target.model_dump(mode="json") not in [x["actor"] for x in packet["audience"]]:
            target = self.lark
        return {"kind": "ADDRESS", "recipients": [target.model_dump(mode="json")]}

    def draft(self, packet):
        references = packet["dossier"]["context"]["references"]
        refs = []
        if self.boot:
            text = "I’ll wait by the copper lantern. You keep the pen."
        elif self.defer:
            text = "I’ll ask about stores tomorrow. I can wait here while you finish tonight."
        elif self.recall and packet["callsign"] == "Tern":
            memory = next(
                (item for item in references if item.get("origin_reference") == self.promise), None
            )
            if memory:
                text = "I remember the copper lantern. Want me by the door while you write?"
                refs = [memory["id"]]
            else:
                text = "Would you like company while you finish, or some space?"
        elif self.hoist_expected and packet["callsign"] == "Plover":
            hint = next(
                item for item in references if item.get("origin_reference", item["id"]) == self.blue
            )
            text = "Leave the cart by the blue hoist. Dispatch corrected the sheet."
            refs = [hint["id"]]
        else:
            speaker = packet["callsign"]
            line = self.line.rstrip(".?")
            # Keep the filler source-local and out of the later memory checkpoints.
            text = (
                f"I heard you about this part: {line.lower()}. I can keep watch here."
                if speaker == "Tern"
                else f"For my copy: {line.lower()}. I'll see to my own kit."
            )
        return {"kind": "DIALOGUE", "text": text, "source_refs": refs}

    def turn(self, line, *, sent=False, recall=False, boot=False, silent=False, defer=False):
        self.line, self.recall, self.boot, self.silent, self.defer = (
            line,
            recall,
            boot,
            silent,
            defer,
        )
        key = f"turn:{len(self.checkpoints) + 1}"
        if not sent:
            submission(self.app, self.scene, PLAYER, key + ":input", line)
        self.add("Lark", "heard scene turn", line)
        before = state(self.game)
        with self.store.engine.connect() as c:
            time = scene_time(c, self.store.campaign_id, self.scene)
        self.clock.now += 120
        self.pilot.audience_answer, self.pilot.answer = self.plan, self.draft
        outcome = review(self.app, self.scene)["model_outcome"]
        if silent:
            assert outcome["status"] == "wait", outcome
            self.add(self.pilot.plans[-1]["callsign"], "wait", outcome["reason"])
            return None
        assert outcome["status"] == "pilot_review", outcome
        proposal = outcome["proposal_id"]
        draft = self.app.read(OTHER, self.scene, "npc-owner-review", proposal)["proposal"]
        listeners = draft["intended_recipients"]
        pilot_review(self.app, self.scene, proposal, *listeners)
        data = {"proposal": proposal}
        sent = self.app.write(OTHER, key + ":deliver", self.scene, "npc-deliver", data)
        assert self.app.write(OTHER, key + ":retry", self.scene, "npc-deliver", data) == sent
        assert not sent["effects_applied"] and state(self.game) == before
        with self.store.engine.connect() as c:
            assert scene_time(c, self.store.campaign_id, self.scene) == time
        hearing = self.app.npc_delivery.hearing(ADMIN, self.scene, sent["id"])
        assert hearing["recipients"] == listeners
        if PRIVATE in hearing["text"]:
            assert listeners == [self.lark.model_dump(mode="json")]
        self.add(self.pilot.plans[-1]["callsign"], "approved dialogue", hearing["text"])
        assert review(self.app, self.scene) is None
        return sent["reference"]

    def run(self):
        self.prepare_native()
        for number, (self.name, phase, lines) in enumerate(SCENES, 1):
            if number > 1:
                cut = Cut(
                    target=Anchor(
                        chapter="Watch trials", position=Position(day=3 + number, slot="morning")
                    )
                )
                preview = self.timeline.preview_cut(ADMIN, cut)
                self.timeline.commit_cut(ADMIN, f"campaign-day:{number}", cut, preview["token"])
            self.memory_expected = number in (1, 4, 10)
            self.hoist_expected = number in (6, 7, 9, 11, 12)
            mission = None
            if phase == "mission":
                mission = launch(
                    self.missions, f"mission:{number}", f"Inspect the {self.name.lower()}."
                )
            if number != 1:
                channel = (
                    int(mission["channel"]) if mission and "channel" in mission else 910 + number
                )
                self.open_scene(channel, self.name, phase)
            else:
                publish_opening(
                    self.app,
                    self.scene,
                    ADMIN,
                    location=self.name,
                    intro="Lark has a minute before the clerk opens.",
                )
            if number in (4, 10, 11):
                self.approve_memory("promise", self.first, self.promise)
            if number == 11:
                consent(self.app, self.first, PLAYER, value=False, key="withdraw-closed-origin")
                self.withdrawn = True
            if number in (11, 12):
                scene, receipt = self.deferred
                self.approve_memory("pressure", scene, receipt)
            if self.hoist_expected:
                self.approve_memory("corrected_report", self.stores, self.blue)
            if number in (4, 6, 10, 12):
                self.restart()
            if number == 1:
                line = "Would you wait by the copper lantern while I write? Keep that between us."
                hear_aside(self.app, self.scene, "bench-promise", line, NPC)
                self.promise = self.turn(line, sent=True, boot=True)
                self.remember(
                    NPC, "promises", "I promised to stay nearby while Lark writes.", self.promise
                )
            if number == 2:
                self.stores = self.scene
                self.red, previous = self.witness("red-hoist", RED)
                self.remember(PLOVER, "beliefs", "I was told to use the red hoist.", self.red)
                self.turn(RED, sent=True)
                _, update = submission(
                    self.app,
                    self.scene,
                    PLAYER,
                    "blue-hoist",
                    BLUE,
                    source_id=previous["source_id"],
                    expected_source_revision=previous["source_revision"],
                )
                self.blue = self.record_source("blue-hoist", update)
                self.hoist_expected = True
                self.remember(PLOVER, "beliefs", "Dispatch corrected the hoist to blue.", self.blue)
                self.turn(BLUE, sent=True)
                lines = lines[-2:]
            for index, line in enumerate(lines):
                receipt = self.turn(
                    line,
                    recall=number in (4, 10, 12) and index == 1,
                    silent=(index == 2),
                    defer=number == 10 and index == 3,
                )
                if number == 10 and index == 3:
                    assert receipt
                    plan = PressurePlan(
                        stake=self.errand.stake,
                        status="deferred",
                        next_step="Ask the supply desk in the morning.",
                        account="I stopped to give Lark room to finish her report.",
                    )
                    save_pressure(
                        self.app,
                        self.scene,
                        NPC,
                        ERRAND,
                        plan,
                        evidence=(receipt,),
                        pressure_id=self.errand_id,
                    )
                    self.deferred = self.scene, receipt
            if mission:
                Campaign.end(self, mission, f"mission:{number}")
            if number == 12:
                dossiers = self.app.session.dossiers
                assert dossiers.gm(ADMIN, self.scene, NPC)["history"][-1]["state"]["promises"]
            self.close()
            if number == 5:
                self.play_off_duty()
            write_json(self.output / "transcript.json", self.transcript)
        assert all(
            PRIVATE not in json.dumps(item, ensure_ascii=False) for item in self.handler.calls
        )
        assert self.withdrawn and self.restarts == 4
        write_json(
            self.output / "result.json",
            {
                "synthetic": True,
                "scenes": len(SCENES),
                "batches": len(self.checkpoints),
                "deliveries": len(self.pilot.calls),
                "restarts": self.restarts,
                "memory_approvals": self.memory_approvals,
                "native_lifecycle": self.archive,
                "checkpoints": self.checkpoints,
            },
        )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    output = parser.parse_args().output
    output.mkdir(mode=0o700, parents=True)
    with (
        TemporaryDirectory(prefix="harpy-memory-") as directory,
        pytest.MonkeyPatch.context() as patch,
    ):
        resources = ledger.__wrapped__(Path(directory), patch)
        try:
            MemoryCampaign(next(resources), output).run()
        finally:
            resources.close()


if __name__ == "__main__":
    main()
