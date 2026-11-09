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
    source_kind: Literal[
        "budget",
        "asset_installment",
        "defeat_alternative",
        "defeat_new_void",
        "partake_excrete",
        "partake_regrowth",
        "supply_drop_cap",
        "sup_dive_cap",
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
