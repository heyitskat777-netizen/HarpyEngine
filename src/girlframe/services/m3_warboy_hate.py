"""Warboy's owned response to one actual newly imposed Helpless condition."""

import json
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_actor_plays as plays
from girlframe.engine import m3_ancillary as ancillary
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_bond_state import HelplessCondition
from girlframe.engine.m3_actor_state import ActorRef, Model
from girlframe.engine.m3_actors import resolve
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_ancillary import AncillaryService
from girlframe.services.m3_asset_loss import snapshots
from girlframe.services.m3_battle import _cast
from girlframe.services.m3_medical import MedicalService
from girlframe.services.m3_missions import MissionService
from girlframe.services.onboarding import WorkflowError
from girlframe.services.p1_facilitator import require_scene_clear
from girlframe.services.read_only_bot import GuildViewer

RULE = "ancillary.warboy.conditioned-hate"
KIND = "warboy_conditioned_hate"


class Response(Model):
    id: str
    original: HelplessCondition
    channel: int
    scene: str
    authority: int
    appointment: str
    owner: int
    tag: str
    account: str
    proposed: str
    decided: str | None = None
    accepted: bool | None = None


def records(state: GameState) -> tuple[Response, ...]:
    return tuple(
        Response.model_validate_json(x["body"]) for x in state.facts if x.get("kind") == KIND
    )


class ConditionedHateService:
    def __init__(self, game: GameService):
        self.game, self.store = game, game.store

    def _gate(self, c: Connection, viewer: GuildViewer) -> None:
        AncillaryService(MissionService(self.store))._access(c, viewer)
        gate = Access(self.store)
        gate.require_specialist_rule(RULE)
        assert gate.registry is not None
        gate.registry.require_available(ancillary.STARTERS["WARBOY"].rule)

    def _channel(self, c: Connection, event: str) -> int:
        source = c.execute(
            sa.select(t.events.c.payload_json).where(
                t.events.c.campaign_id == self.store.campaign_id,
                t.events.c.id == event,
            )
        ).scalar_one_or_none()
        meta = json.loads(source) if source else {}
        if meta.get("action_id"):
            action = self.game.action(c, meta["action_id"])
            scene_id = action["scene_id"]
        else:
            scene_id = meta.get("scene_id")
        if not scene_id:
            raise WorkflowError("Recover the actual scene of the new Helplessness")
        table = t.m2["m2_scenes"]
        channel = c.scalar(
            sa.select(table.c.channel_id).where(
                table.c.campaign_id == self.store.campaign_id,
                table.c.id == scene_id,
                table.c.open.is_(True),
            )
        )
        if channel is None:
            raise WorkflowError("The original Helplessness scene is unavailable")
        return int(channel)

    def _source(
        self,
        c: Connection,
        state: GameState,
        condition: HelplessCondition,
    ) -> tuple[int, str, int, str]:
        subject = condition.subject
        warboy = next(
            (
                x
                for x in ancillary.records(state)
                if x.actor == subject and x.draft.book == "WARBOY"
            ),
            None,
        )
        current = resolve(state, subject, (), require_current_profile=False)
        if (
            warboy is None
            or not condition.active
            or current.rules != "ancillary"
            or current.offstage_source
            or current.controller != warboy.controller
        ):
            raise WorkflowError("Use the actual original current Warboy and Helpless source")
        event = condition.source_events[0]
        channel = self._channel(c, event)
        before, started = snapshots(self.game, c, event)
        if any(x.id == condition.id for x in before.helpless_conditions) or not any(
            x.id == condition.id
            and x.active
            and x.subject == condition.subject
            and x.foe == condition.foe
            and x.source_events == (event,)
            for x in started.helpless_conditions
        ):
            raise WorkflowError("Only a genuine new Helpless condition can be countered")
        cast = _cast(self.game, c, state, channel)
        gm, appointment = MedicalService(self.store)._handler(c)
        people = {x.actor: x.controller for x in cast.roles}
        if (
            cast.facilitator != gm
            or people.get(subject) != current.controller
            or condition.foe not in people
        ):
            raise WorkflowError("Recover the original scene’s actual Warboy, opponent, and GM")
        return channel, cast.id, gm, appointment

    def _conditions(
        self,
        state: GameState,
        owner: int,
    ) -> tuple[HelplessCondition, ...]:
        actors = {
            x.actor
            for x in ancillary.records(state)
            if x.controller == owner and x.draft.book == "WARBOY"
        }
        recorded = {x.id for x in records(state)}
        return tuple(
            condition
            for condition in state.helpless_conditions
            if condition.active and condition.subject in actors and condition.id not in recorded
        )

    def tasks(
        self, c: Connection, state: GameState, viewer: GuildViewer
    ) -> tuple[tuple[str, str], ...]:
        upcoming = self._conditions(state, viewer.user_id)
        pending = tuple(
            x for x in records(state) if x.authority == viewer.user_id and x.decided is None
        )
        if not upcoming and not pending:
            return ()
        try:
            self._gate(c, viewer)
            current = MedicalService(self.store)._handler(c)
        except (ValueError, WorkflowError):
            return ()
        candidates = [(x.id, "review") for x in pending if (x.authority, x.appointment) == current]
        for condition in upcoming:
            try:
                self._source(c, state, condition)
            except (ValueError, WorkflowError):
                continue
            candidates.append((condition.id, "act"))
        return tuple(candidates)

    def _choice(
        self,
        state: GameState,
        viewer: GuildViewer,
        identity: str,
    ) -> tuple[HelplessCondition, Response | None]:
        case = next((x for x in records(state) if x.id == identity), None)
        if case is not None and case.authority == viewer.user_id and case.decided is None:
            return case.original, case
        condition = next(
            (x for x in self._conditions(state, viewer.user_id) if x.id == identity), None
        )
        if condition is None:
            raise WorkflowError("This original Warboy response is unavailable")
        return condition, None

    def get(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self._gate(c, viewer)
            state = load_state(c, self.store.campaign_id)
            condition, case = self._choice(state, viewer, identity)
            channel, scene, gm, appointment = self._source(c, state, condition)
            tags = _tags(state, condition.subject, scene)
            if case is not None:
                if (case.channel, case.scene, case.authority, case.appointment) != (
                    channel,
                    scene,
                    gm,
                    appointment,
                ):
                    raise WorkflowError(
                        "The original review belongs to its current source facilitator"
                    )
                if case.tag not in tags:
                    raise WorkflowError("This original Tag is no longer available for the response")
                return dict(
                    revision=state.revision,
                    review=True,
                    tag=tags[case.tag],
                    account=case.account,
                )
            return dict(revision=state.revision, review=False, tags=tags)

    def act(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        *,
        tag: str | None = None,
        account: str = "",
        verify: bool | None = None,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            condition, case = self._choice(state, viewer, identity)
            channel, scene, gm, appointment = self._source(c, state, condition)
            require_scene_clear(self.game, c, channel)
            if state.revision != revision:
                raise WorkflowError("STALE_CONDITIONED_HATE: reopen the original response")
            event = str(uuid4())
            tags = _tags(state, condition.subject, scene)
            if case is None:
                if (
                    tag is None
                    or tag not in tags
                    or verify is not None
                    or not 0 < len(account.strip()) <= 1200
                ):
                    raise WorkflowError("Choose your own available Tag and act to reaffirm it")
                case = Response(
                    id=identity,
                    original=condition,
                    channel=channel,
                    scene=scene,
                    authority=gm,
                    appointment=appointment,
                    owner=viewer.user_id,
                    tag=tag,
                    account=account.strip(),
                    proposed=event,
                )
                mutation = "proposed"
            else:
                previous = next(
                    (x for x in state.helpless_conditions if x.id == condition.id and x.active),
                    None,
                )
                if (
                    type(verify) is not bool
                    or tag is not None
                    or case.tag not in tags
                    or (case.channel, case.scene, case.authority, case.appointment)
                    != (channel, scene, gm, appointment)
                    or previous != condition
                ):
                    raise WorkflowError("Recover the same original condition, Tag, and scene")
                if verify:
                    plays.mark(state, condition.subject, case.tag, scene)
                    remaining = previous.source_events[1:]
                    changed = (
                        previous.model_copy(update=dict(source_events=remaining))
                        if remaining
                        else previous.model_copy(update=dict(active=False, recovery_event=event))
                    )
                    state.helpless_conditions = [
                        changed if x.id == previous.id else x for x in state.helpless_conditions
                    ]
                case = case.model_copy(update=dict(decided=event, accepted=verify))
                mutation = "reviewed"
            state.facts = [
                x for x in state.facts if (x.get("kind"), x.get("id")) != (KIND, identity)
            ]
            state.facts.append(dict(kind=KIND, id=identity, body=case.model_dump_json()))
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.conditioned_hate_" + mutation,
                state,
                event_id=event,
            )
            return dict(id=identity, state=mutation)

        def authorize(c: Connection) -> None:
            self._gate(c, viewer)
            state = load_state(c, self.store.campaign_id)
            case = next((x for x in records(state) if x.id == identity), None)
            if case is not None and (
                viewer.user_id not in (case.owner, case.authority)
                or viewer.user_id == case.authority
                and MedicalService(self.store)._handler(c) != (case.authority, case.appointment)
            ):
                raise WorkflowError("This original Warboy response is unavailable")

        try:
            return self.store._write(
                viewer,
                key,
                "m3.conditioned_hate",
                dict(id=identity, revision=revision, tag=tag, account=account, verify=verify),
                operation,
                authorize=authorize,
                auto_audit=False,
            )
        except ValueError as error:
            raise WorkflowError(str(error)) from None


def _tags(state: GameState, actor: ActorRef, scene: str) -> dict[str, str]:
    return {
        x.id: x.label
        for x in plays.tags(state, actor)
        if not x.marked and not x.rejection_pending and x.scene_used != scene
    }
