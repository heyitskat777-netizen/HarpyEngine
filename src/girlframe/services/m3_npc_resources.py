"""Source-backed private NPC treatment setup and proof; no automatic NPC baseline."""

from typing import TYPE_CHECKING, Any
from uuid import NAMESPACE_URL, uuid4, uuid5

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_npc_resources as rules
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef, ActorView
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_changeling import BodyFact
from girlframe.engine.m3_handler_consequences import active_handler
from girlframe.services.handler_setup import HandlerService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_actor_history import snapshot_profiles
from girlframe.services.m3_changeling_body import _fact
from girlframe.services.m3_dose_up import _cast
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer

if TYPE_CHECKING:
    from girlframe.services.m2_game import GameService


def _snapshot(game: "GameService", c: Connection, event: str) -> GameState:
    raw = c.scalar(
        sa.select(t.m2["m2_state_history"].c.body_json).where(
            t.m2["m2_state_history"].c.campaign_id == game.store.campaign_id,
            t.m2["m2_state_history"].c.event_id == event,
        )
    )
    if raw is None:
        raise WorkflowError("Recover the original NPC resource event and snapshot")
    return GameState.model_validate_json(raw)


def _body(
    game: "GameService", c: Connection, state: GameState, target: ActorRef
) -> tuple[ActorView, BodyFact]:
    actual = resolve(
        state,
        target,
        snapshot_profiles(c, game.store.campaign_id, state),
        require_current_profile=False,
    )
    npc = (
        next((x for x in state.world.npcs if x.id == target.entity), None) if state.world else None
    )
    body = _fact(game, c, state, target)
    if (
        target.kind != "npc"
        or npc is None
        or npc.source_kind is not None
        or actual.rules != "npc"
        or not actual.alive
        or body.reset_source
        or body.reset_record
        or body.kind not in ("human_npc", "other")
        or body.vessel != actual.vessel_id
    ):
        raise WorkflowError(
            "Use this living original physical NPC, not a reset or controller proxy"
        )
    return actual, body


def prove(
    game: "GameService",
    c: Connection,
    state: GameState,
    target: ActorRef,
    *,
    in_flight: str | None = None,
) -> rules.NpcResources:
    actual, body = _body(game, c, state, target)
    value = rules.current(state, target)
    if value is None:
        raise WorkflowError("NPC_RESOURCE_SETUP_REQUIRED: record witnessed NPC resources first")
    if (value.body_fact, value.body_event, value.brain, value.vessel) != (
        body.id,
        body.event,
        body.brain,
        body.vessel,
    ):
        raise WorkflowError(
            "Recover the same original NPC brain, vessel and factual resource source"
        )
    born = _snapshot(game, c, value.source_event)
    first = rules.current(born, target)
    row = (
        c.execute(
            sa.select(t.events).where(
                t.events.c.campaign_id == game.store.campaign_id,
                t.events.c.id == value.source_event,
            )
        )
        .mappings()
        .first()
    )
    stable = {"heat", "identities", "awards", "event"}
    if (
        first is None
        or row is None
        or row["kind"] != "m3.npc_resources_recorded"
        or row["actor_id"] != str(value.controller)
        or born.handler != value.controller
        or active_handler(born) != value.author
        or first.awards
        or first.model_dump(exclude=stable) != value.model_dump(exclude=stable)
        or tuple((x.id, x.name) for x in first.identities)
        != tuple((x.id, x.name) for x in value.identities)
    ):
        raise WorkflowError("Recover the original witnessed NPC resource birth and identity names")
    if value.event != in_flight and rules.current(_snapshot(game, c, value.event), target) != value:
        raise WorkflowError("Recover the latest actual NPC resource change")
    # Controller reassignment never reauthors the person or its inventory.
    if actual.controller <= 0:
        raise WorkflowError("Recover the actual current NPC human controller")
    return value


def award_heat(
    game: "GameService",
    c: Connection,
    state: GameState,
    target: ActorRef,
    amount: int,
    action: str,
    event: str,
) -> dict[str, Any]:
    """Apply one source-owned award to the witnessed NPC, preserving old records."""
    value = prove(game, c, state, target, in_flight=event)
    try:
        changed = rules.award(value, action, amount, event)
        rules.put(state, changed)
    except ValueError as exc:
        raise WorkflowError(str(exc)) from None
    return dict(printed_gain=amount, applied_gain=amount, resource=value.id)


def unmark_identity(
    game: "GameService",
    c: Connection,
    state: GameState,
    target: ActorRef,
    identity: str,
    event: str,
) -> None:
    """A rule-specific owner chooses one actual ordinary NPC Identity."""
    value = prove(game, c, state, target, in_flight=event)
    try:
        rules.put(state, rules.unmark(value, identity, event))
    except ValueError as exc:
        raise WorkflowError(str(exc)) from None


class NpcResourcesService:
    def __init__(self, game: "GameService"):
        self.game, self.store = game, game.store

    def _access(self, c: Connection, viewer: GuildViewer) -> None:
        Access(self.store).authorize(c, viewer, "plays", director_response=True)

    def menu(self, viewer: GuildViewer, channel: int) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self._access(c, viewer)
            state = load_state(c, self.store.campaign_id)
            scene = _cast(self.game, c, state, channel)
            result = []
            for role in scene.roles:
                if role.actor.kind != "npc":
                    continue
                try:
                    actual, _ = _body(self.game, c, state, role.actor)
                except (ValueError, WorkflowError):
                    continue
                value = rules.current(state, role.actor)
                permitted = viewer.user_id == actual.controller or (
                    value is not None and viewer.user_id in value.audience
                )
                if not permitted and viewer.user_id != state.handler:
                    continue
                if value is not None:
                    prove(self.game, c, state, role.actor)
                result.append(
                    dict(
                        ref=role.actor.model_dump(mode="json"),
                        token=role.actor.token,
                        label=actual.label,
                        recorded=value is not None,
                        may_record=viewer.user_id == state.handler and value is None,
                        may_view=permitted,
                    )
                )
            return dict(revision=state.revision, actors=result)

    def record(
        self,
        viewer: GuildViewer,
        key: str,
        expected: int,
        channel: int,
        target: ActorRef,
        heat: int,
        identities: tuple[tuple[str, bool], ...],
        account: str,
    ) -> dict[str, Any]:
        def authorize(c: Connection) -> None:
            self._access(c, viewer)
            HandlerService(self.store).authorize(c, viewer)
            self.game.unpaused(c)

        def operation(c: Connection) -> dict[str, Any]:
            state = load_state(c, self.store.campaign_id)
            if state.revision != expected:
                raise WorkflowError("STALE_NPC_RESOURCES: refresh the actual source scene")
            author = active_handler(state)
            if viewer.user_id != state.handler or author is None:
                raise WorkflowError(
                    "Only the current appointed Handler records witnessed NPC resources"
                )
            actual, body = _body(self.game, c, state, target)
            scene = _cast(self.game, c, state, channel)
            if not any(
                x.actor == target and x.controller == actual.controller for x in scene.roles
            ):
                raise WorkflowError(
                    "Join the actual NPC and its current controller to this source scene"
                )
            if rules.original(state, target) is not None:
                raise WorkflowError(
                    "The original NPC resource source is already recorded; do not reset it"
                )
            if not account.strip() or len(account) > 1200 or type(heat) is not int or heat < 0:
                raise WorkflowError(
                    "Record explicit existing Heat and a positive factual resource account"
                )
            event = str(uuid4())
            identity = str(uuid5(NAMESPACE_URL, "npc-resources:" + target.token + ":" + body.id))
            try:
                saved = rules.NpcResources(
                    id=identity,
                    actor=target,
                    body_fact=body.id,
                    body_event=body.event,
                    brain=body.brain,
                    vessel=body.vessel,
                    author=author,
                    controller=viewer.user_id,
                    audience=tuple(sorted({viewer.user_id, actual.controller})),
                    source_event=event,
                    account=account,
                    heat=heat,
                    identities=tuple(
                        rules.NpcIdentity(
                            id=str(uuid5(NAMESPACE_URL, identity + ":identity:" + str(i))),
                            name=name,
                            marked=marked,
                        )
                        for i, (name, marked) in enumerate(identities)
                    ),
                    event=event,
                )
            except ValueError as exc:
                raise WorkflowError(
                    "Use up to four explicitly witnessed ordinary NPC Identities"
                ) from exc
            rules.put(state, saved)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.npc_resources_recorded",
                state,
                event_id=event,
                resource_id=identity,
                patient=target.model_dump(mode="json"),
            )
            return dict(id=identity, game_revision=state.revision)

        return self.store._write(
            viewer,
            key,
            "m3.npc_resources_recorded",
            dict(
                expected=expected,
                channel=channel,
                target=target.model_dump(mode="json"),
                heat=heat,
                identities=identities,
                account=account,
            ),
            operation,
            auto_audit=False,
            authorize=authorize,
        )

    def view(self, viewer: GuildViewer, target: ActorRef) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self._access(c, viewer)
            state = load_state(c, self.store.campaign_id)
            actual, _ = _body(self.game, c, state, target)
            value = prove(self.game, c, state, target)
            if viewer.user_id != actual.controller and viewer.user_id not in value.audience:
                raise WorkflowError(
                    "Only the original resource witnesses and current NPC controller read this"
                )
            return dict(
                revision=state.revision, label=actual.label, resources=value.model_dump(mode="json")
            )
