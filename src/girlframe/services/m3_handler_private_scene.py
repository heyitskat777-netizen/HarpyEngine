"""Owned consent, attested contact and the original Handler book's effects."""

from collections.abc import Callable
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_handler_private_scene as rules
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_bonds import current_ref, is_helpless
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_handler_state import Conditioning
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_handler_advancements import _history
from girlframe.services.m3_handler_book_orders import active_book, private_handler_scene
from girlframe.services.m3_medical import MedicalService
from girlframe.services.onboarding import OnboardingStore, WorkflowError
from girlframe.services.read_only_bot import GuildViewer

EVENT = "m3.mistress_favor"
TRAINER_EVENT = "m3.trainer_private_scene"


class HandlerPrivateSceneService:
    def __init__(self, store: OnboardingStore, game: GameService | None = None):
        self.store, self.game = store, game or GameService(store)

    def _write(
        self,
        viewer: GuildViewer,
        key: str,
        payload: dict[str, Any],
        operation: Callable[[Connection], dict[str, Any]],
    ) -> dict[str, Any]:
        def access(c: Connection) -> None:
            Access(self.store).authorize(c, viewer, "plays")
            self.game.unpaused(c)

        try:
            return self.store._write(
                viewer, key, EVENT, payload, operation, authorize=access, auto_audit=False
            )
        except ValueError as exc:
            raise WorkflowError(str(exc)) from None

    def _available(
        self, c: Connection, state: GameState, channel: int, handler: ActorRef
    ) -> tuple[str, ActorRef]:
        scene, girl = private_handler_scene(self.game, c, state, channel, handler)
        sheet = state.sheets[girl.entity]
        actual = resolve(
            state, girl, profiles(c, self.store.campaign_id), require_current_profile=False
        )
        if (
            sheet.medical_state != "fit"
            or actual.inside_frame is True
            or actual.custody not in (None, "free")
            or actual.offstage_source
            or any(is_helpless(state, x) for x in (girl, handler))
        ):
            raise WorkflowError("Both original participants must be able to give free consent")
        lock = self.game.lock(c, channel)
        if lock and lock["state"] != "released":
            raise WorkflowError("Finish the pending Play in the original scene")
        return scene["id"], girl

    def invite(
        self,
        viewer: GuildViewer,
        key: str,
        expected: int,
        channel: int,
        *,
        playbook: rules.Book = "Mistress",
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            canon = load_state(c, self.store.campaign_id)
            owned = active_book(self.game, c, canon, book=playbook, rule=rules.RULES[playbook])
            if (
                owned is None
                or owned[0].entity != str(viewer.user_id)
                or canon.revision != expected
            ):
                raise WorkflowError("Use the original Handler in this book and reopen the scene")
            scene, girl = self._available(c, canon, channel, owned[0])
            if any(
                x.handler == owned[0]
                and x.girl == girl
                and x.phase not in ("complete", "withdrawn")
                for x in rules.records(canon)
            ):
                raise WorkflowError(
                    "Continue the existing private choice between these participants"
                )
            event, identity = str(uuid4()), str(uuid4())
            value = rules.PrivateScene(
                id=identity,
                handler=owned[0],
                girl=girl,
                scene=scene,
                channel=channel,
                event=event,
                playbook=playbook,
            )
            rules.put(canon, value)
            self.game.event(
                c,
                viewer.user_id,
                key,
                _event(value),
                canon,
                event_id=event,
                case=identity,
                step="invite",
            )
            return dict(id=identity, revision=canon.revision)

        return self._write(
            viewer,
            key,
            dict(expected=expected, channel=channel)
            | ({"playbook": playbook} if playbook != "Mistress" else {}),
            operation,
        )

    def _case(
        self, c: Connection, canon: GameState, viewer: GuildViewer, identity: str
    ) -> tuple[rules.PrivateScene, ActorRef]:
        value = next((x for x in rules.records(canon) if x.id == identity), None)
        if value is None or str(viewer.user_id) not in (value.handler.entity, value.girl.entity):
            raise WorkflowError("This private choice belongs to its original participants")
        original = _history(c, self.game, value.event)
        if value not in rules.records(original):
            raise WorkflowError("Recover the original committed private choice")
        return value, value.handler if value.handler.entity == str(viewer.user_id) else value.girl

    def _options(self, value: rules.PrivateScene, actor: ActorRef) -> tuple[str, ...]:
        if value.phase == "invite":
            return ("consent", "withdraw") if actor == value.girl else ("withdraw",)
        if value.phase == "scene":
            return ("attest", "withdraw") if actor not in value.attestations else ("withdraw",)
        if value.phase == "trainer_question" and actor == value.handler:
            return ("trainer_ask",)
        if value.phase == "trainer_answer" and actor == value.girl:
            return ("trainer_yes", "trainer_understands")
        if value.phase == "trainer_install" and actor == value.handler:
            return ("install_speak", "pass_phrase")
        if value.phase == "favor" and actor == value.handler:
            return ("ask",)
        if value.phase == "decision" and actor == value.girl:
            return ("accept", "decline")
        if value.phase == "owed" and actor == value.girl:
            return ("fulfilled", "failed")
        if value.phase == "review" and actor == value.handler:
            return ("confirm", "find_failed")
        return ()

    def _proof_of_favor(self, c: Connection, value: rules.PrivateScene, action_id: str) -> None:
        action = self.game.action(c, action_id)
        events = t.events
        accepted = c.scalar(
            sa.select(events.c.seq).where(
                events.c.campaign_id == self.store.campaign_id,
                events.c.id == value.accepted_event,
            )
        )
        authored = c.scalar(
            sa.select(events.c.seq)
            .where(
                events.c.campaign_id == self.store.campaign_id,
                events.c.actor_id == value.girl.entity,
                events.c.kind.in_(
                    ("m2.play_confirmed", "m3.play_confirmed", "m2.followthrough_confirmed")
                ),
                sa.func.json_extract(events.c.payload_json, "$.action_id") == action_id,
            )
            .limit(1)
        )
        if (
            action["actor_id"] != value.girl.entity
            or action["state"] != "complete"
            or action["data"].get("character_ids", {}).get(value.girl.entity)
            != value.girl.incarnation
            or accepted is None
            or authored is None
            or authored <= accepted
        ):
            raise WorkflowError("Use a real later completed Play made by the original Girl")

    def respond(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        expected: int,
        step: str,
        *,
        text: str = "",
        action: str = "",
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            canon = load_state(c, self.store.campaign_id)
            value, actor = self._case(c, canon, viewer, identity)
            if canon.revision != expected or step not in self._options(value, actor):
                raise WorkflowError("Reopen your own current private choice")
            event = str(uuid4())
            owned = active_book(
                self.game, c, canon, book=value.playbook, rule=rules.RULES[value.playbook]
            )
            if step != "withdraw" and (
                owned is None
                or owned[0] != value.handler
                or current_ref(canon, int(value.girl.entity)) != value.girl
            ):
                raise WorkflowError("Recover the original Handler and Girl")
            in_scene = step in ("consent", "attest", "ask", "accept", "decline") or (
                value.playbook == "Trainer" and step != "withdraw"
            )
            if in_scene and self._available(c, canon, value.channel, value.handler) != (
                value.scene,
                value.girl,
            ):
                raise WorkflowError("Recover the original private scene and participants")
            if step in ("ask", "fulfilled", "failed", "confirm", "find_failed") and not (
                1 <= len(text.strip()) <= 1200
            ):
                raise WorkflowError("Record the actual favor or what happened")
            update: dict[str, Any] = dict(event=event)
            if step == "withdraw":
                update.update(phase="withdrawn")
            elif step == "consent":
                update.update(phase="scene")
            elif step == "attest":
                performed = (*value.attestations, actor)
                update.update(
                    attestations=performed,
                    phase=("favor" if value.playbook == "Mistress" else "trainer_question")
                    if len(performed) == 2
                    else "scene",
                )
            elif value.playbook == "Trainer":
                update.update(_training(canon, value, step, text, event))
            elif step == "ask":
                update.update(phase="decision", favor=text.strip())
            elif step == "decline":
                update.update(phase="complete", outcome="declined")
            elif step == "accept":
                rules.change_rank(canon, int(value.girl.entity), ace=True)
                update.update(phase="owed", accepted_event=event)
            elif step == "fulfilled":
                self._proof_of_favor(c, value, action)
                update.update(phase="review", account=text.strip(), action=action)
            elif step == "failed":
                if self.game.pending_actions(c):
                    raise WorkflowError("Finish the actual pending Play before changing Status")
                rules.change_rank(canon, int(value.girl.entity), ace=False)
                update.update(phase="complete", outcome="failed", account=text.strip())
            else:
                if MedicalService(self.store)._handler(c)[0] != viewer.user_id or not value.action:
                    raise WorkflowError(
                        "The authorized human reviews the original Girl's completed Play"
                    )
                self._proof_of_favor(c, value, value.action)
                if step == "find_failed":
                    if self.game.pending_actions(c):
                        raise WorkflowError("Finish the actual pending Play before changing Status")
                    rules.change_rank(canon, int(value.girl.entity), ace=False)
                update.update(
                    phase="complete",
                    outcome="fulfilled" if step == "confirm" else "failed",
                    account=text.strip(),
                )
            value = rules.PrivateScene.model_validate(dict(value.model_dump(), **update))
            rules.put(canon, value)
            self.game.event(
                c,
                viewer.user_id,
                key,
                _event(value),
                canon,
                event_id=event,
                case=identity,
                step=step,
            )
            return dict(id=identity, phase=value.phase, revision=canon.revision)

        return self._write(
            viewer,
            key,
            dict(id=identity, expected=expected, step=step, text=text, action=action),
            operation,
        )

    def menu(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            Access(self.store).authorize(c, viewer, "plays")
            canon = load_state(c, self.store.campaign_id)
            value, actor = self._case(c, canon, viewer, identity)
            sheet = canon.sheets.get(value.girl.entity)
            return dict(
                id=value.id,
                revision=canon.revision,
                phase=value.phase,
                playbook=value.playbook,
                options=self._options(value, actor),
                favor=value.favor,
                outcome=value.outcome,
                action=value.action,
                account=value.account,
                identities=tuple(
                    (x.id, x.name)
                    for x in sheet.identities
                    if not (
                        x.protected
                        or x.paired
                        or x.am_limiter
                        or x.id in sheet.sedation_locked
                        or x.obsession_sources
                    )
                )
                if value.phase == "trainer_answer"
                and actor == value.girl
                and sheet is not None
                and sheet.character_id == value.girl.incarnation
                else (),
            )

    def _tasks(self, viewer: GuildViewer, state: GameState) -> list[tuple[str, rules.Book]]:
        return [
            (x.id, x.playbook)
            for x in rules.records(state)
            if str(viewer.user_id) in (x.handler.entity, x.girl.entity)
            and self._options(x, x.handler if x.handler.entity == str(viewer.user_id) else x.girl)
        ]


def _event(value: rules.PrivateScene) -> str:
    return EVENT if value.playbook == "Mistress" else TRAINER_EVENT


def _training(
    state: GameState, value: rules.PrivateScene, step: str, identity: str, event: str
) -> dict[str, Any]:
    if step == "trainer_ask":
        return dict(phase="trainer_answer")
    if step == "trainer_yes" or (
        step == "trainer_understands" and not state.sheets[value.girl.entity].identities
    ):
        return dict(phase="trainer_install")
    if step == "trainer_understands":
        from girlframe.services.m3_ankou_support import erase_identity

        erase_identity(state, value.girl, identity)
        if not state.sheets[value.girl.entity].identities:
            return dict(phase="trainer_install", identity=identity)
        return dict(phase="complete", outcome="identity_erased", identity=identity)
    if step == "pass_phrase":
        return dict(phase="complete", outcome="identity_erased" if value.identity else "declined")
    persona = state.handler_persona
    if (
        step != "install_speak"
        or persona is None
        or any(x.pilot == value.girl and "speak" in x.phrases for x in persona.conditioning)
    ):
        raise WorkflowError("Choose a supported conditioning phrase that is not already installed")
    installation = Conditioning(pilot=value.girl, phrases=("speak",), source_event=event)
    state.handler_persona = persona.model_copy(
        update=dict(conditioning=(*persona.conditioning, installation))
    )
    return dict(phase="complete", outcome="speak_installed")
