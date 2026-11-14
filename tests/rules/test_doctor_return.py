"""One actual ordinary loan/loss/replacement/return, plus transformed custody transfer."""

import asyncio
from uuid import uuid4

import pytest
import sqlalchemy as sa
from test_doctor_runtime import acquire, doctor, next_period
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Gateway, answer, pass_tags, state, tick
from test_mission_ui import current
from test_replacement import supplied

from girlframe.database import tables as t
from girlframe.delivery.m2_worker import GameWorker
from girlframe.discord_adapter.m3_doctor_return import open_return
from girlframe.engine import m3_doctor as medical
from girlframe.engine import m3_doctor_return as rules
from girlframe.engine.m2 import AssetState, PlayInput
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_frame_state import Preferences
from girlframe.services.m3_doctor_procedures import ProcedureService
from girlframe.services.m3_doctor_return import ReturnService
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_replacement import ROOT, ReplacementService
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer


def _borrow(game, *, corrupt_graft=False, replace=None):
    with game.store.transaction() as c:
        canon = state(game)
        canon.sheets["2"].heat = 3
        selected = next(x for x in canon.sheets["3"].assets if x.family == "frame")
        selected.damaged = True
        selected.void = corrupt_graft
        selected.description = "Original physically borrowed component"
        game.event(c, 1, str(uuid4()), "synthetic.prior_damaged_component", canon)
    procedures = ProcedureService(game)
    identity = procedures.propose(
        PLAYER,
        str(uuid4()),
        state(game).revision,
        900,
        current_ref(state(game), 3),
        "wings",
        "PRIVATE original doctor performs the graft",
        asset=selected.id,
        heat=2,
        replace=replace,
    )["id"]
    procedures.confirm(
        OTHER,
        str(uuid4()),
        identity,
        state(game).revision,
        "PRIVATE original donor confirms real hardware removal",
    )
    return medical.values(state(game), "doctor_loan", medical.Loan)[-1], selected


def _replace(service, viewer, identity):
    data = service.get(viewer, identity)
    proposal = service.propose(
        viewer,
        str(uuid4()),
        identity,
        data["revision"],
        data["game_revision"],
        Preferences(frame="THE ENFORCER"),
    )
    data = service.get(ADMIN, proposal["package_id"])
    service.quote(
        ADMIN, str(uuid4()), data["id"], data["revision"], data["game_revision"], supplied()
    )
    data = service.get(viewer, identity)
    return service.apply(
        viewer,
        str(uuid4()),
        identity,
        data["revision"],
        data["game_revision"],
        data["package_revision"],
    )


def test_native_original_donor_scrapping_replacement_then_one_true_return(
    ledger, tmp_path, monkeypatch
):
    import test_m2_game

    original_ready = test_m2_game.ready
    monkeypatch.setattr(
        test_m2_game,
        "ready",
        lambda store, girl, frame: original_ready(store, girl, frame, other_frame=medical.BOOK),
    )
    original_selected = test_m2_game.selected
    monkeypatch.setattr(
        test_m2_game, "selected", lambda girl, frame: original_selected(girl, medical.BOOK)
    )
    _, game = doctor(ledger, tmp_path, monkeypatch)
    acquire(game, medical.WINGS)
    with ledger.transaction() as c:
        canon = state(game)
        canon.sheets["3"].obsolescence_marked = 7
        patient_asset = next(x for x in canon.sheets["2"].assets if x.family == "girl")
        patient_asset.damaged = True
        game.event(c, 1, str(uuid4()), "synthetic.prior_real_obsolescence_and_injury", canon)
    loan, original = _borrow(game)
    old_frame = loan.donor_frame
    game.dice.faces = (1, 1)
    procedure = game.begin(
        OTHER,
        str(uuid4()),
        900,
        state(game).sheets["3"].revision,
        PlayInput(
            play="nanobot_injection",
            target_actor=current_ref(state(game), 2),
            heat=0,
            context="Donor actually treats the original Doctor; her track fills",
            trigger_confirmed=True,
        ),
    )["action_id"]
    worker, gateway = GameWorker(game), Gateway()
    tick(worker, gateway, 3)
    pass_tags(game)
    answer(game, PLAYER, "doctor_patient", options=(patient_asset.id,))
    tick(worker, gateway, 6)
    assert game.inspect(OTHER, procedure)["state"] == "complete"
    assert state(game).sheets["3"].frame_scrapped
    missions = MissionService(ledger)
    replacement = next(x for x in missions.owned_work(OTHER) if x["kind"] == ROOT)
    _replace(ReplacementService(missions), OTHER, replacement["id"])
    assert rules.frame(state(game), loan.donor) != old_frame
    assert medical.values(state(game), "doctor_loan", medical.Loan)[-1].phase == "borrowed"
    next_period(ledger, game, monkeypatch)
    returns = ReturnService(game)
    identity = returns.tasks(OTHER)[0]["id"]
    assert not returns.tasks(PLAYER)[0]["actionable"]
    assert not returns.tasks(OTHER)[0]["actionable"]
    assert returns.tasks(ADMIN)[0]["actionable"]
    assert returns.get(OTHER, identity)["state"] == "pending"
    assert any(x.id == loan.asset for x in state(game).sheets["2"].assets)
    outsider = GuildViewer(4, 200, True, True)
    ledger.join(outsider, str(uuid4()))
    with pytest.raises(WorkflowError):
        returns.get(outsider, identity)

    async def native():
        quote_interaction = current(1, 991203)
        await quote_interaction.response.defer(ephemeral=True)
        await open_return(quote_interaction, returns, identity)
        picker = quote_interaction.edit_original_response.call_args.kwargs["view"]
        form_interaction = current(1, 991204)
        await form_interaction.response.defer(ephemeral=True)
        await picker.open_item(form_interaction, "quote")
        form = form_interaction.edit_original_response.call_args.kwargs["view"]
        form.values.update(
            replace=("none",),
            account=(
                "PRIVATE engineers return the exact graft to the donor's "
                "chosen current replacement Frame"
            ),
        )
        await form.confirm.callback(current(1, 991205))
        assert form.completed
        viewed = returns.get(OTHER, identity)
        assert returns.tasks(OTHER)[0]["actionable"]
        assert not returns.tasks(PLAYER)[0]["actionable"]
        assert viewed["package"]["frame"] == rules.frame(state(game), loan.donor)
        with pytest.raises(WorkflowError, match="original donor"):
            returns.confirm(
                ADMIN, str(uuid4()), identity, viewed["revision"], viewed["game_revision"]
            )
        donor = current(3, 991206)
        await donor.response.defer(ephemeral=True)
        await open_return(donor, ReturnService(game), identity)
        picker = donor.edit_original_response.call_args.kwargs["view"]
        await picker.open_item(current(3, 991207), "confirm")
        assert returns.get(OTHER, identity)["state"] == "resolved"
        # Original repeated interaction cannot move or create another component.
        result = returns.confirm(
            OTHER, "991207", identity, viewed["revision"], viewed["game_revision"]
        )
        assert result["state"] == "resolved"
        reopened = current(3, 991208)
        await reopened.response.defer(ephemeral=True)
        await open_return(reopened, returns, identity)
        assert "returned" in reopened.edit_original_response.call_args.kwargs["content"]
        assert not reopened.edit_original_response.call_args.kwargs["allowed_mentions"].everyone
        with pytest.raises(WorkflowError, match="STALE_RETURN"):
            returns.confirm(
                OTHER, str(uuid4()), identity, viewed["revision"], viewed["game_revision"]
            )

    asyncio.run(native())
    after = state(game)
    assert not any(x.id == loan.asset for x in after.sheets["2"].assets)
    returned = next(x for x in after.sheets["3"].assets if x.id == original.id)
    assert not returned.damaged and returned.void == original.void
    assert len([x for x in after.facts if x.get("kind") == "doctor_wings_return_receipt"]) == 1
    with ledger.engine.connect() as c:
        assert "PRIVATE" not in str(list(c.scalars(sa.select(t.events.c.payload_json))))
    game.rebuild()
    assert state(game) == after


def test_converted_doctor_graft_recovers_same_noncore_component(ledger, tmp_path, monkeypatch):
    """Actual Wings/abandonment producer, then the new pure transfer consumer.

    The first test covers native Off-Duty packaging; this scoped normal checks
    transformed same-copy extraction, not a second full Off-Duty/Strain matrix.
    """
    from test_void_service import respond
    from test_world import initial

    from girlframe.engine.m3_assets import frame_capacity
    from girlframe.engine.m3_physical_state import InitialPlacement
    from girlframe.engine.m3_world_state import Asset, CorePlan, Gorgon
    from girlframe.services.m3_physical import PhysicalService
    from girlframe.services.m3_void import VoidService

    _, game = doctor(ledger, tmp_path, monkeypatch)
    acquire(game, medical.WINGS)
    with ledger.transaction() as c:
        canon = state(game)
        canon.world = initial()
        game.event(c, 1, str(uuid4()), "synthetic.prior_campaign_world", canon)
    physical = PhysicalService(ledger)
    for viewer in (PLAYER, OTHER):
        actor = current_ref(state(game), viewer.user_id)
        proposal = physical.propose(
            viewer,
            str(uuid4()),
            state(game).revision,
            InitialPlacement(
                actor=actor,
                frame_instance=rules.frame(state(game), actor),
                girl_cell=(0, 0),
                frame_cell=(0, 0),
                mode="outside_frame",
                account="Actual original body and Frame at base",
                facts_confirmed=True,
            ),
        )
        physical.decide(
            ADMIN,
            str(uuid4()),
            proposal["id"],
            1,
            "accept",
            "Handler confirms the actual original people and Frame locations",
        )
    with ledger.transaction() as c:
        canon = state(game)
        host = canon.sheets["2"]
        for index in range(
            frame_capacity(host, canon) - sum(x.family == "frame" for x in host.assets)
        ):
            host.assets.append(
                AssetState(
                    id="prior-cap:" + str(index), family="frame", name="Physical prior hardware"
                )
            )
        hardware = [x for x in host.assets if x.family == "frame"]
        for asset in hardware:
            asset.void = True
            asset.description = "Original physical Frame hardware"
        replace = hardware[0]
        replace.void = False
        game.event(c, 1, str(uuid4()), "synthetic.prior_cap_corruption", canon)
    loan, original = _borrow(game, corrupt_graft=True, replace=replace.id)
    void = VoidService(ledger)
    work = next(x["id"] for x in void.tasks(PLAYER))
    assert void.get(PLAYER, work)["stage"] == "abandoned"
    before = state(game)
    hardware = [x for x in before.sheets["2"].assets if x.family == "frame"]
    core = next(x for x in hardware if x.id != loan.asset)
    gorgon = Gorgon(
        id="actual-original-doctor-body",
        name="Actual cooperative converted Frame",
        gorgon_class="benevolent",
        types=("sentinel",),
        cell=(0, 0),
        assets=tuple(
            Asset(
                id=x.id,
                name=x.name,
                description=x.description,
                family="gorgon",
                void=x.void,
                damaged=x.damaged,
            )
            for x in hardware
        ),
        core_plan=CorePlan(assets=(core.id,), weakness="Actual original core access"),
    )
    respond(
        void,
        work,
        "abandoned",
        dict(
            gorgon=gorgon.model_dump(mode="json"),
            account="Handler records this actual unoccupied Frame's cooperative Gorgon conversion",
        ),
        viewer=ADMIN,
    )
    converted = state(game)
    assert converted.sheets["2"].frame_scrapped
    source = rules.locate(converted, loan)
    assert source.kind == "gorgon" and source.asset.void and source.asset.id == loan.asset
    with ledger.engine.connect() as c:
        package = ReturnService(game)._package(
            c,
            converted,
            loan,
            "PRIVATE actual engineers recover the accessible non-core component "
            "from the cooperative body at the donor's base",
            "synthetic-package-preview",
            1,
            None,
        )
    returned = rules.transfer(converted, package, "synthetic-pure-return", 3)
    body = next(x for x in returned.world.gorgons if x.id == gorgon.id)
    assert body.alive and body.core_plan == gorgon.core_plan
    assert {x.id for x in body.assets} == {x.id for x in gorgon.assets} - {loan.asset}
    actual = next(x for x in returned.sheets["3"].assets if x.id == original.id)
    assert actual.void and not actual.damaged
    assert medical.values(returned, "doctor_loan", medical.Loan)[-1].phase == "returned"
    assert medical.values(converted, "doctor_loan", medical.Loan)[-1].phase == "borrowed"
    with pytest.raises(ValueError, match="still-borrowed"):
        rules.transfer(returned, package, "cannot-return-twice", 3)
