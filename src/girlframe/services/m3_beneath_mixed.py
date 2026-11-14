"""Finite native Beneath/pin with proved ordinary observers, not non-Girl rollers."""

from typing import TYPE_CHECKING, Any

from sqlalchemy import Connection

from girlframe.engine.m2 import GameState, PlayInput
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_actors import resolve
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_dose_up import _cast, _native
from girlframe.services.onboarding import WorkflowError

if TYPE_CHECKING:
    from girlframe.services.m2_game import GameService
    from girlframe.services.read_only_bot import GuildViewer


def snapshot(
    game: "GameService", c: Connection, state: GameState, channel: int
) -> dict[str, Any] | None:
    scene = game.scene(c, channel)
    current = next((x for x in state.scene_casts if x.id == scene["id"] and x.open), None)
    if current is None or not any(role.actor.kind in ("npc", "handler") for role in current.roles):
        return None
    cast = _cast(game, c, state, channel)
    table = set(scene["participants"])
    bound = profiles(c, game.store.campaign_id)
    for role in cast.roles:
        if role.actor.kind == "pilot":
            actual = _native(game, c, state, role.actor)
            if (
                game.character_binding(c, state, role.controller, require_current_profile=False)
                != role.actor.incarnation
            ):
                raise WorkflowError("Preserve the original native observer character")
        elif role.actor.kind == "npc":
            from girlframe.services.m3_npc_flirt import _npc

            _npc(state, role.actor)
            actual = resolve(state, role.actor, bound)
        elif role.actor.kind == "clone_am":
            from girlframe.services.m3_clone_am import prove_copy

            prove_copy(game, c, state, role.actor)
            actual = resolve(state, role.actor, bound)
            if actual.rules != "clone_am" or actual.custody not in (None, "free"):
                raise WorkflowError("Use the actual available Frame-resident Clone AM observer")
        elif role.actor.kind == "handler":
            from girlframe.engine.m3_handler_consequences import active_handler

            actual = resolve(state, role.actor, bound)
            if (
                role.actor != active_handler(state)
                or actual.rules != "handler"
                or actual.custody not in (None, "free")
                or game.director_mode_pending(c, role.controller)
            ):
                raise WorkflowError("Use the actual available ordinary Handler observer")
        else:
            raise WorkflowError(
                "This native social scope admits only native Girls and ordinary observers"
            )
        if not actual.alive or actual.controller != role.controller or role.controller not in table:
            raise WorkflowError("Preserve the actual living cast and existing private controllers")
    return cast.model_dump(mode="json")


def prepare(
    game: "GameService",
    c: Connection,
    viewer: "GuildViewer",
    state: GameState,
    prepared: PlayInput,
    channel: int,
    beneath: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if prepared.play not in ("put_someone_beneath_you", "keep_your_head", "flirt"):
        return None
    # Do not turn unrelated ordinary Plays into mixed-role controls.
    if beneath is None and prepared.parent is None:
        return None
    if prepared.source_work is not None or prepared.order_id is not None:
        return None
    if beneath is None:
        assert prepared.parent is not None
        parent = game.action(c, prepared.parent)
        identity = parent["data"].get("ankou_feedback")
        if not parent["data"].get("beneath"):
            return None
        from girlframe.services.m3_ankou_feedback import prove

        value = prove(game, c, state, identity) if identity else None
        if value is not None and (
            value.beneath_counter_source is not None
            or value.phase != "resolved"
            or value.rolled_event is None
        ):
            return None
        if value is None and not parent["data"].get("beneath_mixed"):
            return None
    cast = snapshot(game, c, state, channel)
    if cast is None:
        return None
    if beneath is not None:
        if (
            prepared.parent is not None
            or prepared.source_work is not None
            or prepared.order_id is not None
            or prepared.piloting
            or beneath["special_girl"] is not None
        ):
            return None
        owners = [ActorRef.model_validate(beneath[key]) for key in ("actor", "target")]
        for owner in owners:
            actual = _native(game, c, state, owner)
            if not any(
                role["actor"] == owner.model_dump(mode="json")
                and role["controller"] == actual.controller
                for role in cast["roles"]
            ):
                raise WorkflowError("Join as the actual original native Beneath participant")
        return dict(cast=cast, parent=None)
    from girlframe.services.m3_ankou_pin import validate_resumed_beneath_response

    validate_resumed_beneath_response(
        game, c, viewer, state, prepared, channel, value, native_parent=parent["id"]
    )
    return dict(cast=cast, parent=parent["id"])


def pre_roll(game: "GameService", c: Connection, state: GameState, action: dict[str, Any]) -> None:
    scope = action["data"].get("beneath_mixed")
    if scope is not None and snapshot(game, c, state, int(action["channel_id"])) != scope["cast"]:
        raise WorkflowError("Preserve the original native Beneath/pin cast before rolling")
