"""Source inventory and truthful certification gates; no storage or Discord dependencies."""

from collections import Counter
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from girlframe.engine.frame_classes import FRAME_CLASSES, FrameClass, FrameRule

RuleId = Annotated[str, Field(pattern=r"^[a-z0-9][a-z0-9_.-]+$")]


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class Anchor(Model):
    document: Literal["rulebook", "sheets"] = "rulebook"
    pdf_page: int = Field(ge=1)
    printed_page: int | None = Field(default=None, ge=1)
    heading: str = Field(min_length=1, max_length=180)


class Contract(Model):
    trigger: str = Field(min_length=1)
    actor_type: str = Field(min_length=1)
    pre_roll_sources: tuple[str, ...]
    roll_kind: Literal["2d6", "d6", "diceless", "special"]
    allowed_modifiers: tuple[str, ...]
    tier_options: dict[str, tuple[str, ...]]
    choice_ownership: str = Field(min_length=1)
    target_policy: str = Field(min_length=1)
    post_roll_effects: tuple[str, ...]
    mandatory_followups: tuple[str, ...]
    handler_or_gm_intervention: str = Field(min_length=1)
    test_fixture_ids: tuple[str, ...] = Field(min_length=1)


class Entry(Model):
    id: RuleId
    title: str = Field(min_length=1, max_length=180)
    scope: str = Field(min_length=1)
    module: Literal["core", "ancillary"] = "core"
    kind: Literal["mechanic", "playbook", "play", "table_event", "endgame", "reference"]
    source: Anchor
    required: bool = True
    implementation: Literal["unimplemented", "subset", "implemented"] = "unimplemented"
    source_audit: Literal["inventoried", "audited"] = "inventoried"
    independent_review: Literal["pending", "approved"] = "pending"
    reviewer: str | None = None
    review_reference: str | None = None
    contract: Contract | None = None
    dependencies: tuple[str, ...] = ()
    test_evidence: tuple[str, ...] = ()
    m2_play_id: str | None = None
    aliases: tuple[RuleId, ...] = ()
    frame_playbook: str | None = None
    frame_class: FrameClass | None = None
    frame_rule: FrameRule | None = None

    @model_validator(mode="after")
    def certification(self) -> "Entry":
        if self.id in self.aliases or len(set(self.aliases)) != len(self.aliases):
            raise ValueError("A rule has distinct historical aliases without its own canonical ID")
        if any(x is not None for x in (self.frame_playbook, self.frame_class, self.frame_rule)):
            if self.scope != "frame" or self.frame_rule is None or self.frame_class is None:
                raise ValueError(
                    "Frame classification needs actual Frame scope, rule category and class"
                )
            if self.frame_rule == "class_requisition":
                if self.frame_playbook is not None or self.kind != "mechanic":
                    raise ValueError(
                        "A class Requisition belongs to its class rather than a Frame playbook"
                    )
            elif self.frame_playbook not in FRAME_CLASSES:
                raise ValueError("Use an official Frame playbook in source classification")
            elif FRAME_CLASSES[self.frame_playbook] != self.frame_class:
                raise ValueError("Frame class must match its actual official playbook")
            if (self.frame_rule == "playbook") != (self.kind == "playbook"):
                raise ValueError(
                    "A Frame playbook heading and a specific runtime rule are distinct"
                )
        if self.frame_rule in ("base", "requisition") and self.kind not in ("mechanic", "play"):
            raise ValueError("Specific Frame classification requires an actual mechanic or Play")
        if self.implementation == "implemented" and (
            self.contract is None or not self.test_evidence or self.source_audit != "audited"
        ):
            raise ValueError(
                "Implemented rules require an audited contract and executed test evidence"
            )
        if self.independent_review == "approved" and (
            self.implementation != "implemented" or not self.reviewer or not self.review_reference
        ):
            raise ValueError(
                "Independent approval requires complete implementation and review provenance"
            )
        return self

    @property
    def verified(self) -> bool:
        return self.implementation == "implemented" and self.independent_review == "approved"


class Document(Model):
    id: Literal["rulebook", "sheets"]
    name: str
    pdf_pages: int = Field(ge=1)
    version_note: str


class Ruling(Model):
    id: str
    summary: str
    provenance: Literal["owner_approved_campaign_ruling"]
    source: str
    authority: Literal["explicit_owner", "delegated_recommendation"] = "explicit_owner"
    rationale: str = ""
    alternatives: tuple[str, ...] = ()
    policy_key: str | None = None
    clarity_review: bool = True
    revision: int = Field(default=1, ge=1)
    implementation_note: str = ""
    change_impact: str = ""

    @model_validator(mode="after")
    def delegated_record(self) -> "Ruling":
        if self.authority == "delegated_recommendation" and (
            not self.rationale.strip()
            or not self.alternatives
            or not self.implementation_note.strip()
            or not self.change_impact.strip()
        ):
            raise ValueError(
                "Delegated rulings need rationale, alternatives and implementation/change notes"
            )
        return self


class Registry(Model):
    schema_version: Literal[1] = 1
    ruleset: Literal["girlframe-m3-source-inventory-1"] = "girlframe-m3-source-inventory-1"
    inventory_status: Literal["branch_audit_pending", "complete"] = "branch_audit_pending"
    enabled_modules: frozenset[Literal["core", "ancillary"]] = frozenset({"core"})
    source_documents: tuple[Document, ...]
    campaign_rulings: tuple[Ruling, ...] = ()
    entries: tuple[Entry, ...]

    @model_validator(mode="after")
    def consistent(self) -> "Registry":
        if "core" not in self.enabled_modules:
            raise ValueError("The core rules module must remain enabled")
        documents = {x.id: x for x in self.source_documents}
        if len(documents) != len(self.source_documents):
            raise ValueError("Source document IDs must be unique")
        ids = {x.id for x in self.entries}
        if len(ids) != len(self.entries):
            raise ValueError("Rule IDs must be unique")
        references = [value for entry in self.entries for value in (entry.id, *entry.aliases)]
        if len(references) != len(set(references)):
            raise ValueError(
                "Historical rule aliases cannot collide with another canonical ID or alias"
            )
        if len({x.id for x in self.campaign_rulings}) != len(self.campaign_rulings):
            raise ValueError("Campaign ruling IDs must be unique")
        for entry in self.entries:
            document = documents.get(entry.source.document)
            if document is None or entry.source.pdf_page > document.pdf_pages:
                raise ValueError("Source page is outside the supplied document")
            if not set(entry.dependencies) <= ids or entry.id in entry.dependencies:
                raise ValueError("Rule dependency is missing or self-referential")
        return self

    @property
    def coverage(self) -> Literal["RULES_SUBSET", "RULES_COMPLETE"]:
        required = [x for x in self.entries if x.required and x.module in self.enabled_modules]
        if self.inventory_status == "complete" and required and all(x.verified for x in required):
            return "RULES_COMPLETE"
        return "RULES_SUBSET"

    def summary(self) -> dict[str, object]:
        return {
            "coverage": self.coverage,
            "inventory_status": self.inventory_status,
            "entries": len(self.entries),
            "enabled_modules": sorted(self.enabled_modules),
            "required": sum(x.required and x.module in self.enabled_modules for x in self.entries),
            "verified": sum(
                x.verified for x in self.entries if x.required and x.module in self.enabled_modules
            ),
            "implementation": dict(Counter(x.implementation for x in self.entries)),
        }

    def require_available(self, identity: str) -> Entry:
        entry = self.entry(identity)
        if entry.module not in self.enabled_modules:
            raise ValueError("MODULE_DISABLED: this rule belongs to a disabled optional module")
        if not entry.verified:
            # Report only canonical public registry metadata, never the caller's
            # free-form identity, private action context or reviewer references.
            # Preserve the prefix consumed by native adapters and keep fail-closed
            # admission unchanged, including for historical aliases.
            raise ValueError(
                "UNSUPPORTED_RULE: implementation and review are incomplete "
                f"[rule={entry.id}; implementation={entry.implementation}; "
                f"source_audit={entry.source_audit}; "
                f"independent_review={entry.independent_review}]"
            )
        return entry

    def entry(self, identity: str) -> Entry:
        entry = next((x for x in self.entries if x.id == identity or identity in x.aliases), None)
        if entry is None:
            raise ValueError("UNSUPPORTED_RULE: unknown registry entry")
        return entry
