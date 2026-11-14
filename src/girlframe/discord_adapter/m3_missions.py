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
        if mission["phase"] == "offered" and "accept" not in mission["responses"].values():
            actions.append(("cancel", "Cancel this undispatched offer"))
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
        elif operation == "cancel":
            result = await asyncio.to_thread(
                service.cancel, actor, key, identity, mission["revision"]
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

    @group.command(
        name="actors", description="Review your actual Girl, NPC and other controlled roles"
    )
    async def actors(interaction: discord.Interaction) -> None:
        from girlframe.discord_adapter.m3_actors import open_actors
        from girlframe.services.m3_actors import ActorService

        await interaction.response.defer(ephemeral=True)
        try:
            await open_actors(interaction, ActorService(service))
        except WorkflowError as error:
            await reply(interaction, str(error))

    @group.command(name="cast", description="Choose your actual roles in this bound scene")
    async def cast_scene(interaction: discord.Interaction) -> None:
        from girlframe.discord_adapter.m3_cast import open_cast
        from girlframe.services.m3_actors import ActorService
        from girlframe.services.m3_cast import CastService

        await interaction.response.defer(ephemeral=True)
        try:
            await open_cast(interaction, CastService(ActorService(service)))
        except WorkflowError as error:
            await reply(interaction, str(error))

    @group.command(
        name="regulations", description="Review known behavioural rules and recorded breaches"
    )
    async def regulations(interaction: discord.Interaction) -> None:
        from girlframe.discord_adapter.m3_regulations import open_regulations
        from girlframe.services.m3_regulations import RegulationService

        await interaction.response.defer(ephemeral=True)
        try:
            await open_regulations(interaction, RegulationService(service))
        except WorkflowError as error:
            await reply(interaction, str(error))

    @group.command(
        name="repairs", description="Review exact Handler prices for extra shortage repairs"
    )
    async def repairs(interaction: discord.Interaction) -> None:
        from girlframe.discord_adapter.m3_repairs import open_repairs
        from girlframe.services.m3_off_duty import OffDutyService
        from girlframe.services.m3_repairs import RepairService

        await interaction.response.defer(ephemeral=True)
        try:
            await open_repairs(interaction, RepairService(OffDutyService(service)))
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

    @group.command(name="npc", description="Offer your NPC role to another human for acceptance")
    async def npc_role(interaction: discord.Interaction) -> None:
        from girlframe.discord_adapter.m3_world import open_npc_role
        from girlframe.services.m3_world import WorldService

        await interaction.response.defer(ephemeral=True)
        try:
            await open_npc_role(interaction, WorldService(service), bond=False)
        except WorkflowError as error:
            await reply(interaction, str(error))

    @group.command(name="guard", description="Review your Guard's actual weapon facts")
    async def guard(interaction: discord.Interaction) -> None:
        from girlframe.discord_adapter.m3_npc_guard import open_guard
        from girlframe.services.m3_npc_guard import GuardService

        await interaction.response.defer(ephemeral=True)
        try:
            await open_guard(interaction, GuardService(service.game))
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

    @group.command(name="requisitions", description="Review your owned Permissions and purchases")
    async def requisitions(interaction: discord.Interaction) -> None:
        from girlframe.discord_adapter.m3_requisitions import open_requisitions
        from girlframe.services.m3_requisitions import RequisitionService

        await interaction.response.defer(ephemeral=True)
        try:
            await open_requisitions(interaction, RequisitionService(service.game))
        except WorkflowError as error:
            await reply(interaction, str(error))

    @group.command(
        name="janus", description="Review your original JANUS Core and source-owned work"
    )
    async def janus(interaction: discord.Interaction) -> None:
        from girlframe.discord_adapter.m3_janus import open_janus
        from girlframe.services.m3_janus import JanusService

        await interaction.response.defer(ephemeral=True)
        try:
            await open_janus(interaction, JanusService(service.game))
        except WorkflowError as error:
            await reply(interaction, str(error))

    @group.command(name="leviathan", description="Declare your Leviathan's actual influence")
    async def leviathan(interaction: discord.Interaction) -> None:
        from girlframe.discord_adapter.m3_leviathan_obsession import open_influence
        from girlframe.services.m3_leviathan_obsession import ObsessionService

        await interaction.response.defer(ephemeral=True)
        try:
            await open_influence(interaction, ObsessionService(service.game))
        except WorkflowError as error:
            await reply(interaction, str(error))

    @group.command(
        name="virus", description="Use source-owned Compliance Virus and factual link review"
    )
    async def virus(interaction: discord.Interaction) -> None:
        from girlframe.discord_adapter.m3_compliance_virus import open_virus_hub

        await interaction.response.defer(ephemeral=True)
        try:
            await open_virus_hub(interaction, service.game)
        except WorkflowError as error:
            await reply(interaction, str(error))

    @group.command(
        name="enforcer", description="Review actual Enforcer accusations and source-owned case work"
    )
    async def enforcer(interaction: discord.Interaction) -> None:
        from girlframe.discord_adapter.m3_enforcer import open_conditioning, open_enforcer_task
        from girlframe.discord_adapter.m3_punishments import Picker
        from girlframe.services.m3_enforcer import EnforcerService
        from girlframe.services.m3_role_punishments import RolePunishmentService

        await interaction.response.defer(ephemeral=True)
        try:
            enforcers = EnforcerService(service.game)
            saved = await asyncio.to_thread(enforcers.tasks, viewer_from_interaction(interaction))
            grasps = await asyncio.to_thread(enforcers.grasps, viewer_from_interaction(interaction))
            discipline = RolePunishmentService(service.game)
            cases = await asyncio.to_thread(discipline.tasks, viewer_from_interaction(interaction))

            from girlframe.engine.m3_plays import HEAT_IDS

            initiative = False
            if "enforcement_initiative" in HEAT_IDS and interaction.channel_id is not None:
                from girlframe.services.m3_enforcement_initiative import preview

                available = await asyncio.to_thread(
                    preview,
                    service.game,
                    viewer_from_interaction(interaction),
                    interaction.channel_id,
                )
                initiative = available["available"]

            async def choose(current: discord.Interaction, token: str) -> None:
                if token == "volunteer":
                    from girlframe.discord_adapter.m3_enforcer_volunteer import open_volunteer
                    from girlframe.services.m3_enforcer_volunteer import VolunteerService

                    await open_volunteer(current, VolunteerService(service.game))
                elif token == "item-fact":
                    from girlframe.discord_adapter.m3_items import open_item_proposal

                    await open_item_proposal(current, service.game)
                elif token.startswith("grasp:"):
                    from girlframe.discord_adapter.m3_enforcement_initiative import open_grasp

                    await open_grasp(current, service.game, token[6:])
                elif token == "initiative":
                    from girlframe.discord_adapter.m3_enforcement_initiative import open_initiative

                    await open_initiative(current, service.game)
                elif token.startswith("punishment:"):
                    from girlframe.discord_adapter.m3_role_punishments import open_role_punishment

                    await open_role_punishment(current, discipline, token[11:])
                elif token == "conditioning":
                    await open_conditioning(current, enforcers)
                else:
                    await open_enforcer_task(current, enforcers, token)

            await Picker(
                interaction.user.id,
                "Your actual Enforcer controls",
                (
                    ("conditioning", "Obedience Conditioning — actual known NPCs"),
                    ("item-fact", "Existing held object — actual possession review"),
                    ("volunteer", "Volunteer to carry out an actual Punishment"),
                )
                + (
                    (("initiative", "Enforcement Initiative — actual take hold"),)
                    if initiative
                    else ()
                )
                + tuple((x["id"], x["kind"].replace("_", " ").title()) for x in saved)
                + tuple(("punishment:" + x["id"], "Actual instructed Punishment") for x in cases)
                + tuple(
                    ("grasp:" + x["id"], "Release your actual held grasp")
                    for x in grasps
                    if x["held"]
                ),
                choose,
            ).show(interaction)
        except WorkflowError as error:
            await reply(interaction, str(error))

    @group.command(
        name="handler", description="Review your Handler persona or source-owned basic Plays"
    )
    async def handler_creation(interaction: discord.Interaction) -> None:
        from girlframe.discord_adapter.m3_handler_creation import open_handler
        from girlframe.discord_adapter.m3_handler_plays import open_handler_plays
        from girlframe.discord_adapter.m3_punishments import Picker
        from girlframe.services.m3_handler_creation import HandlerCreationService
        from girlframe.services.m3_handler_plays import HandlerPlayService

        await interaction.response.defer(ephemeral=True)
        try:

            async def choose(current: discord.Interaction, token: str) -> None:
                if token == "persona":
                    await open_handler(current, HandlerCreationService(service.store))
                elif token == "plays":
                    await open_handler_plays(current, HandlerPlayService(service.store))
                elif token == "ordinary":
                    from girlframe.discord_adapter.m3_handler_ordinary import open_ordinary
                    from girlframe.services.m3_handler_ordinary import HandlerOrdinaryService

                    await open_ordinary(current, HandlerOrdinaryService(service.store))
                else:
                    raise WorkflowError("Choose a current Handler control.")

            await Picker(
                interaction.user.id,
                "Your actual Handler controls",
                (
                    ("persona", "Create or review your fictional Handler persona"),
                    ("plays", "Basic Handler Plays — actual human GM procedures"),
                    ("ordinary", "Campaign sessions and ordinary advancement"),
                ),
                choose,
            ).show(interaction)
        except WorkflowError as error:
            await reply(interaction, str(error))

    @group.command(
        name="position", description="Review your actual original body and Frame positions"
    )
    async def position(interaction: discord.Interaction) -> None:
        from girlframe.discord_adapter.m3_physical import open_initial
        from girlframe.services.m3_physical import PhysicalService

        await interaction.response.defer(ephemeral=True)
        try:
            await open_initial(interaction, PhysicalService(service.store))
        except WorkflowError as error:
            await reply(interaction, str(error))

    @group.command(name="contraband", description="Review your own private contraband finds")
    async def contraband(interaction: discord.Interaction) -> None:
        from girlframe.discord_adapter.m3_contraband import open_finds
        from girlframe.services.m3_contraband import ContrabandService

        await interaction.response.defer(ephemeral=True)
        try:
            await open_finds(interaction, ContrabandService(service.game))
        except WorkflowError as error:
            await reply(interaction, str(error))

    tree.add_command(group, guild=discord.Object(id=guild_id))
