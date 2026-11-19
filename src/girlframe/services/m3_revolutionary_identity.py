"""Track the actual loss of the Revolutionary's original Handler-authored Identities."""

from typing import TYPE_CHECKING

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_ancillary import find
from girlframe.services.m3_access import Access
from girlframe.services.onboarding import WorkflowError

if TYPE_CHECKING:
    from girlframe.services.m2_game import GameService

RULE = "ancillary.revolutionary-idealist.easily-broken"
LOSS = "revolutionary_original_identities_lost"


def note_loss(
    game: "GameService",
    c: Connection,
    state: GameState,
    actor: ActorRef,
    event: str,
) -> None:
    try:
        Access(game.store).require_specialist_rule(RULE)
    except (ValueError, WorkflowError):
        return
    actual = find(state, actor)
    if actual is None or actual.draft.book != "REVOLUTIONARY IDEALIST":
        raise WorkflowError("Recover the actual original Revolutionary.")
    if any(x.get("kind") == LOSS and x.get("actor") == actor.token for x in state.facts):
        return
    history = t.m2["m2_state_history"]
    body = c.scalar(
        sa.select(history.c.body_json).where(
            history.c.campaign_id == game.store.campaign_id,
            history.c.event_id == actual.event,
        )
    )
    original = find(GameState.model_validate_json(body), actor) if body else None
    if original is None or original.controller != actual.controller:
        raise WorkflowError("Recover the original Handler-authored Identity source.")
    remaining = {x.id for x in actual.identities}
    if remaining.isdisjoint(x.id for x in original.identities):
        state.facts.append(dict(kind=LOSS, actor=actor.token, original=original.event, event=event))
