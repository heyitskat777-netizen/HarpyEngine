"""Owned Handler Plays: fictional effects and source-limited human authority."""

from typing import Literal

from pydantic import Field, model_validator

from girlframe.engine.identity import Snowflake
from girlframe.engine.m3_actor_state import ActorRef, Model
from girlframe.engine.m3_work_scope import WorkScope
from girlframe.engine.m3_world_state import Cell, Npc

BASIC = (
    ("brief", "Brief them on the situation"),
    ("punish", "Punish them"),
    ("escalate", "Escalate the situation"),
    ("support", "Introduce the support"),
    ("mess", "Mess with Status, Tags or Assets"),
    ("expectation", "Place an expectation on them"),
    ("off_duty", "Go Off-Duty"),
)
EXTRA = (
    ("tracker_intercept", "Intercept them"),
    ("tracker_voyeur", "Play voyeur to a private moment"),
    ("contaminant_warp", "Warp the quarantined area"),
)
Play = Literal[
    "brief",
    "punish",
    "escalate",
    "support",
    "mess",
    "expectation",
    "off_duty",
    "tracker_intercept",
    "tracker_voyeur",
    "contaminant_warp",
]


class Effect(Model):
    kind: Literal[
        "brief",
        "punish",
        "escalate",
        "support",
        "status",
        "tag",
        "damage",
        "expectation",
        "off_duty",
        "tracker_intercept",
        "tracker_voyeur",
        "contaminant_warp",
    ]
    account: str = Field(min_length=1, max_length=1200)
    detail: str = Field(default="", max_length=1200)
    stakes: str = Field(default="", max_length=1200)
    target: ActorRef | None = None
    status: Literal[-1, 0, 1] = 0
    tag: str = Field(default="", max_length=120)
    asset: str | None = Field(default=None, min_length=1, max_length=100)
    npc: Npc | None = None
    threat: ActorRef | None = None
    executor: ActorRef | None = None
    opponent: ActorRef | None = None
    source_label: str | None = Field(default=None, min_length=1, max_length=100)
    off_duty: str | None = Field(default=None, min_length=1, max_length=100)

    zone: str | None = Field(
        default=None, min_length=1, max_length=100, exclude_if=lambda x: x is None
    )
    cell: Cell | None = Field(default=None, exclude_if=lambda x: x is None)

    @model_validator(mode="after")
    def actual_effect(self) -> "Effect":
        if not self.account.strip():
            raise ValueError("Describe the actual information, situation or consequence")
        allowed = {
            "brief": set(),
            "punish": {"target", "executor"},
            "escalate": {"detail", "stakes", "threat"},
            "support": {"npc"},
            "status": {"target", "status"},
            "tag": {"target", "tag"},
            "damage": {"target", "asset", "opponent"},
            "expectation": {"detail", "stakes"},
            "off_duty": {"off_duty"},
            "tracker_intercept": {"target"},
            "tracker_voyeur": {"target", "detail"},
            "contaminant_warp": {"zone", "cell", "detail"},
        }[self.kind] | {"kind", "account", "source_label"}
        baseline = Effect.model_construct(kind=self.kind, account=self.account)
        if any(
            getattr(self, name) != getattr(baseline, name)
            for name in type(self).model_fields
            if name not in allowed
        ):
            raise ValueError("This Handler Play includes an unrelated effect")
        if self.kind in ("punish", "status", "tag", "damage") and self.target is None:
            raise ValueError("Choose the actual affected original actor")
        if self.kind == "status" and self.status == 0:
            raise ValueError("Choose a real Status increase or decrease")
        if self.kind == "tag" and not self.tag.strip():
            raise ValueError("Describe the actual new Tag")
        if (
            self.kind == "damage"
            and self.asset is None
            and (self.target is None or self.target.kind not in ("handler", "npc"))
        ):
            raise ValueError(
                "Choose an actual undamaged mechanical Asset or the printed "
                "Handler/NPC damage replacement"
            )
        if self.kind == "support" and self.npc is None:
            raise ValueError("Introduce an actual employee with an owned NPC record")
        if self.kind in ("escalate", "expectation") and (
            not self.detail.strip() or not self.stakes.strip()
        ):
            raise ValueError("Specify the real threat/rule and stakes/consequence")
        if self.kind == "off_duty" and self.off_duty is None:
            raise ValueError("Use the actual canonical Off-Duty period")
        if self.kind in ("tracker_intercept", "tracker_voyeur") and self.target is None:
            raise ValueError("Use the actual original tracker target")
        if self.kind == "tracker_voyeur" and not self.detail.strip():
            raise ValueError("Observe an actual human-authored fictional moment")
        if self.kind == "contaminant_warp" and (
            self.zone is None
            or self.cell is None
            or not self.source_label
            or not self.detail.strip()
        ):
            raise ValueError("Warp a real owned zone with an actual located feature")
        return self


class HandlerPlay(Model):
    id: str = Field(min_length=1)
    source: Literal["ordinary", "battle_counter", "required"]
    source_event: str = Field(min_length=1)
    source_action: str | None = None
    source_choice: str | None = None
    clause: str = Field(min_length=1)
    chooser_actor: ActorRef | None
    chooser_controller: Snowflake
    appointment: str | None = None
    adjudicator_ref: ActorRef | None = None
    adjudicator_source: str | None = None
    targets: tuple[ActorRef, ...] = Field(min_length=1)
    target_controllers: dict[str, Snowflake] = Field(default_factory=dict)
    scope: WorkScope
    final_original: bool = False
    nonbody_only: bool = False
    state: Literal["pending", "awaiting_effect", "complete", "withdrawn", "declined"] = "pending"
    selected: Play | None = None
    effect: Effect | None = None
    effect_event: str | None = None
    completed_event: str | None = None
    followups: tuple[str, ...] = ()
    withdrawn_event: str | None = None
    declined_event: str | None = None

    @model_validator(mode="after")
    def actual_authority(self) -> "HandlerPlay":
        if self.nonbody_only and (
            self.source != "required"
            or self.clause != "all_out_assault.low"
            or len(self.targets) != 1
            or self.targets[0].kind != "pilot"
        ):
            raise ValueError("Only this original-ended mandatory source owns a nonbody procedure")
        if self.target_controllers and set(self.target_controllers) != {
            x.token for x in self.targets
        }:
            raise ValueError("Freeze the actual human audience of each original target")
        if len(set(self.targets)) != len(self.targets):
            raise ValueError("Keep actual affected originals distinct")
        if self.source == "battle_counter" and (
            self.chooser_actor is None
            or not self.source_action
            or not self.source_choice
            or len(self.targets) != 1
            or self.appointment is not None
        ):
            raise ValueError("A counter is only its actual chooser against the actual attacker")
        if self.source == "required" and (
            self.appointment is None
            or self.chooser_actor is not None
            or not self.source_action
            or not self.source_choice
            or self.final_original
        ):
            raise ValueError(
                "A required Handler Play uses its exact source and actual human GM appointment"
            )
        if self.source == "ordinary" and (
            self.appointment is None
            or self.source_action
            or self.source_choice
            or self.final_original
        ):
            raise ValueError("Ordinary Handler Plays use the actual human GM appointment")
        if self.state not in ("pending", "withdrawn", "declined") and (
            self.selected is None or self.effect is None or self.effect_event is None
        ):
            raise ValueError("The actual owner must choose and commit the effect")
        if self.state == "withdrawn" and (
            self.source != "ordinary" or self.effect is not None or not self.withdrawn_event
        ):
            raise ValueError("Only an untouched ordinary move can be explicitly withdrawn")
        if self.state == "declined" and (
            self.source != "battle_counter" or self.effect is not None or not self.declined_event
        ):
            raise ValueError(
                "Only its actual source owner may decline an untouched optional counter"
            )
        if self.state == "complete" and not self.completed_event:
            raise ValueError(
                "Finish actual effect and required followups before completing the Play"
            )
        return self
