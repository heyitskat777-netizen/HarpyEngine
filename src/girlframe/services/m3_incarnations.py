"""Authenticate legacy identities from original snapshots; never infer a person from a UID."""

from typing import Any

import sqlalchemy as sa
from pydantic import Field
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine.identity import Snowflake
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef, Model
from girlframe.engine.m3_careers import binding, profile_character
from girlframe.services.onboarding import OnboardingStore, WorkflowError


class IdentityProof(Model):
    owner: Snowflake
    character: str = Field(min_length=1)
    profile: str = Field(min_length=1)
    source_profile_revision: int = Field(ge=1)
    snapshot_event: str = Field(min_length=1)
    binding_event: str | None = None
    canonical_event: str | None = None


def proof(
    c: Connection,
    campaign: str,
    state: GameState,
    owner: int,
    *,
    require_current_profile: bool = False,
) -> IdentityProof:
    sheet = state.sheets.get(str(owner))
    profile = c.execute(
        sa.select(t.characters.c.id, t.characters.c.revision).where(
            t.characters.c.campaign_id == campaign, t.characters.c.user_id == str(owner)
        )
    ).first()
    if sheet is None or sheet.owner != owner or profile is None:
        raise WorkflowError("STALE_CHARACTER: recover the actual original active character.")
    if require_current_profile and profile.revision != sheet.source_profile_revision:
        raise WorkflowError(
            "STALE_PROFILE: active profile changed; canonical resources were preserved."
        )
    snapshot = c.execute(
        sa.select(t.snapshots.c.character_id, t.snapshots.c.event_id)
        .join(
            t.events,
            sa.and_(
                t.events.c.campaign_id == t.snapshots.c.campaign_id,
                t.events.c.id == t.snapshots.c.event_id,
            ),
        )
        .where(
            t.snapshots.c.campaign_id == campaign,
            t.snapshots.c.user_id == str(owner),
            t.snapshots.c.revision == sheet.source_profile_revision,
        )
    ).first()
    if (
        snapshot is None
        or snapshot.character_id != profile.id
        or sheet.source_profile_revision < 1
        or profile.revision < sheet.source_profile_revision
    ):
        raise WorkflowError(
            "SOURCE_IDENTITY_MISSING: recover the original profile revision snapshot."
        )
    current = binding(state, owner)
    if current is not None and (
        current.profile_id != snapshot.character_id
        or sheet.source_profile_revision < current.first_profile_revision
    ):
        raise WorkflowError("STALE_CHARACTER: old resources cannot inherit a replacement identity.")
    try:
        character = profile_character(state, owner, profile.id, profile.revision)
    except ValueError as error:
        raise WorkflowError(str(error)) from None
    if sheet.character_id is not None and sheet.character_id != character:
        raise WorkflowError("STALE_CHARACTER: resources belong to another original character.")
    canonical_event = None
    if sheet.character_id is None and current is not None:
        raw = c.scalar(
            sa.select(t.m2["m2_state_history"].c.body_json).where(
                t.m2["m2_state_history"].c.campaign_id == campaign,
                t.m2["m2_state_history"].c.event_id == current.source_event,
            )
        )
        source = GameState.model_validate_json(raw) if raw else None
        if source is None or current not in source.incarnation_bindings:
            raise WorkflowError(
                "SOURCE_IDENTITY_MISSING: recover the actual incarnation binding event."
            )
        history = t.m2["m2_state_history"]
        prefix = '$.sheets."' + str(owner) + '".'
        canonical_event = c.scalar(
            sa.select(history.c.event_id)
            .where(
                history.c.campaign_id == campaign,
                history.c.revision <= state.revision,
                sa.func.json_extract(history.c.body_json, prefix + "character_id")
                == current.character,
                sa.func.json_extract(history.c.body_json, prefix + "source_profile_revision")
                == sheet.source_profile_revision,
                sa.func.json_extract(history.c.body_json, prefix + "source_fingerprint")
                == sheet.source_fingerprint,
            )
            .order_by(history.c.revision.desc())
            .limit(1)
        )
        if canonical_event is None:
            raise WorkflowError(
                "SOURCE_IDENTITY_MISSING: a replacement draft cannot relabel an old resource sheet."
            )
    return IdentityProof(
        owner=owner,
        character=character,
        profile=profile.id,
        source_profile_revision=sheet.source_profile_revision,
        snapshot_event=snapshot.event_id,
        binding_event=current.source_event if current else None,
        canonical_event=canonical_event,
    )


def identity(
    c: Connection,
    campaign: str,
    state: GameState,
    owner: int,
    *,
    require_current_profile: bool = True,
) -> str:
    # Existing explicitly bound canonical sheets retain their original contract.
    # Authorized profile changes stage the next snapshot after the actual event;
    # they must not be mistaken for a legacy unknown identity during that write.
    sheet = state.sheets.get(str(owner))
    if sheet is not None and sheet.character_id is not None:
        profile = c.execute(
            sa.select(t.characters.c.id, t.characters.c.revision).where(
                t.characters.c.campaign_id == campaign, t.characters.c.user_id == str(owner)
            )
        ).first()
        if profile is None or sheet.owner != owner:
            raise WorkflowError("STALE_CHARACTER: recover the actual original active character.")
        if require_current_profile and profile.revision != sheet.source_profile_revision:
            raise WorkflowError("STALE_PROFILE: active profile changed; resources were preserved.")
        current = binding(state, owner)
        if current is not None and sheet.source_profile_revision < current.first_profile_revision:
            raise WorkflowError(
                "STALE_CHARACTER: old resources cannot inherit replacement authority."
            )
        try:
            actual = profile_character(state, owner, profile.id, profile.revision)
        except ValueError as error:
            raise WorkflowError(str(error)) from None
        if actual != sheet.character_id:
            raise WorkflowError("STALE_CHARACTER: resources belong to another original character.")
        return actual
    return proof(
        c, campaign, state, owner, require_current_profile=require_current_profile
    ).character


def hydrate(c: Connection, campaign: str, original: GameState) -> GameState:
    """A private read projection: set only authenticated missing IDs, without writing anything."""
    state = GameState.model_validate_json(original.model_dump_json())
    for uid, sheet in state.sheets.items():
        if sheet.character_id is None:
            sheet.character_id = proof(c, campaign, state, int(uid)).character
    return state


def prepare_write(
    c: Connection, campaign: str, original: GameState
) -> tuple[GameState, list[dict[str, Any]]]:
    """Return exact identity-only write evidence before the caller creates its real audit event."""
    state = hydrate(c, campaign, original)
    raw = c.scalar(
        sa.select(t.m2["m2_state"].c.body_json).where(t.m2["m2_state"].c.campaign_id == campaign)
    )
    previous = GameState.model_validate_json(raw) if raw else GameState()
    evidence = []
    for uid, sheet in previous.sheets.items():
        if sheet.character_id is not None:
            continue
        saved = proof(c, campaign, previous, int(uid))
        actor = ActorRef(kind="pilot", entity=uid, incarnation=saved.character)
        active = state.sheets.get(uid)
        if not (
            (active is not None and active.character_id == saved.character)
            or any(x.actor == actor for x in state.career_archives)
        ):
            raise WorkflowError("Preserve the actual legacy original or its source-owned archive.")
        evidence.append(saved.model_dump(mode="json"))
    return state, evidence


def backfill(
    store: OnboardingStore, *, apply: bool, key: str, operator: str = "offline-maintenance"
) -> dict[str, object]:
    """Offline maintenance is explicitly identified, not a fabricated Discord action."""
    from girlframe.services.m2_game import GameService

    def operation(c: Connection) -> dict[str, object]:
        raw = c.scalar(
            sa.select(t.m2["m2_state"].c.body_json).where(
                t.m2["m2_state"].c.campaign_id == store.campaign_id
            )
        )
        original = GameState.model_validate_json(raw) if raw else GameState()
        state, evidence = prepare_write(c, store.campaign_id, original)
        if apply and evidence:
            GameService(store).event(
                c, "maintenance:" + operator, key, "m3.legacy_incarnations_bound", state
            )
        return dict(
            dry_run=not apply,
            identities_found=len(evidence),
            identities_persisted=len(evidence) if apply else 0,
            game_revision=state.revision,
        )

    if apply:
        with store.transaction() as c:
            return operation(c)
    with store.engine.connect() as c:
        return operation(c)
