"""Elective Captured! with actual rebel custody and independently owned effects."""

from collections.abc import Callable, Iterator
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_captured as rules
from girlframe.engine import m3_physical as physical
from girlframe.engine.m2 import GameState, IdentityState
from girlframe.engine.m3_actor_bonds import make_helpless
from girlframe.engine.m3_actor_state import ActorRef, ActorView, SceneCast
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_hallucinations import Roll
from girlframe.engine.m3_parasite_infection import controls_identity
from girlframe.engine.m3_world_state import AdversaryPilot, Npc
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_battle import _cast
from girlframe.services.m3_medical import MedicalService
from girlframe.services.onboarding import WorkflowError
from girlframe.services.p1_facilitator import require_scene_clear
from girlframe.services.read_only_bot import GuildViewer

MID = {
    "escape": "Set a scene outside the captured room after getting free",
    "chance": "Set another actual fighting chance",
}
HIGH = {
    "pilot": "An actual Rebel Pilot wants something from her",
    "handler": "An actual Rebel Handler restrains her",
    "staff": "Rebel personnel are sent to punish her",
    "other": "The rebels leave her drained",
}


class CapturedService:
    def __init__(self, game: GameService):
        self.game, self.store = game, game.store

    def _gate(self, c: Connection, viewer: GuildViewer) -> None:
        access = Access(self.store)
        access.authorize(c, viewer, "plays", director_response=True)
        access.authorize(c, viewer, "world", director_response=True)
        access.require_specialist_rule(rules.RULE)

    def _source(
        self,
        c: Connection,
        state: GameState,
        channel: int,
        captor: ActorRef,
        *,
        held: bool = False,
    ) -> tuple[SceneCast, ActorView, str, str, dict[str, ActorView]]:
        cast = _cast(self.game, c, state, channel)
        gm, _ = MedicalService(self.store)._handler(c)
        world = state.world
        if world is None or cast.facilitator != gm:
            raise WorkflowError("Recover a facilitated original rebel scene")
        bound = profiles(c, self.store.campaign_id)
        actor = resolve(state, captor, bound, require_current_profile=False)
        if (
            not actor.alive
            or actor.offstage_source
            or actor.cell is None
            or actor.custody not in (None, "free")
            or not any(x.actor == captor and x.controller == actor.controller for x in cast.roles)
        ):
            raise WorkflowError("Recover the original Rebel captor")
        source: AdversaryPilot | Npc | None
        if captor.kind == "external_pilot":
            source = next(
                (x for x in world.pilots if x.id == captor.entity and x.kind == "rebel"), None
            )
        elif captor.kind == "npc":
            source = next(
                (x for x in world.npcs if x.id == captor.entity and "handler" in x.jobs), None
            )
        else:
            source = None
        faction = next(
            (
                x
                for x in world.factions
                if source and x.id == source.faction and x.active and x.kind == "rebel"
            ),
            None,
        )
        base = next(
            (
                x
                for x in world.locations
                if x.kind == "base"
                and x.allegiance == "rebel"
                and x.operational
                and x.cell == actor.cell
            ),
            None,
        )
        if faction is None or base is None or base.cell not in faction.cells:
            raise WorkflowError("Use the actual original Rebel captor at their operational base")
        targets = {}
        for role in cast.roles:
            if role.actor.kind != "pilot" or role.controller == actor.controller:
                continue
            girl = resolve(state, role.actor, bound, require_current_profile=False)
            placement = next((x for x in state.placements if x.actor == role.actor), None)
            if not (
                girl.alive
                and girl.rules == "girl_frame"
                and girl.controller == role.controller
                and girl.cell == actor.cell
                and girl.inside_frame is False
                and not girl.offstage_source
                and placement is not None
                and placement.vitals_active
                and placement.custody == (captor if held else None)
            ):
                continue
            targets[role.actor.token] = girl
        return cast, actor, base.id, faction.id, targets

    def menu(self, viewer: GuildViewer, channel: int, captor: ActorRef) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self._gate(c, viewer)
            state = load_state(c, self.store.campaign_id)
            if MedicalService(self.store)._handler(c)[0] != viewer.user_id:
                raise WorkflowError("The original human facilitator opens this capture")
            _, _, _, _, targets = self._source(c, state, channel, captor)
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
                "m3.captured",
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
        step: str,
        value: rules.Capture,
        event: str,
    ) -> dict[str, Any]:
        rules.put(state, value)
        self.game.event(c, viewer.user_id, key, "m3.captured_" + step, state, event_id=event)
        return dict(
            id=value.id, event=event, tier=value.current.roll.result if value.current else None
        )

    def start(
        self,
        viewer: GuildViewer,
        key: str,
        channel: int,
        captor: ActorRef,
        revision: int,
        subject: str,
        account: str,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            MedicalService(self.store)._idle(c)
            require_scene_clear(self.game, c, channel)
            state = load_state(c, self.store.campaign_id)
            cast, actor, base, faction, targets = self._source(c, state, channel, captor)
            gm, appointment = MedicalService(self.store)._handler(c)
            girl = targets.get(subject)
            if (
                girl is None
                or gm != viewer.user_id
                or revision != state.revision
                or not 0 < len(account.strip()) <= 1200
                or any(
                    x.girl == girl.ref and not x.declined and not x.escaped
                    for x in rules.records(state)
                )
            ):
                raise WorkflowError("Record an actual narrated capture of the original Girl")
            event = str(uuid4())
            value = rules.Capture(
                id=event,
                scene=cast.id,
                channel=channel,
                girl=girl.ref,
                captor=captor,
                controller=actor.controller,
                base=base,
                faction=faction,
                gm=gm,
                appointment=appointment,
                account=account.strip(),
            )
            return self._save(c, state, viewer, key, "start", value, event)

        return self._write(
            viewer,
            key,
            dict(
                channel=channel,
                captor=captor.token,
                revision=revision,
                subject=subject,
                account=account,
            ),
            operation,
        )

    def _step(self, state: GameState, viewer: GuildViewer, value: rules.Capture) -> str | None:
        owner = int(value.girl.entity) == viewer.user_id
        sheet = state.sheets.get(value.girl.entity)
        if (
            value.declined
            or value.escaped
            or sheet is None
            or sheet.character_id != value.girl.incarnation
        ):
            return None
        if not value.confirmed:
            return "consent" if owner else None
        if not rules.active(state, value.girl):
            return None
        result = value.current
        if result is None or result.completed:
            return "roll" if owner else None
        if result.roll.result == "mid":
            return "mid" if owner else None
        if result.roll.result == "high":
            if result.chosen_event:
                return "erase" if owner else None
            return "high_scene" if value.gm == viewer.user_id else None
        return "low_review" if owner or value.gm == viewer.user_id else None

    def tasks(
        self, c: Connection, state: GameState, viewer: GuildViewer
    ) -> tuple[tuple[rules.Capture, str], ...]:
        cards = tuple(
            (x, step) for x in rules.records(state) if (step := self._step(state, viewer, x))
        )
        if cards:
            try:
                self._gate(c, viewer)
            except (ValueError, WorkflowError):
                return ()
        return cards

    def _record(
        self, c: Connection, state: GameState, viewer: GuildViewer, identity: str
    ) -> tuple[rules.Capture, str]:
        item = next((x for x in self.tasks(c, state, viewer) if x[0].id == identity), None)
        if item is None:
            raise WorkflowError("This actual private Captured! choice is unavailable")
        value, step = item
        if MedicalService(self.store)._handler(c) != (value.gm, value.appointment):
            raise WorkflowError("Recover the actual original capture facilitator")
        history = t.m2["m2_state_history"]
        for event, suffix, author, snapshot in self._roots(value):
            if event is None:
                continue
            raw = c.scalar(
                sa.select(history.c.body_json)
                .join(t.events, t.events.c.id == history.c.event_id)
                .where(
                    history.c.campaign_id == self.store.campaign_id,
                    history.c.event_id == event,
                    t.events.c.campaign_id == self.store.campaign_id,
                    t.events.c.kind == "m3.captured_" + suffix,
                    t.events.c.actor_id == str(author),
                )
            )
            if not raw or snapshot not in rules.records(GameState.model_validate_json(raw)):
                raise WorkflowError("Recover the exact original custody and printed roll")
        return value, step

    @staticmethod
    def _roots(value: rules.Capture) -> Iterator[tuple[str | None, str, int, rules.Capture]]:
        yield value.id, "start", value.gm, value.model_copy(update=dict(confirmed=None, rolls=()))
        yield (
            value.confirmed,
            "consent",
            int(value.girl.entity),
            value.model_copy(update=dict(rolls=())),
        )
        current = value.current
        if current:
            first = current.model_copy(update=dict(prompt=None, chosen_event=None))
            first = first.model_copy(update=dict(completed=None, erased_identity=None))
            yield (
                current.roll.event,
                "roll",
                int(value.girl.entity),
                value.model_copy(update=dict(rolls=(*value.rolls[:-1], first))),
            )
            if current.roll.result == "high":
                scene = current.model_copy(update=dict(completed=None, erased_identity=None))
                yield (
                    current.chosen_event,
                    "high_scene",
                    value.gm,
                    value.model_copy(update=dict(rolls=(*value.rolls[:-1], scene))),
                )
            if current.completed:
                kind = "erase" if current.roll.result == "high" else "mid"
                yield current.completed, kind, int(value.girl.entity), value

    def _slots(self, state: GameState, value: rules.Capture) -> tuple[IdentityState, ...]:
        from girlframe.engine.m3_clone_am import additional_identities

        sheet = state.sheets[value.girl.entity]
        if sheet.frame == "PROJECT ANKOU" or additional_identities(state, sheet.owner):
            return ()
        return tuple(
            slot
            for slot in sheet.identities
            if not (slot.protected or slot.paired or slot.am_limiter or slot.obsession_sources)
            and slot.id not in sheet.sedation_locked
            and not controls_identity(state, value.girl, slot.id)
        )

    def get(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self._gate(c, viewer)
            state = load_state(c, self.store.campaign_id)
            value, step = self._record(c, state, viewer, identity)
            current = value.current
            return dict(
                step=step,
                revision=state.revision,
                account=value.account if step == "consent" else "",
                heat=state.sheets[value.girl.entity].heat if step == "roll" else None,
                no_heat=bool(current and current.completed and current.roll.result == "high"),
                prompt=current.prompt if current and step == "erase" else None,
                roll=current.roll.model_dump(mode="json") if current else None,
                tier=current.roll.result if current else None,
                slots={i.id: i.name for i in self._slots(state, value)} if step == "erase" else {},
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
        heat: int | None = None,
        account: str = "",
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            MedicalService(self.store)._idle(c)
            state = load_state(c, self.store.campaign_id)
            value, expected = self._record(c, state, viewer, identity)
            if expected != step or state.revision != revision or len(account.strip()) > 1200:
                raise WorkflowError("Refresh the actual original Captured! decision")
            event = str(uuid4())
            if step == "consent" and choice == "decline" and heat is None and not account:
                return self._save(
                    c,
                    state,
                    viewer,
                    key,
                    step,
                    value.model_copy(update=dict(declined=event)),
                    event,
                )
            require_scene_clear(self.game, c, value.channel)
            cast, captor, base, faction, targets = self._source(
                c, state, value.channel, value.captor, held=bool(value.confirmed)
            )
            if (
                cast.id != value.scene
                or captor.controller != value.controller
                or (base, faction) != (value.base, value.faction)
                or value.girl.token not in targets
            ):
                raise WorkflowError("Recover the actual Rebel base and original capture")
            state, changed = self._apply(state, value, event, step, choice, heat, account.strip())
            return self._save(c, state, viewer, key, step, changed, event)

        return self._write(
            viewer,
            key,
            dict(
                id=identity, revision=revision, step=step, choice=choice, heat=heat, account=account
            ),
            operation,
        )

    def _apply(
        self,
        state: GameState,
        value: rules.Capture,
        event: str,
        step: str,
        choice: str | None,
        heat: int | None,
        account: str,
    ) -> tuple[GameState, rules.Capture]:
        sheet = state.sheets[value.girl.entity]
        current = value.current
        if step == "consent" and choice == "accept" and heat is None and not account:
            self._custody(state, value, event, value.captor, value.account)
            state = make_helpless(state, value.girl, value.captor, event)
            return state, value.model_copy(update=dict(confirmed=event))
        if step == "roll" and choice is None and not account and type(heat) is int:
            no_heat = bool(current and current.completed and current.roll.result == "high")
            if (
                not 0 <= heat <= sheet.heat
                or no_heat
                and heat != 0
                or not no_heat
                and sheet.heat >= 5
                and heat != sheet.heat
            ):
                raise WorkflowError("Spend the original Girl's actual permitted Heat")
            sheet.heat -= heat
            sheet.revision += 1
            result = rules.Result(
                roll=Roll(faces=self.game.dice.roll(), heat=heat, event=event), no_heat=no_heat
            )
            return state, value.model_copy(update=dict(rolls=(*value.rolls, result)))
        if current is None or heat is not None:
            raise WorkflowError("Recover the actual original Captured! roll")
        if step == "mid" and choice in MID and account:
            rules.recover_capture_helplessness(state, value, event)
            if choice == "escape":
                self._custody(state, value, event, None, account)
                value = value.model_copy(update=dict(escaped=event))
            result = current.model_copy(
                update=dict(prompt=account, chosen_event=event, completed=event)
            )
        elif step == "high_scene" and choice in HIGH and account:
            if (choice == "pilot" and value.captor.kind != "external_pilot") or (
                choice == "handler" and value.captor.kind != "npc"
            ):
                raise WorkflowError("Choose a scene with the actual original Rebel role")
            result = current.model_copy(update=dict(prompt=account, chosen_event=event))
        elif (
            step == "erase" and choice in {x.id for x in self._slots(state, value)} and not account
        ):
            sheet.identities = [x for x in sheet.identities if x.id != choice]
            sheet.revision += 1
            result = current.model_copy(update=dict(erased_identity=choice, completed=event))
        else:
            raise WorkflowError("Apply one actual original Captured! consequence")
        return state, value.model_copy(update=dict(rolls=(*value.rolls[:-1], result)))

    @staticmethod
    def _custody(
        state: GameState, value: rules.Capture, event: str, custodian: ActorRef | None, account: str
    ) -> None:
        body = next(x for x in state.placements if x.actor == value.girl)
        physical._source(state, event, account, value.girl)
        physical._save(
            state,
            body.model_copy(update=dict(custody=custodian, source_event=event, account=account)),
        )
