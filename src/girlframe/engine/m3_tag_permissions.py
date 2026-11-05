"""Original-person Tag locks survive only proved, selected same-person retention."""

import json
from typing import Any

from girlframe.engine.m2 import GameState, Obligation, PilotSheet
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_void_state import HarpyState

MARKER = "same_person_conversion"


def signature(gate: Obligation) -> tuple[object, ...]:
    return tuple(getattr(gate, k) for k in ("id", "kind", "owner", "target", "action", "details"))


def original_role(gate: Obligation, *, locker: bool) -> ActorRef:
    owner = gate.owner if locker else gate.target
    character = gate.details.get("owner_character" if locker else "target_character")
    if owner is None or not character or character == "None":
        raise ValueError("Recover the actual original Tag locker and bearer identities")
    return ActorRef(kind="pilot", entity=str(owner), incarnation=character)


def conversion(state: GameState, actor: ActorRef) -> tuple[HarpyState, dict[str, Any]]:
    body = next((x for x in state.harpy_states if x.id == actor.entity and x.alive), None)
    archive = next(
        (x for x in state.career_archives if body is not None and x.id == body.original_archive),
        None,
    )
    if (
        actor.kind != "external_pilot"
        or body is None
        or archive is None
        or archive.ending != "harpy"
        or archive.actor != body.origin
        or archive.source_event != body.source_event
        or body.controller != int(body.origin.entity)
    ):
        raise ValueError("Recover this actual living Harpy's original-person conversion source")
    marker = json.loads(archive.links_json).get(MARKER)
    if (
        not isinstance(marker, dict)
        or marker.get("original") != body.origin.model_dump(mode="json")
        or marker.get("resulting_actor") != actor.model_dump(mode="json")
        or marker.get("source_event") != body.source_event
        or not isinstance(marker.get("retained_tag_ids"), list)
        or not any(
            x.actor == body.origin
            and x.stage == "converted"
            and x.resulting_actor == actor
            and x.response_event == body.source_event
            for x in state.void_thresholds
        )
    ):
        raise ValueError(
            "Recover the actual selected same-person retention record, never a UID alias"
        )
    retained = marker["retained_tag_ids"]
    if not all(isinstance(x, str) and x for x in retained) or len(set(retained)) != len(retained):
        raise ValueError("Recover the exact distinct retained Tag source identities")
    return body, marker


def record_conversion(
    original: GameState,
    origin: ActorRef,
    result: ActorRef,
    archive_id: str,
    retained_tags: tuple[str, ...],
    event: str,
) -> GameState:
    """Called only by actual rebirth, before its first immutable canonical history."""
    state = GameState.model_validate_json(original.model_dump_json())
    body = next((x for x in state.harpy_states if x.id == result.entity), None)
    archive = next((x for x in state.career_archives if x.id == archive_id), None)
    if (
        origin.kind != "pilot"
        or result.kind != "external_pilot"
        or body is None
        or archive is None
        or body.origin != origin
        or body.original_archive != archive_id
        or archive.actor != origin
        or archive.ending != "harpy"
        or body.source_event != event
        or archive.source_event != event
        or set(retained_tags) != {x.id for x in body.tags}
        or len(set(retained_tags)) != len(retained_tags)
    ):
        raise ValueError("Record only the actual original birth and exact selected retained Tags")
    links = json.loads(archive.links_json)
    if MARKER in links:
        raise ValueError("Never replace a prior original-person conversion record")
    old = PilotSheet.model_validate_json(archive.sheet_json)
    if not set(retained_tags) <= {x.id for x in old.tags}:
        raise ValueError("Only actual original Tags can survive this conversion")
    links[MARKER] = dict(
        original=origin.model_dump(mode="json"),
        resulting_actor=result.model_dump(mode="json"),
        source_event=event,
        retained_tag_ids=list(retained_tags),
    )
    updated = archive.model_copy(update={"links_json": json.dumps(links, sort_keys=True)})
    state.career_archives = [updated if x.id == archive_id else x for x in state.career_archives]
    conversion(state, result)
    return state


def _current_pilot(state: GameState, actor: ActorRef) -> bool:
    sheet = state.sheets.get(actor.entity)
    if (
        actor.kind != "pilot"
        or sheet is None
        or sheet.character_id != actor.incarnation
        or int(actor.entity) not in state.order
    ):
        return False
    if any(x.actor == actor for x in state.career_archives):
        return any(
            x.owner == int(actor.entity) and x.character == actor.incarnation and x.active
            for x in state.incarnation_bindings
        )
    return True


def representation(state: GameState, original: ActorRef) -> ActorRef | None:
    found = []
    if _current_pilot(state, original):
        found.append(original)
    for body in state.harpy_states:
        if body.alive and body.origin == original:
            actual = ActorRef(kind="external_pilot", entity=body.id)
            conversion(state, actual)
            found.append(actual)
    if len(found) > 1:
        raise ValueError("An original person's consent cannot acquire duplicate live authorities")
    return found[0] if found else None


def present(state: GameState, actor: ActorRef, tag_id: str) -> bool:
    if actor.kind == "pilot":
        sheet = state.sheets.get(actor.entity)
        return bool(
            _current_pilot(state, actor)
            and sheet is not None
            and any(x.id == tag_id for x in sheet.tags)
        )
    if actor.kind == "external_pilot":
        from girlframe.engine.m3_harpy_defeat import harpy

        body = harpy(state, actor)
        from girlframe.engine.m3_janus_state import JanusCore

        alive = (
            body.alive
            if isinstance(body, (HarpyState, JanusCore))
            else bool(
                state.world and any(x.id == actor.entity and x.alive for x in state.world.pilots)
            )
        )
        return alive and any(x.id == tag_id for x in body.tags)
    if actor.kind == "handler":
        from girlframe.engine.m3_handler_consequences import same_handler_body

        return same_handler_body(state, actor) and any(x.id == tag_id for x in state.handler_tags)
    return False


def locks(state: GameState, actor: ActorRef, tag_id: str) -> tuple[Obligation, ...]:
    if not present(state, actor, tag_id):
        raise ValueError("Choose an actual current Tag of this original person")
    candidates = [
        x
        for x in state.obligations
        if x.kind == "tag_rejection_permission" and x.details.get("tag") == tag_id
    ]
    if not candidates:
        return ()
    original = actor
    if actor.kind == "external_pilot" and any(x.id == actor.entity for x in state.harpy_states):
        body, marker = conversion(state, actor)
        if tag_id not in marker["retained_tag_ids"]:
            raise ValueError("A discarded/copied Tag cannot impersonate the original retained lock")
        original = body.origin
    return tuple(x for x in candidates if original_role(x, locker=False) == original)


def participants(state: GameState, gate: Obligation) -> tuple[ActorRef | None, ActorRef | None]:
    locker = representation(state, original_role(gate, locker=True))
    bearer = representation(state, original_role(gate, locker=False))
    if locker is not None and locker.kind == "external_pilot":
        body, _ = conversion(state, locker)
        archive = next(x for x in state.career_archives if x.id == body.original_archive)
        owned = json.loads(archive.links_json).get("owned_obligations", [])
        if not any(
            signature(Obligation.model_validate_json(json.dumps(x))) == signature(gate)
            for x in owned
        ):
            raise ValueError("This original Harpy never owned the recorded locker authority")
    if bearer is not None:
        if not present(state, bearer, gate.details["tag"]):
            bearer = None
        elif gate.id not in {x.id for x in locks(state, bearer, gate.details["tag"])}:
            bearer = None
    return locker, bearer


def can_reject(state: GameState, actor: ActorRef, tag_id: str) -> bool:
    return all(x.state == "fulfilled" for x in locks(state, actor, tag_id))
