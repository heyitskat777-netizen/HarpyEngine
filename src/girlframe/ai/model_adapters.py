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


class HandlerDraft(Contract):
    disposition: Literal["answer", "clarification", "requires_engine_workflow"]
    text: str = Field(min_length=1, max_length=1200)
    source_refs: tuple[str, ...] = Field(default=(), max_length=3)
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
            "reason for this reply. Cite each required reference and only references in the "
            "current scene. Closed-scene reports are private background pending local disclosure. "
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
            "needs no additional intervention. For indirect, personal, or follow-up needs "
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
        candidate = self.client.generate(
            "Propose a rules outcome for the exact native action, its owned choices and its "
            "recorded roll. Assess the declared task and committed traits. Cite actual evidence. "
            "Use a held Keep when intent, prerequisites or target response are unresolved. "
            "Follow the native answer contract. Keep private reasoning out of result prose. "
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
