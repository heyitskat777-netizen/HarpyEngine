"""Enforcement Initiative uses the shared roll and exact source consequence continuations."""

import json
from typing import TYPE_CHECKING, Any

from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine.m3_handler_consequence_state import HandlerConsequence
from girlframe.services.m2_state import load_state
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer

if TYPE_CHECKING:
    from girlframe.services.m2_game import GameService


def complete_handler_consequence(
    game: "GameService",
    c: Connection,
    action: dict[str, Any],
    record: HandlerConsequence,
    event: str,
    viewer: GuildViewer,
    key: str,
) -> None:
    """Do not let an unwired source family finish through the generic Handler callback."""
    raise WorkflowError(
        "UNSUPPORTED_INITIATIVE_CONTINUATION: this source Play remains unavailable until "
        "its actual post-Handler consequence and mandatory Punishment consumers are complete."
    )


def continue_punishment(
    game: "GameService", c: Connection, action: dict[str, Any], event: str
) -> None:
    meta = action["data"].get("enforcement")
    if not meta or not meta.get("punishment") or action["state"] == "complete":
        return
    state = load_state(c, game.store.campaign_id)
    case = next((x for x in state.role_punishments if x.id == meta["punishment"]), None)
    if case is None or case.completion_event is None:
        return
    requests = [
        x
        for x in game.pending(c, action["id"])
        if x["kind"] == "enforcer_punishment"
        and json.loads(x["body_json"]).get("case_id") == case.id
    ]
    if len(requests) != 1:
        raise WorkflowError("Recover the exact actual source Punishment continuation.")
    request = requests[0]
    choices = t.m2["m2_choices"]
    c.execute(
        choices.update()
        .where(
            choices.c.campaign_id == game.store.campaign_id,
            choices.c.id == request["id"],
            choices.c.state == "pending",
        )
        .values(
            state="answered",
            revision=request["revision"] + 1,
            body_json=json.dumps(
                json.loads(request["body_json"])
                | dict(
                    completed_by_work=case.id,
                    actual_effect_event=case.effect_event,
                    completion_source=event,
                )
            ),
        )
    )
    meta["punishment_completed"] = True
    from girlframe.services.m2_choices import ChoiceEngine

    if not game.pending(c, action["id"]):
        ChoiceEngine(game).finish(c, state, action)
    game.save_action(c, action)
