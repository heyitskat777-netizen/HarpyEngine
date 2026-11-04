"""Native private mission offers and explicit player/Handler transitions."""

import asyncio
from typing import Any, cast

import discord
from discord import app_commands

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.ledger import clean
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import private_operation, reply
from girlframe.services.handler_setup import HandlerService
from girlframe.services.m3_missions import MissionService
from girlframe.services.onboarding import WorkflowError


def details(data: dict[str, Any]) -> str:
    mission = data["mission"]
    lines = [
        "**Mission — " + clean(mission["phase"].replace("_", " ")) + "**",
        clean(mission["objective"]),
        "Revision "
        + str(mission["revision"])
        + " · pending required work: "
        + str(data["pending_count"]),
    ]
    lines += [
        "Player " + str(uid) + ": " + mission["responses"].get(str(uid), "awaiting response")
        for uid in mission["offered_to"]
    ]
    if mission["success"] is not None:
        lines.append("Outcome: " + ("success" if mission["success"] else "failure"))
    lines.append("Mission `" + mission["id"] + "`")
    return "\n".join(lines)[:1800]


async def open_mission(
    interaction: discord.Interaction, service: MissionService, identity: str
) -> None:
    viewer = viewer_from_interaction(interaction)
    data = await asyncio.to_thread(service.get, viewer, identity)
    mission = data["mission"]
    actions = []
    if (
        mission["phase"] == "offered"
        and viewer.user_id in mission["offered_to"]
        and str(viewer.user_id) not in mission["responses"]
    ):
        actions.extend([("accept", "Accept the offer"), ("decline", "Decline the offer")])
    with service.store.engine.connect() as c:
        current_handler = HandlerService(service.store).current(c)[1].handler_id
    if current_handler == viewer.user_id:
        if (
            mission["phase"] == "offered"
            and len(mission["responses"]) == len(mission["offered_to"])
            and "accept" in mission["responses"].values()
        ):
            actions.append(("start", "Dispatch accepted participants"))
        elif mission["phase"] == "active":
            actions.extend(
                [
                    ("end_success", "Record mission success"),
                    ("end_failure", "Record mission failure"),
                ]
            )
        elif mission["phase"] in ("ending", "awaiting_consequences") and data["pending_count"] == 0:
            actions.append(("advance", "Advance resolved mission work"))
    if not actions:
        await reply(interaction, details(data) + "\nReopen /mission inbox to refresh.")
        return

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        actor = viewer_from_interaction(current)
        operation = values["action"][0]
        if operation not in {value for value, _ in actions}:
            raise WorkflowError("Choose an action from this current mission view.")
        key = str(current.id)
        if operation in ("accept", "decline"):
            result = await asyncio.to_thread(
                service.respond, actor, key, identity, mission["revision"], cast(Any, operation)
            )
        elif operation == "start":
            result = await asyncio.to_thread(
                service.start, actor, key, identity, mission["revision"]
            )
        elif operation in ("end_success", "end_failure"):
            result = await asyncio.to_thread(
                service.end, actor, key, identity, mission["revision"], operation == "end_success"
            )
        else:
            result = await asyncio.to_thread(
                service.complete, actor, key, identity, mission["revision"]
            )
        return (
            "Saved: "
            + str(result["phase"]).replace("_", " ")
            + ". Reopen /mission inbox for current progress."
        )

    form = NativeForm(
        viewer.user_id,
        "Review mission",
        details(data),
        [Field("action", "Choose your action", tuple(actions))],
        submit,
    )
    await reply(interaction, form.text(), form)


class MissionSelect(discord.ui.Select["MissionQueue"]):
    def __init__(self, parent: "MissionQueue"):
        self.parent_queue = parent
        window = parent.rows[parent.page * 25 : parent.page * 25 + 25]
        super().__init__(
            placeholder="Choose a mission to review",
            row=0,
            options=[
                discord.SelectOption(
                    label=str(x["objective"])[:100],
                    value=x["id"],
                    description=str(x["phase"]).replace("_", " "),
                )
                for x in window
            ],
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        try:
            await open_mission(interaction, self.parent_queue.service, self.values[0])
        except WorkflowError as error:
            await reply(interaction, str(error))


class MissionQueue(discord.ui.View):
    def __init__(self, service: MissionService, owner: int, rows: list[dict[str, Any]]):
        super().__init__(timeout=600)
        self.service = service
        self.owner = owner
        self.rows = rows
        self.page = 0
        self.controls()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner:
            await reply(interaction, "This queue belongs to another player.")
            return False
        return True

    def controls(self) -> None:
        for child in list(self.children):
            if isinstance(child, MissionSelect):
                self.remove_item(child)
        if self.rows:
            self.add_item(MissionSelect(self))
        self.previous.disabled = self.page == 0
        self.next.disabled = (self.page + 1) * 25 >= len(self.rows)

    async def show(self, interaction: discord.Interaction) -> None:
        self.controls()
        await reply(
            interaction,
            (
                f"**Your missions**\nPage {self.page + 1} · {len(self.rows)} permitted missions. "
                "Select one to review."
            ),
            self,
        )

    @discord.ui.button(label="Previous", row=1)
    async def previous(
        self, interaction: discord.Interaction, button: discord.ui.Button[Any]
    ) -> None:
        self.page = max(0, self.page - 1)
        await interaction.response.defer()
        await self.show(interaction)

    @discord.ui.button(label="Next", row=1)
    async def next(self, interaction: discord.Interaction, button: discord.ui.Button[Any]) -> None:
        self.page += 1
        await interaction.response.defer()
        await self.show(interaction)


def register_missions(
    tree: app_commands.CommandTree, guild_id: int, service: MissionService
) -> None:
    group = app_commands.Group(
        name="mission",
        description="Private mission offers, responses and progress",
        guild_only=True,
    )

    @group.command(
        name="offer", description="Choose active Pilots and review a mission offer (Handler)"
    )
    async def offer(interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        try:
            roster = await asyncio.to_thread(service.roster, viewer_from_interaction(interaction))
            if not roster:
                raise WorkflowError("Activate the participating Pilots before offering a mission.")

            async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
                result = await asyncio.to_thread(
                    service.offer,
                    viewer_from_interaction(current),
                    str(current.id),
                    values["objective"],
                    tuple(int(x) for x in values["players"]),
                )
                return (
                    "Offer saved. Each invited player must answer through /mission inbox. Mission `"
                    + str(result["id"])
                    + "`."
                )

            form = NativeForm(
                interaction.user.id,
                "Offer a mission",
                (
                    "Choose Pilots and describe the objective. Each player answers privately. "
                    "Opening a menu never accepts an offer."
                ),
                [
                    Field("players", "Invite Pilots", roster, 1, min(25, len(roster))),
                    Field("objective", "Mission objective", paragraph=True),
                ],
                submit,
            )
            await reply(interaction, form.text(), form)
        except WorkflowError as error:
            await reply(interaction, str(error))

    @group.command(
        name="inbox", description="Review your saved missions and answer your own offers"
    )
    async def inbox(interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        try:
            rows = await asyncio.to_thread(service.list, viewer_from_interaction(interaction))
            if not rows:
                await reply(interaction, "No saved mission offers or progress are visible to you.")
                return
            view = MissionQueue(service, interaction.user.id, rows)
            await view.show(interaction)
        except WorkflowError as error:
            await reply(interaction, str(error))

    @group.command(
        name="show",
        description="Read a saved mission visible to you; /mission inbox offers dropdowns",
    )
    async def show(interaction: discord.Interaction, mission: str) -> None:
        await private_operation(
            interaction, lambda: details(service.get(viewer_from_interaction(interaction), mission))
        )

    @group.command(
        name="discipline", description="Review assigned Punishments and Handler consultations"
    )
    async def discipline(interaction: discord.Interaction) -> None:
        from girlframe.discord_adapter.m3_punishments import discipline_queue
        from girlframe.services.m3_punishments import PunishmentService

        await interaction.response.defer(ephemeral=True)
        try:
            await discipline_queue(
                interaction, PunishmentService(service.store, service.access.registry)
            )
        except WorkflowError as error:
            await reply(interaction, str(error))

    @group.command(name="reactions", description="Review required mission-end playbook reactions")
    async def reactions(interaction: discord.Interaction) -> None:
        from girlframe.discord_adapter.m3_reactions import reaction_queue
        from girlframe.services.m3_reactions import ReactionService

        await interaction.response.defer(ephemeral=True)
        try:
            await reaction_queue(interaction, ReactionService(service))
        except WorkflowError as error:
            await reply(interaction, str(error))

    @group.command(name="replacement", description="Review compulsory free Frame replacement tasks")
    async def replacement(interaction: discord.Interaction) -> None:
        from girlframe.discord_adapter.m3_replacement import replacement_queue
        from girlframe.services.m3_replacement import ReplacementService

        await interaction.response.defer(ephemeral=True)
        try:
            await replacement_queue(interaction, ReplacementService(service))
        except WorkflowError as error:
            await reply(interaction, str(error))

    @group.command(name="off_duty", description="Begin or resume saved Off-Duty preparation")
    async def off_duty(interaction: discord.Interaction) -> None:
        from girlframe.discord_adapter.m3_off_duty import open_period
        from girlframe.services.m3_off_duty import OffDutyService

        await interaction.response.defer(ephemeral=True)
        try:
            await open_period(interaction, OffDutyService(service))
        except WorkflowError as error:
            await reply(interaction, str(error))

    @group.command(
        name="strain", description="Choose initial Strain or review saved start work (Handler)"
    )
    async def strain(interaction: discord.Interaction) -> None:
        from girlframe.discord_adapter.m3_strain import open_strain
        from girlframe.services.m3_off_duty import OffDutyService
        from girlframe.services.m3_strain import StrainService

        await interaction.response.defer(ephemeral=True)
        try:
            await open_strain(interaction, StrainService(OffDutyService(service)))
        except WorkflowError as error:
            await reply(interaction, str(error))

    @group.command(name="world", description="Set up or manage the canonical world (Handler)")
    async def world(interaction: discord.Interaction) -> None:
        from girlframe.discord_adapter.m3_world import open_world
        from girlframe.services.m3_world import WorldService

        await interaction.response.defer(ephemeral=True)
        try:
            await open_world(interaction, WorldService(service))
        except WorkflowError as error:
            await reply(interaction, str(error))

    @group.command(name="map", description="Read the player map with only revealed Gorgons")
    async def map_view(interaction: discord.Interaction) -> None:
        from girlframe.discord_adapter.m3_world import MapPages
        from girlframe.services.m3_world import WorldService

        await interaction.response.defer(ephemeral=True)
        try:
            await MapPages(WorldService(service), interaction.user.id).show(interaction)
        except WorkflowError as error:
            await reply(interaction, str(error))

    @group.command(name="npc", description="Explicitly take the role of an introduced NPC")
    async def npc_role(interaction: discord.Interaction) -> None:
        from girlframe.discord_adapter.m3_world import open_npc_role
        from girlframe.services.m3_world import WorldService

        await interaction.response.defer(ephemeral=True)
        try:
            await open_npc_role(interaction, WorldService(service), bond=False)
        except WorkflowError as error:
            await reply(interaction, str(error))

    @group.command(name="npc_bond", description="Link your own saved starting NPC Bond")
    async def npc_bond(interaction: discord.Interaction) -> None:
        from girlframe.discord_adapter.m3_world import open_npc_role
        from girlframe.services.m3_world import WorldService

        await interaction.response.defer(ephemeral=True)
        try:
            await open_npc_role(interaction, WorldService(service), bond=True)
        except WorkflowError as error:
            await reply(interaction, str(error))

    tree.add_command(group, guild=discord.Object(id=guild_id))
