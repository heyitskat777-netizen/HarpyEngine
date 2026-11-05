"""Actual object-source proofs and atomic theft; descriptions grant no Asset slots."""

import hashlib
import json
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_items as rules
from girlframe.engine.m2 import AssetState, GameState
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_handler_consequences import active_handler
from girlframe.engine.m3_item_state import HeldItem
from girlframe.engine.m3_role_punishments import view
from girlframe.services.handler_setup import HandlerService
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_work import related
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer

KIND = "held_item_fact"


def _snapshot(c: Connection, game: GameService, event: str | None) -> GameState | None:
    body = (
        c.scalar(
            sa.select(t.m2["m2_state_history"].c.body_json).where(
                t.m2["m2_state_history"].c.campaign_id == game.store.campaign_id,
                t.m2["m2_state_history"].c.event_id == event,
            )
        )
        if event
        else None
    )
    return GameState.model_validate_json(body) if body else None


def prove_item(c: Connection, game: GameService, state: GameState, item_id: str) -> HeldItem:
    item = next((x for x in state.held_items if x.id == item_id), None)
    if item is None:
        raise WorkflowError("SOURCE_ITEM_MISSING: recover the actual held object.")
    original = _snapshot(c, game, item.source_event)
    first = next((x for x in original.held_items if x.id == item.id), None) if original else None
    stable = (
        "id",
        "source_event",
        "source_owner",
        "origin_event",
        "origin_asset_json",
        "proposed_event",
        "confirmed_by",
        "confirmed_controller",
        "confirmed_event",
        "factual_source_action",
        "weapon",
    )
    if first is None or any(getattr(first, k) != getattr(item, k) for k in stable):
        raise WorkflowError("SOURCE_ITEM_MISSING: recover the immutable original possession proof.")
    if item.source_owner.kind == "handler" and item.confirmed_event and item.origin_asset_json:
        from girlframe.services.m3_handler_girl_void import prove_handler_item

        prove_handler_item(c, game, state, item)
    elif item.origin_asset_json:
        old = _snapshot(c, game, item.origin_event)
        source = old.sheets.get(item.source_owner.entity) if old else None
        asset = AssetState.model_validate_json(item.origin_asset_json)
        if (
            item.source_owner.kind != "pilot"
            or source is None
            or source.character_id != item.source_owner.incarnation
            or not any(x == asset for x in source.assets)
        ):
            raise WorkflowError(
                "SOURCE_ITEM_ASSET_MISSING: recover the original actual owned Asset."
            )
    elif item.factual_source_action and game.action(c, item.factual_source_action)["data"].get(
        "snoop"
    ):
        from girlframe.services.m3_enforcer_snoop import prove_object

        prove_object(c, game, state, item)
    else:
        event = (
            c.execute(
                sa.select(t.events).where(
                    t.events.c.campaign_id == game.store.campaign_id,
                    t.events.c.id == item.confirmed_event,
                )
            )
            .mappings()
            .first()
        )
        if (
            event is None
            or event["kind"] != "m3.held_item_fact_confirmed"
            or event["actor_id"] != str(item.confirmed_controller)
            or original is None
            or original.handler != item.confirmed_controller
        ):
            raise WorkflowError(
                "SOURCE_ITEM_FACT_MISSING: recover the actual factual confirmation."
            )
    latest = _snapshot(c, game, item.state_event or item.transferred_event or item.source_event)
    saved = next((x for x in latest.held_items if x.id == item.id), None) if latest else None
    if saved != item:
        raise WorkflowError("SOURCE_ITEM_CUSTODY_MISSING: recover the latest actual custody event.")
    return item


def _weapon_asset(state: GameState, holder: ActorRef, asset: AssetState) -> bool:
    if any(
        x.actor == holder and any(i.asset == asset.id for i in x.issues)
        for x in state.personal_firearms
    ):
        return True
    sheet = state.sheets.get(holder.entity) if holder.kind == "pilot" else None
    if sheet and sheet.character_id == holder.incarnation:
        for index, chosen in enumerate(sheet.review.creation.girl_assets):
            if chosen.name == "Gun (legal)" and asset.id == "girl:" + str(index):
                return True
    return False


def available_items(
    c: Connection,
    game: GameService,
    state: GameState,
    holder: ActorRef,
    *,
    weapons_only: bool = False,
    scene: str | None = None,
) -> list[dict[str, Any]]:
    view(state, holder, profiles(c, game.store.campaign_id))
    result: list[dict[str, Any]] = []
    bindings: set[str] = set()
    if holder.kind == "pilot":
        for asset in state.sheets[holder.entity].assets:
            if asset.family != "girl" or asset.concealed or asset.battery_asset is not None:
                continue
            recorded = next(
                (
                    x
                    for x in state.held_items
                    if x.holder == holder and x.asset_owner == holder and x.asset_id == asset.id
                ),
                None,
            )
            if recorded:
                prove_item(c, game, state, recorded.id)
                if recorded.location_mode == "scene" and (
                    weapons_only or recorded.scene_id != scene
                ):
                    continue
                bindings.add(recorded.id)
            if recorded is None and not _weapon_asset(state, holder, asset):
                # Owning a body part/trait is not proof of a takeable held object.
                continue
            weapon = not asset.damaged and (
                bool(recorded and recorded.weapon) or _weapon_asset(state, holder, asset)
            )
            if not weapons_only or weapon:
                result.append(
                    dict(id="asset:" + asset.id, label=asset.name, mechanical=True, weapon=weapon)
                )
    for item in state.held_items:
        if not rules.same_holder(state, item.holder, holder) or item.id in bindings:
            continue
        if item.location_mode == "scene" and (weapons_only or item.scene_id != scene):
            continue
        if (
            item.asset_json is None
            and item.condition == "ruined"
            and (weapons_only or scene is None)
        ):
            continue
        prove_item(c, game, state, item.id)
        actual = rules.actual_asset(state, item)
        if item.asset_owner == holder and holder.kind == "pilot" and actual is None:
            continue
        if actual is not None and (actual.family != "girl" or actual.concealed):
            continue
        weapon = item.weapon and (actual is None or not actual.damaged)
        if not weapons_only or weapon:
            result.append(
                dict(id=item.id, label=item.name, mechanical=actual is not None, weapon=weapon)
            )
    return result


def take_in_transaction(
    c: Connection,
    game: GameService,
    state: GameState,
    *,
    source: ActorRef,
    recipient: ActorRef,
    selection: str,
    action: str,
    event: str,
    account: str,
    replace: str | None = None,
    inside_frame: bool | None = None,
    source_work: str | None = None,
    snoop: bool = False,
) -> GameState:
    scene = None
    alpha_sex = False
    if source_work is None and not snoop:
        raw_action = c.scalar(
            sa.select(t.m2["m2_actions"].c.body_json).where(
                t.m2["m2_actions"].c.campaign_id == game.store.campaign_id,
                t.m2["m2_actions"].c.id == action,
            )
        )
        alpha_sex = bool(raw_action and json.loads(raw_action).get("alpha_sex"))
        actual_action = game.action(c, action) if alpha_sex else None
        if alpha_sex:
            assert actual_action is not None
            from girlframe.services.m3_alpha_sex import (
                validate_transfer_source as validate_alpha_transfer,
            )

            validate_alpha_transfer(c, game, state, actual_action, source, recipient)
    if snoop:
        from girlframe.services.m3_enforcer_snoop import validate_transfer_source

        scene = validate_transfer_source(c, game, state, action, source, recipient, selection)
    if selection not in {x["id"] for x in available_items(c, game, state, source, scene=scene)}:
        raise WorkflowError(
            "Select an actual accessible object from its current original custodian."
        )
    if not selection.startswith("asset:"):
        prove_item(c, game, state, selection)
    history = t.m2["m2_state_history"]
    origin = c.scalar(
        sa.select(history.c.event_id)
        .where(history.c.campaign_id == game.store.campaign_id)
        .order_by(history.c.revision.desc())
        .limit(1)
    )
    if origin is None:
        raise WorkflowError("Recover the actual canonical possession source before this transfer.")
    if source_work is not None:
        from girlframe.services.m3_battle_npc import NpcDamageService

        service = NpcDamageService(game.store)
        source_row = service._row(c, source_work)
        actual_source, actual_recipient = service._proof(c, source_row)
        if (
            source_row["state"] == "resolved"
            or actual_source != source
            or actual_recipient != recipient
            or (json.loads(source_row["body_json"]).get("source_action") or source_work) != action
        ):
            raise WorkflowError(
                "Use the exact actual NPC damage source and original physical attacker."
            )
    changed = rules.take(
        state,
        source,
        recipient,
        profiles(c, game.store.campaign_id),
        selection,
        action,
        event,
        account,
        origin_event=origin,
        replace=replace,
        inside_frame=inside_frame,
        scene=scene,
    )
    if new_void_families(state, changed):
        source_action = game.action(c, action) if source_work is None else None
        if (
            source_work is None
            and source_action is not None
            and not source_action["data"].get("enforcement")
            and not snoop
        ):
            raise WorkflowError(
                "This source needs its actual item-removal Void continuation "
                "before taking the object."
            )
    transfer = changed.item_transfers[-1].model_copy(
        update=dict(
            source_work=source_work,
            source_kind="alpha_sex"
            if alpha_sex
            else "enforcer_snoop"
            if snoop
            else "npc_damage"
            if source_work
            else "enforcement_initiative",
        )
    )
    changed.item_transfers[-1] = transfer
    old_asset = (
        next((x for x in state.sheets[source.entity].assets if selection == "asset:" + x.id), None)
        if source.kind == "pilot"
        else None
    )
    if old_asset and _weapon_asset(state, source, old_asset):
        changed.held_items = [
            x.model_copy(update={"weapon": True})
            if x.id == transfer.item and x.source_event == event
            else x
            for x in changed.held_items
        ]
    return changed


class ItemService:
    """Prove an existing unmodeled possession; confirmation creates no Asset statistics."""

    def __init__(self, game: GameService):
        self.game, self.store = game, game.store

    def _row(self, c: Connection, identity: str) -> dict[str, Any]:
        table = t.m3["m3_required_work"]
        row = (
            c.execute(
                sa.select(table)
                .where(
                    table.c.campaign_id == self.store.campaign_id,
                    table.c.id == identity,
                    table.c.kind == KIND,
                )
                .order_by(table.c.revision.desc())
                .limit(1)
            )
            .mappings()
            .first()
        )
        if row is None:
            raise WorkflowError("Recover the original held-item factual proposal.")
        return dict(row)

    def _tasks(self, c: Connection, viewer: GuildViewer) -> list[dict[str, Any]]:
        self.game.authorize(c, viewer, game=False)
        table = t.m3["m3_required_work"]
        latest = {
            x["id"]: dict(x)
            for x in c.execute(
                sa.select(table)
                .where(table.c.campaign_id == self.store.campaign_id, table.c.kind == KIND)
                .order_by(table.c.revision)
            ).mappings()
        }
        return [
            dict(
                id=x["id"],
                revision=x["revision"],
                state=x["state"],
                actionable=x["owner_id"] == str(viewer.user_id),
            )
            for x in latest.values()
            if str(viewer.user_id) in (x["owner_id"], x["subject_id"])
        ]

    def get(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            row = self._row(c, identity)
            if str(viewer.user_id) not in (row["owner_id"], row["subject_id"]):
                raise WorkflowError(
                    "This possession fact belongs to its actual source participants."
                )
            return dict(
                id=identity,
                revision=row["revision"],
                state=row["state"],
                body=json.loads(row["body_json"]),
                can_confirm=str(viewer.user_id) == row["owner_id"],
            )

    def propose(
        self,
        viewer: GuildViewer,
        key: str,
        holder: ActorRef,
        name: str,
        description: str,
        *,
        weapon: bool = False,
        action: str | None = None,
        asset_id: str | None = None,
    ) -> dict[str, Any]:
        if (
            not name.strip()
            or not description.strip()
            or len(name) > 120
            or len(description) > 1200
        ):
            raise WorkflowError("Name and describe the actual existing object, not a new Asset.")

        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            actor = view(state, holder, profiles(c, self.store.campaign_id))
            if actor.controller != viewer.user_id or state.handler is None:
                raise WorkflowError(
                    "The actual holder's human proposes; the appointed Handler confirms."
                )
            if any(
                x.holder == holder and x.name.casefold() == name.strip().casefold()
                for x in state.held_items
            ):
                raise WorkflowError(
                    "Use the existing actual object and its original custody proof."
                )
            asset = None
            if asset_id is not None:
                if holder.kind != "pilot":
                    raise WorkflowError(
                        "Only the actual original Girl sheet supplies this Asset proof."
                    )
                asset = next(
                    (
                        x
                        for x in state.sheets[holder.entity].assets
                        if x.id == asset_id and x.family == "girl" and not x.concealed
                    ),
                    None,
                )
                if asset is None:
                    raise WorkflowError(
                        "Select an actual accessible Girl Asset; "
                        "no body/Frame detachment is granted."
                    )
                if any(
                    x.source_owner == holder
                    and x.origin_asset_json is not None
                    and AssetState.model_validate_json(x.origin_asset_json).id == asset_id
                    for x in state.held_items
                ):
                    raise WorkflowError(
                        "Recover the existing actual object's custody; do not duplicate it."
                    )
            identity, event = str(uuid4()), str(uuid4())
            scope: dict[str, Any] = dict(campaign_id=self.store.campaign_id, campaign_context=True)
            if action:
                source = self.game.action(c, action)
                if source["state"] == "complete":
                    raise WorkflowError("Use the actual pending source scene.")
                scope = dict(campaign_id=self.store.campaign_id, scene_id=source["scene_id"])
            proposal = dict(
                holder=holder.model_dump(mode="json"),
                name=name.strip(),
                description=description.strip(),
                weapon=weapon,
                source_action=action,
                proposed_event=event,
                asset_json=asset.model_dump_json() if asset is not None else None,
            )
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.held_item_fact_proposed",
                event_id=event,
                holder=holder.model_dump(mode="json"),
                work_id=identity,
                proposal_sha256=hashlib.sha256(
                    json.dumps(proposal, sort_keys=True).encode()
                ).hexdigest(),
            )
            related(
                c, self.store, scope, identity, state.handler, viewer.user_id, KIND, proposal, event
            )
            return dict(id=identity, state="pending")

        return self.store._write(
            viewer,
            key,
            "m3.held_item_propose",
            dict(
                holder=holder.model_dump(mode="json"),
                name=name,
                description=description,
                weapon=weapon,
                action=action,
                asset_id=asset_id,
            ),
            operation,
            authorize=lambda c: Access(self.store).authorize(c, viewer, "discipline"),
            auto_audit=False,
        )

    def confirm(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        *,
        exists: bool,
        account: str,
    ) -> dict[str, Any]:
        if not account.strip() or len(account) > 1200:
            raise WorkflowError("Record the factual evidence for this existing possession.")

        def operation(c: Connection) -> dict[str, Any]:
            HandlerService(self.store).authorize(c, viewer)
            self.game.unpaused(c)
            row = self._row(c, identity)
            if (
                row["revision"] != revision
                or row["state"] == "resolved"
                or row["owner_id"] != str(viewer.user_id)
            ):
                raise WorkflowError("STALE_ITEM_FACT: reopen the actual pending factual proposal.")
            body = json.loads(row["body_json"])
            source = (
                c.execute(
                    sa.select(t.events).where(
                        t.events.c.campaign_id == self.store.campaign_id,
                        t.events.c.id == body["proposed_event"],
                    )
                )
                .mappings()
                .first()
            )
            if (
                source is None
                or source["kind"] != "m3.held_item_fact_proposed"
                or source["actor_id"] != row["subject_id"]
                or json.loads(source["payload_json"]).get("proposal_sha256")
                != hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()
            ):
                raise WorkflowError("Recover the original holder's immutable proposal.")
            state = load_state(c, self.store.campaign_id)
            holder = ActorRef.model_validate(body["holder"])
            if view(state, holder, profiles(c, self.store.campaign_id)).controller != int(
                row["subject_id"]
            ):
                raise WorkflowError(
                    "This fact belongs to the original actual holder, not a replacement."
                )
            asset = (
                AssetState.model_validate_json(body["asset_json"])
                if body.get("asset_json")
                else None
            )
            if asset is not None:
                if any(
                    x.source_owner == holder
                    and x.origin_asset_json is not None
                    and AssetState.model_validate_json(x.origin_asset_json).id == asset.id
                    for x in state.held_items
                ):
                    raise WorkflowError(
                        "This exact physical Asset already has a source custody record."
                    )
                actual = next(
                    (x for x in state.sheets[holder.entity].assets if x.id == asset.id), None
                )
                if actual != asset:
                    raise WorkflowError(
                        "The actual proposed Asset changed; do not confirm a replacement's object."
                    )
            history = t.m2["m2_state_history"]
            prior = c.scalar(
                sa.select(history.c.event_id)
                .where(history.c.campaign_id == self.store.campaign_id)
                .order_by(history.c.revision.desc())
                .limit(1)
            )
            event = str(uuid4())
            if exists:
                if any(x.id == identity for x in state.held_items):
                    raise WorkflowError("This actual object was already confirmed.")
                state.held_items.append(
                    HeldItem(
                        id=identity,
                        holder=holder,
                        source_owner=holder,
                        name=asset.name if asset is not None else body["name"],
                        description=body["description"],
                        origin_event=prior if asset is not None else None,
                        origin_asset_json=body.get("asset_json"),
                        asset_json=body.get("asset_json"),
                        asset_id=asset.id if asset is not None else None,
                        asset_owner=holder if asset is not None else None,
                        source_event=event,
                        state_event=event,
                        proposed_event=body["proposed_event"],
                        confirmed_by=active_handler(state),
                        confirmed_controller=viewer.user_id,
                        confirmed_event=event,
                        factual_source_action=body["source_action"],
                        weapon=bool(
                            body["weapon"]
                            or asset is not None
                            and _weapon_asset(state, holder, asset)
                        ),
                    )
                )
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.held_item_fact_confirmed" if exists else "m3.held_item_fact_rejected",
                state,
                event_id=event,
                work_id=identity,
            )
            c.execute(
                t.m3["m3_required_work"]
                .insert()
                .values(
                    **{
                        k: v
                        for k, v in row.items()
                        if k not in ("revision", "event_id", "body_json", "state")
                    },
                    revision=revision + 1,
                    event_id=event,
                    state="resolved",
                    body_json=json.dumps(
                        body | dict(exists=exists, evidence=account.strip(), effect_event=event)
                    ),
                )
            )
            return dict(
                id=identity,
                state="confirmed" if exists else "rejected",
                item=identity if exists else None,
            )

        return self.store._write(
            viewer,
            key,
            "m3.held_item_confirm",
            dict(id=identity, revision=revision, exists=exists, account=account),
            operation,
            authorize=lambda c: Access(self.store).authorize(c, viewer, "discipline"),
            auto_audit=False,
        )


def prove_transfer(
    c: Connection, game: GameService, identity: str
) -> tuple[GameState, GameState, Any]:
    state = load_state(c, game.store.campaign_id)
    transfer = next((x for x in state.item_transfers if x.id == identity), None)
    after = _snapshot(c, game, transfer.event) if transfer else None
    before = _snapshot(c, game, transfer.prior_event) if transfer else None
    original = next((x for x in after.item_transfers if x.id == identity), None) if after else None
    if transfer is None or original != transfer or before is None or after is None:
        raise WorkflowError(
            "SOURCE_TRANSFER_MISSING: recover the actual before/after possession event."
        )
    if any(x.id == identity for x in before.item_transfers):
        raise WorkflowError("The actual source transfer must be new in its committed effect event.")
    if transfer.source.kind == "pilot" and transfer.removed_asset is not None:
        source = before.sheets.get(transfer.source.entity)
        if (
            source is None
            or source.character_id != transfer.source.incarnation
            or not any(x.id == transfer.removed_asset for x in source.assets)
        ):
            raise WorkflowError("Recover the actual removed original Girl Asset source.")
        if any(x.id == transfer.removed_asset for x in after.sheets[transfer.source.entity].assets):
            raise WorkflowError("The source object was not actually removed.")
    item = prove_item(c, game, after, transfer.item)
    if (
        not rules.same_holder(after, item.holder, transfer.recipient)
        or item.transferred_event != transfer.event
    ):
        raise WorkflowError("Recover the actual receiving original custodian and physical object.")
    if transfer.recipient.kind == "pilot" and transfer.received_asset:
        target = after.sheets.get(transfer.recipient.entity)
        if (
            target is None
            or target.character_id != transfer.recipient.incarnation
            or not any(x.id == transfer.received_asset for x in target.assets)
        ):
            raise WorkflowError("Recover the actual receiving Girl's installed Asset.")
    return before, after, transfer


def new_void_families(before: GameState, after: GameState) -> list[ActorRef]:
    result = []
    for key, sheet in after.sheets.items():
        old = before.sheets.get(key)
        if sheet.character_id is None:
            continue
        from girlframe.engine.m3_janus_storage import effective_assets

        actor = ActorRef(kind="pilot", entity=key, incarnation=sheet.character_id)
        current = [x for x in effective_assets(after, actor) if x.family == "girl"]
        prior = [x for x in effective_assets(before, actor) if x.family == "girl"] if old else []
        if (
            old
            and old.character_id == sheet.character_id
            and sheet.character_id
            and current
            and all(x.void for x in current)
            and not (prior and all(x.void for x in prior))
        ):
            result.append(ActorRef(kind="pilot", entity=key, incarnation=sheet.character_id))
    return result


def create_snoop_item_void(
    game: GameService, c: Connection, transfer_id: str, event: str
) -> tuple[str, ...]:
    """The actual committed Snoop transfer opens its original owned threshold."""
    from uuid import NAMESPACE_URL, uuid5

    from girlframe.services.m3_void import _append, prepare_threshold

    before, after, transfer = prove_transfer(c, game, transfer_id)
    action = game.action(c, transfer.action)
    meta = action["data"].get("snoop") or {}
    if (
        transfer.source_kind != "enforcer_snoop"
        or transfer.event != event
        or transfer_id not in meta.get("transfers", [])
    ):
        raise WorkflowError("Recover the actual committed Snoop object-transfer event.")
    result = []
    for owner in new_void_families(before, after):
        identity = str(
            uuid5(NAMESPACE_URL, "girlframe:snoop-item-void:" + transfer_id + ":" + owner.token)
        )
        table = t.m3["m3_required_work"]
        if c.scalar(
            sa.select(table.c.id)
            .where(table.c.campaign_id == game.store.campaign_id, table.c.id == identity)
            .limit(1)
        ):
            result.append(identity)
            continue
        related(
            c,
            game.store,
            dict(campaign_id=game.store.campaign_id, scene_id=action["scene_id"]),
            identity,
            int(owner.entity),
            int(owner.entity),
            "void_threshold",
            dict(
                reason="item_transfer",
                item_source="enforcer_snoop",
                owner=owner.model_dump(mode="json"),
                character=owner.incarnation,
                source_action=action["id"],
                source_pdf=19,
                immediate=True,
                transfer=transfer_id,
                details=dict(family="girl"),
            ),
            event,
        )
        game.request(
            c, action, int(owner.entity), "snoop_item_void_threshold", dict(work_id=identity)
        )
        game.save_action(c, action)
        updated, value = prepare_threshold(c, game, identity)
        opened = game.event(
            c,
            meta["procedural_gm"],
            str(uuid4()),
            "m3.snoop_item_void_opened",
            updated,
            source_event=event,
            work_id=identity,
        )
        if value.stage == "prevented":
            row = dict(
                c.execute(
                    sa.select(table)
                    .where(table.c.campaign_id == game.store.campaign_id, table.c.id == identity)
                    .order_by(table.c.revision.desc())
                    .limit(1)
                )
                .mappings()
                .one()
            )
            _append(
                c,
                row,
                opened,
                json.loads(row["body_json"])
                | dict(threshold=value.id, resolution=value.stage, actual_actor=None),
                resolved=True,
            )
            from girlframe.services.m3_enforcer_snoop import complete_item_void

            complete_item_void(game, c, identity, opened, None, str(uuid4()))
        result.append(identity)
    return tuple(result)


def create_npc_item_void(
    game: GameService, c: Connection, transfer_id: str, event: str
) -> tuple[str, ...]:
    """After the real NPC effect commits inside its transaction, open its owned thresholds."""
    from uuid import NAMESPACE_URL, uuid5

    from girlframe.services.m3_battle_npc import NpcDamageService
    from girlframe.services.m3_void import _append, prepare_threshold

    before, after, transfer = prove_transfer(c, game, transfer_id)
    if (
        transfer.source_kind != "npc_damage"
        or transfer.source_work is None
        or transfer.event != event
    ):
        raise WorkflowError("Use the exact committed original NPC item-transfer event.")
    source = NpcDamageService(game.store)._row(c, transfer.source_work)
    parent = json.loads(source["body_json"])
    actual = (
        c.execute(
            sa.select(t.events).where(
                t.events.c.campaign_id == game.store.campaign_id, t.events.c.id == event
            )
        )
        .mappings()
        .first()
    )
    if actual is None or actual["kind"] != "m3.npc_damage_applied":
        raise WorkflowError("Recover the actual NPC damage item effect audit.")
    result = []
    for owner in new_void_families(before, after):
        identity = str(
            uuid5(NAMESPACE_URL, "girlframe:npc-item-void:" + transfer_id + ":" + owner.token)
        )
        table = t.m3["m3_required_work"]
        if not c.scalar(
            sa.select(table.c.id)
            .where(table.c.campaign_id == game.store.campaign_id, table.c.id == identity)
            .limit(1)
        ):
            related(
                c,
                game.store,
                source,
                identity,
                int(owner.entity),
                int(owner.entity),
                "void_threshold",
                dict(
                    reason="item_transfer",
                    item_source="npc_damage",
                    source_work=transfer.source_work,
                    owner=owner.model_dump(mode="json"),
                    character=owner.incarnation,
                    source_action=parent.get("source_action"),
                    source_pdf=19,
                    immediate=True,
                    transfer=transfer_id,
                    details=dict(family="girl"),
                ),
                event,
            )
            if parent.get("source_action"):
                action = game.action(c, parent["source_action"])
                game.request(
                    c,
                    action,
                    int(owner.entity),
                    "battle_item_void_threshold",
                    dict(work_id=identity),
                )
                game.save_action(c, action)
            updated, value = prepare_threshold(c, game, identity)
            opened = game.event(
                c,
                actual["actor_id"],
                str(uuid4()),
                "m3.npc_item_void_threshold_opened",
                updated,
                source_event=event,
                work_id=identity,
            )
            if value.stage == "prevented":
                row = (
                    c.execute(
                        sa.select(table)
                        .where(
                            table.c.campaign_id == game.store.campaign_id, table.c.id == identity
                        )
                        .order_by(table.c.revision.desc())
                        .limit(1)
                    )
                    .mappings()
                    .one()
                )
                _append(
                    c,
                    dict(row),
                    opened,
                    json.loads(row["body_json"])
                    | dict(threshold=value.id, resolution=value.stage, actual_actor=None),
                    resolved=True,
                )
                from girlframe.services.m3_battle_npc import complete_void_continuation

                complete_void_continuation(
                    game, c, identity, opened, None, str(actual["command_key"])
                )
        result.append(identity)
    return tuple(result)
