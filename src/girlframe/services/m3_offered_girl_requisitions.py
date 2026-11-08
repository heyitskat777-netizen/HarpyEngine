"""Source-funded Girl gifts retain actual receipts, delayed scenes and career effects."""

import json
from typing import Any, cast
from uuid import NAMESPACE_URL, uuid4, uuid5

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_comforts as comforts
from girlframe.engine import m3_offered_requisition_state as rules
from girlframe.engine import m3_retirement as retirement
from girlframe.engine import m3_scene_requisitions as scenes
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_requisition_state import ComfortReceipt, RetirementReceipt, SceneReceipt
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_careers import end_in_transaction, synchronize_end
from girlframe.services.m3_handler_advancements import _history
from girlframe.services.m3_requisitions import RequisitionService
from girlframe.services.m3_vatgrown_plays import prove_offer
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer

type GiftReceipt = ComfortReceipt | SceneReceipt | RetirementReceipt
EVENT = "m3.girl_requisition_accepted"


def prove_receipt(game: GameService, c: Connection, state: GameState, receipt: GiftReceipt) -> None:
    if receipt.source_offer is None or receipt.price != 0:
        raise WorkflowError("Recover the actual source-funded offered receipt")
    accepted = next(
        (
            x
            for x in rules.records(state)
            if x.receipt == receipt.id and x.offer == receipt.source_offer
        ),
        None,
    )
    source = (
        c.execute(
            sa.select(t.events).where(
                t.events.c.campaign_id == game.store.campaign_id,
                t.events.c.id == receipt.source_event,
            )
        )
        .mappings()
        .first()
    )
    original = _history(c, game, receipt.source_event)
    saved = next((x for x in original.requisitions if x.id == receipt.id), None)
    metadata = json.loads(source["payload_json"]) if source else {}
    if (
        accepted is None
        or accepted not in rules.records(original)
        or saved != receipt
        or source is None
        or source["kind"] != EVENT
        or source["actor_id"] != receipt.actor.entity
        or metadata.get("offer_id") != receipt.source_offer
        or metadata.get("requisition_id") != receipt.id
        or metadata.get("requisition_kind") != receipt.kind
        or accepted.actor != receipt.actor
        or accepted.kind != receipt.kind
        or accepted.event != receipt.source_event
    ):
        raise WorkflowError("Preserve the immutable actual gift, recipient, kind and receipt")
    offer = prove_offer(game, c, original, accepted.offer)
    if (
        offer.actor != accepted.actor
        or offer.investor != accepted.investor
        or offer.kind != accepted.kind
    ):
        raise WorkflowError("This actual original Investor funded a different gift")
    if isinstance(receipt, SceneReceipt) and accepted.companion != receipt.companion:
        raise WorkflowError("Preserve the original recipient's actual Privacy companion")
    if isinstance(receipt, RetirementReceipt):
        archive = next((x for x in original.career_archives if x.id == receipt.archive_id), None)
        if (
            not accepted.confirmed_retirement
            or accepted.archive != receipt.archive_id
            or archive is None
            or archive.actor != receipt.actor
            or archive.ending != "retirement"
            or archive.source_event != receipt.source_event
        ):
            raise WorkflowError(
                "The actual offered Retirement must end the explicitly confirmed original career"
            )
    from girlframe.services.m3_asset_loss import snapshots

    before, after = snapshots(game, c, receipt.source_event)
    from girlframe.engine.m3_intracadre_marriage import PermissionFlow, records

    if any(
        x.event == receipt.source_event and x.kind in ("purchase", "grant")
        for x in records(after, PermissionFlow)
    ):
        raise WorkflowError("An offered gift cannot invent a Permission purchase or grant")
    # Genuine Retirement archives the original sheet; no charge/credit is hidden in the ending.
    old = before.sheets.get(receipt.actor.entity)
    current = after.sheets.get(receipt.actor.entity)
    if old is None or old.character_id != receipt.actor.incarnation:
        raise WorkflowError("Recover the actual original recipient at acceptance")
    if isinstance(receipt, RetirementReceipt):
        archive = next(x for x in after.career_archives if x.id == receipt.archive_id)
        archived = json.loads(archive.sheet_json)
        if archived.get("permissions") != old.permissions:
            raise WorkflowError("Offered Retirement cannot charge the original wallet")
    elif current is None or current.permissions != old.permissions:
        raise WorkflowError("An actual offered gift does not charge or credit Permissions")


def offer_receipt(game: GameService, c: Connection, state: GameState, offer_id: str) -> str | None:
    rows = [x for x in rules.records(state) if x.offer == offer_id]
    if len(rows) > 1:
        raise WorkflowError("One actual offer has exactly one actual accepted receipt")
    if not rows:
        return None
    receipt = next((x for x in state.requisitions if x.id == rows[0].receipt), None)
    if not isinstance(receipt, (ComfortReceipt, SceneReceipt, RetirementReceipt)):
        raise WorkflowError("Recover the actual accepted Girl Requisition effect receipt")
    prove_receipt(game, c, state, receipt)
    return receipt.id


def _result(receipt: GiftReceipt) -> dict[str, Any]:
    result: dict[str, Any] = dict(
        id=receipt.id, offer=receipt.source_offer, kind=receipt.kind, charged=0
    )
    if isinstance(receipt, RetirementReceipt):
        result.update(archive_id=receipt.archive_id, ending="retirement")
    return result


def accept_offer(
    game: GameService,
    viewer: GuildViewer,
    key: str,
    offer: str,
    revision: int,
    account: str,
    *,
    companion: ActorRef | None = None,
    confirmed_retirement: bool = False,
) -> dict[str, Any]:
    if not account.strip() or len(account) > 1200:
        raise WorkflowError("Explicitly accept the actual source-funded Girl Requisition")
    store = game.store

    def authorize(c: Connection) -> None:
        Access(store).authorize(c, viewer, "economy", director_response=True)

    def operation(c: Connection) -> dict[str, Any]:
        game.unpaused(c)
        state = load_state(c, store.campaign_id)
        existing = offer_receipt(game, c, state, offer)
        if existing:
            receipt = next(x for x in state.requisitions if x.id == existing)
            if (
                receipt.actor.entity != str(viewer.user_id)
                or not isinstance(receipt, (ComfortReceipt, SceneReceipt, RetirementReceipt))
                or isinstance(receipt, SceneReceipt)
                and companion is not None
                and receipt.companion != companion
            ):
                raise WorkflowError(
                    "This actual accepted gift belongs to its original recipient and choice"
                )
            return _result(receipt)
        if state.revision != revision:
            raise WorkflowError("STALE_OFFER: reopen the actual offered Requisition")
        source = prove_offer(game, c, state, offer)
        if (
            source.actor.kind != "pilot"
            or source.actor.entity != str(viewer.user_id)
            or current_ref(state, viewer.user_id) != source.actor
            or source.kind not in rules.KINDS
        ):
            raise WorkflowError(
                "Only the actual original current recipient may accept this exact gift"
            )
        RequisitionService(game)._safe(c, state, viewer.user_id)
        actor = resolve(state, source.actor, profiles(c, store.campaign_id))
        if actor.controller != viewer.user_id or not actor.alive or actor.offstage_source:
            raise WorkflowError("Use the actual available original recipient")
        if source.kind != "privacy" and companion is not None:
            raise WorkflowError("Only the recipient's actual Privacy choice names another Girl")
        if source.kind == "privacy" and companion is None:
            raise WorkflowError("PRIVACY_COMPANION_REQUIRED: choose the actual other Girl")
        if source.kind == "retirement" and confirmed_retirement is not True:
            raise WorkflowError(
                "RETIREMENT_CONFIRMATION_REQUIRED: explicitly confirm this original career ending"
            )
        if source.kind != "retirement" and confirmed_retirement:
            raise WorkflowError("This gift does not authorize a career ending")
        identity = str(uuid5(NAMESPACE_URL, "girlframe:offered-girl:" + offer))
        event, archive = str(uuid4()), None
        bound = profiles(c, store.campaign_id)
        if source.kind == "creature_comforts":
            state = comforts.grant_offered(
                state,
                source.actor,
                bound,
                actor.source_sha256,
                identity,
                event,
                account.strip(),
                offer,
            )
        elif source.kind in ("privacy", "visiting_home"):
            state = scenes.grant_offered(
                state,
                source.actor,
                bound,
                actor.source_sha256,
                cast(scenes.Kind, source.kind),
                companion,
                account.strip(),
                identity,
                event,
                offer,
            )
        else:
            archive = str(uuid5(NAMESPACE_URL, "girlframe:offered-retirement:" + offer))
            state = retirement.grant_offered(
                state,
                source.actor,
                bound,
                actor.source_sha256,
                account.strip(),
                identity,
                archive,
                event,
                offer,
            )
            state = end_in_transaction(
                c,
                game,
                state,
                source.actor,
                reason="retirement",
                source_event=event,
                account=account.strip(),
                archive_id=archive,
            )
            state.facts.append(
                dict(
                    kind="retirement_discharge",
                    actor=source.actor.model_dump_json(),
                    source_event=event,
                    receipt=identity,
                )
            )
        rules.put(
            state,
            rules.OfferedAcceptance(
                id=identity,
                offer=offer,
                receipt=identity,
                actor=source.actor,
                investor=source.investor,
                kind=cast(rules.Kind, source.kind),
                event=event,
                companion=companion,
                archive=archive,
                confirmed_retirement=confirmed_retirement,
            ),
        )
        game.event(
            c,
            viewer.user_id,
            key,
            EVENT,
            state,
            event_id=event,
            offer_id=offer,
            requisition_id=identity,
            requisition_kind=source.kind,
        )
        if archive is not None:
            synchronize_end(c, game, next(x for x in state.career_archives if x.id == archive))
        receipt = next(x for x in state.requisitions if x.id == identity)
        assert isinstance(receipt, (ComfortReceipt, SceneReceipt, RetirementReceipt))
        return _result(receipt)

    try:
        return store._write(
            viewer,
            key,
            EVENT,
            dict(
                offer=offer,
                revision=revision,
                account=account,
                companion=companion.model_dump(mode="json") if companion else None,
                confirmed_retirement=confirmed_retirement,
            ),
            operation,
            auto_audit=False,
            authorize=authorize,
        )
    except ValueError as error:
        raise WorkflowError(str(error)) from None
