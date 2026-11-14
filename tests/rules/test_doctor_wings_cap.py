"""Printed p13/p70 normal: the Doctor owns cap exchange, the donor owns transfer."""

import asyncio
from uuid import uuid4

import pytest
import sqlalchemy as sa
from test_doctor_runtime import acquire, doctor, next_period
from test_ledger import OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state
from test_mission_ui import current

from girlframe.database import tables as t
from girlframe.discord_adapter.m3_doctor import open_procedure, open_request
from girlframe.engine import m3_doctor as rules
from girlframe.engine.m2 import AssetState
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.services.m3_doctor_procedures import ProcedureService
from girlframe.services.onboarding import WorkflowError


def test_native_wings_at_cap_preserves_owned_exchange_source_and_off_duty_return(
    ledger, tmp_path, monkeypatch
):
    source, game = doctor(ledger, tmp_path, monkeypatch)
    acquire(game, rules.WINGS)
    with ledger.transaction() as c:
        initial = state(game)
        doc = initial.sheets["2"]
        doc.heat = 3
        for index in range(5 - sum(x.family == "frame" for x in doc.assets)):
            doc.assets.append(
                AssetState(
                    id="owned-cap:" + str(index),
                    family="frame",
                    name="PRIVATE_OWNED_HARDWARE " + str(index),
                )
            )
        replaced = doc.assets[-1].model_copy(deep=True)
        donor = initial.sheets["3"]
        damaged = next(x for x in donor.assets if x.family == "frame")
        damaged.damaged = True
        original = damaged.model_copy(deep=True)
        game.event(c, 1, str(uuid4()), "synthetic.actual_wings_cap_resources", initial)
    actor, donor_ref = current_ref(state(game), 2), current_ref(state(game), 3)
    calls = game.dice.calls
    prior_doc = state(game).sheets["2"].model_copy(deep=True)
    prior_donor = state(game).sheets["3"].model_copy(deep=True)
    procedures = ProcedureService(game)
    with pytest.raises(WorkflowError, match="explicitly replace"):
        procedures.propose(
            PLAYER,
            str(uuid4()),
            state(game).revision,
            900,
            donor_ref,
            "wings",
            "The cap cannot silently choose which owned Asset to erase",
            asset=original.id,
            heat=2,
        )
    assert not rules.values(state(game), "doctor_procedure", rules.Procedure)
    assert state(game).sheets["2"] == prior_doc
    assert state(game).sheets["3"] == prior_donor

    async def episode():
        menu = source.menu(PLAYER, 900)
        assert replaced.id in {x["id"] for x in menu["wings_replacements"]}
        own = current(2, 999401)
        own.channel_id = 900
        await own.response.defer(ephemeral=True)
        await open_procedure(own, source, menu, "wings")
        form = own.edit_original_response.call_args.kwargs["view"]
        assert next(x for x in form.fields if x.key == "replace").required
        item = next(
            x
            for x in menu["wings_assets"]
            if x["id"] == original.id and x["ref"] == donor_ref.model_dump(mode="json")
        )
        form.values.update(
            asset=(item["token"],),
            replace=(replaced.id,),
            heat=("2",),
            account="PRIVATE_WINGS I graft the damaged hardware and replace my selected component",
        )
        submitted = current(2, 999402)
        await form.confirm.callback(submitted)
        assert form.completed
        await form.confirm.callback(submitted)
        proposals = rules.values(state(game), "doctor_procedure", rules.Procedure)
        assert len(proposals) == 1
        proposal = proposals[0]
        assert proposal.replace == replaced.id and proposal.phase == "proposal"
        assert state(game).sheets["2"] == prior_doc
        assert state(game).sheets["3"] == prior_donor
        assert "PRIVATE_OWNED_HARDWARE" not in str(procedures.get(OTHER, proposal.id))
        with pytest.raises(WorkflowError, match="actual donor"):
            procedures.confirm(
                PLAYER, str(uuid4()), proposal.id, state(game).revision, "Cannot answer for donor"
            )
        donor = current(3, 999403)
        await donor.response.defer(ephemeral=True)
        await open_request(donor, source, proposal.id)
        confirmation = donor.edit_original_response.call_args.kwargs["view"]
        assert [x.key for x in confirmation.fields] == ["account"]
        confirmation.values.update(account="PRIVATE_DONOR I confirm the performed transfer")
        accepted = current(3, 999404)
        await confirmation.confirm.callback(accepted)
        assert confirmation.completed
        complete = state(game)
        await confirmation.confirm.callback(accepted)
        assert state(game) == complete
        loan = rules.values(complete, "doctor_loan", rules.Loan)[0]
        doc = complete.sheets["2"]
        assert doc.heat == 1 and sum(x.family == "frame" for x in doc.assets) == 5
        assert replaced.id not in {x.id for x in doc.assets}
        received = next(x for x in doc.assets if x.id == loan.asset)
        assert received.name == original.name and not received.damaged
        assert original.id not in {x.id for x in complete.sheets["3"].assets}
        assert loan.donor == donor_ref and loan.doctor == actor
        assert loan.source_asset_json == original.model_dump_json()
        with ledger.engine.connect() as c:
            public = str(list(c.scalars(sa.select(t.events.c.payload_json))))
            assert "PRIVATE_WINGS" not in public and "PRIVATE_DONOR" not in public
        assert game.dice.calls == calls
        return loan

    loan = asyncio.run(episode())
    next_period(ledger, game, monkeypatch)
    final = state(game)
    assert rules.values(final, "doctor_loan", rules.Loan)[0].phase == "returned"
    assert loan.asset not in {x.id for x in final.sheets["2"].assets}
    assert replaced.id not in {x.id for x in final.sheets["2"].assets}
    restored = next(x for x in final.sheets["3"].assets if x.id == original.id)
    assert not restored.damaged and restored.name == original.name
