"""Ordinary native Oldgen advice retains its actual source through Ankou Feedback."""

import hashlib
import json
from typing import TYPE_CHECKING, Any

from sqlalchemy import Connection

from girlframe.engine import m3_oldgen as advice
from girlframe.engine.m2 import GameState, PlayInput
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef, SceneCast
from girlframe.engine.m3_actors import fingerprint
from girlframe.engine.m3_girl_runtime_state import has_rule
from girlframe.services.m3_dose_up import _cast, _native
from girlframe.services.onboarding import WorkflowError

if TYPE_CHECKING:
    from girlframe.services.m2_game import GameService


def source_binding(
    game: "GameService", c: Connection, state: GameState, action: dict[str, Any]
) -> str:
    """Bind native advice, including its original proved low-Brutalize counter."""
    prepared = PlayInput.model_validate_json(json.dumps(action["data"]["prepared"]))
    meta = action["data"].get("oldgen")
    counter = None
    if action["data"].get("alpha_counter_source"):
        from girlframe.services.m3_ankou_alpha_counter import source_binding as counter_binding

        counter = counter_binding(game, c, state, action)
    if (
        meta is None
        or action["data"].get("play") != advice.PLAY
        or prepared.play != advice.PLAY
        or prepared.target is None
        or prepared.target_actor is not None
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
            "SOURCE_ANKOU_ADVICE_PORT_REQUIRED: preserve this specialised advice source"
        )
    actor = ActorRef.model_validate(meta["actor"])
    target = ActorRef.model_validate(meta["target"])
    sheet = state.sheets.get(actor.entity)
    cast = SceneCast.model_validate_json(json.dumps(meta["cast"]))
    if (
        actor.kind != "pilot"
        or target.kind != "pilot"
        or actor == target
        or sheet is None
        or sheet.girl != "OLDGEN"
        or not has_rule(sheet, advice.ADVICE, "OLDGEN")
        or actor != current_ref(state, int(action["actor_id"]))
        or target != current_ref(state, prepared.target)
        or cast.channel != int(action["channel_id"])
        or cast.id != action["scene_id"]
        or fingerprint(cast) != meta["cast_sha256"]
        or any(
            action["data"].get("character_ids", {}).get(ref.entity) != ref.incarnation
            for ref in (actor, target)
        )
    ):
        raise WorkflowError("Preserve the actual native adviser, recipient and original scene")
    first, other = _native(game, c, state, actor), _native(game, c, state, target)
    if (
        meta["caster"] != first.controller
        or meta["counterpart"] != other.controller
        or any(
            not any(role.actor == ref and role.controller == owner for role in cast.roles)
            for ref, owner in ((actor, first.controller), (target, other.controller))
        )
    ):
        raise WorkflowError("Preserve both original advice controllers and actual scene roles")
    return hashlib.sha256(
        json.dumps(
            dict(
                action=action["id"],
                prepared=prepared.model_dump(mode="json"),
                declaration={
                    key: meta[key]
                    for key in (
                        "actor",
                        "target",
                        "caster",
                        "counterpart",
                        "handler_controller",
                        "handler",
                        "cast",
                        "cast_sha256",
                        "table",
                        "registry",
                    )
                },
                actor_position=first.position_sha256,
                actor_vessel=first.vessel_id,
                target_position=other.position_sha256,
                target_vessel=other.vessel_id,
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
        value.advice_source != source_binding(game, c, state, action)
        or action["data"]["oldgen"]["phase"] != "unrolled"
        or action["data"].get("receipt") is not None
        or value.cast != _cast(game, c, state, int(action["channel_id"]))
    ):
        raise WorkflowError("Recover the same original unrolled advice and its actual people")
