"""Native world setup and source-owned NPC control without exposing GM records."""

import asyncio
from typing import Any, cast
from uuid import uuid4

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.ledger import clean
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.m3_punishments import Picker
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine.m3_world_state import NPC_JOBS, Asset, Board, CorePlan, Gorgon, Location, Npc
from girlframe.services.m3_world import WorldService
from girlframe.services.onboarding import WorkflowError

TYPES = tuple(
    (x, x.title())
    for x in (
        "incubus",
        "doppleganger",
        "jackdaw",
        "mother",
        "sentinel",
        "leviathan",
        "growth",
        "parasite",
    )
)
START_CELLS = ((0, 0), (4, 0), (8, 0), (0, 5), (8, 5), (2, 3), (5, 5), (7, 8))
START_NAMES = (
    "North Base\nCentral Base\nEast Base\nArcadia\nNew Edmonton\nM-96\nFirst Side\nChreston"
)


def coordinates(text: str) -> tuple[int, int]:
    parts = text.strip().split(",")
    if len(parts) != 2:
        raise WorkflowError("Use a chosen map square in x,y form.")
    return int(parts[0]), int(parts[1])


def squares(board: dict[str, Any]) -> tuple[tuple[str, str], ...]:
    minimum, maximum = board["minimum"], board["maximum"]
    return tuple(
        (f"{x},{y}", f"Square {x}, {y}")
        for y in range(minimum[1], maximum[1] + 1)
        for x in range(minimum[0], maximum[0] + 1)
    )


async def setup_world(
    interaction: discord.Interaction, service: WorldService, data: dict[str, Any]
) -> None:
    viewer = viewer_from_interaction(interaction)
    location_ids = tuple(str(uuid4()) for _ in range(8))
    asset_ids = tuple(str(uuid4()) for _ in range(2))
    secret_id = str(uuid4())

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        names = [x.strip() for x in values["names"].splitlines()]
        if len(names) != 8 or any(not x for x in names):
            raise WorkflowError(
                "Name three bases, two cities and three important locations, in that order."
            )
        cells: tuple[tuple[int, int], ...] = START_CELLS
        if values["layout"][0] == "custom":
            cells = tuple(
                coordinates(x) for x in values.get("coordinates", "").splitlines() if x.strip()
            )
            if len(cells) != 8:
                raise WorkflowError("Provide one distinct chosen square per location.")
        assets = tuple(x.strip() for x in values["assets"].splitlines())
        if len(assets) != 2 or any(not x for x in assets):
            raise WorkflowError("Name two Assets for the secret Class 0.")
        locations = tuple(
            Location(
                id=location_ids[i],
                name=name,
                cell=cell,
                kind="base" if i < 3 else "city" if i < 5 else "important",
            )
            for i, (name, cell) in enumerate(zip(names, cells, strict=True))
        )
        supplied = tuple(
            Asset(id=asset_ids[i], name=name, description=name, family="gorgon")
            for i, name in enumerate(assets)
        )
        selected = tuple(supplied[int(x)].id for x in values["core_assets"])
        secret = Gorgon(
            id=secret_id,
            name=values["secret_name"],
            gorgon_class="benevolent",
            types=(cast(Any, values["type"][0]),),
            cell=locations[int(values["base"][0])].cell,
            assets=supplied,
            core_plan=CorePlan(assets=selected, weakness=values["weakness"]),
        )
        await asyncio.to_thread(
            service.initialize,
            viewer_from_interaction(current),
            str(current.id),
            data["game_revision"],
            Board(minimum=(0, 0), maximum=(9, 9)),
            locations,
            secret,
        )
        return "World saved; Class 0 remains private. Reopen /mission world for NPCs or the map."

    form = NativeForm(
        viewer.user_id,
        "Set up Quadrant 12",
        "Confirm a new 10×10 campaign map. Location order: 3 Foundation bases, "
        "2 cities, 3 important locations. The starter positions are "
        "(0,0), (4,0), (8,0), (0,5), (8,5), (2,3), (5,5), (7,8). "
        "This is a selectable layout, not a printed map. Secret Class 0 details stay private.",
        [
            Field("names", "Eight location names, one per line", paragraph=True),
            Field(
                "layout",
                "Choose the map layout",
                (
                    ("starter", "Use the displayed starter positions"),
                    ("custom", "Use my eight custom squares"),
                ),
            ),
            Field(
                "coordinates", "Custom x,y squares, one per line", paragraph=True, required=False
            ),
            Field(
                "base",
                "Secret Class 0 starts at which base?",
                (("0", "First base"), ("1", "Second base"), ("2", "Third base")),
            ),
            Field("secret_name", "Private Class 0 name"),
            Field("type", "Secret Gorgon Type", TYPES),
            Field("assets", "Two Class 0 Asset names, one per line", paragraph=True),
            Field(
                "core_assets",
                "Which Assets protect its Core?",
                (("0", "First Asset"), ("1", "Second Asset")),
                1,
                2,
            ),
            Field("weakness", "What tactical weakness exposes its Core?", paragraph=True),
        ],
        submit,
        values={"names": START_NAMES},
    )
    await reply(interaction, form.text(), form)


class MapPages(discord.ui.View):
    def __init__(self, service: WorldService, owner: int):
        super().__init__(timeout=600)
        self.service, self.owner, self.page = service, owner, 0

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner:
            await reply(interaction, "This map view belongs to another player.")
            return False
        return True

    async def show(self, interaction: discord.Interaction) -> None:
        data = await asyncio.to_thread(self.service.get, viewer_from_interaction(interaction))
        world = data["world"]
        if world is None:
            await reply(interaction, "The Handler has not initialized the world yet.")
            return
        lines = [
            f"{clean(x['name'])} · {x['cell'][0]},{x['cell'][1]} · {x['kind']} · "
            + ("unavailable" if not x["operational"] else x["condition"])
            for x in world["locations"]
        ]
        lines += [
            f"{clean(x['name'])} · {x['cell'][0]},{x['cell'][1]} · known {x['gorgon_class']}"
            for x in world["gorgons"]
        ]
        self.page = min(self.page, max(0, (len(lines) - 1) // 8))
        self.previous.disabled = self.page == 0
        self.next.disabled = (self.page + 1) * 8 >= len(lines)
        await reply(
            interaction,
            f"**Quadrant map — page {self.page + 1}**\n"
            + "\n".join(lines[self.page * 8 : self.page * 8 + 8])
            + f"\nGorgon territory: {len(world['territory'])} squares.",
            self,
        )

    @discord.ui.button(label="Previous")
    async def previous(
        self, interaction: discord.Interaction, button: discord.ui.Button[Any]
    ) -> None:
        self.page = max(0, self.page - 1)
        await interaction.response.defer(ephemeral=True)
        await self.show(interaction)

    @discord.ui.button(label="Next")
    async def next(self, interaction: discord.Interaction, button: discord.ui.Button[Any]) -> None:
        self.page += 1
        await interaction.response.defer(ephemeral=True)
        await self.show(interaction)


async def open_world(interaction: discord.Interaction, service: WorldService) -> None:
    viewer = viewer_from_interaction(interaction)
    data = await asyncio.to_thread(service.get, viewer, private=True)
    if data["world"] is None:
        await setup_world(interaction, service, data)
        return

    async def choose(current: discord.Interaction, action: str) -> None:
        fresh = await asyncio.to_thread(service.get, viewer_from_interaction(current), private=True)
        world = fresh["world"]
        if world is None:
            raise WorkflowError("Initialize the world first.")
        if action == "map":
            await MapPages(service, viewer.user_id).show(current)
            return
        if action == "gorgon_position":
            unknown = tuple((x["id"], x["name"]) for x in world["gorgons"] if x["cell"] is None)
            if not unknown:
                raise WorkflowError("No actual Gorgon has an unrecorded position.")

            async def locate(response: discord.Interaction, values: dict[str, Any]) -> str:
                await asyncio.to_thread(
                    service.locate_gorgon,
                    viewer_from_interaction(response),
                    str(response.id),
                    fresh["game_revision"],
                    values["gorgon"][0],
                    coordinates(values["cell"][0]),
                    values["account"],
                )
                return "Actual initial position recorded; no known position was moved."

            form = NativeForm(
                current.user.id,
                "Record missing Gorgon position",
                "Use the actual current map facts. This cannot move an already located Gorgon.",
                [
                    Field("gorgon", "Actual unplaced Gorgon", unknown),
                    Field("cell", "Actual map square", squares(world["board"])),
                    Field("account", "Factual source", paragraph=True),
                ],
                locate,
            )
            await reply(current, form.text(), form)
            return
        if action == "gorgon_attack":
            from girlframe.discord_adapter.m3_gorgon import open_gorgon_attack
            from girlframe.services.m3_gorgon import GorgonService

            await open_gorgon_attack(current, GorgonService(service))
            return
        if action in ("gorgon_contest", "gorgon_core"):
            from girlframe.discord_adapter.m3_gorgon_combat import open_contest, open_exposure
            from girlframe.services.m3_gorgon import GorgonService

            await (open_contest if action == "gorgon_contest" else open_exposure)(
                current, GorgonService(service)
            )
            return
        if action in ("npc", "npc_invite"):
            npc_identity = str(uuid4())
            from girlframe.services.m3_npc_roles import NpcRoleService

            roles = NpcRoleService(service)
            invited = action == "npc_invite"
            members = (await asyncio.to_thread(roles.members, viewer))["members"] if invited else ()
            if invited and not members:
                raise WorkflowError(
                    "Another joined campaign member is needed for a separate NPC role."
                )

            async def submit(actor: discord.Interaction, values: dict[str, Any]) -> str:
                npc = Npc(
                    id=npc_identity,
                    name=values["name"],
                    jobs=tuple(values["jobs"]),
                    detail=values["detail"],
                    controller=int(values["controller"][0]) if invited else actor.user.id,
                    cell=coordinates(values["cell"][0]),
                    revealed=values["visible"][0] == "yes",
                )
                await asyncio.to_thread(
                    roles.offer if invited else service.npc,
                    viewer_from_interaction(actor),
                    str(actor.id),
                    fresh["game_revision"],
                    npc,
                )
                return (
                    "Private NPC role invitation saved. The invited human must answer."
                    if invited
                    else "NPC introduced. Another human can explicitly claim a revealed NPC's role."
                )

            fields = [
                Field("name", "NPC name"),
                Field(
                    "jobs",
                    "Printed NPC playbooks",
                    tuple((x, x.replace("_", " ").title()) for x in NPC_JOBS),
                    1,
                    len(NPC_JOBS),
                ),
                Field("detail", "Defining quirk, appearance or item", paragraph=True),
                Field("cell", "Where are they?", squares(world["board"])),
                Field(
                    "visible",
                    "Introduced to the players?",
                    (("yes", "Yes"), ("no", "Keep private")),
                ),
            ]
            if invited:
                fields.insert(0, Field("controller", "Invite this human to play the NPC", members))
            form = NativeForm(
                viewer.user_id,
                "Invite a human to an NPC role" if invited else "Introduce an NPC",
                "Choose who they are and where they enter the world. "
                "Their private notes and any starting Bond feelings stay outside the public map.",
                fields,
                submit,
            )
            await reply(current, form.text(), form)
        elif action == "reveal":
            options = tuple((x["id"], x["name"]) for x in world["gorgons"] if not x["revealed"])
            if not options:
                await reply(current, "No unrevealed Gorgon is recorded.")
                return

            async def submit(actor: discord.Interaction, values: dict[str, Any]) -> str:
                await asyncio.to_thread(
                    service.reveal,
                    viewer_from_interaction(actor),
                    str(actor.id),
                    fresh["game_revision"],
                    values["gorgon"][0],
                    values["account"],
                )
                return "The encounter is recorded and the Gorgon is now visible on the player map."

            form = NativeForm(
                viewer.user_id,
                "Reveal an encountered Gorgon",
                "Record the actual encounter; the Core plan stays private.",
                [
                    Field("gorgon", "Which Gorgon?", options),
                    Field("account", "What revealed it?", paragraph=True),
                ],
                submit,
            )
            await reply(current, form.text(), form)

    view = Picker(
        viewer.user_id,
        "**World management**\nChoose an explicit action.",
        (
            ("map", "View the player map"),
            ("gorgon_position", "Record an actually unknown Gorgon position"),
            ("npc", "Introduce an NPC"),
            ("npc_invite", "Invite someone to play an NPC / Director"),
            ("reveal", "Reveal a Gorgon encountered by the Cadre"),
            ("gorgon_attack", "Gorgon Attack on an ordinary NPC"),
            ("gorgon_contest", "Pit two Gorgons' actual Assets"),
            ("gorgon_core", "Confirm actual Gorgon Core exposure"),
        ),
        choose,
    )
    await view.show(interaction)


async def open_npc_role(
    interaction: discord.Interaction, service: WorldService, *, bond: bool
) -> None:
    viewer = viewer_from_interaction(interaction)
    data = await asyncio.to_thread(
        service.bond_options if bond else service.control_options, viewer
    )
    options = data["options"] if bond else data["npcs"]
    if not options:
        await reply(
            interaction,
            "No matching unlinked starting NPC Bond."
            if bond
            else "No revealed living NPC is available.",
        )
        return

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        selected = values["npc"][0]
        if selected not in dict(options):
            raise WorkflowError("Choose an NPC from your own current view.")
        if bond:
            slot, identity = selected.split(":", 1)
            await asyncio.to_thread(
                service.import_starting_npc,
                viewer_from_interaction(current),
                str(current.id),
                data["game_revision"],
                int(slot),
                identity,
            )
            return "Your own starting NPC Bond is linked. Private feelings remain private."
        await asyncio.to_thread(
            service.claim_npc,
            viewer_from_interaction(current),
            str(current.id),
            data["game_revision"],
            selected,
        )
        return "You now play this NPC. Choose their actions during the conversation."

    form = NativeForm(
        viewer.user_id,
        "Link your own starting NPC" if bond else "Play an NPC",
        "Your confirmation records only this selected role or your own saved starting Bond.",
        [Field("npc", "Choose an available NPC", tuple(options))],
        submit,
    )
    await reply(interaction, form.text(), form)
