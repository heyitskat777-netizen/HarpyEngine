"""A fiction-only decision for a single scoped Activity intake batch."""

import re
from typing import Annotated, Literal, Protocol, runtime_checkable

from pydantic import Field, StringConstraints, model_validator

from girlframe.ai.contracts import Contract
from girlframe.ai.conversation import HandlerDecision, HandlerPersona
from girlframe.ai.director import KnowledgeReference
from girlframe.ai.director_dossiers import CharacterSetup, DossierPacket
from girlframe.ai.director_fronts import MissionAccess, PortrayalMove
from girlframe.ai.handler_initiative import HandlerInitiative
from girlframe.ai.pilot_initiative import PilotInitiative, PilotLenses
from girlframe.ai.worldbuilding import DevelopmentAction
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_handler_character import Cue, PlaybookProfile
from girlframe.engine.m3_handler_state import HandlerNotes
from girlframe.scenes.opening import SceneOpening


class HeardReport(Contract):
    source_id: str
    revision: int
    speaker: ActorRef
    text: str = Field(min_length=1, max_length=1000)
    classification: Literal["reported_claim"] = "reported_claim"


class BatchListener(Contract):
    actor: ActorRef
    label: str
    report_ids: tuple[str, ...]


def scene_details(
    references: tuple[KnowledgeReference, ...], *, limit: int = 3
) -> tuple[KnowledgeReference, ...]:
    """Select immediate surroundings from an already authorized role packet."""
    return tuple(
        ref
        for ref in references
        if ref.classification == "established_world"
        and ref.topic == "general"
        and ref.origin_scene is None
    )[-limit:]


class FictionBeat(Contract):
    own_action: str | None = Field(default=None, min_length=1, max_length=240)
    offers_help: bool = False
    follows_offer: str | None = Field(default=None, min_length=1, max_length=100)
    answers_offer: str | None = Field(
        default=None, min_length=1, max_length=100, exclude_if=lambda value: value is None
    )

    @model_validator(mode="after")
    def one_offer_link(self) -> "FictionBeat":
        if self.answers_offer and self.follows_offer:
            raise ValueError("Answer another speaker's offer or follow through on one of your own")
        return self


class FictionTradeoff(Contract):
    """Private planning for a draft. Neither field records an action or its outcome."""

    accepted_cost: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=180)
    ]
    next_move: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=180)
    ]


class PriorContribution(Contract):
    reference: str
    text: str
    own_action: str | None
    open_offer: bool
    carried: bool = Field(default=False, exclude_if=lambda value: not value)


BatchHandlerPlay = Literal[
    "brief", "support", "expectation", "dress_them_down", "get_them_alone", "break_down"
]


class HandlerPlayOpportunity(Contract):
    play: BatchHandlerPlay
    title: str
    trigger: str
    report_id: str
    source_refs: tuple[str, ...] = Field(max_length=3)


NativeHandlerSignature = Literal[
    "catch_more_flies_with_honey", "head_to_the_lab", "rebel_sympathizers", "conditioning_phrases"
]


class NativeSignatureOpportunity(Contract):
    play: NativeHandlerSignature
    title: str
    trigger: str
    control: str | None = Field(default=None, exclude=True)
    destination: Literal["signature_choice", "conditioning_phrase", "off_duty_signature"] | None = (
        Field(default=None, exclude=True)
    )


class ActivityBatchPacket(Contract):
    scene: str
    opening: SceneOpening
    trigger: Literal["quiet", "size", "age", "completed_play"]
    has_completed_play: bool
    handler: ActorRef
    persona: HandlerPersona | None
    playbook_profile: PlaybookProfile | None
    character_notes: HandlerNotes | None
    character_setup: CharacterSetup | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    references: tuple[KnowledgeReference, ...]
    private_memories: tuple[KnowledgeReference, ...]
    reports: tuple[HeardReport, ...] = Field(max_length=20)
    earlier_reports: tuple[HeardReport, ...] = Field(
        default=(), max_length=3, exclude_if=lambda value: not value
    )
    eligible_listeners: tuple[BatchListener, ...] = ()
    scene_details: tuple[KnowledgeReference, ...] = Field(default=(), max_length=3)
    response_need: HandlerDecision | None
    response_report_id: str | None = Field(default=None, exclude_if=lambda value: value is None)
    initiative: HandlerInitiative | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    recent_contributions: tuple[PriorContribution, ...] = ()
    opportunity: PortrayalMove | None = Field(default=None, exclude_if=lambda value: value is None)
    play_opportunities: tuple[HandlerPlayOpportunity, ...] = Field(
        default=(), exclude_if=lambda value: not value
    )
    native_signatures: tuple[NativeSignatureOpportunity, ...] = Field(
        default=(), exclude_if=lambda value: not value
    )


class StaySilent(Contract):
    kind: Literal["WAIT"]
    reason: Literal["no_grounded_need", "pilots_have_the_floor"]


_LISTENER_STAGE_ACTION = re.compile(
    r"\byou(?:(?:\s+are|'re)\s+"
    r"(?:handing|passing|giving|offering|sliding|holding|reaching|writing|signing|initiall?ing)"
    r"|\s+(?:hand|pass|give|offer|slide|hold|reach|write|sign|initial))\b"
    r"|\byour\s+(?:hands?|arms?|fingers?)\s+"
    r"(?:reaches?|push(?:es)?|pulls?|closes?|moves?|holds?|takes?)\b"
    r"|\byour\s+(?:outstretched|extended)\s+hands?\b"
)


class NpcSpeech(Contract):
    kind: Literal["NPC_DIALOGUE"]
    reason: Literal["response_need", "shared_report", "character_cue", "follow_through"]
    text: str = Field(min_length=1, max_length=1100)
    source_refs: tuple[str, ...] = Field(max_length=3)
    report_ids: tuple[str, ...] = Field(max_length=2)
    intended_recipients: tuple[ActorRef, ...] = Field(min_length=1, max_length=2)
    cue: Cue | None = None
    fiction: FictionBeat = Field(default_factory=FictionBeat)
    tradeoff: FictionTradeoff | None = Field(default=None, exclude_if=lambda value: value is None)
    play_offer: BatchHandlerPlay | None = Field(
        default=None, exclude_if=lambda value: value is None
    )

    def authors_listener_action(self) -> bool:
        """Spot present physical actions assigned to a listener in the stage direction."""
        action = (self.fiction.own_action or "").casefold().replace("’", "'")
        return bool(_LISTENER_STAGE_ACTION.search(action))

    def with_played_action(self) -> "NpcSpeech":
        """Keep enacted gestures separate from speech, offers, and future plans."""
        action = self.fiction.own_action
        if action is None:
            return self
        action = action.strip().casefold().replace("’", "'")
        proposed = re.match(
            r"(?:i (?:can|could|may|might|would|will|should)|i'(?:d|ll))(?=\s|$)", action
        )
        spoken_words = self.text.casefold().replace("’", "'")
        echo = action.rstrip(".!?") in {
            sentence.strip() for sentence in re.split(r"[.!?]+", spoken_words)
        }
        if proposed or echo:
            return self.model_copy(
                update={"fiction": self.fiction.model_copy(update={"own_action": None})}
            )
        return self


class ProposeEvent(Contract):
    kind: Literal["WORLD_EVENT_PROPOSAL"]
    action: DevelopmentAction
    source_refs: tuple[str, ...] = Field(min_length=1, max_length=3)


class Escalate(Contract):
    kind: Literal["NEEDS_REVIEW"]
    reason: Literal["unsupported_outcome", "uncertain_authority"]


class ReviewNativeSignature(Contract):
    kind: Literal["REVIEW_HANDLER_SIGNATURE"]
    play: NativeHandlerSignature


class ActivityBatchDecision(Contract):
    decision: Annotated[
        StaySilent | NpcSpeech | ProposeEvent | Escalate | ReviewNativeSignature,
        Field(discriminator="kind"),
    ]


class ActivityBatchProvider(Protocol):
    def decide(self, packet: ActivityBatchPacket) -> ActivityBatchDecision: ...


class ReceivedOffer(Contract):
    reference: str
    speaker: ActorRef
    text: str


class PilotListener(BatchListener):
    source_refs: tuple[str, ...] = ()


class PilotSpeech(Contract):
    recipients: tuple[ActorRef, ...] = Field(min_length=1, max_length=6)


class PilotIntent(Contract):
    tactic: Literal["ask", "offer", "counteroffer", "set_boundary", "decline", "defer"]
    if_refused: Literal["wait", "let_go", "ask_later", "try_elsewhere"]
    priority: str | None = Field(
        default=None, min_length=1, max_length=180, exclude_if=lambda value: value is None
    )
    tradeoff: FictionTradeoff | None = Field(default=None, exclude_if=lambda value: value is None)
    pressure_id: str | None = Field(default=None, min_length=1, max_length=100)
    move_id: str | None = Field(
        default=None, min_length=1, max_length=100, exclude_if=lambda value: value is None
    )


class ActivityPilotPacket(Contract):
    scene: str
    opening: SceneOpening
    trigger: Literal["quiet", "size", "age", "completed_play"]
    callsign: str
    dossier: DossierPacket
    report: HeardReport
    earlier_reports: tuple[HeardReport, ...] = Field(
        default=(), max_length=3, exclude_if=lambda value: not value
    )
    nearby_reports: tuple[HeardReport, ...] = Field(default=(), max_length=4)
    latest_heard_report_id: str | None = Field(default=None, exclude_if=lambda value: value is None)
    audience: tuple[PilotListener, ...] = ()
    portrayal_lenses: PilotLenses = Field(default_factory=PilotLenses)
    initiative: PilotInitiative | None = Field(default=None, exclude_if=lambda value: value is None)
    scene_details: tuple[KnowledgeReference, ...] = Field(default=(), max_length=3)
    front_refs: tuple[str, ...] = Field(default=(), max_length=6)
    recent_contributions: tuple[PriorContribution, ...] = ()
    received_offers: tuple[ReceivedOffer, ...] = Field(default=(), max_length=3)
    speech: PilotSpeech | None = Field(default=None, exclude_if=lambda value: value is None)
    intent: PilotIntent | None = Field(default=None, exclude_if=lambda value: value is None)
    opportunity: PortrayalMove | None = Field(default=None, exclude_if=lambda value: value is None)
    native_plays: tuple[dict[str, str], ...] = Field(default=(), exclude_if=lambda value: not value)
    revise_for: Literal["citation_scope"] | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    previous_speech: PilotSpeech | None = Field(
        default=None, exclude_if=lambda value: value is None
    )


class PilotContribution(Contract):
    kind: Literal["DIALOGUE", "SCENE_OFFER"]
    text: str = Field(min_length=1, max_length=1000)
    source_refs: tuple[str, ...] = Field(max_length=3)
    play_id: str | None = Field(
        default=None, min_length=1, max_length=160, exclude_if=lambda value: value is None
    )
    access_claim: MissionAccess | None = Field(default=None, exclude_if=lambda value: value is None)
    fiction: FictionBeat = Field(default_factory=FictionBeat)
    intended_recipients: tuple[ActorRef, ...] = Field(
        default=(), max_length=6, exclude_if=lambda value: not value
    )


class ActivityPilotDecision(Contract):
    decision: Annotated[StaySilent | PilotContribution | Escalate, Field(discriminator="kind")]


class ActivityPilotProvider(Protocol):
    def decide(self, packet: ActivityPilotPacket) -> ActivityPilotDecision: ...


class AddressPilotListeners(PilotSpeech):
    kind: Literal["ADDRESS"]
    intent: PilotIntent | None = None


class PrivatePilotIntent(Contract):
    kind: Literal["PRIVATE_INTENT"]
    intent: PilotIntent | None = None


class PilotAudienceDecision(Contract):
    decision: Annotated[
        AddressPilotListeners | PrivatePilotIntent | StaySilent | Escalate,
        Field(discriminator="kind"),
    ]


@runtime_checkable
class ScopedActivityPilotProvider(ActivityPilotProvider, Protocol):
    def select_audience(self, packet: ActivityPilotPacket) -> PilotAudienceDecision: ...
