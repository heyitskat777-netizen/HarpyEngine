"""Private elective Escape choices and the original Girl’s actual consequences."""

from collections.abc import Callable
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_physical as physical
from girlframe.engine.m2 import GameState, IdentityState, shift_status
from girlframe.engine.m3_actor_bonds import (
    change,
    depth,
    is_helpless,
    make_helpless,
)
from girlframe.engine.m3_actor_state import ActorRef, ActorView, Model, SceneCast
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_core import damage
from girlframe.engine.m3_hallucinations import Roll
from girlframe.engine.m3_harpy_defeat import give_tag
from girlframe.engine.m3_intracadre_marriage import status_groups
from girlframe.engine.m3_parasite_infection import controls_identity
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_battle import _cast
from girlframe.services.m3_medical import MedicalService
from girlframe.services.onboarding import WorkflowError
from girlframe.services.p1_facilitator import require_scene_clear
from girlframe.services.read_only_bot import GuildViewer

RULE = "situational.situational.escape"
KIND = "escape_situational"


class Escape(Model):
    id: str
    girl: ActorRef
    gm: int
    appointment: str
    scene: str
    channel: int
    base: str
    roll: Roll
    account: str
    rescuer: ActorRef | None = None
    rescuer_controller: int | None = None
    found: str | None = None
    finding: str | None = None
    erased: str | None = None
    resolved: str | None = None
    ward: ActorRef | None = None
    restraint_released: str | None = None


def records(state: GameState) -> tuple[Escape, ...]:
    return tuple(
        Escape.model_validate_json(x["body"]) for x in state.facts if x.get("kind") == KIND
    )


def held(state: GameState, actor: ActorRef) -> bool:
    return any(
        case.girl == actor and (not case.resolved or case.ward and not case.restraint_released)
        for case in records(state)
    )


class EscapeService:
    def __init__(self, game: GameService):
        self.game, self.store = game, game.store

    def _gate(self, c: Connection, viewer: GuildViewer) -> None:
        access = Access(self.store)
        access.authorize(c, viewer, "plays", director_response=True)
        access.authorize(c, viewer, "world", director_response=True)
        access.require_specialist_rule(RULE)

    def _where(
        self,
        c: Connection,
        state: GameState,
        channel: int,
        actor: ActorRef,
        *,
        held: ActorRef | None = None,
        injured: bool = False,
    ) -> tuple[SceneCast, ActorView, str, tuple[int, str]]:
        cast = _cast(self.game, c, state, channel)
        appointment = MedicalService(self.store)._handler(c)
        world = state.world
        actual = resolve(
            state, actor, profiles(c, self.store.campaign_id), require_current_profile=False
        )
        body = next((x for x in state.placements if x.actor == actor), None)
        base = (
            next(
                (
                    x.id
                    for x in world.locations
                    if x.kind == "base" and x.foundation_operational and x.cell == actual.cell
                ),
                None,
            )
            if world
            else None
        )
        if (
            actor.kind != "pilot"
            or not actual.alive
            or actual.rules != "girl_frame"
            or actual.offstage_source is not None
            or base is None
            or body is None
            or body.mode != "outside_frame"
            or not body.vitals_active
            or body.custody != held
            or body.incapacitated != injured
            or cast.facilitator != appointment[0]
            or not any(x.actor == actor and x.controller == actual.controller for x in cast.roles)
        ):
            raise WorkflowError(
                "Recover the original Girl outside her Frame at her Foundation base"
            )
        return cast, actual, base, appointment

    def _people(
        self,
        c: Connection,
        state: GameState,
        cast: SceneCast,
        actor: ActorView,
        *,
        personnel: bool,
    ) -> dict[str, ActorView]:
        bound = profiles(c, self.store.campaign_id)
        result = {}
        for role in cast.roles:
            if role.actor == actor.ref or role.actor.kind not in ("pilot", "npc"):
                continue
            witness = resolve(state, role.actor, bound, require_current_profile=False)
            if (
                witness.controller == role.controller
                and witness.controller != actor.controller
                and witness.alive
                and not witness.offstage_source
                and witness.cell == actor.cell
                and witness.custody in (None, "free")
                and (
                    not personnel
                    or witness.ref.kind == "npc"
                    and bool({"base_personnel", "doctor"} & set(witness.jobs))
                )
                and not is_helpless(state, actor.ref, witness.ref)
            ):
                result[witness.ref.token] = witness
        return result

    def menu(self, viewer: GuildViewer, channel: int, actor: ActorRef) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self._gate(c, viewer)
            state = load_state(c, self.store.campaign_id)
            _, actual, _, _ = self._where(c, state, channel, actor)
            if actual.controller != viewer.user_id:
                raise WorkflowError("Only the original Girl starts her Escape Play")
            return dict(revision=state.revision, heat=state.sheets[actor.entity].heat)

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
                "m3.escape",
                payload,
                operation,
                authorize=lambda c: self._gate(c, viewer),
                auto_audit=False,
            )
        except ValueError as error:
            raise WorkflowError(str(error)) from None

    def _save(
        self,
        c: Connection,
        state: GameState,
        viewer: GuildViewer,
        key: str,
        case: Escape,
        step: str,
        event: str,
    ) -> dict[str, Any]:
        state.facts = [x for x in state.facts if (x.get("kind"), x.get("id")) != (KIND, case.id)]
        state.facts.append(dict(kind=KIND, id=case.id, body=case.model_dump_json()))
        self.game.event(c, viewer.user_id, key, "m3.escape_" + step, state, event_id=event)
        return dict(id=case.id, tier=case.roll.result, event=event)

    def start(
        self,
        viewer: GuildViewer,
        key: str,
        channel: int,
        actor: ActorRef,
        revision: int,
        heat: int,
        account: str,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            MedicalService(self.store)._idle(c)
            require_scene_clear(self.game, c, channel)
            state = load_state(c, self.store.campaign_id)
            cast, actual, base, (gm, appointment) = self._where(c, state, channel, actor)
            sheet = state.sheets[actor.entity]
            if (
                state.revision != revision
                or actual.controller != viewer.user_id
                or type(heat) is not int
                or not 0 <= heat <= sheet.heat
                or sheet.heat >= 5
                and heat != sheet.heat
                or not 0 < len(account.strip()) <= 1200
                or sheet.medical_state != "fit"
                or is_helpless(state, actor)
                or any(x.girl == actor and not x.resolved for x in records(state))
            ):
                raise WorkflowError("Confirm the original scene and your actual permitted Heat")
            event = str(uuid4())
            roll = Roll(faces=self.game.dice.roll(), heat=heat, event=event)
            sheet.heat -= heat
            sheet.revision += 1
            case = Escape(
                id=event,
                girl=actor,
                gm=gm,
                appointment=appointment,
                scene=cast.id,
                channel=channel,
                base=base,
                roll=roll,
                account=account.strip(),
            )
            if roll.result == "mid":
                body = next(x for x in state.placements if x.actor == actor)
                physical._source(state, event, account.strip(), actor)
                physical._save(
                    state,
                    body.model_copy(
                        update=dict(incapacitated=True, source_event=event, account=account.strip())
                    ),
                )
            return self._save(c, state, viewer, key, case, "roll", event)

        return self._write(
            viewer,
            key,
            dict(channel=channel, actor=actor.token, revision=revision, heat=heat, account=account),
            operation,
        )

    @staticmethod
    def _step(state: GameState, viewer: GuildViewer, case: Escape) -> str | None:
        sheet = state.sheets.get(case.girl.entity)
        if sheet is None or sheet.character_id != case.girl.incarnation:
            return None
        owner = str(viewer.user_id) == case.girl.entity
        if case.resolved:
            if case.ward and not case.restraint_released:
                return "release" if viewer.user_id == case.gm else None
            return None
        if case.roll.result == "low":
            return "erase" if owner else None
        if case.roll.result == "high":
            return "ward" if viewer.user_id == case.gm else None
        if case.found:
            return "rescue" if viewer.user_id == case.rescuer_controller else None
        return "find" if viewer.user_id == case.gm else None

    def tasks(
        self, c: Connection, state: GameState, viewer: GuildViewer
    ) -> tuple[tuple[Escape, str], ...]:
        result = tuple((x, step) for x in records(state) if (step := self._step(state, viewer, x)))
        if result:
            try:
                self._gate(c, viewer)
            except (ValueError, WorkflowError):
                return ()
        return result

    def _read(
        self, c: Connection, state: GameState, viewer: GuildViewer, identity: str
    ) -> tuple[Escape, str]:
        entry = next((x for x in self.tasks(c, state, viewer) if x[0].id == identity), None)
        if entry is None:
            raise WorkflowError("This original private Escape choice is unavailable")
        case, step = entry
        if MedicalService(self.store)._handler(c) != (case.gm, case.appointment):
            raise WorkflowError("Recover the original human facilitator")
        initial = case.model_copy(
            update=dict(
                rescuer=None,
                rescuer_controller=None,
                found=None,
                finding=None,
                resolved=None,
                ward=None,
            )
        )
        pairs = (
            (case.id, "roll", int(case.girl.entity), initial),
            (case.found, "find", case.gm, case),
            (case.resolved, "ward", case.gm, case),
        )
        history = t.m2["m2_state_history"]
        for event, kind, author, value in pairs:
            if event is None:
                continue
            raw = c.scalar(
                sa.select(history.c.body_json)
                .join(t.events, t.events.c.id == history.c.event_id)
                .where(
                    history.c.campaign_id == self.store.campaign_id,
                    history.c.event_id == event,
                    t.events.c.campaign_id == self.store.campaign_id,
                    t.events.c.kind == "m3.escape_" + kind,
                    t.events.c.actor_id == str(author),
                )
            )
            if not raw or value not in records(GameState.model_validate_json(raw)):
                raise WorkflowError("Recover the exact original Escape roll and choice")
        return case, step

    @staticmethod
    def _identities(state: GameState, case: Escape) -> dict[str, IdentityState]:
        from girlframe.engine.m3_clone_am import additional_identities

        sheet = state.sheets[case.girl.entity]
        if sheet.frame == "PROJECT ANKOU" or additional_identities(state, sheet.owner):
            return {}
        return {
            x.id: x
            for x in sheet.identities
            if not (x.protected or x.paired or x.am_limiter or x.obsession_sources)
            and x.id not in sheet.sedation_locked
            and not controls_identity(state, case.girl, x.id)
        }

    def get(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self._gate(c, viewer)
            state = load_state(c, self.store.campaign_id)
            case, step = self._read(c, state, viewer, identity)
            people = {}
            if step in ("find", "ward"):
                cast, actor, _, _ = self._where(
                    c, state, case.channel, case.girl, injured=step == "find"
                )
                people = {
                    key: person.label
                    for key, person in self._people(
                        c, state, cast, actor, personnel=step == "ward"
                    ).items()
                }
            return dict(
                revision=state.revision,
                step=step,
                tier=case.roll.result,
                roll=case.roll.model_dump(mode="json"),
                people=people,
                account=case.finding if step == "rescue" else "",
                identities={key: x.name for key, x in self._identities(state, case).items()}
                if step == "erase"
                else {},
            )

    def act(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        step: str,
        *,
        choice: str | None = None,
        account: str = "",
        tag: str = "",
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            MedicalService(self.store)._idle(c)
            state = load_state(c, self.store.campaign_id)
            case, expected = self._read(c, state, viewer, identity)
            if (
                state.revision != revision
                or step != expected
                or len(account.strip()) > 1200
                or len(tag.strip()) > 120
                or tag
                and step != "rescue"
            ):
                raise WorkflowError("Refresh the original Escape decision")
            require_scene_clear(self.game, c, case.channel)
            cast, actor, base, _ = self._where(
                c,
                state,
                case.channel,
                case.girl,
                held=case.ward if step == "release" else None,
                injured=step in ("find", "rescue", "release"),
            )
            if cast.id != case.scene or base != case.base:
                raise WorkflowError("Recover the original actual Escape scene and base")
            event = str(uuid4())
            state, case = self._apply(
                c, state, cast, actor, case, step, choice, account.strip(), tag.strip(), event
            )
            return self._save(c, state, viewer, key, case, step, event)

        return self._write(
            viewer,
            key,
            dict(
                id=identity,
                revision=revision,
                step=step,
                choice=choice,
                account=account,
                tag=tag,
            ),
            operation,
        )

    def _apply(
        self,
        c: Connection,
        state: GameState,
        cast: SceneCast,
        actor: ActorView,
        case: Escape,
        step: str,
        choice: str | None,
        account: str,
        tag: str,
        event: str,
    ) -> tuple[GameState, Escape]:
        sheet = state.sheets[case.girl.entity]
        if step == "erase" and choice in self._identities(state, case) and not account:
            sheet.identities = [x for x in sheet.identities if x.id != choice]
            sheet.revision += 1
            return state, case.model_copy(update=dict(erased=choice, resolved=event))
        if step in ("find", "ward") and account:
            person = self._people(c, state, cast, actor, personnel=step == "ward").get(choice or "")
            if person is None:
                raise WorkflowError("Select the actual original finder or base personnel")
            state = make_helpless(state, case.girl, person.ref, event)
            if step == "ward":
                sheet = state.sheets[case.girl.entity]
                for asset in tuple(sheet.assets):
                    if asset.family == "girl" and not asset.damaged:
                        sheet = damage(sheet, asset.id, piloting=False).sheet
                state.sheets[case.girl.entity] = sheet
                self._dog(state, case.girl)
                body = next(x for x in state.placements if x.actor == case.girl)
                physical._source(state, event, account, case.girl)
                physical._save(
                    state,
                    body.model_copy(
                        update=dict(
                            custody=person.ref,
                            incapacitated=True,
                            source_event=event,
                            account=account,
                        )
                    ),
                )
                return state, case.model_copy(update=dict(ward=person.ref, resolved=event))
            while depth(state, case.girl, person.ref) < 2:
                state = change(state, case.girl, person.ref, 1, event)
            return state, case.model_copy(
                update=dict(
                    rescuer=person.ref,
                    rescuer_controller=person.controller,
                    found=event,
                    finding=account,
                )
            )
        if step == "rescue" and choice == "save" and account and case.rescuer:
            rescuer = resolve(
                state,
                case.rescuer,
                profiles(c, self.store.campaign_id),
                require_current_profile=False,
            )
            if (
                not rescuer.alive
                or rescuer.cell != actor.cell
                or rescuer.offstage_source
                or not any(
                    x.actor == case.rescuer and x.controller == rescuer.controller
                    for x in cast.roles
                )
                or rescuer.controller != case.rescuer_controller
            ):
                raise WorkflowError("Recover the actual original finder who can save her")
            self._release_condition(state, case.girl, rescuer.ref, case.found, event)
            body = next(x for x in state.placements if x.actor == case.girl)
            if body.source_event != case.roll.event:
                raise WorkflowError("Recover the original physical rescue in this scene")
            physical._source(state, event, account, case.girl)
            physical._save(
                state,
                body.model_copy(
                    update=dict(
                        incapacitated=False,
                        source_event=event,
                        account=account,
                    )
                ),
            )
            if tag:
                state = give_tag(
                    state,
                    case.girl,
                    rescuer.ref,
                    tag,
                    event,
                    event,
                    tuple(sorted({int(case.girl.entity), rescuer.controller})),
                )
                self._dog(state, case.girl)
            return state, case.model_copy(update=dict(resolved=event))
        if step == "release" and choice == "release" and account and case.ward:
            body = next(x for x in state.placements if x.actor == case.girl)
            if body.source_event != case.resolved or not body.incapacitated:
                raise WorkflowError("Recover the exact original sickbay restraint")
            self._release_condition(state, case.girl, case.ward, case.resolved, event)
            physical._source(state, event, account, case.girl)
            physical._save(
                state,
                body.model_copy(
                    update=dict(
                        custody=None,
                        incapacitated=False,
                        source_event=event,
                        account=account,
                    )
                ),
            )
            return state, case.model_copy(update=dict(restraint_released=event))
        raise WorkflowError("Resolve only the actual original Escape consequence")

    @staticmethod
    def _release_condition(
        state: GameState, subject: ActorRef, source: ActorRef, imposed: str | None, event: str
    ) -> None:
        match = next(
            (
                x
                for x in state.helpless_conditions
                if x.active
                and x.subject == subject
                and x.foe == source
                and imposed in x.source_events
            ),
            None,
        )
        if match is None:
            raise WorkflowError("Recover the actual original Escape restraint")
        remaining = tuple(x for x in match.source_events if x != imposed)
        changed = match.model_copy(
            update=dict(source_events=remaining)
            if remaining
            else dict(active=False, recovery_event=event)
        )
        state.helpless_conditions = [
            changed if x.id == match.id else x for x in state.helpless_conditions
        ]

    @staticmethod
    def _dog(state: GameState, actor: ActorRef) -> None:
        owner = int(actor.entity)
        for _ in status_groups(state):
            if owner in status_groups(state)[-1]:
                return
            shift_status(state, owner, -1)
        raise WorkflowError("Recover the actual current Cadre Status")
