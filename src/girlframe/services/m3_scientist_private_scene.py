"""An original Scientist's private laboratory exchange and ordinary Void gain."""

import json
from typing import TYPE_CHECKING, Any

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine.m2 import AssetState, GameState
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_core import install
from girlframe.engine.m3_handler_private_scene import LabExchange, PrivateScene, records
from girlframe.engine.m3_janus_storage import alter
from girlframe.engine.m3_janus_storage import ids as stored_void
from girlframe.engine.m3_promotional_opportunity import in_responsibility
from girlframe.engine.m3_void import FINAL
from girlframe.services.m3_handler_advancements import _history
from girlframe.services.m3_work import related
from girlframe.services.onboarding import WorkflowError

if TYPE_CHECKING:
    from girlframe.services.m2_game import GameService

GAIN = "gain_void"
THRESHOLD = "scientist_private_void"


def lab_at(state: GameState, cell: tuple[int, int] | None) -> str | None:
    return (
        next(
            (
                x.id
                for x in state.world.locations
                if x.cell == cell
                and x.kind == "base"
                and x.foundation_operational
                and in_responsibility(state, x.cell)
            ),
            None,
        )
        if state.world is not None
        else None
    )


def eligible(state: GameState, girl: ActorRef) -> tuple[tuple[str, str], ...]:
    sheet = state.sheets.get(girl.entity)
    if sheet is None or sheet.character_id != girl.incarnation:
        return ()
    bound = stored_void(state, girl)
    return tuple(
        (x.id, x.name)
        for x in sheet.assets
        if x.family == "girl" and x.void and x.intrinsic is None and x.id not in bound
    )


def excise(
    state: GameState,
    girl: ActorRef,
    picked: str,
    proposal: LabExchange,
    event: str,
) -> str:
    if picked not in dict(eligible(state, girl)) or any(
        x.actor == girl and x.stage not in FINAL for x in state.void_thresholds
    ):
        raise WorkflowError(
            "Choose an actual ordinary Void-touched Girl Asset with no active threshold"
        )
    original = state.sheets[girl.entity]
    remaining = original.model_copy(
        update=dict(assets=[x for x in original.assets if x.id != picked])
    )
    replacement = AssetState(
        id=event + ":scientist-exchange",
        family="girl",
        name=proposal.name.strip(),
        description=proposal.description.strip(),
    )
    result = install(remaining, replacement, state=state)
    state.sheets[girl.entity] = result.sheet
    return replacement.id


def uncorrupted(state: GameState, girl: ActorRef) -> tuple[tuple[str, str], ...]:
    sheet = state.sheets.get(girl.entity)
    if sheet is None or sheet.character_id != girl.incarnation:
        return ()
    bound = stored_void(state, girl)
    return tuple(
        (x.id, x.name)
        for x in sheet.assets
        if x.family in ("frame", "girl") and not x.void and x.id not in bound
    )


def respond(
    state: GameState,
    value: PrivateScene,
    event: str,
    step: str,
    text: str,
    asset: str,
    exchange: LabExchange | None,
    effects: tuple[str, ...],
) -> dict[str, Any]:
    if step == "scientist_plan_exchange":
        if (
            exchange is None
            or not exchange.name.strip()
            or not exchange.description.strip()
            or effects not in ((), (GAIN,))
            or asset
        ):
            raise WorkflowError(
                "Name and describe the replacement and select at most one second experiment"
            )
        return dict(phase="scientist_asset", exchange=exchange, effects=effects)
    if effects or exchange is not None or asset and step != "scientist_gain_void":
        raise WorkflowError("Use only the original prepared experiment")
    if step == "scientist_cause_void":
        return dict(phase="scientist_void", accepted_event=event, effects=(GAIN,))
    if step == "scientist_exchange" and value.exchange is not None:
        replacement = excise(state, value.girl, text, value.exchange, event)
        return dict(
            phase="scientist_void" if GAIN in value.effects else "complete",
            accepted_event=event if GAIN in value.effects else value.accepted_event,
            outcome="scientist_exchanged",
            removed_asset=text,
            installed_asset=replacement,
        )
    if step == "scientist_decline":
        return dict(phase="complete", outcome=value.outcome or "declined")
    if step != "scientist_gain_void" or value.accepted_event is None:
        raise WorkflowError("Recover the actual proposed experiment")
    if (
        asset not in dict(uncorrupted(state, value.girl))
        or not 1 <= len(text.strip()) <= 1200
        or any(x.actor == value.girl and x.stage not in FINAL for x in state.void_thresholds)
    ):
        raise WorkflowError(
            "Describe Void in your own uncorrupted Asset after resolving existing thresholds"
        )
    original = next(x for x in state.sheets[value.girl.entity].assets if x.id == asset)
    changed, followups = alter(
        state, value.girl, asset, text.strip(), value.id, event, piloting=False
    )
    for field in GameState.model_fields:
        setattr(state, field, getattr(changed, field))
    applied = next(x for x in state.sheets[value.girl.entity].assets if x.id == asset).void
    family = original.family
    required = (
        (f"{value.id}:void:{family}",)
        if any(x.kind == f"{family}_void_threshold" for x in followups)
        else ()
    )
    return dict(
        phase="scientist_followup" if required else "complete",
        outcome="scientist_void_gained" if applied else "scientist_void_resisted",
        void_asset=asset if applied else None,
        required_work=required,
    )


def materialize(game: "GameService", c: Connection, value: PrivateScene) -> None:
    for identity in value.required_work:
        related(
            c,
            game.store,
            dict(campaign_id=game.store.campaign_id, scene_id=value.scene),
            identity,
            int(value.girl.entity),
            int(value.girl.entity),
            "void_threshold",
            dict(
                owner=value.girl.model_dump(mode="json"),
                character=value.girl.incarnation,
                source_action=None,
                source_pdf=19,
                reason=THRESHOLD,
                case=value.id,
                details=dict(family=identity.rsplit(":", 1)[-1]),
            ),
            value.event,
        )


def prove_threshold(
    game: "GameService", c: Connection, row: dict[str, Any], body: dict[str, Any], girl: ActorRef
) -> None:
    from girlframe.services.m3_handler_private_scene import SCIENTIST_EVENT

    def audit(event: str) -> tuple[str | None, str | None]:
        proof = (
            c.execute(
                sa.select(t.events.c.kind, t.events.c.actor_id, t.events.c.payload_json).where(
                    t.events.c.campaign_id == game.store.campaign_id, t.events.c.id == event
                )
            )
            .mappings()
            .first()
        )
        if proof is None or proof["kind"] != SCIENTIST_EVENT:
            return None, None
        payload = json.loads(proof["payload_json"])
        if payload.get("case") != body["case"]:
            return None, None
        return proof["actor_id"], payload.get("step")

    resolved = _history(c, game, row["event_id"])
    value = next((x for x in records(resolved) if x.id == body["case"]), None)
    family = body["details"]["family"]
    if (
        value is None
        or value.playbook != "Scientist"
        or value.girl != girl
        or value.scene != row["scene_id"]
        or value.event != row["event_id"]
        or value.phase != "scientist_followup"
        or not value.accepted_event
        or value.outcome != "scientist_void_gained"
        or GAIN not in value.effects
        or row["id"] != f"{value.id}:void:{family}"
        or row["id"] not in value.required_work
        or audit(value.event) != (girl.entity, "scientist_gain_void")
        or audit(value.accepted_event)
        not in ((value.handler.entity, "scientist_cause_void"), (girl.entity, "scientist_exchange"))
        or not any(
            x.id == value.void_asset and x.void and x.family == family
            for x in resolved.sheets[girl.entity].assets
        )
    ):
        raise ValueError("Recover the actual accepted Scientist experiment and its original Asset")
