"""An original Harpy's surviving Tag grants priority for an actual Order."""

from sqlalchemy import Connection

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef, SceneCast
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_harpy_advancements import ECHOES
from girlframe.services.m2_game import GameService
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_harpy_advancements import advancement_source
from girlframe.services.onboarding import WorkflowError


def authority(
    game: GameService,
    c: Connection,
    state: GameState,
    issuer: ActorRef,
    target: ActorRef,
    controller: int,
    *,
    condition: str | None = None,
) -> str:
    bound = profiles(c, game.store.campaign_id)
    subject = state.sheets.get(target.entity)
    actual = resolve(state, issuer, bound, require_current_profile=False)
    if (
        issuer.kind != "external_pilot"
        or actual.girl != "harpy"
        or actual.controller != controller
        or target.kind != "pilot"
        or subject is None
        or subject.character_id != target.incarnation
        or actual.offstage_source is not None
        or advancement_source(game, c, state, issuer, controller, ECHOES) is None
    ):
        raise WorkflowError("Use the living original Harpy that owns Echoes of Old Command")
    if resolve(state, target, bound, require_current_profile=False).offstage_source is not None:
        raise WorkflowError("Recover the actual original Girl before issuing this Order")
    found = next(
        (
            x.id
            for x in subject.tags
            if x.giver_actor == issuer and (condition is None or condition == x.id)
        ),
        None,
    )
    if found is None:
        raise WorkflowError("The original Girl must still carry a Tag given by this Harpy")
    return found


def voices(
    game: GameService, c: Connection, state: GameState, cast: SceneCast, viewer: int
) -> dict[ActorRef, str]:
    from girlframe.services.m3_battle import _visible

    bound = profiles(c, game.store.campaign_id)
    result = {}
    for role in cast.roles:
        if role.actor.kind not in ("pilot", "npc", "handler", "external_pilot") or not _visible(
            state, role.actor, viewer
        ):
            continue
        try:
            actor = resolve(state, role.actor, bound, require_current_profile=False)
        except ValueError:
            continue
        if actor.controller == role.controller and actor.offstage_source is None:
            result[actor.ref] = actor.label
    return result
