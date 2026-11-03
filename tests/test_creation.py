import asyncio
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import discord
import pytest
import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError
from test_ledger import OTHER, PLAYER, seed
from test_ledger import ledger as ledger_fixture

from girlframe.database import tables as t
from girlframe.discord_adapter.creation import CreationView, DetailsModal, summary
from girlframe.engine.creation import AssetChoice, CreationDraft, official_frame
from girlframe.engine.creation_catalog import CATALOG
from girlframe.engine.drafts import DraftInput
from girlframe.services.creation import CreationService
from girlframe.services.onboarding import OnboardingStore, WorkflowError
from girlframe.services.read_only_bot import GuildViewer

ledger = ledger_fixture


def selected(girl="MOCKINGBIRD", frame="JANUS-B"):
    return CreationDraft(
        girl_playbook=girl,
        frame_playbook=frame,
        girl_assets=tuple(
            AssetChoice(name=a, description="Synthetic description")
            for a in CATALOG[girl]["assets"][:2]
        )
        if girl != "BONDED"
        else (),
        frame_assets=tuple(
            AssetChoice(name=a, description="Synthetic frame asset")
            for a in CATALOG[official_frame(frame)]["assets"][:2]
        ),
        void_asset=CATALOG[girl]["assets"][0] if girl == "MOCKINGBIRD" else None,
        frame_name="Synthetic Frame",
        girl_appearance="Synthetic pilot",
        frame_appearance="Synthetic frame",
    )


@pytest.mark.parametrize("girl", [k for k, v in CATALOG.items() if v["family"] == "girl"])
def test_source_catalog_and_starting_identities(girl):
    data = selected(girl)
    assert len(data.identities) == 4 and len(set(data.identities)) == 4
    assert len(CATALOG[girl]["assets"]) == 5
    assert CATALOG[girl]["book_printed_page"] == CATALOG[girl]["book_pdf_page"] - 2
    if girl != "BONDED":
        assert data.missing() == []
    else:
        assert any("Pair-owned" in item for item in data.missing())


@pytest.mark.parametrize(
    "frame", [k for k, v in CATALOG.items() if v["family"] == "frame"] + ["JANUS-B"]
)
def test_frame_assets_and_owner_approved_janus_alias(frame):
    data = selected(frame=frame)
    assert len(data.frame_assets) == 2 and len(CATALOG[official_frame(frame)]["assets"]) == 9
    assert data.intrinsic_frame_assets == (("Enormous",) if frame == "WYVERN 0.4" else ())
    assert data.frame_playbook == frame


def test_invalid_assets_duplicates_void_and_pair_authority():
    base = selected().model_dump()
    for change in [
        {"girl_assets": (AssetChoice(name="Invented Asset"),)},
        {"girl_assets": (base["girl_assets"][0], base["girl_assets"][0])},
        {"frame_assets": (AssetChoice(name="Enormous"),)},
        {"void_asset": "not selected"},
        {"girl_playbook": "BONDED"},
    ]:
        with pytest.raises(ValueError):
            CreationDraft.model_validate(base | change)
    blank = CreationDraft(girl_playbook="MOCKINGBIRD", frame_playbook="JANUS-B")
    assert "one selected Girl Asset altered by the Void" in blank.missing()
    assert not hasattr(blank, "heat") and not hasattr(blank, "status")


def test_owner_save_restart_history_and_private_audit(ledger):
    seed(ledger)
    service = CreationService(ledger)
    initial = service.get(PLAYER)
    data = selected().model_copy(update={"girl_appearance": "CREATION_PRIVATE_CANARY"})
    saved = service.save(PLAYER, "creation", 0, initial.character_revision, data)
    assert saved == service.save(PLAYER, "creation", 0, initial.character_revision, data)
    restarted = CreationService(OnboardingStore(ledger.engine, ledger.policy))
    assert restarted.get(PLAYER).draft == data
    with ledger.engine.connect() as connection:
        assert connection.scalar(sa.select(sa.func.count()).select_from(t.creation_drafts)) == 1
        assert all(
            "CREATION_PRIVATE_CANARY" not in row
            for row in connection.execute(sa.select(t.events.c.payload_json)).scalars()
        )
    assert ledger.draft(PLAYER)["status"] == "draft_rules_unverified"
    ledger.join(OTHER, "join-other")
    with pytest.raises(WorkflowError):
        service.get(OTHER)
    with pytest.raises(WorkflowError, match="IDEMPOTENCY_CONFLICT"):
        service.save(PLAYER, "creation", 0, initial.character_revision, selected())
    with ledger.engine.begin() as connection:
        with pytest.raises(IntegrityError):
            connection.execute(t.creation_drafts.delete())


def test_stale_profile_concurrency_and_two_campaign_isolation(ledger):
    seed(ledger)
    service = CreationService(ledger)
    initial = service.get(PLAYER)

    def save(key):
        try:
            return service.save(PLAYER, key, 0, initial.character_revision, selected())
        except WorkflowError as e:
            return str(e)

    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(save, ["a", "b"]))
    assert sum(isinstance(r, dict) for r in results) == 1
    assert any("STALE_REVISION" in r for r in results if isinstance(r, str))
    ledger.save_draft(
        PLAYER,
        "changed-profile",
        1,
        DraftInput(callsign="SYNTH", girl_playbook="PRINCESS", frame_playbook="THE PRINCE"),
    )
    assert service.get(PLAYER).playbooks_changed
    assert service.get(PLAYER).draft.girl_assets == ()
    with pytest.raises(WorkflowError, match="STALE_REVISION"):
        service.save(PLAYER, "stale", 1, initial.character_revision, selected())
    other = OnboardingStore(
        ledger.engine, ledger.policy.model_copy(update={"guild_id": 300, "campaign_id": uuid4()})
    )
    viewer = GuildViewer(2, 300, True, False)
    seed(other, viewer)
    assert CreationService(other).get(viewer).revision == 0
    assert len(service.get(PLAYER).draft.identities) == 4


def test_native_wizard_restores_choices_and_rejects_other_owner(ledger):
    seed(ledger)
    service = CreationService(ledger)
    service.save(PLAYER, "initial", 0, service.get(PLAYER).character_revision, selected())

    async def run():
        view = CreationView(service, PLAYER.user_id, service.get(PLAYER))
        girl = next(x for x in view.children if isinstance(x, discord.ui.Select) and x.row == 0)
        assert sum(option.default for option in girl.options) == 2
        assert len(view.children) <= 25
        assert len(DetailsModal(view, assets=True).children) == 4
        assert "not activated" in summary(view.draft)
        request = MagicMock()
        request.user.id = OTHER.user_id
        request.response.is_done.return_value = True
        request.edit_original_response = AsyncMock()
        assert not await view.interaction_check(request)
        assert "another player" in request.edit_original_response.call_args.kwargs["content"]

    asyncio.run(run())


def test_creation_rollback_revocation_and_private_backup(ledger, monkeypatch, tmp_path):
    from pathlib import Path

    from girlframe.config import Settings
    from girlframe.database.connection import create_database_engine
    from girlframe.database.maintenance import copy_database

    seed(ledger)
    service = CreationService(ledger)
    initial = service.get(PLAYER)
    original = ledger._audit

    def fail_after_event(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError("Synthetic transaction failure")

    with monkeypatch.context() as patch:
        patch.setattr(ledger, "_audit", fail_after_event)
        with pytest.raises(RuntimeError):
            service.save(PLAYER, "retry", 0, initial.character_revision, selected())
    assert service.get(PLAYER).revision == 0
    with ledger.engine.connect() as connection:
        assert not connection.execute(
            sa.select(t.commands).where(t.commands.c.interaction_key == "retry")
        ).first()
        assert not connection.execute(
            sa.select(t.events).where(t.events.c.kind == "character.creation_saved")
        ).first()
    service.save(PLAYER, "retry", 0, initial.character_revision, selected())
    backup = tmp_path / "creation-backup.db"
    copy_database(Path(ledger.engine.url.database), backup)
    restored = create_database_engine(Settings(database_url=f"sqlite:///{backup}"))
    try:
        assert (
            CreationService(OnboardingStore(restored, ledger.policy)).get(PLAYER).draft
            == selected()
        )
    finally:
        restored.dispose()
    assert "girl_assets" not in str(ledger.public_export())
    with ledger.engine.begin() as connection:
        connection.execute(t.members.update().values(active=False))
    for operation in [
        lambda: service.get(PLAYER),
        lambda: service.save(PLAYER, "retry", 0, initial.character_revision, selected()),
    ]:
        with pytest.raises(WorkflowError):
            operation()


def test_builder_save_callback_and_stale_modal(ledger, monkeypatch):
    from girlframe.discord_adapter import onboarding

    monkeypatch.setattr(onboarding, "allow_action", lambda *a, **kw: True)
    seed(ledger)
    service = CreationService(ledger)

    def interaction(identity):
        request = MagicMock()
        request.user = MagicMock(spec=discord.Member)
        request.user.id = PLAYER.user_id
        request.user.guild_permissions = discord.Permissions.none()
        request.guild_id, request.id = 200, identity
        request.response.is_done.return_value = True
        request.response.defer = AsyncMock()
        request.edit_original_response = AsyncMock()
        return request

    async def run():
        view = CreationView(service, PLAYER.user_id, service.get(PLAYER))
        view.update(**selected().model_dump(mode="json"))
        modal = DetailsModal(view, assets=False)
        view.update(frame_name="Revised Frame")
        request = interaction(101)
        await modal.on_submit(request)
        assert "Choices changed" in request.edit_original_response.call_args.kwargs["content"]
        assert view.draft.frame_name == "Revised Frame"
        save = interaction(102)
        await view.save.callback(save)
        save.response.defer.assert_awaited_once_with(ephemeral=True, thinking=True)
        assert service.get(PLAYER).draft.frame_name == "Revised Frame"
        assert "Progress saved" in save.edit_original_response.call_args.kwargs["content"]
        # The reopened view comes from storage; a second edit appends a revision.
        reopened = CreationView(service, PLAYER.user_id, service.get(PLAYER))
        assert reopened.draft == view.draft
        reopened.update(frame_name="Second Revision")
        await reopened.save.callback(interaction(103))
        assert service.get(PLAYER).revision == 2
        assert service.get(PLAYER).draft.frame_name == "Second Revision"
        # A still-open first view cannot overwrite the later revision.
        stale = interaction(104)
        await view.save.callback(stale)
        assert "STALE_REVISION" in stale.edit_original_response.call_args.kwargs["content"]
        # Provider/domain errors never include submitted content in fallback replies.
        error = interaction(105)
        await view.on_error(error, ValueError("PRIVATE_CANARY"), view.save)
        assert "PRIVATE_CANARY" not in str(error.edit_original_response.call_args)

    asyncio.run(run())
