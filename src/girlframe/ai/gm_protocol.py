"""Provider-neutral private GM proposals and engine-owned validation (offline v2)."""

from typing import Literal, Protocol

from pydantic import Field, JsonValue

from girlframe.ai.contracts import Contract

Play = Literal["keep_your_head", "check_sensors", "engage", "disobey_orders", "flirt"]
Trait = Literal[
    "desperate", "sexy", "beautiful", "tough", "vicious", "in_control", "experienced", "big_enough"
]


class Demand(Contract):
    id: str = Field(min_length=1, max_length=80)
    question: str = Field(min_length=1, max_length=1000)


class Prerequisite(Contract):
    evidence_id: str
    state: Literal["satisfied", "blocked", "unknown", "irrelevant"]
    interpretation: str = Field(min_length=1, max_length=1000)


class TaskFrame(Contract):
    stakes: str = Field(min_length=1, max_length=1000)
    demands: tuple[Demand, ...] = Field(default=(), max_length=12)
    prerequisites: tuple[Prerequisite, ...] = Field(default=(), max_length=32)
    intent: Literal["established", "needs_clarification"] = "established"


class Evidence(Contract):
    id: str
    value: JsonValue
    audience: Literal["gm", "actor", "scene"]


class GMPacket(Contract):
    schema_version: Literal[2] = 2
    request_id: str
    play: Play
    source_id: str
    source_revision: int
    action_id: str
    action_revision: int
    receipt_id: str
    goal: str
    frame: TaskFrame
    evidence: tuple[Evidence, ...]
    positive: tuple[str, ...]
    negative: tuple[str, ...]
    stage: Literal["awaiting_keep_ruling", "pending_choices", "complete"]
    pending_choices: tuple[dict[str, JsonValue], ...]
    native_result: dict[str, JsonValue]
    followups: tuple[dict[str, JsonValue], ...]
    gm_private_context: dict[str, JsonValue]


class TraitClaim(Contract):
    trait: Trait
    polarity: Literal["are", "are_not"]


class Assessment(Contract):
    demand_id: str
    sufficient: bool | None
    evidence_ids: tuple[str, ...] = Field(min_length=1, max_length=32)
    traits: tuple[TraitClaim, ...] = Field(default=(), max_length=8)
    private_reason: str = Field(min_length=1, max_length=4000)


class GMProposal(Contract):
    schema_version: Literal[2] = 2
    request_id: str
    verdict: Literal[
        "enough", "not_enough", "needs_clarification", "native_outcome", "pending_choices"
    ]
    assessments: tuple[Assessment, ...] = Field(default=(), max_length=12)
    cited_evidence: tuple[str, ...] = Field(min_length=1, max_length=64)
    private_reasoning: str = Field(min_length=1, max_length=12000)
    # Native owner confirmation is the only supported consumer. No arbitrary effects.
    effects: tuple[()] = ()


class GMProvider(Protocol):
    def propose(self, packet: GMPacket) -> GMProposal: ...


class OfflineReviewProvider:
    """Safe default with no network or pretend general-language intelligence."""

    def propose(self, packet: GMPacket) -> GMProposal:
        verdict: Literal["needs_clarification", "native_outcome", "pending_choices"] = (
            "native_outcome"
            if packet.stage == "complete"
            else "needs_clarification"
            if packet.stage == "awaiting_keep_ruling"
            else "pending_choices"
        )
        return GMProposal(
            request_id=packet.request_id,
            verdict=verdict,
            cited_evidence=("goal", "receipt"),
            private_reasoning="Offline provider: obtain an explicit GM assessment "
            "for contextual judgment; retain actual native choices and outcomes.",
        )


def validate_proposal(packet: GMPacket, proposal: GMProposal) -> None:
    """Check evidence/coverage/authority, without demanding an oracle's prose."""
    if proposal.request_id != packet.request_id:
        raise ValueError("Wrong frozen request")
    facts = {fact.id for fact in packet.evidence}
    if not set(proposal.cited_evidence) <= facts:
        raise ValueError("Unknown evidence")
    if not {"goal", "receipt"} <= set(proposal.cited_evidence):
        raise ValueError("Original goal and receipt must be cited")
    if packet.stage != "awaiting_keep_ruling":
        expected = "native_outcome" if packet.stage == "complete" else "pending_choices"
        if proposal.verdict != expected or proposal.assessments:
            raise ValueError("Retain the actual printed outcome and pending owner choices")
        return
    if proposal.verdict not in ("enough", "not_enough", "needs_clarification"):
        raise ValueError("Keep needs its own enough judgment")
    if proposal.verdict == "needs_clarification":
        # Partial reasoning is permitted, but any supplied claims must still be valid.
        pass
    elif packet.frame.intent != "established" or not packet.frame.demands:
        raise ValueError("The attempted goal is not established")
    expected_demands = {d.id for d in packet.frame.demands}
    seen = set()
    for assessment in proposal.assessments:
        if assessment.demand_id in seen or assessment.demand_id not in expected_demands:
            raise ValueError("Wrong or duplicate demand")
        seen.add(assessment.demand_id)
        if not set(assessment.evidence_ids) <= facts or "traits" not in assessment.evidence_ids:
            raise ValueError("Assessment must cite actual traits and known evidence")
        for claim in assessment.traits:
            actual = packet.positive if claim.polarity == "are" else packet.negative
            if claim.trait not in actual:
                raise ValueError("An asserted trait was not established by the actual choices")
        if assessment.sufficient is not None and not assessment.traits:
            raise ValueError("Resolved Keep assessment needs actual trait evidence")
    if proposal.verdict == "needs_clarification":
        return
    if seen != expected_demands:
        raise ValueError("Every established demand must be assessed")
    constraints = {p.evidence_id: p.state for p in packet.frame.prerequisites}
    required = {f.id for f in packet.evidence if f.id.startswith("condition:")}
    if required - constraints.keys() or "unknown" in constraints.values():
        raise ValueError("An unresolved scene prerequisite requires clarification")
    if not required <= set(proposal.cited_evidence):
        raise ValueError("The scene prerequisites must be cited")
    if "blocked" in constraints.values() and proposal.verdict == "enough":
        raise ValueError("A blocked prerequisite cannot be ignored")
    values = [a.sufficient for a in proposal.assessments]
    if any(value is None for value in values):
        raise ValueError("An unresolved demand requires clarification")
    expected = "not_enough" if False in values or "blocked" in constraints.values() else "enough"
    if proposal.verdict != expected:
        raise ValueError("Verdict disagrees with the individual assessments")
