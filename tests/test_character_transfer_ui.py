"""Private native file transport; engine transaction tests live in the service suite."""

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import discord
from discord import app_commands
from test_ledger import OTHER, PLAYER
from test_start_dashboard_ui import current

from girlframe import __version__
from girlframe.discord_adapter.character_transfer import (
    MAX_IMPORT_BYTES,
    ImportConfirmation,
    register_character_transfer,
)
from girlframe.engine.character_documents import CharacterSheetDocument
from girlframe.services.onboarding import WorkflowError


class TransferFake:
    def __init__(self):
        self.denied = False
        self.applied = []
        self.previews = []
        self.snapshots = []
        self.error = None
        self.preview_result = SimpleNamespace(
            document=SimpleNamespace(
                profile=SimpleNamespace(
                    callsign="SYNTH", girl_playbook="MOCKINGBIRD", frame_playbook="JANUS-B"
                )
            ),
            changes=("profile.callsign", "creation.girl_assets"),
            warnings=("Review and activation remain separate.",),
        )

    def authorize(self, viewer):
        if self.denied or not viewer.is_member or viewer.guild_id != 200:
            raise WorkflowError("This action is unavailable here.")

    def preview(self, viewer, raw):
        self.authorize(viewer)
        self.previews.append(raw)
        if self.error:
            raise self.error
        return self.preview_result

    def apply(self, viewer, key, preview):
        self.authorize(viewer)
        self.applied.append((viewer, key, preview))
        return {"profile_revision": 1, "creation_revision": 1}

    def snapshot(self, viewer, *, audience, owner, include_private):
        self.authorize(viewer)
        self.snapshots.append((audience, owner, include_private))
        sheet = {"callsign": "SYNTH", "girl_playbook": "MOCKINGBIRD", "frame_playbook": "JANUS-B"}
        if audience == "owner":
            sheet.update(
                heat=2, bonds=[{"counterpart_id": "3", "depth": "Personal", "context": "shared"}]
            )
            if include_private:
                sheet["private_notes"] = "SYNTH_PRIVATE_CANARY"
        return CharacterSheetDocument(
            engine_version=__version__,
            audience=audience,
            owner_id=str(owner),
            character_id="synthetic-character",
            revision=1,
            sheet=sheet,
        )


def attachment(raw=b'{"format":"harpyengine.character-draft","schema_version":1}'):
    result = MagicMock(spec=discord.Attachment)
    result.filename, result.size = "synthetic.json", len(raw)
    result.read = AsyncMock(return_value=raw)
    return result


async def registered(service):
    client = discord.Client(intents=discord.Intents.none())
    tree = app_commands.CommandTree(client)
    group = app_commands.Group(name="character", description="Synthetic existing character group")
    tree.add_command(group, guild=discord.Object(id=200))
    register_character_transfer(tree, 200, service)
    return client, tree, group


def test_native_import_preview_explicit_owner_confirmation_and_single_submission(monkeypatch):
    from girlframe.discord_adapter import onboarding

    monkeypatch.setattr(onboarding, "allow_action", lambda *args, **kwargs: True)
    service = TransferFake()

    async def run():
        client, tree, group = await registered(service)
        async with client:
            assert not tree.get_commands()
            assert {x.name for x in group.commands} == {"import", "export"}
            group.to_dict(tree)
            opening = current(PLAYER, 920001)
            uploaded = attachment()
            await group.get_command("import").callback(opening, uploaded)
            opening.response.defer.assert_awaited_once_with(ephemeral=True, thinking=True)
            rendered = opening.edit_original_response.call_args.kwargs
            view = rendered["view"]
            assert isinstance(view, ImportConfirmation) and not service.applied
            assert (
                rendered["allowed_mentions"].to_dict() == discord.AllowedMentions.none().to_dict()
            )
            await view.confirm.callback(current(OTHER, 920002))
            assert not service.applied
            other_guild = current(PLAYER, 920003)
            other_guild.guild_id = 201
            assert not await view.interaction_check(other_guild)
            confirmed = current(PLAYER, 920004)
            await view.confirm.callback(confirmed)
            assert len(service.applied) == 1 and service.applied[0][1] == view.command_key
            assert (
                "Imported as an editable draft"
                in confirmed.edit_original_response.call_args.kwargs["content"]
            )
            assert confirmed.edit_original_response.call_args.kwargs["embed"] is None
            await view.confirm.callback(current(PLAYER, 920005))
            assert len(service.applied) == 1
            assert view._finished

    asyncio.run(run())


def test_attachment_auth_size_recheck_and_parser_errors_are_private(monkeypatch):
    from girlframe.discord_adapter import onboarding

    monkeypatch.setattr(onboarding, "allow_action", lambda *args, **kwargs: True)
    service = TransferFake()

    async def run():
        client, _, group = await registered(service)
        async with client:
            command = group.get_command("import")
            service.denied = True
            blocked = attachment()
            await command.callback(current(PLAYER, 921001), blocked)
            blocked.read.assert_not_awaited()
            service.denied = False
            oversized = attachment(b"x" * (MAX_IMPORT_BYTES + 1))
            oversized.size = 1
            await command.callback(current(PLAYER, 921002), oversized)
            assert not service.previews
            service.error = ValueError("SYNTH_PRIVATE_PARSER_CANARY")
            bad = current(PLAYER, 921003)
            await command.callback(bad, attachment())
            response = bad.edit_original_response.call_args.kwargs
            assert "Invalid or unsupported" in response["content"]
            assert "CANARY" not in response["content"] and not service.applied
            service.error = None
            opening = current(PLAYER, 921004)
            await command.callback(opening, attachment())
            view = opening.edit_original_response.call_args.kwargs["view"]
            service.denied = True
            await view.confirm.callback(current(PLAYER, 921005))
            assert not service.applied

    asyncio.run(run())


def test_native_export_filters_audience_and_annotates_current_member_names(monkeypatch):
    from girlframe.discord_adapter import onboarding

    monkeypatch.setattr(onboarding, "allow_action", lambda *args, **kwargs: True)
    service = TransferFake()

    async def run():
        client, _, group = await registered(service)
        async with client:
            command = group.get_command("export")
            private = current(PLAYER, 922001)
            await command.callback(private, "sheet", "owner", False)
            result = private.edit_original_response.call_args.kwargs
            exported = json.loads(result["attachments"][0].fp.read())
            assert exported["display_name"] == "SORROW"
            assert exported["members"]["3"] == "Current server nickname"
            assert exported["owner_id"] == "2" and exported["sheet"]["heat"] == 2
            assert "private_notes" not in exported["sheet"]
            assert result["allowed_mentions"].to_dict() == discord.AllowedMentions.none().to_dict()
            public = current(PLAYER, 922002)
            await command.callback(public, "sheet", "public", False)
            exported = json.loads(
                public.edit_original_response.call_args.kwargs["attachments"][0].fp.read()
            )
            assert exported["audience"] == "public"
            assert "heat" not in exported["sheet"] and "bonds" not in exported["sheet"]
            assert service.snapshots[-1] == ("public", 2, False)
            calls = len(service.snapshots)
            rejected = current(PLAYER, 922003)
            await command.callback(rejected, "sheet", "public", True)
            assert len(service.snapshots) == calls
            assert "Private notes" in rejected.edit_original_response.call_args.kwargs["content"]

    asyncio.run(run())
