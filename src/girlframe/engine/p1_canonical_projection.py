"""Narrow canonical comparison only; no authorization, availability or rule completion."""

import json
from typing import Literal

from pydantic import Field

from girlframe.engine.m2 import GameState, PilotSheet, spend_heat
from girlframe.engine.m3_actor_state import ActorRef, Model


class ProjectionError(ValueError):
    """A comparison failed without disclosing protected canonical values."""


# Explicit inventories: new top-level/sheet fields require classification review.
# Only sheets/revision and the subject's heat/revision may change in this slice.
GAME_FIELDS = frozenset(
    {
        "schema_version",
        "revision",
        "sheets",
        "order",
        "handler",
        "handler_heat",
        "handler_tags",
        "handler_persona",
        "handler_archives",
        "handler_departures",
        "mockingbird",
        "passengers",
        "handler_consequences",
        "handler_injuries",
        "handler_opportunities",
        "handler_fatal_sources",
        "role_punishments",
        "handler_plays",
        "held_items",
        "item_transfers",
        "bonds",
        "actor_bonds",
        "alpha_broken",
        "helpless_conditions",
        "leviathan_obsessions",
        "leviathan_identity_authorities",
        "external_poses",
        "leviathan_arrivals",
        "obligations",
        "facts",
        "intense_tag_bonus",
        "strain",
        "world",
        "director_contexts",
        "scene_casts",
        "regulations",
        "repair_shortages",
        "repair_quotes",
        "supply_losses",
        "requisitions",
        "placements",
        "frame_locks",
        "parked_frames",
        "escort_journeys",
        "personal_firearms",
        "refusal_bonuses",
        "contraband_finds",
        "career_archives",
        "career_returns",
        "incarnation_bindings",
        "unlinked_careers",
        "harpy_states",
        "native_harpies",
        "janus_cores",
        "battery_links",
        "neural_connections",
        "frame_commands",
        "harpy_setups",
        "handler_girl_void",
        "handler_void",
        "harpy_rests",
        "harpy_defeats",
        "harpy_defeat_declarations",
        "void_rifts",
        "harpy_travels",
        "void_thresholds",
        "lobotomies",
        "enforcer_ranks",
        "enforcer_accusations",
        "enforcer_grasps",
    }
)

SHEET_FIELDS = frozenset(
    {
        "owner",
        "character_id",
        "revision",
        "callsign",
        "girl",
        "frame",
        "source_fingerprint",
        "source_profile_revision",
        "review",
        "identities",
        "obsession_sources",
        "assets",
        "tags",
        "heat",
        "permissions",
        "mentor",
        "pair",
        "helpless_against",
        "status_marked",
        "maxims_marked",
        "public_fields",
        "sedation_locked",
        "sedation_period",
        "libido_inhibited",
        "obsolescence_marked",
        "frame_scrapped",
        "frame_runtime",
        "medical_state",
        "girl_runtime",
        "blocked_plays",
    }
)


class HeatSpendScope(Model):
    actor: ActorRef
    amount: int = Field(ge=1)
    protected: tuple[ActorRef, ...] = Field(min_length=1)


class ProjectionEvidence(Model):
    actor: ActorRef
    protected: tuple[ActorRef, ...]
    amount: int
    from_revision: int
    to_revision: int
    classification: Literal["pilot_heat_spend_only"] = "pilot_heat_spend_only"
    authorization: Literal[False] = False


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ProjectionError("Ambiguous canonical JSON")
        result[key] = value
    return result


def _reject_constant(_value: str) -> None:
    raise ProjectionError("Non-finite canonical JSON")


def _state(body: str) -> GameState:
    try:
        json.loads(body, object_pairs_hook=_unique_object, parse_constant=_reject_constant)
        return GameState.model_validate_json(body)
    except (TypeError, ValueError):
        raise ProjectionError("Canonical snapshot cannot be classified") from None


def _pilot(state: GameState, actor: ActorRef) -> PilotSheet:
    if actor.kind != "pilot":
        raise ProjectionError("Only original Pilot comparisons are supported")
    sheet = state.sheets.get(actor.entity)
    if sheet is None or str(sheet.owner) != actor.entity or sheet.character_id != actor.incarnation:
        raise ProjectionError("Original actor is missing or replaced")
    return sheet


def verify_heat_spend(
    before_body: str, after_body: str, scope: HeatSpendScope
) -> ProjectionEvidence:
    """Prove exactly one Pilot's existing spend_heat transition, nothing else.

    Protected refs and the spend declaration are comparison inputs, not trusted
    availability or consent. Future source adapters must authenticate both.
    Entire canonical state is compared; cost is not actor-sized or constant-time.
    This supports a canonical substep, not a complete existing gameplay command.
    """
    if set(GameState.model_fields) != GAME_FIELDS or set(PilotSheet.model_fields) != SHEET_FIELDS:
        raise ProjectionError("Canonical field inventory needs classification review")
    scope = HeatSpendScope.model_validate(scope.model_dump())
    if len(set(scope.protected)) != len(scope.protected):
        raise ProjectionError("Duplicate protected actor comparison")
    before, after = _state(before_body), _state(after_body)
    for actor in (scope.actor, *scope.protected):
        _pilot(before, actor)
        _pilot(after, actor)
    if scope.actor in scope.protected:
        raise ProjectionError("Protected actor cannot spend Heat in this slice")
    expected = _state(before_body)
    subject = _pilot(expected, scope.actor)
    try:
        spend_heat(subject, scope.amount)
    except ValueError:
        raise ProjectionError("Heat spend does not satisfy the existing rule") from None
    subject.revision += 1
    expected.revision += 1
    # Equality includes every current field, not an ownership guess or recursive
    # search for a matching account ID. Unknown facts may remain, never change.
    if expected != after:
        raise ProjectionError("Unclassified canonical change; preserve the original actors")
    return ProjectionEvidence(
        actor=scope.actor,
        protected=scope.protected,
        amount=scope.amount,
        from_revision=before.revision,
        to_revision=after.revision,
    )
