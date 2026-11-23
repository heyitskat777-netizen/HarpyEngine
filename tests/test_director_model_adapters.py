"""Local wire-contract rehearsals. The transport never contacts an external endpoint."""

import json
from urllib.request import Request

import pytest
from test_director_activity_scene import P2Scene, input_command
from test_director_continuity import roles
from test_director_conversation import routed as routed
from test_director_observation import observed as observed
from test_director_observation import send
from test_director_worldbuilding import detail, ready
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Gateway, answer, pass_tags, start, state, tick

from girlframe.ai.gm_outcomes import OutcomePacket
from girlframe.ai.gm_protocol import Demand, TaskFrame
from girlframe.ai.model_adapters import (
    HandlerDraft,
    ModelOutcomes,
    ModelReactions,
    _handler_portrayal,
)
from girlframe.ai.model_transport import ModelLimits, ModelUnavailable, OpenAIResponses
from girlframe.delivery.m2_worker import GameWorker
from girlframe.engine.m3_handler_character import PROFILES
from girlframe.engine.m3_handler_state import HandlerNotes
from girlframe.services.onboarding import WorkflowError


class Recorder:
    def __init__(self, output):
        self.packets, self.result, self.requests = [], output, []

    def __call__(self, request: Request, timeout: float) -> bytes:
        envelope = json.loads(request.data)
        self.requests.append(envelope)
        assert request.full_url == "https://api.openai.com/v1/responses"
        assert envelope["store"] is False and "tools" not in envelope and timeout == 20
        packet = json.loads(envelope["input"][1]["content"])["packet"]
        self.packets.append(packet)
        result = self.result(packet) if callable(self.result) else self.result
        if isinstance(result, bytes):
            return result
        return json.dumps(
            {
                "status": "completed",
                "output": [
                    {
                        "role": "assistant",
                        "type": "message",
                        "content": [{"type": "output_text", "text": json.dumps(result)}],
                    }
                ],
            }
        ).encode()

    def client(self, attempts=5):
        return OpenAIResponses(
            model="synthetic-contract",
            api_key="inert-fixture",
            limits=ModelLimits(attempts=attempts, output_tokens=1000),
            post=self,
        )


def test_handler_speech_habits_cover_every_playbook_and_preserve_personal_notes():
    notes = HandlerNotes(voice="I use long, deliberate sentences.", personality="dry")
    stored = notes.model_dump(mode="json")
    cadence = set()
    for profile in PROFILES.values():
        packet = _handler_portrayal({"character_notes": stored}, notes, profile)
        assert packet["character_notes"] == stored
        assert packet["personality_prompt"]
        habits = packet["speech_habits"]
        assert set(habits) == {"cadence", "under_pressure", "tell"}
        assert all(habits.values())
        cadence.add(habits["cadence"])
    assert len(cadence) == len(PROFILES)
    assert _handler_portrayal({}, None, None) == {}


def test_model_handler_failure_and_same_command_retry_preserve_scoped_draft(routed):
    observer, context, scene, game, dice = routed
    recorder = Recorder(b'{"status":"incomplete"}')
    app = P2Scene.model_fixture(context, recorder.client())
    before = state(game)
    entries = len(app.timeline(PLAYER, scene)["entries"])
    quiet = input_command(observer, PLAYER, scene, "silence", "I tidy the spare gloves.")
    app.submit(PLAYER, scene, quiet)
    assert recorder.requests == []
    cmd = input_command(observer, PLAYER, scene, "respond", "Handler, what is the objective?")
    with pytest.raises(WorkflowError, match="CONVERSATION_UNAVAILABLE"):
        app.submit(PLAYER, scene, cmd)
    assert len(app.timeline(PLAYER, scene)["entries"]) == entries + 2
    assert not app.gm_work(ADMIN, scene)["handler_drafts"]
    recorder.result = lambda packet: {
        "disposition": "answer",
        "source_refs": [
            next(x["id"] for x in packet["context"]["references"] if x["topic"] == "objective")
        ],
        "text": "Inspect the relay and report what you observe.",
        "handler_action": "I set my own map on the table.",
    }
    receipt = app.submit(PLAYER, scene, cmd)
    assert app.submit(PLAYER, scene, cmd) == receipt
    assert len(recorder.requests) == 2
    packet = json.dumps(recorder.packets[-1])
    assert all(
        secret not in packet
        for secret in (
            "SYNTHETIC_GM_SECRET_CANARY",
            "SYNTHETIC_PC_ONLY_REFERENCE",
            "canonical_state",
        )
    )
    draft = app.gm_work(ADMIN, scene)["handler_drafts"][0]["id"]
    _, pilot = roles(observer, scene)
    assert len(app.timeline(PLAYER, scene)["entries"]) == entries + 2
    app.approve_handler(ADMIN, "review", scene, draft, "Verified scope.", (pilot,))
    app.deliver_handler(ADMIN, "deliver", scene, draft)
    assert app.timeline(PLAYER, scene)["entries"][-1]["kind"] == "handler"
    assert not any(x["kind"] == "handler" for x in app.timeline(OTHER, scene)["entries"])
    assert state(game) == before and dice.calls == 0


def test_typed_model_ruling_waits_for_the_actual_owner_and_preserves_the_roll(routed):
    observer, context, scene, game, dice = routed
    recorder = Recorder(
        lambda packet: {
            "request_id": packet["request_id"],
            "decision": {
                "kind": "keep",
                "verdict": "enough",
                "narration": "The needle stayed on the mark.",
                "assessments": [
                    {
                        "demand_id": "control",
                        "sufficient": True,
                        "evidence_ids": ["source", "native", "traits"],
                        "traits": [{"trait": "in_control", "polarity": "are"}],
                        "private_reason": "The committed positive traits include control.",
                    }
                ],
            },
            "cited_evidence": ["source", "native"],
            "private_reasoning": "Decide only the declared action.",
        }
    )
    app = P2Scene.model_fixture(context, Recorder({}).client(), recorder.client())
    timeline = app.timeline(PLAYER, scene)
    action = start(game, context="Hold the relay needle on the marked limit.")
    tick(GameWorker(game), Gateway())
    pass_tags(game)
    answer(game, PLAYER, "actor_keep", options=("tough", "in_control"), denied=("desperate",))
    item = next(x for x in app.gm_work(ADMIN, scene)["outcome_sources"] if x["action_id"] == action)
    frame = TaskFrame(
        stakes="Hold the mark.",
        demands=(Demand(id="control", question="Was the needle held?"),),
        response_scope="self",
    )
    opened = app.open_ruling(ADMIN, "open", scene, item["source_kind"], item["source_id"], frame)
    payload = {"request": opened["id"]}
    before = state(game)
    proposal = app.write(ADMIN, "generate", scene, "ruling-generate", payload)
    assert app.write(ADMIN, "generate", scene, "ruling-generate", payload) == proposal
    assert len(recorder.requests) == 1 and app.timeline(PLAYER, scene) == timeline
    assert "gm_private_context" not in recorder.packets[0]
    assert "SYNTHETIC_GM_SECRET_CANARY" not in json.dumps(recorder.packets[0])
    assert state(game) == before
    with pytest.raises(WorkflowError):
        app.confirm_ruling(OTHER, "wrong-owner", scene, proposal["id"])
    app.confirm_ruling(ADMIN, "confirm", scene, proposal["id"])
    assert app.play_results(PLAYER, scene, action)["state"] == "complete" and dice.calls == 1


def test_model_worldbuilding_proposal_stays_private_through_review(routed):
    ready(routed)
    observer, context, scene, game, _ = routed
    action = detail(text="The maintenance board has a public queue of inspections.")
    recorder = Recorder(
        lambda packet: {
            "request_id": packet["request_id"],
            "action": action.model_dump(mode="json"),
            "cited_evidence": ["source", "native"],
            "private_reasoning": "Grounded local detail.",
        }
    )
    app = P2Scene.model_fixture(context, Recorder({}).client(), recorder.client())
    world = app.session.worldbuilding
    _, source = send(observer, scene, "source-world", text="I stop by the maintenance board.")
    request = world.open(ADMIN, "request-world", scene, source.source_id)
    before = state(game)
    payload = {"request": request["id"]}
    result = app.write(ADMIN, "world-model", scene, "world-generate", payload)
    assert app.write(ADMIN, "world-model", scene, "world-generate", payload) == result
    assert len(recorder.requests) == 1 and state(game) == before
    assert "canonical_state" not in recorder.packets[0]
    world.review(ADMIN, "review-world", scene, result["id"], "approve", "Scope reviewed.")
    assert world.confirm(ADMIN, "confirm-world", scene, result["id"])["canon_committed"]
    handler, _ = roles(observer, scene)
    assert "maintenance board" not in context.build(ADMIN, scene, actor=handler).model_dump_json()


def test_reaction_only_sends_the_actor_projection_and_can_wait():
    recorder = Recorder(
        {"request_id": "episode", "kind": "WAIT", "rationale": "No reason to speak."}
    )
    adapter = ModelReactions(recorder.client())
    role = {"actor": {"kind": "npc"}, "question": "No newly heard speech."}
    proposal = adapter.propose(
        {
            "request_id": "episode",
            "role": role,
            "controller": "PRIVATE_OWNER",
            "gm_context": "PRIVATE_GM_MOTIVE",
        }
    )
    assert proposal.kind == "WAIT" and not proposal.text
    assert recorder.packets == [
        {
            "request_id": "episode",
            "role": role,
        }
    ]
    with pytest.raises(ValueError, match="cast NPC"):
        adapter.propose({"request_id": "episode", "role": {"actor": {"kind": "handler"}}})
    assert len(recorder.requests) == 1


def test_model_adapter_leaves_table_selection_to_the_gm():
    recorder = Recorder({})
    packet = OutcomePacket(
        request_id="table-request",
        scene_id="scene",
        source_kind="table",
        source_id="native-choice",
        operation="table",
        owner_id="1",
        evidence=(),
        native={},
        gm_private_context={},
    )
    with pytest.raises(ValueError, match="actual GM selects"):
        ModelOutcomes(recorder.client()).propose(packet)
    assert recorder.requests == []


def test_transport_rejects_unusable_envelope_and_cannot_send_after_budget():
    recorder = Recorder(
        {"disposition": "answer", "text": "A result.", "gm_decision": "unsupported"}
    )
    model = recorder.client(attempts=1)
    with pytest.raises(ModelUnavailable, match="usable"):
        model.generate("Role.", {"question": "fixture"}, HandlerDraft)
    with pytest.raises(ModelUnavailable, match="budget"):
        model.generate("Role.", {"question": "fixture"}, HandlerDraft)
    assert len(recorder.requests) == 1
