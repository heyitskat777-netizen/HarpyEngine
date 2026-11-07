"""Tracker hardware, anatomical sources and private knowledge (PDF155/153)."""

from typing import Literal

from pydantic import Field, model_validator

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef, Model, SceneCast

RULE = "handler-advancement.handler-advancement.tracker-implants"
PLAYS = (
    ("tracker_intercept", "Intercept them"),
    ("tracker_voyeur", "Play voyeur to a private moment"),
)


class Site(Model):
    actor: ActorRef
    site: str = Field(min_length=1, max_length=120)
    asset: str | None = Field(default=None, min_length=1, max_length=100)

    @model_validator(mode="after")
    def native_body(self) -> "Site":
        if self.actor.kind != "pilot" or not self.site.strip():
            raise ValueError("Choose an actual original Girl and a real anatomical site")
        return self


class Implant(Site):
    id: str
    vessel: str


class Acquisition(Model):
    id: str
    award: str
    handler: ActorRef
    appointment: str
    event: str
    account: str
    implants: tuple[Implant, ...]


class Removal(Model):
    id: str
    tracker: str
    event: str
    remover: ActorRef
    controller: int
    account: str


class Moment(Model):
    id: str
    actor: ActorRef
    vessel: str
    event: str
    controller: int
    cast: SceneCast
    account: str = Field(min_length=1, max_length=1200)
    cell: tuple[int, int]


class SiteVoid(Model):
    id: str
    actor: ActorRef
    vessel: str
    source_event: str
    asset: str
    site: str
    controller: int
    event: str


class Alert(Model):
    id: str
    acquisition: str
    tracker: str
    reason: Literal["removed", "site_void"]
    event: str
    source_event: str
    attribution: str | None = None
    asset: str | None = None


class PlaySource(Model):
    id: str
    tracker: str
    acquisition: str
    event: str
    play: Literal["tracker_intercept", "tracker_voyeur"]
    cast: SceneCast
    cell: tuple[int, int]
    moment: str | None = None


KINDS: dict[type[Model], str] = {
    Acquisition: "tracker_acquisition",
    Removal: "tracker_removal",
    Moment: "tracker_moment",
    SiteVoid: "tracker_site_void",
    Alert: "tracker_alert",
    PlaySource: "tracker_play_source",
}


def records[T: Model](state: GameState, model: type[T]) -> tuple[T, ...]:
    return tuple(
        model.model_validate_json(x["body"]) for x in state.facts if x.get("kind") == KINDS[model]
    )


def put(state: GameState, value: Model) -> None:
    kind = KINDS[type(value)]
    identity = value.model_dump()["id"]
    if any(x.get("kind") == kind and x.get("id") == identity for x in state.facts):
        raise ValueError("Preserve this actual original tracker source without overwriting it")
    state.facts.append(dict(kind=kind, id=identity, body=value.model_dump_json()))


def acquisitions(state: GameState) -> tuple[Acquisition, ...]:
    return records(state, Acquisition)


def implant(state: GameState, identity: str) -> tuple[Acquisition, Implant]:
    for source in acquisitions(state):
        for item in source.implants:
            if item.id == identity:
                return source, item
    raise ValueError("Recover the actual original implanted tracker")


def attached(state: GameState, identity: str) -> bool:
    implant(state, identity)
    return not any(x.tracker == identity for x in records(state, Removal))


def body_void_changes(
    before: GameState, after: GameState, actor: ActorRef, vessel: str
) -> tuple[str, ...]:
    old = before.sheets.get(actor.entity)
    new = after.sheets.get(actor.entity)
    first = next((x for x in before.placements if x.actor == actor), None)
    last = next((x for x in after.placements if x.actor == actor), None)
    if (
        old is None
        or new is None
        or old.character_id != actor.incarnation
        or new.character_id != actor.incarnation
        or first is None
        or last is None
        or first.vessel_id != vessel
        or last.vessel_id != vessel
    ):
        return ()
    prior = {x.id: x for x in old.assets}
    return tuple(
        x.id
        for x in new.assets
        if x.family == "girl"
        and x.void
        and (x.id not in prior or (prior[x.id].family == "girl" and not prior[x.id].void))
    )


def add_alert(
    state: GameState,
    source: Acquisition,
    item: Implant,
    *,
    reason: Literal["removed", "site_void"],
    event: str,
    source_event: str,
    asset: str | None = None,
    attribution: str | None = None,
) -> None:
    identity = "tracker-alert:" + item.id + ":" + reason + ":" + source_event
    if any(x.id == identity for x in records(state, Alert)):
        return
    put(
        state,
        Alert(
            id=identity,
            acquisition=source.id,
            tracker=item.id,
            reason=reason,
            event=event,
            source_event=source_event,
            asset=asset,
            attribution=attribution,
        ),
    )
