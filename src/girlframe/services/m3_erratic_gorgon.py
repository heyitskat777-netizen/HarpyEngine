"""Original Erratic Gorgon Tags, battlefield flight and pursuit."""

from collections.abc import Callable
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_erratic_flight as flight_rules
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef, SceneCast
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_engage import Maneuver
from girlframe.engine.m3_world import update
from girlframe.engine.m3_world_state import Cell, Gorgon, Npc, WorldTag
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_battle import _cast, _visible
from girlframe.services.m3_gorgon_play import GorgonPlayService
from girlframe.services.m3_handler_advancements import _history
from girlframe.services.m3_movement import apply_reviewed_movement, proposal_context
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer

RULE = "gorgon.gorgon.class-iii-erratic"
TAG_EVENT = "m3.erratic_npc_tag_inflicted"
FLEE_EVENT = "m3.erratic_gorgon_fled"
CATCH_EVENT = "m3.erratic_gorgon_caught"


def require_caught(state: GameState, target: ActorRef, scene: str) -> None:
    if target.kind == "gorgon" and flight_rules.active(state, target, scene):
        raise WorkflowError("Catch the fled Erratic Gorgon with an actual pursuit Play first")


def _battle(
    game: GameService, c: Connection, action: dict[str, Any], scene: str
) -> dict[str, Any] | None:
    data = action["data"]
    meta = data.get("battle") or data.get("engage")
    if (
        action["state"] != "complete"
        or action["scene_id"] != scene
        or not meta
        or not data.get("receipt")
    ):
        return None
    receipts = t.m2["m2_receipts"]
    saved = c.scalar(
        sa.select(receipts.c.id).where(
            receipts.c.campaign_id == game.store.campaign_id,
            receipts.c.action_id == action["id"],
            receipts.c.id == data["receipt"]["id"],
        )
    )
    return meta if saved else None


def _pursued(
    game: GameService,
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    flight: flight_rules.Flight,
    actor: ActorRef,
) -> bool:
    meta = _battle(game, c, action, flight.scene)
    if (
        not meta
        or action["actor_id"] != actor.entity
        or action["data"]["play"] != "engage"
        or not meta.get("applied")
        or meta["target"] != flight.gorgon.model_dump(mode="json")
        or meta["actor"] != actor.model_dump(mode="json")
    ):
        return False
    events = sa.select(t.events.c.seq).where(t.events.c.campaign_id == game.store.campaign_id)
    after = c.scalar(events.where(t.events.c.id == flight.event))
    if after is None:
        return False
    for fact in state.facts:
        if fact.get("kind") != "engage_maneuver":
            continue
        maneuver = Maneuver.model_validate_json(fact["body"])
        if (
            maneuver.source_action == action["id"]
            and maneuver.actor == actor
            and maneuver.opponent == flight.gorgon
            and maneuver.scene == flight.scene
            and maneuver.kind in ("advance", "pin")
            and c.scalar(
                events.where(t.events.c.id == maneuver.source_event, t.events.c.seq > after)
            )
        ):
            born = _history(c, game, maneuver.source_event)
            if fact in born.facts:
                return True
    return False


class ErraticService:
    def __init__(self, game: GameService):
        self.game, self.store = game, game.store

    def _access(self, c: Connection, viewer: GuildViewer) -> None:
        GorgonPlayService(self.game).authorize(c, viewer)
        try:
            Access(self.store).require_specialist_rule(RULE)
        except ValueError as error:
            raise WorkflowError(str(error)) from None

    def _options(
        self, c: Connection, viewer: GuildViewer, channel: int
    ) -> tuple[GameState, SceneCast, dict[str, Gorgon], dict[str, Npc]]:
        state = load_state(c, self.store.campaign_id)
        cast = _cast(self.game, c, state, channel)
        if state.world is None:
            raise WorkflowError("Initialize the actual world before the Gorgon acts")
        bound = profiles(c, self.store.campaign_id)
        by_id = {x.id: x for x in state.world.gorgons if x.alive and x.gorgon_class == "erratic"}
        gorgons = {}
        for role in cast.roles:
            if (
                role.actor.kind != "gorgon"
                or role.controller != viewer.user_id
                or role.actor.entity not in by_id
            ):
                continue
            actual = resolve(state, role.actor, bound)
            if (
                actual.controller == viewer.user_id
                and actual.cell is not None
                and actual.offstage_source is None
            ):
                gorgons[role.actor.entity] = by_id[role.actor.entity]
        targets = (
            {
                x.id: x
                for x in state.world.npcs
                if x.alive and _visible(state, ActorRef(kind="npc", entity=x.id), viewer.user_id)
            }
            if gorgons
            else {}
        )
        return state, cast, gorgons, targets

    def view(self, viewer: GuildViewer, channel: int) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self._access(c, viewer)
            state, _, gorgons, targets = self._options(c, viewer, channel)
            return dict(
                revision=state.revision,
                gorgons=tuple((key, x.name) for key, x in gorgons.items()),
                npcs=tuple((key, x.name) for key, x in targets.items()),
            )

    def flight_view(self, viewer: GuildViewer, channel: int) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self._access(c, viewer)
            state, cast, originals, _ = self._options(c, viewer, channel)
            if not any(role.controller == viewer.user_id for role in cast.roles):
                return dict(revision=state.revision, battles=[], pursuits=[])
            recorded = flight_rules.flights(state).values()
            used = {(item.gorgon, item.battle) for item in recorded}
            waiting = {
                item.gorgon for item in recorded if item.scene == cast.id and item.caught is None
            }
            active = [
                x
                for x in recorded
                if x.scene == cast.id
                and x.caught is None
                and _visible(state, x.gorgon, viewer.user_id)
            ]
            table = t.m2["m2_actions"]
            actions = [
                self.game.action(c, identity)
                for identity in c.scalars(
                    sa.select(table.c.id)
                    .where(
                        table.c.campaign_id == self.store.campaign_id,
                        table.c.scene_id == cast.id,
                        table.c.state == "complete",
                    )
                    .order_by(table.c.id)
                )
            ]
            battles: list[dict[str, str]] = []
            pursuits: list[dict[str, str]] = []
            for action in actions:
                meta = _battle(self.game, c, action, cast.id)
                if meta is None:
                    continue
                for field in ("actor", "target"):
                    ref = ActorRef.model_validate(meta[field])
                    if (
                        ref.kind == "gorgon"
                        and ref.entity in originals
                        and ref not in waiting
                        and (ref, action["id"]) not in used
                    ):
                        battles.append(
                            dict(
                                action=action["id"],
                                gorgon=ref.entity,
                                label=originals[ref.entity].name,
                            )
                        )
                if viewer.user_id in state.order and action["actor_id"] == str(viewer.user_id):
                    actor = current_ref(state, viewer.user_id)
                    pursuits.extend(
                        dict(action=action["id"], event=x.event, gorgon=x.gorgon.entity)
                        for x in active
                        if _pursued(self.game, c, state, action, x, actor)
                    )
            return dict(revision=state.revision, battles=battles, pursuits=pursuits)

    def flee(
        self,
        viewer: GuildViewer,
        key: str,
        channel: int,
        expected: int,
        gorgon: str,
        battle: str,
        destination: Cell,
        account: str,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            state, cast, originals, _ = self._options(c, viewer, channel)
            if state.revision != expected or gorgon not in originals:
                raise WorkflowError("Reopen your original Erratic Gorgon's flight from battle")
            ref = ActorRef(kind="gorgon", entity=gorgon)
            active = flight_rules.flights(state).values()
            meta = _battle(self.game, c, self.game.action(c, battle), cast.id)
            origin = originals[gorgon].cell
            if (
                not meta
                or all(ActorRef.model_validate(meta[name]) != ref for name in ("actor", "target"))
                or origin is None
                or origin == destination
                or any(
                    x.gorgon == ref and (x.battle == battle or x.scene == cast.id and not x.caught)
                    for x in active
                )
            ):
                raise WorkflowError(
                    "Flee a real completed exchange once to a different mapped square"
                )
            context = proposal_context(
                self.game, c, viewer, state, channel, ref, destination, False, account
            )
            event = str(uuid4())
            apply_reviewed_movement(self.game, c, viewer, state, context, event)
            flight_rules.save(
                state,
                flight_rules.Flight(
                    gorgon=ref,
                    scene=cast.id,
                    channel=channel,
                    battle=battle,
                    departure=origin,
                    destination=destination,
                    event=event,
                ),
            )
            self.game.event(
                c, viewer.user_id, key, FLEE_EVENT, state, event_id=event, scene_id=cast.id
            )
            return dict(event=event, destination=list(destination))

        return self._write_flight(
            viewer,
            key,
            FLEE_EVENT,
            dict(
                channel=channel,
                expected=expected,
                gorgon=gorgon,
                battle=battle,
                destination=destination,
                account=account,
            ),
            operation,
        )

    def catch(
        self,
        viewer: GuildViewer,
        key: str,
        channel: int,
        expected: int,
        identity: str,
        pursuit: str,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            state, cast, _, _ = self._options(c, viewer, channel)
            item = flight_rules.flights(state).get(identity)
            if (
                state.revision != expected
                or item is None
                or item.scene != cast.id
                or item.caught
                or viewer.user_id not in state.order
                or not _visible(state, item.gorgon, viewer.user_id)
            ):
                raise WorkflowError("Reopen the actual original pursuit in this scene")
            actor = current_ref(state, viewer.user_id)
            bound = profiles(c, self.store.campaign_id)
            first, second = (resolve(state, ref, bound) for ref in (actor, item.gorgon))
            action = self.game.action(c, pursuit)
            if (
                first.cell is None
                or first.cell != second.cell
                or first.offstage_source
                or second.offstage_source
                or not {actor, item.gorgon} <= {x.actor for x in cast.roles}
                or not _pursued(self.game, c, state, action, item, actor)
                or flight_rules.flights(_history(c, self.game, item.event)).get(identity) != item
            ):
                raise WorkflowError(
                    "Reach the original Gorgon's square and complete a real Engage advance or pin"
                )
            lock = self.game.lock(c, channel)
            if lock and lock["state"] != "released":
                raise WorkflowError(
                    "Finish and restore this source's battle before recording the catch"
                )
            event = str(uuid4())
            flight_rules.save(
                state, item.model_copy(update=dict(catcher=actor, pursuit=pursuit, caught=event))
            )
            self.game.event(
                c, viewer.user_id, key, CATCH_EVENT, state, event_id=event, scene_id=cast.id
            )
            return dict(event=event, original_flight=identity)

        return self._write_flight(
            viewer,
            key,
            CATCH_EVENT,
            dict(channel=channel, expected=expected, identity=identity, pursuit=pursuit),
            operation,
        )

    def _write_flight(
        self,
        viewer: GuildViewer,
        key: str,
        event: str,
        payload: dict[str, Any],
        operation: Callable[[Connection], dict[str, Any]],
    ) -> dict[str, Any]:
        def authorize(c: Connection) -> None:
            self._access(c, viewer)
            self.game.unpaused(c)

        try:
            return self.store._write(
                viewer, key, event, payload, operation, auto_audit=False, authorize=authorize
            )
        except ValueError as exc:
            raise WorkflowError(str(exc)) from None

    def tag(
        self,
        viewer: GuildViewer,
        key: str,
        channel: int,
        expected: int,
        gorgon: str,
        npc: str,
        label: str,
        account: str,
    ) -> dict[str, Any]:
        if not 0 < len(label.strip()) <= 120 or not 0 < len(account.strip()) <= 1200:
            raise WorkflowError("Provide the actual Tag and how the Erratic Gorgon caused it")

        def authorize(c: Connection) -> None:
            self._access(c, viewer)
            self.game.unpaused(c)

        def operation(c: Connection) -> dict[str, Any]:
            state, cast, gorgons, targets = self._options(c, viewer, channel)
            lock = self.game.lock(c, channel)
            if state.revision != expected or (lock is not None and lock["state"] != "released"):
                raise WorkflowError(
                    "STALE_ERRATIC: finish the actual current scene Play and reopen the choice"
                )
            target = targets.get(npc)
            if gorgon not in gorgons or target is None:
                raise WorkflowError(
                    "Choose an actual controlled Erratic Gorgon and eligible original NPC"
                )
            assert state.world is not None
            event = str(uuid4())
            actor = ActorRef(kind="gorgon", entity=gorgon)
            tag = WorldTag(id=event, label=label.strip(), giver_entity=actor.model_dump_json())
            altered = target.model_copy(update={"tags": (*target.tags, tag)})
            state.world = update(
                state.world, npcs=tuple(altered if x.id == npc else x for x in state.world.npcs)
            )
            state.facts.append(
                dict(
                    kind="erratic_npc_tag",
                    id=event,
                    gorgon=gorgon,
                    npc=npc,
                    scene=cast.id,
                    account=account.strip(),
                )
            )
            self.game.event(
                c, viewer.user_id, key, TAG_EVENT, state, event_id=event, scene_id=cast.id
            )
            return dict(event=event, state="resolved")

        return self.store._write(
            viewer,
            key,
            TAG_EVENT,
            dict(
                channel=channel,
                expected=expected,
                gorgon=gorgon,
                npc=npc,
                label=label,
                account=account,
            ),
            operation,
            auto_audit=False,
            authorize=authorize,
        )
