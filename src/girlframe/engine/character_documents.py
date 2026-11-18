"""Versioned portable creation choices and read-only character sheet documents.

Files contain data, never authority: services rebind ownership, live coordination,
campaign policy and revisions before a creation document can be saved.
"""

import json
import math
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from girlframe.engine.creation import AssetChoice, CreationDraft
from girlframe.engine.creation_details import GirlDetails
from girlframe.engine.drafts import DraftInput
from girlframe.engine.fanbase import Fanbase
from girlframe.engine.npc_bonds import NpcBond
from girlframe.engine.playbooks import canonical_frame, canonical_girl, normalize_frame_fields

MAX_DOCUMENT_BYTES = 256 * 1024
DRAFT_FORMAT: Literal["harpyengine.character-draft"] = "harpyengine.character-draft"
SHEET_FORMAT: Literal["harpyengine.character-sheet"] = "harpyengine.character-sheet"
TRUSTED_CREATION_FIELDS = frozenset(
    {
        "frame_setup",
        "pair_source_token",
        "shared_tokens",
        "starting_bond_id",
        "additional_starting_bond_id",
        "prior_missions",
        "cadre_discussed",
    }
)


class DocumentError(ValueError):
    """Safe file feedback which does not include uploaded private content."""


class PortableProfile(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True, hide_input_in_errors=True)
    callsign: str = Field(min_length=1, max_length=32)
    girl_playbook: str = Field(min_length=1, max_length=60)
    frame_playbook: str = Field(min_length=1, max_length=60)
    # None is omitted private content, not a request to clear existing notes.
    notes: str | None = Field(default=None, max_length=1000)

    @field_validator("callsign", "girl_playbook", "frame_playbook")
    @classmethod
    def single_line(cls, value: str) -> str:
        value = value.strip()
        if not value or any(ord(char) < 32 or ord(char) == 127 for char in value):
            raise ValueError("Use a nonempty single-line label")
        return value

    @field_validator("girl_playbook")
    @classmethod
    def girl(cls, value: str) -> str:
        return canonical_girl(value)

    @field_validator("frame_playbook")
    @classmethod
    def frame(cls, value: str) -> str:
        return canonical_frame(value)

    def as_profile(self, existing_notes: str = "") -> DraftInput:
        return DraftInput(
            callsign=self.callsign,
            girl_playbook=self.girl_playbook,
            frame_playbook=self.frame_playbook,
            notes=existing_notes if self.notes is None else self.notes,
        )


class PortableChoices(BaseModel):
    """Player-owned descriptions/choices only; live agreement IDs are excluded."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True, hide_input_in_errors=True)
    girl_assets: tuple[AssetChoice, ...] = Field(default=(), max_length=2)
    frame_assets: tuple[AssetChoice, ...] = Field(default=(), max_length=2)
    void_asset: str | None = None
    frame_name: str = Field(default="", max_length=80)
    girl_appearance: str = Field(default="", max_length=700)
    frame_appearance: str = Field(default="", max_length=700)
    pair_asset_descriptions: tuple[AssetChoice, ...] = Field(default=(), max_length=2)
    npc_bonds: tuple[NpcBond, ...] = Field(default=(), max_length=2)
    dna_basis: str = Field(default="", max_length=300)
    fanbase: Fanbase | None = None
    girl_details: GirlDetails | None = None


class CharacterDraftDocument(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True, hide_input_in_errors=True)
    format: Literal["harpyengine.character-draft"] = DRAFT_FORMAT
    schema_version: Literal[1] = 1
    profile: PortableProfile
    creation: PortableChoices = PortableChoices()

    def to_creation(self, **trusted_source_fields: Any) -> CreationDraft:
        """Rebind server-owned facts; a file cannot supply these keyword fields."""
        if not trusted_source_fields.keys() <= TRUSTED_CREATION_FIELDS:
            raise DocumentError("Unsupported trusted creation field")
        data = self.creation.model_dump(mode="json") | {
            "girl_playbook": self.profile.girl_playbook,
            "frame_playbook": self.profile.frame_playbook,
        }
        data.update(trusted_source_fields)
        # JSON-mode validation accepts arrays for strict tuple fields while all
        # scalar types, static choices and cross-playbook constraints stay strict.
        return CreationDraft.model_validate_json(json.dumps(data, default=_model_json))

    @model_validator(mode="after")
    def legal_static_choices(self) -> Self:
        self.to_creation()
        return self


class CharacterSheetDocument(BaseModel):
    """A display snapshot. This format is never accepted by the draft importer."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True, hide_input_in_errors=True)
    format: Literal["harpyengine.character-sheet"] = SHEET_FORMAT
    schema_version: Literal[1] = 1
    engine_version: str
    audience: Literal["owner", "public"]
    owner_id: str = Field(pattern=r"^[1-9][0-9]{0,19}$")
    character_id: str | None = None
    revision: int = Field(ge=0)
    display_name: str = ""
    members: dict[str, str] = Field(default_factory=dict)
    sheet: dict[str, Any]
    rules_status: Literal["RULES_SUBSET"] = "RULES_SUBSET"

    @field_validator("sheet")
    @classmethod
    def frame_names(cls, sheet: dict[str, Any]) -> dict[str, Any]:
        return dict(normalize_frame_fields(sheet))


def _model_json(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    raise TypeError("Unsupported document value")


def _object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise DocumentError("Invalid character document: duplicate JSON key")
        result[key] = value
    return result


def _nonfinite(_: str) -> Any:
    raise DocumentError("Invalid character document: non-finite JSON number")


def _float(value: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        _nonfinite(value)
    return number


def parse_draft(raw: bytes) -> CharacterDraftDocument:
    """Parse untrusted UTF-8 creation JSON with bounded, non-echoing errors."""
    if not isinstance(raw, bytes) or len(raw) > MAX_DOCUMENT_BYTES:
        raise DocumentError("Character JSON must be UTF-8 and at most 256 KiB")
    try:
        data = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_object,
            parse_constant=_nonfinite,
            parse_float=_float,
        )
        if not isinstance(data, dict) or data.get("format") != DRAFT_FORMAT:
            raise DocumentError("Import requires a harpyengine.character-draft document")
        if type(data.get("schema_version")) is not int or data["schema_version"] != 1:
            raise DocumentError("Unsupported or missing character document schema version")
        # Round-trip the already strictly parsed value to retain Pydantic's
        # strict JSON-mode handling of tuples and nested existing engine types.
        return CharacterDraftDocument.model_validate_json(json.dumps(data, allow_nan=False))
    except DocumentError:
        raise
    except (UnicodeError, ValueError, TypeError, RecursionError, ValidationError):
        raise DocumentError(
            "Invalid character document: check schema version, fields and creation choices"
        ) from None


def encode_document(document: CharacterDraftDocument | CharacterSheetDocument) -> bytes:
    """Stable portable JSON; no canonical event/state objects are accepted."""
    if not isinstance(document, (CharacterDraftDocument, CharacterSheetDocument)):
        raise DocumentError("Choose a supported character document")
    try:
        return (
            json.dumps(
                document.model_dump(mode="json"),
                ensure_ascii=False,
                sort_keys=True,
                indent=2,
                allow_nan=False,
            )
            + "\n"
        ).encode("utf-8")
    except (ValueError, TypeError, RecursionError):
        raise DocumentError("Character document cannot be encoded as finite JSON") from None
