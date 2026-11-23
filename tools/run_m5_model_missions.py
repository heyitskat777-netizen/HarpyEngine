"""Exercise a synthetic Session Zero and mission with a role-only decision exchange."""

import argparse
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from time import monotonic, sleep

import pytest
from run_m5_briefing_rehearsal import ROOT, MissionBrief
from test_activity_shadow_readiness import publish_opening
from test_ledger import ADMIN, OTHER, PLAYER, ledger
from test_m2_game import answer, pass_tags, state
from test_m5_activity_batch import SECRET, WAIT, RelayRehearsal, deliver_handler
from test_m5_handler_comparison import approve, delivered_to
from test_punishment_service import submit
from test_session_zero import FACILITATOR

from girlframe.engine.m2 import PlayInput
from girlframe.engine.m3_handler_state import HandlerNotes
from girlframe.engine.m3_punishments import Details
from girlframe.services.m3_punishments import PunishmentService
from girlframe.services.onboarding import WorkflowError

PILOTS = {"Lark": PLAYER, "Kite": OTHER}
DECK = ROOT / "tools" / "fixtures" / "m5_model_missions.json"


def write_json(path, data):
    staging = path.with_suffix(".tmp")
    staging.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    staging.replace(path)


def replay_decision(directory, number, packet):
    def read(kind):
        return json.loads((directory / f"{kind}-{number:02}.json").read_text())

    original = read("request")
    result = read("decision")
    ids = {}
    actors = {}
    for group, identifier, fields in (
        ("references", "id", ("topic", "text", "classification")),
        ("reports", "source_id", ("text", "classification", "revision")),
        ("recent_contributions", "reference", ("text", "own_action", "open_offer")),
    ):
        for before, after in zip(original[group], packet[group], strict=True):
            assert all(before[field] == after[field] for field in fields)
            ids[before[identifier]] = after[identifier]
            if group == "reports":
                actors[json.dumps(before["speaker"], sort_keys=True)] = after["speaker"]
    decision = result["decision"]
    for field in ("source_refs", "report_ids"):
        if field in decision:
            decision[field] = [ids.get(identity, identity) for identity in decision[field]]
    if decision["kind"] == "NPC_DIALOGUE":
        if "intended_recipients" in decision:
            decision["intended_recipients"] = [
                actors[json.dumps(actor, sort_keys=True)]
                for actor in decision["intended_recipients"]
            ]
        else:
            # Older captures used the original report speakers as the delivery audience.
            decision["intended_recipients"] = list(
                {
                    json.dumps(report["speaker"], sort_keys=True): report["speaker"]
                    for report in packet["reports"]
                    if report["source_id"] in decision["report_ids"]
                }.values()
            )
    fiction = decision.get("fiction") or {}
    if fiction.get("follows_offer"):
        identity = fiction["follows_offer"]
        fiction["follows_offer"] = ids.get(identity, identity)
    return result


class ModelMission(RelayRehearsal):
    def __init__(self, store, playbook, scenario, exchange, fixture, replay):
        self.calls = []
        self.exchange = exchange
        self.fixture = fixture
        self.replay = replay
        self.output = self.answer
        super().__init__(
            store,
            playbook,
            brief=MissionBrief(**scenario["brief"]),
            notes=HandlerNotes(**scenario["notes"]),
        )

    def post(self, request, timeout):
        body = json.loads(request.data)
        destination = self.exchange / "contract.json"
        if not destination.exists():
            write_json(
                destination,
                {
                    "instructions": body["input"][0]["content"],
                    "contract": json.loads(body["input"][1]["content"])["contract"],
                },
            )
        return super().post(request, timeout)

    def answer(self, packet):
        number = self.beat_number
        write_json(self.exchange / f"request-{number:02}.json", packet)
        if self.fixture:
            self.decision = {"decision": WAIT}
            return WAIT
        path = self.exchange / f"decision-{number:02}.json"
        if self.replay:
            write_json(path, replay_decision(self.replay, number, packet))
        deadline = monotonic() + 1200
        while not path.is_file() and monotonic() < deadline:
            sleep(0.25)
        if not path.is_file():
            raise TimeoutError(f"Missing {path}")
        self.decision = json.loads(path.read_text())
        return self.decision["decision"]

    def hear_draft(self, draft, number):
        preview = self.app.read(ADMIN, self.scene, "handler-draft", draft)
        listeners = [preview["source_actor"]]
        listeners.extend(listener["actor"] for listener in preview.get("additional_listeners", []))
        if "intended_listeners" in preview:
            listeners = [listener["actor"] for listener in preview["intended_listeners"]]
        lengths = {name: len(delivered_to(self, viewer)) for name, viewer in PILOTS.items()}
        try:
            approve(self, draft, f"review:{number}", *listeners)
        except WorkflowError as error:
            self.app.write(
                ADMIN,
                f"withhold:{number}",
                self.scene,
                "handler-reject",
                {"draft": draft, "reason": "The synthetic delivery checks rejected the draft."},
            )
            return {}, str(error).partition(":")[0]
        assert all(
            len(delivered_to(self, viewer)) == lengths[name] for name, viewer in PILOTS.items()
        )
        receipt = deliver_handler(self, draft, f"deliver:{number}")
        assert not receipt["effects_applied"]
        assert deliver_handler(self, draft, f"retry:{number}") == receipt
        heard = {}
        for name, viewer in PILOTS.items():
            new = delivered_to(self, viewer)[lengths[name] :]
            assert len(new) <= 1
            if new:
                heard[name] = {"text": new[0]["text"], "action": new[0].get("action")}
        assert len(heard) == len(listeners)
        return heard, None

    def play_keep(self, native, *, key="staged-keep"):
        self.dice.faces = (4, 5)
        started = self.game.begin(
            PLAYER,
            key,
            self.scene_channel,
            state(self.game).sheets["2"].revision,
            PlayInput(
                play="keep_your_head", context=native["intent"], trigger_confirmed=True, heat=0
            ),
        )
        self.tick()
        pass_tags(self.game)
        answer(
            self.game, PLAYER, "actor_keep", options=("tough", "in_control"), denied=("desperate",)
        )
        answer(self.game, ADMIN, "handler_keep", flag=True, text=native["ruling"])
        self.tick()
        action = self.game.inspect(PLAYER, started["action_id"])
        assert action["state"] == "complete"
        return {**native, "action": action}

    def run_mission(self, scenario):
        self.line_count = 0
        zero, briefing = self.setup()
        mission = self.dispatch(zero, briefing)
        publish_opening(self.app, self.scene, FACILITATOR)
        self.line("private-canary", OTHER, SECRET, channel="private")
        assert any(
            row.get("text") == SECRET for row in self.app.timeline(OTHER, self.scene)["entries"]
        )
        assert SECRET not in json.dumps(self.app.timeline(PLAYER, self.scene))

        beats = []
        native = None
        for number, beat in enumerate(scenario["beats"], 1):
            self.beat_number = number
            for index, (speaker, text) in enumerate(beat["lines"], 1):
                self.line(f"beat:{number}:{index}", PILOTS[speaker], text)
                self.line_count += 1
            if beat.get("native"):
                native = self.play_keep(beat["native"])
            baseline = self.canon_and_time()
            pre_calls = len(self.calls)
            if not beat.get("native"):
                assert self.run_batch(119) is None and len(self.calls) == pre_calls
            self.decision = None
            outcome = self.run_batch(0 if beat.get("native") else 1)
            assert outcome
            if outcome == {"status": "wait", "reason": "pilot_requested_space"}:
                assert len(self.calls) == pre_calls
                gate = {"action": "WAIT", "reason": outcome["reason"]}
                trigger = "completed_play" if beat.get("native") else "quiet"
                write_json(self.exchange / f"skip-{number:02}.json", outcome)
            else:
                assert len(self.calls) == pre_calls + 1
                assert self.calls[-1]["has_completed_play"] == bool(beat.get("native"))
                gate = self.calls[-1]["response_need"]
                trigger = self.calls[-1]["trigger"]
            heard, review_block = (
                self.hear_draft(outcome["draft_id"], number)
                if outcome["status"] == "draft"
                else ({}, None)
            )
            assert self.canon_and_time() == baseline
            calls_after_review = len(self.calls)
            assert self.run_batch(0) is None and len(self.calls) == calls_after_review
            result = {
                "id": beat["id"],
                "input": beat["lines"],
                "trigger": trigger,
                "gate": gate,
                "decision": self.decision,
                "result": {key: value for key, value in outcome.items() if key != "draft_id"},
                "heard": heard,
                "review_block": review_block,
            }
            beats.append(result)
            write_json(self.exchange / "transcript.json", {"beats": beats})
        assert self.dice.calls == 1 and native is not None
        final = self.missions.end(
            ADMIN,
            "controller-end",
            mission["id"],
            mission["revision"],
            scenario["success"],
            debrief=scenario["debrief"],
        )
        if final["phase"] == "awaiting_consequences":
            discipline = PunishmentService(self.store, self.missions.access.registry)
            for index, item in enumerate(self.missions.get(ADMIN, mission["id"])["work"]):
                if discipline.get(ADMIN, item["id"])["state"] == "resolved":
                    continue
                submit(
                    discipline,
                    ADMIN,
                    item["id"],
                    Details(kind="stimulant_injection"),
                    f"close-dog-duty:{index}",
                )
            final = self.missions.complete(
                ADMIN, "close-after-work", mission["id"], final["revision"]
            )
        assert final["phase"] == "complete"
        summary = {
            "playbook": self.playbook,
            "session_zero": {
                "difficulty": "narrative",
                "handler_control": "ai",
                "pilots": list(PILOTS),
            },
            "brief": scenario["brief"],
            "pilot_lines": self.line_count,
            "beats": beats,
            "native_play": native,
            "dice_calls": self.dice.calls,
            "phase": final["phase"],
            "success": scenario["success"],
            "debrief": scenario["debrief"],
        }
        write_json(self.exchange / "transcript.json", summary)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("playbook", choices=tuple(json.loads(DECK.read_text())))
    parser.add_argument("directory", type=Path)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--fixture", action="store_true", help="Exercise the exchange with WAIT only."
    )
    mode.add_argument("--replay", type=Path, help="Replay saved decisions with current scoped IDs.")
    args = parser.parse_args()
    args.directory.mkdir(mode=0o700, parents=True)
    scenario = json.loads(DECK.read_text())[args.playbook]
    with (
        TemporaryDirectory(prefix="harpy-m5-model-mission-") as temp,
        pytest.MonkeyPatch.context() as patch,
    ):
        fixture = ledger.__wrapped__(Path(temp), patch)
        try:
            ModelMission(
                next(fixture), args.playbook, scenario, args.directory, args.fixture, args.replay
            ).run_mission(scenario)
        finally:
            fixture.close()


if __name__ == "__main__":
    main()
