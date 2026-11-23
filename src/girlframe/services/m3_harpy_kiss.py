"""Kiss Me, Darling tied to an actual original Harpy Play and verified surprise."""

import json
from typing import Any, Literal
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_bonds import depth
from girlframe.engine.m3_actor_state import ActorRef, ActorView, Model, SceneCast
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_harpy_advancements import KISS
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_harpy_advancements import scene_harpy
from girlframe.services.m3_harpy_intimacy import Encounter, HarpyIntimacyService, put
from girlframe.services.m3_harpy_intimacy import records as intimacy_records
from girlframe.services.m3_medical import MedicalService
from girlframe.services.onboarding import WorkflowError
from girlframe.services.p1_facilitator import require_scene_clear
from girlframe.services.read_only_bot import GuildViewer

KIND = "harpy_kiss"


class Surprise(Model):
    id: str
    action: str
    scene: str
    channel: int
    harpy: ActorRef
    controller: int
    girl: ActorRef
    gm: int
    appointment: str
    advancement: str
    choice: Literal["kiss", "linger"]
    account: str
    answer: bool | None = None
    reviewed: str | None = None
    encounter: str | None = None


def records(state: GameState) -> tuple[Surprise, ...]:
    return tuple(
        Surprise.model_validate_json(x["body"]) for x in state.facts if x.get("kind") == KIND
    )


class KissService:
    def __init__(self, game: GameService):
        self.game, self.store = game, game.store
        self.intimacy = HarpyIntimacyService(game)

    def _gate(self, c: Connection, viewer: GuildViewer) -> None:
        gate = Access(self.store)
        gate.authorize(c, viewer, "plays", director_response=True)
        gate.require_specialist_rule(KISS)

    def _action(
        self,
        c: Connection,
        action: dict[str, Any],
        cast: SceneCast,
        source: ActorView,
        people: dict[str, ActorView],
        advancement: str,
    ) -> ActorView:
        data = action["data"]
        if (
            action["actor_id"] != str(source.controller)
            or action["scene_id"] != cast.id
            or action["state"] != "complete"
            or data.get("actor_basic", {}).get("ref") != source.ref.model_dump(mode="json")
            or not data.get("receipt")
        ):
            raise WorkflowError("Use an actual original completed Harpy Play against this Girl")
        target = (data.get("harpy_flirt") or data.get("battle") or {}).get("target")
        target_actor = ActorRef.model_validate(target) if target else None
        girl = people.get(target_actor.token) if target_actor else None
        if girl is None:
            raise WorkflowError("Choose the original Girl actually targeted by the Play")
        events = t.events
        sequence = c.scalar(
            sa.select(events.c.seq).where(
                events.c.campaign_id == self.store.campaign_id,
                events.c.actor_id == str(source.controller),
                events.c.kind == "m3.actor_play_confirmed",
                sa.func.json_extract(events.c.payload_json, "$.action_id") == action["id"],
            )
        )
        advancement_seq = c.scalar(
            sa.select(events.c.seq).where(
                events.c.campaign_id == self.store.campaign_id, events.c.id == advancement
            )
        )
        if sequence is None or advancement_seq is None or advancement_seq >= sequence:
            raise WorkflowError("The original Harpy must already own the advancement at the Play")
        history = t.m2["m2_state_history"]
        body = c.scalar(
            sa.select(history.c.body_json)
            .join(events, events.c.id == history.c.event_id)
            .where(
                history.c.campaign_id == self.store.campaign_id,
                events.c.campaign_id == self.store.campaign_id,
                events.c.seq < sequence,
            )
            .order_by(events.c.seq.desc())
            .limit(1)
        )
        if not body:
            raise WorkflowError("Recover the original Harpy’s actual earlier physical position")
        original = GameState.model_validate_json(body)
        early = resolve(
            original, source.ref, profiles(c, self.store.campaign_id), require_current_profile=False
        )
        if early.inside_frame is not False or source.inside_frame is not False:
            raise WorkflowError("The actual Harpy must have been outside her own Frame")
        return girl

    def _where(
        self,
        c: Connection,
        state: GameState,
        channel: int,
        actor: ActorRef,
        controller: int,
    ) -> tuple[SceneCast, ActorView, tuple[int, str], dict[str, ActorView], str]:
        cast, source, gm, people = self.intimacy._where(c, state, channel, actor)
        _, advancement = scene_harpy(self.game, c, state, controller, cast, actor, KISS)
        return cast, source, gm, people, advancement

    def menu(self, viewer: GuildViewer, channel: int, actor: ActorRef) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self._gate(c, viewer)
            state = load_state(c, self.store.campaign_id)
            cast, source, _, people, advancement = self._where(
                c, state, channel, actor, viewer.user_id
            )
            table = t.m2["m2_actions"]
            used = {x.action for x in records(state)}
            options = {}
            for candidate in c.scalars(
                sa.select(table.c.id).where(
                    table.c.campaign_id == self.store.campaign_id,
                    table.c.actor_id == str(viewer.user_id),
                    table.c.scene_id == cast.id,
                    table.c.state == "complete",
                )
            ):
                if candidate in used:
                    continue
                action = self.game.action(c, candidate)
                try:
                    girl = self._action(c, action, cast, source, people, advancement)
                except (ValueError, WorkflowError):
                    continue
                options[candidate] = (
                    action["data"]["play"].replace("_", " ").title() + " — " + girl.label
                )
            return dict(revision=state.revision, actions=options)

    def _save(
        self,
        c: Connection,
        state: GameState,
        viewer: GuildViewer,
        key: str,
        case: Surprise,
        event: str,
        operation: str,
    ) -> dict[str, Any]:
        state.facts = [x for x in state.facts if (x.get("kind"), x.get("id")) != (KIND, case.id)]
        state.facts.append(dict(kind=KIND, id=case.id, body=case.model_dump_json()))
        self.game.event(
            c,
            viewer.user_id,
            key,
            "m3.harpy_kiss_" + operation,
            state,
            event_id=event,
            case=case.id,
            action_id=case.action,
        )
        return dict(id=case.id, encounter=case.encounter)

    def propose(
        self,
        viewer: GuildViewer,
        key: str,
        channel: int,
        actor: ActorRef,
        revision: int,
        action: str,
        choice: Literal["kiss", "linger"],
        account: str,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            require_scene_clear(self.game, c, channel)
            state = load_state(c, self.store.campaign_id)
            cast, source, (gm, appointment), people, advancement = self._where(
                c, state, channel, actor, viewer.user_id
            )
            if (
                state.revision != revision
                or choice not in ("kiss", "linger")
                or not 0 < len(account.strip()) <= 1200
                or any(x.action == action for x in records(state))
            ):
                raise WorkflowError("Choose one actual eligible original Play and response")
            girl = self._action(c, self.game.action(c, action), cast, source, people, advancement)
            event = str(uuid4())
            case = Surprise(
                id=event,
                action=action,
                scene=cast.id,
                channel=channel,
                harpy=actor,
                controller=viewer.user_id,
                girl=girl.ref,
                gm=gm,
                appointment=appointment,
                advancement=advancement,
                choice=choice,
                account=account.strip(),
            )
            return self._save(c, state, viewer, key, case, event, "proposed")

        return self.store._write(
            viewer,
            key,
            "m3.harpy_kiss_proposal",
            dict(
                channel=channel,
                actor=actor.model_dump(mode="json"),
                revision=revision,
                action=action,
                choice=choice,
                account=account,
            ),
            operation,
            authorize=lambda c: self._gate(c, viewer),
            auto_audit=False,
        )

    def _review(
        self,
        c: Connection,
        state: GameState,
        viewer: GuildViewer,
        identity: str,
    ) -> tuple[Surprise, ActorView]:
        case = next((x for x in records(state) if x.id == identity), None)
        if case is None or case.gm != viewer.user_id or case.reviewed is not None:
            raise WorkflowError("This original private review is unavailable")
        cast, source, actual, people, advancement = self._where(
            c, state, case.channel, case.harpy, case.controller
        )
        if (cast.id, actual, advancement) != (
            case.scene,
            (case.gm, case.appointment),
            case.advancement,
        ):
            raise WorkflowError("Recover the original appointment and actual scene")
        girl = self._action(c, self.game.action(c, case.action), cast, source, people, advancement)
        if girl.ref != case.girl:
            raise WorkflowError("Use the actual original surprised participant")
        return case, girl

    def tasks(
        self,
        c: Connection,
        state: GameState,
        viewer: GuildViewer,
    ) -> tuple[str, ...]:
        waiting = tuple(x.id for x in records(state) if x.gm == viewer.user_id and not x.reviewed)
        if not waiting:
            return ()
        try:
            self._gate(c, viewer)
        except (ValueError, WorkflowError):
            return ()
        allowed = []
        for identity in waiting:
            try:
                self._review(c, state, viewer, identity)
            except (ValueError, WorkflowError):
                continue
            allowed.append(identity)
        return tuple(allowed)

    def get(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self._gate(c, viewer)
            state = load_state(c, self.store.campaign_id)
            case, girl = self._review(c, state, viewer, identity)
            return dict(
                revision=state.revision, choice=case.choice, account=case.account, girl=girl.label
            )

    def confirm(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        approve: bool,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            case, girl = self._review(c, state, viewer, identity)
            require_scene_clear(self.game, c, case.channel)
            if state.revision != revision or type(approve) is not bool:
                raise WorkflowError("Reopen the original surprise review")
            event = str(uuid4())
            encounter = None
            if approve and case.choice == "kiss":
                self.intimacy._gate(c, viewer)
                if any(
                    x.harpy == case.harpy and x.girl == case.girl and x.phase != "complete"
                    for x in intimacy_records(state)
                ):
                    raise WorkflowError("Finish the existing original private encounter first")
                encounter = event
                put(
                    state,
                    Encounter(
                        id=event,
                        scene=case.scene,
                        channel=case.channel,
                        gm=case.gm,
                        appointment=case.appointment,
                        harpy=case.harpy,
                        controller=case.controller,
                        girl=case.girl,
                        owner=girl.controller,
                        bond=depth(state, case.harpy, girl.ref),
                        frame=girl.frame_instance,
                        kiss=case.id,
                    ),
                )
            case = case.model_copy(update=dict(answer=approve, reviewed=event, encounter=encounter))
            return self._save(c, state, viewer, key, case, event, "reviewed")

        def authorize(c: Connection) -> None:
            self._gate(c, viewer)
            state = load_state(c, self.store.campaign_id)
            case = next((x for x in records(state) if x.id == identity), None)
            if (
                case is None
                or case.gm != viewer.user_id
                or MedicalService(self.store)._handler(c) != (case.gm, case.appointment)
            ):
                raise WorkflowError("This original private review is unavailable")

        return self.store._write(
            viewer,
            key,
            "m3.harpy_kiss_review",
            dict(id=identity, revision=revision, approve=approve),
            operation,
            authorize=authorize,
            auto_audit=False,
        )


def prove_encounter(
    game: GameService,
    c: Connection,
    state: GameState,
    encounter: Encounter,
) -> None:
    Access(game.store).require_specialist_rule(KISS)
    case = next((x for x in records(state) if x.id == encounter.kiss), None)
    events = t.events
    row = c.execute(
        sa.select(events.c.kind, events.c.actor_id, events.c.payload_json).where(
            events.c.campaign_id == game.store.campaign_id,
            events.c.id == encounter.id,
        )
    ).first()
    if (
        case is None
        or case.answer is not True
        or case.choice != "kiss"
        or case.encounter != encounter.id
        or case.reviewed != encounter.id
        or (case.harpy, case.girl, case.scene, case.gm, case.appointment)
        != (encounter.harpy, encounter.girl, encounter.scene, encounter.gm, encounter.appointment)
        or row is None
        or row.kind != "m3.harpy_kiss_reviewed"
        or row.actor_id != str(case.gm)
        or json.loads(row.payload_json).get("case") != case.id
    ):
        raise WorkflowError("Recover the original confirmed Kiss Me, Darling source")
