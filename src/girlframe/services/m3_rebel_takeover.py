"""The original takeover settles only after real custody and Broken effects."""

import json
from typing import Any
from uuid import NAMESPACE_URL, uuid4, uuid5

from sqlalchemy import Connection

from girlframe.engine import m3_rebel_takeover as rules
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef, SceneCast
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_handler_consequences import active_handler, same_handler_body
from girlframe.engine.m3_world_state import Cell, Faction
from girlframe.services.handler_setup import HandlerService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_budget_tags import _selection
from girlframe.services.m3_rebel_ambush import _cast
from girlframe.services.m3_strain import StrainService
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer

EVENT = "m3.rebel_group_takeover"


def visible(state: GameState, viewer: GuildViewer) -> tuple[rules.Takeover, ...]:
    world = state.world
    if world is None:
        return ()
    return tuple(
        x
        for x in rules.takeovers(state)
        if (
            x.handler.entity == str(viewer.user_id)
            and same_handler_body(state, x.handler)
            or any(
                npc.faction == x.replacement.id and npc.alive and npc.controller == viewer.user_id
                for npc in world.npcs
            )
            or any(
                captive.actor.entity == pilot.id and pilot.controller == viewer.user_id
                for captive in x.prisoners
                for pilot in world.pilots
            )
        )
    )


class TakeoverService:
    def __init__(self, strain: StrainService):
        self.strain, self.store, self.game = strain, strain.store, strain.game

    def _source(self, c: Connection, identity: str) -> tuple[dict[str, Any], GameState, str]:
        row, original = _selection(c, self.game, identity, rule=rules.RULE)
        source = json.loads(row["body_json"])["source_work"]
        group = (
            next((x.faction for x in original.strain.endgames if x.id == source), None)
            if original.strain
            else None
        )
        if group is None:
            raise WorkflowError("Recover the original selected Rebel Group")
        return row, original, group

    def _available(
        self,
        c: Connection,
        state: GameState,
        value: rules.Takeover,
        viewer: GuildViewer,
        channel: int,
    ) -> tuple[SceneCast | None, dict[str, tuple[ActorRef, ActorRef, str, str]]]:
        world = state.world
        cast = _cast(self.game, c, state, channel)
        if cast is None or world is None or value.completed:
            return cast, {}
        joined = {x.actor: x.controller for x in cast.roles}
        members = HandlerService(self.store)
        pairs = {}
        for body in world.npcs:
            captor = ActorRef(kind="npc", entity=body.id)
            if (
                body.controller != viewer.user_id
                or joined.get(captor) != viewer.user_id
                or body.faction != value.replacement.id
                or not body.alive
                or body.captive_of is not None
            ):
                continue
            physical = resolve(state, captor, ())
            if physical.cell is None or physical.offstage_source is not None:
                continue
            for pilot in world.pilots:
                target = ActorRef(kind="external_pilot", entity=pilot.id)
                if (
                    target not in value.pilots
                    or not pilot.revealed
                    or not pilot.alive
                    or pilot.faction != value.original.id
                    or pilot.controller == viewer.user_id
                    or joined.get(target) != pilot.controller
                    or not members._member(c, pilot.controller)
                ):
                    continue
                target_body = resolve(state, target, ())
                if (
                    target_body.cell != physical.cell
                    or target_body.offstage_source
                    or target_body.inside_frame is not False
                ):
                    continue
                captive = next((x for x in value.prisoners if x.actor == target), None)
                if captive is None and pilot.custody == "free":
                    decision = "capture"
                elif (
                    captive is not None
                    and captive.captor == captor
                    and captive.scene == cast.id
                    and not captive.broken
                    and pilot.custody == "captured"
                    and pilot.custody_event == captive.source
                ):
                    decision = "break"
                else:
                    continue
                key = str(
                    uuid5(
                        NAMESPACE_URL,
                        value.id + ":" + captor.token + ":" + target.token + ":" + decision,
                    )
                )
                pairs[key] = (
                    captor,
                    target,
                    decision,
                    ("Capture " if decision == "capture" else "Break ") + pilot.name,
                )
        return cast, pairs

    def get(self, viewer: GuildViewer, identity: str, channel: int) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            state = load_state(c, self.store.campaign_id)
            value = next((x for x in rules.takeovers(state) if x.id == identity), None)
            if value is None:
                _, original, group = self._source(c, identity)
                handler = active_handler(original)
                if (
                    handler is None
                    or handler.entity != str(viewer.user_id)
                    or not same_handler_body(state, handler)
                ):
                    raise WorkflowError("Only the original Handler writes up the new group")
                return dict(revision=state.revision, setup=True, original=group)
            if value not in visible(state, viewer):
                raise WorkflowError("The takeover belongs to its actual original participants")
            _, pairs = self._available(c, state, value, viewer, channel)
            is_handler = value.handler.entity == str(viewer.user_id) and same_handler_body(
                state, value.handler
            )
            world = state.world
            assert world is not None
            own_roles = {
                ActorRef(kind="npc", entity=x.id)
                for x in world.npcs
                if x.controller == viewer.user_id and x.alive
            }
            own_roles |= {
                ActorRef(kind="external_pilot", entity=x.id)
                for x in world.pilots
                if x.controller == viewer.user_id and x.alive
            }
            heard = (
                value.prisoners
                if is_handler
                else tuple(x for x in value.prisoners if {x.actor, x.captor} & own_roles)
            )
            return dict(
                revision=state.revision,
                setup=False,
                group=value.replacement.name,
                captured=len(heard),
                broken=sum(bool(x.broken) for x in heard),
                total=len(value.pilots) if is_handler else None,
                complete=bool(value.completed),
                choices=tuple((token, p[3]) for token, p in pairs.items()),
            )

    def organize(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        name: str,
        description: str,
        cell: Cell,
    ) -> dict[str, Any]:
        name, description = name.strip(), description.strip()
        if not (0 < len(name) <= 120 and 0 < len(description) <= 1200):
            raise WorkflowError("Write up the original new group and its actual danger")

        def authorize(c: Connection) -> None:
            self.strain._authorize(c, viewer)
            self.strain.missions.access.authorize(c, viewer, "world")
            self.game.unpaused(c)

        def operation(c: Connection) -> dict[str, Any]:
            state = self.strain._state(c, revision)
            row, original, group = self._source(c, identity)
            handler = active_handler(original)
            world = state.world
            period = self.strain.periods._get(c, row["off_duty_id"])
            old = next((x for x in world.factions if x.id == group), None) if world else None
            if (
                handler is None
                or not same_handler_body(state, handler)
                or handler.entity != str(viewer.user_id)
                or row["state"] != "pending"
                or period.phase != "preparing"
                or world is None
                or old is None
                or not world.board.contains(cell)
            ):
                raise WorkflowError(
                    "Recover the original group, original Handler and actual mapped territory"
                )
            roster = tuple(
                x for x in world.pilots if x.kind == "rebel" and x.faction == old.id and x.alive
            )
            if any(x.custody != "free" for x in roster):
                raise WorkflowError(
                    "Review existing custody of an original Pilot before the takeover"
                )
            event = str(uuid4())
            new_id = str(uuid5(NAMESPACE_URL, "rebel-takeover:" + identity))
            replacement = Faction(
                id=new_id, kind="rebel", name=name, cells=(cell,), description=description
            )
            changed = rules.organize(
                state,
                rules.Takeover(
                    id=identity,
                    source=row["event_id"],
                    period=period.id,
                    handler=handler,
                    original=old,
                    replacement=replacement,
                    organization=event,
                    pilots=tuple(ActorRef(kind="external_pilot", entity=x.id) for x in roster),
                ),
            )
            self.game.event(
                c,
                viewer.user_id,
                key,
                EVENT,
                state,
                event_id=event,
                work_id=identity,
                decision="organize",
                faction=new_id,
            )
            if changed.completed:
                self.strain._save(c, row, event, json.loads(row["body_json"]), resolved=True)
            return dict(id=identity, group=new_id, complete=bool(changed.completed))

        return self.strain.missions._write(
            viewer,
            key,
            EVENT,
            dict(id=identity, revision=revision, name=name, description=description, cell=cell),
            operation,
            authorize,
        )

    def resolve(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        channel: int,
        selection: str,
        account: str,
    ) -> dict[str, Any]:
        account = account.strip()
        if not 0 < len(account) <= 1200:
            raise WorkflowError("Record your own part in the original custody or breaking")

        def authorize(c: Connection) -> None:
            for scope in ("strain", "world"):
                self.strain.missions.access.authorize(c, viewer, scope)
            self.game.unpaused(c)
            if not any(
                x.id == identity for x in visible(load_state(c, self.store.campaign_id), viewer)
            ):
                raise WorkflowError("Only an original participant can act in the takeover")

        def operation(c: Connection) -> dict[str, Any]:
            row, original, group = self._source(c, identity)
            state = self.strain._state(c, revision)
            value = next(x for x in rules.takeovers(state) if x.id == identity)
            cast, pairs = self._available(c, state, value, viewer, channel)
            pair = pairs.get(selection)
            if (
                pair is None
                or cast is None
                or row["state"] != "pending"
                or row["event_id"] != value.source
                or value.original.id != group
                or active_handler(original) != value.handler
                or not same_handler_body(state, value.handler)
                or self.strain.periods._get(c, value.period).phase != "preparing"
            ):
                raise WorkflowError(
                    "Only the actual new rebel in the original scene can resolve this custody"
                )
            event = str(uuid4())
            captor, target, decision, _ = pair
            if decision == "capture":
                value = rules.capture(
                    state,
                    value,
                    rules.Prisoner(
                        actor=target,
                        captor=captor,
                        source=event,
                        scene=cast.id,
                        account=account,
                    ),
                    viewer.user_id,
                )
            else:
                prisoner = next(x for x in value.prisoners if x.actor == target)
                value = rules.break_pilot(state, value, prisoner, event, account)
            self.game.event(
                c,
                viewer.user_id,
                key,
                EVENT,
                state,
                event_id=event,
                work_id=identity,
                decision=decision,
                target_actor=target.model_dump(mode="json"),
                captor=captor.model_dump(mode="json"),
            )
            if value.completed:
                self.strain._save(c, row, event, json.loads(row["body_json"]), resolved=True)
            return dict(id=identity, decision=decision, complete=bool(value.completed))

        return self.strain.missions._write(
            viewer,
            key,
            EVENT,
            dict(
                id=identity,
                revision=revision,
                channel=channel,
                selection=selection,
                account=account,
            ),
            operation,
            authorize,
        )
