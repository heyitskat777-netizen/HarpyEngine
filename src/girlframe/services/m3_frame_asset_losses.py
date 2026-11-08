"""Explicit source producers share one immutable Frame-loss selection shape."""

import json
from typing import Any, Literal

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_consume as consume
from girlframe.engine.m2 import AssetState, ChoiceAnswer, GameState
from girlframe.engine.m3_actor_state import ActorRef, Model
from girlframe.engine.m3_budget_removal import blocked
from girlframe.engine.m3_core import install
from girlframe.engine.m3_defeat_state import Alternative, Decision
from girlframe.engine.m3_janus_storage import ids as stored_ids
from girlframe.engine.m3_requisition_state import Receipt
from girlframe.engine.m3_requisitions import asset_name
from girlframe.services.m2_game import GameService
from girlframe.services.m3_asset_loss import snapshots
from girlframe.services.m3_privileges import purchase_proof
from girlframe.services.onboarding import WorkflowError


class FrameAssetLoss(Model):
    source_kind: Literal["budget", "asset_installment", "defeat_alternative"]
    id: str
    actor: ActorRef
    frame: str
    event: str
    asset: AssetState


def installment_loss(
    game: GameService, c: Connection, state: GameState, receipt: Receipt
) -> FrameAssetLoss | None:
    """Only a real paid cap exchange proves this source; a generic diff proves nothing."""
    if receipt.installation.replace is None:
        raise WorkflowError("Use an actual paid Asset Installment cap replacement")
    purchase_proof(c, game.store, receipt)
    before, born = snapshots(game, c, receipt.source_event)
    actor = receipt.actor
    old_sheet, new_sheet = before.sheets.get(actor.entity), born.sheets.get(actor.entity)
    current = state.sheets.get(actor.entity)
    original = next((x for x in born.requisitions if x.id == receipt.id), None)
    if (
        actor.kind != "pilot"
        or old_sheet is None
        or new_sheet is None
        or current is None
        or any(
            x.character_id != actor.incarnation or x.frame_scrapped
            for x in (old_sheet, new_sheet, current)
        )
        or original != receipt
        or any(
            consume.frame(actual, actor) != receipt.frame_instance
            for actual in (before, born, state)
        )
    ):
        raise WorkflowError("Keep the actual original purchaser and same current living Frame")
    old = next((x for x in old_sheet.assets if x.id == receipt.installation.replace), None)
    installed = next((x for x in new_sheet.assets if x.id == receipt.asset_id), None)
    if (
        old is None
        or old.family != "frame"
        or installed is None
        or installed.family != "frame"
        or installed.id != "requisition:" + receipt.id
        or installed.name != asset_name(receipt.installation)
        or installed.description != receipt.installation.description.strip()
        or installed.damaged
        or installed.void
        or installed.intrinsic is not None
        or any(x.id == old.id for x in new_sheet.assets)
    ):
        raise WorkflowError("Prove the actual removed permanent component and paid new Asset")
    # Reuse the real install reducer's cap/Void/slot rules, without replaying debit.
    try:
        expected = install(
            old_sheet,
            installed,
            replace=old.id,
            effective_void=stored_ids(before, actor),
            state=before,
        )
    except ValueError as error:
        raise WorkflowError("Recover the actual legal paid cap exchange: " + str(error)) from None
    if expected.sheet.assets != new_sheet.assets:
        raise WorkflowError("Preserve this source's exact legal paid component exchange")
    # Valid source, unsuitable regrowth candidate: keep ordinary repairs available.
    # This filtering never catches or waives a broken canonical purchase proof.
    if (
        old.intrinsic is not None
        or old.battery_asset is not None
        or old.id in blocked(before, actor)
    ):
        return None
    return FrameAssetLoss(
        source_kind="asset_installment",
        id=receipt.id,
        actor=actor,
        frame=receipt.frame_instance,
        event=receipt.source_event,
        asset=old,
    )


def _response(
    game: GameService,
    c: Connection,
    action: str,
    choice: str,
    event: str,
    kind: str,
    human: int,
) -> ChoiceAnswer:
    requests, answers = t.m2["m2_choices"], t.m2["m2_responses"]
    row = (
        c.execute(
            sa.select(requests).where(
                requests.c.campaign_id == game.store.campaign_id,
                requests.c.id == choice,
            )
        )
        .mappings()
        .first()
    )
    response = (
        c.execute(
            sa.select(answers).where(
                answers.c.campaign_id == game.store.campaign_id,
                answers.c.choice_id == choice,
            )
        )
        .mappings()
        .first()
    )
    audit = (
        c.execute(
            sa.select(t.events).where(
                t.events.c.campaign_id == game.store.campaign_id,
                t.events.c.id == event,
            )
        )
        .mappings()
        .first()
    )
    payload = json.loads(audit["payload_json"]) if audit else {}
    if (
        row is None
        or response is None
        or audit is None
        or row["action_id"] != action
        or row["kind"] != kind
        or row["state"] != "answered"
        or row["actor_id"] != str(human)
        or response["actor_id"] != str(human)
        or response["event_id"] != event
        or audit["actor_id"] != str(human)
        or audit["kind"] not in ("m2.choice_resolved", "m3.choice_resolved")
        or payload.get("choice_id") != choice
        or payload.get("action_id") != action
    ):
        raise WorkflowError("Recover the actual original human's canonical Defeat decision")
    return ChoiceAnswer.model_validate_json(response["answer_json"])


def _preceding(
    game: GameService,
    c: Connection,
    action: str,
    kind: str,
    before_sequence: int,
) -> dict[str, Any]:
    requests, answers = t.m2["m2_choices"], t.m2["m2_responses"]
    row = (
        c.execute(
            sa.select(requests.c.id, answers.c.event_id, t.events.c.seq)
            .join(
                answers,
                sa.and_(
                    answers.c.campaign_id == requests.c.campaign_id,
                    answers.c.choice_id == requests.c.id,
                ),
            )
            .join(
                t.events,
                sa.and_(
                    t.events.c.campaign_id == answers.c.campaign_id,
                    t.events.c.id == answers.c.event_id,
                ),
            )
            .where(
                requests.c.campaign_id == game.store.campaign_id,
                requests.c.action_id == action,
                requests.c.kind == kind,
                t.events.c.seq < before_sequence,
            )
            .order_by(t.events.c.seq.desc())
            .limit(1)
        )
        .mappings()
        .first()
    )
    if row is None:
        raise WorkflowError("Recover the actual source-selected Defeat and Handler's offered loss")
    return dict(row)


def defeat_alternative_losses(
    game: GameService,
    c: Connection,
    state: GameState,
    actor: ActorRef,
) -> tuple[FrameAssetLoss, ...]:
    """Only genuinely accepted offers; other Defeat outcomes are separate sources."""
    from girlframe.engine.m3_battle import original_ended
    from girlframe.services.m3_consume import _raw_receipt

    result = []
    current_frame = consume.frame(state, actor)
    for fact in state.facts:
        if fact.get("kind") != "defeat_resolved" or fact.get("actor") != actor.model_dump_json():
            continue
        event, action_id = fact["source_event"], fact["action"]
        audit = (
            c.execute(
                sa.select(t.events).where(
                    t.events.c.campaign_id == game.store.campaign_id,
                    t.events.c.id == event,
                )
            )
            .mappings()
            .first()
        )
        payload = json.loads(audit["payload_json"]) if audit else {}
        choice = (
            c.execute(
                sa.select(t.m2["m2_choices"]).where(
                    t.m2["m2_choices"].c.campaign_id == game.store.campaign_id,
                    t.m2["m2_choices"].c.id == payload.get("choice_id"),
                )
            )
            .mappings()
            .first()
        )
        if (
            audit is None
            or audit["kind"] not in ("m2.choice_resolved", "m3.choice_resolved")
            or payload.get("action_id") != action_id
            or choice is None
        ):
            raise WorkflowError("Recover the actual canonical original Defeat resolution")
        if choice["kind"] != "defeat_accept_alternative":
            continue  # A real ordinary/new-Void Defeat result is a different producer.
        before, born = snapshots(game, c, event)
        if fact not in born.facts:
            raise WorkflowError("Keep the actual immutable Defeat resolution event")
        if (
            original_ended(born, actor)
            or born.sheets[actor.entity].frame_scrapped
            or consume.frame(before, actor) != current_frame
            or consume.frame(born, actor) != current_frame
        ):
            continue  # Valid but obsolete/whole-Frame outcomes are not current missing hardware.
        actual = game.action(c, action_id)
        binding = actual["data"].get("character_ids")
        if binding is None:
            binding = game.legacy_action_bindings(c, actual)
        if (
            audit is None
            or actual["data"].get("play") != "defeat"
            or actual["actor_id"] != actor.entity
            or binding.get(actor.entity) != actor.incarnation
            or actual["data"].get("defeat", {}).get("actor") != actor.model_dump(mode="json")
            or payload.get("action_id") != action_id
        ):
            raise WorkflowError("Prove the real original Defeat actor and source Action")
        _raw_receipt(game, c, actual)
        accepted = _response(
            game, c, action_id, choice["id"], event, "defeat_accept_alternative", int(actor.entity)
        )
        if accepted.flag is not True:
            raise WorkflowError(
                "Only the original Girl's actual acceptance removes offered hardware"
            )
        offer_event = _preceding(game, c, action_id, "defeat_alternative", audit["seq"])
        _, after_offer = snapshots(game, c, offer_event["event_id"])
        handler = after_offer.handler
        if handler is None:
            raise WorkflowError("Recover the actual original offering Handler")
        offered = _response(
            game,
            c,
            action_id,
            offer_event["id"],
            offer_event["event_id"],
            "defeat_alternative",
            handler,
        )
        offer = Alternative.model_validate_json(json.dumps(actual["data"].get("defeat_offer")))
        selected = Decision.model_validate_json(json.dumps(actual["data"].get("defeat_selected")))
        selected_event = _preceding(game, c, action_id, "defeat_select", offer_event["seq"])
        selection = _response(
            game,
            c,
            action_id,
            selected_event["id"],
            selected_event["event_id"],
            "defeat_select",
            int(actor.entity),
        )
        if (
            "handler_ruinous_alternative" not in selected.options
            or selection.options != selected.options
            or selection.text != selected.account
            or offered.flag is not True
            or offered.text != offer.account
            or tuple(filter(None, offered.fields.get("assets", "").split(",")))
            != offer.assets_removed
            or tuple(filter(None, offered.fields.get("identities", "").split(",")))
            != offer.identities_removed
            or (offered.number or 0) != offer.permissions_lost
            or offered.fields.get("tag", "") != offer.tag
            or (offered.fields.get("helpless_foe") or None)
            != (offer.helpless_foe.token if offer.helpless_foe else None)
            or offer.outside_frame
            != {"inside": False, "outside": True}.get(
                offered.fields.get("frame_context", "unspecified")
            )
        ):
            raise WorkflowError("Preserve the actual selected and accepted Handler offer unchanged")
        for identity in offer.assets_removed:
            old = next((x for x in before.sheets[actor.entity].assets if x.id == identity), None)
            if old is None or any(x.id == identity for x in born.sheets[actor.entity].assets):
                raise WorkflowError(
                    "The actual accepted offer must remove its named original component"
                )
            if (
                old.family != "frame"
                or old.intrinsic is not None
                or old.battery_asset is not None
                or old.id in blocked(before, actor)
            ):
                continue
            result.append(
                FrameAssetLoss(
                    source_kind="defeat_alternative",
                    id=consume.identity(
                        "defeat-alternative-loss", action_id, choice["id"], identity
                    ),
                    actor=actor,
                    frame=current_frame,
                    event=event,
                    asset=old,
                )
            )
    return tuple(result)
