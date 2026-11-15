"""Guided confirmed edits persist through existing services; review stays explicit."""

import asyncio
from unittest.mock import AsyncMock

import sqlalchemy as sa
from test_creation_review import ready
from test_inbox import request
from test_ledger import OTHER, PLAYER, seed
from test_ledger import ledger as ledger

from girlframe.database import tables as t
from girlframe.discord_adapter.creation import AssetSelect, CreationView
from girlframe.discord_adapter.creation_review import ReviewView
from girlframe.discord_adapter.onboarding import DraftModal
from girlframe.engine.creation_catalog import CATALOG
from girlframe.services.creation import CreationService


def test_guided_profile_and_confirmed_assets_save_resume_and_refuse_stale(ledger, monkeypatch):
    from girlframe.discord_adapter import onboarding

    monkeypatch.setattr(onboarding, "allow_action", lambda *args, **kwargs: True)
    seed(ledger)

    async def run():
        profile_saved = AsyncMock()
        modal = DraftModal(
            ledger,
            PLAYER.user_id,
            ledger.draft(PLAYER),
            autosave=True,
            on_saved=profile_saved,
        )
        modal.callsign._value = "SORROW"
        modal.notes._value = "PRIVATE_GUIDED_CREATION"
        await modal.on_submit(request(PLAYER, 981001))
        profile_saved.assert_awaited_once()
        assert ledger.draft(PLAYER)["callsign"] == "SORROW"
        assert ledger.draft(PLAYER)["revision"] == 2

        service = CreationService(ledger)
        continued = AsyncMock()
        first = CreationView(
            service, PLAYER.user_id, service.get(PLAYER), autosave=True, on_saved=continued
        )
        await first.render(request(PLAYER, 981002))
        assert service.get(PLAYER).revision == 0  # Opening a step does not create progress.
        menu = next(x for x in first.children if isinstance(x, AssetSelect) and x.family == "girl")
        menu._values = list(CATALOG["MOCKINGBIRD"]["assets"][:2])
        await menu.callback(request(PLAYER, 981003))
        actual = service.get(PLAYER)
        assert actual.revision == 1
        assert tuple(x.name for x in actual.draft.girl_assets) == tuple(menu.values)
        assert actual.draft.frame_assets == ()  # An incomplete valid section is durable.
        continued.assert_not_awaited()

        resumed = CreationView(
            service, PLAYER.user_id, service.get(PLAYER), autosave=True, on_saved=continued
        )
        frame = next(
            x for x in resumed.children if isinstance(x, AssetSelect) and x.family == "frame"
        )
        frame._values = list(CATALOG["JANUS"]["assets"][:2])
        await frame.callback(request(PLAYER, 981004))
        assert service.get(PLAYER).revision == 2
        first.update(girl_appearance="A stale edit must not replace newer saved choices")
        rejected = request(PLAYER, 981005)
        await first.render(rejected)
        assert "STALE_REVISION" in rejected.edit_original_response.call_args.kwargs["content"]
        actual = service.get(PLAYER)
        assert actual.revision == 2 and actual.draft.girl_appearance == ""
        assert tuple(x.name for x in actual.draft.frame_assets) == tuple(frame.values)
        await resumed.save.callback(request(PLAYER, 981006))
        continued.assert_awaited_once()
        assert (
            service.get(PLAYER).revision == 2
        )  # Continue does not duplicate an autosaved revision.
        assert not await resumed.interaction_check(request(OTHER, 981007))

        # An acknowledged-local-write/unknown-result boundary cannot blindly resave.
        uncertain = CreationView(service, PLAYER.user_id, service.get(PLAYER), autosave=True)
        original_save, saves = service.save, []

        def lost_result(*args, **kwargs):
            saves.append(args)
            original_save(*args, **kwargs)
            raise TimeoutError("PRIVATE_STORAGE_FAILURE")

        monkeypatch.setattr(service, "save", lost_result)
        uncertain.update(frame_name="Saved despite unknown response")
        unknown = request(PLAYER, 981008)
        await uncertain.render(unknown)
        assert uncertain._save_uncertain
        assert "PRIVATE_STORAGE_FAILURE" not in str(unknown.edit_original_response.call_args)
        uncertain.update(frame_name="Must not overwrite until reopen")
        await uncertain.render(request(PLAYER, 981009))
        assert len(saves) == 1
        assert service.get(PLAYER).draft.frame_name == "Saved despite unknown response"

    asyncio.run(run())


def test_guided_review_only_continues_after_owned_explicit_current_save(ledger, monkeypatch):
    from girlframe.discord_adapter import onboarding

    monkeypatch.setattr(onboarding, "allow_action", lambda *args, **kwargs: True)
    service, _, _ = ready(ledger)

    async def run():
        continued = AsyncMock()
        view = ReviewView(service, PLAYER.user_id, on_saved=continued)
        await view.present(request(PLAYER, 982001))
        assert not service.get(PLAYER).saved_current
        continued.assert_not_awaited()
        control = view.save.custom_id
        await view.save.callback(request(OTHER, 982002, control))
        assert not service.get(PLAYER).saved_current
        continued.assert_not_awaited()
        await view.save.callback(request(PLAYER, 982003, "old-review-control"))
        assert not service.get(PLAYER).saved_current
        continued.assert_not_awaited()
        await view.save.callback(request(PLAYER, 982004, view.save.custom_id))
        continued.assert_awaited_once()
        assert service.get(PLAYER).saved_current
        with ledger.engine.connect() as connection:
            assert connection.scalar(sa.select(sa.func.count()).select_from(t.m2["m2_state"])) == 0

    asyncio.run(run())
