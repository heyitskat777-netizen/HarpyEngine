"""Separate zero-cost GM/Handler request types and deterministic response policy."""

import re
from typing import Literal, Protocol

from pydantic import ConfigDict, Field, JsonValue, model_validator

from girlframe.ai.contracts import Contract
from girlframe.ai.director import DirectorContext, KnowledgeReference
from girlframe.ai.director_dossiers import DossierProfile, DossierState
from girlframe.ai.observation import Observation
from girlframe.ai.play_names import LABELS, requested_play
from girlframe.ai.play_review import PlayReferral
from girlframe.engine.m3_handler_character import Cue, PlaybookProfile
from girlframe.engine.m3_handler_play_state import Play
from girlframe.engine.m3_handler_state import HandlerNotes

Route = Literal["gm", "handler"]


class HandlerDecision(Contract):
    action: Literal["RESPOND", "WAIT"]
    reason: Literal[
        "direct_question",
        "scope_boundary",
        "scope_already_addressed",
        "known_update",
        "update_already_addressed",
        "gm_request",
        "no_handler_need",
        "reviewed_indirect_request",
        "reviewed_urgent_report",
        "reviewed_follow_up",
        "reviewed_character_cue",
        "peer_response",
        "need_already_addressed",
        "handler_absent",
    ]
    source_refs: tuple[str, ...] = Field(default=(), max_length=3)
    concern_id: str | None = Field(default=None, exclude_if=lambda x: x is None)
    cue: Cue | None = Field(default=None, exclude_if=lambda x: x is None)


class HandlerPersona(Contract):
    version: int = Field(ge=1)
    profile: DossierProfile
    state: DossierState


class HandlerConcern(Contract):
    id: str
    text: str = Field(min_length=1, max_length=300)


class HandlerRequest(Contract):
    schema_version: Literal[1] = 1
    question: str = Field(min_length=1, max_length=1000)
    context: DirectorContext
    addressed_update_refs: tuple[str, ...] = Field(default=(), exclude_if=lambda x: not x)
    persona: HandlerPersona | None = Field(default=None, exclude_if=lambda x: x is None)
    playbook_profile: PlaybookProfile | None = Field(default=None, exclude_if=lambda x: x is None)
    character_notes: HandlerNotes | None = Field(default=None, exclude_if=lambda x: x is None)
    response_need: HandlerDecision | None = Field(default=None, exclude_if=lambda x: x is None)
    open_concerns: tuple[HandlerConcern, ...] = Field(default=(), exclude_if=lambda x: not x)
    closed_scene_reports: tuple[KnowledgeReference, ...] = Field(
        default=(),
        max_length=100,
        exclude_if=lambda x: not x,
        description="Private debrief memory. Scene speech uses current audience-scoped citations.",
    )

    @model_validator(mode="after")
    def handler_boundary(self) -> "HandlerRequest":
        if (
            self.context.audience != "actor"
            or self.context.actor is None
            or self.context.actor.kind != "handler"
        ):
            raise ValueError("Handler request requires its isolated actual Handler context")
        return self


class HeatAnswer(Contract):
    rule_id: Literal["core.core.heat"] = "core.core.heat"
    printed_page: Literal[8] = 8
    status: Literal["rule", "no_cost", "needs_source", "pending", "committed", "cancelled"]
    action_id: str | None = None
    amount: int | None = Field(default=None, ge=0)
    receipt_id: str | None = None


class GMRequest(Contract):
    schema_version: Literal[1] = 1
    question: str = Field(min_length=1, max_length=1000)
    context: DirectorContext
    canonical_state: dict[str, JsonValue]
    engine_records: dict[str, list[dict[str, JsonValue]]]
    scene_inputs: tuple[Observation, ...] = Field(max_length=100)
    scene_inputs_omitted: int = Field(default=0, ge=0)
    recipient_references: tuple[KnowledgeReference, ...]
    play_candidates: tuple[PlayReferral, ...] = ()
    play_declaration: bool = False
    heat_answer: HeatAnswer | None = Field(default=None, exclude_if=lambda x: x is None)

    @model_validator(mode="after")
    def gm_boundary(self) -> "GMRequest":
        if self.context.audience != "gm" or self.context.actor is not None:
            raise ValueError("GM request requires its separate campaign GM context")
        return self


class GMDecision(Contract):
    action: Literal["RESPOND", "WAIT"]
    reason: Literal[
        "no_gm_need",
        "explicit_gm_request",
        "play_request",
        "scope_adjudication",
        "completed_play",
        "rules_question",
    ]


class ConversationReply(Contract):
    model_config = ConfigDict(
        json_schema_extra={
            "allOf": [
                {
                    "if": {
                        "properties": {
                            "provider": {"const": "reviewed-handler-v1"},
                            "route": {"const": "handler"},
                            "disposition": {"const": "answer"},
                        },
                        "required": ["provider", "route", "disposition"],
                    },
                    "then": {
                        "required": ["source_refs"],
                        "properties": {"source_refs": {"minItems": 1}},
                    },
                }
            ]
        }
    )
    schema_version: Literal[1] = 1
    route: Route
    disposition: Literal["answer", "clarification", "requires_engine_workflow"] = Field(
        description="Use clarification for unknown information, even when saying 'I do not know'. "
        "Factual answers in reviewed Handler mode require actual scoped source_refs."
    )
    text: str = Field(min_length=1, max_length=6000)
    source_refs: tuple[str, ...] = Field(default=(), max_length=3)
    play_id: str | None = None
    handler_action: str | None = Field(
        default=None, min_length=1, max_length=600, exclude_if=lambda x: x is None
    )
    handler_play_offer: Play | None = Field(default=None, exclude_if=lambda x: x is None)
    handler_concern: str | None = Field(
        default=None, min_length=1, max_length=300, exclude_if=lambda x: x is None
    )
    gm_decision: GMDecision | None = None
    gm_rule: HeatAnswer | None = Field(default=None, exclude_if=lambda x: x is None)
    application: Literal["blocked"] = "blocked"
    provider: Literal["synthetic-conversation-v1", "reviewed-handler-v1"] = (
        "synthetic-conversation-v1"
    )

    @model_validator(mode="after")
    def separate_gm_decision(self) -> "ConversationReply":
        if self.route == "handler" and (self.gm_decision is not None or self.gm_rule is not None):
            raise ValueError("GM intervention decisions are not Handler output")
        if any(
            x is not None
            for x in (self.handler_action, self.handler_play_offer, self.handler_concern)
        ) and (self.route != "handler" or self.provider != "reviewed-handler-v1"):
            raise ValueError("Handler initiative requires reviewed Handler output")
        if self.handler_action is not None and not self.handler_action.strip():
            raise ValueError("Describe the Handler's own action")
        if self.handler_concern is not None and not self.handler_concern.strip():
            raise ValueError("Describe the actual concern that remains open")
        return self


class GMProvider(Protocol):
    def respond(self, request: GMRequest) -> ConversationReply: ...


class HandlerProvider(Protocol):
    def respond(self, request: HandlerRequest) -> ConversationReply: ...


class HandlerNeedPacket(Contract):
    request_id: str
    scene_id: str
    source_id: str
    source_revision: int
    request: HandlerRequest
    revision: str


class PeerResponse(Contract):
    source_id: str
    source_revision: int = Field(ge=1)
    quote: str = Field(min_length=1, max_length=1000)


class HandlerNeedProposal(Contract):
    model_config = ConfigDict(
        json_schema_extra={
            "allOf": [
                {
                    "if": {
                        "properties": {"kind": {"const": "character_cue"}},
                        "required": ["kind"],
                    },
                    "then": {"required": ["cue"], "properties": {"cue": {"type": "string"}}},
                },
                {
                    "if": {
                        "properties": {"kind": {"enum": ["indirect_request", "character_cue"]}},
                        "required": ["kind"],
                    },
                    "then": {
                        "required": ["speech_quote"],
                        "properties": {"speech_quote": {"type": "string", "minLength": 1}},
                    },
                },
                {
                    "if": {
                        "properties": {"kind": {"enum": ["urgent_known_report", "follow_up"]}},
                        "required": ["kind"],
                    },
                    "then": {
                        "required": ["source_refs"],
                        "properties": {"source_refs": {"minItems": 1}},
                    },
                },
                {
                    "if": {"properties": {"kind": {"const": "no_need"}}, "required": ["kind"]},
                    "then": {"properties": {"action": {"const": "WAIT"}}},
                },
                {
                    "if": {"properties": {"action": {"const": "RESPOND"}}, "required": ["action"]},
                    "then": {
                        "properties": {
                            "kind": {
                                "enum": [
                                    "indirect_request",
                                    "urgent_known_report",
                                    "follow_up",
                                    "character_cue",
                                ]
                            }
                        }
                    },
                },
            ]
        }
    )
    request_id: str
    action: Literal["RESPOND", "WAIT"]
    kind: Literal[
        "indirect_request", "urgent_known_report", "follow_up", "character_cue", "no_need"
    ]
    concern_id: str | None = Field(default=None, exclude_if=lambda x: x is None)
    cue: Cue | None = Field(default=None, exclude_if=lambda x: x is None)
    peer_response: PeerResponse | None = Field(default=None, exclude_if=lambda x: x is None)
    speech_quote: str | None = Field(
        default=None,
        max_length=1000,
        description="For an indirect request, quote actual words heard by the Handler, "
        "never private narration.",
    )
    source_refs: tuple[str, ...] = Field(
        default=(),
        max_length=3,
        description="Only actual Handler-known references. Urgent reports require at least one.",
    )
    reason: str = Field(
        min_length=1,
        max_length=1200,
        description="A brief private GM interpretation, not new facts, dialogue "
        "or mechanical effects.",
    )

    @model_validator(mode="after")
    def need_shape(self) -> "HandlerNeedProposal":
        if len(set(self.source_refs)) != len(self.source_refs):
            raise ValueError("Cite each Handler reference once")
        if self.action == "RESPOND" and self.kind == "no_need":
            raise ValueError("No need cannot request a response")
        if (
            self.kind in ("indirect_request", "follow_up", "character_cue")
            and not (self.speech_quote or "").strip()
        ):
            raise ValueError("The response needs an exact heard speech quote")
        if self.kind in ("urgent_known_report", "follow_up") and not self.source_refs:
            raise ValueError("An urgent report needs actual known references")
        if (self.kind == "follow_up") != bool(self.concern_id) or (
            self.kind == "follow_up" and self.action != "RESPOND"
        ):
            raise ValueError("A follow-up responds to one actual open concern")
        if (self.kind == "character_cue") != (self.cue is not None):
            raise ValueError("A character cue needs one recognised kind of heard situation")
        if self.peer_response and (self.kind != "character_cue" or self.action != "WAIT"):
            raise ValueError("A covering peer reply supports waiting on the original cue")
        return self


class HandlerNeedProvider(Protocol):
    def propose(self, packet: HandlerNeedPacket) -> HandlerNeedProposal: ...


def handler_updates(context: DirectorContext) -> tuple[KnowledgeReference, ...]:
    """Use one eligible-update definition for need selection and delivery suppression."""
    return tuple(
        x
        for x in context.references
        if x.topic in ("briefing", "tactical", "debrief")
        or (
            x.topic in ("objective", "scope", "status")
            and any(relation.kind == "corrects" for relation in x.relations)
        )
    )


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
        updates = handler_updates(request.context)
        pending = tuple(x for x in updates if x.id not in request.addressed_update_refs)
        if pending:
            return HandlerDecision(
                action="RESPOND", reason="known_update", source_refs=(pending[0].id,)
            )
        if updates:
            return HandlerDecision(action="WAIT", reason="update_already_addressed")
        return HandlerDecision(action="WAIT", reason="no_handler_need")


class SyntheticGMPolicy:
    """Select visible intervention; routine private GM review remains separate."""

    def decide(self, request: GMRequest) -> GMDecision:
        text = request.question.strip().casefold()
        if request.heat_answer is not None:
            return GMDecision(action="RESPOND", reason="rules_question")
        if re.match(
            r"(?:i|we)\s+(?:will|intend to|am going to|are going to)\s+"
            r"(?:force|breach|break open)\b",
            text,
        ):
            return GMDecision(action="RESPOND", reason="scope_adjudication")
        if request.play_declaration or request.play_candidates or requested_play(text) is not None:
            return GMDecision(action="RESPOND", reason="play_request")
        if re.match(r"gm\s*[:,]", text):
            return GMDecision(action="RESPOND", reason="explicit_gm_request")
        return GMDecision(action="WAIT", reason="no_gm_need")


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
        if decision.reason == "known_update":
            references = tuple(
                x for x in request.context.references if x.id in decision.source_refs
            )
            return ConversationReply(
                route="handler",
                disposition="answer",
                text="Recorded " + references[0].topic + " update: " + references[0].text,
                source_refs=decision.source_refs,
            )
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
        decision = SyntheticGMPolicy().decide(request)
        if request.heat_answer is not None:
            answer = request.heat_answer
            text = {
                "rule": "Each Heat adds +1 to an applicable roll. Spend before rolling. "
                "At 5 or more, spend all available Heat when the rule applies.",
                "no_cost": "An ordinary spoken question or correction spends no Heat. "
                "A separate Play uses its own trigger and cost if called.",
                "needs_source": "Which action do you mean? Use GM, Heat for <action ID> "
                "for a supported Play owned by you in this scene.",
                "pending": f"The prepared Play specifies {answer.amount} Heat. The roll has "
                "not committed the cost.",
                "committed": f"The native roll committed {answer.amount} Heat.",
                "cancelled": "This Play closed before its roll. No Heat spend was recorded for it.",
            }[answer.status]
            reply = ConversationReply(
                route="gm",
                text=text,
                gm_rule=answer,
                disposition="clarification" if answer.status == "needs_source" else "answer",
            )
        elif decision.reason == "play_request":
            if len(request.play_candidates) > 1 or (
                not request.play_candidates and requested_play(request.question) is None
            ):
                reply = ConversationReply(
                    route="gm",
                    disposition="clarification",
                    text="That declaration needs a source workflow clarified. "
                    "Choose the qualified Play or rule ID for GM review; no roll or choice "
                    "has been supplied by this referral.",
                )
            else:
                candidate = request.play_candidates[0] if request.play_candidates else None
                play = candidate.play_id if candidate else requested_play(request.question)
                assert play is not None
                reply = ConversationReply(
                    route="gm",
                    disposition="requires_engine_workflow",
                    play_id=play,
                    text=(candidate.title if candidate else LABELS[play])
                    + " requires its actual source workflow and GM review. "
                    "Original players and controllers retain their choices; required Handler "
                    "work remains with its actual owner. This referral resolves no outcome.",
                )
                if candidate and not candidate.module_enabled:
                    reply = reply.model_copy(
                        update={
                            "disposition": "clarification",
                            "text": candidate.title + " belongs to a disabled module. "
                            "GM review can record the blocker; "
                            "it cannot enable or resolve that rule.",
                        }
                    )
        elif decision.reason == "scope_adjudication":
            reply = ConversationReply(
                route="gm",
                disposition="clarification",
                text="That is a proposed action, not a resolved outcome. Clarify what you "
                "intend before adjudication; this conversation grants no access, permission "
                "or automatic success. Any applicable Play must use its actual engine workflow.",
            )
        else:
            reply = _answer("gm", request.question, request.recipient_references)
        return reply.model_copy(update={"gm_decision": decision})
