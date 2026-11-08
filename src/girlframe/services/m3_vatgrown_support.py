"""Explicit adapters for original Vatgrown source effects."""

import json
from typing import Any

from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_cast import withdraw
from girlframe.services.m2_game import GameService
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer


def accept_offer(
    game: GameService,
    viewer: GuildViewer,
    key: str,
    offer: str,
    revision: int,
    account: str,
    *,
    companion: ActorRef | None = None,
    confirmed_retirement: bool = False,
) -> dict[str, Any]:
    from girlframe.services.m3_offered_girl_requisitions import accept_offer as accept

    return accept(
        game,
        viewer,
        key,
        offer,
        revision,
        account,
        companion=companion,
        confirmed_retirement=confirmed_retirement,
    )


def offer_receipt(game: GameService, c: Connection, state: GameState, offer_id: str) -> str | None:
    from girlframe.services.m3_offered_girl_requisitions import offer_receipt as receipt

    return receipt(game, c, state, offer_id)


def depart_counterpart(
    game: GameService, c: Connection, state: GameState, session: str, event: str
) -> ActorRef:
    from girlframe.services.m3_vatgrown_plays import prove, validate_counterpart_departure

    actor = validate_counterpart_departure(game, c, state, session, event)
    source = prove(game, c, state, session)
    before = next(x for x in state.scene_casts if x.id == source.cast.id and x.open)
    after = withdraw(before, actor, source.counterpart)
    state.scene_casts = [after if x.id == before.id else x for x in state.scene_casts]
    scene = game.scene(c, before.channel)
    people = [
        uid
        for uid in scene["participants"]
        if uid != source.counterpart
        or uid == after.facilitator
        or any(r.controller == uid and r.actor.kind == "pilot" for r in after.roles)
    ]
    table = t.m2["m2_scenes"]
    c.execute(
        table.update()
        .where(table.c.campaign_id == game.store.campaign_id, table.c.id == before.id)
        .values(participants_json=json.dumps(people), revision=table.c.revision + 1)
    )
    return actor


def departure_order(
    game: GameService, viewer: GuildViewer, key: str, session: str, revision: int, departure: str
) -> dict[str, Any]:
    """Record the original player's attempt against the actual stay-by-side condition."""
    from uuid import uuid4

    from girlframe.engine.m3_actor_bonds import current_ref
    from girlframe.services.m2_state import load_state
    from girlframe.services.m3_vatgrown_plays import _access, leaving_order, prove

    def authorize(c: Connection) -> None:
        _access(game, c, viewer)

    def operation(c: Connection) -> dict[str, Any]:
        game.unpaused(c)
        state = load_state(c, game.store.campaign_id)
        source = prove(game, c, state, session)
        if state.revision != revision or current_ref(state, viewer.user_id) != source.actor:
            raise WorkflowError(
                "Reopen your own current original source before attempting departure."
            )
        if not departure.strip() or len(departure) > 1200:
            raise WorkflowError("Describe the actual attempted departure.")
        lock = game.lock(c, source.cast.channel)
        if lock and lock["state"] != "released":
            raise WorkflowError("Restore chat before beginning your actual departure.")
        meta = leaving_order(game, c, state, source.actor, departure, source.cast.channel)
        if meta is None:
            raise WorkflowError("This original stay-by-side condition is no longer active.")
        identity, event = str(uuid4()), str(uuid4())
        meta["order_event"] = event
        table = t.m2["m2_orders"]
        c.execute(
            table.insert().values(
                campaign_id=game.store.campaign_id,
                id=identity,
                issuer_id=str(source.counterpart),
                target_id=str(viewer.user_id),
                channel_id=str(source.cast.channel),
                state="disobey",
                body_json=json.dumps(
                    dict(text=meta["context"], vatgrown_leaving=meta), sort_keys=True
                ),
            )
        )
        game.event(
            c,
            viewer.user_id,
            key,
            "m3.vatgrown_departure_attempted",
            state,
            event_id=event,
            order_id=identity,
            session=session,
        )
        return dict(
            order_id=identity,
            channel=source.cast.channel,
            sheet_revision=state.sheets[source.actor.entity].revision,
        )

    return game.store._write(
        viewer,
        key,
        "m3.vatgrown_departure_attempted",
        dict(session=session, revision=revision, departure=departure),
        operation,
        auto_audit=False,
        authorize=authorize,
    )


def valid_departure_order(
    game: GameService, c: Connection, state: GameState, row: dict[str, Any]
) -> bool:
    import sqlalchemy as sa

    from girlframe.services.m3_vatgrown_plays import leaving_order, prove

    meta = json.loads(row["body_json"]).get("vatgrown_leaving")
    if meta is None:
        return False
    source = prove(game, c, state, meta["session"])
    expected = leaving_order(
        game, c, state, source.actor, meta["departure"], int(row["channel_id"])
    )
    event = (
        c.execute(
            sa.select(t.events).where(
                t.events.c.campaign_id == game.store.campaign_id,
                t.events.c.id == meta.get("order_event"),
            )
        )
        .mappings()
        .first()
    )
    if (
        expected is None
        or {k: v for k, v in meta.items() if k != "order_event"} != expected
        or row["target_id"] != source.actor.entity
        or row["issuer_id"] != str(source.counterpart)
        or event is None
        or event["kind"] != "m3.vatgrown_departure_attempted"
        or event["actor_id"] != source.actor.entity
        or json.loads(event["payload_json"]).get("order_id") != row["id"]
    ):
        raise WorkflowError("Recover the actual original source-bound departure attempt.")
    return True


def finish_departure(
    game: GameService, c: Connection, state: GameState, action: dict[str, Any], event: str
) -> None:
    from girlframe.services.m3_vatgrown_plays import complete_departure, prove

    complete_departure(game, c, state, action, event)
    source = prove(game, c, state, action["data"]["vatgrown_leaving"]["session"])
    before = next((x for x in state.scene_casts if x.id == source.cast.id and x.open), None)
    if before is None:
        raise WorkflowError("Recover the actual original departure scene.")
    after = withdraw(before, source.actor, source.caster)
    state.scene_casts = [after if x.id == before.id else x for x in state.scene_casts]
    scene = game.scene(c, before.channel)
    people = [
        uid
        for uid in scene["participants"]
        if uid != source.caster
        or uid == after.facilitator
        or any(r.controller == uid for r in after.roles)
    ]
    table = t.m2["m2_scenes"]
    c.execute(
        table.update()
        .where(table.c.campaign_id == game.store.campaign_id, table.c.id == before.id)
        .values(participants_json=json.dumps(people), revision=table.c.revision + 1)
    )
