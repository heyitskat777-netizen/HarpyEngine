"""Private, owner-confirmed creation-file exchange; services own all persistence."""

import asyncio
from io import BytesIO
from typing import Any, Literal, cast
from uuid import uuid4

import discord
from discord import app_commands

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.member_names import resolve_member_names
from girlframe.discord_adapter.onboarding import action_gate, reply
from girlframe.engine.character_documents import (
    MAX_DOCUMENT_BYTES,
    CharacterSheetDocument,
    encode_document,
)
from girlframe.serialization.character_sheet_html import render_sheet
from girlframe.services.character_transfer import CharacterTransferService, ImportPreview
from girlframe.services.onboarding import WorkflowError

MAX_IMPORT_BYTES = MAX_DOCUMENT_BYTES
MAX_EXPORT_BYTES = 7 * 1024 * 1024


def clean(value: str) -> str:
    return discord.utils.escape_markdown(discord.utils.escape_mentions(value))


def preview_pages(preview: ImportPreview) -> list[str]:
    profile = preview.document.profile
    lines = [
        f"**{clean(profile.callsign)}** · {clean(profile.girl_playbook)} / "
        + clean(profile.frame_playbook),
        "Confirming saves an editable draft. Profile changes schedule the usual "
        "role/nickname sync. "
        "Review, other-player agreements and activation remain separate.",
        "\n**Changed fields**",
        *("• " + clean(path) for path in preview.changes),
        *("\n" + clean(warning) for warning in preview.warnings),
    ]
    if not preview.changes:
        lines.insert(3, "No editable field differences; confirmation records this draft import.")
    rendered = "\n".join(lines)
    return [rendered[i : i + 3500] for i in range(0, len(rendered), 3500)] or [""]


class ImportConfirmation(discord.ui.View):
    def __init__(
        self, service: CharacterTransferService, guild_id: int, owner: int, preview: ImportPreview
    ):
        super().__init__(timeout=600)
        self.service, self.guild_id, self.owner, self.preview = service, guild_id, owner, preview
        self.command_key = "character-import:" + uuid4().hex
        self.pages, self.page = preview_pages(preview), 0
        self._busy, self._finished, self._uncertain = False, False, False

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner or interaction.guild_id != self.guild_id:
            await reply(interaction, "This private import belongs to another member or server.")
            return False
        if self._finished:
            await reply(
                interaction, "This import is finished. Reopen /start to read saved progress."
            )
            return False
        if self._uncertain:
            await reply(
                interaction,
                "This import's outcome is unknown. Check /start or /character review "
                "before importing again.",
            )
            return False
        if self._busy:
            await reply(interaction, "This import is being saved. Please wait.")
            return False
        try:
            await asyncio.to_thread(self.service.authorize, viewer_from_interaction(interaction))
            if self._busy or self._finished or self._uncertain:
                await reply(
                    interaction, "This import is already being saved or needs a fresh preview."
                )
                return False
            return True
        except WorkflowError as error:
            await reply(interaction, str(error))
            return False

    async def present(self, interaction: discord.Interaction) -> None:
        if not await self.interaction_check(interaction):
            return
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True)
        self.previous.disabled = self.page == 0
        self.next.disabled = self.page == len(self.pages) - 1
        embed = discord.Embed(
            title=f"Import creation draft — review {self.page + 1}/{len(self.pages)}",
            description=self.pages[self.page],
            color=0x9F96FF,
        )
        await interaction.edit_original_response(
            content=None, embed=embed, view=self, allowed_mentions=discord.AllowedMentions.none()
        )

    async def on_error(
        self, interaction: discord.Interaction, error: Exception, item: discord.ui.Item[Any]
    ) -> None:
        await reply(
            interaction,
            "Import unavailable. Check /start for saved progress before opening a fresh preview.",
        )

    @discord.ui.button(label="Previous", row=0)
    async def previous(
        self, interaction: discord.Interaction, button: discord.ui.Button[Any]
    ) -> None:
        if await self.interaction_check(interaction):
            self.page = max(0, self.page - 1)
            await self.present(interaction)

    @discord.ui.button(label="Next", row=0)
    async def next(self, interaction: discord.Interaction, button: discord.ui.Button[Any]) -> None:
        if await self.interaction_check(interaction):
            self.page = min(len(self.pages) - 1, self.page + 1)
            await self.present(interaction)

    @discord.ui.button(label="Confirm draft import", style=discord.ButtonStyle.success, row=1)
    async def confirm(
        self, interaction: discord.Interaction, button: discord.ui.Button[Any]
    ) -> None:
        if not await self.interaction_check(interaction) or not await action_gate(
            interaction, "metadata"
        ):
            return
        if self._busy or self._finished or self._uncertain:
            await reply(interaction, "This import is already being saved or needs a fresh preview.")
            return
        self._busy = True
        started, known = False, False
        try:
            await interaction.response.defer(ephemeral=True, thinking=True)
            started = True
            try:
                result = await asyncio.to_thread(
                    self.service.apply,
                    viewer_from_interaction(interaction),
                    self.command_key,
                    self.preview,
                )
            except WorkflowError as error:
                known = True
                await reply(interaction, str(error))
                return
            except Exception:
                await reply(
                    interaction,
                    "Could not confirm this import's outcome. Check /start or /character review "
                    "before importing again.",
                )
                return
            known, self._finished = True, True
            self.stop()
            await interaction.edit_original_response(
                content="Imported as an editable draft. "
                f"Profile revision {result.get('profile_revision', 'saved')}; "
                f"creation revision {result.get('creation_revision', 'saved')}. "
                "Use /start to continue, then save a fresh /character review. "
                "Activation and other people's consent remain separate.",
                embed=None,
                view=None,
                allowed_mentions=discord.AllowedMentions.none(),
            )
        finally:
            if started and not known:
                self._uncertain = True
            self._busy = False

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary, row=1)
    async def cancel(
        self, interaction: discord.Interaction, button: discord.ui.Button[Any]
    ) -> None:
        if not await self.interaction_check(interaction):
            return
        self._finished = True
        self.stop()
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True)
        await interaction.edit_original_response(
            content="Import cancelled. No draft changes were saved.",
            embed=None,
            view=None,
            allowed_mentions=discord.AllowedMentions.none(),
        )


async def named_snapshot(
    interaction: discord.Interaction, document: CharacterSheetDocument
) -> CharacterSheetDocument:
    ids = {int(document.owner_id)}
    ids.update(int(key) for key in document.members if key.isdecimal())
    for bond in document.sheet.get("bonds", []):
        identity = str(bond.get("counterpart_id", ""))
        if identity.isdecimal():
            ids.add(int(identity))
    names = await resolve_member_names(interaction, ids)
    return document.model_copy(
        update={
            "display_name": names.get(int(document.owner_id), "Unavailable member"),
            "members": {str(key): value for key, value in names.items()},
        }
    )


def register_character_transfer(
    tree: app_commands.CommandTree,
    guild_id: int,
    service: CharacterTransferService,
) -> None:
    character = tree.get_command("character", guild=discord.Object(id=guild_id))
    assert isinstance(character, app_commands.Group)

    @character.command(
        name="import", description="Privately preview and confirm a creation JSON file"
    )
    async def import_character(
        interaction: discord.Interaction, document: discord.Attachment
    ) -> None:
        if not await action_gate(interaction, "metadata"):
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        viewer = viewer_from_interaction(interaction)
        try:
            await asyncio.to_thread(service.authorize, viewer)
            if not document.filename.lower().endswith(".json"):
                raise WorkflowError("Upload a HarpyEngine creation .json file.")
            if not 0 < document.size <= MAX_IMPORT_BYTES:
                raise WorkflowError("Creation JSON must be nonempty and at most 256 KiB.")
            raw = await document.read()
            if not 0 < len(raw) <= MAX_IMPORT_BYTES:
                raise WorkflowError("Creation JSON must be nonempty and at most 256 KiB.")
            preview = await asyncio.to_thread(service.preview, viewer, raw)
            await ImportConfirmation(service, guild_id, viewer.user_id, preview).present(
                interaction
            )
        except WorkflowError as error:
            await reply(interaction, str(error))
        except (ValueError, UnicodeError):
            await reply(
                interaction,
                "Invalid or unsupported creation JSON. Use the HarpyEngine character-draft "
                "schema; current-sheet snapshots cannot be imported as creation drafts.",
            )
        except discord.HTTPException:
            await reply(interaction, "Could not read that attachment. Upload the JSON file again.")
        except Exception:
            await reply(interaction, "Could not prepare this preview. Reopen /start and try again.")

    @character.command(
        name="export", description="Privately download a template or authorized sheet"
    )
    @app_commands.choices(
        format=[
            app_commands.Choice(name="Importable creation template (JSON)", value="template"),
            app_commands.Choice(name="Current sheet snapshot (JSON)", value="sheet"),
            app_commands.Choice(name="Printable current sheet (HTML)", value="html"),
        ],
        audience=[
            app_commands.Choice(name="Owner view", value="owner"),
            app_commands.Choice(name="Approved public fields", value="public"),
        ],
    )
    @app_commands.describe(
        format="Choose an importable template or read-only sheet download",
        audience="Choose owner data or approved public fields; the download stays private",
        include_private="Include personal notes (owner exports only)",
        member="Omit for yourself; another member can only be exported with public audience",
    )
    async def export_character(
        interaction: discord.Interaction,
        format: str = "template",
        audience: str = "owner",
        include_private: bool = False,
        member: discord.Member | None = None,
    ) -> None:
        if not await action_gate(interaction, "sheet_export"):
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        viewer = viewer_from_interaction(interaction)
        try:
            await asyncio.to_thread(service.authorize, viewer)
            if audience not in {"owner", "public"} or format not in {"template", "sheet", "html"}:
                raise WorkflowError("Choose a supported export format and audience.")
            if include_private and audience != "owner":
                raise WorkflowError("Private notes require an owner-view export.")
            owner = member.id if member is not None else viewer.user_id
            if format == "template":
                if owner != viewer.user_id or audience != "owner":
                    raise WorkflowError("Creation templates are private exports of your own draft.")
                template = await asyncio.to_thread(
                    service.template, viewer, include_private=include_private
                )
                payload, filename = encode_document(template), "harpyengine-character-draft-v1.json"
            else:
                snapshot = await asyncio.to_thread(
                    service.snapshot,
                    viewer,
                    audience=cast(Literal["owner", "public"], audience),
                    owner=owner,
                    include_private=include_private,
                )
                snapshot = await named_snapshot(interaction, snapshot)
                payload = (
                    render_sheet(snapshot).encode("utf-8")
                    if format == "html"
                    else encode_document(snapshot)
                )
                filename = "harpyengine-character-sheet-v1." + (
                    "html" if format == "html" else "json"
                )
            if len(payload) > MAX_EXPORT_BYTES:
                raise WorkflowError(
                    "This export exceeds the download limit; no data was truncated."
                )
            await interaction.edit_original_response(
                content="Your private download is ready. "
                + (
                    "This creation template can be imported as a draft."
                    if format == "template"
                    else "This sheet is a read-only snapshot, not an activation or state import."
                ),
                attachments=[discord.File(BytesIO(payload), filename=filename)],
                allowed_mentions=discord.AllowedMentions.none(),
            )
        except WorkflowError as error:
            await reply(interaction, str(error))
        except ValueError:
            await reply(interaction, "This character cannot be exported in the selected format.")
        except Exception:
            await reply(interaction, "Could not prepare this export. Reopen the command to retry.")
