"""Wings must preserve a donor's live expiry/return source before moving hardware."""

from uuid import uuid4

import pytest
from test_doctor_runtime import acquire, doctor
from test_ledger import OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state

from girlframe.engine import m3_doctor as rules
from girlframe.engine import m3_supply_drop as supply
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.services.m3_doctor_procedures import ProcedureService
from girlframe.services.m3_doctor_requisitions import DoctorRequisitionService
from girlframe.services.onboarding import WorkflowError


def test_wings_rejects_temporary_donor_and_legacy_confirmation_without_spending(
    ledger, tmp_path, monkeypatch
):
    _, game = doctor(ledger, tmp_path, monkeypatch)
    acquire(game, rules.WINGS)
    with ledger.transaction() as c:
        value = state(game)
        doc, donor = current_ref(value, 2), current_ref(value, 3)
        value.sheets["2"].heat = 3
        equipment = next(x for x in value.sheets["3"].assets if x.family == "frame")
        equipment.damaged = True
        # Existing delivered source, including the supported Modular repair lineage.
        # Supply Drop's own acquisition/delivery is covered by test_supply_drop.py.
        delivered_id = "synthetic-delivered-equipment"
        supply.put(
            value,
            supply.Use(
                id="prior-delivery",
                acquisition="prior-supply-purchase",
                handler=ActorRef(kind="handler", entity="1"),
                mission="ongoing-mission",
                target=donor,
                frame="initial:" + str(donor.incarnation),
                kind="drop",
                phase="delivered",
                asset=delivered_id,
                name=equipment.name,
                description="Prior temporary equipment with a real current component",
                position="prior-delivery-position",
                cell=(0, 0),
                event="prior-drop-proposal",
                account="Existing temporary source",
                effect_event="prior-drop-delivery",
            ),
        )
        value.facts.append(
            dict(
                kind="modular_repair",
                actor=donor.model_dump_json(),
                old=delivered_id,
                new=equipment.id,
            )
        )
        # A persisted pre-fix proposal must not bypass validation at confirmation.
        pending = rules.Procedure(
            id="legacy-wings-proposal",
            kind="wings",
            doctor=doc,
            frame=rules.frame_id(value, doc),
            counterpart=donor,
            controller=3,
            source_event="prior-wings-proposal",
            account="Existing unconfirmed procedure",
            channel=900,
            heat=2,
            asset=equipment.id,
        )
        rules.put(value, "doctor_procedure", pending)
        game.event(c, 1, str(uuid4()), "synthetic.prior_linked_donor", value)
    procedures = ProcedureService(game)
    before, calls = state(game), game.dice.calls
    with pytest.raises(WorkflowError, match="temporary Supply Drop"):
        procedures.propose(
            PLAYER,
            str(uuid4()),
            before.revision,
            900,
            donor,
            "wings",
            "Must preserve the live Mission expiry source",
            asset=equipment.id,
            heat=2,
        )
    assert state(game) == before
    with pytest.raises(WorkflowError, match="temporary Supply Drop"):
        procedures.confirm(
            OTHER, str(uuid4()), pending.id, before.revision, "Cannot orphan live equipment"
        )
    assert state(game) == before and game.dice.calls == calls
    assert not rules.values(state(game), "doctor_loan", rules.Loan)


def test_wings_does_not_reloan_another_doctors_live_borrowed_asset(ledger, tmp_path, monkeypatch):
    import test_m2_game
    from test_creation import selected
    from test_creation_review import ready

    # Both actual characters are created as native Doctors, rather than changing
    # a Frame label after creation or manufacturing an incompatible entitlement.
    monkeypatch.setattr(
        test_m2_game,
        "ready",
        lambda store, girl, frame: ready(store, girl, frame, other_frame=rules.BOOK),
    )
    monkeypatch.setattr(test_m2_game, "selected", lambda girl, frame: selected(girl, rules.BOOK))
    _, game = doctor(ledger, tmp_path, monkeypatch)
    acquire(game, rules.WINGS)
    with ledger.transaction() as c:
        value = state(game)
        value.sheets["3"].permissions = 2
        for sheet in value.sheets.values():
            sheet.heat = 3
        equipment = next(x for x in value.sheets["3"].assets if x.family == "frame")
        equipment.damaged = True
        game.event(c, 1, str(uuid4()), "synthetic.existing_doctor_resources", value)
    DoctorRequisitionService(game).buy(
        OTHER, str(uuid4()), state(game).revision, rules.WINGS, "Actual second Doctor purchase"
    )
    procedures = ProcedureService(game)
    doc, donor = current_ref(state(game), 2), current_ref(state(game), 3)
    proposal = procedures.propose(
        PLAYER,
        str(uuid4()),
        state(game).revision,
        900,
        donor,
        "wings",
        "Actual ordinary original transfer",
        asset=equipment.id,
        heat=2,
    )
    procedures.confirm(
        OTHER, str(uuid4()), proposal["id"], state(game).revision, "Original donor confirms"
    )
    loan = rules.values(state(game), "doctor_loan", rules.Loan)[0]
    with ledger.transaction() as c:
        value = state(game)
        graft = next(x for x in value.sheets["2"].assets if x.id == loan.asset)
        graft.damaged = True
        game.event(c, 1, str(uuid4()), "synthetic.later_borrowed_hardware_damage", value)
    before, calls = state(game), game.dice.calls
    with pytest.raises(WorkflowError, match="borrowed Wings Asset"):
        procedures.propose(
            OTHER,
            str(uuid4()),
            before.revision,
            900,
            doc,
            "wings",
            "A second loan must not strand the first return",
            asset=loan.asset,
            heat=2,
        )
    assert state(game) == before and game.dice.calls == calls
    assert rules.values(state(game), "doctor_loan", rules.Loan) == (loan,)


def test_wings_preserves_custody_when_call_reclassifies_a_held_asset(ledger, tmp_path, monkeypatch):
    from test_items import carried_asset

    from girlframe.engine.m3_items import actual_asset
    from girlframe.engine.m3_mockingbird_assets import classify
    from girlframe.services.m3_actors import profiles

    _, game = doctor(ledger, tmp_path, monkeypatch)
    acquire(game, rules.WINGS)
    equipment = next(x for x in state(game).sheets["3"].assets if x.family == "girl")
    carried_asset(game, OTHER, equipment)
    with ledger.transaction() as c:
        value = state(game)
        donor = current_ref(value, 3)
        value, followups = classify(
            value,
            profiles(c, ledger.campaign_id),
            donor,
            {equipment.id: "frame"},
            (),
            action="prior-owned-call",
            step=0,
            event="prior-call-classification",
            account="Actual Call changes the owned held Asset's classification",
        )
        assert not followups
        value.sheets["2"].heat = 3
        moved = next(x for x in value.sheets["3"].assets if x.id == equipment.id)
        moved.damaged = True
        game.event(c, 1, str(uuid4()), "synthetic.after_owned_call_and_damage", value)
    before, calls = state(game), game.dice.calls
    item = before.held_items[-1]
    assert actual_asset(before, item).family == "frame"
    with pytest.raises(WorkflowError, match="held object's custody"):
        ProcedureService(game).propose(
            PLAYER,
            str(uuid4()),
            before.revision,
            900,
            donor,
            "wings",
            "The existing object's custody cannot remain on the emptied donor",
            asset=equipment.id,
            heat=2,
        )
    assert state(game) == before and game.dice.calls == calls
    assert actual_asset(state(game), item) == actual_asset(before, item)
