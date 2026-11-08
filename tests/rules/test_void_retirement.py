"""Actual recursive Void source, native private offer, owned accept/decline and archive."""

import asyncio
from uuid import uuid4

import pytest
import sqlalchemy as sa
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state
from test_mission_ui import current
from test_strain_service import prepared, ready

from girlframe.database import tables as t
from girlframe.discord_adapter.inbox import InboxView
from girlframe.engine.m2 import PilotSheet
from girlframe.engine.m3_void_retirement import offers
from girlframe.services.inbox import InboxService
from girlframe.services.m3_void_retirement import StipendService
from girlframe.services.onboarding import WorkflowError


@pytest.mark.parametrize("outcome", ["accept", "decline"])
def test_genuine_void_endgame_owned_stipend_offer_and_actual_career_outcome(ledger, outcome):
    strain, game = ready(ledger, face=6)
    approval = ledger.policy.m3_approval
    ledger.policy = ledger.policy.model_copy(
        update={
            "m3_approval": approval.model_copy(
                update={"subsystems": approval.subsystems | {"economy"}}
            )
        }
    )
    # Prior current Void sustains the High track; no synthetic source outcome.
    with ledger.transaction() as c:
        initial = state(game)
        initial.sheets["2"].assets[0].void = True
        game.event(c, 1, "prior-void", "synthetic.prior_void", initial)
    prepared(strain, game, high=frozenset({"void"}))
    while True:
        request = next(
            x
            for x in state(game).strain.requests
            if x.track == "void" and (x.kind == "endgame" or x.severity == "high")
        )
        if request.kind == "endgame":
            break
        strain.roll(ADMIN, str(uuid4()), request.id, 1, state(game).revision)
        strain.choose(ADMIN, str(uuid4()), request.id, 2, state(game).revision, 2)
    strain.choose(
        ADMIN, "actual-stipend-endgame", request.id, 1, state(game).revision, 4, endgame=True
    )
    identity = request.id + ":effect"
    service = StipendService(ledger)
    baseline = state(game)
    original_girl = baseline.sheets["2"].model_copy(deep=True)
    dice_calls = strain.dice.calls, game.dice.calls
    with pytest.raises(WorkflowError):
        service.view(PLAYER, identity)

    async def native(viewer, number, values):
        inbox = InboxService(ledger)
        item = next(x for x in inbox.items(viewer) if x.identity == identity)
        assert item.task == "m3_void_retirement"
        interaction = current(viewer.user_id, number)
        interaction.channel_id = 999
        await interaction.response.defer(ephemeral=True)
        await InboxView(inbox, viewer.user_id).route(interaction, item)
        form = interaction.edit_original_response.call_args.kwargs["view"]
        form.values.update(values)
        await form.confirm.callback(current(viewer.user_id, number + 1))
        assert form.completed

    asyncio.run(native(ADMIN, 31210, dict(girl=("2",), account="PRIVATE STIPEND OFFER")))
    offered = state(game)
    assert offers(offered)[0].phase == "offered" and offered.sheets == baseline.sheets
    with pytest.raises(WorkflowError):
        service.view(OTHER, identity)
    with pytest.raises(WorkflowError):
        service.act(
            ADMIN, "no-owner-response", identity, offered.revision, outcome, "Not my choice"
        )
    assert state(game) == offered
    revision = offered.revision
    asyncio.run(native(PLAYER, 31220, dict(response=(outcome,), account="PRIVATE PLAYER RESPONSE")))
    after = state(game)
    value = offers(after)[0]
    assert value.phase == ("accepted" if outcome == "accept" else "declined")
    if outcome == "accept":
        assert "2" not in after.sheets and 2 not in after.order
        archive = after.career_archives[-1]
        assert archive.id == value.archive and archive.actor == value.girl
        assert archive.ending == "retirement"
        saved = PilotSheet.model_validate_json(archive.sheet_json)
        assert saved.permissions == original_girl.permissions
        assert saved.assets == original_girl.assets and saved.identities == original_girl.identities
        stipend = next(x for x in after.facts if x.get("kind") == "void_retirement_stipend")
        assert stipend["stipend"] == "granted" and stipend["archive"] == archive.id
        assert not any(x.source_event == value.response_event for x in after.requisitions)
    else:
        assert after.sheets == baseline.sheets and after.order == baseline.order
        assert after.career_archives == baseline.career_archives
    assert (strain.dice.calls, game.dice.calls) == dice_calls
    assert service.act(
        PLAYER, "31221", identity, revision, outcome, "PRIVATE PLAYER RESPONSE"
    ) == dict(id=identity, phase=value.phase)
    assert state(game) == after
    with ledger.engine.connect() as c:
        row = (
            c.execute(
                sa.select(t.m3["m3_required_work"])
                .where(t.m3["m3_required_work"].c.id == identity)
                .order_by(t.m3["m3_required_work"].c.revision.desc())
                .limit(1)
            )
            .mappings()
            .one()
        )
        assert row["state"] == "resolved"
        assert "PRIVATE " not in str(list(c.scalars(sa.select(t.events.c.payload_json))))

    async def reopen():
        from girlframe.discord_adapter.m3_void_retirement import open_offer

        interaction = current(2, 31230)
        await interaction.response.defer(ephemeral=True)
        await open_offer(interaction, service, identity)
        card = interaction.edit_original_response.call_args.kwargs
        assert [x.description for x in card["embeds"]] == [
            "PRIVATE STIPEND OFFER",
            "PRIVATE PLAYER RESPONSE",
        ]
        assert card["view"] is None

    asyncio.run(reopen())
    assert state(game) == after
