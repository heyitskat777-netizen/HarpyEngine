"""Actual unlocked regional resources, source-proved rival downfall and responsibility."""

import json
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_handler_advancements as awards
from girlframe.engine import m3_promotional_opportunity as rules
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_actors import fingerprint
from girlframe.engine.m3_harpy_defeat_state import NativeHarpyRuntime
from girlframe.services import m3_advancement_acquisition as acquisition_source
from girlframe.services.handler_setup import HandlerService
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_asset_loss import snapshots
from girlframe.services.m3_handler_advancements import HandlerAdvancementService, _history
from girlframe.services.m3_handler_pr import _audit
from girlframe.services.onboarding import OnboardingStore, WorkflowError
from girlframe.services.read_only_bot import GuildViewer


def _runtime(source: rules.Acquisition) -> NativeHarpyRuntime:
    value = source.setup.harpy
    if value is None:
        raise WorkflowError("This original unlocked map has no active Harpy threat")
    person, facts = value.person, value.facts
    return NativeHarpyRuntime(
        id=person.id,
        controller=person.controller,
        source_event=source.event,
        proposed_event=source.event,
        world_source_sha256=fingerprint(person),
        body_vessel="promotional-body:" + person.id,
        frame_instance="initial:" + person.id,
        cell=person.cell,
        frame_cell=person.cell,
        linked=True,
        heat=facts.heat,
        identities=facts.identities,
        tags=(),
    )


def paid(game: GameService, c: Connection, state: GameState, identity: str) -> rules.Acquisition:
    return acquisition_source.prove(
        game,
        c,
        state,
        identity,
        rule=rules.RULE,
        receipts=rules.acquisitions,
        missing="Recover the actual Promotional Opportunity source",
        failure="Preserve the original held Award, purchasing Handler and map acquisition",
    )


def prove(game: GameService, c: Connection, state: GameState, identity: str) -> rules.Acquisition:
    value = paid(game, c, state, identity)
    before, born = snapshots(game, c, value.event)
    _audit(game, c, value.event, "m3.handler_advancement_spent", value.handler.entity)
    audit = c.scalar(
        sa.select(t.events.c.payload_json).where(
            t.events.c.campaign_id == game.store.campaign_id, t.events.c.id == value.event
        )
    )
    if (
        before.world is None
        or born.world is None
        or born.world != rules.unlock(before.world, value)
        or before.sheets != born.sheets
        or before.placements != born.placements
        or json.loads(audit or "{}").get("rule_id") != rules.RULE
        or state.world is None
        or state.world.quadrant12 != value.original_board
        or state.world.board != born.world.board
    ):
        raise WorkflowError(
            "Preserve the actual old map, bodies and exact unlocked regional contents"
        )
    region = next((x for x in state.world.regions if x.acquisition == identity), None)
    original = born.world.regions[0] if born.world else None
    if (
        region is None
        or original is None
        or any(
            getattr(region, k) != getattr(original, k)
            for k in type(original).model_fields
            if k not in ("responsible", "takeover_event")
        )
    ):
        raise WorkflowError("Preserve the original actual regional office and authored geography")
    if value.setup.harpy:
        initial = next(
            (x for x in born.native_harpies if x.id == value.setup.harpy.person.id), None
        )
        if initial != _runtime(value):
            raise WorkflowError("Recover the real source-created Harpy body and Frame runtime")
    if region.responsible is not None:
        takeover = next((x for x in rules.takeovers(state) if x.acquisition == identity), None)
        if takeover is None:
            raise WorkflowError("Regional responsibility requires an actual source-proved takeover")
        _takeover_proof(game, c, state, value, takeover)
    return value


def prove_harpy(
    game: GameService, c: Connection, state: GameState, actor: ActorRef
) -> NativeHarpyRuntime:
    receipt = next(
        (
            x
            for x in rules.acquisitions(state)
            if x.setup.harpy and x.setup.harpy.person.id == actor.entity
        ),
        None,
    )
    current = next((x for x in state.native_harpies if x.id == actor.entity), None)
    if receipt is None or current is None or actor.kind != "external_pilot":
        raise WorkflowError("Recover this actual original regional Harpy source")
    source = prove(game, c, state, receipt.id)
    initial = _runtime(source)
    person = (
        next((x for x in state.world.pilots if x.id == actor.entity), None) if state.world else None
    )
    assert source.setup.harpy is not None
    original = source.setup.harpy.person
    if (
        person is None
        or person.tags
        or any(
            getattr(person, k) != getattr(original, k)
            for k in ("id", "kind", "girl", "frame", "controller")
        )
        or any(
            getattr(current, k) != getattr(initial, k)
            for k in (
                "id",
                "controller",
                "source_event",
                "proposed_event",
                "world_source_sha256",
                "body_vessel",
                "frame_instance",
            )
        )
    ):
        raise WorkflowError(
            "Preserve the original actual Harpy while retaining its current damage/resources"
        )
    return current


def prove_responsibility(game: GameService, c: Connection, state: GameState) -> None:
    if state.world:
        for region in state.world.regions:
            prove(game, c, state, region.acquisition)


def _death(game: GameService, c: Connection, source: rules.Acquisition, identity: str) -> str:
    from girlframe.services.m3_battle_npc import NpcDamageService
    from girlframe.services.m3_handler_plays import _source

    service = NpcDamageService(game.store)
    row = service._row(c, identity)
    target, _ = service._proof(c, row)
    body = json.loads(row["body_json"])
    if (
        target != ActorRef(kind="npc", entity=source.setup.rival.id)
        or row["state"] != "resolved"
        or body.get("effect") != "kill"
        or not body.get("source_work")
        or not body.get("effect_event")
    ):
        raise WorkflowError(
            "Prove the actual rival's completed canonical death, not an asserted downfall"
        )
    _, grant = _source(c, game, body["source_work"])
    event = body["effect_event"]
    before, after = snapshots(game, c, event)
    old = (
        next((x for x in before.world.npcs if x.id == target.entity), None)
        if before.world
        else None
    )
    dead = (
        next((x for x in after.world.npcs if x.id == target.entity), None) if after.world else None
    )
    earlier = next((x for x in rules.acquisitions(before) if x.id == source.id), None)
    _audit(game, c, event, "m3.npc_damage_applied", source.handler.entity)
    if (
        grant.source != "ordinary"
        or grant.chooser_actor != source.handler
        or grant.chooser_controller != int(source.handler.entity)
        or grant.appointment != source.appointment
        or grant.state != "complete"
        or grant.effect is None
        or grant.effect.kind != "damage"
        or grant.effect.target != target
        or identity not in grant.followups
        or earlier != source
        or old is None
        or not old.alive
        or dead is None
        or dead.alive
        or old.controller != source.setup.rival.controller
        or old.jobs != ("handler",)
    ):
        raise WorkflowError(
            "Bind the actual original Handler's arranged source and real rival's fate"
        )
    return str(event)


def _takeover_proof(
    game: GameService,
    c: Connection,
    state: GameState,
    source: rules.Acquisition,
    value: rules.Takeover,
) -> None:
    born = _history(c, game, value.event)
    before, _ = snapshots(game, c, value.event)
    region = (
        next((x for x in born.world.regions if x.acquisition == source.id), None)
        if born.world
        else None
    )
    previous = (
        next((x for x in before.world.regions if x.acquisition == source.id), None)
        if before.world
        else None
    )
    _audit(game, c, value.event, "m3.promotional_opportunity_taken_over", source.handler.entity)
    if (
        value not in rules.takeovers(born)
        or value.handler != source.handler
        or value.death_event != _death(game, c, source, value.death_work)
        or region is None
        or previous is None
        or previous.responsible is not None
        or region.responsible != source.handler
        or region.takeover_event != value.event
        or state.world is None
        or next((x for x in state.world.regions if x.acquisition == source.id), None) != region
    ):
        raise WorkflowError(
            "Recover the actual original rival downfall and single regional takeover"
        )


class PromotionalOpportunityService:
    def __init__(self, store: OnboardingStore):
        self.store, self.game = store, GameService(store)

    def _access(self, c: Connection, viewer: GuildViewer) -> None:
        gate = Access(self.store)
        for subsystem in ("economy", "playbooks", "world"):
            gate.authorize(c, viewer, subsystem)
        assert gate.registry is not None
        gate.registry.require_available(rules.RULE)

    def _write(
        self, viewer: GuildViewer, key: str, kind: str, payload: dict[str, Any], operation: Any
    ) -> dict[str, Any]:
        try:
            return self.store._write(
                viewer,
                key,
                kind,
                payload,
                operation,
                auto_audit=False,
                authorize=lambda c: self._access(c, viewer),
            )
        except ValueError as error:
            raise WorkflowError(str(error)) from None

    def acquire(
        self, viewer: GuildViewer, key: str, award_id: str, revision: int, setup: rules.Setup
    ) -> dict[str, Any]:
        setup = rules.Setup.model_validate_json(setup.model_dump_json())

        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            state, handler, appointment, award = acquisition_source.held(
                self.game,
                c,
                viewer,
                award_id,
                revision,
                setup.account,
                failure="Spend this actual held Award to unlock its new regional map",
            )
            if (
                state.world is None
                or state.world.regions
                or rules.acquisitions(state)
                or self.game.pending_actions(c)
            ):
                raise WorkflowError(
                    "Use the existing actual World, preserve its history and finish pending Plays"
                )
            if any(
                not HandlerService(self.store)._member(c, x.controller) for x in setup.people()
            ) or (
                setup.harpy is not None
                and not HandlerService(self.store)._member(c, setup.harpy.person.controller)
            ):
                raise WorkflowError(
                    "Assign each actual new NPC/Harpy to a current real human controller"
                )
            event = str(uuid4())
            value = rules.Acquisition(
                id="promotional-opportunity:" + award_id,
                award=award_id,
                handler=handler,
                appointment=appointment,
                event=event,
                account=setup.account,
                setup=setup,
                original_board=state.world.board,
            )
            state.world = rules.unlock(state.world, value)
            if setup.harpy:
                state.native_harpies.append(_runtime(value))
            rules.put(state, value)
            acquisition_source.record_spend(state, award, value, rules.RULE)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.handler_advancement_spent",
                state,
                event_id=event,
                award_id=award_id,
                acquisition_id=value.id,
                rule_id=rules.RULE,
            )
            return dict(id=value.id, phase="unlocked")

        return self._write(
            viewer,
            key,
            "m3.promotional_opportunity_acquired",
            dict(award=award_id, revision=revision, setup=setup.model_dump(mode="json")),
            operation,
        )

    def take_over(
        self, viewer: GuildViewer, key: str, acquisition: str, revision: int, death_work: str
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            source = prove(self.game, c, state, acquisition)
            HandlerAdvancementService(self.store)._current(
                c, state, source.handler, source.appointment
            )
            if (
                viewer.user_id != int(source.handler.entity)
                or state.revision != revision
                or any(x.acquisition == acquisition for x in rules.takeovers(state))
            ):
                raise WorkflowError("The original current Handler takes this actual region once")
            death_event = _death(self.game, c, source, death_work)
            event = str(uuid4())
            value = rules.Takeover(
                id=acquisition + ":takeover",
                acquisition=acquisition,
                handler=source.handler,
                event=event,
                death_work=death_work,
                death_event=death_event,
            )
            assert state.world is not None
            state.world = state.world.model_copy(
                update=dict(
                    regions=tuple(
                        x.model_copy(update=dict(responsible=source.handler, takeover_event=event))
                        if x.acquisition == acquisition
                        else x
                        for x in state.world.regions
                    )
                )
            )
            rules.put(state, value)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.promotional_opportunity_taken_over",
                state,
                event_id=event,
                acquisition_id=acquisition,
            )
            return dict(id=acquisition, phase="responsible")

        return self._write(
            viewer,
            key,
            "m3.promotional_opportunity_taken_over",
            dict(acquisition=acquisition, revision=revision, death_work=death_work),
            operation,
        )

    def menu(self, viewer: GuildViewer, identity: str | None = None) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self._access(c, viewer)
            state = load_state(c, self.store.campaign_id)
            receipts = [
                prove(self.game, c, state, x.id)
                for x in rules.acquisitions(state)
                if x.handler.entity == str(viewer.user_id)
                and (identity is None or x.id == identity)
            ]
            held = [
                x
                for x in awards.awards(state)
                if x.phase == "held"
                and x.handler.entity == str(viewer.user_id)
                and (identity is None or x.id == identity)
            ]
            if identity and not receipts and not held:
                raise WorkflowError("Recover your own actual source Award or regional acquisition")
            choices = []
            if receipts:
                table = t.m3["m3_required_work"]
                rows = c.execute(
                    sa.select(table)
                    .where(
                        table.c.campaign_id == self.store.campaign_id, table.c.kind == "npc_damage"
                    )
                    .order_by(table.c.revision)
                ).mappings()
                for row in {x["id"]: dict(x) for x in rows}.values():
                    body = json.loads(row["body_json"])
                    if (
                        row["state"] == "resolved"
                        and body.get("effect") == "kill"
                        and body.get("owner", {}).get("entity") == receipts[0].setup.rival.id
                    ):
                        choices.append(dict(id=row["id"], label="Actual rival's canonical death"))
            region = state.world.regions[0] if receipts and state.world else None
            return dict(
                revision=state.revision,
                acquisition=receipts[0].id if receipts else None,
                region=region.model_dump(mode="json") if region else None,
                awards=[dict(id=x.id, label=x.account) for x in held],
                board=state.world.board.model_dump(mode="json") if state.world else None,
                members=[dict(id=viewer.user_id, label="My actual Handler control")]
                + [
                    dict(id=uid, label=x.get("callsign", "Current member " + str(uid)))
                    for uid, x in HandlerService(self.store)._roster(c).items()
                ],
                deaths=choices,
            )

    def _tasks(self, c: Connection, viewer: GuildViewer) -> list[dict[str, Any]]:
        state = load_state(c, self.store.campaign_id)
        return [
            dict(
                id=x.id,
                revision=state.revision,
                label="Quadrant13 regional responsibility",
                phase="responsible"
                if any(t.acquisition == x.id for t in rules.takeovers(state))
                else "unlocked",
                pending=False,
            )
            for x in rules.acquisitions(state)
            if x.handler.entity == str(viewer.user_id)
        ]
