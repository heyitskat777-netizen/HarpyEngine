"""Separate structured model contracts for Handler and Director tasks."""

from typing import Any, Literal

from pydantic import Field

from girlframe.ai.contracts import Contract
from girlframe.ai.conversation import (
    ConversationReply,
    HandlerNeedPacket,
    HandlerNeedProposal,
    HandlerRequest,
)
from girlframe.ai.director_reactions import ReactionProposal
from girlframe.ai.gm_outcomes import OutcomePacket, OutcomeProposal
from girlframe.ai.model_transport import OpenAIResponses
from girlframe.ai.worldbuilding import WorldbuildingPacket, WorldbuildingProposal
from girlframe.engine.m3_handler_play_state import Play
from girlframe.scenes.campaign_time import Identity


class HandlerDraft(Contract):
    disposition: Literal["answer", "clarification", "requires_engine_workflow"]
    text: str = Field(min_length=1, max_length=1200)
    source_refs: tuple[str, ...] = Field(default=(), max_length=3)
    clock_receipt: Identity | None = None
    handler_action: str | None = Field(default=None, max_length=600)
    handler_play_offer: Play | None = None
    handler_concern: str | None = Field(default=None, max_length=300)


class ModelHandler:
    def __init__(self, client: OpenAIResponses):
        self.client = client

    def respond(self, request: HandlerRequest) -> ConversationReply:
        if request.response_need is None or request.response_need.action != "RESPOND":
            raise ValueError("Use the engine-approved response need.")
        draft = self.client.generate(
            "You portray the appointed Handler using your own playbook and dossier. Use the "
            "playbook's routine voice, pressure and recovery tendencies and your own character "
            "notes to shape your reply. Express priorities in what you address first and repair "
            "habits in what you do after mistakes. Keep portrayal notes, starting history and "
            "closed-scene experiences private. Carry forward only the named Pilot's own prior "
            "experience. A declined offer is a reason to ask or wait before offering that help "
            "again, and a completed handoff or kept promise can inform who you defer to. "
            "Give current requests precedence and use the approved reason for this reply. "
            "Cite each required reference and only references in the "
            "current scene. Closed-scene reports are private background pending local disclosure. "
            "Use the supplied fictional clock for pacing. Cite its exact clock_receipt to state "
            "the current minute, cutoff or deadline status. Use ordinary sources for other facts. "
            "The clock never creates knowledge, a consequence or a player choice. "
            "Acknowledge uncertainty, choices or refusals, and act only for the Handler. "
            "You can suggest an eligible native Play for review. You cannot resolve it or speak "
            "for another actor. Follow through only on what someone actually reported. Be brief.",
            request.model_dump(mode="json"),
            HandlerDraft,
        )
        return ConversationReply(
            route="handler", provider="reviewed-handler-v1", **draft.model_dump()
        )


class ModelHandlerNeeds:
    def __init__(self, client: OpenAIResponses):
        self.client = client

    def propose(self, packet: HandlerNeedPacket) -> HandlerNeedProposal:
        candidate = self.client.generate(
            "Propose whether this Handler has a reason to respond. Use WAIT when the scene "
            "needs no additional intervention or the Handler's playbook suggests holding back. "
            "Use the Handler's priorities, intervention instinct and the current Pilot's "
            "reviewed past experiences to choose among plausible responses to heard evidence. "
            "A past refusal, handoff or promise does not establish a new need to respond. "
            "A clock update alone is not a reason to speak. Use timing alongside a heard need. "
            "For indirect, personal, or follow-up needs "
            "quote exact heard speech. Use the actual open concern and required scoped evidence. "
            "Use an optional cue only when allowed by the Handler playbook. A reviewer decides.",
            packet.model_dump(mode="json"),
            HandlerNeedProposal,
        )
        if candidate.request_id != packet.request_id:
            raise ValueError("Retain the actual response-need request.")
        return candidate


class ModelOutcomes:
    def __init__(self, client: OpenAIResponses):
        self.client = client

    def propose(self, packet: OutcomePacket) -> OutcomeProposal:
        if packet.operation == "table":
            raise ValueError("The actual GM selects table outcomes.")
        data = packet.model_dump(mode="json", exclude={"gm_private_context"})
        # Provide actual scene declarations and typed/native evidence. Full campaign
        # snapshots and bookkeeping are available to the original facilitator.
        data["scene_history"] = packet.gm_private_context.get("history", [])
        if "fictional_time" in packet.gm_private_context:
            data["fictional_time"] = packet.gm_private_context["fictional_time"]
        candidate = self.client.generate(
            "Propose a rules outcome for the exact native action, its owned choices and its "
            "recorded roll. Assess the declared task and committed traits. Cite actual evidence. "
            "Use a held Keep when intent, prerequisites or target response are unresolved. "
            "Follow the native answer contract. Keep private reasoning out of result prose. "
            "Fictional time is context. Preserve the recorded time and the exact native roll. "
            "Do not claim a result has committed or dictate a player's choice.",
            data,
            OutcomeProposal,
        )
        if candidate.request_id != packet.request_id:
            raise ValueError("Retain the actual GM outcome request.")
        return candidate


class ModelWorldbuilding:
    def __init__(self, client: OpenAIResponses):
        self.client = client

    def propose(self, packet: WorldbuildingPacket) -> WorldbuildingProposal:
        data = packet.model_dump(mode="json", exclude={"canonical_state", "native_guard"})
        data["world"] = packet.canonical_state.get("world")
        candidate = self.client.generate(
            packet.instructions + " Use the current Fronts as pressures and unresolved choices. "
            "Ready status does not resolve a complication or advance fictional time.",
            data,
            WorldbuildingProposal,
        )
        if candidate.request_id != packet.request_id:
            raise ValueError("Retain the actual worldbuilding request.")
        return candidate


class ModelReactions:
    def __init__(self, client: OpenAIResponses):
        self.client = client

    def propose(self, packet: dict[str, Any]) -> ReactionProposal:
        role = packet["role"]
        if role["actor"]["kind"] != "npc":
            raise ValueError("Use the cast NPC reaction workflow.")
        candidate = self.client.generate(
            "Propose one optional reaction for this actor. Use their known speech, owned "
            "dossier, currently known fronts and available actions. Waiting or declining "
            "can be appropriate. Never speak for a Pilot or grant a new effect. "
            "The actual controller reviews the proposal.",
            {"request_id": packet["request_id"], "role": role},
            ReactionProposal,
        )
        if candidate.request_id != packet["request_id"]:
            raise ValueError("Retain the actual NPC reaction request.")
        return candidate
