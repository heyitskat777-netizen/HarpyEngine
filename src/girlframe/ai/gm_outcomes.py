"""Typed proposals for existing source consumers; private reasons are never answer text."""

from typing import Annotated, Literal, Protocol

from pydantic import Field, JsonValue

from girlframe.ai.contracts import Contract
from girlframe.ai.gm_protocol import Assessment, Evidence, TaskFrame
from girlframe.engine.m3_battle_state import Defense
from girlframe.engine.m3_handler_play_state import Effect, Play
from girlframe.engine.m3_janus_pandora import ChildProposal


class KeepOutcome(Contract):
    kind: Literal["keep"] = "keep"
    verdict: Literal["enough", "not_enough", "needs_clarification"]
    assessments: tuple[Assessment, ...] = ()
    narration: str = Field(min_length=1, max_length=1200)


class SensorAnswers(Contract):
    kind: Literal["sensors"] = "sensors"
    answers: dict[str, str] = Field(min_length=1, max_length=8)
    consequence: Literal["incomplete_information", "punishment_later"] | None = None


class BattleFacts(Contract):
    kind: Literal["battle_facts"] = "battle_facts"
    opening: bool
    reach: bool
    outside_permission: bool = False
    indirect: bool = False
    evidence: str = Field(min_length=1, max_length=1200)
    defense: Defense | None = None
    dormant_awakened: bool = False
    dormant_close: bool = False
    core_capability_confirmed: bool = False
    actor_outside_frame: bool | None = None
    target_outside_frame: bool | None = None


class BattleConsequences(Contract):
    kind: Literal["battle_consequences"] = "battle_consequences"
    choices: tuple[Literal["collateral_damage", "handler_play", "damage_actor_asset"], ...] = Field(
        min_length=1, max_length=2
    )
    account: str = Field(min_length=1, max_length=1200)


class GorgonJudgment(Contract):
    kind: Literal["gorgon_judgment"] = "gorgon_judgment"
    verdict: Literal[
        "attacker", "defender", "lands", "averted", "reached", "unreachable", "capable", "incapable"
    ]
    losing_asset: str | None = None
    indirect: bool = False
    account: str = Field(min_length=1, max_length=1200)


class CollateralOutcome(Contract):
    kind: Literal["collateral"] = "collateral"
    effects: tuple[Literal["civilians", "structure", "electronics", "environment"], ...] = Field(
        min_length=1, max_length=2
    )
    structure: str | None = None
    civilians: tuple[str, ...] = ()
    account: str = Field(min_length=1, max_length=1200)


class WarpOutcome(Contract):
    kind: Literal["warp"] = "warp"
    effect: Literal["escalate", "evolve", "protect"]
    name: str = Field(default="", max_length=120)
    description: str = Field(default="", max_length=1200)
    account: str = Field(min_length=1, max_length=1200)


class PandoraOutcome(Contract):
    kind: Literal["pandora"] = "pandora"
    child: ChildProposal


class WraithOutcome(Contract):
    kind: Literal["wraith"] = "wraith"
    rules: str = Field(min_length=1, max_length=1200)
    tag: str | None = Field(default=None, min_length=1, max_length=120)


class HandlerOutcome(Contract):
    kind: Literal["handler_effect"] = "handler_effect"
    play: Play
    effect: Effect


class TableOutcome(Contract):
    kind: Literal["table"] = "table"
    vast_advantage: bool | None = None
    answers: dict[str, str] = Field(default_factory=dict, max_length=8)
    account: str = Field(min_length=1, max_length=1200)


class FactOutcome(Contract):
    kind: Literal["source_fact"] = "source_fact"
    established: bool
    account: str = Field(min_length=1, max_length=1200)


class OutcomeNarration(Contract):
    kind: Literal["narration"] = "narration"
    text: str = Field(min_length=1, max_length=1200)
    effect_refs: tuple[str, ...] = Field(min_length=1, max_length=24)


Decision = Annotated[
    KeepOutcome
    | SensorAnswers
    | BattleFacts
    | BattleConsequences
    | GorgonJudgment
    | CollateralOutcome
    | WarpOutcome
    | PandoraOutcome
    | WraithOutcome
    | HandlerOutcome
    | TableOutcome
    | FactOutcome
    | OutcomeNarration,
    Field(discriminator="kind"),
]


class OutcomePacket(Contract):
    schema_version: Literal[3] = 3
    request_id: str
    scene_id: str
    source_kind: Literal["choice", "battle", "handler_grant", "table", "completed"]
    source_id: str
    operation: str
    owner_id: str
    evidence: tuple[Evidence, ...]
    frame: TaskFrame | None = None
    native: dict[str, JsonValue]
    gm_private_context: dict[str, JsonValue]


class OutcomeProposal(Contract):
    request_id: str
    decision: Decision
    cited_evidence: tuple[str, ...] = Field(min_length=1, max_length=64)
    private_reasoning: str = Field(min_length=1, max_length=12000)


class OutcomeProvider(Protocol):
    def propose(self, packet: OutcomePacket) -> OutcomeProposal: ...
