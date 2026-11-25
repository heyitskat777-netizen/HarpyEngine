"""An actual Chained Darling Bond attempt opens the original Handler’s alternative."""

from typing import Any
from uuid import uuid4

from sqlalchemy import Connection

from girlframe.engine import m3_ancillary_cadre as rank
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_bonds import depth
from girlframe.engine.m3_actor_state import CastRole
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_ancillary import find
from girlframe.engine.m3_battle import damage
from girlframe.engine.m3_harpy_defeat import give_tag
from girlframe.engine.m3_role_punishment_state import RolePunishment
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_role_punishments import case_proof, current, synchronize
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer

RULE = "ancillary.chained-darling.isolation-protocol"
KIND = "chained_isolation"


def _approved(game: GameService) -> bool:
    try:
        Access(game.store).require_specialist_rule(RULE)
    except (ValueError, WorkflowError):
        return False
    return True


def stage(game: GameService, state: GameState, case: RolePunishment, event: str) -> bool:
    role = find(state, case.subject)
    if (
        case.source_kind != "ancillary_cadre"
        or case.instruction is None
        or case.instruction.kind != "quality_time"
        or role is None
        or role.draft.book != "CHAINED DARLING"
        or depth(state, case.subject, case.executor) > 0
        or not _approved(game)
    ):
        return False
    cadre = rank.current(state, case.subject)
    if cadre is None or cadre.handler != case.executor or pending(state, case.id):
        raise WorkflowError("Recover the original Chained Darling and the actual Handler choice.")
    state.facts.append(dict(kind=KIND, id=case.id, source=event, handler=str(cadre.handler_owner)))
    return True


def pending(state: GameState, identity: str) -> bool:
    return any(
        x.get("kind") == KIND and x.get("id") == identity and not x.get("decided")
        for x in state.facts
    )


def _issued(state: GameState, identity: str, order: str) -> dict[str, str]:
    fact = next(
        (
            x
            for x in state.facts
            if x.get("kind") == KIND
            and x.get("id") == identity
            and x.get("order") == order
            and not x.get("decided")
        ),
        None,
    )
    if fact is None:
        raise WorkflowError("Recover the original outstanding Isolation Order.")
    return fact


def prove_order(
    game: GameService,
    c: Connection,
    state: GameState,
    identity: str,
    order: str,
    owner: CastRole,
    target: CastRole,
) -> None:
    Access(game.store).require_specialist_rule(RULE)
    fact = _issued(state, identity, order)
    case = case_proof(c, game, identity)
    current(c, game, state, case)
    if (
        case.effect_event != fact["source"]
        or (case.executor, case.executor_controller) != (owner.actor, owner.controller)
        or (case.subject, case.subject_controller) != (target.actor, target.controller)
    ):
        raise WorkflowError("Recover the original Handler and affected Chained Darling.")


def complete_order(state: GameState, identity: str, order: str, event: str) -> None:
    _issued(state, identity, order)["decided"] = event


def _channel(state: GameState, identity: str) -> int:
    from girlframe.services.m3_ancillary_discipline import SCOPE

    fact = next(
        (x for x in state.facts if x.get("kind") == SCOPE and x.get("id") == identity), None
    )
    if fact is None:
        raise WorkflowError("Recover the original punishment scene.")
    return int(fact["channel"])


class IsolationService:
    def __init__(self, game: GameService):
        self.game, self.store = game, game.store

    def _gate(self, c: Connection, viewer: GuildViewer) -> None:
        gate = Access(self.store)
        gate.authorize(c, viewer, "discipline")
        gate.require_specialist_rule(RULE)

    def _source(
        self,
        c: Connection,
        state: GameState,
        viewer: GuildViewer,
        identity: str,
    ) -> tuple[dict[str, str], RolePunishment]:
        fact = next(
            (
                x
                for x in state.facts
                if x.get("kind") == KIND
                and x.get("id") == identity
                and not x.get("decided")
                and not x.get("order")
                and x.get("handler") == str(viewer.user_id)
            ),
            None,
        )
        if fact is None:
            raise WorkflowError("This original Isolation replacement is unavailable.")
        case = case_proof(c, self.game, identity)
        current(c, self.game, state, case)
        if case.effect_event != fact["source"] or case.executor_controller != viewer.user_id:
            raise WorkflowError("Recover the actual executed original source and original Handler.")
        return fact, case

    def _damage(self, c: Connection, state: GameState, case: RolePunishment) -> dict[str, str]:
        actual = resolve(state, case.subject, profiles(c, self.store.campaign_id))
        names = {
            x.id: x.name
            for x in actual.assets
            if x.family == "girl" and not x.damaged and not x.concealed
        }
        return names if len(names) >= 2 else {}

    def tasks(self, c: Connection, state: GameState, viewer: GuildViewer) -> tuple[str, ...]:
        candidates = tuple(
            x["id"]
            for x in state.facts
            if x.get("kind") == KIND
            and x.get("handler") == str(viewer.user_id)
            and not x.get("decided")
            and not x.get("order")
        )
        if not candidates:
            return ()
        try:
            self._gate(c, viewer)
        except (ValueError, WorkflowError):
            return ()
        ready = []
        for identity in candidates:
            try:
                self._source(c, state, viewer, identity)
            except (ValueError, WorkflowError):
                continue
            ready.append(identity)
        return tuple(ready)

    def get(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        from girlframe.services.m3_ancillary_orders import AncillaryOrderService

        with self.store.engine.connect() as c:
            self._gate(c, viewer)
            state = load_state(c, self.store.campaign_id)
            _, case = self._source(c, state, viewer, identity)
            available = False
            try:
                AncillaryOrderService(self.game).isolation_roles(
                    c, state, case, _channel(state, identity)
                )
                available = True
            except (ValueError, WorkflowError):
                pass
            return dict(
                revision=state.revision,
                assets=self._damage(c, state, case),
                order_available=available,
            )

    def decide(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        choice: str,
        *,
        tag: str = "",
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            _, case = self._source(c, state, viewer, identity)
            if state.revision != revision:
                raise WorkflowError("Reopen the exact original Isolation replacement.")
            event = str(uuid4())
            if choice == "order" and not tag:
                from girlframe.services.m3_ancillary_orders import AncillaryOrderService

                AncillaryOrderService(self.game).isolation_order(
                    c, state, case, _channel(state, identity), event
                )
            elif choice == "tag" and 0 < len(tag.strip()) <= 120:
                state = give_tag(
                    state,
                    case.subject,
                    case.executor,
                    tag.strip(),
                    event,
                    str(uuid4()),
                    (case.subject_controller, case.executor_controller),
                )
            elif choice != "pass" and not tag and choice in self._damage(c, state, case):
                state, work = damage(
                    state,
                    case.subject,
                    choice,
                    profiles(c, self.store.campaign_id),
                    event,
                    opponent=case.executor,
                )
                if work:
                    raise WorkflowError("Recover the actual required Asset consequence.")
            elif choice != "pass" or tag:
                raise WorkflowError("Choose exactly one actual permitted replacement or pass.")
            fact = next(x for x in state.facts if (x.get("kind"), x.get("id")) == (KIND, identity))
            if choice == "order":
                fact.update(order=event, choice=choice)
            else:
                fact.update(decided=event, choice=choice)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.chained_isolation_replacement",
                state,
                event_id=event,
                case_id=identity,
            )
            synchronize(self.game, c, None, event)
            return dict(id=identity, event=event)

        return self.store._write(
            viewer,
            key,
            "m3.chained_isolation_replacement",
            dict(id=identity, revision=revision, choice=choice, tag=tag),
            operation,
            authorize=lambda c: self._gate(c, viewer),
            auto_audit=False,
        )
