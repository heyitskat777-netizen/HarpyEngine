"""Assisted offline player-test console with durable synthetic state and native choices."""

import argparse
import json
from pathlib import Path
from uuid import uuid4

from p2_trial_runtime import Trial

HELP = """Synthetic personas: /as lark | kite | handler | gm
Text submits your persona's IC scene input. /retry resumes the last operation.
/work /campaign-work [PERIOD] /choices /decision ID /status /narrations
/play JSON (native PlayInput) /choice ID JSON /answer KIND JSON /roll ACTION
/battle-preview /battle-declare JSON (native Declaration) /grant [2,3]
GM: /frame JSON /propose KIND SOURCE /propose-next OPERATION /load REQUEST FILE /review PROPOSAL
GM declarations: /bind REVIEW ACTION /triage REVIEW PLAY DECISION note
Actual owner: /confirm PROPOSAL
GM memory: /memory /remember SOURCE lark,kite,handler [topic]
/archive ID,ID reason /advance SECONDS /pause /resume /reopen /quit
Files are saved in your synthetic trial directory. /propose exports a private packet,
a proposal template and JSON Schema. Fill the template, /load it, then review/confirm.
Model calls/cost: zero. Persona switching is a local test harness, not authentication.
"""


class Console:
    def __init__(self, trial):
        self.trial = trial
        self.state = trial.console_state
        self.state.setdefault("variables", {})

    def _resolve(self, factory):
        if "resolved" not in self.state["last"]:
            self.state["last"]["resolved"] = factory()
            self.trial.save()
        return self.state["last"]["resolved"]

    def execute(self, line):
        if line == "/retry":
            last = self.state.get("last")
            if not last or last["role"] != self.trial.role:
                raise ValueError("Use the original persona for the saved operation.")
            return self._execute(last["line"], last["key"], retry=True)
        for name, value in self.state["variables"].items():
            line = line.replace("$" + name, value)
        self.state["last"] = {"line": line, "key": str(uuid4()), "role": self.trial.role}
        self.trial.save()
        return self._execute(line, self.state["last"]["key"])

    def _execute(self, line, key, *, retry=False):
        from test_m2_game import state

        from girlframe.ai.gm_outcomes import OutcomeProposal
        from girlframe.ai.gm_protocol import TaskFrame
        from girlframe.engine.m2 import ChoiceAnswer, PlayInput
        from girlframe.engine.m3_actor_bonds import current_ref
        from girlframe.engine.m3_battle_state import Declaration
        from girlframe.services.director_shadow import DirectorShadowService
        from girlframe.services.m3_battle import BattleService
        from girlframe.services.m3_handler_plays import HandlerPlayService

        trial, viewer, scene = self.trial, self.trial.viewer, self.trial.scene
        command, _, argument = line.partition(" ")
        result = None
        if command == "/as":
            if argument not in trial.viewers():
                raise ValueError("Choose gm, handler, lark or kite.")
            trial.role = argument
            result = {"persona": trial.role, "authentication": "local_synthetic_fixture"}
        elif command == "/help":
            return {"help": HELP}
        elif command == "/work":
            result = trial.session.work(viewer, scene, gm=trial.role == "gm")
        elif command == "/campaign-work":
            result = trial.session.campaign_work(viewer, scene, period_id=argument or None)
        elif command == "/choices":
            result = trial.game.choices(viewer)
        elif command == "/decision":
            result = trial.game.decision(viewer, argument)
        elif command == "/status":
            result = trial.observer.status(viewer, scene).model_dump(mode="json")
        elif command == "/narrations":
            result = trial.session.contributions(viewer, scene)
        elif command == "/play":
            body = json.loads(argument)
            if (
                "context" not in body
                and trial.last_message
                and trial.last_message["role"] == trial.role
            ):
                body["context"] = trial.last_message["command"]["text"]
            value = PlayInput.model_validate_json(json.dumps(body))
            revision = self._resolve(
                lambda: {"revision": state(trial.game).sheets[str(viewer.user_id)].revision}
            )["revision"]
            result = trial.game.begin(viewer, key, trial.scene_channel, revision, value)
            self.state["variables"]["action"] = result["action_id"]
            trial.tick()
        elif command in ("/choice", "/answer"):
            identity, body = argument.split(" ", 1)
            value = ChoiceAnswer.model_validate_json(body)

            def selected():
                matches = (
                    [x for x in trial.game.choices(viewer) if x["id"] == identity]
                    if command == "/choice"
                    else [x for x in trial.game.choices(viewer) if x["kind"] == identity]
                )
                if len(matches) != 1:
                    raise ValueError("Choose one of your actual pending decisions by ID.")
                return {"identity": matches[0]["id"], "revision": matches[0]["revision"]}

            args = self._resolve(selected)
            result = trial.game.respond(viewer, key, args["identity"], args["revision"], value)
            trial.tick()
        elif command == "/roll":
            result = trial.game.roll(viewer, key, argument)
            trial.tick()
        elif command == "/battle-preview":
            result = BattleService(trial.store).preview(viewer, trial.scene_channel)
        elif command == "/battle-declare":
            revision = self._resolve(lambda: {"revision": state(trial.game).revision})["revision"]
            result = BattleService(trial.store).propose(
                viewer,
                key,
                revision,
                trial.scene_channel,
                Declaration.model_validate_json(argument),
            )
            self.state["variables"]["battle"] = result["id"]
        elif command == "/grant":
            args = self._resolve(
                lambda: {
                    "revision": state(trial.game).revision,
                    "targets": [
                        current_ref(state(trial.game), int(x)).model_dump(mode="json")
                        for x in json.loads(argument)
                    ],
                }
            )
            from girlframe.engine.m3_actor_state import ActorRef

            result = HandlerPlayService(trial.store).start(
                viewer,
                key,
                args["revision"],
                tuple(ActorRef.model_validate_json(json.dumps(x)) for x in args["targets"]),
            )
            self.state["variables"]["grant"] = result["id"]
        elif command == "/bind":
            self._gm()
            review, action = argument.split()
            result = trial.session.bind_action(viewer, key, scene, review, action)
        elif command == "/triage":
            self._gm()
            review, play, decision, note = argument.split(" ", 3)
            revision = self._resolve(
                lambda: {
                    "fingerprint": trial.session.reviews.gm(viewer, scene, review)["fingerprint"]
                }
            )["fingerprint"]
            result = trial.session.reviews.review(
                viewer, key, scene, review, revision, play, decision, note
            )
        elif command == "/frame":
            self._gm()
            frame = TaskFrame.model_validate_json(argument)
            self.state["frame"] = frame.model_dump(mode="json")
            result = {"frame": self.state["frame"]}
        elif command in ("/propose", "/propose-next"):
            self._gm()
            if command == "/propose-next":

                def selected_source():
                    matches = [
                        x
                        for x in trial.session.work(viewer, scene, gm=True)["outcome_sources"]
                        if x["operation"] == argument
                    ]
                    if len(matches) != 1:
                        raise ValueError("Choose the exact source from /work with /propose.")
                    return {"kind": matches[0]["source_kind"], "identity": matches[0]["source_id"]}

                selected = self._resolve(selected_source)
                kind, identity = selected["kind"], selected["identity"]
            else:
                kind, identity = argument.split(" ", 1)
            frame = (
                TaskFrame.model_validate_json(json.dumps(self.state["frame"]))
                if self.state.get("frame")
                else None
            )
            result = trial.session.outcomes.open(viewer, key, scene, kind, identity, frame)
            packet = trial.session.outcomes.packet(viewer, scene, result["id"])
            destination = trial.directory / result["id"].replace(":", "-")
            destination.mkdir(mode=0o700, exist_ok=True)
            self._private_json(destination / "request.json", packet.model_dump(mode="json"))
            if not (destination / "proposal.json").exists():
                self._private_json(
                    destination / "proposal.json",
                    {
                        "request_id": packet.request_id,
                        "decision": {"kind": packet.operation},
                        "cited_evidence": ["source", "native"],
                        "private_reasoning": "Enter the facilitator's evidence-based reasoning.",
                    },
                )
            self._private_json(destination / "schema.json", OutcomeProposal.model_json_schema())
            self.state["variables"]["request"] = result["id"]
            result = {
                **result,
                "directory": str(destination),
                "notice": "GM-private; fill required decision fields before /load.",
            }
        elif command == "/load":
            self._gm()
            request, filename = argument.split(" ", 1)
            value = OutcomeProposal.model_validate_json(Path(filename).read_text())
            result = trial.session.outcomes.propose(viewer, key, scene, request, value)
            self.state["variables"]["proposal"] = result["id"]
        elif command == "/review":
            result = trial.session.outcomes.owner_review(viewer, scene, argument)
        elif command == "/confirm":
            result = trial.session.outcomes.confirm(viewer, key, scene, argument)
            trial.tick()
        elif command == "/memory":
            self._gm()
            result = trial.context.build(viewer, scene).model_dump(mode="json")
        elif command == "/remember":
            self._gm()
            source, roles, *topic = argument.split()
            result = trial.remember(
                source,
                tuple(roles.split(",")) if roles != "-" else (),
                topic[0] if topic else "general",
            )
        elif command == "/archive":
            self._gm()
            ids, reason = argument.split(" ", 1)
            revision = self._resolve(
                lambda: {"revision": trial.context.build(viewer, scene).revision}
            )["revision"]
            result = trial.context.archive(
                viewer,
                key,
                scene,
                revision,
                tuple(ids.split(",")),
                reason,
            )
        elif command == "/advance":
            seconds = int(argument)
            if not 0 <= seconds <= 3600:
                raise ValueError("Advance the synthetic clock by 0–3600 seconds.")
            self._gm()
            trial.clock.now = self._resolve(lambda: {"clock": trial.clock.now + seconds})["clock"]
            batch = trial.observer.claim_review(scene)
            result = (
                DirectorShadowService(trial.context).evaluate(viewer, scene, batch.run_id)
                if batch
                else {"status": "no_eligible_batch"}
            )
        elif command in ("/pause", "/resume"):
            revision = self._resolve(lambda: {"revision": trial.store.status(viewer)["revision"]})[
                "revision"
            ]
            result = trial.store.safety(viewer, key, revision, pause=command == "/pause")
        elif command == "/reopen":
            trial.restart_services()
            result = {
                "status": "services_reopened",
                "work": trial.session.work(viewer, scene, gm=trial.role == "gm"),
            }
        elif command.startswith("/"):
            raise ValueError("Unknown command; use /help.")
        else:
            result = trial.retry() if retry else trial.message(line, command_key=key)
            self.state["variables"]["source"] = result["input"]["source_id"] or ""
            if result.get("conversation") and result["conversation"]["gm"].get("play_review_id"):
                self.state["variables"]["review"] = result["conversation"]["gm"]["play_review_id"]
        trial.save()
        return result

    def _gm(self):
        if self.trial.role != "gm":
            raise ValueError("Select the synthetic GM persona for private facilitator work.")

    @staticmethod
    def _private_json(path, value):
        path.write_text(json.dumps(value, indent=2) + "\n")
        path.chmod(0o600)


def run_demo(console):
    """Explicit fixture choices and facilitator interpretation, not an AI player or GM."""
    from girlframe.ai.gm_outcomes import KeepOutcome, OutcomeNarration, OutcomeProposal
    from girlframe.ai.gm_protocol import Assessment, TraitClaim

    def step(line):
        print(console.trial.role + "> " + line)
        result = console.execute(line)
        print(json.dumps(result, indent=2))
        return result

    print("DEMO: all owner choices and GM interpretations below are explicit synthetic fixtures.")
    step("Handler, what is the established objective?")
    step("GM, I choose Keep Your Head to hold the calibration needle steady.")
    step('/play {"play":"keep_your_head","heat":0,"trigger_confirmed":true}')
    for role in ("lark", "kite", "gm"):
        step("/as " + role)
        step('/answer tag_window {"options":["pass"]}')
    step("/as lark")
    step('/answer actor_keep {"options":["tough","in_control"],"denied":["desperate"]}')
    step("/as gm")
    step("/bind $review $action")
    step(
        '/frame {"stakes":"Hold the needle steady","demands":'
        '[{"id":"control","question":"Can the pilot maintain deliberate precision?"}]}'
    )
    request = step("/propose-next keep")
    packet = json.loads((Path(request["directory"]) / "request.json").read_text())
    proposal = OutcomeProposal(
        request_id=packet["request_id"],
        decision=KeepOutcome(
            verdict="enough",
            narration="The pilot keeps the needle steady.",
            assessments=(
                Assessment(
                    demand_id="control",
                    sufficient=True,
                    evidence_ids=("source", "native", "traits"),
                    traits=(TraitClaim(trait="in_control", polarity="are"),),
                    private_reason="Explicit fixture control assessment.",
                ),
            ),
        ),
        cited_evidence=("source", "native"),
        private_reasoning="Explicit offline fixture judgment.",
    )
    path = Path(request["directory"]) / "proposal.json"
    Console._private_json(path, proposal.model_dump(mode="json"))
    saved = step("/load " + request["id"] + " " + str(path))
    step("/review " + saved["id"])
    step("/confirm " + saved["id"])
    step("/retry")
    request = step("/propose-next narration")
    packet = json.loads((Path(request["directory"]) / "request.json").read_text())
    proposal = OutcomeProposal(
        request_id=packet["request_id"],
        decision=OutcomeNarration(
            text="The committed Keep ruling leaves the needle steady.", effect_refs=("tier",)
        ),
        cited_evidence=("source", "native"),
        private_reasoning="Readback adds no mechanical effect.",
    )
    path = Path(request["directory"]) / "proposal.json"
    Console._private_json(path, proposal.model_dump(mode="json"))
    saved = step("/load " + request["id"] + " " + str(path))
    readback = step("/confirm " + saved["id"])
    step("/remember " + readback["id"] + " lark,kite,handler status")
    step("/as lark")
    step("/reopen")
    step("/narrations")
    print("Demo finished. Reopen this saved trial for assisted synthetic player testing.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--new", type=Path)
    group.add_argument("--resume", type=Path)
    parser.add_argument("--commands", type=Path, help="Optional JSON array of console commands")
    parser.add_argument(
        "--demo", action="store_true", help="Run an explicit fixture demonstration and save it"
    )
    args = parser.parse_args()
    if args.demo and (not args.new or args.commands):
        parser.error("--demo needs a fresh --new directory and cannot combine with --commands")
    print("SYNTHETIC PLAYER TEST — invented data only; no network/model/Discord delivery.")
    print(HELP)
    trial = Trial(args.new or args.resume, create=bool(args.new))
    console = Console(trial)
    commands = iter(json.loads(args.commands.read_text())) if args.commands else None
    rejected = 0
    try:
        if args.demo:
            run_demo(console)
        while True:
            if args.demo:
                break
            try:
                line = next(commands) if commands is not None else input(trial.role + "> ")
            except (EOFError, StopIteration):
                break
            if line == "/quit":
                break
            try:
                result = console.execute(line)
                print(json.dumps(result, indent=2))
            except Exception as error:
                from girlframe.services.onboarding import WorkflowError

                if not isinstance(error, (WorkflowError, ValueError, KeyError, StopIteration)):
                    raise
                print(f"Rejected: {error}")
                rejected += 1
            finally:
                trial.save()
    finally:
        trial.close()
    print(f"Saved synthetic trial: {trial.directory}. External tokens/cost: 0.")
    return int(commands is not None and rejected > 0)


if __name__ == "__main__":
    raise SystemExit(main())
