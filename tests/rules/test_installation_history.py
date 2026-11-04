"""Original paid Asset details survive changed sheets, without transferring authority."""

import asyncio
import json
from pathlib import Path
from uuid import uuid4

import pytest
import sqlalchemy as sa
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state
from test_mission_ui import current
from test_requisition_service import buy, ready

from girlframe.config import Settings
from girlframe.database import tables as t
from girlframe.database.connection import create_database_engine
from girlframe.database.maintenance import copy_database
from girlframe.discord_adapter.m3_requisitions import InstallationPages, open_requisitions
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_frame_state import FrameRuntime
from girlframe.engine.m3_requisition_state import Installation
from girlframe.services.m2_game import GameService
from girlframe.services.m3_requisitions import RequisitionService
from girlframe.services.onboarding import OnboardingStore, WorkflowError
from girlframe.services.read_only_bot import GuildViewer


def purchase(svc):
    return buy(
        svc,
        choice=Installation(
            name="PRIVATE_ORIGINAL_NAME",
            description="PRIVATE_ORIGINAL_DESCRIPTION",
            account="PRIVATE_ORIGINAL_ACCOUNT",
            trigger_confirmed=True,
        ),
    )["id"]


@pytest.mark.parametrize("change", ("asset", "frame", "profile", "character"))
def test_original_receipt_survives_change_without_granting_purchase_rights(ledger, change):
    svc, game = ready(ledger)
    identity = purchase(svc)
    original = svc.installation(PLAYER, identity)
    preview = svc.view(PLAYER)
    with ledger.transaction() as c:
        if change in ("profile", "character"):
            c.execute(
                t.characters.update()
                .where(
                    t.characters.c.campaign_id == ledger.campaign_id, t.characters.c.user_id == "2"
                )
                .values(
                    **(
                        {"revision": t.characters.c.revision + 1}
                        if change == "profile"
                        else {"id": str(uuid4())}
                    )
                )
            )
        else:
            canon = state(game)
            sheet = canon.sheets["2"]
            sheet.assets = [x for x in sheet.assets if x.id != original["receipt"]["asset_id"]]
            if change == "frame":
                sheet.frame_runtime = FrameRuntime(
                    id="new-frame", generation=1, source_work="synthetic-frame-source"
                )
            game.event(c, 1, "synthetic-owned-change", "synthetic.state", canon)
    before = state(game)
    assert svc.installation(PLAYER, identity) == original
    assert svc.installation_history(PLAYER) == [dict(id=identity, name="PRIVATE_ORIGINAL_NAME")]
    with pytest.raises(WorkflowError, match="STALE"):
        buy(svc, data=preview)
    assert state(game) == before and game.dice.calls == 0


def test_saved_installation_is_readable_when_paused_gates_revoked_and_registry_missing(
    ledger, monkeypatch, tmp_path
):
    svc, game = ready(ledger)
    identity = purchase(svc)
    original = svc.installation(PLAYER, identity)
    ledger.safety(OTHER, "pause-history", ledger.status(OTHER)["revision"], pause=True)
    ledger.policy = ledger.policy.model_copy(update={"m3_approval": None, "m2_approval": None})
    monkeypatch.setenv("GIRLFRAME_RULES_REGISTRY", str(tmp_path / "missing.json"))
    assert svc.installation(PLAYER, identity) == original
    assert len(svc.installation_history(PLAYER)) == 1
    before = state(game)
    with pytest.raises(WorkflowError):
        buy(svc)
    assert state(game) == before


def test_original_purchase_is_private_to_member_and_campaign_without_admin_override(ledger):
    svc, game = ready(ledger)
    identity = purchase(svc)
    for viewer in (OTHER, ADMIN):
        assert svc.installation_history(viewer) == []
        with pytest.raises(WorkflowError, match="original owner"):
            svc.installation(viewer, identity)
    foreign = str(uuid4())
    with ledger.transaction() as c:
        c.execute(t.campaigns.insert().values(id=foreign, guild_id="999", revision=0))
        c.execute(
            t.members.insert().values(campaign_id=foreign, user_id="2", role="player", active=True)
        )
    other = RequisitionService(
        GameService(
            OnboardingStore(
                ledger.engine,
                ledger.policy.model_copy(update={"campaign_id": foreign, "guild_id": 999}),
            )
        )
    )
    viewer = GuildViewer(2, 999, True, True)
    assert other.installation_history(viewer) == []
    with pytest.raises(WorkflowError, match="original owner"):
        other.installation(viewer, identity)
    with ledger.transaction() as c:
        c.execute(
            t.members.update()
            .where(t.members.c.campaign_id == ledger.campaign_id, t.members.c.user_id == "2")
            .values(active=False)
        )
    with pytest.raises(WorkflowError):
        svc.installation(PLAYER, identity)


@pytest.mark.parametrize("field", ("owner", "account", "source", "frame", "asset"))
def test_changed_receipt_cannot_forge_an_original_purchase_source_or_reader(ledger, field):
    svc, game = ready(ledger)
    identity = purchase(svc)
    with ledger.transaction() as c:
        canon = state(game)
        receipt = canon.requisitions[0]
        assert receipt.kind == "asset_installment"
        update = {
            "owner": {
                "actor": ActorRef(
                    kind="pilot", entity="3", incarnation=canon.sheets["3"].character_id
                )
            },
            "account": {
                "installation": receipt.installation.model_copy(
                    update={"account": "FORGED_ACCOUNT"}
                )
            },
            "source": {"source_event": str(uuid4())},
            "frame": {"frame_instance": "another-frame"},
            "asset": {"asset_id": "another-asset"},
        }[field]
        canon.requisitions[0] = receipt.model_copy(update=update)
        game.event(c, 1, "synthetic-receipt-corruption", "synthetic.state", canon)
    viewer = OTHER if field == "owner" else PLAYER
    with pytest.raises(WorkflowError, match="SOURCE_REQUISITION_MISSING"):
        svc.installation(viewer, identity)
    with pytest.raises(WorkflowError, match="SOURCE_REQUISITION_MISSING"):
        svc.installation_history(viewer)


def test_original_receipt_survives_backup_restore_and_canonical_rebuild_without_public_leak(
    ledger, tmp_path
):
    svc, game = ready(ledger)
    identity = purchase(svc)
    original = svc.installation(PLAYER, identity)
    assert "PRIVATE_ORIGINAL" not in json.dumps(ledger.public_export())
    with ledger.engine.connect() as c:
        assert "PRIVATE_ORIGINAL" not in str(list(c.scalars(sa.select(t.events.c.payload_json))))
        assert c.scalar(sa.select(sa.func.count()).select_from(t.m2["m2_outbox"])) == 0
    restored_path = tmp_path / "restored-installation.db"
    copy_database(Path(ledger.engine.url.database), restored_path)
    restored = create_database_engine(Settings(database_url="sqlite:///" + str(restored_path)))
    try:
        other_game = GameService(OnboardingStore(restored, ledger.policy))
        other = RequisitionService(other_game)
        assert other.installation(PLAYER, identity) == original
        with other_game.store.transaction() as c:
            c.execute(
                t.m2["m2_state"]
                .delete()
                .where(t.m2["m2_state"].c.campaign_id == ledger.campaign_id)
            )
        assert other_game.rebuild() > 0
        assert other.installation(PLAYER, identity) == original
    finally:
        restored.dispose()


def test_native_history_reopens_after_character_change_and_reads_each_page_with_current_authority(
    ledger,
):
    svc, game = ready(ledger)
    identity = purchase(svc)
    with ledger.transaction() as c:
        c.execute(
            t.characters.update()
            .where(t.characters.c.campaign_id == ledger.campaign_id, t.characters.c.user_id == "2")
            .values(id=str(uuid4()))
        )

    async def run():
        owner = current(2)
        await owner.response.defer(ephemeral=True)
        await open_requisitions(owner, svc)
        picker = owner.edit_original_response.call_args.kwargs["view"]
        assert not await picker.interaction_check(current(3))
        assert picker.options == ((identity, "PRIVATE_ORIGINAL_NAME"),)
        await picker.open_item(owner, identity)
        view = owner.edit_original_response.call_args.kwargs["view"]
        assert isinstance(view, InstallationPages) and not await view.interaction_check(current(3))
        text = owner.edit_original_response.call_args.kwargs["content"]
        assert "PRIVATE\\_ORIGINAL\\_NAME" in text and "JANUS-B" in text
        await view.next.callback(owner)
        assert (
            "PRIVATE\\_ORIGINAL\\_DESCRIPTION"
            in owner.edit_original_response.call_args.kwargs["content"]
        )
        await view.next.callback(owner)
        assert (
            "PRIVATE\\_ORIGINAL\\_ACCOUNT"
            in owner.edit_original_response.call_args.kwargs["content"]
        )
        with ledger.transaction() as c:
            c.execute(
                t.members.update()
                .where(t.members.c.campaign_id == ledger.campaign_id, t.members.c.user_id == "2")
                .values(active=False)
            )
        await view.previous.callback(owner)
        assert "PRIVATE" not in owner.edit_original_response.call_args.kwargs["content"]

    asyncio.run(run())
    assert game.dice.calls == 0


def test_native_receipt_preserves_long_escaped_account_in_discord_sized_pages(ledger):
    svc, game = ready(ledger)
    description, account = "*" * 700, "*" * 1190 + "TAIL_MARK"
    identity = buy(
        svc,
        choice=Installation(
            name="Long receipt", description=description, account=account, trigger_confirmed=True
        ),
    )["id"]

    async def run():
        owner = current(2)
        await owner.response.defer(ephemeral=True)
        view = InstallationPages(svc, 2, identity)
        shown = []
        for index in range(4):
            view.index = index
            await view.show(owner)
            text = owner.edit_original_response.call_args.kwargs["content"]
            assert len(text) <= 2000
            shown.append(text)
        assert "TAIL\\_MARK" in shown[-1]

    asyncio.run(run())
