"""Private radio song and the original Girl's actual physical response."""

from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_bonds import change, depth
from girlframe.engine.m3_actor_state import ActorRef, ActorView, Model, SceneCast
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_harpy_advancements import SONG_OF_LOVE_LOST
from girlframe.engine.m3_world_state import Cell
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_battle import _cast
from girlframe.services.m3_harpy_advancements import scene_harpy
from girlframe.services.m3_jackdaw import require_audible
from girlframe.services.m3_movement import apply_reviewed_movement, proposal_context
from girlframe.services.onboarding import WorkflowError
from girlframe.services.p1_facilitator import require_scene_clear
from girlframe.services.read_only_bot import GuildViewer

KIND = "harpy_song"


class Song(Model):
    id: str
    scene: str
    channel: int
    source: ActorRef
    controller: int
    advancement: str
    girl: ActorRef
    location: Cell
    account: str
    response: str | None = None
    moved: bool = False


def records(state: GameState) -> tuple[Song, ...]:
    return tuple(Song.model_validate_json(x["body"]) for x in state.facts if x.get("kind") == KIND)


class HarpySongService:
    def __init__(self, game: GameService):
        self.game, self.store = game, game.store

    def _gate(self, c: Connection, viewer: GuildViewer) -> None:
        access = Access(self.store)
        access.authorize(c, viewer, "plays", director_response=True)
        access.authorize(c, viewer, "world", director_response=True)
        access.require_specialist_rule(SONG_OF_LOVE_LOST)

    def _targets(
        self,
        c: Connection,
        state: GameState,
        cast: SceneCast,
        source: ActorView,
    ) -> dict[str, ActorView]:
        assert source.cell is not None
        result = {}
        bound = profiles(c, self.store.campaign_id)
        for role in cast.roles:
            if role.actor.kind != "pilot":
                continue
            girl = resolve(state, role.actor, bound, require_current_profile=False)
            if (
                girl.rules != "girl_frame"
                or not girl.alive
                or girl.controller != role.controller
                or girl.offstage_source
                or girl.inside_frame is not False
                or girl.cell is None
                or girl.custody not in (None, "free")
                or depth(state, source.ref, girl.ref) != 0
                or not 0 < max(abs(a - b) for a, b in zip(source.cell, girl.cell, strict=True)) <= 1
            ):
                continue
            try:
                require_audible(c, self.store.campaign_id, state, (source, girl))
            except WorkflowError:
                continue
            result[girl.ref.token] = girl
        return result

    def options(self, viewer: GuildViewer, channel: int, actor: ActorRef) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self._gate(c, viewer)
            state = load_state(c, self.store.campaign_id)
            cast = _cast(self.game, c, state, channel)
            source, _ = scene_harpy(
                self.game, c, state, viewer.user_id, cast, actor, SONG_OF_LOVE_LOST
            )
            return dict(
                revision=state.revision,
                targets={
                    key: view.label for key, view in self._targets(c, state, cast, source).items()
                },
            )

    def act(
        self,
        viewer: GuildViewer,
        key: str,
        channel: int,
        actor: ActorRef,
        revision: int,
        target: str,
        account: str,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            require_scene_clear(self.game, c, channel)
            lock = self.game.lock(c, channel)
            if lock and lock["state"] != "released":
                raise WorkflowError("Finish the original held scene Play before broadcasting")
            state = load_state(c, self.store.campaign_id)
            if revision != state.revision:
                raise WorkflowError("STALE_HARPY_SONG: reopen the original broadcast")
            cast = _cast(self.game, c, state, channel)
            source, advancement = scene_harpy(
                self.game, c, state, viewer.user_id, cast, actor, SONG_OF_LOVE_LOST
            )
            girl = self._targets(c, state, cast, source).get(target)
            if girl is None or not 0 < len(account.strip()) <= 1200:
                raise WorkflowError(
                    "Choose an actual audible Girl with no Bond and describe the song"
                )
            if any(
                x.source == actor and x.girl == girl.ref and not x.response for x in records(state)
            ):
                raise WorkflowError("Recover the original outstanding Harpy song")
            assert source.cell is not None
            entry = Song(
                id=str(uuid4()),
                scene=cast.id,
                channel=channel,
                source=actor,
                controller=source.controller,
                girl=girl.ref,
                location=source.cell,
                advancement=advancement,
                account=account.strip(),
            )
            state.facts.append(dict(kind=KIND, id=entry.id, body=entry.model_dump_json()))
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.harpy_song_offered",
                state,
                event_id=entry.id,
                scene=cast.id,
            )
            return dict(id=entry.id, state="awaiting_girl")

        return self.store._write(
            viewer,
            key,
            "m3.harpy_song_offered",
            dict(
                actor=actor.model_dump(mode="json"),
                channel=channel,
                revision=revision,
                target=target,
                account=account,
            ),
            operation,
            authorize=lambda c: self._gate(c, viewer),
            auto_audit=False,
        )

    def _owned(self, c: Connection, state: GameState, viewer: GuildViewer, identity: str) -> Song:
        case = next((x for x in records(state) if x.id == identity), None)
        if case is None or case.girl.entity != str(viewer.user_id) or case.response is not None:
            raise WorkflowError("This private Harpy song is unavailable")
        sheet = state.sheets.get(case.girl.entity)
        if sheet is None or sheet.character_id != case.girl.incarnation:
            raise WorkflowError("Use the actual original recipient of the radio song")
        history = t.m2["m2_state_history"]
        raw = c.scalar(
            sa.select(history.c.body_json)
            .join(t.events, t.events.c.id == history.c.event_id)
            .where(
                history.c.campaign_id == self.store.campaign_id,
                t.events.c.campaign_id == self.store.campaign_id,
                t.events.c.id == case.id,
                t.events.c.kind == "m3.harpy_song_offered",
                t.events.c.actor_id == str(case.controller),
            )
        )
        if raw is None or case not in records(GameState.model_validate_json(raw)):
            raise WorkflowError("Recover the actual source Harpy and original broadcast")
        return case

    def tasks(self, c: Connection, state: GameState, viewer: GuildViewer) -> tuple[Song, ...]:
        cases = tuple(
            x
            for x in records(state)
            if x.girl.entity == str(viewer.user_id)
            and not x.response
            and (sheet := state.sheets.get(x.girl.entity)) is not None
            and sheet.character_id == x.girl.incarnation
        )
        if cases:
            try:
                self._gate(c, viewer)
            except (ValueError, WorkflowError):
                return ()
        return cases

    def get(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self._gate(c, viewer)
            state = load_state(c, self.store.campaign_id)
            case = self._owned(c, state, viewer, identity)
            return dict(revision=state.revision, account=case.account)

    def respond(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        *,
        accept: bool,
        account: str,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            case = self._owned(c, state, viewer, identity)
            if state.revision != revision or (type(accept) is not bool):
                raise WorkflowError("STALE_HARPY_SONG: reopen your original decision")
            event = str(uuid4())
            if accept:
                cast = _cast(self.game, c, state, case.channel)
                source, receipt = scene_harpy(
                    self.game,
                    c,
                    state,
                    case.controller,
                    cast,
                    case.source,
                    SONG_OF_LOVE_LOST,
                )
                if (
                    cast.id != case.scene
                    or source.cell != case.location
                    or receipt != case.advancement
                    or case.girl.token not in self._targets(c, state, cast, source)
                ):
                    raise WorkflowError("Recover the actual original Harpy, Girl and radio reach")
                context = proposal_context(
                    self.game,
                    c,
                    viewer,
                    state,
                    case.channel,
                    case.girl,
                    case.location,
                    False,
                    account,
                )
                apply_reviewed_movement(self.game, c, viewer, state, context, event)
                state = change(state, case.source, case.girl, 1, event)
            current = case.model_copy(update=dict(response=event, moved=accept))
            state.facts = [
                x for x in state.facts if (x.get("kind"), x.get("id")) != (KIND, identity)
            ]
            state.facts.append(dict(kind=KIND, id=identity, body=current.model_dump_json()))
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.harpy_song_responded",
                state,
                event_id=event,
                source=identity,
                accepted=accept,
            )
            return dict(event=event, accepted=accept)

        return self.store._write(
            viewer,
            key,
            "m3.harpy_song_responded",
            dict(id=identity, revision=revision, accept=accept, account=account),
            operation,
            authorize=lambda c: self._gate(c, viewer),
            auto_audit=False,
        )
