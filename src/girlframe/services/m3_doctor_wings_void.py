"""Printed p17/p70: prove the original donor-confirmed Wings transfer before Void work."""

from typing import TYPE_CHECKING, Any

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_doctor as rules
from girlframe.engine.m2 import AssetState, GameState
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_actors import resolve
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_asset_loss import snapshots
from girlframe.services.m3_doctor_wings import graft
from girlframe.services.onboarding import WorkflowError

if TYPE_CHECKING:
    from girlframe.services.m2_game import GameService


def prove_loss_source(
    game: "GameService",
    c: Connection,
    state: GameState,
    event: str,
    identity: str,
    actor: ActorRef,
) -> dict[str, Any]:
    before, born = snapshots(game, c, event)
    proposal = next(
        (x for x in rules.values(before, "doctor_procedure", rules.Procedure) if x.id == identity),
        None,
    )
    completed = next(
        (x for x in rules.values(born, "doctor_procedure", rules.Procedure) if x.id == identity),
        None,
    )
    loan = next(
        (x for x in rules.values(born, "doctor_loan", rules.Loan) if x.id == identity), None
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
    donor = proposal.counterpart if proposal is not None else actor
    old, new = before.sheets.get(donor.entity), born.sheets.get(donor.entity)
    if (
        actor.kind != "pilot"
        or proposal is None
        or completed is None
        or loan is None
        or old is None
        or new is None
        or audit is None
        or proposal.kind != "wings"
        or proposal.phase != "proposal"
        or actor not in (proposal.counterpart, proposal.doctor)
        or proposal.controller != int(donor.entity)
        or audit["kind"] != "m3.doctor_procedure_completed"
        or audit["actor_id"] != donor.entity
        or completed != proposal.model_copy(update={"phase": "complete", "completion_event": event})
        or loan.source_event != event
        or loan.phase != "borrowed"
        or loan.donor != donor
        or loan.doctor != proposal.doctor
        or loan.frame != proposal.frame
        or old.character_id != donor.incarnation
        or new.character_id != donor.incarnation
        or old.frame_scrapped
        or new.frame_scrapped
        or loan.donor_frame
        != (old.frame_runtime.id if old.frame_runtime else "initial:" + str(donor.incarnation))
        or any(x.id == identity for x in rules.values(before, "doctor_loan", rules.Loan))
    ):
        raise WorkflowError("Recover the actual original donor-confirmed Wings source")
    asset = next((x for x in old.assets if x.id == proposal.asset), None)
    if (
        asset is None
        or asset.family != "frame"
        or not asset.damaged
        or AssetState.model_validate_json(loan.source_asset_json) != asset
        or loan.asset != "doctor-loan:" + identity
        or new.assets != [x for x in old.assets if x.id != asset.id]
    ):
        raise WorkflowError("Preserve the actual removed donor component and same-copy loan")
    expected, _ = graft(before, proposal.doctor, asset, loan.asset, proposal.replace)
    expected.heat -= proposal.heat
    doctor_before = before.sheets.get(proposal.doctor.entity)
    doctor_after = born.sheets.get(proposal.doctor.entity)
    if (
        doctor_before is None
        or doctor_after is None
        or doctor_before.character_id != proposal.doctor.incarnation
        or doctor_after.character_id != proposal.doctor.incarnation
        or rules.frame_id(before, proposal.doctor) != proposal.frame
        or rules.frame_id(born, proposal.doctor) != proposal.frame
        or expected != doctor_after
    ):
        raise WorkflowError("Preserve the actual Doctor graft and single Heat payment")
    if state.sheets.get(actor.entity) is None:
        raise WorkflowError("Recover the actual transfer participant source state")
    actual = resolve(
        before, actor, profiles(c, game.store.campaign_id), require_current_profile=False
    )
    return dict(piloting=actual.piloting, in_battle=None, source_action=None)
