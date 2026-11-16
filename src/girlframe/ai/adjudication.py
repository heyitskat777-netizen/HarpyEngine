"""Source-bound GM adjudication proposals; local judgment is not a printed trait rule."""

import re
from typing import Literal, Protocol

from pydantic import Field, JsonValue, model_validator

from girlframe.ai.contracts import Contract
from girlframe.ai.conversation import GMRequest


class AdjudicationRequest(Contract):
    play_id: str
    action_id: str
    action_revision: int
    source_id: str
    source_revision: int
    receipt_id: str
    pending_choice_id: str
    narration: str = Field(min_length=1, max_length=1200)
    actual_result: dict[str, JsonValue]
    gm_context: GMRequest


class AdjudicationProposal(Contract):
    verdict: Literal["success", "failure", "needs_clarification", "requires_play_adapter"]
    enough: bool | None
    goal: str
    reasoning: str
    narration: str
    source_refs: tuple[str, ...]
    application: Literal["proposal_only"] = "proposal_only"
    provider: Literal["synthetic-adjudication-v1"] = "synthetic-adjudication-v1"

    @model_validator(mode="after")
    def consistent_verdict(self) -> "AdjudicationProposal":
        expected = {
            "success": True,
            "failure": False,
            "needs_clarification": None,
            "requires_play_adapter": None,
        }[self.verdict]
        if self.enough is not expected:
            raise ValueError("The enough value must match the explicit verdict")
        return self


class AdjudicationProvider(Protocol):
    def adjudicate(self, request: AdjudicationRequest) -> AdjudicationProposal: ...


class SyntheticAdjudicator:
    """A bounded stand-in for GM judgment, not a universal trait success table.

    Uses only the declared goal and actual traits for its player-facing explanation.
    The GM receives broad context; hidden facts are not copied into narration.
    """

    def adjudicate(self, request: AdjudicationRequest) -> AdjudicationProposal:
        context = request.narration.strip()
        goal = re.split(r"keep[_ ]your[_ ]head\s+to\s+", context, flags=re.I)[-1].rstrip(".")
        refs = (request.source_id, request.receipt_id, request.pending_choice_id)

        def result(
            verdict: str, enough: bool | None, reasoning: str, narration: str
        ) -> AdjudicationProposal:
            return AdjudicationProposal.model_validate(
                {
                    "verdict": verdict,
                    "enough": enough,
                    "goal": goal,
                    "reasoning": reasoning,
                    "narration": narration,
                    "source_refs": refs,
                }
            )

        if request.play_id != "keep_your_head":
            return result(
                "requires_play_adapter",
                None,
                f"{request.play_id} needs its own printed outcome adapter; Keep's trait judgment "
                "does not apply to this Play.",
                "Facilitator review is required for this Play's specific choices "
                "and fictional outcome.",
            )
        text = goal.casefold()
        # These are labelled synthetic GM interpretations of a few concrete goals,
        # not new rules, mechanical modifiers or a claim of general language reasoning.
        if re.search(r"\b(?:steady|precis\w*|calibrat\w*|focus|composure)\b", text):
            trait, demand = (
                "in_control",
                "maintaining deliberate control through the stated pressure",
            )
        elif re.search(r"\b(?:freezing|cold|exhaust\w*|endurance|endure)\b", text):
            trait, demand = "tough", "enduring the stated physical strain long enough to continue"
        else:
            return result(
                "needs_clarification",
                None,
                "The declared context does not establish a goal this bounded GM "
                "adapter can assess.",
                "What exactly are you trying to achieve, and what would prevent it? No success or "
                "failure is established until that context is clear.",
            )
        positives = request.actual_result.get("positive", [])
        negatives = request.actual_result.get("negative", [])
        assert isinstance(positives, list) and isinstance(negatives, list)
        label = trait.replace("_", " ")
        if trait in positives:
            return result(
                "success",
                True,
                f"This attempt depends on {demand}. The committed choices establish that you ARE "
                f"{label}, which is enough for that stated goal. "
                "The roll's tier is not the verdict.",
                f"For the declared attempt — {goal} — your chosen {label} is enough to make it "
                "through. This succeeds at that stated goal; "
                "it grants no unrelated mission success.",
            )
        if trait in negatives:
            return result(
                "failure",
                False,
                f"This attempt depends on {demand}. The committed choices establish that you are "
                f"NOT {label}. The other selected traits do not meet that particular demand, "
                "so they are not enough even if the dice tier is high.",
                f"For the declared attempt — {goal} — being not {label} prevents the stated goal. "
                "That attempt fails. No extra injury, punishment, expenditure "
                "or PC action is invented.",
            )
        return result(
            "needs_clarification",
            None,
            f"The task calls for {demand}, but the actual choices establish neither {label} "
            "nor its negation. An unselected trait is not automatically false.",
            "Clarify how the established traits meet this task's demand before deciding whether "
            "they are enough. The GM has not inferred an extra trait or rolled again.",
        )
