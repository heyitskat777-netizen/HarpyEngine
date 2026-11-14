"""Native Brutalize retains its original people through mandatory Ankou Feedback."""

import hashlib
import json
from typing import TYPE_CHECKING, Any

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_alpha as alpha
from girlframe.engine.m2 import GameState, PlayInput
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef, SceneCast
from girlframe.engine.m3_actors import fingerprint, resolve
from girlframe.engine.m3_girl_runtime_state import has_rule
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_dose_up import _cast
from girlframe.services.onboarding import WorkflowError

if TYPE_CHECKING:
    from girlframe.services.m2_game import GameService


def source_binding(
    game: "GameService",
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    *,
    original_cast: SceneCast | None = None,
) -> str:
    """Bind native Alpha, including one proved original native counter source."""
    prepared = PlayInput.model_validate_json(json.dumps(action["data"]["prepared"]))
    meta = action["data"].get("alpha")
    counter = None
    if action["data"].get("alpha_counter_source"):
        from girlframe.services.m3_ankou_alpha_counter import source_binding as counter_binding

        counter = counter_binding(game, c, state, action)
    if (
        meta is None
        or action["data"].get("play") != "brutalize"
        or prepared.play != "brutalize"
        or prepared.target_actor is None
        or prepared.target is not None
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
            "SOURCE_ANKOU_ALPHA_PORT_REQUIRED: preserve this specialised Brutalize source"
        )
    actor = ActorRef.model_validate(meta["actor"])
    target = ActorRef.model_validate(meta["target"])
    sheet = state.sheets.get(actor.entity)
    cast = SceneCast.model_validate_json(json.dumps(meta["cast"]))
    # Alpha also supports legacy casts proved by actual bind/join events. They
    # need not have a materialized state.scene_casts row. Historical callers
    # supply the immutable, already-proved Feedback cast instead of today's
    # scene in a potentially reused channel.
    expected_cast = original_cast or _cast(game, c, state, int(action["channel_id"]))
    if (
        actor.kind != "pilot"
        or target.kind not in ("pilot", "npc")
        or actor == target
        or sheet is None
        or sheet.girl != "ALPHA"
        or not has_rule(sheet, alpha.RULE, "ALPHA")
        or actor != current_ref(state, int(action["actor_id"]))
        or target != prepared.target_actor
        or target.kind == "pilot"
        and target != current_ref(state, int(target.entity))
        or cast.channel != int(action["channel_id"])
        or cast.id != action["scene_id"]
        or cast != expected_cast
        or not cast.open
        or cast.facilitator != state.handler
        or cast.adjudicator is not None
        or any(
            action["data"].get("character_ids", {}).get(ref.entity) != ref.incarnation
            for ref in (actor, target)
            if ref.kind == "pilot"
        )
    ):
        raise WorkflowError("Preserve the actual native Alpha, original target and scene")
    bindings = profiles(c, game.store.campaign_id)
    own = resolve(state, actor, bindings, require_current_profile=False)
    other = resolve(state, target, bindings, require_current_profile=False)
    if (
        own.rules != "girl_frame"
        or target.kind == "pilot"
        and (other.rules != "girl_frame" or other.inside_frame is None)
        or any(
            not any(role.actor == ref and role.controller == owner for role in cast.roles)
            for ref, owner in ((actor, own.controller), (target, other.controller))
        )
    ):
        raise WorkflowError("Preserve the actual original Brutalize bodies and controllers")
    assessment = None
    if target.kind == "npc":
        from girlframe.engine import m3_npc_guard as guard
        from girlframe.services.m3_npc_guard import prove_assessment

        body = (
            next(
                (person for person in state.world.npcs if person.id == target.entity),
                None,
            )
            if state.world is not None
            else None
        )
        if (
            body is None
            or body.source_kind is not None
            or other.rules != "npc"
            or not guard.supported(state, target, actor, cast)
            or not meta.get("npc_assessment")
        ):
            raise WorkflowError(
                "SOURCE_ANKOU_ALPHA_NPC_PORT_REQUIRED: retain the actual ordinary Guard source"
            )
        assessment = prove_assessment(c, game, state, target, meta["npc_assessment"])
        if assessment.scene != cast.id or assessment.controller != other.controller:
            raise WorkflowError("Preserve the original Guard controller and actual scene review")
    declaration = dict(
        actor=actor.model_dump(mode="json"),
        target=target.model_dump(mode="json"),
        actor_controller=own.controller,
        target_controller=other.controller,
        cast=cast.model_dump(mode="json"),
        cast_sha256=fingerprint(cast),
        table=sorted(
            {role.controller for role in cast.roles}
            | ({cast.facilitator} if cast.facilitator is not None else set())
        ),
        registry=meta["registry"],
        npc_assessment=assessment.id if assessment is not None else None,
    )
    if any(meta.get(key) != expected for key, expected in declaration.items()):
        raise WorkflowError("Preserve the actual original Brutalize bodies and controllers")
    # Historical proof uses the original state and controllers. Live native
    # pre-roll still checks current availability after this pending-source guard.
    return hashlib.sha256(
        json.dumps(
            dict(
                action=action["id"],
                prepared=prepared.model_dump(mode="json"),
                declaration=declaration,
                actor_position=own.position_sha256,
                actor_vessel=own.vessel_id,
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
        value.alpha_source != source_binding(game, c, state, action)
        or action["data"]["alpha"]["phase"] != "unrolled"
        or action["data"].get("receipt") is not None
        or value.cast != _cast(game, c, state, int(action["channel_id"]))
    ):
        raise WorkflowError("Recover the same original unrolled Brutalize and its actual people")


def completed_npc_death(
    game: "GameService", c: Connection, state: GameState, action: dict[str, Any]
) -> bool:
    """Permit historical replay only for an actual completed, Feedback-bound NPC death."""
    from girlframe.services.m3_ankou_feedback import prove
    from girlframe.services.m3_handler_advancements import _history

    meta = action["data"].get("alpha", {})
    identity = action["data"].get("ankou_feedback")
    if (
        action["state"] != "complete"
        or meta.get("phase") != "complete"
        or meta.get("target", {}).get("kind") != "npc"
        or not identity
        or not action["data"].get("receipt")
    ):
        return False
    # The caller cannot substitute a completed-looking projection for the real
    # action. Pending actions still use their unchanged live cast checks.
    if action != game.action(c, action["id"]):
        raise WorkflowError("Recover the actual saved completed Brutalize")
    value = prove(game, c, state, identity)
    if (
        value.alpha_source is None
        or value.phase != "resolved"
        or not value.rolled_event
        or value.receipt != action["data"]["receipt"]["id"]
        or game.pending(c, action["id"])
    ):
        raise WorkflowError("Recover the completed native Feedback and original receipt")
    event = meta.get("effect_event")
    audit = (
        c.execute(
            sa.select(t.events).where(
                t.events.c.campaign_id == game.store.campaign_id,
                t.events.c.id == event,
            )
        )
        .mappings()
        .first()
    )
    if audit is None or audit["kind"] != "m3.choice_resolved":
        return False
    payload = json.loads(audit["payload_json"])
    choices = t.m2["m2_choices"]
    row = (
        c.execute(
            sa.select(choices).where(
                choices.c.campaign_id == game.store.campaign_id,
                choices.c.action_id == action["id"],
                choices.c.id == payload.get("choice_id"),
                choices.c.state == "answered",
                choices.c.kind.in_(("alpha_npc_damage", "alpha_npc_mercy")),
                choices.c.actor_id == str(meta["actor_controller"]),
            )
        )
        .mappings()
        .first()
    )
    if (
        payload.get("action_id") != action["id"]
        or audit["actor_id"] != str(meta["actor_controller"])
        or row is None
    ):
        raise WorkflowError("Preserve the actual Alpha-owned NPC outcome event")
    original = _history(c, game, str(event))
    target = ActorRef.model_validate(meta["target"])
    outcome = next(
        (
            fact
            for fact in original.facts
            if fact.get("kind") == "alpha_npc_outcome"
            and fact.get("event") == event
            and fact.get("action") == action["id"]
            and fact.get("target") == target.model_dump_json()
        ),
        None,
    )
    if outcome is None or outcome.get("killed") != "True":
        return False
    body = (
        next((person for person in original.world.npcs if person.id == target.entity), None)
        if original.world is not None
        else None
    )
    if (
        body is None
        or body.alive
        or any(role.actor == target for cast in original.scene_casts for role in cast.roles)
    ):
        raise WorkflowError("Preserve the genuine NPC death and removal from the original cast")
    return True
