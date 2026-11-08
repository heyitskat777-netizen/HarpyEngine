"""Actual native Identity slots and owner-disclosed copy content for Changeling."""

import json
from typing import TYPE_CHECKING, Any

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_changeling as rules
from girlframe.engine.m2 import GameState, IdentityState, PilotSheet, shift_status
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_clone_am import additional_identities
from girlframe.engine.m3_identity_slots import bind, replacement_slot
from girlframe.engine.m3_leviathan_obsession import require_identity_change, require_unlocked
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_handler_advancements import _history
from girlframe.services.onboarding import WorkflowError

if TYPE_CHECKING:
    from girlframe.services.m2_game import GameService


def _sheet(state: GameState, actor: ActorRef) -> PilotSheet:
    sheet = state.sheets.get(actor.entity) if actor.kind == "pilot" else None
    if sheet is None or sheet.character_id != actor.incarnation:
        raise WorkflowError("SOURCE_IDENTITY_BODY_REQUIRED: use the actual original native slots")
    return sheet


def _legal(state: GameState, actor: ActorRef, item: IdentityState) -> bool:
    sheet = _sheet(state, actor)
    if item.protected or item.paired or item.am_limiter or item.id in sheet.sedation_locked:
        return False
    try:
        require_unlocked(sheet.identities, (item.id,))
        require_identity_change(state, actor, (item.id,))
    except ValueError:
        return False
    return True


def identity_options(
    game: "GameService",
    c: Connection,
    state: GameState,
    owner: ActorRef,
    *,
    chooser: ActorRef,
    clause: str,
) -> list[tuple[str, str]]:
    if clause not in ("blank_low", "blank_all", "fingers_counter"):
        raise WorkflowError("Use the actual printed erasure clause")
    sheet = _sheet(state, owner)
    resolve(state, owner, profiles(c, game.store.campaign_id), require_current_profile=False)
    if additional_identities(state, int(owner.entity)):
        raise WorkflowError(
            "SOURCE_CLONE_IDENTITY_ERASURE_REQUIRED: preserve actual copy aftermath"
        )
    return [(item.id, item.name) for item in sheet.identities if _legal(state, owner, item)]


def identity_requirements(
    game: "GameService",
    c: Connection,
    state: GameState,
    owner: ActorRef,
) -> dict[str, Any]:
    sheet = _sheet(state, owner)
    return dict(preserved=[item.id for item in sheet.identities if not _legal(state, owner, item)])


def erase_identities(
    game: "GameService",
    c: Connection,
    state: GameState,
    owner: ActorRef,
    ids: tuple[str, ...],
    event: str,
    source: str,
    *,
    clause: str,
) -> tuple[GameState, tuple[str, ...]]:
    sheet = _sheet(state, owner)
    options = dict(identity_options(game, c, state, owner, chooser=owner, clause=clause))
    actual = {item.id for item in sheet.identities}
    if not event or not source or len(set(ids)) != len(ids) or not set(ids) <= actual:
        raise WorkflowError("Preserve the exact distinct actual original Identity batch")
    if clause == "blank_all":
        session = rules.session(state, source)
        if session.actor != owner or session.total < 11 or ids != session.identities:
            raise WorkflowError("Use exactly the initial held batch of this real high result")
        selected = tuple(item for item in ids if item in options)
    else:
        if len(ids) != 1 or not set(ids) <= set(options):
            raise WorkflowError("Choose one actual legal erased Identity")
        selected = ids
    changed = GameState.model_validate_json(state.model_dump_json())
    target = changed.sheets[owner.entity]
    require_identity_change(changed, owner, selected)
    require_unlocked(target.identities, selected)
    target.identities = [item for item in target.identities if item.id not in selected]
    if selected:
        target.revision += 1
        changed.sheets[owner.entity] = bind(target)
    changed.facts.append(
        dict(
            kind="changeling_identity_erased",
            event=event,
            source=source,
            actor=owner.model_dump_json(),
            clause=clause,
            ids=json.dumps(selected),
            initial=json.dumps(ids),
            preserved=json.dumps(tuple(item for item in ids if item not in selected)),
        )
    )
    return changed, ()


def erased_batch(state: GameState, source: rules.Session) -> bool:
    fact = next(
        (
            item
            for item in state.facts
            if item.get("kind") == "changeling_identity_erased"
            and item.get("source") == source.id
            and item.get("event") == source.erased_event
        ),
        None,
    )
    if fact is None:
        return False
    removed = set(json.loads(fact["ids"]))
    return not removed & {item.id for item in _sheet(state, source.actor).identities}


def grant_blank(
    game: "GameService",
    c: Connection,
    state: GameState,
    source: rules.Session,
    event: str,
) -> tuple[GameState, str, tuple[str, ...]]:
    if source.total < 11 or not erased_batch(state, source):
        raise WorkflowError("Complete the actual high result's legal erasure batch first")
    changed = GameState.model_validate_json(state.model_dump_json())
    sheet = bind(_sheet(changed, source.actor))
    identity = rules.identity("blank-identity", source.id)
    if any(item.id == identity for item in sheet.identities):
        raise WorkflowError("The actual high source grants its Blank Slate exactly once")
    slot = replacement_slot(sheet, None)
    if slot is None:
        raise WorkflowError("SOURCE_BLANK_SLOT_REQUIRED: preserve genuine reserved Identity slots")
    sheet.identities.append(IdentityState(id=identity, name="Blank Slate", slot=slot))
    sheet.revision += 1
    changed.sheets[source.actor.entity] = sheet
    return changed, identity, ()


def prove_disclosure(
    game: "GameService",
    c: Connection,
    state: GameState,
    value: rules.IdentityDisclosure,
) -> None:
    row = (
        c.execute(
            sa.select(t.events).where(
                t.events.c.campaign_id == game.store.campaign_id, t.events.c.id == value.event
            )
        )
        .mappings()
        .first()
    )
    if (
        row is None
        or row["kind"] != "m3.changeling_identity_disclosed"
        or row["actor_id"] != str(value.controller)
    ):
        raise WorkflowError("Recover the actual owner's original factual Identity disclosure")
    saved = _history(c, game, value.event)
    if rules.record(saved, rules.IdentityDisclosure, value.id) != value:
        raise WorkflowError("Preserve the actual disclosed content and conversation")
    actual = resolve(
        state, value.actor, profiles(c, game.store.campaign_id), require_current_profile=False
    )
    if not any(
        item.id == value.identity and item.name == value.label for item in actual.identities
    ):
        raise WorkflowError("The speaker must actually still possess this disclosed Identity")


def copy_choices(
    game: "GameService",
    c: Connection,
    state: GameState,
    owner: ActorRef,
    other: ActorRef,
) -> list[dict[str, Any]]:
    result = []
    for value in rules.records(state, rules.IdentityDisclosure):
        if value.actor != other or value.addressed != owner:
            continue
        prove_disclosure(game, c, state, value)
        result.append(dict(id=value.id, label=value.label, identity=value.identity))
    return result


def replace_blank(
    game: "GameService",
    c: Connection,
    state: GameState,
    grant: rules.BlankSlate,
    other: ActorRef,
    identity_id: str,
    event: str,
) -> tuple[GameState, str, tuple[str, ...]]:
    disclosure = rules.record(state, rules.IdentityDisclosure, identity_id)
    if disclosure.actor != other or disclosure.addressed != grant.actor:
        raise WorkflowError("Use content actually disclosed to the original Changeling")
    prove_disclosure(game, c, state, disclosure)
    sheet = _sheet(state, grant.actor)
    blank = next((item for item in sheet.identities if item.id == grant.identity), None)
    if (
        grant.replaced_event
        or blank is None
        or blank.name != "Blank Slate"
        or not _legal(state, grant.actor, blank)
    ):
        raise WorkflowError("Replace the actual original still-held Blank Slate once")
    changed = GameState.model_validate_json(state.model_dump_json())
    target = changed.sheets[grant.actor.entity]
    target.identities = [
        item.model_copy(update=dict(name=disclosure.label)) if item.id == blank.id else item
        for item in target.identities
    ]
    target.revision += 1
    return changed, blank.id, ()


def can_lower_status(game: "GameService", c: Connection, state: GameState, actor: ActorRef) -> bool:
    actual = resolve(
        state, actor, profiles(c, game.store.campaign_id), require_current_profile=False
    )
    return (
        actor.kind == "pilot" and int(actor.entity) in state.order and actual.rules == "girl_frame"
    )


def status(
    game: "GameService",
    c: Connection,
    state: GameState,
    actor: ActorRef,
    delta: int,
    event: str,
    source: str,
) -> tuple[GameState, tuple[str, ...]]:
    if delta not in (-1, 1) or not can_lower_status(game, c, state, actor):
        raise WorkflowError(
            "SOURCE_ACTUAL_STATUS_REQUIRED: use this person's genuine ranked resource"
        )
    changed = GameState.model_validate_json(state.model_dump_json())
    shift_status(changed, int(actor.entity), delta)
    changed.facts.append(
        dict(
            kind="changeling_status",
            actor=actor.model_dump_json(),
            delta=str(delta),
            source=source,
            event=event,
        )
    )
    return changed, ()
