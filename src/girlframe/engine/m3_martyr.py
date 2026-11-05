"""Actual original death relief and its human-authored memorial, never a living successor."""

from typing import Literal
from uuid import NAMESPACE_URL, uuid5

from pydantic import Field

from girlframe.engine.frame_classes import frame_class
from girlframe.engine.m2 import GameState, PilotSheet
from girlframe.engine.m3_actor_state import ActorRef, Model
from girlframe.engine.m3_career_state import CareerArchive
from girlframe.engine.m3_privileges import suspended
from girlframe.engine.m3_requisition_state import FrameRuleReceipt
from girlframe.engine.m3_strain import copy as strain_copy
from girlframe.engine.m3_untouchable import native

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
    try:
        sheet, frame = native(state, actor)
    except (ValueError, KeyError):
        return None
    return next(
        (
            x
            for x in state.requisitions
            if isinstance(x, FrameRuleReceipt)
            and x.actor == actor
            and x.rule_id == RULE
            and x.frame_instance == frame
            and x.frame == sheet.frame
            and x.donor_frame == sheet.frame
            and x.kind == "ability_unlock"
            and not suspended(state, x.id)
        ),
        None,
    )


def trigger(state: GameState, archive: CareerArchive, purchase: FrameRuleReceipt) -> Martyr:
    if (
        archive not in state.career_archives
        or archive.ending not in ("death", "execution")
        or purchase.actor != archive.actor
        or purchase.rule_id != RULE
        or state.strain is None
    ):
        raise ValueError("Martyr needs its actual paid original death and existing Strain")
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
        frame=purchase.frame_instance,
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
            or receipt.kind != "ability_unlock"
            or receipt.frame_instance != value.frame
        ):
            continue
        original = PilotSheet.model_validate_json(archive.sheet_json)
        frame = (
            original.frame_runtime.id
            if original.frame_runtime
            else "initial:" + str(value.actor.incarnation)
        )
        if (
            frame == value.frame
            and receipt.frame == original.frame
            and receipt.donor_frame == original.frame
            and frame_class(original.frame) == "autocrat"
        ):
            return True
    return False
