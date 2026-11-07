"""Paid NPC relationship and separately owned attendance/treatment; no invented consent."""

import json
from typing import TYPE_CHECKING, Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_physiotherapist as rules
from girlframe.engine.frame_classes import frame_class
from girlframe.engine.m2 import GameState, TagState
from girlframe.engine.m3_actor_bonds import current_ref, depth, set_depth
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_intracadre_marriage import available, debit
from girlframe.engine.m3_janus_storage import active as stored_points
from girlframe.engine.m3_nightmare import DONORS, current
from girlframe.engine.m3_off_duty import Period
from girlframe.engine.m3_privileges import suspended
from girlframe.engine.m3_requisition_state import FrameRuleReceipt
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_actors import ActorService, profiles
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_intracadre_marriage import prepare_payment
from girlframe.services.m3_privileges import purchase_proof
from girlframe.services.m3_requisitions import RequisitionService
from girlframe.services.m3_work import related
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer

if TYPE_CHECKING:
    from girlframe.services.m2_game import GameService


class PhysiotherapistService:
    def __init__(self, game: "GameService"):
        self.game, self.store = game, game.store

    def _rows(self, c: Connection) -> list[dict[str, Any]]:
        table = t.m3["m3_required_work"]
        return list(
            {
                x["id"]: dict(x)
                for x in c.execute(
                    sa.select(table)
                    .where(
                        table.c.campaign_id == self.store.campaign_id, table.c.kind == rules.KIND
                    )
                    .order_by(table.c.revision)
                ).mappings()
            }.values()
        )

    def _source(
        self, c: Connection, state: GameState, identity: str
    ) -> tuple[dict[str, Any], rules.Therapy]:
        row = next((x for x in self._rows(c) if x["id"] == identity), None)
        if row is None:
            raise WorkflowError("This original private physiotherapy request is unavailable")
        value = rules.Therapy.model_validate_json(
            json.dumps(json.loads(row["body_json"])["therapy"])
        )
        history = t.m2["m2_state_history"]
        snapshot = c.scalar(
            sa.select(history.c.body_json).where(
                history.c.campaign_id == self.store.campaign_id, history.c.event_id == value.event
            )
        )
        original = GameState.model_validate_json(snapshot) if snapshot else None
        fact = dict(kind=rules.KIND, id=value.id, body=value.model_dump_json())
        receipt = next((x for x in state.requisitions if x.id == value.purchase), None)
        if (
            original is None
            or fact not in original.facts
            or fact not in state.facts
            or row["event_id"] != value.event
            or row["owner_id"] != value.actor.entity
            or row["subject_id"] != str(value.controller)
            or row["off_duty_id"] != value.period
            or row["campaign_context"] != (value.period is None)
            or not isinstance(receipt, FrameRuleReceipt)
            or receipt.actor != value.actor
            or receipt.rule_id != rules.RULE
        ):
            raise WorkflowError("Recover the actual paid relationship/scene source")
        purchase_proof(c, self.store, receipt)
        return row, value

    def _visible(self, viewer: GuildViewer, value: rules.Therapy) -> None:
        if viewer.user_id not in (int(value.actor.entity), value.controller):
            raise WorkflowError(
                "This relationship and therapy scene belong to their original humans"
            )

    def _current(self, c: Connection, state: GameState, value: rules.Therapy) -> None:
        self.game.character_binding(c, state, int(value.actor.entity))
        receipt = rules.held(state, value.actor)
        if receipt is None or receipt.id != value.purchase:
            raise WorkflowError(
                "Restore this original paid Physiotherapist source before treatment"
            )
        from girlframe.services.m3_class_retention import proof

        _, chain = proof(self.game, c, state, receipt)
        if len(chain) > 1:
            gate = Access(self.store)
            if gate.registry is None:
                raise WorkflowError("Restore the actual paid Frame Swap source before treatment")
            gate.registry.require_available("core.core.frame-requisitions")
        npc = (
            next((x for x in state.world.npcs if x.id == value.npc.entity), None)
            if state.world
            else None
        )
        if npc is None or not npc.alive or npc.controller != value.controller:
            raise WorkflowError("Recover this actual living NPC's original controller")

    def _period(self, c: Connection, value: rules.Therapy) -> Period:
        table = t.m3["m3_off_duty"]
        raw = c.scalar(
            sa.select(table.c.body_json).where(
                table.c.campaign_id == self.store.campaign_id, table.c.phase == "active"
            )
        )
        period = Period.model_validate_json(raw) if raw else None
        if (
            period is None
            or period.character_ids.get(value.actor.entity) != value.actor.incarnation
            or value.actor.entity in period.ended_characters
        ):
            raise WorkflowError(
                "Record the scene in this original Girl's actual active Off-Duty period"
            )
        return period

    def _eligible(self, state: GameState, value: rules.Therapy) -> list[dict[str, str]]:
        sheet = state.sheets.get(value.actor.entity)
        if sheet is None or sheet.character_id != value.actor.incarnation:
            return []
        overlays = {x.asset for x in stored_points(state, value.actor)}
        return [
            dict(id=x.id, label=x.name)
            for x in state.sheets[value.actor.entity].assets
            if x.void and x.id not in overlays and not x.battery_asset
        ]

    def menu(self, viewer: GuildViewer) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            state = load_state(c, self.store.campaign_id)
            try:
                actor = current_ref(state, viewer.user_id)
                sheet, frame = current(state, actor)
                gate = Access(self.store)
                if gate.registry is None:
                    return dict(available=False)
                gate.registry.require_available(rules.RULE)
            except (ValueError, WorkflowError):
                return dict(available=False)
            self.game.character_binding(c, state, viewer.user_id)
            native = frame_class(sheet.frame) == "priestess"
            acquired = next(
                (
                    x
                    for x in state.requisitions
                    if isinstance(x, FrameRuleReceipt)
                    and x.actor == actor
                    and rules.receipt_eligible(state, x)
                ),
                None,
            )
            from girlframe.engine.m3_class_retention import binding

            chain = binding(state, acquired)[1] if acquired is not None else ()
            return dict(
                available=True,
                revision=state.revision,
                actor=actor.model_dump(mode="json"),
                frame=frame,
                owned=rules.held(state, actor) is not None,
                suspended=any(suspended(state, identity) for identity in chain),
                kind="ability_unlock" if native else "frame_grafting",
                price=2 if native else 3,
                donors=[] if native else list(DONORS),
                npcs=[
                    dict(id=x.id, label=x.name)
                    for x in state.world.npcs
                    if x.alive and x.revealed and "director" not in x.jobs
                ]
                if state.world
                else [],
                requests=[x["id"] for x in self._rows(c) if x["owner_id"] == str(viewer.user_id)],
            )

    def get(self, viewer: GuildViewer, identity: str, channel: int | None = None) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            state = load_state(c, self.store.campaign_id)
            row, value = self._source(c, state, identity)
            self._visible(viewer, value)
            locations = (
                [dict(id=x.id, label=x.name) for x in state.world.locations if x.operational]
                if state.world
                else []
            )
            period = None
            if value.phase in ("ready", "closed"):
                try:
                    period = self._period(c, value).id
                except WorkflowError:
                    pass
            return dict(
                id=identity,
                revision=row["revision"],
                game_revision=state.revision,
                therapy=value.model_dump(mode="json"),
                patient=viewer.user_id == int(value.actor.entity),
                controller=viewer.user_id == value.controller,
                period=period,
                assets=self._eligible(state, value) if value.actor.entity in state.sheets else [],
                locations=locations,
            )

    def _tasks(self, c: Connection, viewer: GuildViewer) -> list[dict[str, Any]]:
        state = load_state(c, self.store.campaign_id)
        result = []
        for row in self._rows(c):
            if str(viewer.user_id) not in (row["owner_id"], row["subject_id"]):
                continue
            _, value = self._source(c, state, row["id"])
            if value.phase in ("bond", "scene"):
                result.append(
                    dict(
                        id=value.id,
                        state=value.phase,
                        actionable=viewer.user_id == value.controller,
                    )
                )
        return result

    def buy(
        self,
        viewer: GuildViewer,
        key: str,
        revision: int,
        npc: str,
        account: str,
        donor_frame: str | None = None,
    ) -> dict[str, Any]:
        def change(c: Connection) -> dict[str, Any]:
            state = load_state(c, self.store.campaign_id)
            RequisitionService(self.game)._safe(c, state, viewer.user_id)
            actor = current_ref(state, viewer.user_id)
            sheet, frame = current(state, actor)
            native = frame_class(sheet.frame) == "priestess"
            price = 2 if native else 3
            donor = sheet.frame if native else donor_frame
            if (
                native
                and donor_frame not in (None, sheet.frame)
                or not native
                and donor not in DONORS
            ):
                raise WorkflowError("Select an actual Priestess donor for this non-Priestess graft")
            assert donor is not None
            self.game.character_binding(c, state, viewer.user_id)
            target = (
                next(
                    (
                        x
                        for x in state.world.npcs
                        if x.id == npc and x.alive and x.revealed and "director" not in x.jobs
                    ),
                    None,
                )
                if state.world
                else None
            )
            if (
                state.revision != revision
                or target is None
                or available(state, actor) < price
                or not account.strip()
                or len(account) > 1200
            ):
                raise WorkflowError("Refresh the actual purchase, NPC and available Permissions")
            if any(
                isinstance(x, FrameRuleReceipt)
                and x.actor == actor
                and rules.receipt_eligible(state, x)
                for x in state.requisitions
            ):
                raise WorkflowError("Restore the original paid relationship rather than buy twice")
            if not c.scalar(
                sa.select(t.members.c.user_id).where(
                    t.members.c.campaign_id == self.store.campaign_id,
                    t.members.c.user_id == str(target.controller),
                    t.members.c.active.is_(True),
                )
            ):
                raise WorkflowError("The NPC needs an actual current campaign human controller")
            identity, event = str(uuid4()), str(uuid4())
            value = rules.Therapy(
                id=identity,
                actor=actor,
                npc=ActorRef(kind="npc", entity=npc),
                controller=target.controller,
                purchase=identity,
                source_event=event,
                event=event,
                relationship=account,
            )
            payment = prepare_payment(self.game, c, state, viewer, actor, rules.RULE, price, donor)
            debit(state, actor, price, event=event, source=identity, payment=payment)
            sheet.revision += 1
            state.requisitions.append(
                FrameRuleReceipt(
                    id=identity,
                    kind="ability_unlock" if native else "frame_grafting",
                    actor=actor,
                    frame_instance=frame,
                    frame=sheet.frame,
                    donor_frame=donor,
                    rule_id=rules.RULE,
                    grant="physiotherapist:" + identity,
                    price=2 if native else 3,
                    account=account,
                    source_event=event,
                )
            )
            rules.put(state, value)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.ability_unlock_purchased" if native else "m3.frame_grafting_purchased",
                state,
                event_id=event,
                requisition_id=identity,
                rule_id=rules.RULE,
                cost=price,
            )
            related(
                c,
                self.store,
                dict(campaign_id=self.store.campaign_id, campaign_context=True),
                identity,
                viewer.user_id,
                target.controller,
                rules.KIND,
                dict(therapy=value.model_dump(mode="json")),
                event,
            )
            return dict(id=identity, cost=price)

        return self._write(
            viewer,
            key,
            "purchase",
            dict(revision=revision, npc=npc, account=account)
            | (dict(donor_frame=donor_frame) if donor_frame is not None else {}),
            change,
        )

    def _write(
        self, viewer: GuildViewer, key: str, operation: str, payload: dict[str, Any], change: Any
    ) -> dict[str, Any]:
        def access(c: Connection) -> None:
            gate = Access(self.store)
            gate.authorize(c, viewer, "economy", director_response=True)
            assert gate.registry is not None
            entry = gate.registry.require_available(rules.RULE)
            if (entry.scope, entry.frame_class, entry.frame_rule) != (
                "frame",
                "priestess",
                "class_requisition",
            ):
                raise WorkflowError("Recover the actual Priestess Class Physiotherapist source")
            self.game.unpaused(c)

        return self.store._write(
            viewer,
            key,
            "m3.physiotherapist_" + operation,
            payload,
            change,
            auto_audit=False,
            authorize=access,
        )

    def respond(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        expected: int,
        *,
        operation: str,
        account: str,
        channel: int | None = None,
        location: str = "",
        asset: str | None = None,
        tag: str = "",
    ) -> dict[str, Any]:
        def change(c: Connection) -> dict[str, Any]:
            state = load_state(c, self.store.campaign_id)
            row, value = self._source(c, state, identity)
            self._visible(viewer, value)
            self._current(c, state, value)
            if row["revision"] != revision or state.revision != expected or not account.strip():
                raise WorkflowError("Refresh this actual owned therapy response")
            RequisitionService(self.game)._safe(c, state, int(value.actor.entity))
            event = str(uuid4())
            new_scene = False
            if (
                operation == "accept"
                and value.phase == "bond"
                and viewer.user_id == value.controller
            ):
                state = set_depth(
                    state,
                    value.actor,
                    value.npc,
                    2 if depth(state, value.actor, value.npc) == 2 else 1,
                    event,
                )
                value = value.model_copy(update=dict(phase="ready", accepted_account=account))
            elif (
                operation == "scene"
                and value.phase in ("ready", "closed")
                and viewer.user_id == int(value.actor.entity)
            ):
                period = self._period(c, value)
                if channel is None or (
                    asset is not None
                    and asset not in {x["id"] for x in self._eligible(state, value)}
                ):
                    raise WorkflowError("Choose an actual permanent Void Asset or decline removal")
                from girlframe.services.m3_missions import MissionService

                casts = CastService(ActorService(MissionService(self.store)))
                cast, _ = casts._current(c, state, channel)
                actual = rules.scene(
                    state,
                    profiles(c, self.store.campaign_id),
                    value,
                    cast,
                    location,
                    account,
                    str(uuid4()),
                )
                value = value.model_copy(
                    update=dict(
                        id=str(uuid4()),
                        phase="scene",
                        scene=actual,
                        period=period.id,
                        asset=asset,
                        treatment="",
                        tag=None,
                    )
                )
                new_scene = True
            elif (
                operation == "treat"
                and value.phase == "scene"
                and viewer.user_id == value.controller
            ):
                period = self._period(c, value)
                if (
                    period.id != value.period
                    or not tag.strip()
                    or len(tag) > 80
                    or value.scene is None
                ):
                    raise WorkflowError("Record the actual scene, NPC-given Tag and treatment")
                if value.asset is not None:
                    if value.asset not in {x["id"] for x in self._eligible(state, value)}:
                        raise WorkflowError(
                            "Refresh the actual permanent Void Asset; "
                            "conditional storage is separate"
                        )
                    next(
                        x for x in state.sheets[value.actor.entity].assets if x.id == value.asset
                    ).void = False
                scene = value.scene.model_copy(
                    update=dict(
                        acknowledgements=tuple(
                            sorted({*value.scene.acknowledgements, viewer.user_id})
                        )
                    )
                )
                sheet = state.sheets[value.actor.entity]
                tag_id = str(uuid4())
                sheet.tags.append(
                    TagState(
                        id=tag_id,
                        label=tag.strip(),
                        giver=viewer.user_id,
                        giver_actor=value.npc,
                        observers=tuple(sorted({int(value.actor.entity), viewer.user_id})),
                    )
                )
                sheet.revision += 1
                value = value.model_copy(
                    update=dict(phase="closed", scene=scene, treatment=account, tag=tag_id)
                )
            else:
                raise WorkflowError(
                    "Only the actual original owner may answer this current scene step"
                )
            value = value.model_copy(update=dict(event=event))
            rules.put(state, value)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.physiotherapist_" + operation,
                state,
                event_id=event,
                therapy_id=value.id,
            )
            if new_scene:
                related(
                    c,
                    self.store,
                    dict(campaign_id=self.store.campaign_id, off_duty_id=value.period),
                    value.id,
                    int(value.actor.entity),
                    value.controller,
                    rules.KIND,
                    dict(therapy=value.model_dump(mode="json")),
                    event,
                )
                return dict(id=value.id, phase=value.phase)
            c.execute(
                t.m3["m3_required_work"]
                .insert()
                .values(
                    **{
                        k: v
                        for k, v in row.items()
                        if k
                        not in (
                            "revision",
                            "state",
                            "body_json",
                            "event_id",
                        )
                    },
                    revision=revision + 1,
                    state="pending" if value.phase in ("bond", "scene") else "resolved",
                    event_id=event,
                    body_json=json.dumps(
                        dict(therapy=value.model_dump(mode="json")), sort_keys=True
                    ),
                )
            )
            return dict(id=identity, phase=value.phase)

        return self._write(
            viewer,
            key,
            operation,
            dict(
                identity=identity,
                revision=revision,
                expected=expected,
                account=account,
                channel=channel,
                location=location,
                asset=asset,
                tag=tag,
            ),
            change,
        )
