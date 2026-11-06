"""Genuine AM Identity/memory snapshots; restoring one never rewinds the world."""

from uuid import NAMESPACE_URL, uuid5

from pydantic import Field

from girlframe.engine.m2 import GameState, IdentityState
from girlframe.engine.m3_actor_state import ActorRef, Model
from girlframe.engine.m3_am_memory import Erasure, losses


class Backup(Model):
    id: str
    maintenance: str
    actor: ActorRef
    operator: ActorRef
    action: str
    event: str
    captured_revision: int = Field(ge=0)
    identities: tuple[IdentityState, ...]
    memory_losses: tuple[Erasure, ...] = ()
    memory_baseline: str | None = None


class Retained(Model):
    slot: int | None
    current_id: str
    current: str
    saved: str | None
    reason: str


class Reversion(Model):
    id: str
    backup: str
    actor: ActorRef
    owner: int
    event: str
    through_revision: int = Field(ge=0)
    retained: tuple[Retained, ...] = ()


def backups(state: GameState, actor: ActorRef | None = None) -> tuple[Backup, ...]:
    return tuple(
        value
        for fact in state.facts
        if fact.get("kind") == "am_backup"
        if (value := Backup.model_validate_json(fact["body"]))
        if actor is None or value.actor == actor
    )


def backup(state: GameState, identity: str) -> Backup:
    value = next((x for x in backups(state) if x.id == identity), None)
    if value is None:
        raise ValueError("Recover the actual original AM backup")
    return value


def reversions(state: GameState, actor: ActorRef | None = None) -> tuple[Reversion, ...]:
    return tuple(
        value
        for fact in state.facts
        if fact.get("kind") == "am_backup_reversion"
        if (value := Reversion.model_validate_json(fact["body"]))
        if actor is None or value.actor == actor
    )


def latest(state: GameState, actor: ActorRef) -> Reversion | None:
    return max(reversions(state, actor), key=lambda x: x.through_revision, default=None)


def capture(
    state: GameState,
    maintenance: str,
    actor: ActorRef,
    operator: ActorRef,
    action: str,
    event: str,
) -> str:
    sheet = state.sheets.get(actor.entity)
    if (
        actor.kind != "pilot"
        or sheet is None
        or sheet.character_id != actor.incarnation
        or not event
        or not action
        or any(x.maintenance == maintenance for x in backups(state))
    ):
        raise ValueError("Back up only this actual original AM's rolled moment once")
    baseline = latest(state, actor)
    value = Backup(
        id=str(uuid5(NAMESPACE_URL, "girlframe:am-backup:" + maintenance)),
        maintenance=maintenance,
        actor=actor,
        operator=operator,
        action=action,
        event=event,
        captured_revision=state.revision,
        identities=tuple(x.model_copy(deep=True) for x in sheet.identities),
        memory_losses=losses(state, actor),
        memory_baseline=baseline.id if baseline else None,
    )
    state.facts.append(dict(kind="am_backup", id=value.id, body=value.model_dump_json()))
    return value.id


def plan(state: GameState, value: Backup) -> tuple[tuple[IdentityState, ...], tuple[Retained, ...]]:
    """Restore content by actual slot while keeping current source/mark authority."""
    from girlframe.engine.m3_leviathan_obsession import require_identity_change

    sheet = state.sheets.get(value.actor.entity)
    if (
        value.actor.kind != "pilot"
        or sheet is None
        or sheet.character_id != value.actor.incarnation
        or sheet.girl != "AM"
    ):
        raise ValueError("Only this same actual original current AM can revert her backup")
    saved = {x.slot: x for x in value.identities if x.slot is not None}
    current = {x.slot: x for x in sheet.identities if x.slot is not None}
    if set(saved) != set(current) or any(
        not x.protected and x.slot is None for x in (*sheet.identities, *value.identities)
    ):
        raise ValueError(
            "UNSUPPORTED_RULE: recover changed original ordinary Identity slot authority"
        )
    # Historical source-protected extras cannot be recreated as new source grants.
    if any(
        x.slot is None and not any(y.id == x.id for y in sheet.identities) for x in value.identities
    ):
        raise ValueError("UNSUPPORTED_RULE: recover the historical protected Identity source")
    result: list[IdentityState] = []
    retained: list[Retained] = []
    for item in sheet.identities:
        old = (
            saved.get(item.slot)
            if item.slot is not None
            else next((x for x in value.identities if x.id == item.id), None)
        )
        reason = ""
        if item.am_limiter:
            reason = "Current Limited Identity and its source remain"
        elif item.paired:
            reason = "Current Paired Identity and its source remain"
        elif item.protected:
            reason = "Current protected Identity and its source remain"
        else:
            try:
                require_identity_change(state, value.actor, (item.id,))
            except ValueError:
                reason = "Current source-locked Identity remains"
            if item.obsession_sources:
                reason = "Current source-locked Identity remains"
        if reason:
            result.append(item.model_copy(deep=True))
            if old is None or old.model_dump(exclude={"marked"}) != item.model_dump(
                exclude={"marked"}
            ):
                retained.append(
                    Retained(
                        slot=item.slot,
                        current_id=item.id,
                        current=item.name,
                        saved=old.name if old else None,
                        reason=reason,
                    )
                )
            continue
        assert old is not None
        if old.protected or old.paired or old.am_limiter or old.obsession_sources:
            raise ValueError("UNSUPPORTED_RULE: recover the backed-up protected Identity source")
        result.append(old.model_copy(deep=True, update=dict(marked=item.marked)))
    if len({x.id for x in result}) != len(result):
        raise ValueError("Recover distinct actual original Identity slot sources")
    return tuple(result), tuple(retained)


def restore(original: GameState, identity: str, event: str) -> tuple[GameState, Reversion]:
    state = GameState.model_validate_json(original.model_dump_json())
    value = backup(state, identity)
    identities, retained = plan(state, value)
    if not event:
        raise ValueError("Restore only from an actual owned reversion event")
    sheet = state.sheets[value.actor.entity]
    replacements = {old.id: new.id for old, new in zip(sheet.identities, identities, strict=True)}
    if tuple(sheet.identities) != identities:
        sheet.identities = list(identities)
        sheet.sedation_locked = tuple(replacements.get(x, x) for x in sheet.sedation_locked)
        sheet.revision += 1
    record = Reversion(
        id=str(uuid5(NAMESPACE_URL, "girlframe:am-revert:" + event)),
        backup=value.id,
        actor=value.actor,
        owner=int(value.actor.entity),
        event=event,
        through_revision=state.revision,
        retained=retained,
    )
    state.facts.append(
        dict(kind="am_backup_reversion", id=record.id, body=record.model_dump_json())
    )
    return GameState.model_validate_json(state.model_dump_json()), record


def recall_state(
    state: GameState, actor: ActorRef, learned_revision: int
) -> tuple[bool, tuple[Erasure, ...]]:
    """Evaluate a frozen memory lineage without deleting any OOC memory evidence."""
    baseline = latest(state, actor)
    actual_losses = losses(state, actor)
    later: tuple[Erasure, ...] = ()
    seen: set[str] = set()
    while baseline is not None:
        if baseline.id in seen or baseline.actor != actor:
            raise ValueError("Recover the original acyclic AM memory snapshot lineage")
        seen.add(baseline.id)
        later += tuple(x for x in actual_losses if x.through_revision > baseline.through_revision)
        if learned_revision > baseline.through_revision:
            return True, later
        saved = backup(state, baseline.backup)
        if saved.actor != actor or saved.captured_revision > baseline.through_revision:
            raise ValueError("Recover this original AM's earlier genuine memory snapshot")
        if learned_revision > saved.captured_revision:
            return False, later
        actual_losses = saved.memory_losses
        baseline = next(
            (x for x in reversions(state, actor) if x.id == saved.memory_baseline), None
        )
        if saved.memory_baseline and baseline is None:
            raise ValueError("Recover the original frozen memory baseline")
    return True, actual_losses + later
