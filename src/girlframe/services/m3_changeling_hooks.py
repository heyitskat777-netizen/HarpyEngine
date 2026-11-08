"""Actual creation, Bond-operation and damage producers for Changeling sources."""

from typing import TYPE_CHECKING, Any

from sqlalchemy import Connection

from girlframe.engine import m3_changeling as rules
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_bonds import depth
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_bond_operations import records as changes
from girlframe.services.m3_actors import profiles

if TYPE_CHECKING:
    from girlframe.services.m2_game import GameService


def stage(
    game: "GameService",
    c: Connection,
    before: GameState,
    after: GameState,
    event: str,
    metadata: dict[str, Any],
) -> None:
    from girlframe.services import m3_changeling as source

    if not source._available(game, rules.STRINGS):
        return
    people = [
        ActorRef(kind="pilot", entity=str(x.owner), incarnation=x.character_id)
        for x in after.sheets.values()
        if x.character_id
    ]
    if after.world is not None:
        people += [ActorRef(kind="npc", entity=x.id) for x in after.world.npcs if x.alive]
    for actor in people:
        if actor.kind != "pilot":
            continue
        sheet = after.sheets[actor.entity]
        prior = before.sheets.get(actor.entity)
        if sheet.frame == rules.FRAME and (
            prior is None or prior.character_id != actor.incarnation
        ):
            subjects = tuple(x for x in people if x != actor and depth(after, actor, x) > 0)
            source.stage_start(game, c, after, actor, event, subjects)
    previous = {x.id for x in changes(before)}
    for change in changes(after):
        if change.id not in previous and change.event == event and change.delta == 1:
            source.stage_deepen(
                game, c, before, after, change.first, change.second, event, change.id
            )
    bound = profiles(c, game.store.campaign_id)
    for actor in people:
        try:
            prior_actor = resolve(before, actor, bound, require_current_profile=False)
            current = resolve(after, actor, bound, require_current_profile=False)
        except ValueError:
            continue
        old = {x.id: x for x in prior_actor.assets}
        for asset in current.assets:
            if asset.damaged and asset.id in old and not old[asset.id].damaged:
                source.stage_damage(
                    game,
                    c,
                    before,
                    after,
                    actor,
                    asset.id,
                    event,
                    str(metadata.get("action_id") or event),
                )


def performance(game: "GameService", c: Connection, action: dict[str, Any], event: str) -> None:
    """Observe a genuine settled All Out Assault without replaying its effects."""
    if action["data"].get("play") != "all_out_assault" or not action["data"].get("battle"):
        return
    if not action["data"].get("receipt") or "total" not in action["data"].get("result", {}):
        return
    if any(x["kind"].startswith("tag_") for x in game.pending(c, action["id"])):
        return
    from uuid import uuid4

    from girlframe.services.m2_state import load_state
    from girlframe.services.m3_changeling import stage_assault

    state = load_state(c, game.store.campaign_id)
    before = state.model_dump_json()
    fresh = str(uuid4())
    stage_assault(game, c, state, action, fresh)
    if state.model_dump_json() != before:
        game.event(
            c,
            int(action["actor_id"]),
            str(uuid4()),
            "m3.changeling_assault_gift",
            state,
            event_id=fresh,
            source_event=event,
            action_id=action["id"],
        )


def interruption(
    game: "GameService",
    c: Connection,
    viewer: Any,
    state: GameState,
    action: dict[str, Any],
    row: dict[str, Any],
) -> dict[str, Any]:
    from girlframe.services.m3_changeling_effects import _interruption
    from girlframe.services.onboarding import WorkflowError

    original = next(
        (
            x
            for x in rules.records(state, rules.Interruption)
            if x.incoming == action["id"] and x.choice == row["id"]
        ),
        None,
    )
    if original is None:
        raise WorkflowError("Recover the actual original interrupted Play")
    proved = _interruption(game, c, state, original.id)
    if (
        viewer.user_id != int(row["actor_id"])
        or resolve(
            state, proved.actor, profiles(c, game.store.campaign_id), require_current_profile=False
        ).controller
        != viewer.user_id
    ):
        raise WorkflowError(
            "Only the original interrupted person chooses their actual different Play"
        )
    return dict(source=proved.use)
