"""Genuine award/quarantine sources, real world effects and owned Warp grants."""

from typing import Any
from uuid import uuid4

from sqlalchemy import Connection

from girlframe.engine import m3_contaminant_zone as rules
from girlframe.engine import m3_handler_advancements as awards
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_handler_play_state import HandlerPlay
from girlframe.engine.m3_harpy_defeat_state import NativeHarpyRuntime
from girlframe.engine.m3_work_scope import WorkScope
from girlframe.engine.m3_world import update
from girlframe.engine.m3_world_state import AreaFeature, Cell
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_handler_advancements import HandlerAdvancementService, _history
from girlframe.services.m3_missions import MissionService
from girlframe.services.onboarding import OnboardingStore, WorkflowError
from girlframe.services.read_only_bot import GuildViewer


def paid(game: GameService, c: Connection, state: GameState, identity: str) -> rules.Acquisition:
    gate = Access(game.store)
    assert gate.registry is not None
    gate.registry.require_available(rules.RULE)
    value = next((x for x in rules.acquisitions(state) if x.id == identity), None)
    if value is None:
        raise WorkflowError("Recover the actual Contaminant Zone acquisition")
    born = next(
        (x for x in rules.acquisitions(_history(c, game, value.event)) if x.id == identity), None
    )
    _, _, handler, appointment, award = HandlerAdvancementService(game.store)._proof(c, value.award)
    if (
        born != value
        or award is None
        or award.acquisition != value.id
        or award.acquired_rule != rules.RULE
        or award.spend_event != value.event
        or (handler, appointment) != (value.handler, value.appointment)
    ):
        raise WorkflowError("Preserve the actual original award and acquisition source")
    return value


def zone_proof(game: GameService, c: Connection, state: GameState, identity: str) -> rules.Zone:
    value = next((x for x in rules.zones(state) if x.id == identity), None)
    if value is None:
        raise WorkflowError("Recover the actual quarantined area")
    receipt = paid(game, c, state, value.acquisition)
    born = next((x for x in rules.zones(_history(c, game, value.event)) if x.id == identity), None)
    mutable = {"broken_event", "breach_actor", "breach_cell", "breach_account"}
    if (
        born is None
        or born.broken_event is not None
        or any(
            getattr(born, k) != getattr(value, k)
            for k in rules.Zone.model_fields
            if k not in mutable
        )
        or (value.handler, value.appointment) != (receipt.handler, receipt.appointment)
    ):
        raise WorkflowError("Preserve the original actual quarantine, effects and source")
    if value.broken_event:
        ending = next(
            (x for x in rules.zones(_history(c, game, value.broken_event)) if x.id == identity),
            None,
        )
        if ending != value:
            raise WorkflowError("Preserve the actual recorded quarantine breach")
    return value


def prove_relief(game: GameService, c: Connection, state: GameState) -> None:
    if state.strain is None:
        return
    expected = {
        x.id for x in rules.zones(state) if "void_relief" in x.effects and x.broken_event is None
    }
    if set(state.strain.void_relief_sources) != expected:
        raise WorkflowError("Temporary Void relief requires the exact surviving quarantine sources")
    for identity in state.strain.void_relief_sources:
        zone_proof(game, c, state, identity)


def prove_harpy(
    game: GameService, c: Connection, state: GameState, actor: ActorRef
) -> NativeHarpyRuntime:
    value = next((x for x in state.native_harpies if x.id == actor.entity), None)
    source = next((x for x in rules.zones(state) if actor.entity in x.harpies), None)
    if actor.kind != "external_pilot" or value is None or source is None:
        raise WorkflowError("Recover the actual quarantine-created world Harpy")
    zone_proof(game, c, state, source.id)
    from girlframe.engine.m3_actors import fingerprint
    from girlframe.services.m3_girl_insurance import _before

    born = _history(c, game, source.event)
    before = _before(game, c, source.event)
    group = source.harpy_groups.get(actor.entity)
    old_group = (
        next((x for x in before.world.factions if x.id == group), None) if before.world else None
    )
    ended_group = (
        next((x for x in born.world.factions if x.id == group), None) if born.world else None
    )
    original = next((x for x in born.native_harpies if x.id == actor.entity), None)
    person = (
        next((x for x in born.world.pilots if x.id == actor.entity), None) if born.world else None
    )
    live_person = (
        next((x for x in state.world.pilots if x.id == actor.entity), None) if state.world else None
    )
    if (
        original is None
        or person is None
        or person.kind != "harpy"
        or old_group is None
        or not old_group.active
        or ended_group is None
        or ended_group.active
        or source.groups.get(group or "") != old_group.model_dump_json()
        or not set(old_group.cells) <= set(source.cells)
        or group is None
        or len(source.harpies) != len(source.groups)
        or set(source.harpy_groups) != set(source.harpies)
        or set(source.harpy_groups.values()) != set(source.groups)
        or live_person is None
        or live_person.kind != "harpy"
        or live_person.tags
        or live_person.controller != person.controller
        or person.controller != int(source.handler.entity)
        or original.world_source_sha256 != fingerprint(person)
        or original.frame_instance != "initial:" + person.id
        or original.body_vessel != "contaminant-body:" + person.id
        or source.acquisition not in {x.id for x in rules.acquisitions(before)}
        or before.world is None
        or any(x.id == person.id for x in before.world.pilots)
        or value.source_event != source.event
        or value.controller != int(source.handler.entity)
        or any(
            getattr(original, k) != getattr(value, k)
            for k in (
                "controller",
                "source_event",
                "proposed_event",
                "body_vessel",
                "frame_instance",
            )
        )
    ):
        raise WorkflowError("Preserve the genuine Harpy birth, physical person and Frame source")
    return value


def _current(
    game: GameService, c: Connection, state: GameState, receipt: rules.Acquisition
) -> None:
    HandlerAdvancementService(game.store)._current(c, state, receipt.handler, receipt.appointment)
    actual = resolve(
        state, receipt.handler, profiles(c, game.store.campaign_id), require_current_profile=False
    )
    if actual.rules != "handler" or actual.offstage_source or actual.custody not in (None, "free"):
        raise WorkflowError("This source needs its actual available original native Handler body")


def warp_options(
    game: GameService, c: Connection, state: GameState, handler: ActorRef | None
) -> list[dict[str, str]]:
    rows = []
    for value in rules.zones(state):
        if value.handler != handler or value.broken_event:
            continue
        receipt = paid(game, c, state, value.acquisition)
        _current(game, c, state, receipt)
        zone_proof(game, c, state, value.id)
        rows.append(dict(id=value.id, label="Warp " + value.perimeter[:70]))
    return rows


def start_warp(
    game: GameService,
    c: Connection,
    state: GameState,
    viewer: GuildViewer,
    zone: str,
    event: str,
    *,
    scene: str | None = None,
) -> str:
    value = zone_proof(game, c, state, zone)
    receipt = paid(game, c, state, value.acquisition)
    _current(game, c, state, receipt)
    if value.broken_event or value.handler.entity != str(viewer.user_id):
        raise WorkflowError("Only this actual source owner warps an intact Contaminant Zone")
    if scene is not None:
        cast = next((x for x in state.scene_casts if x.id == scene and x.open), None)
        if cast is None or not any(
            r.actor == value.handler and r.controller == viewer.user_id for r in cast.roles
        ):
            raise WorkflowError("Use the actual original Handler's joined open scene")
    identity = "contaminant-warp:" + str(uuid4())
    state.handler_plays.append(
        HandlerPlay(
            id=identity,
            source="ordinary",
            source_event=event,
            clause="contaminant-zone:" + zone,
            chooser_actor=value.handler,
            chooser_controller=viewer.user_id,
            appointment=value.appointment,
            targets=(value.handler,),
            target_controllers={value.handler.token: viewer.user_id},
            scope=WorkScope(scene_id=scene) if scene else WorkScope(campaign_context=True),
        )
    )
    rules.put(
        state,
        rules.WarpGrant(
            id=identity,
            zone=zone,
            acquisition=receipt.id,
            handler=value.handler,
            appointment=value.appointment,
            event=event,
            scene=scene,
        ),
    )
    return identity


def prove_warp(
    game: GameService, c: Connection, state: GameState, grant: HandlerPlay
) -> rules.Zone:
    source = next((x for x in rules.grants(state) if x.id == grant.id), None)
    if source is None:
        raise WorkflowError(
            "A basic Handler grant cannot substitute for actual zone Warp authority"
        )
    proof = _history(c, game, source.event)
    born = next((x for x in rules.grants(proof) if x.id == grant.id), None)
    original = next((x for x in proof.handler_plays if x.id == grant.id), None)
    value = zone_proof(game, c, state, source.zone)
    receipt = paid(game, c, state, source.acquisition)
    if grant.state != "complete":
        _current(game, c, state, receipt)
    if (
        born != source
        or original is None
        or value.broken_event is not None
        and grant.state != "complete"
        or grant.clause != "contaminant-zone:" + source.zone
        or grant.source != "ordinary"
        or grant.chooser_actor != source.handler
        or grant.appointment != source.appointment
        or grant.chooser_controller != int(source.handler.entity)
        or grant.targets != (source.handler,)
        or grant.scope != original.scope
        or grant.target_controllers != original.target_controllers
        or grant.source_event != source.event
    ):
        raise WorkflowError("Preserve this original source-owned actual Warp grant and active area")
    if source.scene and grant.state != "complete":
        cast = next((x for x in state.scene_casts if x.id == source.scene and x.open), None)
        if cast is None or not any(r.actor == source.handler for r in cast.roles):
            raise WorkflowError("The actual source Handler must still own the joined scene context")
    return value


def apply_warp(
    game: GameService,
    c: Connection,
    state: GameState,
    *,
    handler: ActorRef,
    appointment: str,
    zone: str,
    cell: Cell,
    label: str,
    description: str,
    event: str,
    grant: str,
    scene: str | None = None,
) -> GameState:
    actual = next((x for x in state.handler_plays if x.id == grant), None)
    if actual is None:
        raise WorkflowError("Use the actual owned Warp Play")
    value = prove_warp(game, c, state, actual)
    source = next(x for x in rules.grants(state) if x.id == grant)
    if (
        (handler, appointment, zone, scene)
        != (value.handler, value.appointment, value.id, source.scene)
        or value.broken_event is not None
        or cell not in value.cells
        or not label.strip()
        or not description.strip()
        or actual.state != "awaiting_effect"
        or actual.selected != "contaminant_warp"
        or actual.effect is None
        or actual.effect.kind != "contaminant_warp"
        or (
            actual.effect.zone,
            actual.effect.cell,
            actual.effect.source_label,
            actual.effect.detail,
        )
        != (zone, cell, label, description)
        or actual.effect_event != event
        or state.world is None
        or any(x.grant == grant for x in state.world.features)
    ):
        raise WorkflowError("Apply one actual terrain feature from this committed source Play")
    changed = GameState.model_validate_json(state.model_dump_json())
    assert changed.world is not None
    changed.world = update(
        changed.world,
        features=changed.world.features
        + (
            AreaFeature(
                id=rules.warp_identity(grant),
                zone=zone,
                cell=cell,
                label=label.strip(),
                description=description.strip(),
                source_event=event,
                grant=grant,
            ),
        ),
    )
    return changed


class ContaminantZoneService:
    def __init__(self, store: OnboardingStore):
        self.store, self.game = store, GameService(store)

    def _access(self, c: Connection, viewer: GuildViewer) -> None:
        gate = Access(self.store)
        for subsystem in ("economy", "world"):
            gate.authorize(c, viewer, subsystem)
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
        if state.revision != revision or self.game.pending_actions(c):
            raise WorkflowError("Reopen the current actual source after pending Plays finish")
        return state

    def buy(
        self, viewer: GuildViewer, key: str, award: str, revision: int, account: str
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            state = self._safe(c, revision)
            _, _, handler, appointment, value = HandlerAdvancementService(self.store)._source(
                c, viewer, award
            )
            HandlerAdvancementService(self.store)._current(c, state, handler, appointment)
            if (
                value is None
                or value.phase != "held"
                or not account.strip()
                or any(x.handler == handler for x in rules.acquisitions(state))
            ):
                raise WorkflowError("Spend one genuine held award on unowned Contaminant Zone")
            event = str(uuid4())
            receipt = rules.Acquisition(
                id="contaminant:" + award,
                award=award,
                handler=handler,
                appointment=appointment,
                event=event,
                account=account.strip(),
            )
            rules.put(state, receipt)
            awards.put(
                state,
                awards.Award.model_validate_json(
                    value.model_copy(
                        update=dict(
                            phase="spent",
                            acquired_rule=rules.RULE,
                            acquisition=receipt.id,
                            spend_event=event,
                            spend_account=account.strip(),
                        )
                    ).model_dump_json()
                ),
            )
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
            "m3.contaminant_acquired",
            dict(award=award, revision=revision, account=account),
            operation,
        )

    def quarantine(
        self,
        viewer: GuildViewer,
        key: str,
        acquisition: str,
        revision: int,
        request: rules.Quarantine,
    ) -> dict[str, Any]:
        request = rules.Quarantine.model_validate_json(request.model_dump_json())

        def operation(c: Connection) -> dict[str, Any]:
            state = self._safe(c, revision)
            receipt = paid(self.game, c, state, acquisition)
            _current(self.game, c, state, receipt)
            if viewer.user_id != int(receipt.handler.entity):
                raise WorkflowError("Only the original source Handler establishes this quarantine")
            MissionService(self.store)._handler(c, viewer)
            identity, event = "contaminant-zone:" + str(uuid4()), str(uuid4())
            try:
                result = rules.apply_quarantine(state, receipt, identity, event, request)
            except ValueError as error:
                raise WorkflowError(str(error)) from None
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.contaminant_quarantined",
                result,
                event_id=event,
                zone=identity,
                acquisition=acquisition,
            )
            return dict(id=identity)

        return self._write(
            viewer,
            key,
            "m3.contaminant_quarantined",
            dict(
                acquisition=acquisition, revision=revision, request=request.model_dump(mode="json")
            ),
            operation,
        )

    def break_quarantine(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        actor: ActorRef,
        cell: Cell,
        account: str,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            state = self._safe(c, revision)
            MissionService(self.store)._handler(c, viewer)
            zone_proof(self.game, c, state, identity)
            actual = resolve(
                state, actor, profiles(c, self.store.campaign_id), require_current_profile=False
            )
            if actual.cell != cell or actual.offstage_source:
                raise WorkflowError("A cached label cannot establish the actual breach body/cell")
            event = str(uuid4())
            try:
                result = rules.break_zone(state, identity, event, actor, cell, account)
            except ValueError as error:
                raise WorkflowError(str(error)) from None
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.contaminant_broken",
                result,
                event_id=event,
                zone=identity,
                breach_actor=actor.model_dump(mode="json"),
                cell=cell,
                account=account.strip(),
            )
            return dict(id=identity, event=event)

        return self._write(
            viewer,
            key,
            "m3.contaminant_broken",
            dict(
                identity=identity,
                revision=revision,
                actor=actor.model_dump(mode="json"),
                cell=cell,
                account=account,
            ),
            operation,
        )

    def start_warp(
        self, viewer: GuildViewer, key: str, identity: str, revision: int
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            state = self._safe(c, revision)
            event = str(uuid4())
            grant = start_warp(self.game, c, state, viewer, identity, event)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.contaminant_warp_started",
                state,
                event_id=event,
                grant_id=grant,
                zone=identity,
            )
            return dict(id=grant)

        return self._write(
            viewer,
            key,
            "m3.contaminant_warp_started",
            dict(identity=identity, revision=revision),
            operation,
        )

    def menu(self, viewer: GuildViewer, identity: str | None = None) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self._access(c, viewer)
            state = load_state(c, self.store.campaign_id)
            receipt = next(
                (
                    x
                    for x in rules.acquisitions(state)
                    if x.id == identity
                    or identity is None
                    and x.handler.entity == str(viewer.user_id)
                ),
                None,
            )
            if receipt is not None:
                paid(self.game, c, state, receipt.id)
                if receipt.handler.entity != str(viewer.user_id):
                    raise WorkflowError("This acquisition belongs to its original Handler")
                _current(self.game, c, state, receipt)
                return dict(
                    kind="acquired",
                    revision=state.revision,
                    acquisition=receipt.id,
                    zones=[
                        x.model_dump(mode="json")
                        for x in rules.zones(state)
                        if x.acquisition == receipt.id
                    ],
                    npcs=[
                        dict(id=x.id, name=x.name, cell=x.cell) for x in state.world.npcs if x.alive
                    ]
                    if state.world
                    else [],
                    groups=[
                        x.model_dump(mode="json")
                        for x in state.world.factions
                        if x.active and x.kind == "rebel"
                    ]
                    if state.world
                    else [],
                )
            value = next((x for x in rules.zones(state) if x.id == identity), None)
            if value:
                value = zone_proof(self.game, c, state, value.id)
                if value.handler.entity != str(viewer.user_id):
                    raise WorkflowError("This private zone history belongs to its source Handler")
                return dict(
                    kind="zone",
                    revision=state.revision,
                    body=value.model_dump(mode="json"),
                    actors=[
                        dict(
                            ref=x.model_dump(mode="json"),
                            label=resolve(
                                state,
                                x,
                                profiles(c, self.store.campaign_id),
                                require_current_profile=False,
                            ).label,
                        )
                        for x in self._breach_actors(c, state, value)
                    ],
                    features=[
                        x.model_dump(mode="json")
                        for x in state.world.features
                        if x.zone == value.id
                    ]
                    if state.world
                    else [],
                )
            service = HandlerAdvancementService(self.store)
            if identity is not None:
                _, _, handler, _, award = service._source(c, viewer, identity)
                if award is None or award.phase != "held" or handler.entity != str(viewer.user_id):
                    raise WorkflowError("Choose the actual original Handler's held award")
                return dict(kind="buy", revision=state.revision, award=identity)
            return dict(
                kind="awards",
                revision=state.revision,
                awards=[
                    dict(id=x.id, label=x.account)
                    for x in awards.awards(state)
                    if x.phase == "held" and x.handler.entity == str(viewer.user_id)
                ],
            )

    def _breach_actors(self, c: Connection, state: GameState, value: rules.Zone) -> list[ActorRef]:
        if state.world is None or value.broken_event:
            return []
        candidates = [ActorRef(kind="gorgon", entity=x.id) for x in state.world.gorgons if x.alive]
        candidates += [ActorRef(kind="npc", entity=x.id) for x in state.world.npcs if x.alive]
        candidates += [
            ActorRef(kind="external_pilot", entity=x.id) for x in state.world.pilots if x.alive
        ]
        result = []
        for ref in candidates:
            actual = resolve(
                state, ref, profiles(c, self.store.campaign_id), require_current_profile=False
            )
            if actual.cell in value.cells and not actual.offstage_source:
                result.append(ref)
        return result

    def _tasks(self, c: Connection, viewer: GuildViewer) -> list[dict[str, Any]]:
        self.game.authorize(c, viewer, game=False)
        state = load_state(c, self.store.campaign_id)
        return [
            dict(
                id=x.id,
                revision=state.revision,
                label="Contaminant Zone",
                phase="acquired",
                pending=False,
            )
            for x in rules.acquisitions(state)
            if x.handler.entity == str(viewer.user_id)
        ] + [
            dict(
                id=x.id,
                revision=state.revision,
                label="Actual quarantine",
                phase="broken" if x.broken_event else "active",
                pending=False,
            )
            for x in rules.zones(state)
            if x.handler.entity == str(viewer.user_id)
        ]


def break_by_blast(
    game: GameService, c: Connection, state: GameState, drop: str, identity: str, event: str
) -> None:
    from girlframe.services.m3_a_bomb import prove_drop

    source = prove_drop(game, c, state, drop)
    zone = zone_proof(game, c, state, identity)
    account = source.breaches.get(identity)
    crossing = next(
        (
            cell
            for cell in zone.cells
            if cell in source.cells
            and any(
                (cell[0] + dx, cell[1] + dy) not in zone.cells
                and (cell[0] + dx, cell[1] + dy) in source.cells
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))
            )
        ),
        None,
    )
    if not account or crossing is None or zone.broken_event is not None:
        raise WorkflowError(
            "Prove actual nuclear crossing and physical breach of the recorded quarantine perimeter"
        )
    changed = rules.break_by_blast(state, identity, event, crossing, account)
    for field in GameState.model_fields:
        setattr(state, field, getattr(changed, field))
    state.facts.append(
        dict(
            kind="a_bomb_perimeter_breach",
            drop=drop,
            zone=identity,
            event=event,
            perimeter=zone.perimeter,
            account=account,
        )
    )
