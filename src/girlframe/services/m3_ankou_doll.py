"""Native Unassuming Doll retains its actual observer across mandatory Ankou Feedback."""

import hashlib
import json
from typing import TYPE_CHECKING, Any

from sqlalchemy import Connection

from girlframe.engine import m3_vatgrown as doll
from girlframe.engine.m2 import GameState, PlayInput
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef, SceneCast
from girlframe.engine.m3_actors import fingerprint, resolve
from girlframe.engine.m3_girl_runtime_state import has_rule
from girlframe.engine.m3_handler_consequences import active_handler
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_dose_up import _cast
from girlframe.services.onboarding import WorkflowError

if TYPE_CHECKING:
    from girlframe.services.m2_game import GameService


def source_binding(
    game: "GameService", c: Connection, state: GameState, action: dict[str, Any]
) -> str:
    """Bind native Doll, including her original proved low-Brutalize counter."""
    from girlframe.services.m3_vatgrown import _npc_observer

    prepared = PlayInput.model_validate_json(json.dumps(action["data"]["prepared"]))
    meta = action["data"].get("vatgrown")
    counter = None
    if action["data"].get("alpha_counter_source"):
        from girlframe.services.m3_ankou_alpha_counter import source_binding as counter_binding

        counter = counter_binding(game, c, state, action)
    if (
        meta is None
        or action["data"].get("play") != doll.PLAY
        or prepared.play != doll.PLAY
        or prepared.parent is not None
        and counter is None
        or action.get("parent_id") is not None
        and counter is None
        or prepared.source_work is not None
        or prepared.order_id is not None
        or prepared.off_duty_id is not None
        or meta.get("princess_direction")
        or any(
            action["data"].get(key)
            for key in (
                "learned_play",
                "princess_child",
                "actor_basic",
                "ankou_effect_child",
                "easy_target_child",
                "alpha_sex_counter_source",
            )
        )
    ):
        raise WorkflowError(
            "SOURCE_ANKOU_DOLL_PORT_REQUIRED: preserve this specialised Doll source"
        )
    actor = ActorRef.model_validate(meta["actor"])
    target = ActorRef.model_validate(meta["target"])
    sheet = state.sheets.get(actor.entity)
    cast = SceneCast.model_validate_json(json.dumps(meta["cast"]))
    selected = prepared.target_actor
    if selected is None and prepared.target is not None:
        selected = current_ref(state, prepared.target)
    if (
        actor.kind != "pilot"
        or sheet is None
        or sheet.girl != "VATGROWN"
        or actor != current_ref(state, int(action["actor_id"]))
        or selected != target
        or prepared.target is not None
        and prepared.target_actor is not None
        or cast.channel != int(action["channel_id"])
        or cast.id != action["scene_id"]
        or action["data"].get("character_ids", {}).get(actor.entity) != actor.incarnation
        or target.kind == "pilot"
        and action["data"].get("character_ids", {}).get(target.entity) != target.incarnation
    ):
        raise WorkflowError("Preserve the original native Doll, selected observer and actual scene")
    bindings = profiles(c, game.store.campaign_id)
    own = resolve(state, actor, bindings, require_current_profile=False)
    other = resolve(state, target, bindings, require_current_profile=False)
    _npc_observer(state, actor, target)
    handler = active_handler(state)
    # Prove the original snapshot, not today's scene occupying the same channel.
    # Resume separately validates the live scene and runs native Doll pre-roll.
    if (
        target.kind not in ("pilot", "handler", "npc")
        or target == actor
        or not has_rule(sheet, doll.RULE, "VATGROWN")
        or own.rules != "girl_frame"
        or own.offstage_source is not None
        or own.custody not in (None, "free")
        or sheet.medical_state != "fit"
        or own.inside_frame is not False
        or own.cell is None
        or own.cell != other.cell
        or own.vessel_id is None
        or other.offstage_source
        or other.custody not in (None, "free")
        or target.kind == "handler"
        and target != handler
        or target.kind == "pilot"
        and other.rules != "girl_frame"
        or handler is None
        or cast not in state.scene_casts
        or not cast.open
        or cast.facilitator is None
        or cast.facilitator != state.handler
        or cast.adjudicator is not None
        or not all(
            any(role.actor == ref and role.controller == owner for role in cast.roles)
            for ref, owner in ((actor, own.controller), (target, other.controller))
        )
    ):
        raise WorkflowError("Preserve the actual original Doll body and observer controllers")
    declaration = dict(
        actor=actor.model_dump(mode="json"),
        caster=own.controller,
        target=target.model_dump(mode="json"),
        counterpart=other.controller,
        vessel=own.vessel_id,
        actor_position=own.position_sha256,
        target_position=other.position_sha256,
        cast=cast.model_dump(mode="json"),
        cast_sha256=fingerprint(cast),
        table=sorted({role.controller for role in cast.roles} | {cast.facilitator}),
        handler=handler.model_dump(mode="json"),
        handler_controller=cast.facilitator,
    )
    if any(meta.get(key) != expected for key, expected in declaration.items()):
        raise WorkflowError("Preserve the actual original Doll body and observer controllers")
    return hashlib.sha256(
        json.dumps(
            dict(
                action=action["id"],
                prepared=prepared.model_dump(mode="json"),
                declaration=declaration,
                **({"counter": counter} if counter is not None else {}),
            ),
            sort_keys=True,
        ).encode()
    ).hexdigest()


def validate_pending(
    game: "GameService", c: Connection, state: GameState, action: dict[str, Any]
) -> None:
    from girlframe.engine import m3_ankou_feedback as feedback

    value = feedback.get(state, action["data"]["ankou_feedback"])
    if (
        value.doll_source != source_binding(game, c, state, action)
        or action["data"]["vatgrown"]["phase"] != "unrolled"
        or action["data"].get("receipt") is not None
        or value.cast != _cast(game, c, state, int(action["channel_id"]))
    ):
        raise WorkflowError("Recover the same original unrolled Doll and its actual observer")
