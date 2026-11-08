"""Finite Partake regrowth from explicit Budget and paid same-Frame cap-loss sources."""

import json
from typing import Any, Literal

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_budget_removal as budget
from girlframe.engine import m3_consume as rules
from girlframe.engine.m2 import AssetState, GameState
from girlframe.engine.m3_actor_state import ActorRef, Model
from girlframe.engine.m3_core import install
from girlframe.engine.m3_janus_storage import effective_assets
from girlframe.engine.m3_requisition_state import Receipt
from girlframe.services.m2_game import GameService
from girlframe.services.m3_budget_removal import prove_loss_source
from girlframe.services.m3_frame_asset_losses import (
    FrameAssetLoss,
    defeat_alternative_losses,
    defeat_void_losses,
    installment_loss,
    partake_losses,
)
from girlframe.services.m3_handler_advancements import _history
from girlframe.services.onboarding import WorkflowError


class Selection(Model):
    token: str
    kind: Literal["repair", "missing"]
    original: AssetState
    loss: str | None = None
    loss_event: str | None = None
    loss_kind: (
        Literal[
            "asset_installment",
            "defeat_alternative",
            "defeat_new_void",
            "partake_excrete",
            "partake_regrowth",
        ]
        | None
    ) = None
    replacement: str | None = None


class RegrowthPlan(Model):
    actor: ActorRef
    frame: str
    action: str
    opportunity: str
    choice: str
    receipt: str
    frame_assets: tuple[AssetState, ...]
    selected: tuple[Selection, ...]


def _dive(
    game: GameService,
    c: Connection,
    state: GameState,
    actor: ActorRef,
    action: dict[str, Any],
    *,
    historical: bool = False,
) -> tuple[rules.Opportunity, str, str]:
    source = next(
        (
            value
            for value in rules.records(state, rules.Opportunity)
            if value.action == action["id"] and value.kind == "partake"
        ),
        None,
    )
    if (
        source is None
        or source.actor != actor
        or source.completed_event is not None
        and not historical
        or action["data"].get("play") != "dive_deep"
        or action["actor_id"] != actor.entity
    ):
        raise WorkflowError("Regrowth requires the actual original unresolved Dive Partake source")
    receipt = c.scalar(
        sa.select(t.m2["m2_receipts"].c.body_json).where(
            t.m2["m2_receipts"].c.campaign_id == game.store.campaign_id,
            t.m2["m2_receipts"].c.action_id == action["id"],
        )
    )
    if receipt is None or json.loads(receipt) != action["data"].get("receipt"):
        raise WorkflowError("Recover the genuine original committed Dive receipt")
    bindings = action["data"].get("character_ids")
    if bindings is None:
        bindings = game.legacy_action_bindings(c, action)
    if bindings.get(actor.entity) != actor.incarnation:
        raise WorkflowError("Preserve the actual original Dive actor; never a replacement account")
    if not historical:
        game.action_characters(c, action, state)
    birth = _history(c, game, source.event)
    original = next(
        (value for value in rules.records(birth, rules.Opportunity) if value.id == source.id), None
    )
    if (
        original is None
        or original.action != source.action
        or original.actor != actor
        or original.kind != "partake"
        or rules.frame(birth, actor) != rules.frame(state, actor)
    ):
        raise WorkflowError("Keep the actual original Dive and current physical Frame")
    choices = list(
        c.execute(
            sa.select(t.m2["m2_choices"]).where(
                t.m2["m2_choices"].c.campaign_id == game.store.campaign_id,
                t.m2["m2_choices"].c.action_id == action["id"],
                t.m2["m2_choices"].c.kind == "consume_partake",
                t.m2["m2_choices"].c.actor_id == actor.entity,
            )
        ).mappings()
    )
    if len(choices) != 1:
        raise WorkflowError("Recover the exact original owner's Partake choice")
    return source, choices[0]["id"], json.loads(receipt)["id"]


def _loss(game: GameService, c: Connection, state: GameState, value: budget.Loss) -> budget.Loss:
    born = _history(c, game, value.event)
    original = next((loss for loss in budget.losses(born) if loss.id == value.id), None)
    if original is None or any(
        getattr(original, name) != getattr(value, name)
        for name in ("actor", "frame", "context", "event", "frame_asset")
    ):
        raise WorkflowError("Preserve the immutable actual original Frame-Asset loss")
    prove_loss_source(game, c, born, value.event, value.id, value.actor)
    asset = original.frame_asset
    if asset.family != "frame" or asset.intrinsic is not None or asset.battery_asset is not None:
        raise WorkflowError(
            "SOURCE_REGROWTH_LIFECYCLE_REQUIRED: use ordinary permanent Frame hardware"
        )
    return original


def _namespace(base: str, kind: str | None) -> str:
    # Preserve the published three providers' exact old IDs and namespaces.
    if kind is None:
        return base
    if kind == "asset_installment":
        return base + "-installment"
    if kind == "defeat_alternative":
        return base + "-defeat"
    return base + "-" + kind.replace("_", "-")


def _selections(
    game: GameService, c: Connection, state: GameState, actor: ActorRef
) -> tuple[Selection, ...]:
    frame = rules.frame(state, actor)
    sheet = state.sheets[actor.entity]
    present = {asset.id for asset in sheet.assets}
    result = [
        Selection(token=asset.id, kind="repair", original=asset)
        for asset in sheet.assets
        if asset.family == "frame" and asset.damaged
    ]
    consumed = {
        (value.loss_kind or "budget", value.loss)
        for value in rules.records(state, rules.RegrownFrame)
    }
    losses = []
    for value in budget.losses(state):
        if (
            value.actor != actor
            or value.frame != frame
            or ("budget", value.id) in consumed
            or value.frame_asset.id in present
        ):
            continue
        original = _loss(game, c, state, value)
        losses.append(
            FrameAssetLoss(
                source_kind="budget",
                id=original.id,
                actor=original.actor,
                frame=original.frame,
                event=original.event,
                asset=original.frame_asset,
            )
        )
    for receipt in state.requisitions:
        if (
            isinstance(receipt, Receipt)
            and receipt.actor == actor
            and receipt.frame_instance == frame
            and receipt.installation.replace is not None
            and receipt.installation.replace not in present
            and ("asset_installment", receipt.id) not in consumed
        ):
            paid_loss = installment_loss(game, c, state, receipt)
            if paid_loss is not None:
                losses.append(paid_loss)
    for provider in (defeat_alternative_losses, defeat_void_losses, partake_losses):
        losses.extend(
            value
            for value in provider(game, c, state, actor)
            if value.asset.id not in present and (value.source_kind, value.id) not in consumed
        )
    for loss in losses:
        kind: (
            Literal[
                "asset_installment",
                "defeat_alternative",
                "defeat_new_void",
                "partake_excrete",
                "partake_regrowth",
            ]
            | None
        ) = loss.source_kind if loss.source_kind != "budget" else None
        result.append(
            Selection(
                token=rules.identity(
                    _namespace("missing-frame", kind),
                    loss.id,
                ),
                kind="missing",
                original=loss.asset,
                loss=loss.id,
                loss_event=loss.event,
                loss_kind=kind,
            )
        )
    return tuple(result)


def regrowth_options(
    game: GameService,
    c: Connection,
    state: GameState,
    actor: ActorRef,
    action: dict[str, Any],
) -> tuple[dict[str, str], ...]:
    _dive(game, c, state, actor, action)
    return tuple(
        dict(
            id=value.token,
            kind=value.kind,
            label=value.original.name + (" (missing)" if value.kind == "missing" else " (damaged)"),
        )
        for value in _selections(game, c, state, actor)
    )


def _component(plan: RegrowthPlan, selected: Selection, event: str) -> AssetState:
    return AssetState(
        id=rules.identity(
            _namespace("regrown-frame", selected.loss_kind),
            plan.action,
            selected.loss or "",
        ),
        family="frame",
        name=selected.original.name,
        description=selected.original.description,
        damaged=False,
        void=selected.original.void,
        classification_event=event,
    )


def prepare_regrowth(
    game: GameService,
    c: Connection,
    state: GameState,
    actor: ActorRef,
    action: dict[str, Any],
    selected: tuple[str, ...],
    replacements: dict[str, str],
    *,
    historical: bool = False,
) -> RegrowthPlan:
    opportunity, choice, receipt = _dive(game, c, state, actor, action, historical=historical)
    if len(selected) > 2 or len(set(selected)) != len(selected):
        raise WorkflowError("Select up to two distinct actual Frame Assets")
    available = {value.token: value for value in _selections(game, c, state, actor)}
    if not set(selected) <= available.keys() or not set(replacements) <= set(selected):
        raise WorkflowError("Choose actual damaged or source-proved missing Frame Assets")
    if len(set(replacements.values())) != len(replacements) or set(replacements.values()) & set(
        selected
    ):
        raise WorkflowError("Choose distinct actual replacements separate from repaired Assets")
    plan = RegrowthPlan(
        actor=actor,
        frame=rules.frame(state, actor),
        action=action["id"],
        opportunity=opportunity.id,
        choice=choice,
        receipt=receipt,
        frame_assets=tuple(
            asset for asset in state.sheets[actor.entity].assets if asset.family == "frame"
        ),
        selected=tuple(
            available[token].model_copy(update={"replacement": replacements.get(token)})
            for token in selected
        ),
    )
    # Validate all births/cap removals on a clone before the real Girl-Asset cost.
    _install(state, plan, opportunity.event, record=False)
    return plan


def _install(state: GameState, plan: RegrowthPlan, event: str, *, record: bool) -> GameState:
    if rules.frame(state, plan.actor) != plan.frame:
        raise WorkflowError("The physical Frame changed before regrowth")
    current = tuple(
        asset for asset in state.sheets[plan.actor.entity].assets if asset.family == "frame"
    )
    if current != plan.frame_assets:
        raise WorkflowError("Reopen the actual changed Frame inventory before paying the cost")
    changed = GameState.model_validate_json(state.model_dump_json())
    for selected in plan.selected:
        sheet = changed.sheets[plan.actor.entity]
        if selected.kind == "repair":
            if selected.replacement is not None:
                raise WorkflowError("Present damaged hardware needs no cap replacement")
            next(asset for asset in sheet.assets if asset.id == selected.token).damaged = False
            continue
        if selected.replacement in budget.blocked(changed, plan.actor):
            raise WorkflowError(
                "SOURCE_REGROWTH_LIFECYCLE_REQUIRED: preserve linked replacement hardware"
            )
        component = _component(plan, selected, event)
        effective = frozenset(
            asset.id for asset in effective_assets(changed, plan.actor) if asset.void
        )
        result = install(
            sheet, component, replace=selected.replacement, effective_void=effective, state=changed
        )
        changed.sheets[plan.actor.entity] = result.sheet
        if record:
            rules.put(
                changed,
                rules.RegrownFrame(
                    id=rules.identity(
                        _namespace("regrowth", selected.loss_kind),
                        plan.action,
                        selected.loss or "",
                    ),
                    actor=plan.actor,
                    frame=plan.frame,
                    action=plan.action,
                    opportunity=plan.opportunity,
                    choice=plan.choice,
                    receipt=plan.receipt,
                    loss=selected.loss or "",
                    loss_event=selected.loss_event or "",
                    loss_kind=selected.loss_kind,
                    original=selected.original,
                    component=component,
                    event=event,
                    replacement=selected.replacement,
                ),
            )
    return changed


def apply_regrowth(
    game: GameService, c: Connection, state: GameState, plan: RegrowthPlan, event: str
) -> GameState:
    return _install(state, plan, event, record=True)


def prove_regrowth(
    game: GameService, c: Connection, state: GameState, identity: str
) -> rules.RegrownFrame:
    from girlframe.services.m3_asset_loss import snapshots

    value = next(
        (value for value in rules.records(state, rules.RegrownFrame) if value.id == identity), None
    )
    if value is None:
        raise WorkflowError("Recover the original regrown component birth")
    before, born = snapshots(game, c, value.event)
    saved = next(
        (entry for entry in rules.records(born, rules.RegrownFrame) if entry.id == identity), None
    )
    source = next(
        (entry for entry in rules.records(born, rules.Partaking) if entry.id == value.event), None
    )
    action = game.action(c, value.action)
    opportunity, choice_id, receipt_id = _dive(
        game, c, before, value.actor, action, historical=True
    )
    if (
        saved != value
        or source is None
        or source.option != "regrow"
        or source.actor != value.actor
        or source.action != value.action
        or choice_id != value.choice
        or receipt_id != value.receipt
        or opportunity.id != value.opportunity
        or rules.frame(before, value.actor) != value.frame
    ):
        raise WorkflowError("Preserve the genuine Partake choice, Frame and original Dive receipt")
    row = (
        c.execute(
            sa.select(t.m2["m2_choices"]).where(
                t.m2["m2_choices"].c.campaign_id == game.store.campaign_id,
                t.m2["m2_choices"].c.id == value.choice,
            )
        )
        .mappings()
        .one()
    )
    response = (
        c.execute(
            sa.select(t.m2["m2_responses"]).where(
                t.m2["m2_responses"].c.campaign_id == game.store.campaign_id,
                t.m2["m2_responses"].c.choice_id == value.choice,
            )
        )
        .mappings()
        .first()
    )
    if (
        response is None
        or response["actor_id"] != value.actor.entity
        or response["event_id"] != value.event
    ):
        raise WorkflowError("Recover the original human's actual regrowth response")
    answer = json.loads(response["answer_json"])
    fields = answer.get("fields", {})
    if (
        row["state"] != "answered"
        or answer.get("options") != ["regrow"]
        or fields.get("girl_asset") != source.girl_asset
        or tuple(json.loads(fields.get("frame_assets", "[]"))) != source.frame_assets
        or json.loads(fields.get("regrow_replacements", "{}")) != source.regrow_replacements
    ):
        raise WorkflowError("Preserve the actual original owner's resolved regrowth selection")
    old_girl = next(
        (
            asset
            for asset in before.sheets[value.actor.entity].assets
            if asset.id == source.girl_asset
        ),
        None,
    )
    new_girl = next(
        (
            asset
            for asset in born.sheets[value.actor.entity].assets
            if asset.id == source.girl_asset
        ),
        None,
    )
    if (
        old_girl is None
        or old_girl.family != "girl"
        or old_girl.damaged
        or new_girl is None
        or not new_girl.damaged
    ):
        raise WorkflowError("The actual intact Girl Asset must pay the real damage cost")
    plan = prepare_regrowth(
        game,
        c,
        before,
        value.actor,
        action,
        source.frame_assets,
        source.regrow_replacements,
        historical=True,
    )
    selected = next(
        (
            entry
            for entry in plan.selected
            if entry.loss == value.loss and entry.loss_kind == value.loss_kind
        ),
        None,
    )
    if (
        selected is None
        or selected.original != value.original
        or selected.loss_event != value.loss_event
        or _component(plan, selected, value.event) != value.component
        or selected.replacement != value.replacement
        or value.component not in born.sheets[value.actor.entity].assets
    ):
        raise WorkflowError(
            "Preserve exact original loss and new component birth; never old occupants"
        )
    return value
