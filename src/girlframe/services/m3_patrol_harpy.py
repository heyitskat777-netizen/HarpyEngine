"""Original Handler's source-bound patrol event and the actual observer's private knowledge."""

import json
from typing import Any, Literal, cast
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_patrol_harpy as rules
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef, Model, SceneCast
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_handler_consequences import active_handler, same_handler_body
from girlframe.engine.m3_world_state import AdversaryPilot
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_actor_history import snapshot_profiles
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_dose_up import _cast
from girlframe.services.m3_handler_advancements import _history
from girlframe.services.m3_strain import StrainService
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer


def _get[T: Model](state: GameState, model: type[T], key: str) -> T:
    try:
        return rules.get(state, model, key)
    except ValueError as error:
        raise WorkflowError(str(error)) from None


def _row(game: GameService, c: Connection, work: str, *, first: bool = False) -> dict[str, Any]:
    table = t.m3["m3_required_work"]
    row = (
        c.execute(
            sa.select(table)
            .where(table.c.campaign_id == game.store.campaign_id, table.c.id == work)
            .order_by(table.c.revision if first else table.c.revision.desc())
            .limit(1)
        )
        .mappings()
        .first()
    )
    if row is None:
        raise WorkflowError("Recover this actual selected Low Void event")
    return dict(row)


def _source(
    game: GameService, c: Connection, work: str
) -> tuple[dict[str, Any], ActorRef, GameState]:
    row = _row(game, c, work, first=True)
    body = json.loads(row["body_json"])
    event = (
        c.execute(
            sa.select(t.events).where(
                t.events.c.campaign_id == game.store.campaign_id, t.events.c.id == row["event_id"]
            )
        )
        .mappings()
        .first()
    )
    payload = json.loads(event["payload_json"]) if event else {}
    source = _history(c, game, row["event_id"])
    selection = (
        next((x for x in source.strain.events if x.id == body.get("source_work")), None)
        if source.strain
        else None
    )
    handler = active_handler(source)
    if (
        row["kind"] != "strain_event"
        or body.get("rule_id") != rules.RULE
        or event is None
        or event["kind"] != "m3.strain_option_saved"
        or event["actor_id"] != row["owner_id"]
        or payload.get("rule_id") != rules.RULE
        or payload.get("work_id") != body.get("source_work")
        or handler is None
        or source.handler != int(row["owner_id"])
        or selection is None
        or selection.period_id != row["off_duty_id"]
        or (selection.track, selection.severity, selection.face, selection.column)
        != ("void", "low", 3, 1)
    ):
        raise WorkflowError("Prove the original Handler's actual Low Void die3 column1 choice")
    return row, handler, source


def _original_handler(
    game: GameService,
    c: Connection,
    state: GameState,
    viewer: GuildViewer,
    work: str,
    revision: int,
) -> dict[str, Any]:
    first, original, _ = _source(game, c, work)
    row = _row(game, c, work)
    from girlframe.services.m3_missions import MissionService
    from girlframe.services.m3_off_duty import OffDutyService

    strain = StrainService(OffDutyService(MissionService(game.store)))
    strain._authorize(c, viewer)
    strain.missions.access.authorize(c, viewer, "world")
    if strain.missions.access.registry is None:
        raise WorkflowError("Recover the approved actual patrol rule source")
    strain.missions.access.registry.require_available(rules.RULE)
    game.unpaused(c)
    strain._check(c, viewer, row, revision)
    if viewer.user_id != int(first["owner_id"]) or not same_handler_body(state, original):
        raise WorkflowError("Only the actual original Handler stages this patrol source")
    return row


def validate_introduction(
    game: GameService,
    c: Connection,
    state: GameState,
    viewer: GuildViewer,
    work: str,
    work_revision: int,
    pilot: AdversaryPilot,
) -> None:
    """Root World owns introduction; this proves its one real pending source without writes."""
    _original_handler(game, c, state, viewer, work, work_revision)
    if pilot.kind != "harpy" or pilot.controller != viewer.user_id:
        raise WorkflowError("The original Handler controls this genuine new World Harpy")


def _context(
    game: GameService,
    c: Connection,
    state: GameState,
    observer: ActorRef,
    harpy: ActorRef,
    channel: int,
) -> tuple[SceneCast, AdversaryPilot, Any, Any]:
    from girlframe.services.m3_harpy_defeat import HarpyDefeatService

    HarpyDefeatService(game.store, game=game)._runtime(c, state, harpy)
    scene = _cast(game, c, state, channel)
    bound = snapshot_profiles(c, game.store.campaign_id, state)
    body, target = (
        resolve(state, actor, bound, require_current_profile=False) for actor in (observer, harpy)
    )
    entity = (
        next((x for x in state.world.pilots if x.id == harpy.entity), None) if state.world else None
    )
    if (
        observer.kind != "pilot"
        or current_ref(state, int(observer.entity)) != observer
        or harpy.kind != "external_pilot"
        or entity is None
        or entity.kind != "harpy"
        or not body.alive
        or not target.alive
        or body.offstage_source
        or target.offstage_source
        or not body.vessel_id
        or not target.vessel_id
        or not body.position_sha256
        or not target.position_sha256
        or body.cell is None
        or body.cell != target.cell
        or body.custody not in (None, "free")
        or target.custody not in (None, "free")
        or not any(x.actor == observer and x.controller == body.controller for x in scene.roles)
    ):
        raise WorkflowError(
            "Use actual present original patrol bodies and a genuinely joined scene"
        )
    return scene, entity, body, target


def prove_encounter(
    game: GameService, c: Connection, state: GameState, identity: str
) -> rules.Encounter:
    value = _get(state, rules.Encounter, identity)
    row, handler, source = _source(game, c, value.work)
    born = _history(c, game, value.event)
    event = (
        c.execute(
            sa.select(t.events).where(
                t.events.c.campaign_id == game.store.campaign_id, t.events.c.id == value.event
            )
        )
        .mappings()
        .first()
    )
    # Historical readback uses the saved actual cast, not today's SQL scene lifecycle.
    from girlframe.services.m3_harpy_defeat import HarpyDefeatService

    HarpyDefeatService(game.store, game=game)._runtime(c, born, value.harpy)
    bound = snapshot_profiles(c, game.store.campaign_id, born)
    observer, harpy = (
        resolve(born, x, bound, require_current_profile=False)
        for x in (value.observer, value.harpy)
    )
    if (
        value != _get(born, rules.Encounter, identity)
        or value.handler != handler
        or value.source_event != row["event_id"]
        or value.controller != int(row["owner_id"])
        or event is None
        or event["kind"] != "m3.patrol_harpy_staged"
        or event["actor_id"] != str(value.controller)
        or json.loads(event["payload_json"]).get("encounter") != value.id
        or value.observer.entity not in source.sheets
        or source.sheets[value.observer.entity].character_id != value.observer.incarnation
        or observer.controller != value.observer_controller
        or observer.cell != harpy.cell
        or observer.vessel_id != value.observer_vessel
        or observer.position_sha256 != value.observer_position
        or harpy.vessel_id != value.harpy_vessel
        or harpy.position_sha256 != value.harpy_position
        or not born.world
        or value.harpy_body not in born.world.pilots
        or value.harpy_body.id != value.harpy.entity
        or value.harpy_body.kind != "harpy"
        or not any(
            x.actor == value.observer and x.controller == value.observer_controller
            for x in value.cast.roles
        )
    ):
        raise WorkflowError("Preserve the actual original patrol, physical Harpy and human source")
    return value


def prove_sighting(
    game: GameService, c: Connection, state: GameState, identity: str
) -> rules.Sighting:
    value = _get(state, rules.Sighting, identity)
    encounter = prove_encounter(game, c, state, value.encounter)
    born = _history(c, game, value.event)
    event = (
        c.execute(
            sa.select(t.events).where(
                t.events.c.campaign_id == game.store.campaign_id, t.events.c.id == value.event
            )
        )
        .mappings()
        .first()
    )
    row = _row(game, c, value.work)
    if (
        value != _get(born, rules.Sighting, identity)
        or value.work != encounter.work
        or value.id != rules.identity("sighting", encounter.id)
        or event is None
        or event["kind"] != "m3.patrol_harpy_observed"
        or event["actor_id"] != str(encounter.controller)
        or json.loads(event["payload_json"]).get("sighting") != value.id
        or json.loads(event["payload_json"]).get("face") != value.face
        or row["state"] != "resolved"
        or row["event_id"] != value.event
        or json.loads(row["body_json"]).get("patrol_sighting") != value.id
        or json.loads(row["body_json"]).get("patrol_encounter") != encounter.id
    ):
        raise WorkflowError("Recover the canonical once-only patrol observation die")
    return value


def knows(
    game: GameService, c: Connection, state: GameState, observer: ActorRef, harpy: ActorRef
) -> bool:
    for sighting in rules.records(state, rules.Sighting):
        encounter = _get(state, rules.Encounter, sighting.encounter)
        if encounter.observer == observer and encounter.harpy == harpy:
            prove_sighting(game, c, state, sighting.id)
            return True
    return False


class PatrolHarpyService:
    def __init__(self, strain: StrainService):
        self.strain, self.store, self.game = strain, strain.store, strain.game

    def stage(
        self,
        viewer: GuildViewer,
        key: str,
        work: str,
        revision: int,
        game_revision: int,
        observer: ActorRef,
        harpy: ActorRef,
        channel: int,
        account: str,
    ) -> dict[str, Any]:
        if not account.strip() or len(account) > 1200:
            raise WorkflowError("Record the actual patrol and visual contact")

        def operation(c: Connection) -> dict[str, Any]:
            state = self.strain._state(c, game_revision)
            row = _original_handler(self.game, c, state, viewer, work, revision)
            first, handler, source = _source(self.game, c, work)
            if (
                observer.entity not in source.sheets
                or source.sheets[observer.entity].character_id != observer.incarnation
            ):
                raise WorkflowError("Choose an original actual Girl of this source Cadre")
            scene, entity, body, target = _context(self.game, c, state, observer, harpy, channel)
            event = str(uuid4())
            value = rules.Encounter(
                id=rules.identity(work, event),
                work=work,
                source_event=first["event_id"],
                handler=handler,
                controller=viewer.user_id,
                observer=observer,
                observer_controller=body.controller,
                observer_vessel=body.vessel_id,
                observer_position=body.position_sha256,
                harpy=harpy,
                harpy_body=entity,
                harpy_vessel=target.vessel_id,
                harpy_position=target.position_sha256,
                cast=scene,
                account=account.strip(),
                event=event,
            )
            rules.put(state, value)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.patrol_harpy_staged",
                state,
                event_id=event,
                encounter=value.id,
                work=work,
            )
            self.strain._save(
                c, row, event, json.loads(row["body_json"]) | dict(patrol_encounter=value.id)
            )
            return dict(id=work, encounter=value.id)

        return self.store._write(
            viewer,
            key,
            "m3.patrol_harpy_staged",
            dict(
                work=work,
                revision=revision,
                game_revision=game_revision,
                observer=observer.model_dump(mode="json"),
                harpy=harpy.model_dump(mode="json"),
                channel=channel,
                account=account,
            ),
            operation,
            auto_audit=False,
            authorize=lambda c: self.strain._authorize(c, viewer),
        )

    def roll(
        self, viewer: GuildViewer, key: str, work: str, revision: int, game_revision: int
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            state = self.strain._state(c, game_revision)
            row = _original_handler(self.game, c, state, viewer, work, revision)
            encounter = prove_encounter(
                self.game, c, state, json.loads(row["body_json"]).get("patrol_encounter", "")
            )
            scene, entity, body, target = _context(
                self.game, c, state, encounter.observer, encounter.harpy, encounter.cast.channel
            )
            if (
                scene != encounter.cast
                or entity != encounter.harpy_body
                or (body.position_sha256, body.vessel_id, target.position_sha256, target.vessel_id)
                != (
                    encounter.observer_position,
                    encounter.observer_vessel,
                    encounter.harpy_position,
                    encounter.harpy_vessel,
                )
            ):
                raise WorkflowError(
                    "STALE_PATROL: restage actual current bodies before the extra die"
                )
            event = str(uuid4())
            value = rules.Sighting(
                id=rules.identity("sighting", encounter.id),
                encounter=encounter.id,
                work=work,
                face=self.strain.dice.roll_d6(),
                rng_source=cast(Literal["os", "test_injected"], self.strain.rng_source),
                event=event,
            )
            rules.put(state, value)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.patrol_harpy_observed",
                state,
                event_id=event,
                sighting=value.id,
                work=work,
                face=value.face,
            )
            self.strain._save(
                c,
                row,
                event,
                json.loads(row["body_json"]) | dict(patrol_sighting=value.id),
                resolved=True,
            )
            return dict(id=work, sighting=value.id, mood=value.mood)

        return self.store._write(
            viewer,
            key,
            "m3.patrol_harpy_observed",
            dict(work=work, revision=revision, game_revision=game_revision),
            operation,
            auto_audit=False,
            authorize=lambda c: self.strain._authorize(c, viewer),
        )

    def get(self, viewer: GuildViewer, work: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            from girlframe.services.m3_access import Access

            gate = Access(self.store)
            gate.authorize(c, viewer, "strain", director_response=True)
            if gate.registry is None:
                raise WorkflowError("Recover the actual patrol source registry")
            gate.registry.require_available(rules.RULE)
            row, handler, source = _source(self.game, c, work)
            current = _row(self.game, c, work)
            state = load_state(c, self.store.campaign_id)
            body = json.loads(current["body_json"])
            value = (
                prove_encounter(self.game, c, state, body["patrol_encounter"])
                if body.get("patrol_encounter")
                else None
            )
            sighting = (
                prove_sighting(self.game, c, state, body["patrol_sighting"])
                if body.get("patrol_sighting")
                else None
            )
            owner = viewer.user_id == int(row["owner_id"])
            if not owner and not (
                sighting and value and viewer.user_id == value.observer_controller
            ):
                raise WorkflowError(
                    "Only the original Handler and actual observer read this private sighting"
                )
            observers = []
            if owner and current["state"] == "pending":
                for sheet in state.sheets.values():
                    actual = current_ref(state, sheet.owner)
                    if (
                        actual.entity in source.sheets
                        and source.sheets[actual.entity].character_id == actual.incarnation
                    ):
                        observers.append(
                            dict(ref=actual.model_dump(mode="json"), label=sheet.callsign)
                        )
            channels = []
            if owner:
                scenes = t.m2["m2_scenes"]
                for channel in c.scalars(
                    sa.select(scenes.c.channel_id).where(
                        scenes.c.campaign_id == self.store.campaign_id
                    )
                ):
                    try:
                        scene = _cast(self.game, c, state, int(channel))
                    except (WorkflowError, ValueError):
                        continue
                    channels.append(
                        dict(id=str(scene.channel), label="Actual scene " + str(scene.channel))
                    )
            cells: set[tuple[int, int]] = set()
            for candidate in observers:
                cell = resolve(
                    state,
                    ActorRef.model_validate(candidate["ref"]),
                    profiles(c, self.store.campaign_id),
                ).cell
                if cell is not None:
                    cells.add(cell)
            established = {x.id for x in state.native_harpies} | {x.id for x in state.harpy_states}
            setup_pending = {
                x.facts.actor.entity for x in state.harpy_setups if x.state == "proposed"
            }
            return dict(
                id=work,
                revision=current["revision"],
                game_revision=state.revision,
                state=current["state"],
                can_stage=owner and current["state"] == "pending",
                can_roll=owner and current["state"] == "pending" and value is not None,
                encounter=(
                    value.model_dump(mode="json")
                    if owner
                    else dict(
                        id=value.id,
                        work=value.work,
                        observer=value.observer.model_dump(mode="json"),
                        harpy=value.harpy.model_dump(mode="json"),
                        account=value.account,
                        event=value.event,
                        harpy_body=dict(name=value.harpy_body.name),
                    )
                )
                if value
                else None,
                sighting=sighting.model_dump(mode="json") | dict(mood=sighting.mood)
                if sighting
                else None,
                observers=observers,
                channels=channels,
                can_introduce=owner
                and current["state"] == "pending"
                and not any(
                    x.get("kind") == "patrol_harpy_introduction" and x.get("work") == work
                    for x in state.facts
                ),
                cells=sorted(cells),
                setups=[
                    dict(
                        ref=ActorRef(kind="external_pilot", entity=x.id).model_dump(mode="json"),
                        label=x.name,
                    )
                    for x in state.world.pilots
                    if x.kind == "harpy"
                    and x.alive
                    and x.controller == viewer.user_id
                    and x.id not in established | setup_pending
                ]
                if owner and state.world and current["state"] == "pending"
                else [],
                harpies=[
                    dict(
                        ref=ActorRef(kind="external_pilot", entity=x.id).model_dump(mode="json"),
                        label=x.name,
                    )
                    for x in state.world.pilots
                    if x.kind == "harpy" and x.alive and x.custody == "free" and x.id in established
                ]
                if owner and state.world
                else [],
            )

    view = get

    def _tasks(self, c: Connection, viewer: GuildViewer) -> list[dict[str, Any]]:
        state = load_state(c, self.store.campaign_id)
        result = []
        table = t.m3["m3_required_work"]
        seen = set()
        for row in c.execute(
            sa.select(table)
            .where(table.c.campaign_id == self.store.campaign_id, table.c.kind == "strain_event")
            .order_by(table.c.revision.desc())
        ).mappings():
            if row["id"] in seen:
                continue
            seen.add(row["id"])
            body = json.loads(row["body_json"])
            if body.get("rule_id") != rules.RULE or not body.get("patrol_sighting"):
                continue
            encounter = next(
                (
                    x
                    for x in rules.records(state, rules.Encounter)
                    if x.id == body.get("patrol_encounter")
                ),
                None,
            )
            if viewer.user_id != int(row["owner_id"]) and not (
                body.get("patrol_sighting")
                and encounter
                and viewer.user_id == encounter.observer_controller
            ):
                continue
            result.append(
                dict(
                    id=row["id"],
                    revision=row["revision"],
                    label="Actual patrol Harpy sighting",
                    pending=row["state"] == "pending" and viewer.user_id == int(row["owner_id"]),
                )
            )
        return result
