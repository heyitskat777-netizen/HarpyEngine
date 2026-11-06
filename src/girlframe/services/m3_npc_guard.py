"""Actual owned Guard moves, not substitute NPC dice or narrative completion boxes."""

from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_npc_guard as rules
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_actors import resolve
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_battle import _cast
from girlframe.services.m3_items import prove_item
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer

RULE = "npc.npc.guard"


def _snapshot(c: Connection, game: GameService, event: str) -> GameState:
    raw = c.scalar(
        sa.select(t.m2["m2_state_history"].c.body_json).where(
            t.m2["m2_state_history"].c.campaign_id == game.store.campaign_id,
            t.m2["m2_state_history"].c.event_id == event,
        )
    )
    if raw is None:
        raise WorkflowError("Recover the actual performed Guard source")
    return GameState.model_validate_json(raw)


def prove_assessment(
    c: Connection, game: GameService, state: GameState, npc: ActorRef, identity: str
) -> rules.Weapons:
    value = rules.assessment(state, npc)
    if value is None or value.id != identity:
        raise WorkflowError("Review the original Guard's actual weapon facts before this roll")
    event = (
        c.execute(
            sa.select(t.events).where(
                t.events.c.campaign_id == game.store.campaign_id, t.events.c.id == value.event
            )
        )
        .mappings()
        .first()
    )
    original = _snapshot(c, game, value.event)
    fact = next(
        (
            x
            for x in original.facts
            if x.get("kind") == "npc_guard_weapons" and x.get("id") == identity
        ),
        None,
    )
    if (
        event is None
        or event["kind"] != "m3.npc_guard_weapons_reviewed"
        or event["actor_id"] != str(value.controller)
        or fact is None
        or rules.Weapons.model_validate_json(fact["body"]) != value
    ):
        raise WorkflowError("Recover the actual original Guard weapon review")
    for item in rules.weapons(state, npc):
        prove_item(c, game, state, item.id)
    return value


def prove_performed(
    c: Connection,
    game: GameService,
    event: str,
    parent: str,
    choice: str,
    npc: ActorRef,
    attacker: ActorRef,
) -> None:
    original = _snapshot(c, game, event)
    fact = next(
        (
            x
            for x in original.facts
            if x.get("kind") == "npc_guard_performed" and x.get("event") == event
        ),
        None,
    )
    row = (
        c.execute(
            sa.select(t.events).where(
                t.events.c.campaign_id == game.store.campaign_id, t.events.c.id == event
            )
        )
        .mappings()
        .first()
    )
    record = rules.Performed.model_validate_json(fact["body"]) if fact else None
    if (
        record is None
        or row is None
        or row["kind"] != "m3.npc_guard_play_performed"
        or row["actor_id"] != str(record.controller)
        or record.parent != parent
        or record.choice != choice
        or record.actor != npc
        or record.opponent != attacker
        or not rules.supported(original, npc, attacker, record.scene)
    ):
        raise WorkflowError("Only this original performed printed Guard move completes its counter")
    if record.move == "draw_weapon":
        item = prove_item(c, game, original, record.weapon or "")
        if item not in rules.weapons(original, npc):
            raise WorkflowError("The Guard drew no actual carried weapon")


def _prove_branch(game: GameService, c: Connection, state: GameState, actor: ActorRef) -> None:
    from girlframe.engine.m3_am_branch import branch

    copied = branch(state, actor)
    if copied is not None:
        from girlframe.services.m3_am_branch import prove

        prove(game, c, state, copied.id)


class GuardService:
    def __init__(self, game: GameService):
        self.game, self.store = game, game.store

    def _access(self, c: Connection, viewer: GuildViewer) -> None:
        access = Access(self.store)
        access.authorize(c, viewer, "plays")
        access.authorize(c, viewer, "world")
        assert access.registry is not None
        access.registry.require_available(RULE)

    def preview(self, viewer: GuildViewer, channel: int) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self._access(c, viewer)
            state = load_state(c, self.store.campaign_id)
            cast = _cast(self.game, c, state, channel)
            guards = []
            for role in cast.roles:
                if role.actor.kind != "npc" or role.controller != viewer.user_id:
                    continue
                targets = [
                    x.actor for x in cast.roles if rules.supported(state, role.actor, x.actor, cast)
                ]
                if not targets:
                    continue
                actual = resolve(state, role.actor, ())
                _prove_branch(self.game, c, state, role.actor)
                guards.append(
                    dict(
                        ref=role.actor.model_dump(mode="json"),
                        label=actual.label,
                        targets=[
                            dict(
                                ref=x.model_dump(mode="json"), label=state.sheets[x.entity].callsign
                            )
                            for x in targets
                        ],
                        weapons=[
                            dict(id=x.id, label=x.name) for x in rules.weapons(state, role.actor)
                        ],
                    )
                )
            return dict(revision=state.revision, guards=guards)

    def assess(
        self,
        viewer: GuildViewer,
        key: str,
        channel: int,
        npc: ActorRef,
        attacker: ActorRef,
        expected: int,
        unarmed: bool,
        account: str,
    ) -> dict[str, Any]:
        if type(unarmed) is not bool or not account.strip() or len(account) > 1200:
            raise WorkflowError("The actual Guard controller states its real weapon facts")

        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            cast = _cast(self.game, c, state, channel)
            actual = resolve(state, npc, ())
            _prove_branch(self.game, c, state, npc)
            if (
                state.revision != expected
                or actual.controller != viewer.user_id
                or not rules.supported(state, npc, attacker, cast)
            ):
                raise WorkflowError("Review this actual co-present Guard and original opponent")
            items = rules.weapons(state, npc)
            if unarmed and items or not unarmed and not items:
                raise WorkflowError(
                    "Reconcile carried weapons first; absence alone does not prove unarmed"
                )
            for item in items:
                prove_item(c, self.game, state, item.id)
            event, identity = str(uuid4()), str(uuid4())
            value = rules.Weapons(
                id=identity,
                actor=npc,
                npc_sha256=actual.source_sha256,
                inventory_sha256=rules.inventory_sha(state, npc),
                unarmed=unarmed,
                scene=cast.id,
                controller=viewer.user_id,
                event=event,
                account=account,
            )
            state.facts.append(
                dict(kind="npc_guard_weapons", id=identity, body=value.model_dump_json())
            )
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.npc_guard_weapons_reviewed",
                state,
                event_id=event,
                review_id=identity,
            )
            return dict(id=identity, unarmed=unarmed)

        return self.store._write(
            viewer,
            key,
            "m3.npc_guard_weapons_reviewed",
            dict(
                channel=channel,
                npc=npc.model_dump(mode="json"),
                attacker=attacker.model_dump(mode="json"),
                expected=expected,
                unarmed=unarmed,
                account=account,
            ),
            operation,
            auto_audit=False,
            authorize=lambda c: self._access(c, viewer),
        )

    def counter(self, viewer: GuildViewer, parent: str, choice: str) -> dict[str, Any]:
        from girlframe.services.m3_alpha import npc_counter_context

        with self.store.engine.connect() as c:
            self._access(c, viewer)
            state, npc, attacker, cast = npc_counter_context(self.game, c, parent, choice)
            actual = resolve(state, npc, ())
            _prove_branch(self.game, c, state, npc)
            if actual.controller != viewer.user_id or not rules.supported(
                state, npc, attacker, cast
            ):
                raise WorkflowError("Only the actual capable Guard owns this counter")
            return dict(
                revision=state.revision,
                label=actual.label,
                weapons=[dict(id=x.id, label=x.name) for x in rules.weapons(state, npc)],
            )

    def perform_counter(
        self,
        viewer: GuildViewer,
        key: str,
        parent: str,
        choice: str,
        expected: int,
        move: rules.Move,
        account: str,
        weapon: str | None = None,
    ) -> dict[str, Any]:
        from girlframe.services.m3_alpha import complete_npc_counter, npc_counter_context

        if move not in dict(rules.MOVES) or not account.strip() or len(account) > 1200:
            raise WorkflowError(
                "Choose the real printed Guard move and describe its actual performance"
            )

        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            state, npc, attacker, cast = npc_counter_context(self.game, c, parent, choice)
            actual = resolve(state, npc, ())
            _prove_branch(self.game, c, state, npc)
            if (
                state.revision != expected
                or actual.controller != viewer.user_id
                or not rules.supported(state, npc, attacker, cast)
            ):
                raise WorkflowError("STALE_GUARD: reopen the actual original counter")
            if move == "draw_weapon":
                item = prove_item(c, self.game, state, weapon or "")
                if item not in rules.weapons(state, npc):
                    raise WorkflowError("Choose the actual carried weapon")
            elif weapon is not None:
                raise WorkflowError("This printed move does not draw a weapon")
            event = str(uuid4())
            value = rules.Performed(
                event=event,
                parent=parent,
                choice=choice,
                actor=npc,
                opponent=attacker,
                move=move,
                scene=cast,
                controller=viewer.user_id,
                weapon=weapon,
                account=account,
            )
            state.facts.append(
                dict(kind="npc_guard_performed", event=event, body=value.model_dump_json())
            )
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.npc_guard_play_performed",
                state,
                event_id=event,
                parent=parent,
                choice=choice,
            )
            complete_npc_counter(self.game, c, parent, choice, npc, event)
            return dict(event=event, parent=parent)

        return self.store._write(
            viewer,
            key,
            "m3.npc_guard_play_performed",
            dict(
                parent=parent,
                choice=choice,
                expected=expected,
                move=move,
                account=account,
                weapon=weapon,
            ),
            operation,
            auto_audit=False,
            authorize=lambda c: self._access(c, viewer),
        )
