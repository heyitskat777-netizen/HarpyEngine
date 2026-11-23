"""One minute of scoped Harpy editing, with wholly separate owned acceptance."""

from collections.abc import Callable
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine.m2 import GameState, IdentityState
from girlframe.engine.m3_actor_bonds import depth
from girlframe.engine.m3_actor_state import ActorRef, ActorView, Model, SceneCast
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_harpy_advancements import NOTHING
from girlframe.engine.m3_parasite_infection import controls_identity
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_battle import _cast
from girlframe.services.m3_harpy_advancements import scene_harpy
from girlframe.services.m3_medical import MedicalService
from girlframe.services.onboarding import WorkflowError
from girlframe.services.p1_facilitator import require_scene_clear
from girlframe.services.read_only_bot import GuildViewer

KIND = "harpy_sheet_rewrite"


class Rewrite(Model):
    id: str
    scene: str
    channel: int
    harpy: ActorRef
    controller: int
    girl: ActorRef
    advancement: str
    gm: int
    appointment: str
    account: str
    verified: str | None = None
    verification: str | None = None
    authorized: str | None = None
    identities: tuple[IdentityState, ...] = ()
    expires: float | None = None
    draft: dict[str, str] | None = None
    drafted: str | None = None
    closed: str | None = None
    applied: bool = False


def records(state: GameState) -> tuple[Rewrite, ...]:
    return tuple(
        Rewrite.model_validate_json(x["body"]) for x in state.facts if x.get("kind") == KIND
    )


class RewriteService:
    def __init__(self, game: GameService):
        self.game, self.store = game, game.store

    def _gate(self, c: Connection, viewer: GuildViewer) -> None:
        access = Access(self.store)
        access.authorize(c, viewer, "plays", director_response=True)
        access.require_specialist_rule(NOTHING)

    def _scene(
        self, c: Connection, state: GameState, channel: int, owner: int, actor: ActorRef
    ) -> tuple[SceneCast, str, tuple[int, str], dict[str, ActorView]]:
        cast = _cast(self.game, c, state, channel)
        harpy, advancement = scene_harpy(self.game, c, state, owner, cast, actor, NOTHING)
        appointment = MedicalService(self.store)._handler(c)
        if cast.facilitator != appointment[0]:
            raise WorkflowError("Recover the actual facilitated encounter")
        bound = profiles(c, self.store.campaign_id)
        result = {}
        for role in cast.roles:
            if role.actor.kind != "pilot" or role.controller == owner:
                continue
            actual = resolve(state, role.actor, bound, require_current_profile=False)
            if (
                actual.alive
                and actual.rules == "girl_frame"
                and actual.controller == role.controller
                and actual.inside_frame is False
                and actual.cell == harpy.cell
                and not actual.offstage_source
                and actual.custody in (None, "free")
                and depth(state, actor, role.actor) == 2
            ):
                result[role.actor.token] = actual
        return cast, advancement, appointment, result

    def _alone(self, c: Connection, state: GameState, cast: SceneCast, case: Rewrite) -> None:
        bound = profiles(c, self.store.campaign_id)
        subject = resolve(state, case.girl, bound, require_current_profile=False)
        for role in cast.roles:
            if role.actor in (case.girl, case.harpy):
                continue
            other = resolve(
                state, role.actor, bound, require_alive=False, require_current_profile=False
            )
            if other.alive and other.cell == subject.cell and not other.offstage_source:
                raise WorkflowError("The original pair are no longer alone")

    def targets(self, viewer: GuildViewer, channel: int, actor: ActorRef) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self._gate(c, viewer)
            state = load_state(c, self.store.campaign_id)
            _, _, _, targets = self._scene(c, state, channel, viewer.user_id, actor)
            return dict(revision=state.revision, targets={k: x.label for k, x in targets.items()})

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
                "m3.harpy_rewrite",
                payload,
                operation,
                authorize=lambda c: self._gate(c, viewer),
                auto_audit=False,
            )
        except ValueError as error:
            raise WorkflowError(str(error)) from None

    def _persist(
        self,
        c: Connection,
        state: GameState,
        value: Rewrite,
        event: str,
        viewer: GuildViewer,
        key: str,
        step: str,
    ) -> dict[str, Any]:
        state.facts = [x for x in state.facts if (x.get("kind"), x.get("id")) != (KIND, value.id)]
        state.facts.append(dict(kind=KIND, id=value.id, body=value.model_dump_json()))
        self.game.event(c, viewer.user_id, key, "m3.harpy_rewrite_" + step, state, event_id=event)
        return dict(id=value.id, event=event, applied=value.applied)

    def start(
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
            MedicalService(self.store)._idle(c)
            require_scene_clear(self.game, c, channel)
            state = load_state(c, self.store.campaign_id)
            cast, advancement, (gm, appointment), choices = self._scene(
                c, state, channel, viewer.user_id, actor
            )
            subject = choices.get(target)
            if (
                state.revision != revision
                or subject is None
                or not 0 < len(account.strip()) <= 1200
                or any(x.girl == subject.ref and not x.closed for x in records(state))
            ):
                raise WorkflowError("Choose the original Girl with an Intense Bond")
            event = str(uuid4())
            value = Rewrite(
                id=event,
                scene=cast.id,
                channel=channel,
                harpy=actor,
                controller=viewer.user_id,
                girl=subject.ref,
                gm=gm,
                appointment=appointment,
                account=account.strip(),
                advancement=advancement,
            )
            return self._persist(c, state, value, event, viewer, key, "start")

        return self._write(
            viewer,
            key,
            dict(
                channel=channel,
                actor=actor.token,
                revision=revision,
                target=target,
                account=account,
            ),
            operation,
        )

    def _step(self, state: GameState, viewer: GuildViewer, value: Rewrite) -> str | None:
        sheet = state.sheets.get(value.girl.entity)
        if value.closed or sheet is None or sheet.character_id != value.girl.incarnation:
            return None
        owner = str(viewer.user_id) == value.girl.entity
        if value.verified is None:
            return "verify" if viewer.user_id == value.gm else None
        if value.authorized is None:
            return "authorize" if owner else None
        if value.draft is None:
            if value.expires is None or self.store.clock() > value.expires:
                return "expire" if owner or viewer.user_id == value.controller else None
            return "draft" if viewer.user_id == value.controller else None
        return "apply" if owner else None

    def tasks(
        self, c: Connection, state: GameState, viewer: GuildViewer
    ) -> tuple[tuple[Rewrite, str], ...]:
        items = tuple((x, step) for x in records(state) if (step := self._step(state, viewer, x)))
        if items:
            try:
                self._gate(c, viewer)
            except (ValueError, WorkflowError):
                return ()
        return items

    def _original(
        self, c: Connection, state: GameState, viewer: GuildViewer, identity: str
    ) -> tuple[Rewrite, str]:
        value = next((x for x in records(state) if x.id == identity), None)
        step = self._step(state, viewer, value) if value else None
        if value is None or not step:
            raise WorkflowError("This original private edit is unavailable")
        if step == "verify" and MedicalService(self.store)._handler(c) != (
            value.gm,
            value.appointment,
        ):
            raise WorkflowError("Recover the actual original facilitator")
        if step == "draft":
            cast, advancement, _, targets = self._scene(
                c, state, value.channel, value.controller, value.harpy
            )
            if (
                cast.id != value.scene
                or advancement != value.advancement
                or value.girl.token not in targets
            ):
                raise WorkflowError("Recover the original private encounter")
            self._alone(c, state, cast, value)
        root = value.model_copy(
            update=dict(
                verified=None,
                verification=None,
                authorized=None,
                identities=(),
                expires=None,
                draft=None,
                drafted=None,
            )
        )
        bases = (
            (value.id, "start", value.controller, root),
            (
                value.verified,
                "verify",
                value.gm,
                value.model_copy(
                    update=dict(
                        authorized=None, identities=(), expires=None, draft=None, drafted=None
                    )
                ),
            ),
            (
                value.authorized,
                "authorize",
                int(value.girl.entity),
                value.model_copy(update=dict(draft=None, drafted=None)),
            ),
            (value.drafted, "draft", value.controller, value),
        )
        history = t.m2["m2_state_history"]
        for event, action, author, expected in bases:
            if event is None:
                continue
            raw = c.scalar(
                sa.select(history.c.body_json)
                .join(t.events, t.events.c.id == history.c.event_id)
                .where(
                    history.c.campaign_id == self.store.campaign_id,
                    history.c.event_id == event,
                    t.events.c.campaign_id == self.store.campaign_id,
                    t.events.c.kind == "m3.harpy_rewrite_" + action,
                    t.events.c.actor_id == str(author),
                )
            )
            if raw is None or expected not in records(GameState.model_validate_json(raw)):
                raise WorkflowError("Recover the actual original edit and private choices")
        return value, step

    def _slots(self, state: GameState, case: Rewrite) -> dict[str, IdentityState]:
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
            value, step = self._original(c, state, viewer, identity)
            slots = self._slots(state, value).values() if step == "authorize" else value.identities
            return dict(
                revision=state.revision,
                step=step,
                account=value.account if step in ("verify", "authorize") else "",
                slots={x.id: x.name for x in slots}
                if step in ("authorize", "draft", "apply")
                else {},
                changes=value.draft if step == "apply" else None,
                remaining=int(max(0, (value.expires or 0) - self.store.clock()))
                if step == "draft"
                else None,
            )

    def respond(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        step: str,
        *,
        allow: bool | None = None,
        selected: tuple[str, ...] = (),
        changes: dict[str, str] | None = None,
        account: str = "",
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            value, expected = self._original(c, state, viewer, identity)
            if (
                expected != step
                or revision != state.revision
                or len(account.strip()) > 1200
                or (step != "verify" and account)
                or (step != "authorize" and selected)
                or (step != "draft" and changes is not None)
            ):
                raise WorkflowError("Refresh the original private edits")
            event = str(uuid4())
            if step == "expire" and allow is None:
                value = value.model_copy(update=dict(closed=event))
            elif step in ("verify", "authorize", "apply") and allow is False:
                value = value.model_copy(update=dict(closed=event))
            else:
                value = self._advance(
                    c, state, value, step, allow, selected, changes, account.strip(), event
                )
            return self._persist(c, state, value, event, viewer, key, step)

        return self._write(
            viewer,
            key,
            dict(
                id=identity,
                revision=revision,
                step=step,
                allow=allow,
                selected=selected,
                changes=changes,
                account=account,
            ),
            operation,
        )

    def _advance(
        self,
        c: Connection,
        state: GameState,
        value: Rewrite,
        step: str,
        allow: bool | None,
        selected: tuple[str, ...],
        changes: dict[str, str] | None,
        account: str,
        event: str,
    ) -> Rewrite:
        MedicalService(self.store)._idle(c)
        require_scene_clear(self.game, c, value.channel)
        cast, advancement, appointment, targets = self._scene(
            c, state, value.channel, value.controller, value.harpy
        )
        if (
            cast.id != value.scene
            or advancement != value.advancement
            or appointment != (value.gm, value.appointment)
            or value.girl.token not in targets
        ):
            raise WorkflowError("Recover the original bodies, Intense Bond and facilitator")
        self._alone(c, state, cast, value)
        if step == "verify" and allow is True and account:
            return value.model_copy(update=dict(verified=event, verification=account))
        slots = self._slots(state, value)
        if step == "authorize" and allow is True:
            if (
                not selected
                or len(set(selected)) != len(selected)
                or not set(selected) <= slots.keys()
            ):
                raise WorkflowError("Authorize only your actual ordinary Identity slots")
            opened = tuple(slots[key] for key in selected)
            return value.model_copy(
                update=dict(
                    authorized=event, identities=opened, expires=float(self.store.clock()) + 60
                )
            )
        if value.expires is None or any(slots.get(x.id) != x for x in value.identities):
            raise WorkflowError("The original authorized Identities changed")
        if step == "draft" and allow is None and changes and self.store.clock() <= value.expires:
            labels = {key: name.strip() for key, name in changes.items()}
            if not labels.keys() <= {x.id for x in value.identities} or any(
                not 0 < len(name) <= 120 for name in labels.values()
            ):
                raise WorkflowError("Edit only the original authorized Identity names")
            return value.model_copy(update=dict(drafted=event, draft=labels))
        if step == "apply" and allow is True and value.draft:
            self._labels(state, value, value.draft)
            sheet = state.sheets[value.girl.entity]
            for owned in sheet.identities:
                if owned.id in value.draft:
                    owned.name = value.draft[owned.id]
            sheet.revision += 1
            return value.model_copy(update=dict(closed=event, applied=True))
        raise WorkflowError("Record only the actual original rewrite decision")

    def _labels(self, state: GameState, value: Rewrite, changes: dict[str, str]) -> None:
        sheet = state.sheets[value.girl.entity]
        labels = [changes.get(x.id, x.name).casefold() for x in sheet.identities]
        if any(labels.count(name.casefold()) != 1 for name in changes.values()):
            raise WorkflowError("Propose distinct Identity names")
