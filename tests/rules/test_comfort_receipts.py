"""Paid Creature Comforts history is original-owned, source-proved and freshly authorized."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4

import pytest
import sqlalchemy as sa
from test_comfort_service import offered
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state
from test_mission_ui import current
from test_requisition_service import ready

from girlframe.config import Settings
from girlframe.database import tables as t
from girlframe.database.connection import create_database_engine
from girlframe.database.maintenance import copy_database
from girlframe.discord_adapter.m3_comforts import PaidComfortPages, open_comfort
from girlframe.discord_adapter.m3_requisitions import open_requisitions
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.services.m2_game import GameService
from girlframe.services.m3_comforts import ComfortService
from girlframe.services.m3_requisitions import RequisitionService
from girlframe.services.onboarding import OnboardingStore, WorkflowError
from girlframe.services.read_only_bot import GuildViewer


def paid(store, account="PRIVATE_PAID_COMFORT_REQUEST"):
    requisitions, game = ready(store)
    svc = ComfortService(game)
    data = requisitions.view(PLAYER)
    identity = svc.buy_comforts(
        PLAYER,
        "one-paid-comfort",
        ActorRef.model_validate(data["actor"]),
        data["source_sha256"],
        account,
    )["id"]
    return svc, game, identity


def test_paid_request_rolls_back_then_concurrent_retry_commits_one_charge_and_original_receipt(
    ledger, monkeypatch
):
    requisitions, game = ready(ledger)
    svc = ComfortService(game)
    data, before = requisitions.view(PLAYER), state(game)

    def pay():
        return svc.buy_comforts(
            PLAYER,
            "retry-payment",
            ActorRef.model_validate(data["actor"]),
            data["source_sha256"],
            "PRIVATE_PAID_RETRY_REQUEST",
        )

    original = game.event

    def fail(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError("synthetic failure after payment history")

    monkeypatch.setattr(game, "event", fail)
    with pytest.raises(RuntimeError):
        pay()
    assert state(game) == before and svc.receipts(PLAYER) == []
    monkeypatch.setattr(game, "event", original)
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(lambda _: pay(), range(2)))
    assert outcomes[0] == outcomes[1] and len(state(game).requisitions) == 1
    assert state(game).sheets["2"].permissions == before.sheets["2"].permissions - 1
    assert svc.paid_receipt(PLAYER, outcomes[0]["id"])["account"] == "PRIVATE_PAID_RETRY_REQUEST"
    assert pay() == outcomes[0] and game.dice.calls == 0


def test_original_paid_receipt_survives_real_backup_restore_rebuild_and_private_export(
    ledger, tmp_path
):
    svc, game, identity = paid(ledger)
    original = svc.paid_receipt(PLAYER, identity)
    assert "PRIVATE_PAID" not in str(ledger.public_export())
    with ledger.engine.connect() as c:
        assert "PRIVATE_PAID" not in str(list(c.scalars(sa.select(t.events.c.payload_json))))
        assert c.scalar(sa.select(sa.func.count()).select_from(t.m2["m2_outbox"])) == 0
    destination = tmp_path / "restored-paid-comforts.db"
    copy_database(Path(ledger.engine.url.database), destination)
    restored = create_database_engine(Settings(database_url="sqlite:///" + str(destination)))
    try:
        other_game = GameService(OnboardingStore(restored, ledger.policy))
        other = ComfortService(other_game)
        assert other.paid_receipt(PLAYER, identity) == original
        with other_game.store.transaction() as c:
            c.execute(
                t.m2["m2_state"]
                .delete()
                .where(t.m2["m2_state"].c.campaign_id == ledger.campaign_id)
            )
        assert other_game.rebuild() > 0
        assert other.paid_receipt(PLAYER, identity) == original
    finally:
        restored.dispose()


def test_paid_receipt_does_not_grant_access_to_other_humans_admins_or_campaigns(ledger):
    svc, game, identity = paid(ledger)
    expected = svc.paid_receipt(PLAYER, identity)
    for viewer in (OTHER, ADMIN):
        assert svc.receipts(viewer) == []
        with pytest.raises(WorkflowError, match="original owner"):
            svc.paid_receipt(viewer, identity)
    foreign = str(uuid4())
    with ledger.transaction() as c:
        c.execute(t.campaigns.insert().values(id=foreign, guild_id="999", revision=0))
        c.execute(
            t.members.insert().values(campaign_id=foreign, user_id="2", role="player", active=True)
        )
    other = ComfortService(
        GameService(
            OnboardingStore(
                ledger.engine,
                ledger.policy.model_copy(update={"campaign_id": foreign, "guild_id": 999}),
            )
        )
    )
    with pytest.raises(WorkflowError, match="original owner"):
        other.paid_receipt(GuildViewer(2, 999, True, True), identity)
    assert svc.paid_receipt(PLAYER, identity) == expected and game.dice.calls == 0


def test_paid_receipt_stays_owned_and_readable_after_character_change_pause_and_missing_registry(
    ledger, monkeypatch, tmp_path
):
    svc, game, identity = paid(ledger)
    expected = svc.paid_receipt(PLAYER, identity)
    ledger.safety(OTHER, "pause-paid-receipt", ledger.status(OTHER)["revision"], pause=True)
    ledger.policy = ledger.policy.model_copy(update={"m3_approval": None, "m2_approval": None})
    monkeypatch.setenv("GIRLFRAME_RULES_REGISTRY", str(tmp_path / "missing.json"))
    with ledger.transaction() as c:
        c.execute(
            t.characters.update()
            .where(t.characters.c.campaign_id == ledger.campaign_id, t.characters.c.user_id == "2")
            .values(id=str(uuid4()))
        )
    before = state(game)
    assert svc.paid_receipt(PLAYER, identity) == expected
    assert state(game) == before

    async def run():
        owner = current(2)
        await owner.response.defer(ephemeral=True)
        await open_requisitions(owner, RequisitionService(game))
        picker = owner.edit_original_response.call_args.kwargs["view"]
        assert picker.options == (("paid-comfort:" + identity, "Creature Comforts receipt"),)
        await picker.open_item(owner, "paid-comfort:" + identity)
        assert isinstance(owner.edit_original_response.call_args.kwargs["view"], PaidComfortPages)
        assert (
            "PRIVATE\\_PAID\\_COMFORT\\_REQUEST"
            in owner.edit_original_response.call_args.kwargs["content"]
        )

    asyncio.run(run())


@pytest.mark.parametrize("change", ("owner", "account", "source"))
def test_original_payment_source_cannot_be_substituted_for_another_receipt_or_reader(
    ledger, change
):
    svc, game, identity = paid(ledger)
    with ledger.transaction() as c:
        canon = state(game)
        receipt = canon.requisitions[0]
        updates = {
            "owner": {
                "actor": ActorRef(
                    kind="pilot", entity="3", incarnation=canon.sheets["3"].character_id
                )
            },
            "account": {"account": "FORGED_PAID_REQUEST"},
            "source": {"source_event": str(uuid4())},
        }[change]
        canon.requisitions[0] = receipt.model_copy(update=updates)
        game.event(c, 1, "synthetic-paid-receipt-corruption", "synthetic.state", canon)
    with pytest.raises(WorkflowError, match="SOURCE_PURCHASE_MISSING"):
        svc.paid_receipt(OTHER if change == "owner" else PLAYER, identity)


def test_native_waiting_paid_receipt_rechecks_membership_instead_of_using_cached_private_account(
    ledger,
):
    svc, game, identity = paid(ledger)

    async def run():
        owner = current(2)
        await owner.response.defer(ephemeral=True)
        await open_requisitions(owner, RequisitionService(game))
        picker = owner.edit_original_response.call_args.kwargs["view"]
        with ledger.transaction() as c:
            c.execute(
                t.members.update()
                .where(t.members.c.campaign_id == ledger.campaign_id, t.members.c.user_id == "2")
                .values(active=False)
            )
        await picker.open_item(owner, "paid-comfort:" + identity)
        assert "PRIVATE" not in owner.edit_original_response.call_args.kwargs["content"]

    asyncio.run(run())


def test_actual_qualified_opportunity_keeps_its_separate_paid_receipt_accessible(ledger):
    svc, _, game, _, receipts, _ = offered(ledger, faces=(6, 6))
    identity = receipts[0]["id"]
    result = svc.paid_receipt(PLAYER, identity)
    assert result["benefit_id"] is not None and result["state"] == "pending"
    before = state(game)

    async def run():
        owner = current(2)
        await owner.response.defer(ephemeral=True)
        await open_requisitions(owner, RequisitionService(game))
        picker = owner.edit_original_response.call_args.kwargs["view"]
        assert "paid-comfort:" + identity in dict(picker.options)
        assert "comfort:" + result["benefit_id"] in dict(picker.options)
        await picker.open_item(owner, "paid-comfort:" + identity)
        text = owner.edit_original_response.call_args.kwargs["content"]
        assert "Opportunity: pending" in text and "Waiting for your next" not in text

    asyncio.run(run())
    assert state(game) == before


def test_paid_receipt_long_escaped_request_is_complete_paginated_and_owned(ledger):
    svc, _, identity = paid(ledger, "*" * 1190 + "TAIL_MARK")

    async def run():
        owner = current(2)
        await owner.response.defer(ephemeral=True)
        view = PaidComfortPages(svc, 2, identity)
        assert not await view.interaction_check(current(3))
        await view.show(owner)
        assert len(owner.edit_original_response.call_args.kwargs["content"]) <= 2000
        await view.next.callback(owner)
        text = owner.edit_original_response.call_args.kwargs["content"]
        assert len(text) <= 2000 and "TAIL\\_MARK" in text

    asyncio.run(run())


def test_native_improvement_scene_can_use_a_city_and_complete_its_actual_asset_grant(ledger):
    svc, _, game, _, _, _ = offered(ledger, faces=(6, 6))
    identity = svc.list(PLAYER)[0]["id"]
    before = state(game)

    async def run():
        owner = current(2, 16201)
        owner.channel_id = 900
        await owner.response.defer(ephemeral=True)
        await open_comfort(owner, svc, identity)
        picker = owner.edit_original_response.call_args.kwargs["view"]
        await picker.open_item(owner, "scene")
        form = owner.edit_original_response.call_args.kwargs["view"]
        places = next(x.options for x in form.fields if x.key == "location")
        assert "city0" in dict(places)
        data = svc.get(PLAYER, identity, 900)
        role = next(
            x["token"]
            for x in data["roles"]
            if x["ref"]["kind"] == "pilot" and x["ref"]["entity"] == "2"
        )
        form.values.update(
            location=("city0",),
            participants=(role,),
            summary="PRIVATE_CITY_IMPROVEMENT",
            confirm=("yes",),
        )
        await form.confirm.callback(current(2, 16202))
        assert form.completed and svc.get(PLAYER, identity)["scene"]["location"] == "city0"
        await open_comfort(owner, svc, identity)
        grant = owner.edit_original_response.call_args.kwargs["view"]
        grant.values.update(
            name="PRIVATE_CITY_OUTFIT",
            description="An improvement from the actual city scene",
            confirm=("yes",),
        )
        await grant.confirm.callback(current(2, 16203))
        assert grant.completed and svc.get(PLAYER, identity)["taken"] is True

    asyncio.run(run())
    after = state(game)
    assert after.sheets["2"].assets[-1].name == "PRIVATE_CITY_OUTFIT"
    assert after.sheets["2"].permissions == before.sheets["2"].permissions
    assert after.placements == before.placements and after.world == before.world
