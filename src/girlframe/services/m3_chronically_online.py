"""The Revolutionary's earlier knowledge becomes exact scoped Tags on meeting a Pilot."""

from collections.abc import Callable
from typing import Any, Literal
from uuid import uuid4

from sqlalchemy import Connection

from girlframe.engine import m3_ancillary as ancillary
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef, ActorView, CastRole, Model, SceneCast
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_cast import validate_role
from girlframe.engine.m3_harpy_defeat import give_tag
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_ancillary import AncillaryService
from girlframe.services.m3_battle import _cast
from girlframe.services.m3_consume_support import knowledge_allowed
from girlframe.services.m3_missions import MissionService
from girlframe.services.onboarding import WorkflowError
from girlframe.services.p1_facilitator import require_scene_clear
from girlframe.services.read_only_bot import GuildViewer

RULE = "ancillary.revolutionary-idealist.chronically-online"
KIND = "chronically_online"
Category = Literal["personnel", "combat", "childhood", "internet"]
LABELS: dict[Category, str] = {
    "personnel": "Personal and biographical facts",
    "combat": "Combat capabilities",
    "childhood": "Childhood",
    "internet": "Internet history",
}


class PriorFact(Model):
    category: Category
    text: str


class Recall(Model):
    id: str
    revolutionary: CastRole
    pilot: CastRole
    scene: str
    channel: int
    facts: tuple[PriorFact, PriorFact]
    source: str
    stage: Literal["confirm", "known", "meeting", "declined", "used"] = "confirm"
    verified: str | None = None
    encounter: str | None = None
    meeting: str | None = None


def records(state: GameState) -> tuple[Recall, ...]:
    return tuple(
        Recall.model_validate_json(x["body"]) for x in state.facts if x.get("kind") == KIND
    )


class ChronicallyOnlineService:
    def __init__(self, game: GameService):
        self.game, self.store = game, game.store

    def _gate(self, c: Connection, viewer: GuildViewer) -> None:
        AncillaryService(MissionService(self.store))._access(c, viewer)
        access = Access(self.store)
        access.require_specialist_rule(RULE)
        assert access.registry is not None
        access.registry.require_available(ancillary.STARTERS["REVOLUTIONARY IDEALIST"].rule)

    def _role(
        self,
        c: Connection,
        state: GameState,
        cast: SceneCast,
        actor: ActorRef,
    ) -> tuple[CastRole, ActorView]:
        actual = resolve(state, actor, profiles(c, self.store.campaign_id))
        role = validate_role(cast, actual)
        if (
            actual.cell is None
            or actual.offstage_source
            or actual.custody not in (None, "free", "converted")
            or not knowledge_allowed(state, actor)
        ):
            raise WorkflowError("Recover the available original scene participant.")
        return role, actual

    def _revolutionary(
        self,
        c: Connection,
        state: GameState,
        cast: SceneCast,
        actor: ActorRef,
    ) -> tuple[CastRole, ActorView]:
        role, actual = self._role(c, state, cast, actor)
        original = ancillary.find(state, actor)
        if original is None or original.draft.book != "REVOLUTIONARY IDEALIST":
            raise WorkflowError("Use the actual original Revolutionary Idealist.")
        return role, actual

    def _pair(
        self,
        c: Connection,
        state: GameState,
        recall: Recall,
    ) -> tuple[ActorView, ActorView]:
        cast = _cast(self.game, c, state, recall.channel)
        first, revolutionary = self._revolutionary(c, state, cast, recall.revolutionary.actor)
        second, pilot = self._role(c, state, cast, recall.pilot.actor)
        if (
            cast.id != recall.scene
            or first != recall.revolutionary
            or second != recall.pilot
            or pilot.rules != "girl_frame"
            or pilot.controller == revolutionary.controller
        ):
            raise WorkflowError("Recover the original cast for these facts.")
        return revolutionary, pilot

    def options(
        self,
        c: Connection,
        state: GameState,
        viewer: GuildViewer,
        channel: int,
        actor: ActorRef,
    ) -> dict[str, str]:
        self._gate(c, viewer)
        cast = _cast(self.game, c, state, channel)
        role, actual = self._revolutionary(c, state, cast, actor)
        if role.controller != viewer.user_id:
            raise WorkflowError("Only the original Revolutionary recalls her own facts.")
        pending = {
            x.pilot.actor
            for x in records(state)
            if x.revolutionary.actor == actor and x.stage in ("known", "confirm", "meeting", "used")
        }
        people = {}
        for member in cast.roles:
            if (
                member.actor.kind != "pilot"
                or member.controller == actual.controller
                or member.actor in pending
            ):
                continue
            try:
                _, pilot = self._role(c, state, cast, member.actor)
            except (WorkflowError, ValueError):
                continue
            if pilot.rules == "girl_frame" and pilot.cell != actual.cell:
                people[pilot.ref.token] = pilot.label
        return people

    def menu(self, viewer: GuildViewer, channel: int, actor: ActorRef) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            state = load_state(c, self.store.campaign_id)
            people = self.options(c, state, viewer, channel, actor)
            return dict(revision=state.revision, people=people)

    def _save(
        self,
        c: Connection,
        state: GameState,
        viewer: GuildViewer,
        key: str,
        recall: Recall,
        event: str,
    ) -> dict[str, Any]:
        state.facts = [x for x in state.facts if (x.get("kind"), x.get("id")) != (KIND, recall.id)]
        state.facts.append(dict(kind=KIND, id=recall.id, body=recall.model_dump_json()))
        self.game.event(
            c,
            viewer.user_id,
            key,
            "m3.chronically_online_" + recall.stage,
            state,
            event_id=event,
            scene_id=recall.scene,
        )
        return dict(id=recall.id, stage=recall.stage, event=event)

    def _write(
        self,
        viewer: GuildViewer,
        key: str,
        payload: dict[str, Any],
        operation: Callable[[Connection], dict[str, Any]],
    ) -> dict[str, Any]:
        try:
            return self.store._write(
                viewer,
                key,
                "m3.chronically_online",
                payload,
                operation,
                authorize=lambda c: self._gate(c, viewer),
                auto_audit=False,
            )
        except ValueError as error:
            raise WorkflowError(str(error)) from None

    def propose(
        self,
        viewer: GuildViewer,
        key: str,
        channel: int,
        actor: ActorRef,
        revision: int,
        target: str,
        facts: tuple[PriorFact, PriorFact],
        source: str,
    ) -> dict[str, Any]:
        facts = (
            PriorFact.model_validate_json(facts[0].model_dump_json()),
            PriorFact.model_validate_json(facts[1].model_dump_json()),
        )
        if (
            facts[0].category == facts[1].category
            or not source.strip()
            or len(source) > 1200
            or any(not x.text.strip() or len(x.text.strip()) > 120 for x in facts)
        ):
            raise WorkflowError("Record two distinct known categories and their earlier evidence.")

        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            require_scene_clear(self.game, c, channel)
            state = load_state(c, self.store.campaign_id)
            if state.revision != revision or target not in self.options(
                c, state, viewer, channel, actor
            ):
                raise WorkflowError("STALE_RECALL: reopen the existing scene before meeting.")
            cast = _cast(self.game, c, state, channel)
            role, _ = self._revolutionary(c, state, cast, actor)
            pilot = next(x for x in cast.roles if x.actor.token == target)
            event = str(uuid4())
            value = Recall(
                id=event,
                revolutionary=role,
                pilot=pilot,
                scene=cast.id,
                channel=channel,
                facts=facts,
                source=source.strip(),
            )
            return self._save(c, state, viewer, key, value, event)

        return self._write(
            viewer,
            key,
            dict(
                channel=channel,
                actor=actor.token,
                revision=revision,
                target=target,
                source=source,
                facts=[x.model_dump(mode="json") for x in facts],
            ),
            operation,
        )

    def _required(
        self,
        c: Connection,
        state: GameState,
        viewer: GuildViewer,
        value: Recall,
    ) -> str:
        verify = value.stage == "confirm" and value.pilot.controller == viewer.user_id
        use = value.stage == "known" and value.revolutionary.controller == viewer.user_id
        accepts = value.stage == "meeting" and value.pilot.controller == viewer.user_id
        if not verify and not use and not accepts:
            raise WorkflowError("This original private recollection is unavailable.")
        first, second = self._pair(c, state, value)
        if verify and first.cell != second.cell:
            return "confirm"
        if first.cell == second.cell and value.verified is not None:
            if use:
                return "meet"
            if accepts and value.encounter is not None:
                return "encounter"
        raise WorkflowError("This original recollection is unavailable at the current positions.")

    def _find(self, state: GameState, identity: str) -> Recall:
        value = next((x for x in records(state) if x.id == identity), None)
        if value is None:
            raise WorkflowError("This original private recollection is unavailable.")
        return value

    def tasks(
        self,
        c: Connection,
        state: GameState,
        viewer: GuildViewer,
    ) -> tuple[tuple[str, str], ...]:
        candidates = tuple(
            x
            for x in records(state)
            if x.stage in ("confirm", "meeting")
            and x.pilot.controller == viewer.user_id
            or x.stage == "known"
            and x.revolutionary.controller == viewer.user_id
        )
        if not candidates:
            return ()
        try:
            self._gate(c, viewer)
        except (ValueError, WorkflowError):
            return ()
        result = []
        for value in candidates:
            try:
                result.append((value.id, self._required(c, state, viewer, value)))
            except (ValueError, WorkflowError):
                continue
        return tuple(result)

    def get(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self._gate(c, viewer)
            state = load_state(c, self.store.campaign_id)
            value = self._find(state, identity)
            step = self._required(c, state, viewer, value)
            return dict(revision=state.revision, step=step, facts=value.facts, source=value.source)

    def act(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        choice: str,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            value = self._find(state, identity)
            step = self._required(c, state, viewer, value)
            require_scene_clear(self.game, c, value.channel)
            if state.revision != revision:
                raise WorkflowError("STALE_RECALL: reopen the original private recollection.")
            event = str(uuid4())
            if step == "confirm" and choice in ("yes", "no"):
                value = value.model_copy(
                    update=dict(
                        stage="known" if choice == "yes" else "declined",
                        verified=event if choice == "yes" else None,
                    )
                )
            elif step == "meet" and choice == "met":
                value = value.model_copy(update=dict(stage="meeting", encounter=event))
            elif step == "encounter" and choice == "no":
                value = value.model_copy(update=dict(stage="known", encounter=None))
            elif step == "encounter" and choice == "apply":
                recipients = (value.revolutionary.controller, value.pilot.controller)
                for fact in value.facts:
                    state = give_tag(
                        state,
                        value.pilot.actor,
                        value.revolutionary.actor,
                        fact.text.strip(),
                        event,
                        str(uuid4()),
                        recipients,
                    )
                value = value.model_copy(update=dict(stage="used", meeting=event))
            else:
                raise WorkflowError("Use the original participant's private choice.")
            return self._save(c, state, viewer, key, value, event)

        return self._write(
            viewer, key, dict(id=identity, revision=revision, choice=choice), operation
        )
