"""Native Easy Target retains its actual source across Ankou Feedback."""

import hashlib
import json
from typing import TYPE_CHECKING, Any

from sqlalchemy import Connection

from girlframe.engine import m3_easy_target as easy_target
from girlframe.engine.m2 import GameState, PlayInput
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef, SceneCast
from girlframe.engine.m3_actors import fingerprint, resolve
from girlframe.engine.m3_girl_runtime_state import has_rule
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_dose_up import _cast, _native
from girlframe.services.onboarding import WorkflowError

if TYPE_CHECKING:
    from girlframe.services.m2_game import GameService


def source_binding(
    game: "GameService", c: Connection, state: GameState, action: dict[str, Any]
) -> str:
    """Bind the original native mistake and its proved low-Brutalize opportunity."""
    prepared = PlayInput.model_validate_json(json.dumps(action["data"]["prepared"]))
    meta = action["data"].get("easy_target")
    counter = None
    if action["data"].get("alpha_counter_source"):
        from girlframe.services.m3_ankou_alpha_counter import source_binding as counter_binding

        counter = counter_binding(game, c, state, action)
    if (
        meta is None
        or action["data"].get("play") != easy_target.PLAY
        or prepared.play != easy_target.PLAY
        or prepared.target is not None
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
            "SOURCE_ANKOU_EASY_TARGET_PORT_REQUIRED: preserve this specialised mistake source"
        )
    actor = ActorRef.model_validate(meta["actor"])
    sheet = state.sheets.get(actor.entity)
    cast = SceneCast.model_validate_json(json.dumps(meta["cast"]))
    if (
        actor.kind != "pilot"
        or sheet is None
        or sheet.girl != "NEWGIRL"
        or not has_rule(sheet, easy_target.RULE, "NEWGIRL")
        or actor != current_ref(state, int(action["actor_id"]))
        or action["data"].get("character_ids", {}).get(actor.entity) != actor.incarnation
        or cast.channel != int(action["channel_id"])
        or cast.id != action["scene_id"]
        or fingerprint(cast) != meta["cast_sha256"]
        or not any(role.actor != actor for role in cast.roles)
    ):
        raise WorkflowError("Preserve the original native Newgirl and actual mistake scene")
    own = _native(game, c, state, actor)
    if meta["caster"] != own.controller or not any(
        role.actor == actor and role.controller == own.controller for role in cast.roles
    ):
        raise WorkflowError("Preserve the original Newgirl controller and actual scene role")
    people = []
    for role in cast.roles:
        person = resolve(
            state, role.actor, profiles(c, game.store.campaign_id), require_current_profile=False
        )
        if person.controller != role.controller:
            raise WorkflowError("Preserve every original scene person's actual controller")
        people.append(
            dict(
                actor=role.actor.model_dump(mode="json"),
                controller=role.controller,
                position=person.position_sha256,
                vessel=person.vessel_id,
            )
        )
    return hashlib.sha256(
        json.dumps(
            dict(
                action=action["id"],
                prepared=prepared.model_dump(mode="json"),
                declaration={
                    key: meta[key]
                    for key in (
                        "actor",
                        "caster",
                        "handler_controller",
                        "handler",
                        "cast",
                        "cast_sha256",
                        "table",
                        "registry",
                    )
                },
                people=people,
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
        value.easy_target_source != source_binding(game, c, state, action)
        or action["data"]["easy_target"]["phase"] != "unrolled"
        or action["data"].get("receipt") is not None
        or value.cast != _cast(game, c, state, int(action["channel_id"]))
    ):
        raise WorkflowError("Recover the same original unrolled mistake and its actual people")
