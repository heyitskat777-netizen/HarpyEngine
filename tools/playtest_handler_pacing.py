"""Run one 100-input offline Handler pacing scene through the current engine."""

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

from p2_trial_runtime import Trial
from playtest_connected_director import private_json
from playtest_sustained_campaign import Campaign


@dataclass(frozen=True)
class Beat:
    text: str
    role: str = "lark"
    topic: str | None = None
    reply: str | None = None
    action: str | None = None
    concern: str | None = None
    need: str | None = None
    play: str | None = None
    private: bool = False
    single_listener: bool = False
    check: str | None = None


SCENES = {
    "barracks": {
        "objects": ("the spare seals", "the kettle", "the tall locker", "the window latch"),
        "beats": {
            17: Beat(
                "The alarm is still in my ears when I close my eyes.",
                topic="general",
                check="heard social opening with no reviewed need",
            ),
            22: Beat(
                "It would help to have company while I sort the seals.",
                topic="general",
                need="indirect_request",
                reply="Slide that box over. I'm lousy at sorting "
                "by colour, but I can read tiny numbers.",
                action="Anchor takes a stool and turns the label tray toward the light.",
                single_listener=True,
            ),
            26: Beat(
                "The inspection buzzer is stuck on test again.",
                topic="tactical",
                reply="I'll put the kettle on the far counter. Take a breath before "
                "you decide where you want to wait.",
                action="Anchor moves her own mug and leaves the bench free.",
            ),
            74: Beat(
                "Handler, can you remind me which locker is mine?",
                role="kite",
                reply="I don't have your assignment. The tag on my mug is about as "
                "far as my record keeping goes tonight.",
            ),
        },
    },
    "hallway": {
        "objects": ("the corridor map", "the stair rail", "the boot mat", "the shift board"),
        "beats": {
            29: Beat(
                "I see a violet strip behind the closed equipment shutter.",
                topic="tactical",
                private=True,
                check="unreported observation",
            ),
            30: Beat(
                "Handler, can you tell me what's behind the shutter?",
                role="kite",
                reply="I haven't had a report from behind it. I can wait here with you.",
            ),
            38: Beat(
                "The lower corridor is closed for inspection. The public ramp is open.",
                topic="briefing",
                reply="The lower corridor is closed for inspection. "
                "The public ramp is open. I'll pin the update where we can see it.",
                action="Anchor pins the update next to the ramp on her copy of the map.",
                play="brief",
            ),
            40: Beat(
                "I can see a blue reflection at the top of the ramp.",
                topic="tactical",
                reply="Blue at the top of the ramp. I'll leave a question mark by it. "
                "Can you tell what it is from where you are?",
                action="Anchor marks the spot on her map.",
                concern="Identify the blue reflection if the pilot can do so safely.",
            ),
            46: Beat(
                "I can see the blue reflection is from a service mirror.",
                topic="tactical",
                need="follow_up",
                reply="A mirror. Thank you for leaving the question open until you could see it.",
                action="Anchor replaces the question mark with the pilot's description.",
            ),
        },
    },
    "simulator": {
        "objects": ("the footrest", "the practice grid", "the headset cable", "the monitor stand"),
        "beats": {
            11: Beat(
                "Handler, can you repeat the starting position?",
                role="kite",
                reply="I don't have the starting position on this sheet. I'll wait while "
                "you check your own display.",
            ),
            33: Beat(
                "A red training indicator just lit up beside my seat.",
                topic="tactical",
                reply="I see your report. Keep your place if you want. I can stay on the "
                "line while you decide what to check.",
                action="Anchor sets her checklist down and stays at her own console.",
                concern="Check whether the pilot wants assistance with the training indicator.",
            ),
            35: Beat(
                "I decline to leave the seat to investigate the indicator.",
                topic="general",
                need="follow_up",
                reply="Then stay in the seat. I can take my copy of "
                "the checklist to the control desk when you're ready.",
                action="Anchor pulls her own copy free and leaves the pilot's controls alone.",
            ),
            44: Beat(
                "The simulation desk asks for a check-in before anyone resets the exercise.",
                role="kite",
                topic="tactical",
                reply="Check in with me before a reset. "
                "I need to know whose display I'm looking at first.",
                action="Anchor clips a check-in card to her own console.",
                play="expectation",
            ),
            45: Beat(
                "GM, I declare Check Your Sensors to inspect the public practice grid.",
                check="native Play referral",
            ),
        },
    },
    "debrief": {
        "objects": ("the notebook", "the damp jacket", "the debrief roster", "the reclaimed mug"),
        "beats": {
            20: Beat(
                "I could use a minute with someone before I try to explain the all-clear.",
                topic="general",
                need="indirect_request",
                reply="I've got a minute. We can sit until you feel like starting.",
                action="Anchor turns over her own recorder and takes the chair beside the door.",
                single_listener=True,
            ),
            39: Beat(
                "I told the room the ramp was clear. I want to correct that to unverified.",
                topic="tactical",
                reply="I'll keep the first account beside your correction. "
                "You came back to tell us. That matters.",
                action="Anchor leaves the original entry legible and writes the correction below.",
            ),
            54: Beat(
                "Handler, can you confirm who will read the corrected account?",
                role="kite",
                reply="I don't have a distribution list. You can ask the record owner "
                "before you send it anywhere.",
            ),
            64: Beat(
                "GM, can you explain whether that correction costs Heat?",
                check="explicit GM question",
            ),
            81: Beat(
                "I think I'll have my tea out here this time.",
                topic="general",
                check="heard ordinary preference",
            ),
        },
    },
}
ROUTINE = (
    "I move {obj} just enough to make room on my side.",
    "Can you see {obj} from your seat?",
    "I'll leave {obj} where it is until you finish.",
    "I wasn't talking about {obj}. I meant the little shelf beside it.",
    "Fine. I'll lay my things down beside {obj}.",
    "It helps to keep track of {obj} before we pack up.",
    "I compare the note in my pocket with the one beside {obj}.",
    "I can wait here. You tell me when you've finished with {obj}.",
    "I take a last look at {obj}, then go back to my own notes.",
    "The dust on {obj} must be older than this week's shift roster.",
    "That's my copy by {obj}. Yours is still where you left it.",
)


class PacingHandler:
    def __init__(self, beats):
        self.beats = {beat.text: beat for beat in beats.values()}
        self.calls = 0

    def respond(self, request):
        from girlframe.ai.conversation import ConversationReply

        self.calls += 1
        assert request.response_need.action == "RESPOND"
        assert request.persona and "Anchor" in request.persona.profile.background
        for phrase in ("PRIVATE_SUSTAINED_GM_MOTIVE", "violet strip"):
            assert phrase not in request.model_dump_json()
        beat = self.beats.get(request.question)
        refs = request.response_need.source_refs
        if beat and beat.need and request.response_need.reason != "reviewed_" + beat.need:
            return ConversationReply(
                route="handler",
                provider="reviewed-handler-v1",
                disposition="answer",
                text="I've logged the new report.",
                source_refs=refs,
            )
        # The engine can surface an unexpected trigger. Keep that evidence observable.
        reply = beat.reply if beat and beat.reply else "I'm listening. Is there something you need?"
        return ConversationReply(
            route="handler",
            provider="reviewed-handler-v1",
            disposition="answer" if refs else "clarification",
            text=reply,
            source_refs=refs,
            handler_action=beat.action if beat else None,
            handler_concern=beat.concern if beat else None,
            handler_play_offer=beat.play if beat else None,
        )


class Pacing(Campaign):
    def __init__(self, trial, scene, *, review_needs):
        self.scenario = SCENES[scene]
        self.review_needs = review_needs
        self.provider = PacingHandler(self.scenario["beats"])
        super().__init__(trial)
        self.rows = []
        self.hidden_source = None

    def rebuild(self):
        from girlframe.services.director_conversation import DirectorConversationService
        from girlframe.services.director_session import DirectorSessionService

        self.trial.session = DirectorSessionService(
            self.trial.context,
            conversation=DirectorConversationService(
                self.trial.context, handler=self.provider, handler_mode="reviewed"
            ),
        )

    def review_need(self, source, beat, reference):
        from girlframe.ai.conversation import HandlerNeedProposal

        t = self.trial
        service, gm, key = t.session.conversation, t.viewers()["gm"], f"need:{self.number}"
        opened = service.open_handler_need(gm, key, t.scene, source.source_id)
        packet = service.handler_need_packet(gm, t.scene, opened["id"])
        concern = packet.request.open_concerns[0].id if beat.need == "follow_up" else None
        proposal = HandlerNeedProposal(
            request_id=packet.request_id,
            action="RESPOND",
            kind=beat.need,
            speech_quote=beat.text,
            source_refs=(reference,) if reference else (),
            concern_id=concern,
            reason="Synthetic reviewer recognises a heard request or concern response.",
        )
        saved = service.propose_handler_need(gm, key + ":propose", t.scene, opened["id"], proposal)
        service.review_handler_need(
            gm, key + ":approve", t.scene, saved["id"], "approve", "Heard and scoped."
        )

    def route_beat(self, beat):
        from test_m2_game import state

        from girlframe.ai.gm_outcomes import HandlerOutcome
        from girlframe.ai.observation import AppendSceneInput
        from girlframe.engine.m3_handler_play_state import Effect
        from girlframe.services.m3_handler_plays import HandlerPlayService

        t, key = self.trial, f"pacing:{self.number}"
        gm, handler = [t.viewers()[x] for x in ("gm", "handler")]
        viewer = t.viewers()[beat.role]
        service = t.session.conversation
        t.clock.now += 6
        command = AppendSceneInput(
            command_key=key,
            expected_scene_revision=t.observer.status(viewer, t.scene).scene_revision,
            speaker="pilot",
            text=beat.text,
            fictional_channel="private" if beat.private else "comms",
        )
        source = t.observer.append_scene_input(viewer, t.scene, command)
        reference = None
        if beat.topic:
            recipients = (
                (beat.role,)
                if beat.private
                else (("handler", beat.role) if beat.single_listener else tuple(self.actors))
            )
            reference = self.learn(
                source.source_id,
                beat.text,
                recipients,
                basis="perception" if beat.private else "testimony",
                topic=beat.topic,
            )
        if beat.private:
            self.hidden_source = reference
            self.hidden.append((reference, beat.text))
        if beat.need and self.review_needs:
            self.review_need(source, beat, reference)
        gm_case = beat.text.startswith("GM,")
        before = (state(t.game).model_dump_json(), t.dice.calls) if gm_case else None
        result = t.session.submit(viewer, t.scene, command)
        route = result["conversation"]
        gate = route["handler_decision"]["decision"]
        gm_reply = route["gm"]["reply"]
        assert route["gm"]["publication"] == "private_reply_only"
        assert not any(x in gm_reply for x in ("handler_action", "handler_play_offer"))
        if gm_case:
            assert gm_reply["gm_decision"]["action"] == "RESPOND"
            assert route["handler"] is None
            assert before == (state(t.game).model_dump_json(), t.dice.calls)
        row = dict(
            turn=self.number,
            text=beat.text,
            role=beat.role,
            handler_gate=gate,
            gm=gm_reply,
            check=beat.check,
            expected_response=bool(beat.reply)
            and (self.review_needs or not beat.need or beat.topic == "tactical"),
            handler=None,
        )
        if route["handler"]:
            draft = route["handler"]["id"]
            raw = service.private_handler(gm, t.scene, draft)["reply"]
            assert not any(hidden in raw["text"] for _, hidden in self.hidden)
            names = (beat.role,) if beat.single_listener else ("lark", "kite")
            recipients = tuple(self.actors[x] for x in names)
            service.review_handler(
                gm,
                key + ":approve",
                t.scene,
                draft,
                "approve",
                "Synthetic review of scoped in-character contribution.",
                delivery_recipients=recipients,
            )
            preview = service.delivery.preview(handler, t.scene, draft)
            receipt = service.delivery.deliver(handler, key + ":deliver", t.scene, draft)
            assert service.delivery.deliver(handler, key + ":replay", t.scene, draft) == receipt
            for pilot in ("lark", "kite"):
                pilot_viewer = t.viewers()[pilot]
                shown = t.session.contributions(pilot_viewer, t.scene)
                assert (receipt["id"] in {x["id"] for x in shown}) == (pilot in names)
                known = t.context.build(pilot_viewer, t.scene, actor=self.actors[pilot])
                assert (receipt["reference"] in {x.id for x in known.references}) == (
                    pilot in names
                )
                assert (
                    self.hidden_source is None
                    or pilot == "lark"
                    or self.hidden_source not in {x.id for x in known.references}
                )
            row["handler"] = dict(
                text=preview["text"],
                action=preview["action"],
                receipt=receipt["id"],
                recipients=names,
                play=None,
            )
            if beat.play:
                grant = service.start_handler_play(handler, t.scene, draft, state(t.game).revision)
                opened = t.session.outcomes.open(
                    gm, key + ":play", t.scene, "handler_grant", grant["id"]
                )
                fields = dict(
                    detail="Report before resetting.", stakes="Delay the reset for a check."
                )
                effect = Effect(
                    kind=beat.play,
                    account=raw["text"],
                    **(fields if beat.play == "expectation" else {}),
                )
                proof = self.proposal(opened, HandlerOutcome(play=beat.play, effect=effect))
                assert proof["state"] == "complete"
                assert (
                    HandlerPlayService(t.store).notice(viewer, grant["id"])["state"] == "complete"
                )
                row["handler"]["play"] = beat.play
            replay = t.session.submit(viewer, t.scene, command)
            assert replay["conversation"]["handler"]["delivery_id"] == receipt["id"]
        self.rows.append(row)

    def run_scene(self, turns):
        self.setup()
        for self.number in range(1, turns + 1):
            i = self.number - 1
            obj = self.scenario["objects"][(i // len(ROUTINE) + i) % 4]
            beat = self.scenario["beats"].get(self.number) or Beat(
                ROUTINE[i % len(ROUTINE)].format(obj=obj),
                "lark" if i % 2 == 0 else "kite",
            )
            self.route_beat(beat)
            if self.number % 25 == 0:
                self.quiet_review()
                print(f"Routed {self.number} inputs", flush=True)
        assert {
            x["route"]
            for x in self.trial.session.contributions(
                self.trial.viewers()["handler"], self.trial.scene
            )
        } <= {"handler"}
        assert self.provider.calls == sum(bool(row["handler"]) for row in self.rows)
        assert all(bool(row["handler"]) == row["expected_response"] for row in self.rows)
        assert not any(self.trial.game.choices(v) for v in self.trial.viewers().values())
        if turns >= 50 and any(beat.concern for beat in self.scenario["beats"].values()):
            t = self.trial
            handler = self.actors["handler"]
            role = t.context.build(t.viewers()["handler"], t.scene, actor=handler)
            with t.store.engine.connect() as c:
                remaining = t.session.conversation.delivery.open_concerns(
                    c, t.scene, handler, self.actors["lark"], {ref.id for ref in role.references}
                )
            assert len(remaining) == (0 if self.review_needs else 1)
        self.trial.save()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scene", choices=SCENES, required=True)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--turns", type=int, default=100)
    parser.add_argument("--without-need-review", action="store_true")
    args = parser.parse_args()
    run = Pacing(
        Trial(args.directory, create=True), args.scene, review_needs=not args.without_need_review
    )
    try:
        run.run_scene(args.turns)
    finally:
        run.trial.close()
        private_json(args.directory / "pacing-events.json", run.rows)
    rows = run.rows
    lines = [f"# {args.scene.title()} pacing rehearsal", ""]
    for row in rows:
        gate = row["handler_gate"]
        lines += [
            f"{row['turn']:03}. **{row['role']}** {row['text']}",
            f"   - Handler gate `{gate['action']}:{gate['reason']}`",
        ]
        handler = row["handler"]
        if handler:
            lines.append("   - **Anchor** " + handler["text"])
            if handler["action"]:
                lines.append("   - **Anchor acts** " + handler["action"])
            if handler["play"]:
                lines.append("   - **Native Handler Play** " + handler["play"])
        if row["gm"]["gm_decision"]["action"] == "RESPOND":
            lines.append("   - **GM engine** " + row["gm"]["text"])
        lines.append("")
    output = args.directory / "transcript.md"
    output.write_text("\n".join(lines))
    output.chmod(0o600)
    print(
        json.dumps({"scene": args.scene, "inputs": len(rows), "handler_calls": run.provider.calls})
    )


if __name__ == "__main__":
    main()
