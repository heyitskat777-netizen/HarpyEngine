"""Ordered, table-authorized Timeskip changes to the original campaign world."""

from collections.abc import Callable
from typing import Any, Literal
from uuid import uuid4

from sqlalchemy import Connection

from girlframe.engine import m3_world as world_rules
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef, Model
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_battle import category, end_actor_casts
from girlframe.engine.m3_battle_director import die as end_director
from girlframe.engine.m3_careers import binding
from girlframe.engine.m3_collateral import install_budget, stage_loss
from girlframe.engine.m3_enforcer import end_grasps
from girlframe.engine.m3_girl_runtime_state import change_playbook_runtime, has_rule
from girlframe.engine.m3_handler_consequences import active_handler
from girlframe.engine.m3_location_build import require_site
from girlframe.engine.m3_physical import interrupt_journeys
from girlframe.engine.m3_vatgrown_death import RULE as VATGROWN_DEATH_RULE
from girlframe.engine.m3_world_state import Asset, Cell, CorePlan, Gorgon, GorgonType, Location
from girlframe.engine.playbooks import GIRL_TYPES
from girlframe.services.handler_setup import HandlerService
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_careers import end_in_transaction, synchronize_end
from girlframe.services.m3_girl_transition import GirlTransitionService, baseline_id, stage_baseline
from girlframe.services.m3_handler_plays import _ordinary_scene_idle
from girlframe.services.m3_medical import MedicalService
from girlframe.services.m3_quadrant_loss import materialize_loss, require_aftermath_clear
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer

RULE = "situational.situational.timeskip"
KIND = "timeskip"
DURATIONS = {
    6: "Six months",
    12: "One year",
    24: "Two years",
    36: "Three years",
    60: "Five years",
    96: "Eight years",
    120: "A decade",
}


class Arrival(Model):
    kind: Literal["benevolent", "dormant", "erratic"]
    name: str
    type: GorgonType
    assets: tuple[str, ...]
    weakness: str


class Timeskip(Model):
    id: str
    gm: int
    appointment: str
    voters: tuple[int, ...]
    accepted: tuple[int, ...]
    months: int
    step: Literal[
        "agreement",
        "city_ruin",
        "city_foundation",
        "base_ruin",
        "newgirl",
        "death",
        "replacement",
        "base_foundation",
        "declined",
    ]
    city_ruin: str | None = None
    city: str | None = None
    base_ruin: str | None = None
    loss: str | None = None
    graduates: tuple[ActorRef, ...] = ()
    baselines: dict[str, str] = {}
    death: ActorRef | None = None
    death_ballots: tuple[int, ...] = ()
    death_event: str | None = None
    death_archive: str | None = None


def records(state: GameState) -> tuple[Timeskip, ...]:
    return tuple(
        Timeskip.model_validate_json(row["body"]) for row in state.facts if row.get("kind") == KIND
    )


def _local_npcs(state: GameState, cell: Cell) -> dict[str, str]:
    assert state.world is not None
    return {
        npc.id: npc.name
        for npc in state.world.npcs
        if npc.alive
        and resolve(state, ActorRef(kind="npc", entity=npc.id), (), require_alive=False).cell
        == cell
    }


def _end_npcs(
    state: GameState, affected: tuple[str, ...], gm: int, event: str, account: str
) -> GameState:
    assert state.world is not None
    for identity in affected:
        npc = next(x for x in state.world.npcs if x.id == identity)
        ref = ActorRef(kind="npc", entity=identity)
        if (
            npc.controller != gm
            or npc.source_kind is not None
            or category(state, ref) == "harpy"
            or npc.captive_of
        ):
            raise WorkflowError("Resolve an affected non-GM, captive or special NPC with its owner")
        if "director" in npc.jobs:
            state = end_director(state, ref, event, account)
        else:
            state = end_actor_casts(
                end_grasps(interrupt_journeys(state, ref, event, account), ref, event), ref, event
            )
        assert state.world is not None
        state.world = world_rules.update(
            state.world,
            npcs=tuple(
                x.model_copy(update=dict(alive=False)) if x.id == identity else x
                for x in state.world.npcs
            ),
        )
        state.facts.append(
            dict(
                kind="timeskip_npc_ended",
                id=identity,
                event=event,
                body=npc.model_dump_json(),
                account=account,
            )
        )
    return state


class TimeskipService:
    def __init__(self, game: GameService):
        self.game, self.store = game, game.store

    def _gate(self, c: Connection, viewer: GuildViewer) -> None:
        access = Access(self.store)
        access.authorize(c, viewer, "world", director_response=True)
        access.authorize(c, viewer, "plays", director_response=True)
        access.require_specialist_rule(RULE)

    def _current(self, c: Connection, case: Timeskip) -> None:
        if MedicalService(self.store)._handler(c) != (case.gm, case.appointment):
            raise WorkflowError("Recover the original Timeskip facilitator")
        helper = HandlerService(self.store)
        if any(not helper._member(c, uid) for uid in case.voters):
            raise WorkflowError("Resolve the changed Timeskip table with the human GM")

    def _write(
        self,
        viewer: GuildViewer,
        key: str,
        payload: dict[str, Any],
        operation: Callable[[Connection], dict[str, Any]],
    ) -> dict[str, Any]:
        def authorize(c: Connection) -> None:
            self._gate(c, viewer)
            if "id" in payload:
                self._case(c, load_state(c, self.store.campaign_id), viewer, payload["id"])
            elif MedicalService(self.store)._handler(c)[0] != viewer.user_id:
                raise WorkflowError("Only the original human GM can propose a Timeskip")

        try:
            return self.store._write(
                viewer,
                key,
                "m3.timeskip",
                payload,
                operation,
                authorize=authorize,
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
        case: Timeskip,
        operation: str,
        event: str,
    ) -> dict[str, Any]:
        state.facts = [x for x in state.facts if (x.get("kind"), x.get("id")) != (KIND, case.id)]
        state.facts.append(dict(kind=KIND, id=case.id, body=case.model_dump_json()))
        self.game.event(
            c,
            viewer.user_id,
            key,
            "m3.timeskip_" + operation,
            state,
            event_id=event,
            timeskip_id=case.id,
        )
        return dict(id=case.id, step=case.step, event=event)

    def start_menu(self, viewer: GuildViewer) -> int:
        with self.store.engine.connect() as c:
            self._gate(c, viewer)
            state = load_state(c, self.store.campaign_id)
            if MedicalService(self.store)._handler(c)[0] != viewer.user_id or state.world is None:
                raise WorkflowError("The human GM proposes the Timeskip for the existing world")
            if any(case.step != "declined" for case in records(state)):
                raise WorkflowError("Continue the original Timeskip in your private Inbox")
            return state.revision

    def start(self, viewer: GuildViewer, key: str, revision: int, months: int) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            _ordinary_scene_idle(c, self.game)
            state = load_state(c, self.store.campaign_id)
            gm, appointment = MedicalService(self.store)._handler(c)
            require_aftermath_clear(state)
            if (
                gm != viewer.user_id
                or state.world is None
                or state.revision != revision
                or months not in DURATIONS
                or any(case.step != "declined" for case in records(state))
            ):
                raise WorkflowError("Propose one printed duration for the current original world")
            voters = tuple(dict.fromkeys((gm, *state.order)))
            case = Timeskip(
                id=str(uuid4()),
                gm=gm,
                appointment=appointment,
                voters=voters,
                accepted=(gm,),
                months=months,
                step="city_ruin" if voters == (gm,) else "agreement",
            )
            self._current(c, case)
            return self._save(c, state, viewer, key, case, "proposed", case.id)

        return self._write(viewer, key, dict(revision=revision, months=months), operation)

    def _case(
        self, c: Connection, state: GameState, viewer: GuildViewer, identity: str
    ) -> Timeskip:
        case = next((x for x in records(state) if x.id == identity), None)
        if case is None or viewer.user_id not in case.voters:
            raise WorkflowError("The original Timeskip is unavailable")
        self._current(c, case)
        return case

    def vote(
        self, viewer: GuildViewer, key: str, identity: str, revision: int, accept: bool
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            case = self._case(c, state, viewer, identity)
            if (
                case.step != "agreement"
                or viewer.user_id in case.accepted
                or state.revision != revision
                or type(accept) is not bool
            ):
                raise WorkflowError("STALE_TIMESKIP: reopen your original decision")
            if accept:
                accepted = case.accepted + (viewer.user_id,)
                case = case.model_copy(
                    update=dict(
                        accepted=accepted,
                        step="city_ruin" if set(accepted) == set(case.voters) else "agreement",
                    )
                )
            else:
                case = case.model_copy(update=dict(step="declined"))
            return self._save(c, state, viewer, key, case, "vote", str(uuid4()))

        return self._write(
            viewer, key, dict(id=identity, revision=revision, accept=accept), operation
        )

    def _step(self, case: Timeskip, user: int) -> str | None:
        if case.step == "declined":
            return None
        if case.step == "newgirl" and any(
            actor.entity == str(user) and actor.token not in case.baselines
            for actor in case.graduates
        ):
            return "choose_book"
        if case.step == "death" and case.death is not None and user not in case.death_ballots:
            return "death_ballot"
        if user == case.gm or case.step == "agreement" and user not in case.accepted:
            return case.step
        return None

    def tasks(
        self, c: Connection, state: GameState, viewer: GuildViewer
    ) -> tuple[tuple[str, str], ...]:
        original = records(state)
        if not original:
            return ()
        try:
            self._gate(c, viewer)
            current = MedicalService(self.store)._handler(c)
        except (ValueError, WorkflowError):
            return ()
        return tuple(
            (case.id, step)
            for case in original
            if (case.gm, case.appointment) == current
            and viewer.user_id in case.voters
            and (step := self._step(case, viewer.user_id)) is not None
        )

    def get(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self._gate(c, viewer)
            state = load_state(c, self.store.campaign_id)
            case = self._case(c, state, viewer, identity)
            step = self._step(case, viewer.user_id)
            if state.world is None or step is None:
                raise WorkflowError("The original Timeskip choice is unavailable")
            data: dict[str, Any] = dict(
                revision=state.revision,
                step=step,
                duration=DURATIONS[case.months],
                accepted=viewer.user_id in case.accepted,
            )
            if step == "newgirl":
                data["can_continue"] = self._graduated(c, state, case)
            if step == "death" and case.death is None:
                data["people"] = {
                    x.token: label for x, label in self._nominees(c, state, case).items()
                }
            if step in ("death", "death_ballot") and case.death is not None:
                data["nominee"] = self._nominees(c, state, case).get(case.death)
            if step == "replacement":
                data["can_continue"] = self._replacement_ready(state, case)
            kind = {"city_ruin": "city", "base_ruin": "base"}.get(case.step)
            if kind is not None:
                data["locations"] = {
                    location.id: dict(
                        label=location.name,
                        npcs=_local_npcs(state, location.cell) if kind == "base" else {},
                    )
                    for location in state.world.locations
                    if location.kind == kind
                    and location.condition != "destroyed"
                    and not location.protection_sources
                    and (location.ship is None or not location.ship.armoured)
                }
            return data

    def ruin(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        site: str,
        arrival: Arrival,
        occupants: tuple[str, ...],
        account: str,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            _ordinary_scene_idle(c, self.game)
            original = load_state(c, self.store.campaign_id)
            case = self._case(c, original, viewer, identity)
            kind = {"city_ruin": "city", "base_ruin": "base"}.get(case.step)
            if (
                viewer.user_id != case.gm
                or original.world is None
                or kind is None
                or original.revision != revision
                or not 0 < len(account.strip()) <= 1200
            ):
                raise WorkflowError("STALE_TIMESKIP: reopen the original ordered destruction")
            target = next(
                (x for x in original.world.locations if x.id == site and x.kind == kind), None
            )
            if target is None:
                raise WorkflowError("Choose an actual location for this printed step")
            event = str(uuid4())
            assets = tuple(
                Asset(
                    id=event + ":" + str(i), name=x.strip(), description=x.strip(), family="gorgon"
                )
                for i, x in enumerate(arrival.assets)
                if x.strip()
            )
            if (
                len(assets) != world_rules.CLASS_ASSETS[arrival.kind]
                or not arrival.weakness.strip()
            ):
                raise WorkflowError(
                    "Use the exact Class Asset count and describe its Core weakness"
                )
            gorgon = Gorgon(
                id=event,
                name=arrival.name.strip(),
                gorgon_class=arrival.kind,
                types=(arrival.type,),
                cell=target.cell,
                position_event=event,
                assets=assets,
                core_plan=CorePlan(assets=(assets[0].id,), weakness=arrival.weakness.strip()),
            )
            changed = GameState.model_validate_json(original.model_dump_json())
            destroyed = world_rules.destroy(original.world, target.id, gorgon_cause=False)
            if not any(x.kind == "budget_structure_destroyed" for x in destroyed.followups):
                raise WorkflowError("The current location must actually be destroyed")
            changed.world = world_rules.introduce_gorgon(destroyed.world, gorgon, event=event).world
            if len(occupants) != len(set(occupants)) or (
                occupants
                and (
                    kind != "base"
                    or not set(occupants) <= _local_npcs(original, target.cell).keys()
                )
            ):
                raise WorkflowError("Confirm only actual NPCs inside the original base")
            changed = _end_npcs(changed, occupants, case.gm, event, account.strip())
            changed.facts.extend(
                [
                    dict(
                        kind="structure_destroyed_source",
                        id=case.id + ":" + kind,
                        entity=target.id,
                        event=event,
                        source=case.id,
                    ),
                    dict(
                        kind="timeskip_ruin",
                        id=case.id,
                        entity=target.id,
                        gorgon=gorgon.id,
                        event=event,
                        account=account.strip(),
                    ),
                ]
            )
            install_budget(changed)
            loss = stage_loss(
                original,
                changed,
                source=case.id,
                event=event,
                judge=case.gm,
                appointment=case.appointment,
                handler=active_handler(original),
            )
            case = case.model_copy(
                update=(
                    dict(step="city_foundation", city_ruin=target.id)
                    if kind == "city"
                    else dict(
                        step="newgirl",
                        base_ruin=target.id,
                        loss=loss.id if loss else None,
                        graduates=tuple(
                            current_ref(changed, uid)
                            for uid in changed.order
                            if changed.sheets[str(uid)].girl == "NEWGIRL"
                        ),
                    )
                )
            )
            result = self._save(c, changed, viewer, key, case, kind + "_ruined", event)
            if loss:
                materialize_loss(self.game, c, loss, event)
            return result

        return self._write(
            viewer,
            key,
            dict(
                id=identity,
                revision=revision,
                site=site,
                arrival=arrival.model_dump(mode="json"),
                occupants=occupants,
                account=account,
            ),
            operation,
        )

    def establish_city(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        name: str,
        cell: Cell,
        account: str,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            _ordinary_scene_idle(c, self.game)
            state = load_state(c, self.store.campaign_id)
            case = self._case(c, state, viewer, identity)
            if (
                viewer.user_id != case.gm
                or state.world is None
                or case.step != "city_foundation"
                or state.revision != revision
                or not 0 < len(account.strip()) <= 1200
            ):
                raise WorkflowError("STALE_TIMESKIP: reopen the original city establishment")
            require_site(state, cell)
            event = str(uuid4())
            city = Location(id=event, kind="city", name=name.strip(), cell=cell)
            state.world = world_rules.update(state.world, locations=state.world.locations + (city,))
            state.facts.append(
                dict(
                    kind="timeskip_city",
                    id=case.id,
                    entity=city.id,
                    event=event,
                    account=account.strip(),
                )
            )
            case = case.model_copy(update=dict(step="base_ruin", city=city.id))
            return self._save(c, state, viewer, key, case, "city_established", event)

        return self._write(
            viewer,
            key,
            dict(id=identity, revision=revision, name=name, cell=cell, account=account),
            operation,
        )

    def choose_book(
        self, viewer: GuildViewer, key: str, identity: str, revision: int, book: str
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            _ordinary_scene_idle(c, self.game)
            state = load_state(c, self.store.campaign_id)
            require_aftermath_clear(state)
            case = self._case(c, state, viewer, identity)
            girl = next((x for x in case.graduates if x.entity == str(viewer.user_id)), None)
            if (
                case.step != "newgirl"
                or girl is None
                or state.revision != revision
                or girl.token in case.baselines
                or book not in GIRL_TYPES
                or book == "NEWGIRL"
            ):
                raise WorkflowError("Choose a different book for your original Newgirl")
            actual = resolve(
                state, girl, profiles(c, self.store.campaign_id), require_current_profile=False
            )
            sheet = state.sheets[girl.entity]
            if actual.rules != "girl_frame" or sheet.girl != "NEWGIRL":
                raise WorkflowError("Recover the original Newgirl and her current baseline")
            event = str(uuid4())
            state.sheets[girl.entity], fact = change_playbook_runtime(sheet, book, event)
            state.facts.append(fact)
            case = case.model_copy(update=dict(baselines=case.baselines | {girl.token: event}))
            result = self._save(c, state, viewer, key, case, "newgirl_changed", event)
            stage_baseline(c, self.store, girl, fact, event, identity, timeskip=True)
            return result

        return self._write(viewer, key, dict(id=identity, revision=revision, book=book), operation)

    def _graduated(self, c: Connection, state: GameState, case: Timeskip) -> bool:
        try:
            require_aftermath_clear(state)
        except WorkflowError:
            return False
        transitions = GirlTransitionService(self.store)
        for girl in case.graduates:
            event = case.baselines.get(girl.token)
            if event is None:
                return False
            row, body, original = transitions._source(c, baseline_id(case.id, event))
            sheet = state.sheets.get(girl.entity)
            if (
                original != girl
                or row["state"] != "resolved"
                or not body.get("complete")
                or sheet is None
                or sheet.character_id != girl.incarnation
                or sheet.girl != body["new_book"]
                or sheet.girl_runtime is None
                or sheet.girl_runtime.setup is None
                or sheet.girl_runtime.setup.epoch != event
            ):
                return False
        return True

    def advance_newgirl(
        self, viewer: GuildViewer, key: str, identity: str, revision: int
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            _ordinary_scene_idle(c, self.game)
            state = load_state(c, self.store.campaign_id)
            case = self._case(c, state, viewer, identity)
            if (
                viewer.user_id != case.gm
                or case.step != "newgirl"
                or state.revision != revision
                or not self._graduated(c, state, case)
            ):
                raise WorkflowError("Complete the original Newgirl’s baseline before moving on")
            case = case.model_copy(update=dict(step="death"))
            return self._save(c, state, viewer, key, case, "newgirl_completed", str(uuid4()))

        return self._write(
            viewer, key, dict(id=identity, revision=revision, advance=True), operation
        )

    def _nominees(self, c: Connection, state: GameState, case: Timeskip) -> dict[ActorRef, str]:
        if state.world is None:
            return {}
        people = {
            ActorRef(kind="npc", entity=x.id): x.name
            for x in state.world.npcs
            if x.revealed
            and x.alive
            and x.controller == case.gm
            and x.source_kind is None
            and not x.captive_of
            and category(state, ActorRef(kind="npc", entity=x.id)) != "harpy"
        }
        bound = profiles(c, self.store.campaign_id)
        for uid in state.order:
            actor = current_ref(state, uid)
            sheet = state.sheets[actor.entity]
            if uid not in case.voters or has_rule(sheet, VATGROWN_DEATH_RULE, "VATGROWN"):
                continue
            try:
                actual = resolve(state, actor, bound, require_current_profile=False)
            except ValueError:
                continue
            if actual.rules == "girl_frame" and not actual.offstage_source:
                people[actor] = sheet.callsign
        return people

    def nominate(
        self, viewer: GuildViewer, key: str, identity: str, revision: int, nominee: str
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            _ordinary_scene_idle(c, self.game)
            state = load_state(c, self.store.campaign_id)
            case = self._case(c, state, viewer, identity)
            if (
                viewer.user_id != case.gm
                or case.step != "death"
                or case.death is not None
                or state.revision != revision
            ):
                raise WorkflowError("Reopen the original Timeskip death decision")
            selected = next((x for x in self._nominees(c, state, case) if x.token == nominee), None)
            if selected is None:
                raise WorkflowError("Choose one actual original character known to the table")
            case = case.model_copy(update=dict(death=selected, death_ballots=()))
            return self._save(c, state, viewer, key, case, "death_proposed", str(uuid4()))

        return self._write(
            viewer, key, dict(id=identity, revision=revision, nominee=nominee), operation
        )

    def death_vote(
        self, viewer: GuildViewer, key: str, identity: str, revision: int, accept: bool
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            _ordinary_scene_idle(c, self.game)
            state = load_state(c, self.store.campaign_id)
            case = self._case(c, state, viewer, identity)
            if (
                case.step != "death"
                or case.death is None
                or accept
                and case.death not in self._nominees(c, state, case)
                or viewer.user_id in case.death_ballots
                or state.revision != revision
                or type(accept) is not bool
            ):
                raise WorkflowError("STALE_TIMESKIP: reopen the original death decision")
            event = str(uuid4())
            if not accept:
                case = case.model_copy(update=dict(death=None, death_ballots=()))
                return self._save(c, state, viewer, key, case, "death_declined", event)
            ballots = case.death_ballots + (viewer.user_id,)
            case = case.model_copy(update=dict(death_ballots=ballots))
            if set(ballots) != set(case.voters):
                return self._save(c, state, viewer, key, case, "death_voted", event)
            account = "The original table recorded one death during the Timeskip."
            actual = case.death
            assert actual is not None
            if actual.kind == "npc":
                state = _end_npcs(state, (actual.entity,), case.gm, event, account)
                case = case.model_copy(update=dict(step="base_foundation", death_event=event))
                return self._save(c, state, viewer, key, case, "death_committed", event)
            archive = str(uuid4())
            state = end_in_transaction(
                c,
                self.game,
                state,
                actual,
                reason="death",
                source_event=event,
                account=account,
                archive_id=archive,
            )
            case = case.model_copy(
                update=dict(step="replacement", death_event=event, death_archive=archive)
            )
            result = self._save(c, state, viewer, key, case, "death_committed", event)
            actual_archive = next(x for x in state.career_archives if x.id == archive)
            synchronize_end(c, self.game, actual_archive)
            return result

        return self._write(
            viewer, key, dict(id=identity, revision=revision, death_vote=accept), operation
        )

    def _replacement_ready(self, state: GameState, case: Timeskip) -> bool:
        if not case.death_archive or not case.death or case.death.kind != "pilot":
            return False
        current = binding(state, int(case.death.entity))
        sheet = state.sheets.get(case.death.entity)
        return bool(
            current
            and current.active
            and current.previous_archive == case.death_archive
            and sheet
            and sheet.character_id == current.character
            and sheet.girl == "NEWGIRL"
        )

    def advance_replacement(
        self, viewer: GuildViewer, key: str, identity: str, revision: int
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            _ordinary_scene_idle(c, self.game)
            state = load_state(c, self.store.campaign_id)
            case = self._case(c, state, viewer, identity)
            if (
                viewer.user_id != case.gm
                or case.step != "replacement"
                or state.revision != revision
                or not self._replacement_ready(state, case)
            ):
                raise WorkflowError("Complete the original owner’s actual Newgirl activation")
            case = case.model_copy(update=dict(step="base_foundation"))
            return self._save(c, state, viewer, key, case, "replacement_activated", str(uuid4()))

        return self._write(
            viewer, key, dict(id=identity, revision=revision, activated=True), operation
        )
