"""Append-only narrative developments; these records never apply gameplay effects."""

from typing import Literal

from pydantic import Field, model_validator

from girlframe.engine.identity import Snowflake
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_world_state import Model


class Subject(Model):
    kind: Literal["location", "npc", "faction"]
    id: str = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def nonblank(self) -> "Subject":
        if not self.id.strip():
            raise ValueError("WORLD_SUBJECT_INVALID: use an actual world subject ID")
        return self


class DevelopmentDraft(Model):
    key: str = Field(min_length=1, max_length=100, pattern=r"^[a-z][a-z0-9_.:-]*$")
    kind: Literal["detail", "goal", "complication"]
    subject: Subject
    title: str = Field(min_length=1, max_length=120)
    text: str = Field(min_length=1, max_length=2400)
    supersedes: str | None = Field(default=None, min_length=1, max_length=100)

    @model_validator(mode="after")
    def narrative_shape(self) -> "DevelopmentDraft":
        if (
            not self.title.strip()
            or not self.text.strip()
            or (self.supersedes is not None and not self.supersedes.strip())
        ):
            raise ValueError("WORLD_DEVELOPMENT_INVALID: provide nonblank narrative fields")
        if self.kind == "goal" and self.subject.kind == "location":
            raise ValueError("WORLD_GOAL_SUBJECT: only an actual NPC or faction may have a goal")
        return self


class Development(DevelopmentDraft):
    id: str = Field(min_length=1, max_length=100)
    source_event: str = Field(min_length=1, max_length=100)
    source_proposal: str = Field(min_length=1, max_length=200)
    version: int = Field(ge=1)
    confirmed_by: Snowflake

    @model_validator(mode="after")
    def native_provenance(self) -> "Development":
        if any(not value.strip() for value in (self.id, self.source_event, self.source_proposal)):
            raise ValueError("WORLD_DEVELOPMENT_SOURCE: retain actual native provenance")
        if (self.version == 1) != (self.supersedes is None) or self.supersedes == self.id:
            raise ValueError("WORLD_DEVELOPMENT_VERSION: preserve the original revision chain")
        return self


def records(state: GameState) -> tuple[Development, ...]:
    """Return validated history without retiring or changing any earlier text."""
    values = tuple(
        Development.model_validate_json(fact["body"])
        for fact in state.facts
        if fact.get("kind") == "world_development"
    )
    seen: dict[str, Development] = {}
    heads: dict[str, Development] = {}
    events: set[str] = set()
    for value in values:
        if value.id in seen or value.source_event in events:
            raise ValueError("WORLD_DEVELOPMENT_HISTORY: native records and events are unique")
        prior = heads.get(value.key)
        if value.supersedes is None:
            if prior is not None:
                raise ValueError("WORLD_DEVELOPMENT_DUPLICATE: retain one active record per key")
        elif (
            prior is None
            or prior.id != value.supersedes
            or prior.kind != value.kind
            or prior.subject != value.subject
            or value.version != prior.version + 1
        ):
            raise ValueError("WORLD_DEVELOPMENT_HISTORY: preserve each exact prior and subject")
        seen[value.id] = value
        events.add(value.source_event)
        heads[value.key] = value
    return values


def current(state: GameState) -> tuple[Development, ...]:
    history = records(state)
    superseded = {value.supersedes for value in history if value.supersedes is not None}
    return tuple(value for value in history if value.id not in superseded)


def validate(state: GameState, draft: DevelopmentDraft, author: int) -> int:
    """Validate finite subjects and version ownership, returning the next version.

    Text expresses setting detail, desired NPC/faction intent or an unresolved
    complication. It has no effect fields or player subjects. Whether that text
    improperly claims a mechanical result remains an explicit GM review concern.
    """
    draft = DevelopmentDraft.model_validate_json(draft.model_dump_json())
    world = state.world
    if world is None:
        raise ValueError("WORLD_REQUIRED: initialize the actual world before adding developments")
    if author != state.handler:
        raise ValueError("WORLD_DEVELOPMENT_NOT_OWNED: retain the actual native world authority")
    if draft.subject.kind == "location":
        found = any(value.id == draft.subject.id for value in world.locations)
    elif draft.subject.kind == "faction":
        found = any(value.id == draft.subject.id and value.active for value in world.factions)
    else:
        npc = next((value for value in world.npcs if value.id == draft.subject.id), None)
        found = npc is not None and npc.alive
        if draft.kind == "goal" and npc is not None and npc.controller != author:
            raise ValueError(
                "WORLD_GOAL_NOT_OWNED: another controller's NPC intent requires its own workflow"
            )
    if not found:
        raise ValueError("WORLD_SUBJECT_UNAVAILABLE: select a current actual world subject")
    prior = next((value for value in current(state) if value.key == draft.key), None)
    if draft.supersedes is None:
        if prior is not None:
            raise ValueError("WORLD_DEVELOPMENT_DUPLICATE: explicitly supersede the active record")
        return 1
    if (
        prior is None
        or prior.id != draft.supersedes
        or prior.kind != draft.kind
        or prior.subject != draft.subject
    ):
        raise ValueError("STALE_WORLD_DEVELOPMENT: retain the exact active key, kind and subject")
    return prior.version + 1
