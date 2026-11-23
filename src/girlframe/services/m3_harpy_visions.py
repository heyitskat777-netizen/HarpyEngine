"""Consent, actual Harpy dice and independently owned Visions decisions."""

from collections.abc import Callable
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_harpy_visions as rules
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef, ActorView, SceneCast
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_hallucinations import Roll
from girlframe.engine.m3_harpy_advancements import VISIONS
from girlframe.engine.m3_harpy_defeat import harpy, update
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


class VisionsService:
    def __init__(self, game: GameService):
        self.game, self.store = game, game.store

    def _gate(self, c: Connection, viewer: GuildViewer) -> None:
        access = Access(self.store)
        access.authorize(c, viewer, "plays", director_response=True)
        access.require_specialist_rule(VISIONS)

    def _targets(
        self,
        c: Connection,
        state: GameState,
        cast: SceneCast,
        source: ActorView,
    ) -> dict[str, ActorView]:
        bound = profiles(c, self.store.campaign_id)
        result = {}
        for role in cast.roles:
            if role.actor.kind != "pilot":
                continue
            target = resolve(state, role.actor, bound, require_current_profile=False)
            if (
                target.alive
                and target.rules == "girl_frame"
                and target.controller == role.controller
                and target.controller != source.controller
                and not target.offstage_source
                and target.cell == source.cell
                and target.inside_frame is False
            ):
                result[target.ref.token] = target
        return result

    def targets(self, viewer: GuildViewer, channel: int, actor: ActorRef) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self._gate(c, viewer)
            state = load_state(c, self.store.campaign_id)
            cast = _cast(self.game, c, state, channel)
            source, _ = scene_harpy(self.game, c, state, viewer.user_id, cast, actor, VISIONS)
            return dict(
                revision=state.revision,
                targets={
                    key: value.label for key, value in self._targets(c, state, cast, source).items()
                },
            )

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
                "m3.harpy_visions",
                payload,
                operation,
                auto_audit=False,
                authorize=lambda c: self._gate(c, viewer),
            )
        except ValueError as error:
            raise WorkflowError(str(error)) from None

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
            if state.revision != revision or not 0 < len(account.strip()) <= 1200:
                raise WorkflowError(
                    "Refresh the actual Visions initiation and describe its contact"
                )
            cast = _cast(self.game, c, state, channel)
            source, advance = scene_harpy(self.game, c, state, viewer.user_id, cast, actor, VISIONS)
            subject = self._targets(c, state, cast, source).get(target)
            if subject is None or any(
                x.harpy == actor and x.subject == subject.ref and not x.resolved
                for x in rules.records(state)
            ):
                raise WorkflowError(
                    "Choose the original present Girl and recover any existing Visions"
                )
            value = rules.Vision(
                id=str(uuid4()),
                scene=cast.id,
                channel=channel,
                harpy=actor,
                controller=source.controller,
                subject=subject.ref,
                advancement=advance,
                account=account.strip(),
            )
            rules.put(state, value)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.harpy_visions_offered",
                state,
                event_id=value.id,
                case=value.id,
            )
            return dict(id=value.id)

        return self._write(
            viewer,
            key,
            dict(
                channel=channel,
                actor=actor.model_dump(mode="json"),
                revision=revision,
                target=target,
                account=account,
            ),
            operation,
        )

    @staticmethod
    def _step(state: GameState, viewer: GuildViewer, case: rules.Vision) -> str | None:
        sheet = state.sheets.get(case.subject.entity)
        if case.resolved or sheet is None or sheet.character_id != case.subject.incarnation:
            return None
        if case.consent is None:
            return "consent" if str(viewer.user_id) == case.subject.entity else None
        if case.roll is None:
            return "roll" if viewer.user_id == case.controller else None
        if case.roll.result == "low":
            return "replace" if str(viewer.user_id) == case.subject.entity else None
        if case.proposed is not None:
            return "confirm" if str(viewer.user_id) == case.subject.entity else None
        return "plan" if viewer.user_id == case.controller else None

    def tasks(
        self,
        c: Connection,
        state: GameState,
        viewer: GuildViewer,
    ) -> tuple[tuple[rules.Vision, str], ...]:
        pending = tuple(
            (x, step) for x in rules.records(state) if (step := self._step(state, viewer, x))
        )
        if pending:
            try:
                self._gate(c, viewer)
            except (ValueError, WorkflowError):
                return ()
        return pending

    def _read(
        self,
        c: Connection,
        state: GameState,
        viewer: GuildViewer,
        identity: str,
    ) -> tuple[rules.Vision, str]:
        case = next((x for x in rules.records(state) if x.id == identity), None)
        step = self._step(state, viewer, case) if case else None
        if case is None or step is None:
            raise WorkflowError("This original private Visions decision is unavailable")
        rolled = case.model_copy(update=dict(plans=(), returned=()))
        roots = [
            (
                case.id,
                "offered",
                case.controller,
                rolled.model_copy(update=dict(consent=None, roll=None, low_identities=())),
            ),
            (
                case.consent,
                "consent",
                int(case.subject.entity),
                rolled.model_copy(update=dict(roll=None, low_identities=())),
            ),
            (case.roll.event if case.roll else None, "roll", case.controller, rolled),
        ]
        if case.proposed is not None:
            roots.append((case.proposed.event, "plan", case.controller, case))
        for event, kind, author, expected in roots:
            if event is None:
                continue
            saved = self._history(c, event, kind, author)
            if saved is None or expected not in rules.records(saved):
                raise WorkflowError("Recover the original Visions consent and owned roll")
        return case, step

    def _history(self, c: Connection, event: str, kind: str, author: int) -> GameState | None:
        history = t.m2["m2_state_history"]
        raw = c.scalar(
            sa.select(history.c.body_json)
            .join(t.events, t.events.c.id == history.c.event_id)
            .where(
                history.c.campaign_id == self.store.campaign_id,
                history.c.event_id == event,
                t.events.c.campaign_id == self.store.campaign_id,
                t.events.c.actor_id == str(author),
                t.events.c.kind == "m3.harpy_visions_" + kind,
            )
        )
        return GameState.model_validate_json(raw) if raw else None

    def get(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self._gate(c, viewer)
            state = load_state(c, self.store.campaign_id)
            case, step = self._read(c, state, viewer, identity)
            proposal = case.proposed
            descriptions: tuple[str, ...] | None = None
            if step == "confirm" and proposal is not None:
                try:
                    if rules.baseline(state, case, proposal.choices) == proposal.baseline:
                        _, descriptions = rules.preview(state, case, proposal.choices, "preview")
                except ValueError:
                    pass
            return dict(
                revision=state.revision,
                step=step,
                account=case.account,
                heat=harpy(state, case.harpy).heat if step == "roll" else None,
                roll=case.roll.model_dump(mode="json") if case.roll else None,
                tier=case.roll.result if case.roll else None,
                identities=[x.name for x in case.low_identities] if step == "replace" else [],
                can_replace=rules.can_replace(state, case) if step == "replace" else False,
                descriptions=descriptions,
            )

    def respond(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        step: str,
        *,
        choice: bool | None = None,
        heat: int | None = None,
        choices: tuple[rules.Adjustment, ...] | None = None,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            MedicalService(self.store)._idle(c)
            state = load_state(c, self.store.campaign_id)
            case, expected = self._read(c, state, viewer, identity)
            if step != expected or state.revision != revision:
                raise WorkflowError("Refresh the actual original Visions decision")
            cast = _cast(self.game, c, state, case.channel)
            source, receipt = scene_harpy(
                self.game, c, state, case.controller, cast, case.harpy, VISIONS
            )
            if (
                cast.id != case.scene
                or receipt != case.advancement
                or case.subject.token not in self._targets(c, state, cast, source)
            ):
                raise WorkflowError(
                    "Recover the original bodies, their contact and the original advancement"
                )
            event = str(uuid4())
            if step == "consent" and type(choice) is bool and heat is None and choices is None:
                rules.put(
                    state,
                    case.model_copy(
                        update=dict(
                            consent=event if choice else None, resolved=None if choice else event
                        )
                    ),
                )
            elif step == "roll" and heat is not None and choice is None and choices is None:
                body = harpy(state, case.harpy)
                if (
                    type(heat) is not int
                    or not 0 <= heat <= body.heat
                    or body.heat >= 5
                    and heat != body.heat
                ):
                    raise WorkflowError("Spend the original Harpy’s actual available Heat")
                state = update(state, case.harpy, heat=body.heat - heat)
                roll = Roll(faces=self.game.dice.roll(), heat=heat, event=event)
                rules.put(
                    state,
                    case.model_copy(
                        update=dict(
                            roll=roll,
                            low_identities=body.identities if roll.result == "low" else (),
                        )
                    ),
                )
            elif step == "replace" and choice is True and heat is None and choices is None:
                state = rules.replace_low(state, case, event)
            elif step == "plan" and choices is not None and choice is None and heat is None:
                self._propose(state, case, choices, event)
            elif (
                step == "confirm"
                and case.proposed is not None
                and type(choice) is bool
                and heat is None
                and choices is None
            ):
                proposal = case.proposed
                if choice:
                    if rules.baseline(state, case, proposal.choices) != proposal.baseline:
                        raise WorkflowError("Return the changed original choices before applying")
                    state, _ = rules.preview(state, case, proposal.choices, event)
                    rules.put(state, case.model_copy(update=dict(resolved=event)))
                else:
                    rules.put(
                        state,
                        case.model_copy(update=dict(returned=(*case.returned, proposal.event))),
                    )
            else:
                raise WorkflowError(
                    "The original saved Visions still require their actual consequence"
                )
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.harpy_visions_" + step,
                state,
                event_id=event,
                case=identity,
            )
            return dict(event=event, id=identity)

        return self._write(
            viewer,
            key,
            dict(
                id=identity,
                revision=revision,
                step=step,
                choice=choice,
                heat=heat,
                choices=(
                    [x.model_dump(mode="json") for x in choices] if choices is not None else None
                ),
            ),
            operation,
        )

    @staticmethod
    def _propose(
        state: GameState,
        case: rules.Vision,
        choices: tuple[rules.Adjustment, ...],
        event: str,
    ) -> None:
        rules.require_choice_count(case, choices)
        baseline = rules.baseline(state, case, choices)
        plan = rules.Plan(event=event, baseline=baseline, choices=choices)
        rules.put(state, case.model_copy(update=dict(plans=(*case.plans, plan))))

    @staticmethod
    def _recovery_step(
        state: GameState, viewer: GuildViewer, value: rules.Restriction
    ) -> str | None:
        sheet = state.sheets.get(value.actor.entity)
        if (
            value.restored is not None
            or sheet is None
            or sheet.character_id != value.actor.incarnation
        ):
            return None
        if value.recovery is None:
            return "request" if str(viewer.user_id) == value.actor.entity else None
        return "verify" if value.recovery.facilitator == viewer.user_id else None

    def recovery_tasks(
        self, c: Connection, state: GameState, viewer: GuildViewer
    ) -> tuple[tuple[rules.Restriction, str], ...]:
        pending = tuple(
            (x, step)
            for x in rules.restrictions(state)
            if (step := self._recovery_step(state, viewer, x))
        )
        if pending:
            try:
                self._gate(c, viewer)
            except (ValueError, WorkflowError):
                return ()
        return pending

    def _recovery_read(
        self, c: Connection, state: GameState, viewer: GuildViewer, identity: str
    ) -> tuple[rules.Restriction, str]:
        value = next((x for x in rules.restrictions(state) if x.id == identity), None)
        step = self._recovery_step(state, viewer, value) if value else None
        if value is None or step is None:
            raise WorkflowError("This original private reconditioning is unavailable")
        owner = int(value.actor.entity)
        original = self._history(c, value.imposed, "confirm", owner)
        original_restriction = value.model_copy(
            update=dict(recovery=None, processed=None, verification=None)
        )
        if (
            original is None
            or original_restriction not in rules.restrictions(original)
            or not any(
                case.id == value.case
                and case.subject == value.actor
                and case.resolved == value.imposed
                for case in rules.records(original)
            )
        ):
            raise WorkflowError("Recover the original applied Visions restriction")
        if value.recovery is not None:
            request = self._history(c, value.recovery.event, "recondition_request", owner)
            if request is None or value not in rules.restrictions(request):
                raise WorkflowError("Recover the original reconditioning request")
        return value, step

    def _sites(
        self, c: Connection, state: GameState, actor: ActorRef
    ) -> dict[str, tuple[SceneCast, str, str, str]]:
        from girlframe.engine.m3_sentinel_shell import holds

        if state.world is None:
            return {}
        actual = resolve(
            state, actor, profiles(c, self.store.campaign_id), require_current_profile=False
        )
        if (
            not actual.alive
            or actual.rules != "girl_frame"
            or actual.inside_frame is not False
            or actual.offstage_source
            or actual.custody not in (None, "free")
            or holds(state, actor, "trapped")
        ):
            return {}
        gm, appointment = MedicalService(self.store)._handler(c)
        sites = {}
        for cast in state.scene_casts:
            if (
                not cast.open
                or cast.facilitator != gm
                or not any(
                    x.actor == actor and x.controller == actual.controller for x in cast.roles
                )
            ):
                continue
            try:
                if _cast(self.game, c, state, cast.channel) != cast:
                    continue
            except WorkflowError:
                continue
            for base in state.world.locations:
                if base.kind == "base" and base.cell == actual.cell and base.foundation_operational:
                    sites[f"{cast.id}:{base.id}"] = cast, base.id, base.name, appointment
        return sites

    def recovery(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self._gate(c, viewer)
            state = load_state(c, self.store.campaign_id)
            value, step = self._recovery_read(c, state, viewer, identity)
            sites = self._sites(c, state, value.actor)
            return dict(
                revision=state.revision,
                step=step,
                play=rules.REMOVABLE_PLAYS[value.play],
                sites=(
                    {key: name for key, (_, _, name, _) in sites.items()}
                    if step == "request"
                    else {}
                ),
                account=value.recovery.account if step == "verify" and value.recovery else None,
            )

    def recondition(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        step: str,
        *,
        site: str | None = None,
        account: str = "",
        verified: bool | None = None,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            MedicalService(self.store)._idle(c)
            state = load_state(c, self.store.campaign_id)
            value, expected = self._recovery_read(c, state, viewer, identity)
            if state.revision != revision or step != expected:
                raise WorkflowError("Refresh the original reconditioning decision")
            event = str(uuid4())
            original = value.recovery
            if step == "request" and site is not None and verified is None:
                location = self._sites(c, state, value.actor).get(site)
                if location is None or not 0 < len(account.strip()) <= 1200:
                    raise WorkflowError("Describe the original Girl’s performed care at her base")
                cast, base, _, appointment = location
                if cast.facilitator is None:
                    raise WorkflowError("Recover the original Foundation scene facilitator")
                require_scene_clear(self.game, c, cast.channel)
                value = value.model_copy(
                    update=dict(
                        recovery=rules.Recovery(
                            event=event,
                            scene=cast.id,
                            channel=cast.channel,
                            base=base,
                            facilitator=cast.facilitator,
                            appointment=appointment,
                            account=account.strip(),
                        ),
                    )
                )
            elif (
                step == "verify"
                and original is not None
                and type(verified) is bool
                and site is None
                and 0 < len(account.strip()) <= 1200
            ):
                if verified:
                    location = self._sites(c, state, value.actor).get(
                        f"{original.scene}:{original.base}"
                    )
                    if location is None or (
                        location[0].channel,
                        location[0].facilitator,
                        location[3],
                    ) != (original.channel, viewer.user_id, original.appointment):
                        raise WorkflowError("Recover the actual original Foundation care scene")
                    require_scene_clear(self.game, c, original.channel)
                value = value.model_copy(
                    update=dict(
                        recovery=original if verified else None,
                        processed=event,
                        restored=event if verified else None,
                        verification=account.strip(),
                    )
                )
            else:
                raise WorkflowError("Record the original reconditioning and actual result")
            rules.save_restriction(state, value)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.harpy_visions_recondition_" + step,
                state,
                event_id=event,
                restriction=identity,
            )
            return dict(event=event, id=identity)

        return self._write(
            viewer,
            key,
            dict(
                id=identity,
                revision=revision,
                site=site,
                step=step,
                account=account,
                verified=verified,
            ),
            operation,
        )
