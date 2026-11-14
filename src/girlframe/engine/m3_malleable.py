"""Birth-bound Malleable eligibility and actual ordinary Identity/NPC effects."""

from typing import Literal

from girlframe.engine.m2 import GameState, IdentityState, TagState
from girlframe.engine.m3_actor_state import ActorRef, Model, SceneCast
from girlframe.engine.m3_mockingbird import actor_tags

RULE = "girl.stim-blissed.malleable-me-malleable-you"


class Alteration(Model):
    id: str
    subject: ActorRef
    controller: int
    cast: SceneCast
    vessel: str | None
    event: str
    account: str


class AlterationEnd(Model):
    id: str
    alteration: str
    controller: int
    event: str
    account: str


class Birth(Model):
    id: str
    giver: ActorRef
    recipient: ActorRef
    giver_controller: int
    recipient_controller: int
    event: str
    altered_kind: Literal["dose", "stim", "npc", "pilot"]
    altered_id: str
    tag: str


class Forced(Model):
    id: str
    birth: str
    replaced: str
    identity: str
    event: str


class IntoxicationTag(Model):
    id: str
    subject: ActorRef
    controller: int
    event: str
    source_event: str
    action: str
    tag: str
    account: str


class Deprogramming(Model):
    id: str
    subject: ActorRef
    tags: tuple[str, ...]
    event: str
    blocked: bool


KINDS: dict[type[Model], str] = {
    IntoxicationTag: "malleable_intoxication_tag",
    Alteration: "malleable_alteration",
    AlterationEnd: "malleable_alteration_end",
    Birth: "malleable_birth",
    Forced: "malleable_forced",
    Deprogramming: "malleable_deprogramming",
}


def records[T: Model](state: GameState, model: type[T]) -> tuple[T, ...]:
    return tuple(
        model.model_validate_json(x["body"]) for x in state.facts if x.get("kind") == KINDS[model]
    )


def put(state: GameState, value: Model) -> None:
    identity = value.model_dump()["id"]
    kind = KINDS[type(value)]
    if any(x.get("kind") == kind and x.get("id") == identity for x in state.facts):
        raise ValueError("Preserve the immutable original Malleable source")
    state.facts.append(dict(kind=kind, id=identity, body=value.model_dump_json()))


def legal_replacements(
    state: GameState, birth: Birth, *, duplicates: bool
) -> tuple[IdentityState, ...]:
    if birth.recipient.kind != "pilot":
        return ()
    if birth.id.startswith(("dose-up:", "stim-sex-drug:", "bomb-collar:", "cute-uniform:")):
        return ()
    from girlframe.engine.m3_control_ritual import tags as control_tags
    from girlframe.engine.m3_cute_uniforms import tags as uniform_tags

    if any(
        x.id == birth.id
        for x in control_tags(state, int(birth.recipient.entity))
        + uniform_tags(state, int(birth.recipient.entity))
    ):
        return ()
    sheet = state.sheets.get(birth.recipient.entity)
    if sheet is None or sheet.character_id != birth.recipient.incarnation:
        return ()
    if len([x for x in sheet.identities if not x.protected or x.paired or x.am_limiter]) > 4:
        return ()
    tag = next((x for x in sheet.tags if x.id == birth.id), None)
    original = TagState.model_validate_json(birth.tag)
    if tag is not None and any(
        getattr(tag, key) != getattr(original, key)
        for key in (
            "id",
            "label",
            "giver",
            "giver_actor",
            "giver_character",
            "observers",
            "gm_setter_appointment",
            "gm_setter_event",
        )
    ):
        return ()
    if tag is None or (
        not duplicates and any(x.name.casefold() == tag.label.casefold() for x in sheet.identities)
    ):
        return ()
    return tuple(
        x
        for x in sheet.identities
        if not x.protected and not x.paired and not x.obsession_sources and x.am_limiter is None
    )


def force(
    original: GameState, birth: Birth, replaced: str, identity: str, event: str, *, duplicates: bool
) -> GameState:
    if birth not in records(original, Birth) or any(
        x.birth == birth.id for x in records(original, Forced)
    ):
        raise ValueError("Use the unconsumed original birth-qualified Tag")
    selected = next(
        (x for x in legal_replacements(original, birth, duplicates=duplicates) if x.id == replaced),
        None,
    )
    if selected is None or not identity or not event:
        raise ValueError("Choose an actual legal ordinary Identity replacement")
    state = GameState.model_validate_json(original.model_dump_json())
    sheet = state.sheets[birth.recipient.entity]
    tag = next(x for x in sheet.tags if x.id == birth.id)
    locked = selected.id in sheet.sedation_locked
    replacement = IdentityState(id=identity, name=tag.label, marked=locked, slot=selected.slot)
    sheet.identities = [replacement if x.id == selected.id else x for x in sheet.identities]
    sheet.tags = [x for x in sheet.tags if x.id != birth.id]
    sheet.sedation_locked = tuple(
        identity if x == selected.id else x for x in sheet.sedation_locked
    )
    sheet.revision += 1
    put(state, Forced(id=event, birth=birth.id, replaced=replaced, identity=identity, event=event))
    return state


def protected_npc(state: GameState, subject: ActorRef) -> bool:
    # Delegated reading: the original NPC is immune, rather than only the given Tag.
    return subject.kind == "npc" and any(x.recipient == subject for x in records(state, Birth))


def deprogram(
    original: GameState, subject: ActorRef, tags: tuple[str, ...], event: str
) -> tuple[GameState, bool]:
    if subject.kind != "npc" or not tags or len(set(tags)) != len(tags) or not event:
        raise ValueError("Select actual NPC work-affecting Tags for this procedure")
    if not set(tags) <= {x.id for x in actor_tags(original, subject)}:
        raise ValueError("Recover the selected actual NPC Tags")
    state = GameState.model_validate_json(original.model_dump_json())
    blocked = protected_npc(state, subject)
    if not blocked:
        assert state.world is not None
        state.world = state.world.model_copy(
            update={
                "npcs": tuple(
                    x.model_copy(update={"tags": tuple(t for t in x.tags if t.id not in tags)})
                    if x.id == subject.entity
                    else x
                    for x in state.world.npcs
                )
            }
        )
    put(state, Deprogramming(id=event, subject=subject, tags=tags, event=event, blocked=blocked))
    return state, blocked
