"""The private voice source behind a normal, human-owned Receive Orders response."""

import json
from typing import TYPE_CHECKING, Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_rebel_voice as rules
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef, SceneCast
from girlframe.engine.m3_handler_consequences import active_handler, same_handler_body
from girlframe.engine.m3_rebel_escape_offer import speaker
from girlframe.services.handler_setup import HandlerService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_strain import StrainService
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer

if TYPE_CHECKING:
    from girlframe.services.m2_game import GameService

EVENT = "m3.rebel_voice_synthesized"


def stage(
    c: Connection,
    strain: StrainService,
    state: GameState,
    row: dict[str, Any],
    event: str,
    npc: str | None,
) -> None:
    issuer = speaker(state, npc)
    handler = active_handler(state)
    period = strain.periods._get(c, row["off_duty_id"])
    girls = tuple(current_ref(state, uid) for uid in period.pilots)
    if (
        not girls
        or handler is None
        or handler.entity != row["owner_id"]
        or any(period.character_ids.get(x.entity) != x.incarnation for x in girls)
        or not HandlerService(strain.store)._member(c, issuer.controller)
        or any(x.id == row["id"] for x in rules.voices(state))
    ):
        raise WorkflowError("Recover the real original Handler voice, Cadre and Rebel controller")
    rules.save(
        state,
        rules.Voice(
            id=row["id"],
            source=event,
            handler=handler,
            issuer=ActorRef(kind="npc", entity=issuer.id),
            controller=issuer.controller,
            girls=girls,
        ),
    )


def _current(
    game: "GameService", c: Connection, state: GameState, identity: str, controller: int
) -> rules.Voice:
    value = next((x for x in rules.voices(state) if x.id == identity), None)
    if (
        value is None
        or value.controller != controller
        or not same_handler_body(state, value.handler)
        or not HandlerService(game.store)._member(c, controller)
    ):
        raise WorkflowError("The original separate Rebel controller owns this voice source")
    try:
        actual = speaker(state, value.issuer.entity)
    except ValueError as error:
        raise WorkflowError(str(error)) from None
    if actual.controller != controller:
        raise WorkflowError("The original separate Rebel controller owns this voice source")
    return value


def authority(
    game: "GameService",
    c: Connection,
    state: GameState,
    identity: str,
    controller: int,
    issuer: ActorRef,
    girl: ActorRef,
) -> rules.Voice:
    value = _current(game, c, state, identity, controller)
    if (
        value.prepared is None
        or issuer != value.issuer
        or girl not in value.girls
        or girl != current_ref(state, int(girl.entity))
        or girl.entity == str(controller)
    ):
        raise WorkflowError("Use the synthesized voice for one of its actual original Cadre Girls")
    history = t.m2["m2_state_history"]
    raw = c.scalar(
        sa.select(history.c.body_json)
        .join(
            t.events,
            (t.events.c.campaign_id == history.c.campaign_id)
            & (t.events.c.id == history.c.event_id),
        )
        .where(
            history.c.campaign_id == game.store.campaign_id,
            history.c.event_id == value.prepared,
            t.events.c.kind == EVENT,
            t.events.c.actor_id == str(controller),
        )
    )
    original = GameState.model_validate_json(raw) if raw else None
    if original is None or value not in rules.voices(original):
        raise WorkflowError("Recover this voice's actual immutable synthesis")
    return value


class VoiceService:
    def __init__(self, strain: StrainService):
        self.strain, self.store, self.game = strain, strain.store, strain.game

    def _access(self, c: Connection, viewer: GuildViewer, *, read: bool = False) -> None:
        if read:
            self.game.authorize(c, viewer, game=False)
        else:
            from girlframe.services.m3_npc_orders import _access as order_access

            try:
                order_access(self.game, c, viewer, "rebel_voice")
            except ValueError as error:
                raise WorkflowError(str(error)) from None
            self.game.unpaused(c)

    def get(self, viewer: GuildViewer, identity: str, channel: int) -> dict[str, Any]:
        from girlframe.services.m3_enforcement_initiative import _cast

        with self.store.engine.connect() as c:
            self._access(c, viewer, read=True)
            state = load_state(c, self.store.campaign_id)
            value = _current(self.game, c, state, identity, viewer.user_id)
            cast: SceneCast | None = None
            if value.prepared:
                try:
                    if viewer.user_id in self.game.scene(c, channel)["participants"]:
                        cast = _cast(self.game, c, state, channel)
                except WorkflowError:
                    pass
            girls = (
                tuple(
                    (x.actor.entity, state.sheets[x.actor.entity].callsign)
                    for x in cast.roles
                    if x.actor in value.girls
                    and x.controller != viewer.user_id
                    and x.actor == current_ref(state, x.controller)
                )
                if cast
                else ()
            )
            return dict(
                revision=state.revision,
                ready=value.prepared is not None,
                girls=girls,
                issuer=value.issuer,
            )

    def synthesize(
        self, viewer: GuildViewer, key: str, identity: str, expected: int, account: str
    ) -> dict[str, Any]:
        if not account.strip() or len(account) > 1200:
            raise WorkflowError("Record how the original Rebel makes the voice")

        def operation(c: Connection) -> dict[str, Any]:
            from girlframe.services.m3_strain_effects import EffectService

            state = self.strain._state(c, expected)
            value = _current(self.game, c, state, identity, viewer.user_id)
            row = EffectService(self.strain)._row(c, identity)
            body = json.loads(row["body_json"])
            if (
                value.prepared
                or row["state"] != "pending"
                or row["event_id"] != value.source
                or body.get("rule_id") != rules.RULE
                or body.get("voice_requested") != value.source
            ):
                raise WorkflowError("Reopen the original unsynthesized voice source")
            event = str(uuid4())
            rules.save(state, value.model_copy(update={"prepared": event}))
            state.facts.append(
                dict(kind="rebel_voice_account", id=identity, event=event, account=account.strip())
            )
            self.game.event(c, viewer.user_id, key, EVENT, state, event_id=event, work_id=identity)
            self.strain._save(c, row, event, body | {"voice_synthesized": event}, resolved=True)
            return dict(id=identity, state="resolved")

        return self.store._write(
            viewer,
            key,
            EVENT,
            dict(id=identity, expected=expected, account=account),
            operation,
            auto_audit=False,
            authorize=lambda c: self._access(c, viewer),
        )
