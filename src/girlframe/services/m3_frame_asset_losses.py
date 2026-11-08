"""Two explicit producer identities share one immutable Frame-loss selection shape."""

from typing import Literal

from sqlalchemy import Connection

from girlframe.engine import m3_consume as consume
from girlframe.engine.m2 import AssetState, GameState
from girlframe.engine.m3_actor_state import ActorRef, Model
from girlframe.engine.m3_budget_removal import blocked
from girlframe.engine.m3_core import install
from girlframe.engine.m3_janus_storage import ids as stored_ids
from girlframe.engine.m3_requisition_state import Receipt
from girlframe.engine.m3_requisitions import asset_name
from girlframe.services.m2_game import GameService
from girlframe.services.m3_asset_loss import snapshots
from girlframe.services.m3_privileges import purchase_proof
from girlframe.services.onboarding import WorkflowError


class FrameAssetLoss(Model):
    source_kind: Literal["budget", "asset_installment"]
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
