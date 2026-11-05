"""Native LEGION capacity and actual repair replacements from its original paid source."""

from typing import TYPE_CHECKING

from pydantic import Field

from girlframe.engine.m3_actor_state import ActorRef, Model

if TYPE_CHECKING:
    from girlframe.engine.m2 import GameState, PilotSheet
    from girlframe.engine.m3_requisition_state import FrameRuleReceipt

RULE = "frame.class.legion.modular-build"


class Replacement(Model):
    asset: str = Field(min_length=1)
    name: str = Field(min_length=1, max_length=80)
    description: str = Field(min_length=1, max_length=700)


def native(state: "GameState", actor: ActorRef) -> tuple["PilotSheet", str]:
    from girlframe.engine.frame_classes import frame_class
    from girlframe.engine.m3_careers import can_pilot

    sheet = state.sheets.get(actor.entity) if actor.kind == "pilot" else None
    if (
        sheet is None
        or sheet.character_id != actor.incarnation
        or sheet.frame_scrapped
        or frame_class(sheet.frame) != "legion"
        or not can_pilot(state, actor)
    ):
        raise ValueError("Use the actual original Pilot's current native LEGION Frame")
    return sheet, sheet.frame_runtime.id if sheet.frame_runtime else "initial:" + str(
        actor.incarnation
    )


def held(state: "GameState", actor: ActorRef) -> "FrameRuleReceipt | None":
    from girlframe.engine.m3_privileges import suspended
    from girlframe.engine.m3_requisition_state import FrameRuleReceipt

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
            and x.frame_instance == frame
            and x.frame == sheet.frame
            and x.donor_frame == sheet.frame
            and x.rule_id == RULE
            and x.kind == "ability_unlock"
            and not suspended(state, x.id)
        ),
        None,
    )


def replaceable(state: "GameState", actor: ActorRef) -> tuple[str, ...]:
    from girlframe.engine.m3_assets import counts_toward_limit
    from girlframe.engine.m3_janus_storage import points

    if held(state, actor) is None:
        return ()
    sheet = state.sheets[actor.entity]
    stored = {x.asset for x in points(state) if x.actor == actor and not x.removed_event}
    return tuple(
        x.id
        for x in sheet.assets
        if x.family == "frame"
        and x.damaged
        and counts_toward_limit(sheet, x)
        and x.id not in stored
        and not x.id.startswith("doctor-loan:")
        and x.intrinsic is None
    )


def replace_repaired(
    state: "GameState",
    actor: ActorRef,
    before: "PilotSheet",
    choices: tuple[Replacement, ...],
    period: str | None,
    *,
    source: str | None = None,
) -> None:
    from uuid import NAMESPACE_URL, uuid5

    from girlframe.engine.m2 import AssetState

    if not choices:
        return
    if period is None and not source:
        raise ValueError("Modular replacement needs its actual repair source")
    receipt = held(state, actor)
    allowed = set(
        replaceable(
            state.model_copy(update={"sheets": state.sheets | {actor.entity: before}}), actor
        )
    )
    sheet = state.sheets[actor.entity]
    if receipt is None or len({x.asset for x in choices}) != len(choices):
        raise ValueError("Use one owned Modular Build substitution for each actual repair")
    for chosen in choices:
        old = next((x for x in sheet.assets if x.id == chosen.asset), None)
        if (
            chosen.asset not in allowed
            or old is None
            or old.damaged
            or not chosen.name.strip()
            or not chosen.description.strip()
        ):
            raise ValueError(
                "Replace only an actually repaired damaged Frame Asset from this source"
            )
        identity = str(
            uuid5(
                NAMESPACE_URL,
                "girlframe:modular:"
                + (source or str(period))
                + ":"
                + actor.token
                + ":"
                + chosen.asset,
            )
        )
        if any(x.id == identity for x in sheet.assets):
            raise ValueError("This actual repair already owns its one replacement")
        sheet.assets = [
            AssetState(
                id=identity,
                family="frame",
                name=chosen.name.strip(),
                description=chosen.description.strip(),
            )
            if x.id == chosen.asset
            else x
            for x in sheet.assets
        ]
        state.facts.append(
            dict(
                kind="modular_repair",
                **({"period": period} if period is not None else {}),
                **({"source": source} if source is not None else {}),
                actor=actor.model_dump_json(),
                purchase=receipt.id,
                old=chosen.asset,
                new=identity,
            )
        )
    sheet.revision += 1
