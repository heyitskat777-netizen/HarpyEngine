"""Source-bound actual nuclear drops, owned resource choices and genuine immediate endings."""

import ast
import json
from typing import Any
from uuid import NAMESPACE_URL, uuid4, uuid5

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_a_bomb as rules
from girlframe.engine import m3_a_bomb_budget as budget
from girlframe.engine import m3_contaminant_zone as contaminant
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_battle import end_actor_casts
from girlframe.engine.m3_collateral import Selection, Source, perform
from girlframe.engine.m3_handler_consequences import same_handler_body
from girlframe.engine.m3_item_state import HeldItem
from girlframe.engine.m3_missions import Mission
from girlframe.engine.m3_strain import copy as strain_copy
from girlframe.engine.m3_world import update
from girlframe.engine.m3_world_state import Cell, Fallout
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_advancement_acquisition import held, prove, record_spend
from girlframe.services.m3_handler_advancements import HandlerAdvancementService, _history
from girlframe.services.m3_medical import MedicalService
from girlframe.services.onboarding import OnboardingStore, WorkflowError
from girlframe.services.read_only_bot import GuildViewer


def paid(game: GameService, c: Connection, state: GameState, identity: str) -> rules.Acquisition:
    return prove(
        game,
        c,
        state,
        identity,
        rule=rules.RULE,
        receipts=rules.acquisitions,
        missing="Recover the actual nuclear advancement",
        failure="Preserve the original actual award and Handler source",
    )


def _current(
    game: GameService,
    c: Connection,
    state: GameState,
    source: rules.Acquisition,
    viewer: GuildViewer,
) -> None:
    human, appointment = MedicalService(game.store)._handler(c)
    if (
        (str(human), appointment) != (source.handler.entity, source.appointment)
        or viewer.user_id != human
        or not same_handler_body(state, source.handler)
    ):
        raise WorkflowError("Only the original current source Handler controls this advancement")


def _before(game: GameService, c: Connection, event: str) -> GameState:
    from girlframe.services.m3_girl_insurance import _before as before

    return before(game, c, event)


def _copy(state: GameState, changed: GameState) -> None:
    for field in GameState.model_fields:
        setattr(state, field, getattr(changed, field))


def roster(state: GameState, cells: tuple[Cell, ...]) -> tuple[rules.Resource, ...]:
    if state.world is None:
        raise WorkflowError("Use the actual initialized map")
    result: list[rules.Resource] = []
    if any(x.cell is None or x.cell in cells for x in state.parked_frames):
        raise WorkflowError(
            "UNSUPPORTED_BLAST_PARKED_FRAME: actual old Frame/Core damage adapter required"
        )
    for uid in state.order:
        sheet = state.sheets[str(uid)]
        actor = ActorRef(kind="pilot", entity=str(uid), incarnation=sheet.character_id)
        body = next((x for x in state.placements if x.actor == actor), None)
        if body is None or body.girl_cell is None or body.frame_cell is None:
            raise WorkflowError(
                "Resolve every current original body's actual position before this area blast"
            )
        if body.girl_cell not in cells and body.frame_cell not in cells:
            continue
        if (
            sheet.girl == "AM"
            or body.occupied_frame_owner is not None
            or body.subsumed
            or body.frame_cell in cells
            and (
                sheet.frame in ("JANUS", "JANUS-B")
                or sheet.frame_runtime is not None
                and sheet.frame_runtime.core_id is not None
            )
        ):
            raise WorkflowError(
                "UNSUPPORTED_BLAST_BODY: independent/conditional hardware needs its "
                "exact source port"
            )
        if body.frame_cell in cells:
            result.append(
                rules.Resource(
                    actor=actor,
                    controller=uid,
                    family="frame",
                    frame=body.frame_instance,
                    vessel=body.vessel_id,
                    cell=body.frame_cell,
                    assets=tuple(
                        x.id for x in sheet.assets if x.family == "frame" and not x.damaged
                    ),
                    original=sheet.model_dump_json(),
                )
            )
    for target in state.world.gorgons:
        if not target.alive:
            continue
        if target.cell is None:
            raise WorkflowError("Resolve actual unknown Gorgon positions before this area blast")
        if target.cell not in cells or target.gorgon_class == "sprite":
            continue
        if target.flesh_layers is not None:
            raise WorkflowError("UNSUPPORTED_BLAST_LAYERS: resolve the actual layered Gorgon port")
        result.append(
            rules.Resource(
                actor=ActorRef(kind="gorgon", entity=target.id),
                controller=resolve(state, ActorRef(kind="gorgon", entity=target.id), ()).controller,
                family="gorgon",
                cell=target.cell,
                assets=tuple(x.id for x in target.assets if not x.damaged),
                original=target.model_dump_json(),
            )
        )
    from girlframe.engine.m3_harpy_defeat import harpy
    from girlframe.engine.m3_harpy_resources import assets as harpy_assets

    harpy_ids = {x.id for x in state.world.pilots if x.alive and x.kind == "harpy"} | {
        x.id for x in state.harpy_states if x.alive
    }
    for external in state.world.pilots:
        if external.alive and external.kind != "harpy" and external.cell in cells:
            raise WorkflowError(
                "UNSUPPORTED_BLAST_EXTERNAL: actual external body/Frame port required"
            )
    for identity in sorted(harpy_ids):
        harpy_ref = ActorRef(kind="external_pilot", entity=identity)
        try:
            runtime = harpy(state, harpy_ref)
        except ValueError as error:
            raise WorkflowError(str(error)) from None
        actual = resolve(state, harpy_ref, (), require_current_profile=False)
        if actual.cell is None or actual.frame_cell is None:
            raise WorkflowError("Establish the actual Harpy body and Frame positions")
        if actual.cell in cells and not actual.inside_frame:
            raise WorkflowError(
                "UNSUPPORTED_BLAST_DETACHED_HARPY: actual outside-body death port required"
            )
        if actual.frame_cell in cells:
            if actual.frame_instance is None or actual.inside_frame is not True:
                raise WorkflowError("UNSUPPORTED_BLAST_HARPY_FRAME: detached Frame port required")
            result.append(
                rules.Resource(
                    actor=harpy_ref,
                    controller=actual.controller,
                    family="frame",
                    frame=actual.frame_instance,
                    cell=actual.frame_cell,
                    assets=tuple(
                        x.id
                        for x in harpy_assets(state, harpy_ref)
                        if x.family == "frame" and not x.damaged
                    ),
                    original=runtime.model_dump_json(),
                )
            )
    for npc in state.world.npcs:
        if not npc.alive:
            continue
        physical = resolve(
            state, ActorRef(kind="npc", entity=npc.id), (), require_current_profile=False
        )
        if physical.offstage_source or physical.cell != npc.cell:
            raise WorkflowError(
                "UNSUPPORTED_BLAST_NPC_POSITION: prove the actual overlaid body; "
                "never target a stale world label"
            )
    if any(x.alive and x.cell in cells and "director" in x.jobs for x in state.world.npcs):
        raise WorkflowError(
            "UNSUPPORTED_BLAST_DIRECTOR: actual conditional death continuation required"
        )
    return tuple(result)


def prove_drop(game: GameService, c: Connection, state: GameState, identity: str) -> rules.Drop:
    value = next((x for x in rules.drops(state) if x.id == identity), None)
    if value is None:
        raise WorkflowError("Recover the actual original nuclear drop")
    source = paid(game, c, state, value.acquisition)
    born = _history(c, game, value.event)
    original = next((x for x in rules.drops(born) if x.id == identity), None)
    audit = c.execute(
        sa.select(t.events.c.kind, t.events.c.actor_id, t.events.c.payload_json).where(
            t.events.c.campaign_id == game.store.campaign_id, t.events.c.id == value.event
        )
    ).first()
    mutable = {
        "resources",
        "causal",
        "causal_event",
        "causal_account",
        "mission_resolved_event",
        "initial_event",
        "completed_event",
        "loss",
    }
    if (
        original is None
        or audit is None
        or audit.kind != "m3.a_bomb_dropped"
        or audit.actor_id != source.handler.entity
        or json.loads(audit.payload_json).get("drop") != identity
        or any(
            getattr(value, k) != getattr(original, k)
            for k in rules.Drop.model_fields
            if k not in mutable
        )
    ):
        raise WorkflowError("Preserve immutable canonical actual drop, original Handler and source")
    if (
        (value.handler, value.appointment) != (source.handler, source.appointment)
        or value.cells != rules.footprint(value.centre)
        or len(set(value.options)) != 2
    ):
        raise WorkflowError("Preserve the real footprint and exactly two printed choices")
    before = _before(game, c, value.event)
    from girlframe.services.m3_items import prove_item

    prior_item = prove_item(c, game, before, value.device)
    if (
        prior_item.model_dump_json() != value.device_json
        or prior_item.condition != "intact"
        or prior_item.asset_json is not None
        or prior_item.holder != value.handler
    ):
        raise WorkflowError("Prove the actual original device before its irreversible drop")
    device = next(
        (
            x
            for x in rules.devices(before)
            if x.item == value.device and x.acquisition == value.acquisition
        ),
        None,
    )
    if device is None or device not in rules.devices(_history(c, game, device.event)):
        raise WorkflowError("Prove the nuclear capability's actual owned factual source")
    certification = c.execute(
        sa.select(t.events.c.kind, t.events.c.actor_id, t.events.c.payload_json).where(
            t.events.c.campaign_id == game.store.campaign_id, t.events.c.id == device.event
        )
    ).first()
    if (
        certification is None
        or certification.kind != "m3.a_bomb_device_confirmed"
        or certification.actor_id != source.handler.entity
        or json.loads(certification.payload_json).get("device") != device.id
        or device.handler != source.handler
        or device.appointment != source.appointment
    ):
        raise WorkflowError("Preserve the actual original nuclear capability certification")
    release = resolve(before, source.handler, (), require_current_profile=False)
    if (
        release.cell != value.release
        or release.offstage_source
        or release.custody not in (None, "free")
    ):
        raise WorkflowError(
            "Preserve the original Handler's actual available canonical release position"
        )
    if roster(before, value.cells) != original.resources:
        raise WorkflowError("Preserve the actual original resource roster, bodies and cells")
    consumed = next((x for x in born.held_items if x.id == value.device), None)
    if consumed is None or consumed.condition != "ruined" or consumed.state_event != value.event:
        raise WorkflowError("The actual nuclear device must be consumed by this one drop")
    if len(value.resources) != len(original.resources) or any(
        a.model_copy(update=dict(losses=(), event=None, work=())) != b
        for a, b in zip(value.resources, original.resources, strict=True)
    ):
        raise WorkflowError("Preserve original body/resource addresses throughout damage")
    for row in value.resources:
        if row.event:
            saved = next(
                (x for x in rules.drops(_history(c, game, row.event)) if x.id == identity), None
            )
            if saved is None or row not in saved.resources:
                raise WorkflowError("Prove the actual original owner's damage selection")
    for field, kind in (
        ("initial_event", "m3.a_bomb_initial_effects"),
        ("completed_event", "m3.a_bomb_complete"),
        ("causal_event", "m3.a_bomb_mission_cause"),
        ("mission_resolved_event", "m3.mission_rewards_committed"),
    ):
        endpoint = getattr(value, field)
        if endpoint:
            saved = next(
                (x for x in rules.drops(_history(c, game, endpoint)) if x.id == identity), None
            )
            audit_kind = c.scalar(
                sa.select(t.events.c.kind).where(
                    t.events.c.campaign_id == game.store.campaign_id, t.events.c.id == endpoint
                )
            )
            if saved is None or getattr(saved, field) != endpoint or audit_kind != kind:
                raise WorkflowError("Preserve each source-owned canonical blast endpoint")
    return value


def prove_consumed_item(game: GameService, c: Connection, state: GameState, item: HeldItem) -> None:
    value = next(
        (x for x in rules.drops(state) if x.device == item.id and x.event == item.state_event), None
    )
    if value is None:
        raise WorkflowError("Recover this actual consumed device's nuclear source")
    prove_drop(game, c, state, value.id)
    born = next(x for x in _history(c, game, value.event).held_items if x.id == item.id)
    if born != item:
        raise WorkflowError("Preserve the actual spent device without duplication/rearming")


def kill_rostered_sprite(
    game: GameService, c: Connection, state: GameState, drop: str, target: str, event: str
) -> None:
    value = prove_drop(game, c, state, drop)
    assert state.world is not None
    original = value.sprites.get(target)
    actual = next((x for x in state.world.gorgons if x.id == target and x.alive), None)
    if (
        original is None
        or actual is None
        or actual.model_dump_json() != original
        or actual.gorgon_class != "sprite"
        or actual.cell not in value.cells
    ):
        raise WorkflowError("Only the immutable actual-drop Sprite roster grants blast death")
    # This is the printed nuclear death, not a decisive exposed-Core strike.
    state.world = update(
        state.world,
        gorgons=tuple(
            x.model_copy(update=dict(alive=False)) if x.id == target else x
            for x in state.world.gorgons
        ),
    )
    _copy(state, end_actor_casts(state, ActorRef(kind="gorgon", entity=target), event))


def expire_fallout(game: GameService, c: Connection, state: GameState, event: str) -> bool:
    if state.world is None:
        return False
    zones = [x for x in state.world.fallout if x.temporary and x.expired_event is None]
    for zone in zones:
        prove_drop(game, c, state, zone.id)
    if not zones:
        return False
    ids = {x.id for x in zones}
    state.world = update(
        state.world,
        fallout=tuple(
            x.model_copy(update=dict(expired_event=event)) if x.id in ids else x
            for x in state.world.fallout
        ),
        locations=tuple(
            x.model_copy(
                update=dict(fallout_sources=tuple(z for z in x.fallout_sources if z not in ids))
            )
            for x in state.world.locations
        ),
    )
    return True


def finish_mission(
    game: GameService, c: Connection, state: GameState, mission: Mission, success: bool, event: str
) -> None:
    for value in rules.drops(state):
        if (
            value.mission != mission.id
            or value.mission_resolved_event
            or "mission_budget" not in value.options
        ):
            continue
        prove_drop(game, c, state, value.id)
        if value.causal is None:
            raise WorkflowError(
                "The real source judge must record whether this actual drop led to the "
                "Mission result"
            )
        for operation in state.facts:
            if operation.get("kind") != "a_bomb_budget_operation":
                continue
            saved = _history(c, game, operation["event"])
            if not any(
                x.get("kind") == "a_bomb_budget_operation"
                and all(
                    x.get(k) == operation.get(k) for k in ("source", "event", "ordinal", "value")
                )
                for x in saved.facts
            ):
                raise WorkflowError(
                    "Preserve every genuine Budget writer, including unchanged High/Low"
                )
        budget.waive_operation(state, value.id, event=event, waive=success and value.causal)
        rules.put(state, value.model_copy(update=dict(mission_resolved_event=event)))


def prepare_ejections(
    game: GameService, c: Connection, before: GameState, state: GameState, event: str
) -> None:
    new = [
        x for x in state.facts if x.get("kind") == "a_bomb_actual_exit" and x.get("event") == event
    ]
    for old in before.placements:
        changed = next((x for x in state.placements if x.actor == old.actor), None)
        from girlframe.engine.m3_physical import occupied_frame

        occupied = occupied_frame(old)
        hazardous = (
            occupied is not None
            and old.girl_cell is not None
            and rules.radiation_drops(before, occupied[0], occupied[1], old.girl_cell)
        )
        if (
            changed
            and old.mode != "outside_frame"
            and changed.mode == "outside_frame"
            and hazardous
            and not any(x.get("actor") == old.actor.model_dump_json() for x in new)
        ):
            raise WorkflowError("UNPORTED_BLAST_EJECTION: preserve the actual typed exit producer")
    from girlframe.services.m3_careers import end_in_transaction

    for exit in new:
        actor = ActorRef.model_validate_json(exit["actor"])
        body = next((x for x in before.placements if x.actor == actor), None)
        if body is None or body.vessel_id != exit["vessel"] or body.mode == "outside_frame":
            raise WorkflowError("Radiation needs the actual original occupied body's ejection")
        if (
            actor.entity not in state.sheets
            or state.sheets[actor.entity].character_id != actor.incarnation
        ):
            continue
        owner = ActorRef.model_validate_json(exit["owner"])
        sheet = state.sheets.get(owner.entity)
        if sheet is None or any(x.family == "frame" and not x.damaged for x in sheet.assets):
            continue
        affected = []
        for value in rules.drops(before):
            zone = (
                next((x for x in before.world.fallout if x.id == value.id), None)
                if before.world
                else None
            )
            if (
                zone is None
                or zone.expired_event is not None
                or ast.literal_eval(exit["cell"]) not in value.cells
            ):
                continue
            resource = next(
                (x for x in value.resources if x.actor == owner and x.frame == exit["frame"]), None
            )
            if resource and "safe_ejection" not in value.options:
                prove_drop(game, c, before, value.id)
                affected.append(value)
        if affected:
            ended = end_in_transaction(
                c,
                game,
                state,
                actor,
                reason="death",
                source_event=event,
                account="Actual radiation after ejection from a fully damaged blast Frame",
                archive_id=str(uuid5(NAMESPACE_URL, "a-bomb-radiation:" + event + actor.token)),
            )
            _copy(state, ended)
            state.facts.append(
                dict(
                    kind="a_bomb_radiation",
                    event=event,
                    actor=actor.model_dump_json(),
                    sources=json.dumps([x.id for x in affected]),
                    outcome="death"
                    if any(
                        x.actor == actor and x.source_event == event for x in state.career_archives
                    )
                    else "prevented",
                )
            )


def synchronize_ejections(
    game: GameService, c: Connection, state: GameState, event: str, action_id: str | None
) -> None:
    if not any(
        x.get("kind") == "a_bomb_radiation" and x.get("event") == event for x in state.facts
    ):
        return
    from girlframe.services.m3_battle import synchronize_casts
    from girlframe.services.m3_careers import synchronize_end

    for archive in state.career_archives:
        if archive.source_event != event:
            continue
        excluded: tuple[str, ...] = ()
        if action_id is not None:
            action = game.action(c, action_id)
            defeat = action["data"].get("defeat", {})
            child = defeat.get("source_work")
            if (
                action["data"].get("play") == "defeat"
                and action["data"].get("response_event") == event
                and action["state"] == "complete"
                and defeat.get("actor") == archive.actor.model_dump(mode="json")
                and child
            ):
                from girlframe.services.m3_battle import source_parent_for_defeat
                from girlframe.services.m3_defeat import work

                actual = work(game, c, child)
                source_parent_for_defeat(game, c, actual, archive.actor)
                excluded = (child,)
        synchronize_end(c, game, archive, exclude_work=excluded)
    synchronize_casts(game, c, event)


def require_damage_cleared(
    game: GameService, c: Connection, state: GameState, actor: ActorRef
) -> None:
    for source in rules.drops(state):
        if any(x.actor == actor and x.event is None for x in source.resources):
            prove_drop(game, c, state, source.id)
            raise WorkflowError(
                "Resolve actual nuclear resource damage before this original body acts"
            )


class ABombService:
    def __init__(self, store: OnboardingStore):
        self.store, self.game = store, GameService(store)

    def _access(self, c: Connection, viewer: GuildViewer) -> None:
        gate = Access(self.store)
        gate.authorize(c, viewer, "world")
        assert gate.registry is not None
        gate.registry.require_available(rules.RULE)

    def _write(
        self, viewer: GuildViewer, key: str, kind: str, body: dict[str, Any], operation: Any
    ) -> dict[str, Any]:
        return self.store._write(
            viewer,
            key,
            kind,
            body,
            operation,
            authorize=lambda c: self._access(c, viewer),
            auto_audit=False,
        )

    def _safe(self, c: Connection, revision: int) -> GameState:
        self.game.unpaused(c)
        state = load_state(c, self.store.campaign_id)
        if state.revision != revision:
            raise WorkflowError("Reopen the actual current blast source")
        return state

    def buy(
        self, viewer: GuildViewer, key: str, award: str, revision: int, account: str
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            self._safe(c, revision)
            source = held(
                self.game,
                c,
                viewer,
                award,
                revision,
                account,
                failure="Spend an actual held original Handler award",
            )
            state = source.state
            if any(x.handler == source.handler for x in rules.acquisitions(state)):
                raise WorkflowError("This original Handler already owns A-Bomb")
            event = str(uuid4())
            receipt = rules.Acquisition(
                id="a-bomb:" + award,
                award=award,
                handler=source.handler,
                appointment=source.appointment,
                event=event,
                account=account.strip(),
            )
            rules.put(state, receipt)
            record_spend(state, source.award, receipt, rules.RULE)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.handler_advancement_spent",
                state,
                event_id=event,
                acquisition=receipt.id,
                award=award,
                rule=rules.RULE,
            )
            return dict(id=receipt.id)

        return self._write(
            viewer,
            key,
            "m3.a_bomb_acquired",
            dict(award=award, revision=revision, account=account),
            operation,
        )

    def certify_device(
        self,
        viewer: GuildViewer,
        key: str,
        acquisition: str,
        revision: int,
        item: str,
        cell: Cell,
        account: str,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            state = self._safe(c, revision)
            receipt = paid(self.game, c, state, acquisition)
            _current(self.game, c, state, receipt, viewer)
            from girlframe.services.m3_items import prove_item

            actual = prove_item(c, self.game, state, item)
            human, appointment = MedicalService(self.store)._handler(c)
            body = resolve(
                state,
                receipt.handler,
                profiles(c, self.store.campaign_id),
                require_current_profile=False,
            )
            if (
                state.world is None
                or not state.world.board.contains(cell)
                or not account.strip()
                or actual.holder != receipt.handler
                or actual.condition != "intact"
                or actual.asset_json is not None
                or actual.location_mode != "carried"
                or body.offstage_source
                or body.custody not in (None, "free")
                or body.cell not in (None, cell)
                or any(x.item == item for x in rules.devices(state))
            ):
                raise WorkflowError(
                    "Prove actual carried nuclear capability and truthful known/initial"
                    " original Handler position; no teleport/rearm"
                )
            event = str(uuid4())
            device = rules.Device(
                id="nuclear-device:" + event,
                acquisition=acquisition,
                item=item,
                item_json=actual.model_dump_json(),
                handler=receipt.handler,
                appointment=appointment,
                event=event,
                cell=cell,
                account=account.strip(),
            )
            if body.cell is None:
                state.facts.append(
                    dict(
                        kind="a_bomb_actual_position",
                        actor=receipt.handler.model_dump_json(),
                        cell=json.dumps(cell),
                        event=event,
                        account=account.strip(),
                        acquisition=acquisition,
                        item=item,
                    )
                )
            state.facts.append(
                dict(kind="a_bomb_device", id=device.id, body=device.model_dump_json())
            )
            self.game.event(
                c,
                human,
                key,
                "m3.a_bomb_device_confirmed",
                state,
                event_id=event,
                device=device.id,
                item=item,
            )
            return dict(id=device.id)

        return self._write(
            viewer,
            key,
            "m3.a_bomb_device_confirmed",
            dict(acquisition=acquisition, revision=revision, item=item, cell=cell, account=account),
            operation,
        )

    def drop(
        self,
        viewer: GuildViewer,
        key: str,
        acquisition: str,
        revision: int,
        device: str,
        centre: Cell,
        options: tuple[rules.Option, rules.Option],
        delivery: str,
        *,
        mission: str | None = None,
        breaches: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            state = self._safe(c, revision)
            source = paid(self.game, c, state, acquisition)
            _current(self.game, c, state, source, viewer)
            from girlframe.services.m3_items import prove_item

            actual = next(
                (
                    x
                    for x in rules.devices(state)
                    if x.id == device and x.acquisition == acquisition
                ),
                None,
            )
            if actual is None or actual not in rules.devices(_history(c, self.game, actual.event)):
                raise WorkflowError("Prove the actual nuclear capability source")
            item = prove_item(c, self.game, state, actual.item)
            body = resolve(
                state,
                source.handler,
                profiles(c, self.store.campaign_id),
                require_current_profile=False,
            )
            cells = rules.footprint(centre)
            if (
                state.world is None
                or state.strain is None
                or any(not state.world.board.contains(x) for x in cells)
                or len(set(options)) != 2
                or not set(options) <= set(rules.OPTIONS)
                or not delivery.strip()
                or body.cell is None
                or body.offstage_source
                or item.holder != source.handler
                or item.condition != "intact"
                or item.location_mode != "carried"
                or item.model_dump_json() != actual.item_json
            ):
                raise WorkflowError(
                    "Actually drop this original carried nuclear device into an onboard"
                    " 3x3 area; preserve real delivery and exactly two options"
                )
            from girlframe.services.m3_handler_plays import _ordinary_scene_idle

            _ordinary_scene_idle(c, self.game)
            resources = roster(state, cells)
            from girlframe.services.m3_harpy_defeat import HarpyDefeatService

            for resource in resources:
                if resource.actor.kind == "external_pilot":
                    HarpyDefeatService(self.store)._runtime(c, state, resource.actor)
            mission_value = None
            if "mission_budget" in options:
                from girlframe.services.m3_missions import MissionService

                mission_value = MissionService(self.store)._mission(c, mission or "")
                if mission_value.phase != "active" or mission_value.handler != viewer.user_id:
                    raise WorkflowError(
                        "Bind the actual active Mission this nuclear drop may lead to success"
                    )
            elif mission is not None:
                raise WorkflowError("Do not attach an unchosen conditional Budget waiver")
            judge, appointment = MedicalService(self.store)._handler(c)
            event = str(uuid4())
            identity = "a-bomb-drop:" + event
            value = rules.Drop(
                id=identity,
                acquisition=acquisition,
                handler=source.handler,
                appointment=source.appointment,
                event=event,
                device=item.id,
                device_json=item.model_dump_json(),
                release=body.cell,
                centre=centre,
                cells=cells,
                options=options,
                delivery=delivery.strip(),
                judge=judge,
                judge_appointment=appointment,
                resources=resources,
                npcs={
                    x.id: x.model_dump_json()
                    for x in state.world.npcs
                    if x.alive and x.cell in cells
                },
                sprites={
                    x.id: x.model_dump_json()
                    for x in state.world.gorgons
                    if x.alive and x.gorgon_class == "sprite" and x.cell in cells
                },
                deaths=tuple(
                    x.actor
                    for x in state.placements
                    if x.actor.kind == "pilot"
                    and x.girl_cell in cells
                    and x.mode == "outside_frame"
                ),
                structures=tuple(
                    x.id
                    for x in state.world.locations
                    if x.cell in cells and x.condition != "destroyed"
                ),
                mission=mission_value.id if mission_value else None,
                mission_objective=mission_value.objective if mission_value else None,
                breaches=breaches or {},
            )
            if "mission_budget" in options:
                budget.begin_condition(state, identity, event)
            budget.record_write(state, source=identity, event=event, value="high")
            state.strain = strain_copy(
                state.strain,
                levels=state.strain.levels
                | {"budget": "high"}
                | ({} if "gentle_fallout" in options else {"rebellion": "high"}),
            )
            state.held_items = [
                x.model_copy(update=dict(condition="ruined", state_event=event))
                if x.id == item.id
                else x
                for x in state.held_items
            ]
            rules.put(state, value)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.a_bomb_dropped",
                state,
                event_id=event,
                drop=identity,
                device=item.id,
            )
            self._initial(c, viewer, key, state, value)
            return dict(id=identity)

        return self._write(
            viewer,
            key,
            "m3.a_bomb_dropped",
            dict(
                acquisition=acquisition,
                revision=revision,
                device=device,
                centre=centre,
                options=options,
                delivery=delivery,
                mission=mission,
                breaches=breaches,
            ),
            operation,
        )

    def _deaths(self, c: Connection, state: GameState, value: rules.Drop, event: str) -> None:
        from girlframe.services.m3_careers import end_in_transaction

        for actor in value.deaths:
            if any(x.actor == actor for x in state.career_archives) or any(
                x.actor == actor and x.event is None for x in value.resources
            ):
                continue
            changed = end_in_transaction(
                c,
                self.game,
                state,
                actor,
                reason="death",
                source_event=event,
                account="Actual nuclear blast killed this original Girl outside her Frame",
                archive_id=str(uuid5(NAMESPACE_URL, value.id + actor.token)),
            )
            _copy(state, changed)

    def _sync_endings(self, c: Connection, state: GameState, event: str) -> None:
        from girlframe.services.m3_battle import synchronize_casts
        from girlframe.services.m3_careers import synchronize_end

        for archive in state.career_archives:
            if archive.source_event == event:
                synchronize_end(c, self.game, archive)
        synchronize_casts(self.game, c, event)

    def _initial(
        self, c: Connection, viewer: GuildViewer, key: str, state: GameState, value: rules.Drop
    ) -> None:
        prove_drop(self.game, c, state, value.id)
        event = str(uuid4())
        assert state.world is not None
        from girlframe.services.m3_contaminant_zone import break_by_blast

        for zone in value.breaches:
            break_by_blast(self.game, c, state, value.id, zone, event)
        for target in value.sprites:
            kill_rostered_sprite(self.game, c, state, value.id, target, event)
        for target, original in value.npcs.items():
            actual = next(x for x in state.world.npcs if x.id == target)
            if actual.model_dump_json() != original:
                raise WorkflowError("Preserve the actual original NPC casualty")
            state.world = update(
                state.world,
                npcs=tuple(
                    x.model_copy(update=dict(alive=False)) if x.id == target else x
                    for x in state.world.npcs
                ),
            )
            _copy(state, end_actor_casts(state, ActorRef(kind="npc", entity=target), event))
        if "cores" in value.options:
            state.world = update(
                state.world,
                gorgons=tuple(
                    x.model_copy(update=dict(exposed=True))
                    if x.alive and x.cell in value.cells
                    else x
                    for x in state.world.gorgons
                ),
                pilots=tuple(
                    x.model_copy(update=dict(exposed=True))
                    if x.alive and x.kind == "harpy" and x.cell in value.cells
                    else x
                    for x in state.world.pilots
                ),
            )
            # Native/conversion Harpies keep their sole runtime authority as well.
            state.harpy_states = [
                x.model_copy(update=dict(exposed=True))
                if x.alive and x.frame_cell in value.cells
                else x
                for x in state.harpy_states
            ]
        if value.structures:
            result, _ = perform(
                state,
                Source(
                    id=value.id,
                    action=value.id,
                    choice=value.id,
                    event=event,
                    actor=value.handler,
                    actor_controller=viewer.user_id,
                    judge=value.judge,
                    appointment=value.judge_appointment,
                    handler=value.handler,
                ),
                Selection(
                    structures=value.structures,
                    account=value.delivery,
                    reach="Actual nuclear blast footprint",
                ),
                event,
            )
            _copy(state, result)
        from girlframe.engine.m3_collateral import loss as loss_record

        loss = None
        pending_loss = next(
            (
                x
                for x in reversed(state.facts)
                if x.get("kind") == "quadrant_loss"
                and json.loads(x["body"]).get("source") == value.id
            ),
            None,
        )
        if pending_loss:
            loss = loss_record(state, pending_loss["id"])
        fallout = Fallout(
            id=value.id, cells=value.cells, event=event, temporary="gentle_fallout" in value.options
        )
        state.world = update(
            state.world,
            fallout=state.world.fallout + (fallout,),
            locations=tuple(
                x.model_copy(update=dict(fallout_sources=x.fallout_sources + (value.id,)))
                if x.cell in value.cells
                else x
                for x in state.world.locations
            ),
        )
        value = value.model_copy(
            update=dict(
                initial_event=event,
                loss=loss.id if loss else None,
                resources=tuple(
                    x.model_copy(update=dict(event=event)) if not x.assets else x
                    for x in value.resources
                ),
            )
        )
        rules.put(state, value)
        self._deaths(c, state, value, event)
        self.game.event(
            c,
            viewer.user_id,
            key,
            "m3.a_bomb_initial_effects",
            state,
            event_id=event,
            event_index=1,
            drop=value.id,
        )
        self._sync_endings(c, state, event)
        if loss:
            from girlframe.services.m3_quadrant_loss import materialize_loss

            materialize_loss(self.game, c, loss, event)

    def damage(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        target: ActorRef,
        assets: tuple[str, ...],
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            state = self._safe(c, revision)
            value = prove_drop(self.game, c, state, identity)
            row = next((x for x in value.resources if x.actor == target and x.event is None), None)
            if (
                row is None
                or row.controller != viewer.user_id
                or len(assets) != min(2, len(row.assets))
                or len(set(assets)) != len(assets)
                or not set(assets) <= set(row.assets)
            ):
                raise WorkflowError(
                    "The real original resource owner chooses up to two actual "
                    "undamaged Assets once"
                )
            from girlframe.services.m3_battle import damage_blast_resource, synchronize_damage

            event = str(uuid4())
            work: list[str] = []
            for index, asset in enumerate(assets):
                changed, children = damage_blast_resource(
                    self.game,
                    c,
                    state,
                    drop=identity,
                    target=target,
                    asset=asset,
                    event=event,
                    occurrence=str(index),
                )
                _copy(state, changed)
                work.extend(children)
            row = row.model_copy(update=dict(losses=assets, event=event, work=tuple(work)))
            value = value.model_copy(
                update=dict(
                    resources=tuple(row if x.actor == target else x for x in value.resources)
                )
            )
            rules.put(state, value)
            self._deaths(c, state, value, event)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.a_bomb_damage",
                state,
                event_id=event,
                drop=identity,
                target=target.model_dump(mode="json"),
                assets=assets,
            )
            synchronize_damage(self.game, c, event)
            self._sync_endings(c, state, event)
            return dict(id=identity)

        return self._write(
            viewer,
            key,
            "m3.a_bomb_damage",
            dict(
                identity=identity,
                revision=revision,
                target=target.model_dump(mode="json"),
                assets=assets,
            ),
            operation,
        )

    def judge_mission(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        causal: bool,
        account: str,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            state = self._safe(c, revision)
            value = prove_drop(self.game, c, state, identity)
            human, appointment = MedicalService(self.store)._handler(c)
            if (
                (human, appointment) != (value.judge, value.judge_appointment)
                or viewer.user_id != human
                or value.mission is None
                or value.causal is not None
                or not account.strip()
            ):
                raise WorkflowError(
                    "The original actual source judge records one factual Mission/drop "
                    "causal assessment"
                )
            event = str(uuid4())
            rules.put(
                state,
                value.model_copy(
                    update=dict(causal=causal, causal_event=event, causal_account=account.strip())
                ),
            )
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.a_bomb_mission_cause",
                state,
                event_id=event,
                drop=identity,
                mission=value.mission,
                causal=causal,
            )
            return dict(id=identity)

        return self._write(
            viewer,
            key,
            "m3.a_bomb_mission_cause",
            dict(identity=identity, revision=revision, causal=causal, account=account),
            operation,
        )

    def _ready(self, c: Connection, value: rules.Drop) -> bool:
        if (
            value.completed_event
            or any(x.event is None for x in value.resources)
            or value.mission
            and not value.mission_resolved_event
        ):
            return False
        table = t.m3["m3_required_work"]
        children = [work for row in value.resources for work in row.work] + (
            [value.loss] if value.loss else []
        )
        return all(
            c.scalar(
                sa.select(table.c.state)
                .where(table.c.campaign_id == self.store.campaign_id, table.c.id == child)
                .order_by(table.c.revision.desc())
                .limit(1)
            )
            == "resolved"
            for child in children
        )

    def finish(self, viewer: GuildViewer, key: str, identity: str, revision: int) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            state = self._safe(c, revision)
            value = prove_drop(self.game, c, state, identity)
            if viewer.user_id != int(value.handler.entity) or not self._ready(c, value):
                raise WorkflowError(
                    "Finish actual original damage, Mission outcome and every mandatory"
                    " consequence before closing"
                )
            from girlframe.services.m3_careers import end_in_transaction, synchronize_end

            event = str(uuid4())
            for actor in value.deaths:
                if any(x.actor == actor for x in state.career_archives):
                    continue
                changed = end_in_transaction(
                    c,
                    self.game,
                    state,
                    actor,
                    reason="death",
                    source_event=event,
                    account="Actual nuclear blast killed this original Girl outside her Frame",
                    archive_id=str(uuid5(NAMESPACE_URL, identity + actor.token)),
                )
                _copy(state, changed)
            rules.put(state, value.model_copy(update=dict(completed_event=event)))
            self.game.event(
                c, viewer.user_id, key, "m3.a_bomb_complete", state, event_id=event, drop=identity
            )
            for archive in state.career_archives:
                if archive.source_event == event:
                    synchronize_end(c, self.game, archive)
            return dict(id=identity)

        return self._write(
            viewer, key, "m3.a_bomb_complete", dict(identity=identity, revision=revision), operation
        )

    def menu(self, viewer: GuildViewer, identity: str | None = None) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self._access(c, viewer)
            state = load_state(c, self.store.campaign_id)
            if identity and any(x.id == identity for x in rules.drops(state)):
                value = prove_drop(self.game, c, state, identity)
                if viewer.user_id not in {
                    value.judge,
                    int(value.handler.entity),
                    *(x.controller for x in value.resources),
                }:
                    raise WorkflowError(
                        "This original blast record is private to its actual source participants"
                    )
                own = viewer.user_id == int(value.handler.entity)
                judging = viewer.user_id == value.judge
                return dict(
                    kind="drop",
                    revision=state.revision,
                    drop=dict(
                        id=value.id,
                        centre=value.centre,
                        release=value.release,
                        options=value.options,
                        completed_event=value.completed_event,
                        mission=value.mission if judging else None,
                        mission_objective=value.mission_objective if judging else None,
                        causal=value.causal if judging else None,
                    ),
                    owner=own,
                    judge=judging,
                    resources=[
                        dict(
                            actor=x.actor.model_dump(mode="json"),
                            assets=x.assets,
                            labels={
                                a.id: a.name
                                for a in resolve(
                                    state,
                                    x.actor,
                                    profiles(c, self.store.campaign_id),
                                    require_current_profile=False,
                                ).assets
                                if a.id in x.assets
                            },
                        )
                        for x in value.resources
                        if x.controller == viewer.user_id and x.event is None
                    ],
                )

            source = next((x for x in rules.acquisitions(state) if x.id == identity), None)
            if source:
                paid(self.game, c, state, source.id)
                _current(self.game, c, state, source, viewer)
                from girlframe.services.m3_items import available_items

                return dict(
                    kind="source",
                    revision=state.revision,
                    id=source.id,
                    items=available_items(c, self.game, state, source.handler),
                    quarantines=[
                        dict(id=x.id, cells=x.cells, perimeter=x.perimeter)
                        for x in contaminant.zones(state)
                        if x.broken_event is None
                    ],
                    devices=[
                        x.model_dump(mode="json")
                        for x in rules.devices(state)
                        if x.acquisition == source.id
                        and not any(y.device == x.item for y in rules.drops(state))
                    ],
                    missions=[
                        Mission.model_validate_json(x).model_dump(mode="json")
                        for x in c.scalars(
                            sa.select(t.m3["m3_missions"].c.body_json).where(
                                t.m3["m3_missions"].c.campaign_id == self.store.campaign_id,
                                t.m3["m3_missions"].c.phase == "active",
                            )
                        )
                    ],
                )
            if identity:
                award = HandlerAdvancementService(self.store)._source(c, viewer, identity)[-1]
                if award is None or award.phase != "held":
                    raise WorkflowError("Select an actual held award")
                return dict(kind="buy", revision=state.revision, award=identity)
            return dict(
                kind="sources",
                revision=state.revision,
                sources=[
                    dict(id=x.id, label="A-Bomb")
                    for x in rules.acquisitions(state)
                    if x.handler.entity == str(viewer.user_id)
                ],
            )

    def _tasks(self, c: Connection, viewer: GuildViewer) -> list[dict[str, Any]]:
        self.game.authorize(c, viewer, game=False)
        state = load_state(c, self.store.campaign_id)
        result = [
            dict(
                id=x.id,
                revision=state.revision,
                label="A-Bomb source",
                phase="acquired",
                pending=False,
            )
            for x in rules.acquisitions(state)
            if x.handler.entity == str(viewer.user_id)
        ]
        for value in rules.drops(state):
            if viewer.user_id not in {
                value.judge,
                int(value.handler.entity),
                *(x.controller for x in value.resources),
            }:
                continue
            due = (
                any(x.controller == viewer.user_id and x.event is None for x in value.resources)
                or viewer.user_id == value.judge
                and value.mission is not None
                and value.causal is None
            )
            due = due or (viewer.user_id == int(value.handler.entity) and self._ready(c, value))
            result.append(
                dict(
                    id=value.id,
                    revision=state.revision,
                    label="Actual nuclear drop",
                    phase="complete" if value.completed_event else "effects",
                    pending=due,
                )
            )
        return result
