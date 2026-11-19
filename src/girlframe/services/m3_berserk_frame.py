"""Required future work follows the original Frame through activation and defeat."""

import json
from typing import Any

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_berserk_frame as rules
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_handler_consequences import same_handler_body
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_work import related
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer


def visible(state: GameState, viewer: GuildViewer) -> tuple[rules.Threat, ...]:
    result = []
    user = str(viewer.user_id)
    own = state.sheets.get(user)
    for threat in rules.threats(state):
        if threat.handler.entity == user and same_handler_body(state, threat.handler):
            result.append(threat)
        elif (
            threat.activated
            and threat.owner.entity == user
            and own is not None
            and own.character_id == threat.owner.incarnation
        ):
            result.append(threat)
    return tuple(result)


def view(game: GameService, viewer: GuildViewer, identity: str) -> dict[str, Any]:
    with game.store.engine.connect() as c:
        game.authorize(c, viewer, game=False)
        state = load_state(c, game.store.campaign_id)
        threat = next((x for x in visible(state, viewer) if x.id == identity), None)
        if threat is None:
            raise WorkflowError("This original Berserk Frame receipt is private")
        return dict(activated=bool(threat.activated), defeated=bool(threat.defeated))


def schedule(c: Connection, game: GameService, state: GameState, source: str) -> None:
    threat = next(x for x in rules.threats(state) if x.source == source)
    related(
        c,
        game.store,
        dict(campaign_id=game.store.campaign_id, campaign_context=True),
        threat.id + ":berserk",
        int(threat.handler.entity),
        int(threat.owner.entity),
        rules.KIND,
        dict(source=threat.source, frame=threat.frame, work=threat.id),
        source,
    )


def synchronize(c: Connection, game: GameService, state: GameState, event: str) -> None:
    threat = next((x for x in rules.threats(state) if event in (x.activated, x.defeated)), None)
    if threat is None:
        return
    work = t.m3["m3_required_work"]
    row = (
        c.execute(
            sa.select(work)
            .where(
                work.c.campaign_id == game.store.campaign_id,
                work.c.id == threat.id + ":berserk",
                work.c.kind == rules.KIND,
            )
            .order_by(work.c.revision.desc())
            .limit(1)
        )
        .mappings()
        .first()
    )
    source = json.loads(row["body_json"]) if row is not None else {}
    if (
        row is None
        or row["state"] != "pending"
        or source.get("source") != threat.source
        or source.get("frame") != threat.frame
        or row["subject_id"] != threat.owner.entity
        or source.get("activated") != (threat.activated if threat.defeated else None)
    ):
        raise WorkflowError("Recover the original scheduled Berserk consequence")
    c.execute(
        work.insert().values(
            **{
                k: v
                for k, v in row.items()
                if k not in ("revision", "state", "body_json", "event_id")
            },
            revision=row["revision"] + 1,
            state="resolved" if threat.defeated else "pending",
            body_json=json.dumps(
                source | dict(activated=threat.activated, defeated=threat.defeated), sort_keys=True
            ),
            event_id=event,
        )
    )
    if threat.activated == event:
        from girlframe.services.m3_battle import synchronize_casts

        synchronize_casts(game, c, event)
