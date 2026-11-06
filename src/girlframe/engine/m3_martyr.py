"""Actual original death relief and its human-authored memorial, never a living successor."""

from typing import Literal
from uuid import NAMESPACE_URL, uuid5

from pydantic import Field

from girlframe.engine.m2 import GameState, PilotSheet
from girlframe.engine.m3_actor_state import ActorRef, Model
from girlframe.engine.m3_career_state import CareerArchive
from girlframe.engine.m3_requisition_state import FrameRuleReceipt
from girlframe.engine.m3_strain import copy as strain_copy

RULE = "frame.class.autocrat.martyr"
KIND = "martyr_memorial"
MEMORIALS = (
    ("hero", "Remembered as a righteous Foundation hero and perfect pilot"),
    ("obscurity", "Not remembered; consigned to quiet obscurity"),
)


class Martyr(Model):
    id: str
    actor: ActorRef
    frame: str
    purchase: str
    archive: str
    source_event: str
    phase: Literal["pending", "complete"] = "pending"
    memorial: Literal["hero", "obscurity"] | None = None
    response_event: str | None = None
    response_account: str | None = Field(default=None, max_length=1200)


def episodes(state: GameState) -> tuple[Martyr, ...]:
    values = tuple(
        Martyr.model_validate_json(x["body"])
        for x in state.facts
        if x.get("kind") == "martyr_episode"
    )
    if len({x.id for x in values}) != len(values):
        raise ValueError("Recover unique actual Martyr source episodes")
    return values


def save(state: GameState, value: Martyr) -> None:
    entry = dict(kind="martyr_episode", id=value.id, body=value.model_dump_json())
    state.facts = [
        x
        for x in state.facts
        if not (x.get("kind") == "martyr_episode" and x.get("id") == value.id)
    ] + [entry]


def held(state: GameState, actor: ActorRef) -> FrameRuleReceipt | None:
    from girlframe.engine.m3_class_grafts import held as acquired

    return acquired(state, actor, RULE)


def _death_frame(state: GameState, archive: CareerArchive, purchase: FrameRuleReceipt) -> str:
    from girlframe.engine.m3_class_grafts import sheet_eligible
    from girlframe.engine.m3_class_retention import binding

    original = PilotSheet.model_validate_json(archive.sheet_json)
    frame = (
        original.frame_runtime.id
        if original.frame_runtime
        else "initial:" + str(archive.actor.incarnation)
    )
    assigned, chain = binding(state, purchase)
    if (
        archive.actor != purchase.actor
        or str(original.owner) != archive.actor.entity
        or original.character_id != archive.actor.incarnation
        or frame != assigned
        or len(chain) == 1
        and not sheet_eligible(original, purchase)
    ):
        raise ValueError("Recover the original dead Girl's actual paid Frame source")
    return frame


def trigger(state: GameState, archive: CareerArchive, purchase: FrameRuleReceipt) -> Martyr:
    if (
        archive not in state.career_archives
        or archive.ending not in ("death", "execution")
        or purchase.actor != archive.actor
        or purchase.rule_id != RULE
        or state.strain is None
    ):
        raise ValueError("Martyr needs its actual paid original death and existing Strain")
    frame = _death_frame(state, archive, purchase)
    identity = str(uuid5(NAMESPACE_URL, "girlframe:martyr:" + archive.id + ":" + purchase.id))
    existing = next((x for x in episodes(state) if x.id == identity), None)
    if existing:
        return existing
    state.strain = strain_copy(
        state.strain, levels=state.strain.levels | {"budget": "low", "rebellion": "low"}
    )
    value = Martyr(
        id=identity,
        actor=archive.actor,
        frame=frame,
        purchase=purchase.id,
        archive=archive.id,
        source_event=archive.source_event,
    )
    save(state, value)
    return value


def memorial_survives_ending(state: GameState, work_id: str, archive: CareerArchive) -> bool:
    return any(
        x.id == work_id
        and x.archive == archive.id
        and x.actor == archive.actor
        and x.source_event == archive.source_event
        for x in episodes(state)
    )


def budget_death_excluded(state: GameState, source_event: str) -> bool:
    for value in episodes(state):
        if value.source_event != source_event:
            continue
        archive = next((x for x in state.career_archives if x.id == value.archive), None)
        receipt = next(
            (
                x
                for x in state.requisitions
                if isinstance(x, FrameRuleReceipt) and x.id == value.purchase
            ),
            None,
        )
        if (
            archive is None
            or archive.actor != value.actor
            or archive.source_event != source_event
            or archive.ending not in ("death", "execution")
            or receipt is None
            or receipt.actor != value.actor
            or receipt.rule_id != RULE
        ):
            continue
        try:
            if _death_frame(state, archive, receipt) == value.frame:
                return True
        except (ValueError, KeyError):
            continue
    return False
