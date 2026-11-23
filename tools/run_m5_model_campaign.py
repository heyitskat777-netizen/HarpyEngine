"""Matched synthetic missions with model-authored dialogue from the whole cast."""

import argparse
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from time import monotonic, sleep

import pytest
from run_m5_model_missions import (
    ADMIN,
    OTHER,
    PLAYER,
    ModelMission,
    ledger,
    write_json,
)
from test_activity_shadow_readiness import publish_opening
from test_m2_game import pass_tags, state
from test_off_duty_cycle import call, movement
from test_p2_mission_cycle import launch
from test_punishment_service import submit
from test_session_zero import FACILITATOR
from test_strain import facts
from test_strain_service import D6
from test_world import gorgon, initial

from girlframe.ai.activity_batch import ActivityPilotDecision, PilotContribution, scene_details
from girlframe.ai.conversation import RULES_IN_PROSE
from girlframe.ai.director_dossiers import DossierProfile, DossierState
from girlframe.ai.model_transport import ModelLimits, OpenAIResponses
from girlframe.ai.pilot_initiative import pilot_initiative, pilot_lenses
from girlframe.ai.worldbuilding import DevelopmentAction, WorldbuildingProposal
from girlframe.engine.m2 import PlayInput
from girlframe.engine.m3_frame_rewards import Claim
from girlframe.engine.m3_off_duty import RecoveryChoice
from girlframe.engine.m3_punishments import Details
from girlframe.engine.m3_strain_effects import Choice
from girlframe.engine.m3_world_development import DevelopmentDraft, Subject
from girlframe.engine.m3_world_state import Faction
from girlframe.engine.pilot_portrayal import PilotPortrayal
from girlframe.scenes.campaign_time import SLOTS, Anchor, Cut, Position, ScenePlan
from girlframe.services.campaign_time import CampaignTimeService
from girlframe.services.m3_frame_rewards import RewardService
from girlframe.services.m3_off_duty import OffDutyService
from girlframe.services.m3_off_duty_cycle import CycleService
from girlframe.services.m3_punishments import PunishmentService
from girlframe.services.m3_strain import StrainService
from girlframe.services.m3_strain_effects import EffectService
from girlframe.services.onboarding import WorkflowError

PILOTS = {"Lark": PLAYER, "Kite": OTHER}
KEEP = {
    "north-relay": {
        "intent": "Keep the case level on the flexing floor.",
        "ruling": "Lark holds the case level until the floor settles.",
    },
    "south-relay": {
        "intent": "Hold the sighting gauge steady above the loose rail.",
        "ruling": "Lark steadies the gauge long enough to read it safely.",
    },
}
BRIEF = {
    "notes": {
        "voice": "Direct and attentive, with a dry edge at ease. Leave room for an answer.",
        "intervention": "Protect the chance to speak or ask permission to take a specific task.",
    },
    "brief": {},
}
FRAMES = {
    "north-relay": (
        "At the marked lane with a charged case. The shelf is in sight. Establish how you "
        "want to work together.",
        "The floor flexes and Lark's end tilts. The case is still in hand. A stop or a "
        "request for help is available.",
        "The case was steadied through the native ruling. Both can see the charged battery "
        "now rests on the outside shelf with its clips shut. The relay is unverified.",
        "At the exit stripe with time for a brief readback. Each Girl can say what she wants "
        "to keep or change about the way the team worked.",
    ),
    "off-duty": (
        "You're in the barracks after the relay mission. Wet gloves hang between the bunks. "
        "There's time to talk or leave the other person room.",
        "The next shift will share the same comms. Both Girls can bring up one thing they "
        "noticed or wanted to handle differently. The Handler is in earshot.",
        "Lights out is approaching. If you want the team to remember a particular practice "
        "on the next mission, state it in your own words or leave the matter open.",
    ),
    "south-relay": (
        "North relay gear is stowed. At the south relay, the approved task is to read the "
        "gauge from the marked platform. You can bring up a practice from earlier if you "
        "have an approved note.",
        "The marked railing is loose. The maintenance shortcut is unapproved. Decide what to "
        "propose and whether you need the other Girl or Anwen to help.",
        "A native ruling verified Lark steadied the gauge. Both can see it reads steady in "
        "the marked range from the platform. You have no evidence that anything behind the "
        "sealed panel works.",
        "Back on the platform before the debrief. Respond if you have something to add about "
        "the gauge or the way you worked together.",
    ),
}
SCENE_DETAILS = {
    "off-duty": "Wet gloves hang from a pipe between the bunks.",
    "south-relay": "A yellow stripe marks the edge of the platform beside the gauge.",
}
SCENE_OPENINGS = {
    "north-relay": ("North relay", "The Girls can see the marked lane and the outside shelf."),
    "off-duty": ("Barracks", "There is time to talk before lights-out."),
    "south-relay": ("South relay platform", "The approved task is to read the gauge from here."),
}
GM_PROBE = "GM_ONLY_COBALT_47"
PILOT_PROBE = "LARK_ONLY_SAFFRON_18"
PORTRAYAL = {
    "Lark": DossierProfile(
        presence="recurring",
        voice="Dry and quiet. Uses concrete observations and leaves pauses.",
        behavior="Wants a clear handoff and time to finish a report. Admits uncertainty.",
        values=("Accuracy", "Having a say in her own work"),
        fears=("Getting spoken over and then being wrong about what she saw",),
    ),
    "Kite": DossierProfile(
        presence="recurring",
        voice="Practical, quick to joke when she has time. Uses short, plain phrases.",
        behavior="Quick to volunteer. Tends to fill a pause and can notice it.",
        values=("Nobody being left to carry everything",),
        fears=("Standing by while a problem gets worse",),
    ),
}
RETEST_PERSONALITIES = {
    "Lark": PilotPortrayal(
        archetype="Watchkeeper",
        vibe="Dry and exact",
        initiative="Wait through one pause. Step in to name a gap in the watch or record.",
    ),
    "Kite": PilotPortrayal(
        archetype="Mechanic",
        vibe="Warm and restless",
        initiative="Offer a small practical job early. Ask who has it before you take it.",
    ),
}
RETEST_CIRCUMSTANCES = {
    ("north-relay", 1): (
        "There is a blind spot at the bend in the marked lane. Neither of you has said who "
        "will watch it yet."
    ),
    ("off-duty", 2): (
        "Lark has the debrief form. It has one box for relay status, which could blur the "
        "difference between a battery delivered and a relay verified. She can raise it, "
        "let Kite help, or leave the form for later."
    ),
    ("south-relay", 1): (
        "A cabinet by the platform is marked BACKUP POWER. The label establishes what the "
        "cabinet is for. Its condition and any connection to the gauge are still unknown."
    ),
}
PILOT_PROMPT = (
    "Portray only your AI Girl, using her scoped dossier, approved opening, current scene frame, "
    "and heard dialogue. "
    "Use her Girl playbook, Frame and personality to decide what she notices and how she acts. "
    "Play the situation in character. Offer help, disagree, take a first-person small action, "
    "or let the other person speak. Treat reports as reports. No other character's choices "
    "or feelings are yours to narrate. Give permission, refuse or set a boundary for yourself. "
    "Use DIALOGUE for a single short line with optional own_action. Use SCENE_OFFER for a "
    "private proposed intent with real stakes and WAIT if the others have the floor. "
    "Cite only reference IDs from your dossier context. Cite only shared evidence in speech. "
    "Use any approved carryover as context for yourself. Keep any non-shared facts and "
    "private canaries out of speech. Never establish a Play, roll, world result or cost in prose. "
    "Do not use game mechanics in dialogue. A scene frame is a facilitator cue available to you. "
    "It does not provide another person's private history. A scene_details reference can ground "
    "a small gesture or task when it fits. Cite it when you use it."
)
SMOKE = {"kind": "DIALOGUE", "text": "I am here if you want a hand.", "source_refs": []}


class Campaign(ModelMission):
    def __init__(self, store, exchange, fixture, portrayal_retest=False):
        self.serial = 0
        self.journal = []
        self.archive = []
        self.smoke = fixture
        self.portrayal_retest = portrayal_retest
        brief = BRIEF
        if portrayal_retest:
            brief = BRIEF | {"notes": BRIEF["notes"] | {"personality": "dry"}}
        super().__init__(store, "Advocate", brief, exchange, fixture, None)
        policy = store.policy
        store.policy = policy.model_copy(
            update={
                "m3_approval": policy.m3_approval.model_copy(
                    update={"subsystems": policy.m3_approval.subsystems | {"strain", "world"}}
                )
            }
        )
        self.strain = StrainService(OffDutyService(self.missions), dice=D6())
        self.pilot_model = OpenAIResponses(
            model="offline-pilot",
            api_key="offline-fixture",
            limits=ModelLimits(attempts=50, output_tokens=500),
            post=self.pilot_post,
        )

    def exchange_decision(self, role, contract, packet, default):
        self.serial += 1
        number = self.serial
        write_json(
            self.exchange / f"request-{number:02}.json",
            {"role": role, "scene": self.phase, "beat": self.beat, **contract, "packet": packet},
        )
        path = self.exchange / f"decision-{number:02}.json"
        if self.smoke:
            write_json(path, {"decision": default})
        deadline = monotonic() + 1200
        while not path.exists() and monotonic() < deadline:
            sleep(0.25)
        if not path.exists():
            raise TimeoutError(f"Missing {path.name}")
        return json.loads(path.read_text())["decision"]

    def answer(self, packet):
        assert all(probe not in json.dumps(packet) for probe in (GM_PROBE, PILOT_PROBE))
        assert packet["opening"]["location"] == SCENE_OPENINGS[self.phase][0]
        contract = json.loads((self.exchange / "contract.json").read_text())
        output = self.exchange_decision(
            "Anwen", contract, packet, {"kind": "WAIT", "reason": "pilots_have_the_floor"}
        )
        self.add("Anwen", "decision", output)
        self.decision = {"decision": output}
        return output

    def pilot_post(self, request, timeout):
        body = json.loads(request.data)
        assert body["store"] is False and "tools" not in body
        payload = json.loads(body["input"][1]["content"])
        packet = payload["packet"]
        encoded = json.dumps(packet)
        assert GM_PROBE not in encoded
        assert self.speaking == "Lark" or PILOT_PROBE not in encoded
        decision = self.exchange_decision(
            self.speaking,
            {"instructions": body["input"][0]["content"], "contract": payload["contract"]},
            packet,
            SMOKE,
        )
        return json.dumps(
            {
                "status": "completed",
                "output": [
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [
                            {"type": "output_text", "text": json.dumps({"decision": decision})}
                        ],
                    }
                ],
            }
        ).encode()

    def add(self, role, kind, value):
        self.journal.append(
            {"phase": self.phase, "beat": self.beat, "role": role, "kind": kind, "value": value}
        )
        write_json(self.exchange / "journal.json", self.journal)

    def actors(self):
        with self.store.engine.connect() as c:
            return {
                name: self.observer._authorize_input(c, viewer, self.scene, role)[2]
                for name, viewer, role in (
                    ("Lark", PLAYER, "pilot"),
                    ("Kite", OTHER, "pilot"),
                    ("Anwen", ADMIN, "handler"),
                )
            }

    def save_dossiers(self):
        dossiers = self.session.dossiers
        actors = self.actors()
        for name, viewer in PILOTS.items():
            key = f"dossier:{name}"
            profile = PORTRAYAL[name]
            if self.portrayal_retest:
                profile = profile.model_copy(update={"pilot_portrayal": RETEST_PERSONALITIES[name]})
            proposal = dossiers.propose(
                viewer, key, self.scene, actors[name], 0, profile, DossierState()
            )
            dossiers.confirm(viewer, key + ":confirm", self.scene, proposal["id"])

    def save_report(self, source, audience, label):
        with self.store.engine.connect() as c:
            order = len(self.context._references(c, self.scene))
        return self.context.record(
            ADMIN,
            f"{self.phase}:reference:{source}",
            self.scene,
            source,
            order,
            known_by=tuple(audience),
            topic=label,
        )["id"]

    def approve_scene_detail(self, phase):
        key = phase + ":detail"
        world = self.session.worldbuilding
        _, source = self.line(key + ":source", OTHER, "GM, set the immediate surroundings.")
        request = world.open(ADMIN, key + ":open", self.scene, source["source_id"])
        text = SCENE_DETAILS[phase]
        location = state(self.game).world.locations[0]
        proposal = world.propose(
            ADMIN,
            key + ":proposal",
            self.scene,
            request["id"],
            WorldbuildingProposal(
                request_id=request["id"],
                action=DevelopmentAction(
                    development=DevelopmentDraft(
                        key=key,
                        kind="detail",
                        subject=Subject(kind="location", id=location.id),
                        title="Immediate surroundings",
                        text=text,
                    )
                ),
                cited_evidence=("source", "native"),
                private_reasoning="Synthetic shared scenery for the matched model comparison.",
            ),
        )
        world.review(
            ADMIN, key + ":review", self.scene, proposal["id"], "approve", "Shared scenery."
        )
        committed = world.confirm(ADMIN, key + ":confirm", self.scene, proposal["id"])
        world.disclose(
            ADMIN,
            key + ":disclose",
            self.scene,
            committed["id"],
            text,
            tuple(self.actors().values()),
        )

    def pilot_turn(self, name, frame):
        viewer = PILOTS[name]
        actors = self.actors()
        labels = {actor.token: label for label, actor in actors.items()}
        dossier = self.session.dossiers.role_packet(viewer, self.scene, actors[name])
        native = state(self.game).sheets[str(viewer.user_id)]
        traits = dossier.profile.pilot_portrayal if dossier.profile else None
        entries = self.app.timeline(viewer, self.scene)["entries"]
        with self.store.engine.connect() as connection:
            frontier = self.app.shadow.observer._state(connection, self.scene).reviewed_sequence
        nearby = []
        fresh_reports = []
        for item in entries:
            if item["kind"] not in ("input", "handler") or item.get("channel") == "private":
                continue
            actor = item["actor"]
            speaker = next(
                (label for label, role in actors.items() if role.model_dump(mode="json") == actor),
                None,
            )
            if speaker:
                report = {
                    "speaker": speaker,
                    "text": item["text"],
                    "action": item.get("action"),
                    "report_id": item["id"],
                }
                nearby.append(report)
                if (
                    item["kind"] == "input"
                    and item["channel"] == "comms"
                    and item["sequence"] > frontier
                    and speaker != name
                ):
                    fresh_reports.append(report)
        packet = {
            "callsign": name,
            "others": [label for label in labels.values() if label != name],
            "scene_frame": frame,
            "opening": self.app.read(viewer, self.scene, "scene-opening")["opening"],
            "dossier": dossier.model_dump(mode="json"),
            "portrayal_lenses": pilot_lenses(
                traits, girl=native.girl, frame=native.frame
            ).model_dump(mode="json"),
            "scene_details": [
                ref.model_dump(mode="json") for ref in scene_details(dossier.context.references)
            ],
            "heard_here": nearby[-8:],
        }
        for report in reversed(fresh_reports):
            cue = pilot_initiative(
                traits,
                report["report_id"],
                report["text"],
                girl=native.girl,
                frame=native.frame,
                seed=(
                    f"{self.store.campaign_id}:{self.scene}:{actors[name].token}:"
                    f"{actors[report['speaker']].token}"
                ),
            )
            if cue is not None:
                packet["initiative"] = cue.model_dump(mode="json")
                break
        self.speaking = name
        before = self.canon_and_time()
        response = self.pilot_model.generate(PILOT_PROMPT, packet, ActivityPilotDecision).decision
        self.add(name, "decision", response.model_dump(mode="json"))
        assert self.canon_and_time() == before
        if not isinstance(response, PilotContribution) or response.kind == "SCENE_OFFER":
            return None
        shadow = self.app.shadow
        try:
            shadow._check_fiction(response.text)
            shadow._check_action(response.fiction)
            if RULES_IN_PROSE.search(response.text):
                raise WorkflowError("RULES_IN_ROLEPLAY")
            if not set(response.source_refs) <= set(dossier.source_refs):
                raise WorkflowError("PILOT_CITATION")
            if response.fiction.follows_offer:
                raise WorkflowError("PILOT_OFFER_NOT_TRACKED_IN_NATIVE_SEAT")
            if any(
                word in response.text + (response.fiction.own_action or "")
                for word in (GM_PROBE, PILOT_PROBE)
            ):
                raise WorkflowError("PRIVATE_CANARY")
        except WorkflowError as error:
            self.add(name, "withheld", str(error))
            return None
        _, source = self.line(f"pilot:{self.phase}:{self.beat}:{name}", viewer, response.text)
        self.add(name, "heard", {"text": response.text, "action": response.fiction.own_action})
        assert self.canon_and_time() == before
        return source

    def scene_turns(self, phase):
        self.phase = phase
        self.beat = 0
        if phase in SCENE_DETAILS:
            self.approve_scene_detail(phase)
        location, intro = SCENE_OPENINGS[phase]
        baseline = self.canon_and_time()
        publish_opening(self.app, self.scene, FACILITATOR, location=location, intro=intro)
        opening = self.app.read(PLAYER, self.scene, "scene-opening")["opening"]
        assert [detail["text"] for detail in opening["details"]] == (
            [SCENE_DETAILS[phase]] if phase in SCENE_DETAILS else []
        )
        assert self.canon_and_time() == baseline and self.run_batch(0) is None
        self.add("Facilitator", "opening", opening)
        last = None
        for self.beat, frame in enumerate(FRAMES[phase], 1):
            if self.portrayal_retest and (cue := RETEST_CIRCUMSTANCES.get((phase, self.beat))):
                frame += " " + cue
            self.add("Facilitator", "frame", frame)
            for name in PILOTS if self.beat % 2 else reversed(PILOTS):
                source = self.pilot_turn(name, frame)
                if name == "Lark" and source is not None:
                    last = source
            if self.beat == 2 and phase in KEEP:
                ruling = self.play_keep(KEEP[phase], key=f"{phase}:keep")
                self.add("Engine", "native_keep", ruling["ruling"])
            baseline = self.canon_and_time()
            receipt = self.run_batch(120)
            if receipt is None:
                self.add("Engine", "batch", {"status": "idle"})
            elif receipt["status"] == "draft":
                heard, blocked = self.hear_draft(receipt["draft_id"], self.serial + 1)
                self.add(
                    "Anwen",
                    "review",
                    {"reason": receipt["reason"], "heard": heard, "blocked": blocked},
                )
            else:
                self.add("Engine", "batch", receipt)
            assert self.canon_and_time() == baseline
        return last

    def close_for_carry(self, public_source):
        current = self.actors()
        refs = []
        if public_source:
            public = self.save_report(public_source["source_id"], current.values(), "debrief")
            refs.append(public)
            self.add("Facilitator", "approved_report", public_source["source_id"])
        preview = self.app.read(ADMIN, self.scene, "closeout")
        closed = self.app.write(
            ADMIN,
            f"close:{self.phase}",
            self.scene,
            "close",
            {"revision": preview["revision"], "reports": refs},
        )
        self.add("Engine", "closed_scene", closed)
        return self.scene, tuple(refs)

    def bind(self, channel, label):
        self.scene_channel = channel
        timeline = CampaignTimeService(self.store)
        existing = Anchor.model_validate(timeline.projection(ADMIN)["anchor"])
        day, slot = existing.position.order
        next_position = Position(
            day=day + int(slot == len(SLOTS) - 1), slot=SLOTS[(slot + 1) % len(SLOTS)]
        )
        cut = Cut(target=Anchor(chapter=existing.chapter, position=next_position))
        preview = timeline.preview_cut(ADMIN, cut)
        timeline.commit_cut(ADMIN, f"time:{label}", cut, preview["token"])
        self.game.bind_scene(ADMIN, f"bind:{label}", channel)
        with self.store.engine.connect() as c:
            row = self.game.scene(c, channel, check_slot=False)
        timeline.schedule(
            ADMIN,
            f"book:{label}",
            channel,
            row["id"],
            row["revision"],
            timeline.projection(ADMIN)["anchor_receipt"],
            ScenePlan(
                start=next_position, end=next_position, location=label, participants=(1, 2, 3)
            ),
        )
        self.join(row["id"], label)

    def end(self, mission, label):
        result = self.missions.end(
            ADMIN,
            label + ":end",
            mission["id"],
            mission["revision"],
            True,
            debrief="The fixture facilitator verified the stated objective at the marked location.",
        )
        if result["phase"] == "awaiting_consequences":
            discipline = PunishmentService(self.store, self.missions.access.registry)
            for item in self.missions.get(ADMIN, mission["id"])["work"]:
                if discipline.get(ADMIN, item["id"])["state"] != "resolved":
                    submit(
                        discipline,
                        ADMIN,
                        item["id"],
                        Details(kind="stimulant_injection"),
                        item["id"],
                    )
            result = self.missions.complete(
                ADMIN, label + ":complete", mission["id"], result["revision"]
            )
        assert result["phase"] == "complete"
        self.archive.append({"phase": label, "result": result["phase"]})
        self.add("Engine", "mission_complete", result["phase"])

    def prepare_period(self):
        period = self.strain.periods.begin(ADMIN, "begin-off-duty")
        self.strain.prepare(
            ADMIN,
            "prepare-off-duty",
            period["id"],
            period["revision"],
            state(self.game).revision,
            facts(no_girl_void=True, last_mission_success_no_frame_death_infrastructure_loss=True),
        )
        choices = {
            "void": (
                1,
                1,
                Choice(
                    rule_id="strain.void.low.1.1",
                    gorgon=gorgon("directed", "new-threat", (10, 0)),
                    account="A distant threat is tracked.",
                ),
            ),
            "rebellion": (
                1,
                1,
                Choice(
                    rule_id="strain.rebellion.low.1.1",
                    target="city0",
                    faction=Faction(
                        id="local-cell",
                        name="Local cell",
                        kind="rebel",
                        cells=((0, 4),),
                        description="Local dissent.",
                    ),
                    account="A local cell forms.",
                ),
            ),
            "budget": (
                5,
                2,
                Choice(
                    rule_id="strain.budget.low.5.2",
                    rooms=((2, 3),),
                    account="Rooms are reassigned.",
                ),
            ),
        }
        effects = EffectService(self.strain)
        for item in state(self.game).strain.requests:
            assert item.severity == "low"
            face, column, choice = choices[item.track]
            self.strain.dice.face = face
            self.strain.roll(ADMIN, f"die:{item.track}", item.id, 1, state(self.game).revision)
            self.strain.choose(
                ADMIN, f"column:{item.track}", item.id, 2, state(self.game).revision, column
            )
            effects.apply(
                ADMIN,
                f"apply:{item.track}",
                item.id + ":effect",
                1,
                state(self.game).revision,
                choice,
            )
        assert self.strain.dice.calls == 3
        cycle = CycleService(self.strain.periods)
        call(cycle, self.game, ADMIN, period["id"], "activate")
        return cycle, period["id"]

    def finish_period(self, cycle, period):
        rewards = RewardService(cycle.periods)
        for name, viewer in PILOTS.items():
            self.dice.faces = (2, 2) if viewer == PLAYER else (4, 4)
            self.game.begin(
                viewer,
                f"roll-duty:{name}",
                self.scene_channel,
                state(self.game).sheets[str(viewer.user_id)].revision,
                PlayInput(
                    play="go_off_duty",
                    off_duty_id=period,
                    heat=0,
                    context="Time at base",
                    trigger_confirmed=True,
                ),
            )
            self.tick()
            pass_tags(self.game)
            self.tick(8)
            for work in cycle.periods.get(viewer, period)["work"]:
                if work["kind"] != "frame_off_duty_reward":
                    continue
                data = rewards.get(viewer, work["id"])
                if data["mode"] == "conditional" and data["owner_id"] == str(viewer.user_id):
                    rewards.apply(
                        viewer,
                        f"duty-reward:{name}",
                        work["id"],
                        data["revision"],
                        data["game_revision"],
                        Claim(fulfilled=False, account="No qualifying Frame reward recorded."),
                    )
            call(cycle, self.game, viewer, period, "scene", None, (), "")
            call(cycle, self.game, viewer, period, "recover", RecoveryChoice())
        call(
            cycle,
            self.game,
            ADMIN,
            period,
            "handler_scene",
            "routine",
            (1, 2),
            "Barracks check-in.",
        )
        call(cycle, self.game, ADMIN, period, "acknowledge", None)
        call(cycle, self.game, PLAYER, period, "acknowledge", None)
        call(
            cycle, self.game, ADMIN, period, "review_status", (3, 2), "Fixture performance review."
        )
        done = call(cycle, self.game, ADMIN, period, "finish", movement(self.game))
        assert done["phase"] == "complete"
        self.archive.append({"phase": "off-duty", "result": done["phase"]})
        self.add("Engine", "off_duty_complete", done["phase"])

    def carry(self, origin):
        from test_director_continuity import carry

        scene, refs = origin
        if refs:
            carry(self.context, scene, self.scene, refs, f"carry:{self.scene_channel}")

    def run_initiative_probe(self):
        zero, approved = self.setup()
        self.dispatch(zero, approved)
        self.phase, self.beat = "north-relay", 0
        publish_opening(
            self.app,
            self.scene,
            FACILITATOR,
            location="North relay",
            intro="The crew is at the exit stripe with a debrief form.",
        )
        original = self.canon_and_time()
        form = "The report has one box for relay status."
        offer_open = False
        for self.beat in (1, 2, 3):
            if self.beat == 1:
                line = form + " Battery delivered would look like I verified the relay."
            elif self.beat == 2:
                line = "Again, " + form.lower()
            elif offer_open:
                line = "That would help. Please take the form to the desk with both lines intact."
            else:
                line = "I'll write both lines myself. I need a little time with the form."
            self.line(f"probe:{self.beat}:lark", PLAYER, line)
            self.add("Lark", "scripted_report", line)
            if self.beat == 1:
                aside = "My gloves are hanging here to dry."
                self.line("probe:kite:aside", OTHER, aside)
                self.add("Kite", "scripted_report", aside)
            outcome = self.run_batch(120)
            if outcome and outcome["status"] == "draft":
                heard, blocked = self.hear_draft(outcome["draft_id"], self.serial + 1)
                self.add(
                    "Anwen",
                    "review",
                    {"reason": outcome["reason"], "heard": heard, "blocked": blocked},
                )
                offer_open = offer_open or bool(
                    heard and self.decision["decision"].get("fiction", {}).get("offers_help")
                )
            else:
                self.add("Engine", "batch", outcome)
            assert self.canon_and_time() == original
        write_json(
            self.exchange / "result.json",
            {"synthetic": True, "initiative_probe": True, "decisions": self.serial},
        )

    def run_campaign(self):
        with self.store.transaction() as c:
            baseline = state(self.game)
            baseline.world = initial().model_copy(update={"npcs": baseline.world.npcs})
            for sheet in baseline.sheets.values():
                for asset in sheet.assets:
                    asset.void = False
            self.game.event(c, ADMIN.user_id, "no-starting-void", "synthetic.baseline", baseline)
        self.strain.configure(
            ADMIN, "strain-scenario", state(self.game).revision, "business_as_usual", frozenset()
        )
        zero, approved = self.setup()
        opening = zero.view(ADMIN)["opening"]
        first = self.dispatch(zero, approved)
        self.save_dossiers()
        self.phase, self.beat = "north-relay", 0
        self.line("gm-private-probe", OTHER, f"GM, {GM_PROBE}")
        _, private = self.line("pilot-private-probe", PLAYER, PILOT_PROBE, channel="private")
        self.save_report(private["source_id"], (self.actors()["Lark"],), "general")
        last = self.scene_turns("north-relay")
        self.end(first, "north-relay")
        origin = self.close_for_carry(last)
        self.bind(902, "barracks")
        cycle, period = self.prepare_period()
        self.carry(origin)
        last = self.scene_turns("off-duty")
        self.finish_period(cycle, period)
        origin = self.close_for_carry(last)
        self.bind(903, "south-relay")
        self.carry(origin)
        second = launch(
            self.missions, "south", "Read the south relay gauge from the marked platform."
        )
        self.dice.faces = (4, 5)
        last = self.scene_turns("south-relay")
        self.end(second, "south-relay")
        self.close_for_carry(last)
        assert self.dice.calls == 4
        write_json(
            self.exchange / "result.json",
            {
                "synthetic": True,
                **({"portrayal_retest": True} if self.portrayal_retest else {}),
                "opening": opening["handler_control"],
                "decisions": self.serial,
                "native_2d6_rolls": self.dice.calls,
                "strain_d6_rolls": self.strain.dice.calls,
                "campaign": self.archive,
            },
        )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("exchange", type=Path)
    parser.add_argument("--fixture", action="store_true")
    parser.add_argument("--portrayal-retest", action="store_true")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--initiative-probe", action="store_true")
    mode.add_argument(
        "--relationship-rehearsal", action="store_true", help="Run the local relationship fixture."
    )
    mode.add_argument(
        "--relationship-exchange",
        action="store_true",
        help="Run the same scenario with fresh decisions from the local file exchange.",
    )
    mode.add_argument(
        "--relationship-revisit",
        action="store_true",
        help="Use a fixed prior choice and fresh decisions after the scene is restored.",
    )
    args = parser.parse_args()
    args.exchange.mkdir(parents=True, mode=0o700)
    with (
        TemporaryDirectory(prefix="harpy-m5-campaign-") as temp,
        pytest.MonkeyPatch.context() as patch,
    ):
        fixture = ledger.__wrapped__(Path(temp), patch)
        try:
            if (
                args.relationship_rehearsal
                or args.relationship_exchange
                or args.relationship_revisit
            ):
                from run_m5_relationship_rehearsal import run

                run(
                    next(fixture),
                    args.exchange,
                    model_exchange=args.relationship_exchange or args.relationship_revisit,
                    revisit_only=args.relationship_revisit,
                )
                return
            campaign = Campaign(
                next(fixture),
                args.exchange,
                args.fixture,
                args.portrayal_retest or args.initiative_probe,
            )
            if args.initiative_probe:
                campaign.run_initiative_probe()
            else:
                campaign.run_campaign()
        finally:
            fixture.close()


if __name__ == "__main__":
    main()
