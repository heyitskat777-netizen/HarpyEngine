"""Printed p13/p70: owned Wings cap exchange preserves actual linked hardware."""

from girlframe.engine import m3_doctor as rules
from girlframe.engine.m2 import AssetState, GameState, PilotSheet
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_assets import can_replace_at_limit, counts_toward_limit, frame_capacity
from girlframe.engine.m3_budget_removal import blocked
from girlframe.engine.m3_core import install
from girlframe.engine.m3_janus_storage import ids as stored_ids
from girlframe.services.onboarding import WorkflowError


def replacements(state: GameState, actor: ActorRef) -> list[dict[str, str]]:
    sheet = rules.sheet(state, actor)
    if sum(
        x.family == "frame" and counts_toward_limit(sheet, x) for x in sheet.assets
    ) < frame_capacity(sheet, state):
        return []
    excluded = set(blocked(state, actor)) | {
        x.asset
        for x in rules.values(state, "doctor_loan", rules.Loan)
        if x.doctor == actor and x.phase == "borrowed"
    }
    return [
        dict(id=x.id, label=x.name)
        for x in sheet.assets
        if x.family == "frame" and can_replace_at_limit(sheet, x) and x.id not in excluded
    ]


def graft(
    state: GameState, actor: ActorRef, asset: AssetState, identity: str, replace: str | None
) -> tuple[PilotSheet, AssetState]:
    sheet = rules.sheet(state, actor)
    if replace is not None and replace not in {x["id"] for x in replacements(state, actor)}:
        raise WorkflowError("Choose your actual replaceable non-Void Frame Asset at the cap")
    received = asset.model_copy(update={"id": identity, "damaged": False})
    try:
        updated = install(
            sheet, received, replace=replace, effective_void=stored_ids(state, actor), state=state
        ).sheet
    except ValueError as error:
        raise WorkflowError(str(error)) from None
    return updated, received
