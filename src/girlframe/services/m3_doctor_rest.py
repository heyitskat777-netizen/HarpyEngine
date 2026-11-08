"""One real next Off-Duty boundary returns borrowed hardware and schedules actual care."""

from typing import TYPE_CHECKING
from uuid import uuid4

from sqlalchemy import Connection

from girlframe.engine import m3_doctor as rules
from girlframe.engine.m2 import AssetState
from girlframe.engine.m3_off_duty import Period
from girlframe.services.m2_state import load_state
from girlframe.services.m3_scene_requisitions import _activation

if TYPE_CHECKING:
    from girlframe.services.m2_game import GameService


def synchronize(c: Connection, game: "GameService", period: Period, event: str) -> None:
    if period.phase != "active":
        return
    state = load_state(c, game.store.campaign_id)
    loans = [x for x in rules.values(state, "doctor_loan", rules.Loan) if x.phase == "borrowed"]
    cares = [
        x
        for x in rules.values(state, "doctor_care", rules.Care)
        if x.angel and x.phase == "active" and x.period is None
    ]
    if not loans and not cares:
        return
    activation = _activation(c, game.store, period)
    if activation is None:
        return
    initial, source = activation
    changed = False
    actual_event = str(uuid4())
    for loan in loans:
        if not any(x.id == loan.id for x in rules.values(initial, "doctor_loan", rules.Loan)):
            continue
        doc = state.sheets.get(loan.doctor.entity)
        donor = state.sheets.get(loan.donor.entity)
        if (
            doc is None
            or donor is None
            or doc.character_id != loan.doctor.incarnation
            or donor.character_id != loan.donor.incarnation
            or donor.frame_scrapped
        ):
            continue
        frame = (
            donor.frame_runtime.id
            if donor.frame_runtime
            else "initial:" + str(loan.donor.incarnation)
        )
        graft = next((x for x in doc.assets if x.id == loan.asset), None)
        original = AssetState.model_validate_json(loan.source_asset_json)
        if (
            frame != loan.donor_frame
            or graft is None
            or any(x.id == original.id for x in donor.assets)
        ):
            continue
        donor.assets.append(
            original.model_copy(
                update=dict(damaged=graft.damaged, void=graft.void, description=graft.description)
            )
        )
        doc.assets = [x for x in doc.assets if x.id != graft.id]
        doc.revision += 1
        donor.revision += 1
        rules.put(
            state,
            "doctor_loan",
            loan.model_copy(update=dict(phase="returned", return_event=actual_event)),
        )
        changed = True
    for care in cares:
        if (
            initial.sheets.get(care.doctor.entity) is None
            or initial.sheets[care.doctor.entity].character_id != care.doctor.incarnation
            or int(care.doctor.entity) not in period.pilots
            or not any(x.id == care.id for x in rules.values(initial, "doctor_care", rules.Care))
        ):
            continue
        rules.put(
            state, "doctor_care", care.model_copy(update=dict(phase="recovery", period=period.id))
        )
        changed = True
    if changed:
        game.event(
            c,
            period.handler,
            str(uuid4()),
            "m3.doctor_off_duty",
            state,
            event_id=actual_event,
            period=period.id,
            source_event=source,
        )
