"""Private reconstructable facilitator controls and audience-safe persistent notices."""

import asyncio
from typing import Any

import discord
from discord import app_commands

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.ledger import clean
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.m2_gateway import DiscordGameGateway
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine.p1_facilitator import Recipient
from girlframe.services.m2_game import GameService
from girlframe.services.onboarding import WorkflowError
from girlframe.services.p1_facilitator import FacilitatorService


async def open_request(interaction: discord.Interaction, game: GameService, identity: str) -> None:
    service = FacilitatorService(game)
    data = await asyncio.to_thread(service.view, viewer_from_interaction(interaction), identity)
    request = data["request"]
    if request["status"] in ("resolved", "declined"):
        saved_embeds = [
            discord.Embed(title=title, description=clean(request[key]) or "None recorded")
            for key, title in (("reason", "Original private request"), ("ruling", "Saved ruling"))
        ]
        if interaction.response.is_done():
            await interaction.edit_original_response(
                content="Saved adjudication: " + request["status"],
                embeds=saved_embeds,
                view=None,
                allowed_mentions=discord.AllowedMentions.none(),
            )
        else:
            await interaction.response.send_message(
                "Saved adjudication: " + request["status"],
                embeds=saved_embeds,
                ephemeral=True,
                allowed_mentions=discord.AllowedMentions.none(),
            )
        return
    actions = []
    if data["own"]:
        actions.append(("share", "Share my request text with the current facilitator"))
    if data["can_rule"]:
        actions.append(("rule", "Record a human ruling"))
    if request["status"] == "awaiting_owned_effect":
        actions.append(("resume", "Verify real source completion and resume"))
        if request["source_kind"] == "action":
            actions.append(("source", "Open my actual source choice"))
    if not request["mandatory"]:
        actions.append(("decline", "Decline this optional request"))
    if not actions:
        await reply(
            interaction, "Request is pending; configuration or original owner action is required."
        )
        return

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str | None:
        action = values["operation"][0]
        if action == "source":
            from girlframe.discord_adapter.m2_ui import open_choice

            rows = await asyncio.to_thread(game.choices, viewer_from_interaction(current))
            rows = [x for x in rows if x["action_id"] == request["source"]]
            if not rows:
                raise WorkflowError("You have no owned pending choice in this source.")
            await open_choice(current, game, rows[0]["id"])
            return None
        result = await asyncio.to_thread(
            service.change,
            viewer_from_interaction(current),
            str(current.id),
            identity,
            data["revision"],
            data["game_revision"],
            action,
            values.get("reason", ""),
            adapter=values.get("adapter", ("blocked",))[0],
        )
        return (
            "Saved: "
            + str(result["status"])
            + ". Finish the original required actions before resuming."
        )

    fields = [
        Field("operation", "Your own action", tuple(actions)),
        Field(
            "adapter",
            "For ruling/resume: effect route",
            (
                ("blocked", "Keep pending: mechanic unavailable"),
                ("existing_source", "Finish the original required choices"),
                ("fiction_only", "Scene note only; no sheet change"),
            ),
        ),
        Field("reason", "Your human ruling/reason", paragraph=True, required=False),
    ]
    form = NativeForm(
        interaction.user.id,
        "Human adjudication",
        "Request "
        + identity
        + "\n"
        + request["status"]
        + ". Actual owners retain all choices and consent.",
        fields,
        submit,
    )
    # Full private text is shown without NativeForm's short instruction rendering.
    embeds = [
        discord.Embed(title=title, description=clean(request[key]) or "None recorded")
        for key, title in (("reason", "Original request"), ("ruling", "Saved human ruling"))
    ]
    kwargs: dict[str, Any] = dict(
        content=form.text(),
        embeds=embeds,
        view=form,
        allowed_mentions=discord.AllowedMentions.none(),
    )
    if interaction.response.is_done():
        await interaction.edit_original_response(**kwargs)
    else:
        await interaction.response.send_message(**kwargs, ephemeral=True)


class NoticeButton(discord.ui.Button["Notice"]):
    def __init__(self, game: GameService, identity: str):
        super().__init__(label="Open private adjudication", custom_id="p1:ruling:" + identity)
        self.game, self.identity = game, identity

    async def callback(self, interaction: discord.Interaction) -> None:
        try:
            await interaction.response.defer(ephemeral=True)
            await open_request(interaction, self.game, self.identity)
        except WorkflowError as error:
            await reply(interaction, str(error))


class Notice(discord.ui.View):
    def __init__(self, game: GameService, identity: str):
        super().__init__(timeout=None)
        self.add_item(NoticeButton(game, identity))


class DiscordFacilitatorGateway(DiscordGameGateway):
    async def register_notice(self, message: int, request: str) -> None:
        self.guild._state._get_client().add_view(Notice(self.game, request), message_id=message)

    async def notice(self, channel: int, recipient: Recipient, request: str, nonce: str) -> int:
        resource = await self.channel(channel)
        if recipient.kind == "role":
            role = self.guild.get_role(recipient.id)
            if (
                role is None
                or role.is_default()
                or (
                    not role.mentionable
                    and (
                        self.guild.me is None
                        or not resource.permissions_for(self.guild.me).mention_everyone
                    )
                )
            ):
                raise WorkflowError(
                    "Configured facilitator role cannot be notified in this channel."
                )
            mention = f"<@&{recipient.id}>"
            allowed = discord.AllowedMentions(
                everyone=False, roles=[role], users=False, replied_user=False
            )
        else:
            member = self.guild.get_member(recipient.id) or await self.guild.fetch_member(
                recipient.id
            )
            if member.bot:
                raise WorkflowError("The facilitator must be an actual human.")
            mention = f"<@{recipient.id}>"
            allowed = discord.AllowedMentions(
                everyone=False, roles=False, users=[member], replied_user=False
            )
        embed = discord.Embed(
            description=(
                "A human adjudication request is pending. "
                "Private details stay in the authorized view."
            )
        )
        embed.set_footer(text="HarpyEngine facilitator:" + nonce)
        message = await resource.send(
            mention + " — Request `" + request + "`",
            embed=embed,
            view=Notice(self.game, request),
            allowed_mentions=allowed,
        )
        return message.id

    async def find_notice(self, channel: int, nonce: str) -> int | None:
        resource = await self.channel(channel)
        async for message in resource.history(limit=100):
            if (
                self.guild.me
                and message.author.id == self.guild.me.id
                and any(
                    embed.footer.text == "HarpyEngine facilitator:" + nonce
                    for embed in message.embeds
                )
            ):
                return message.id
        return None


def register_facilitator(tree: app_commands.CommandTree, guild_id: int, game: GameService) -> None:
    group = app_commands.Group(
        name="facilitator", description="Human adjudication and scoped resume"
    )
    service = FacilitatorService(game)

    @group.command(
        name="assign_user", description="Explicitly designate this campaign's human facilitator"
    )
    async def assign_user(interaction: discord.Interaction, user: discord.Member) -> None:
        await interaction.response.defer(ephemeral=True)
        try:
            if user.bot:
                raise WorkflowError("Choose an actual human facilitator.")
            await asyncio.to_thread(
                service.configure,
                viewer_from_interaction(interaction),
                str(interaction.id),
                "user",
                user.id,
            )
            await reply(
                interaction, "Human facilitator configured. Existing requests remain durable."
            )
        except WorkflowError as error:
            await reply(interaction, str(error))

    @group.command(
        name="assign_role", description="Explicitly designate the human facilitator role"
    )
    async def assign_role(interaction: discord.Interaction, role: discord.Role) -> None:
        await interaction.response.defer(ephemeral=True)
        try:
            if role.is_default() or role.managed:
                raise WorkflowError("Choose a specific human facilitator role.")
            await asyncio.to_thread(
                service.configure,
                viewer_from_interaction(interaction),
                str(interaction.id),
                "role",
                role.id,
            )
            await reply(
                interaction,
                "Human facilitator role configured; this grants no blanket private access.",
            )
        except WorkflowError as error:
            await reply(interaction, str(error))

    @group.command(name="inbox", description="Open your durable human-adjudication requests")
    async def inbox(interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        try:
            rows = await asyncio.to_thread(service.tasks, viewer_from_interaction(interaction))
            if not rows:
                await reply(interaction, "No pending human-adjudication requests.")
                return

            async def choose(current: discord.Interaction, values: dict[str, Any]) -> None:
                await open_request(current, game, values["request"][0])

            form = NativeForm(
                interaction.user.id,
                "Human adjudication inbox",
                "Choose your authorized request.",
                [Field("request", "Pending request", tuple((x["id"], x["label"]) for x in rows))],
                choose,
            )
            await reply(interaction, form.text(), form)
        except WorkflowError as error:
            await reply(interaction, str(error))

    @group.command(
        name="request", description="Ask for human handling of an actual scene or pending source"
    )
    async def request(interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        try:
            if interaction.channel_id is None:
                raise WorkflowError("Use an actual joined scene channel.")
            channel = interaction.channel_id
            data = await asyncio.to_thread(
                service.candidates, viewer_from_interaction(interaction), channel
            )

            async def create(current: discord.Interaction, values: dict[str, Any]) -> str:
                kind, identity = values["source"][0].split(":", 1)
                value = await asyncio.to_thread(
                    service.request,
                    viewer_from_interaction(current),
                    str(current.id),
                    channel,
                    kind,
                    identity,
                    values["rule"][0],
                    data["game_revision"],
                    values["reason"],
                    shared=values["shared"] == ("yes",),
                )
                return (
                    "Durable request saved: "
                    + str(value["id"])
                    + " ("
                    + str(value["status"])
                    + ")."
                )

            form = NativeForm(
                interaction.user.id,
                "Request human adjudication",
                (
                    "Select the actual source. Mandatory costs/results stay saved; "
                    "only your own request text may be shared."
                ),
                [
                    Field("source", "Actual affected source", tuple(data["sources"])),
                    Field("rule", "Inventoried rule", tuple(data["rules"])),
                    Field(
                        "shared",
                        "Share my request text with designated facilitator?",
                        (("no", "No: withhold details"), ("yes", "Yes: share my request")),
                    ),
                    Field("reason", "Why human handling is needed", paragraph=True),
                ],
                create,
            )
            await reply(interaction, form.text(), form)
        except WorkflowError as error:
            await reply(interaction, str(error))

    tree.add_command(group, guild=discord.Object(id=guild_id))


async def open_missing_source(
    interaction: discord.Interaction, game: GameService, kind: str, identity: str, selector: str
) -> None:
    """A real unsupported pending selector becomes durable work, not a generic error."""
    if interaction.channel_id is None:
        raise WorkflowError("Open this pending source in its actual relevant scene channel.")
    service = FacilitatorService(game)
    from girlframe.services.m2_state import load_state

    with game.store.engine.connect() as c:
        revision = load_state(c, game.store.campaign_id).revision
    created = await asyncio.to_thread(
        service.request,
        viewer_from_interaction(interaction),
        str(interaction.id) + ":unsupported",
        interaction.channel_id,
        kind,
        identity,
        selector,
        revision,
        (
            "The actual pending source has no supported automated selector. "
            "Human handling is required."
        ),
    )
    await open_request(interaction, game, created["id"])


async def open_missing_work(
    interaction: discord.Interaction, game: GameService, identity: str
) -> None:
    import sqlalchemy as sa

    from girlframe.database import tables as t

    with game.store.engine.connect() as c:
        table = t.m3["m3_required_work"]
        kind = c.scalar(
            sa.select(table.c.kind)
            .where(table.c.campaign_id == game.store.campaign_id, table.c.id == identity)
            .order_by(table.c.revision.desc())
            .limit(1)
        )
    if kind is None:
        raise WorkflowError("Recover the actual pending work source.")
    await open_missing_source(interaction, game, "work", identity, "work:" + kind)
