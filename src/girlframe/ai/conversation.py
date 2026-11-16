"""Separate zero-cost GM/Handler request types and deterministic response policy."""

import re
from typing import Literal, Protocol

from pydantic import Field, JsonValue, model_validator

from girlframe.ai.contracts import Contract
from girlframe.ai.director import DirectorContext, KnowledgeReference
from girlframe.ai.observation import Observation

Route = Literal["gm", "handler"]


class HandlerRequest(Contract):
    schema_version: Literal[1] = 1
    question: str = Field(min_length=1, max_length=1000)
    context: DirectorContext

    @model_validator(mode="after")
    def handler_boundary(self) -> "HandlerRequest":
        if (
            self.context.audience != "actor"
            or self.context.actor is None
            or self.context.actor.kind != "handler"
        ):
            raise ValueError("Handler request requires its isolated actual Handler context")
        return self


class GMRequest(Contract):
    schema_version: Literal[1] = 1
    question: str = Field(min_length=1, max_length=1000)
    context: DirectorContext
    canonical_state: dict[str, JsonValue]
    engine_records: dict[str, list[dict[str, JsonValue]]]
    scene_inputs: tuple[Observation, ...] = Field(max_length=100)
    scene_inputs_omitted: int = Field(default=0, ge=0)
    recipient_references: tuple[KnowledgeReference, ...]

    @model_validator(mode="after")
    def gm_boundary(self) -> "GMRequest":
        if self.context.audience != "gm" or self.context.actor is not None:
            raise ValueError("GM request requires its separate campaign GM context")
        return self


class ConversationReply(Contract):
    schema_version: Literal[1] = 1
    route: Route
    disposition: Literal["answer", "clarification", "requires_engine_workflow"]
    text: str = Field(min_length=1, max_length=6000)
    source_refs: tuple[str, ...] = Field(default=(), max_length=3)
    play_id: str | None = None
    application: Literal["blocked"] = "blocked"
    provider: Literal["synthetic-conversation-v1"] = "synthetic-conversation-v1"


class GMProvider(Protocol):
    def respond(self, request: GMRequest) -> ConversationReply: ...


class HandlerProvider(Protocol):
    def respond(self, request: HandlerRequest) -> ConversationReply: ...


class HandlerDecision(Contract):
    action: Literal["RESPOND", "WAIT"]
    reason: Literal["direct_question", "scope_boundary", "gm_request", "no_handler_need"]
    source_refs: tuple[str, ...] = Field(default=(), max_length=3)


class SyntheticHandlerPolicy:
    """Bounded local need detection; it does not infer emotions or choose PC actions."""

    def decide(self, request: HandlerRequest) -> HandlerDecision:
        text = request.question.strip().casefold()
        if re.match(r"gm\s*[:,]", text):
            return HandlerDecision(action="WAIT", reason="gm_request")
        if re.match(r"handler\s*[:,]", text) and (
            "?" in text or re.search(r"\b(?:confirm|repeat|remind|resolve|state|explain)\b", text)
        ):
            return HandlerDecision(action="RESPOND", reason="direct_question")
        # One explicitly supported unsolicited correction: a stated forced-entry
        # plan contradicting the actual Handler-known briefing. Suggestions,
        # quotations and mere mentions of the Handler are not triggers.
        scope = tuple(
            ref
            for ref in request.context.references
            if ref.topic == "scope" and "forced entry is not authorised" in ref.text.casefold()
        )
        if scope and re.match(
            r"(?:i|we)\s+(?:will|intend to|am going to|are going to)\s+"
            r"(?:force|breach|break open)\b",
            text,
        ):
            return HandlerDecision(
                action="RESPOND",
                reason="scope_boundary",
                source_refs=tuple(x.id for x in scope[-3:]),
            )
        return HandlerDecision(action="WAIT", reason="no_handler_need")


def question_topic(question: str) -> str:
    words = set(re.findall(r"[a-z]+", question.casefold()))
    if words & {"roll", "dice", "heat", "play", "resolve", "spend"}:
        return "play"
    if words & {"scope", "include", "includes", "limits", "boundary", "boundaries"}:
        return "scope"
    if words & {"objective", "goal", "brief", "briefing"}:
        return "objective"
    if words & {"accepted", "acceptance", "status", "committed"}:
        return "status"
    if words & {"summary", "summarise", "summarize", "readback", "repeat"}:
        return "readback"
    return "general"


def _answer(
    route: Route, question: str, references: tuple[KnowledgeReference, ...]
) -> ConversationReply:
    topic = question_topic(question)
    if topic == "play":
        return ConversationReply(
            route=route,
            play_id="keep_your_head"
            if route == "gm"
            and ("keep your head" in question.casefold() or "keep_your_head" in question.casefold())
            else None,
            disposition="requires_engine_workflow",
            text=(
                "The GM handles Play resolution. Use the engine’s Play workflow; "
                "I will not choose your expenditure or roll for you."
            )
            if route == "handler"
            else (
                "This needs the engine’s Play workflow. Confirm your actual Play and "
                "player-owned choices there; this reply rolls no dice and spends no Heat."
            ),
        )
    relevant = (
        tuple(x for x in references if x.topic == topic) if topic != "readback" else references
    )
    if topic == "general" or not relevant:
        return ConversationReply(
            route=route,
            disposition="clarification",
            text=(
                "I do not have established information for that question "
                "in my available knowledge. "
                "Which fact or part of the briefing would you like clarified?"
            )
            if route == "handler"
            else (
                "That is not established in the permitted response context. "
                "Please specify the source or request facilitator adjudication."
            ),
        )
    selected = relevant[-3:]
    label = {"objective": "objective", "scope": "scope", "status": "status", "readback": "summary"}[
        topic
    ]
    return ConversationReply(
        route=route,
        disposition="answer",
        text=f"The {label} in the briefing available to me is: "
        + " ".join(x.text for x in selected)
        + (
            " This discussion does not accept a mission or issue a new order."
            if topic in ("objective", "scope")
            else ""
        ),
        source_refs=tuple(x.id for x in selected),
    )


class SyntheticHandler:
    def respond(self, request: HandlerRequest) -> ConversationReply:
        decision = SyntheticHandlerPolicy().decide(request)
        if decision.reason == "scope_boundary":
            references = tuple(
                x for x in request.context.references if x.id in decision.source_refs
            )
            return ConversationReply(
                route="handler",
                disposition="answer",
                text="That proposed action conflicts with the scope known to me: "
                + " ".join(x.text for x in references)
                + " Clarify the plan with the GM before treating it as authorised; "
                "this warning does not decide your action or resolve its outcome.",
                source_refs=decision.source_refs,
            )
        return _answer("handler", request.question, request.context.references)


class SyntheticGM:
    def respond(self, request: GMRequest) -> ConversationReply:
        # Reads the broader GM context, but this conservative synthetic adapter only
        # publishes recipient-permitted references or neutral engine referrals.
        return _answer("gm", request.question, request.recipient_references)
