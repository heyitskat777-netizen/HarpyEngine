"""An original Ancillary Cadre Handler's source-proved social Punishment."""

from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_ancillary_cadre as rank
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_bonds import make_helpless
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_ancillary import find
from girlframe.engine.m3_handler_consequences import active_handler
from girlframe.engine.m3_role_punishment_state import RolePunishment
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_ancillary import AncillaryService
from girlframe.services.m3_battle import _cast
from girlframe.services.m3_missions import MissionService
from girlframe.services.onboarding import WorkflowError
from girlframe.services.p1_facilitator import require_scene_clear
from girlframe.services.read_only_bot import GuildViewer

EARNED = "ancillary.prodigy.earned-confidence"
FAVOURITE = "ancillary.prodigy.the-favourite"
KIND = "prodigy_confidence"
SCOPE = "ancillary_punishment_source"
ROLL_CHOICE = "prodigy_confidence_roll"


def _approved(game: GameService, rule: str) -> bool:
    try:
        Access(game.store).require_specialist_rule(rule)
    except (WorkflowError, ValueError):
        return False
    return True


def _is_prodigy(state: GameState, actor: ActorRef) -> bool:
    original = find(state, actor)
    return original is not None and original.draft.book == "PRODIGY"


def immune(game: GameService, state: GameState, cadre: rank.Cadre, subject: ActorRef) -> bool:
    return (
        _approved(game, FAVOURITE)
        and _is_prodigy(state, subject)
        and rank.actual_members(state, cadre)[0] == subject
    )


def _notches(
    game: GameService, state: GameState, actor: ActorRef, owner: int, *, ace: bool
) -> tuple[str, ...]:
    body = find(state, actor)
    cadre = rank.current(state, actor)
    if (
        body is None
        or cadre is None
        or body.controller != owner
        or body.draft.book != "PRODIGY"
        or (rank.actual_members(state, cadre)[0] == actor) != ace
        or not _approved(game, EARNED)
    ):
        return ()
    return tuple(
        x["id"]
        for x in state.facts
        if x.get("kind") == KIND
        and x.get("actor") == actor.token
        and x.get("cadre") == cadre.id
        and not x.get("spent")
    )


def roll_notches(
    game: GameService, state: GameState, actor: ActorRef, owner: int
) -> tuple[str, ...]:
    return _notches(game, state, actor, owner, ace=True)


def spend_roll_notch(
    game: GameService,
    state: GameState,
    actor: ActorRef,
    owner: int,
    identity: str,
    action: str,
    event: str,
) -> None:
    if identity not in roll_notches(game, state, actor, owner):
        raise WorkflowError("Choose your original unspent notch while you are the current Ace.")
    notch = next(x for x in state.facts if x.get("kind") == KIND and x.get("id") == identity)
    notch.update(spent=event, roll=action)


def _authority(
    game: GameService,
    c: Connection,
    state: GameState,
    cadre: rank.Cadre,
    channel: int,
    subject: ActorRef,
) -> None:
    cast = _cast(game, c, state, channel)
    if not any(x.actor == subject for x in cast.roles):
        raise WorkflowError("Recover the actual original punishment scene and subject.")
    current = rank.current(state, subject)
    if current is None or current.id != cadre.id or current.handler != cadre.handler:
        raise WorkflowError("Recover the original actual Ancillary Cadre appointment.")
    if cadre.handler.kind == "handler":
        if active_handler(state) != cadre.handler or cast.facilitator != cadre.handler_owner:
            raise WorkflowError("Recover the original actual Foundation Handler role.")
    else:
        body = resolve(state, cadre.handler, profiles(c, game.store.campaign_id))
        if (
            body.controller != cadre.handler_owner
            or "handler" not in body.jobs
            or not any(
                x.actor == cadre.handler and x.controller == body.controller for x in cast.roles
            )
        ):
            raise WorkflowError("Recover the original cast Rebel Handler role.")
    if immune(game, state, cadre, subject):
        raise WorkflowError("The actual Handler cannot Punish their Ace under The Favourite.")


def prove_case(
    game: GameService,
    c: Connection,
    state: GameState,
    case: RolePunishment,
) -> None:
    original = next(
        (x for x in state.facts if x.get("kind") == SCOPE and x.get("id") == case.id),
        None,
    )
    if original is None or original.get("event") != case.source_event:
        raise WorkflowError("Recover the actual original Ancillary Punishment source.")
    cadre = rank.current(state, case.subject)
    if cadre is None or cadre.id != case.source_work or cadre.handler != case.executor:
        raise WorkflowError("Recover the actual original Ancillary Punishment authority.")
    if not c.scalar(
        sa.select(t.events.c.id).where(
            t.events.c.campaign_id == game.store.campaign_id,
            t.events.c.id == case.source_event,
            t.events.c.kind == "m3.ancillary_punishment_started",
            t.events.c.actor_id == str(case.executor_controller),
        )
    ):
        raise WorkflowError("Recover the actual original Handler's instruction source.")
    _authority(game, c, state, cadre, int(original["channel"]), case.subject)


def applied_consequences(
    game: GameService,
    state: GameState,
    case: RolePunishment,
    event: str,
) -> GameState:
    if _approved(game, FAVOURITE) and _is_prodigy(state, case.subject):
        state = make_helpless(state, case.subject, case.executor, event)
    cadre = rank.current(state, case.subject)
    if cadre is not None and _approved(game, EARNED):
        for actor in rank.actual_members(state, cadre):
            if actor != case.subject and _is_prodigy(state, actor):
                state.facts.append(
                    dict(
                        kind=KIND,
                        id=case.id + ":" + actor.token,
                        actor=actor.token,
                        source=case.id,
                        event=event,
                        cadre=cadre.id,
                    )
                )
    return state


class AncillaryDisciplineService:
    def __init__(self, game: GameService):
        self.game, self.store = game, game.store

    def _gate(self, c: Connection, viewer: GuildViewer) -> None:
        AncillaryService(MissionService(self.store))._access(c, viewer)
        Access(self.store).authorize(c, viewer, "discipline")

    def options(
        self,
        c: Connection,
        state: GameState,
        viewer: GuildViewer,
        channel: int,
    ) -> dict[str, str]:
        self._gate(c, viewer)
        result = {}
        for cadre in rank.records(state):
            if cadre.state != "active" or cadre.handler_owner != viewer.user_id:
                continue
            for actor in rank.actual_members(state, cadre):
                try:
                    _authority(self.game, c, state, cadre, channel, actor)
                    current = resolve(state, actor, profiles(c, self.store.campaign_id))
                except (ValueError, WorkflowError):
                    continue
                if not any(
                    x.source_kind == "ancillary_cadre"
                    and x.subject == actor
                    and x.completion_event is None
                    for x in state.role_punishments
                ):
                    result[actor.token] = current.label
        return result

    def menu(self, viewer: GuildViewer, channel: int) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            state = load_state(c, self.store.campaign_id)
            return dict(revision=state.revision, people=self.options(c, state, viewer, channel))

    def start(
        self,
        viewer: GuildViewer,
        key: str,
        channel: int,
        revision: int,
        target: str,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            require_scene_clear(self.game, c, channel)
            state = load_state(c, self.store.campaign_id)
            if state.revision != revision or target not in self.options(c, state, viewer, channel):
                raise WorkflowError("Choose a current original eligible member of your Cadre.")
            cast = _cast(self.game, c, state, channel)
            ref = next(x.actor for x in cast.roles if x.actor.token == target)
            cadre = rank.current(state, ref)
            assert cadre is not None
            identity, event = str(uuid4()), str(uuid4())
            from girlframe.services.m3_role_punishments import open_case

            state, _ = open_case(
                state,
                profiles(c, self.store.campaign_id),
                actor=cadre.handler,
                target=ref,
                chooser=cadre.handler,
                source_kind="ancillary_cadre",
                action=None,
                source_work=cadre.id,
                source_event=event,
                identity=identity,
            )
            state.facts.append(dict(kind=SCOPE, id=identity, channel=str(channel), event=event))
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.ancillary_punishment_started",
                state,
                event_id=event,
                scene_id=cast.id,
                case_id=identity,
            )
            return dict(id=identity, event=event)

        return self.store._write(
            viewer,
            key,
            "m3.ancillary_punishment_started",
            dict(channel=channel, revision=revision, target=target),
            operation,
            authorize=lambda c: self._gate(c, viewer),
            auto_audit=False,
        )

    def confidence(
        self,
        c: Connection,
        state: GameState,
        viewer: GuildViewer,
        actor: ActorRef,
    ) -> tuple[str, ...]:
        self._gate(c, viewer)
        return _notches(self.game, state, actor, viewer.user_id, ace=False)

    def confidence_menu(self, viewer: GuildViewer, actor: ActorRef) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            state = load_state(c, self.store.campaign_id)
            return dict(revision=state.revision, owned=self.confidence(c, state, viewer, actor))

    def spend(
        self,
        viewer: GuildViewer,
        key: str,
        actor: ActorRef,
        identity: str,
        revision: int,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            if state.revision != revision or identity not in self.confidence(
                c, state, viewer, actor
            ):
                raise WorkflowError("Reopen your original unspent confidence and current Status.")
            event = str(uuid4())
            if not rank.shift(state, actor, -1, event):
                raise WorkflowError("Choose an actual available Status change.")
            notch = next(
                x for x in state.facts if x.get("kind") == KIND and x.get("id") == identity
            )
            notch["spent"] = event
            self.game.event(
                c, viewer.user_id, key, "m3.prodigy_confidence_spent", state, event_id=event
            )
            return dict(id=identity, event=event)

        return self.store._write(
            viewer,
            key,
            "m3.prodigy_confidence_spent",
            dict(actor=actor.token, id=identity, revision=revision),
            operation,
            authorize=lambda c: self._gate(c, viewer),
            auto_audit=False,
        )
