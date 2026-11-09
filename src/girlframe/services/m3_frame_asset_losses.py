"""Explicit source producers share one immutable Frame-loss selection shape."""

import json
from typing import TYPE_CHECKING, Any, Literal

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

if TYPE_CHECKING:
    from girlframe.engine.m3_modular import Replacement as ModularReplacement


class FrameAssetLoss(Model):
    source_kind: Literal[
        "budget",
        "asset_installment",
        "defeat_alternative",
        "defeat_new_void",
        "partake_excrete",
        "partake_regrowth",
        "supply_drop_cap",
        "sup_dive_cap",
        "modular_recovery",
        "sup_risk_cap",
        "modular_quote",
        "modular_doctor",
        "modular_supply",
    ]
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


def _surviving_frame(state: GameState, before: GameState, born: GameState, actor: ActorRef) -> bool:
    from girlframe.engine.m3_battle import original_ended

    return all(
        actor.kind == "pilot"
        and actor.entity in source.sheets
        and source.sheets[actor.entity].character_id == actor.incarnation
        and not source.sheets[actor.entity].frame_scrapped
        and not original_ended(source, actor)
        and consume.frame(source, actor) == consume.frame(state, actor)
        for source in (before, born, state)
    )


def _eligible(before: GameState, actor: ActorRef, old: AssetState) -> bool:
    return (
        old.family == "frame"
        and old.intrinsic is None
        and old.battery_asset is None
        and old.id not in blocked(before, actor)
    )


def defeat_void_losses(
    game: GameService, c: Connection, state: GameState, actor: ActorRef
) -> tuple[FrameAssetLoss, ...]:
    """An actual selected new-Void installation, never an inferred old inventory."""
    from girlframe.engine import m3_defeat as defeat
    from girlframe.services.m3_actors import profiles
    from girlframe.services.m3_consume import _raw_receipt
    from girlframe.services.m3_defeat import decision

    result = []
    for fact in state.facts:
        if fact.get("kind") != "defeat_resolved" or fact.get("actor") != actor.model_dump_json():
            continue
        event, action_id = fact["source_event"], fact["action"]
        audit = (
            c.execute(
                sa.select(t.events).where(
                    t.events.c.campaign_id == game.store.campaign_id, t.events.c.id == event
                )
            )
            .mappings()
            .first()
        )
        payload = json.loads(audit["payload_json"]) if audit else {}
        row = (
            c.execute(
                sa.select(t.m2["m2_choices"]).where(
                    t.m2["m2_choices"].c.campaign_id == game.store.campaign_id,
                    t.m2["m2_choices"].c.id == payload.get("choice_id"),
                )
            )
            .mappings()
            .first()
        )
        if audit is None or row is None or payload.get("action_id") != action_id:
            raise WorkflowError("Recover the original canonical Defeat choice")
        if row["kind"] != "defeat_select":
            continue
        before, born = snapshots(game, c, event)
        if fact not in born.facts:
            raise WorkflowError("Recover the immutable selected Defeat source")
        if not _surviving_frame(state, before, born, actor):
            continue
        action = game.action(c, action_id)
        binding = action["data"].get("character_ids") or game.legacy_action_bindings(c, action)
        if (
            action["data"].get("play") != "defeat"
            or action["actor_id"] != actor.entity
            or binding.get(actor.entity) != actor.incarnation
            or action["data"].get("defeat", {}).get("actor") != actor.model_dump(mode="json")
        ):
            raise WorkflowError("Prove the original Girl's actual Defeat Action")
        _, roll_event = _raw_receipt(game, c, action)
        from girlframe.services.m3_dose_up import _roll_source

        proven_roll, total = _roll_source(game, c, action)
        if proven_roll != roll_event or action["data"]["defeat"]["roll_event"] != roll_event:
            raise WorkflowError("Preserve the original actual Defeat roll event")
        answer = _response(game, c, action_id, row["id"], event, "defeat_select", int(actor.entity))
        if "new_girl_and_frame_void_assets_heat4" not in answer.options:
            continue  # Another genuine Defeat branch supplies no cap-loss candidate here.
        selected = Decision.model_validate_json(json.dumps(action["data"].get("defeat_selected")))
        if decision(game, c, before, answer) != selected:
            raise WorkflowError("Preserve the exact original human's Defeat selection")
        # The genuine reducer checks tier, cap, Void, both births, and the selected replacement.
        outcome = defeat.apply(
            before,
            actor,
            profiles(c, game.store.campaign_id),
            total,
            selected,
            action_id,
            event,
            prior_event=action["data"]["defeat"]["roll_event"],
        )
        if (
            outcome.state.sheets[actor.entity].assets != born.sheets[actor.entity].assets
            or born.sheets[actor.entity].heat != 4
        ):
            raise WorkflowError("Prove the actual new-Void Defeat Asset births and Heat")
        assert selected.frame_asset is not None
        identity = selected.frame_asset.replace
        if identity is None:
            continue
        old = next((x for x in before.sheets[actor.entity].assets if x.id == identity), None)
        if old is None or any(x.id == identity for x in born.sheets[actor.entity].assets):
            raise WorkflowError("The actual chosen cap exchange must remove its named component")
        if _eligible(before, actor, old):
            result.append(
                FrameAssetLoss(
                    source_kind="defeat_new_void",
                    id=consume.identity("defeat-void-loss", action_id, row["id"], identity),
                    actor=actor,
                    frame=consume.frame(state, actor),
                    event=event,
                    asset=old,
                )
            )
    return tuple(result)


def partake_losses(
    game: GameService, c: Connection, state: GameState, actor: ActorRef
) -> tuple[FrameAssetLoss, ...]:
    """Each real Partake cap exchange has its own strictly earlier source proof."""
    from girlframe.engine.m3_assets import can_replace_at_limit, counts_toward_limit, frame_capacity
    from girlframe.services.m3_consume_regrowth import _dive, prove_regrowth

    result = []
    for source in consume.records(state, consume.Partaking):
        if source.actor != actor or source.option not in ("excrete", "regrow"):
            continue
        before, born = snapshots(game, c, source.event)
        if source not in consume.records(born, consume.Partaking) or source.id != source.event:
            raise WorkflowError("Recover the immutable actual Partaking source")
        if not _surviving_frame(state, before, born, actor):
            continue
        action = game.action(c, source.action)
        opportunity, choice, _ = _dive(game, c, before, actor, action, historical=True)
        answer = _response(
            game, c, source.action, choice, source.event, "consume_partake", int(actor.entity)
        )
        actual_opportunity = next(
            (x for x in consume.records(born, consume.Opportunity) if x.id == opportunity.id), None
        )
        if (
            answer.options != (source.option,)
            or answer.fields.get("girl_asset") != source.girl_asset
            or tuple(json.loads(answer.fields.get("frame_assets", "[]"))) != source.frame_assets
            or (answer.fields.get("replace_frame") or None) != source.replaced_frame
            or json.loads(answer.fields.get("regrow_replacements", "{}"))
            != source.regrow_replacements
            or actual_opportunity is None
            or actual_opportunity.completed_event != source.event
        ):
            raise WorkflowError("Prove the original resolved Partake choice and exact resources")
        if source.option == "regrow":
            for component in consume.records(born, consume.RegrownFrame):
                if (
                    component.event != source.event
                    or component.actor != actor
                    or not component.replacement
                ):
                    continue
                # prove_regrowth reconstructs BEFORE source.event. It cannot see this new loss,
                # so a cap exchange can never authorize its own preceding component birth.
                prove_regrowth(game, c, born, component.id)
                old = next(
                    (
                        x
                        for x in before.sheets[actor.entity].assets
                        if x.id == component.replacement
                    ),
                    None,
                )
                if old is None or any(x.id == old.id for x in born.sheets[actor.entity].assets):
                    raise WorkflowError(
                        "Regrowth must really remove the selected original cap component"
                    )
                if _eligible(before, actor, old):
                    result.append(
                        FrameAssetLoss(
                            source_kind="partake_regrowth",
                            id=consume.identity("partake-regrowth-loss", component.id, old.id),
                            actor=actor,
                            frame=component.frame,
                            event=source.event,
                            asset=old,
                        )
                    )
            continue
        # Excretion has its own real Girl consumption and exact source-authored new Void Asset.
        old_girl = next(
            (x for x in before.sheets[actor.entity].assets if x.id == source.girl_asset), None
        )
        if (
            old_girl is None
            or old_girl.family != "girl"
            or any(x.id == source.girl_asset for x in born.sheets[actor.entity].assets)
        ):
            raise WorkflowError("The actual selected Girl Asset must really be consumed")
        from girlframe.engine.m3_frame_state import SuppliedAsset

        supplied = SuppliedAsset.model_validate_json(answer.fields.get("new_asset", "null"))
        new = AssetState(
            id=consume.identity("excreted", source.action, source.event),
            family="frame",
            name=supplied.name,
            description=supplied.description,
            void=True,
        )
        old = next(
            (x for x in before.sheets[actor.entity].assets if x.id == source.replaced_frame), None
        )
        full = sum(
            counts_toward_limit(before.sheets[actor.entity], x)
            for x in before.sheets[actor.entity].assets
            if x.family == "frame"
        ) >= frame_capacity(before.sheets[actor.entity], before)
        if (
            supplied.damaged
            or not supplied.void
            or new not in born.sheets[actor.entity].assets
            or bool(source.replaced_frame) != full
            or old is not None
            and (
                not can_replace_at_limit(before.sheets[actor.entity], old)
                or old.id in blocked(before, actor)
            )
            or [
                x
                for x in before.sheets[actor.entity].assets
                if x.id not in {source.girl_asset, source.replaced_frame}
            ]
            + [new]
            != born.sheets[actor.entity].assets
        ):
            raise WorkflowError("Prove the actual legal excreted component and cap exchange")
        if source.replaced_frame and old is None:
            raise WorkflowError("Recover the actual excreted cap replacement")
        if old is not None and _eligible(before, actor, old):
            result.append(
                FrameAssetLoss(
                    source_kind="partake_excrete",
                    id=consume.identity("partake-excrete-loss", source.id, old.id),
                    actor=actor,
                    frame=consume.frame(state, actor),
                    event=source.event,
                    asset=old,
                )
            )
    return tuple(result)


def supply_drop_losses(
    game: GameService, c: Connection, state: GameState, actor: ActorRef
) -> tuple[FrameAssetLoss, ...]:
    """Delivery may permanently displace hardware; temporary equipment expiry is not regrowth."""
    from girlframe.engine import m3_supply_drop as supply
    from girlframe.services.m3_supply_drop import use_source

    result = []
    for use in supply.uses(state):
        if (
            use.target != actor
            or use.frame != consume.frame(state, actor)
            or use.kind != "drop"
            or not use.replacement
            or not use.effect_event
            or use.phase not in ("delivered", "expired")
        ):
            continue
        before, born = snapshots(game, c, use.effect_event)
        delivered = use_source(game, c, born, use.id)
        use_source(game, c, state, use.id)
        if not _surviving_frame(state, before, born, actor):
            continue
        prior = next((x for x in supply.uses(before) if x.id == use.id), None)
        audit = (
            c.execute(
                sa.select(t.events).where(
                    t.events.c.campaign_id == game.store.campaign_id,
                    t.events.c.id == use.effect_event,
                )
            )
            .mappings()
            .first()
        )
        old = next((x for x in before.sheets[actor.entity].assets if x.id == use.replacement), None)
        new = AssetState(id=use.asset, family="frame", name=use.name, description=use.description)
        if (
            prior is None
            or prior.phase != "proposed"
            or prior.effect_event is not None
            or delivered.phase != "delivered"
            or delivered.effect_event != use.effect_event
            or delivered.replacement != use.replacement
            or delivered.frame != consume.frame(state, actor)
            or not delivered.effect_account
            or old is None
            or old.family != "frame"
            or any(x.id == old.id for x in born.sheets[actor.entity].assets)
            or new not in born.sheets[actor.entity].assets
            or audit is None
            or audit["kind"] != "m3.supply_drop_delivered"
            or audit["actor_id"] != actor.entity
            or json.loads(audit["payload_json"]).get("use_id") != use.id
        ):
            raise WorkflowError(
                "Prove the actual accepted temporary delivery and permanent cap loss"
            )
        try:
            expected = install(
                before.sheets[actor.entity],
                new,
                replace=old.id,
                effective_void=stored_ids(before, actor),
                state=before,
            )
        except ValueError as error:
            raise WorkflowError(
                "Recover the real legal Supply Drop cap exchange: " + str(error)
            ) from None
        if expected.sheet.assets != born.sheets[actor.entity].assets:
            raise WorkflowError("Preserve this actual Supply Drop component exchange")
        if _eligible(before, actor, old):
            result.append(
                FrameAssetLoss(
                    source_kind="supply_drop_cap",
                    id=use.id,
                    actor=actor,
                    frame=use.frame,
                    event=use.effect_event,
                    asset=old,
                )
            )
    return tuple(result)


def sup_dive_losses(
    game: GameService, c: Connection, state: GameState, actor: ActorRef
) -> tuple[FrameAssetLoss, ...]:
    """Only a genuine paid Sup at an actual Dive Void choice, never every Grown fact."""
    from girlframe.engine import m3_sup as sup
    from girlframe.engine.m3_dive_state import Effect
    from girlframe.services.m3_dose_up import _roll_source
    from girlframe.services.m3_sup import prove_growth

    result = []
    actions, choices = t.m2["m2_actions"], t.m2["m2_choices"]
    for grown in sup.growths(state):
        if grown.actor != actor or grown.choice.family != "frame" or not grown.choice.replace:
            continue
        if (
            c.scalar(
                sa.select(actions.c.id).where(
                    actions.c.campaign_id == game.store.campaign_id, actions.c.id == grown.action
                )
            )
            is None
        ):
            continue  # Other genuine work-owned Sup sources need their own positive adapter.
        action = game.action(c, grown.action)
        if action["data"].get("play") != "dive_deep":
            continue
        before, born = snapshots(game, c, grown.event)
        if grown not in sup.growths(born):
            raise WorkflowError("Recover the exact original canonical Sup growth")
        if not _surviving_frame(state, before, born, actor):
            continue
        _roll_source(game, c, action)
        bound = action["data"].get("character_ids") or game.legacy_action_bindings(c, action)
        if (
            action["actor_id"] != actor.entity
            or bound.get(actor.entity) != actor.incarnation
            or grown.frame != consume.frame(state, actor)
            or prove_growth(game, c, born, actor, grown.event) != grown
        ):
            raise WorkflowError("Keep the original paid Sup, Dive actor and surviving Frame")
        response = (
            c.execute(
                sa.select(choices)
                .join(
                    t.m2["m2_responses"],
                    sa.and_(
                        choices.c.campaign_id == t.m2["m2_responses"].c.campaign_id,
                        choices.c.id == t.m2["m2_responses"].c.choice_id,
                    ),
                )
                .where(
                    choices.c.campaign_id == game.store.campaign_id,
                    choices.c.action_id == grown.action,
                    choices.c.kind == "dive_effect",
                    t.m2["m2_responses"].c.event_id == grown.event,
                )
            )
            .mappings()
            .one_or_none()
        )
        if response is None or json.loads(response["body_json"]).get("step") != grown.step:
            raise WorkflowError("Prove this real original Dive effect choice")
        answer = _response(
            game, c, grown.action, response["id"], grown.event, "dive_effect", int(actor.entity)
        )
        fact = next(
            (
                x
                for x in born.facts
                if x.get("kind") == "dive_effect"
                and x.get("action") == grown.action
                and x.get("step") == str(grown.step)
                and x.get("source_event") == grown.event
            ),
            None,
        )
        effect = Effect.model_validate_json(fact["effect"]) if fact else None
        if (
            fact is None
            or fact["option"] != "void_and_unmark_all"
            or fact["actor"] != actor.model_dump_json()
            or effect is None
            or effect.growth != grown.choice
            or effect.asset is not None
            or effect.description != grown.description
            or answer.text != grown.description
            or answer.fields
            != dict(
                sup_name=grown.choice.name, sup_family="frame", sup_replace=grown.choice.replace
            )
        ):
            raise WorkflowError("Prove the actual owned Void gain and exact Sup choice")
        old = next(
            (x for x in before.sheets[actor.entity].assets if x.id == grown.choice.replace), None
        )
        new = next((x for x in born.sheets[actor.entity].assets if x.id == grown.asset), None)
        if (
            old is None
            or new is None
            or any(x.id == old.id for x in born.sheets[actor.entity].assets)
        ):
            raise WorkflowError(
                "The actual Sup cap exchange must remove the named original hardware"
            )
        try:
            expected, _, exact_growth = sup.grow(
                before,
                actor,
                grown.choice,
                grown.description,
                grown.action,
                grown.event,
                piloting=bool(action["data"]["prepared"]["piloting"]),
                step=grown.step,
            )
        except ValueError as error:
            raise WorkflowError(
                "Recover the actual legal Sup cap exchange: " + str(error)
            ) from None
        if (
            exact_growth != grown
            or expected.sheets[actor.entity].assets != born.sheets[actor.entity].assets
        ):
            raise WorkflowError("Preserve this exact original Sup component exchange")
        if _eligible(before, actor, old):
            result.append(
                FrameAssetLoss(
                    source_kind="sup_dive_cap",
                    id=grown.asset,
                    actor=actor,
                    frame=grown.frame,
                    event=grown.event,
                    asset=old,
                )
            )
    return tuple(result)


def modular_recovery_losses(
    game: GameService, c: Connection, state: GameState, actor: ActorRef
) -> tuple[FrameAssetLoss, ...]:
    """Only actual owner-authored Off-Duty Modular recovery, not every repair fact."""
    from girlframe.engine import m3_modular as modular
    from girlframe.engine.m3_off_duty import Period
    from girlframe.services.m3_dose_up import _roll_source
    from girlframe.services.m3_modular import entitlement

    history = t.m3["m3_off_duty_history"]
    candidates = [
        x
        for x in state.facts
        if x.get("kind") == "modular_repair"
        and x.get("actor") == actor.model_dump_json()
        and x.get("period")
        and not x.get("source")
    ]
    result = []
    for period in {x["period"] for x in candidates}:
        rows = c.execute(
            sa.select(history.c.body_json, history.c.revision, history.c.event_id, t.events)
            .join(
                t.events,
                sa.and_(
                    t.events.c.campaign_id == history.c.campaign_id,
                    t.events.c.id == history.c.event_id,
                ),
            )
            .where(
                history.c.campaign_id == game.store.campaign_id,
                history.c.id == period,
                t.events.c.kind == "m3.off_duty_recovered",
                t.events.c.actor_id == actor.entity,
            )
        ).mappings()
        for row in rows:
            event = row["event_id"]
            before, born = snapshots(game, c, event)
            if not _surviving_frame(state, before, born, actor):
                continue
            facts = [
                x
                for x in born.facts
                if x.get("kind") == "modular_repair"
                and x.get("period") == period
                and x.get("actor") == actor.model_dump_json()
                and not x.get("source")
                and x not in before.facts
            ]
            if not facts:
                continue
            if any(x not in candidates for x in facts):
                raise WorkflowError("Preserve the original canonical Modular recovery selections")
            previous = c.scalar(
                sa.select(history.c.body_json).where(
                    history.c.campaign_id == game.store.campaign_id,
                    history.c.id == period,
                    history.c.revision == row["revision"] - 1,
                )
            )
            recovered = Period.model_validate_json(row["body_json"])
            earlier = Period.model_validate_json(previous) if previous else None
            progress = recovered.progress.get(actor.entity)
            old_progress = earlier.progress.get(actor.entity) if earlier else None
            receipt = entitlement(game, c, born, actor)
            if (
                earlier is None
                or earlier.phase != "active"
                or recovered.phase != "active"
                or recovered.character_ids.get(actor.entity) != actor.incarnation
                or earlier.character_ids != recovered.character_ids
                or progress is None
                or old_progress is None
                or old_progress.recovered
                or not progress.recovered
                or progress.roll is None
                or progress.roll != old_progress.roll
                or progress.action_id is None
                or progress.action_id != old_progress.action_id
                or json.loads(row["payload_json"]).get("period_id") != period
                or receipt is None
                or any(x.get("purchase") != receipt.id for x in facts)
                or len({x["old"] for x in facts}) != len(facts)
            ):
                raise WorkflowError("Recover the actual owned paid Modular Off-Duty recovery")
            action = game.action(c, progress.action_id)
            _roll_source(game, c, action)
            bound = action["data"].get("character_ids") or game.legacy_action_bindings(c, action)
            if (
                action["actor_id"] != actor.entity
                or bound.get(actor.entity) != actor.incarnation
                or action["data"].get("play") != "go_off_duty"
                or action["data"].get("prepared", {}).get("off_duty_id") != period
            ):
                raise WorkflowError("Recover the exact original completed Off-Duty Play")
            intermediate = GameState.model_validate_json(born.model_dump_json())
            intermediate.facts = [x for x in intermediate.facts if x not in facts]
            replacements = []
            originals = []
            for fact in facts:
                old = next(
                    (x for x in before.sheets[actor.entity].assets if x.id == fact["old"]), None
                )
                new = next(
                    (x for x in born.sheets[actor.entity].assets if x.id == fact["new"]), None
                )
                if (
                    old is None
                    or not old.damaged
                    or new is None
                    or new.damaged
                    or old.id == new.id
                    or any(x.id == old.id for x in born.sheets[actor.entity].assets)
                    or any(x.id == new.id for x in before.sheets[actor.entity].assets)
                ):
                    raise WorkflowError(
                        "Recover the exact repaired old and newly authored hardware"
                    )
                intermediate.sheets[actor.entity].assets = [
                    old.model_copy(update={"damaged": False}) if x.id == new.id else x
                    for x in intermediate.sheets[actor.entity].assets
                ]
                replacements.append(
                    modular.Replacement(asset=old.id, name=new.name, description=new.description)
                )
                originals.append(old)
            try:
                modular.replace_repaired(
                    intermediate,
                    actor,
                    before.sheets[actor.entity],
                    tuple(replacements),
                    period,
                )
            except ValueError as error:
                raise WorkflowError(
                    "Recover the actual legal Modular repair: " + str(error)
                ) from None
            if intermediate.sheets[actor.entity].assets != born.sheets[actor.entity].assets or any(
                fact not in intermediate.facts for fact in facts
            ):
                raise WorkflowError("Preserve the original pure Modular repair replacement")
            for old in originals:
                if _eligible(before, actor, old):
                    result.append(
                        FrameAssetLoss(
                            source_kind="modular_recovery",
                            id=consume.identity("modular-recovery", period, actor.token, old.id),
                            actor=actor,
                            frame=consume.frame(born, actor),
                            event=event,
                            asset=old,
                        )
                    )
    return tuple(result)


def sup_risk_losses(
    game: GameService, c: Connection, state: GameState, actor: ActorRef
) -> tuple[FrameAssetLoss, ...]:
    """A paid Sup exchange at an actual owned Risk Factor SQL response, never Grown alone."""
    from girlframe.engine import m3_mockingbird as risk
    from girlframe.engine import m3_sup as sup
    from girlframe.services.m3_actors import profiles
    from girlframe.services.m3_dose_up import _roll_source
    from girlframe.services.m3_sup import prove_growth

    result = []
    actions = t.m2["m2_actions"]
    for grown in sup.growths(state):
        if grown.actor != actor or grown.choice.family != "frame" or not grown.choice.replace:
            continue
        if (
            c.scalar(
                sa.select(actions.c.id).where(
                    actions.c.campaign_id == game.store.campaign_id, actions.c.id == grown.action
                )
            )
            is None
        ):
            continue
        action = game.action(c, grown.action)
        meta = action["data"].get("risk_factor")
        if not meta or (meta.get("payment") or {}).get("event") != grown.event:
            continue  # Other actual Sup source families need their own positive adapters.
        payment = risk.RiskPayment.model_validate(meta["payment"])
        if payment.learned_source is not None:
            continue
        before, born = snapshots(game, c, grown.event)
        if not _surviving_frame(state, before, born, actor):
            continue
        _roll_source(game, c, action)
        bound = action["data"].get("character_ids") or game.legacy_action_bindings(c, action)
        answer = _response(
            game,
            c,
            action["id"],
            meta["choice"],
            grown.event,
            "mockingbird_risk",
            int(actor.entity),
        )
        fact = dict(
            kind="mockingbird_risk_paid",
            action=action["id"],
            event=grown.event,
            actor=actor.model_dump_json(),
            body=payment.model_dump_json(),
        )
        if (
            grown not in sup.growths(born)
            or prove_growth(game, c, born, actor, grown.event) != grown
            or grown.frame != consume.frame(state, actor)
            or action["actor_id"] != actor.entity
            or bound.get(actor.entity) != actor.incarnation
            or meta.get("actor") != actor.model_dump(mode="json")
            or not risk.owns(before, actor, risk.RISK)
            or payment.actor != actor
            or payment.action != action["id"]
            or payment.asset != grown.asset
            or payment.family != "frame"
            or payment.total_before != meta["before"]
            or payment.total_after != answer.number
            or payment.account != grown.description
            or fact not in born.facts
            or fact in before.facts
            or answer.text != grown.description
            or answer.options
            or answer.denied
            or answer.member is not None
            or answer.flag is not None
            or answer.fields
            != dict(
                sup_name=grown.choice.name, sup_family="frame", sup_replace=grown.choice.replace
            )
        ):
            raise WorkflowError("Prove the original owned Risk payment and exact paid Sup choice")
        old = next(
            (x for x in before.sheets[actor.entity].assets if x.id == grown.choice.replace), None
        )
        if old is None or any(x.id == old.id for x in born.sheets[actor.entity].assets):
            raise WorkflowError(
                "The actual Risk Sup cap exchange must remove its original component"
            )
        try:
            expected, _, exact_payment = risk.risk(
                before,
                profiles(c, game.store.campaign_id),
                actor,
                action["id"],
                grown.event,
                "",
                grown.description,
                payment.total_before,
                payment.total_after,
                piloting=bool(action["data"].get("prepared", {}).get("piloting")),
                growth=grown.choice,
            )
        except ValueError as error:
            raise WorkflowError(
                "Recover the actual legal Risk Sup exchange: " + str(error)
            ) from None
        if (
            exact_payment != payment
            or grown not in sup.growths(expected)
            or expected.sheets[actor.entity].assets != born.sheets[actor.entity].assets
        ):
            raise WorkflowError("Preserve the original pure Risk Sup component exchange")
        if _eligible(before, actor, old):
            result.append(
                FrameAssetLoss(
                    source_kind="sup_risk_cap",
                    id=grown.asset,
                    actor=actor,
                    frame=grown.frame,
                    event=grown.event,
                    asset=old,
                )
            )
    return tuple(result)


def _repair_event(
    game: GameService, c: Connection, event: str, kind: str, human: int, key: str, source: str
) -> dict[str, Any]:
    row = (
        c.execute(
            sa.select(t.events).where(
                t.events.c.campaign_id == game.store.campaign_id, t.events.c.id == event
            )
        )
        .mappings()
        .first()
    )
    if (
        row is None
        or row["kind"] != kind
        or row["actor_id"] != str(human)
        or json.loads(row["payload_json"]).get(key) != source
    ):
        raise WorkflowError("Recover the exact original human's canonical repair source")
    return dict(row)


def _modular_repair_losses(
    game: GameService,
    c: Connection,
    before: GameState,
    born: GameState,
    repaired: GameState,
    actor: ActorRef,
    source: str,
    event: str,
    kind: Literal["modular_quote", "modular_doctor", "modular_supply"],
    selected: tuple["ModularReplacement", ...] | None = None,
) -> tuple[FrameAssetLoss, ...]:
    """Replay only after the caller proves its actual distinct repair producer."""
    from girlframe.engine.m3_modular import Replacement, replace_repaired
    from girlframe.services.m3_modular import entitlement

    facts = [
        x
        for x in born.facts
        if x.get("kind") == "modular_repair"
        and x.get("actor") == actor.model_dump_json()
        and x.get("source") == source
        and not x.get("period")
        and x not in before.facts
    ]
    if not facts:
        return ()
    receipt = entitlement(game, c, born, actor)
    if (
        receipt is None
        or any(x.get("purchase") != receipt.id for x in facts)
        or len({x["old"] for x in facts}) != len(facts)
    ):
        raise WorkflowError("Keep the actual original paid Modular repair entitlement")
    choices, originals = [], []
    for fact in facts:
        old = next((x for x in before.sheets[actor.entity].assets if x.id == fact["old"]), None)
        new = next((x for x in born.sheets[actor.entity].assets if x.id == fact["new"]), None)
        if (
            old is None
            or new is None
            or old.id == new.id
            or any(x.id == old.id for x in born.sheets[actor.entity].assets)
            or any(x.id == new.id for x in before.sheets[actor.entity].assets)
        ):
            raise WorkflowError("Recover the original replaced hardware and distinct new component")
        choices.append(Replacement(asset=old.id, name=new.name, description=new.description))
        originals.append(old)
    if selected is not None and tuple(choices) != selected:
        raise WorkflowError("Preserve the original patient's exact owned Modular repair selection")
    try:
        replace_repaired(
            repaired, actor, before.sheets[actor.entity], tuple(choices), None, source=source
        )
    except ValueError as error:
        raise WorkflowError("Recover the actual legal Modular repair: " + str(error)) from None
    if repaired.sheets[actor.entity].assets != born.sheets[actor.entity].assets or any(
        x not in repaired.facts for x in facts
    ):
        raise WorkflowError("Preserve the actual source repair and pure Modular replacement")
    return tuple(
        FrameAssetLoss(
            source_kind=kind,
            id=consume.identity(kind.replace("_", "-"), source, old.id),
            actor=actor,
            frame=consume.frame(born, actor),
            event=event,
            asset=old,
        )
        for old in originals
        if _eligible(before, actor, old)
    )


def modular_quote_losses(
    game: GameService, c: Connection, state: GameState, actor: ActorRef
) -> tuple[FrameAssetLoss, ...]:
    from girlframe.engine.m3_economy import RepairQuote, quoted_repair_in_state
    from girlframe.engine.m3_off_duty import Period
    from girlframe.engine.m3_repairs import active
    from girlframe.services.m3_handler_advancements import _history
    from girlframe.services.m3_intracadre_marriage import prove_flow

    result: list[FrameAssetLoss] = []
    history = t.m3["m3_off_duty_history"]
    for quote in state.repair_quotes:
        source = "repair_quote:" + quote.id
        if quote.owner != actor or quote.state != "accepted" or quote.response_event is None:
            continue
        if not any(
            x.get("kind") == "modular_repair" and x.get("source") == source for x in state.facts
        ):
            continue
        event = quote.response_event
        before, born = snapshots(game, c, event)
        if not _surviving_frame(state, before, born, actor):
            continue
        pending = next((x for x in before.repair_quotes if x.id == quote.id), None)
        original = next(
            (x for x in _history(c, game, quote.source_event).repair_quotes if x.id == quote.id),
            None,
        )
        audit = _repair_event(
            game, c, event, "m3.repair_quote_answered", int(actor.entity), "quote_id", quote.id
        )
        _repair_event(
            game,
            c,
            quote.source_event,
            "m3.repair_quote_offered",
            quote.handler,
            "quote_id",
            quote.id,
        )
        period_raw = c.scalar(
            sa.select(history.c.body_json)
            .join(
                t.events,
                sa.and_(
                    t.events.c.campaign_id == history.c.campaign_id,
                    t.events.c.id == history.c.event_id,
                ),
            )
            .where(
                history.c.campaign_id == game.store.campaign_id,
                history.c.id == quote.period,
                t.events.c.seq < audit["seq"],
            )
            .order_by(t.events.c.seq.desc())
            .limit(1)
        )
        period = Period.model_validate_json(period_raw) if period_raw else None
        if (
            pending is None
            or pending != original
            or pending.state != "pending"
            or quote
            != pending.model_copy(
                update=dict(state="accepted", revision=pending.revision + 1, response_event=event)
            )
            or quote not in born.repair_quotes
            or json.loads(audit["payload_json"]).get("accepted") is not True
            or before.handler != quote.handler
            or quote.frame_instance != consume.frame(before, actor)
            or active(before, quote.period) != quote.shortages
            or period is None
            or period.phase != "active"
            or period.handler != quote.handler
            or period.character_ids.get(actor.entity) != actor.incarnation
            or actor.entity not in period.progress
            or not period.progress[actor.entity].recovered
        ):
            raise WorkflowError("Recover the original accepted Handler quote and actual recovery")
        repaired = GameState.model_validate_json(before.model_dump_json())
        try:
            quoted_repair_in_state(
                repaired,
                actor,
                RepairQuote(
                    id=quote.id,
                    handler_id=quote.handler,
                    owner_id=int(actor.entity),
                    asset_id=quote.asset,
                    sheet_revision=quote.sheet_revision,
                    quote_revision=pending.revision,
                    cost=quote.cost,
                ),
                current_handler=quote.handler,
                expected_quote_revision=pending.revision,
                event=event,
                source=quote.id,
            )
        except ValueError as error:
            raise WorkflowError("Recover the actual paid quote: " + str(error)) from None
        prove_flow(game, c, before, born, actor, event, quote.id, quote.cost)
        if any(
            repaired.sheets[uid].permissions != sheet.permissions
            for uid, sheet in born.sheets.items()
        ):
            raise WorkflowError("Preserve the actual quoted price and Permission balances")
        result.extend(
            _modular_repair_losses(
                game, c, before, born, repaired, actor, source, event, "modular_quote"
            )
        )
    return tuple(result)


def modular_doctor_losses(
    game: GameService, c: Connection, state: GameState, actor: ActorRef
) -> tuple[FrameAssetLoss, ...]:
    from pydantic import TypeAdapter

    from girlframe.engine import m3_doctor as doctor
    from girlframe.engine.m3_modular import Replacement
    from girlframe.services.m3_doctor import owned
    from girlframe.services.m3_dose_up import _roll_source

    result: list[FrameAssetLoss] = []
    requests, responses = t.m2["m2_choices"], t.m2["m2_responses"]
    rows = c.execute(
        sa.select(requests, responses.c.event_id)
        .join(
            responses,
            sa.and_(
                responses.c.campaign_id == requests.c.campaign_id,
                responses.c.choice_id == requests.c.id,
            ),
        )
        .where(
            requests.c.campaign_id == game.store.campaign_id,
            requests.c.kind == "doctor_patient",
            requests.c.actor_id == actor.entity,
        )
    ).mappings()
    for row in rows:
        source = "doctor:" + row["action_id"] + ":" + row["id"]
        if not any(
            x.get("kind") == "modular_repair" and x.get("source") == source for x in state.facts
        ):
            continue
        event = row["event_id"]
        before, born = snapshots(game, c, event)
        if not _surviving_frame(state, before, born, actor):
            continue
        action = game.action(c, row["action_id"])
        meta = action["data"].get("doctor")
        if meta is None or action["data"].get("play") != "nanobot_injection":
            raise WorkflowError("Prove the actual original Nanobot repair Action")
        _roll_source(game, c, action)
        doctor_actor = ActorRef.model_validate(meta["actor"])
        bound = action["data"].get("character_ids") or game.legacy_action_bindings(c, action)
        audit = c.execute(
            sa.select(t.events.c.seq).where(
                t.events.c.campaign_id == game.store.campaign_id, t.events.c.id == event
            )
        ).scalar_one()
        benefits = _preceding(game, c, action["id"], "doctor_nanobot_benefits", audit)
        granted = _response(
            game,
            c,
            action["id"],
            benefits["id"],
            benefits["event_id"],
            "doctor_nanobot_benefits",
            meta["actor_controller"],
        )
        selected = _response(
            game, c, action["id"], row["id"], event, "doctor_patient", int(actor.entity)
        )
        body = json.loads(row["body_json"])
        if (
            meta["target"] != actor.model_dump(mode="json")
            or meta["target_controller"] != int(actor.entity)
            or bound.get(actor.entity) != actor.incarnation
            or bound.get(doctor_actor.entity) != doctor_actor.incarnation
            or action["actor_id"] != doctor_actor.entity
            or not owned(game, c, before, doctor_actor, doctor.NANO)
            or doctor.frame_id(before, doctor_actor) != meta["frame"]
            or "repair" not in granted.options
            or body.get("repair") != 2
            or "modular" not in selected.fields
            or set(selected.fields) - {"modular", "identity"}
        ):
            raise WorkflowError("Keep the actual Doctor benefit and patient's owned repair choices")
        choices = TypeAdapter(tuple[Replacement, ...]).validate_json(selected.fields["modular"])
        if not choices or not {x.asset for x in choices} <= set(selected.options):
            raise WorkflowError("Replace only the actual selected Nanobot repairs")
        repaired = GameState.model_validate_json(before.model_dump_json())
        try:
            doctor.repair(repaired, actor, selected.options, 2)
        except ValueError as error:
            raise WorkflowError("Recover the real patient repairs: " + str(error)) from None
        result.extend(
            _modular_repair_losses(
                game, c, before, born, repaired, actor, source, event, "modular_doctor", choices
            )
        )
    return tuple(result)


def modular_supply_losses(
    game: GameService, c: Connection, state: GameState, actor: ActorRef
) -> tuple[FrameAssetLoss, ...]:
    from girlframe.engine import m3_supply_drop as supply
    from girlframe.engine.m3_actors import resolve
    from girlframe.engine.m3_doctor import repair
    from girlframe.services.m3_actors import profiles
    from girlframe.services.m3_supply_drop import use_source

    result: list[FrameAssetLoss] = []
    for value in supply.uses(state):
        if (
            value.target != actor
            or value.kind != "repair"
            or value.phase != "repaired"
            or not value.effect_event
        ):
            continue
        source, event = value.id, value.effect_event
        if not any(
            x.get("kind") == "modular_repair" and x.get("source") == source for x in state.facts
        ):
            continue
        before, born = snapshots(game, c, event)
        if not _surviving_frame(state, before, born, actor):
            continue
        original = next((x for x in supply.uses(before) if x.id == value.id), None)
        _repair_event(
            game, c, event, "m3.supply_drop_repaired", int(actor.entity), "use_id", value.id
        )
        actual = resolve(
            before, actor, profiles(c, game.store.campaign_id), require_current_profile=False
        )
        if (
            use_source(game, c, born, value.id) != value
            or original is None
            or original.phase != "proposed"
            or original.effect_event is not None
            or value.frame != consume.frame(before, actor)
            or original.position != actual.source_sha256
            or not value.effect_account
            or not value.effect_account.strip()
        ):
            raise WorkflowError("Recover the actual paid Supply repair and recipient acceptance")
        repaired = GameState.model_validate_json(before.model_dump_json())
        try:
            repair(repaired, actor, (value.asset,), 1)
        except ValueError as error:
            raise WorkflowError("Recover the real Supply repair: " + str(error)) from None
        result.extend(
            _modular_repair_losses(
                game, c, before, born, repaired, actor, source, event, "modular_supply"
            )
        )
    return tuple(result)
