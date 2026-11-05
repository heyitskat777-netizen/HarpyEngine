"""Private paginated Asset source selection and explicit one-Permission payment."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.labels import entity_label
from girlframe.discord_adapter.ledger import clean
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.m3_comforts import PaidComfortPages, open_comfort
from girlframe.discord_adapter.m3_punishments import Picker
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_requisition_state import Installation
from girlframe.services.m3_comforts import ComfortService
from girlframe.services.m3_requisitions import RequisitionService
from girlframe.services.onboarding import WorkflowError


class InstallationPages(discord.ui.View):
    def __init__(self, service: RequisitionService, owner: int, identity: str):
        super().__init__(timeout=600)
        self.service, self.owner, self.identity, self.index = service, owner, identity, 0

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner:
            await reply(interaction, "This private purchase belongs to another player.")
            return False
        return True

    async def show(self, interaction: discord.Interaction) -> None:
        try:
            data = await asyncio.to_thread(
                self.service.installation, viewer_from_interaction(interaction), self.identity
            )
        except WorkflowError as error:
            await reply(interaction, str(error))
            return
        receipt, asset = data["receipt"], data["asset"]
        sections = (
            "Asset: " + asset["name"] + "\nInstalled in: " + data["frame"] + "\n1 Permission paid.",
            "Original Asset description\n" + asset["description"],
            "Original installation\n" + receipt["installation"]["account"],
        )
        pages: list[str] = []
        for section in sections:
            escaped = clean(section)
            pages.extend(escaped[start : start + 1700] for start in range(0, len(escaped), 1700))
        self.index = min(max(0, self.index), len(pages) - 1)
        self.previous.disabled, self.next.disabled = self.index == 0, self.index == len(pages) - 1
        await reply(
            interaction,
            "**Your original Asset Installment receipt**\n"
            + pages[self.index]
            + f"\nPage {self.index + 1}/{len(pages)} · Receipt `{self.identity}`",
            self,
        )

    @discord.ui.button(label="Previous")
    async def previous(
        self, interaction: discord.Interaction, button: discord.ui.Button[Any]
    ) -> None:
        self.index -= 1
        await interaction.response.defer(ephemeral=True)
        await self.show(interaction)

    @discord.ui.button(label="Next")
    async def next(self, interaction: discord.Interaction, button: discord.ui.Button[Any]) -> None:
        self.index += 1
        await interaction.response.defer(ephemeral=True)
        await self.show(interaction)


async def open_purchase_history(
    interaction: discord.Interaction, service: RequisitionService
) -> None:
    viewer = viewer_from_interaction(interaction)
    history = await asyncio.to_thread(service.installation_history, viewer)
    comforts = ComfortService(service.game)
    paid = await asyncio.to_thread(comforts.receipts, viewer)

    async def show(current: discord.Interaction, identity: str) -> None:
        if identity.startswith("paid-comfort:"):
            await PaidComfortPages(comforts, viewer.user_id, identity[13:]).show(current)
            return
        await InstallationPages(service, viewer.user_id, identity).show(current)

    await Picker(
        viewer.user_id,
        "**Your saved purchases**\nChoose an original purchase to read its details.",
        tuple((x["id"], x["name"]) for x in history)
        + tuple(("paid-comfort:" + x["id"], "Creature Comforts receipt") for x in paid),
        show,
    ).show(interaction)


async def open_requisitions(interaction: discord.Interaction, service: RequisitionService) -> None:
    viewer = viewer_from_interaction(interaction)
    try:
        data = await asyncio.to_thread(service.view, viewer)
    except WorkflowError as error:
        if not str(error).startswith(("STALE_CHARACTER:", "STALE_PROFILE:", "STALE_ACTOR:")):
            raise
        await open_purchase_history(interaction, service)
        return
    comforts = ComfortService(service.game)
    opportunities = await asyncio.to_thread(comforts.list, viewer)
    paid = {x["id"]: x for x in await asyncio.to_thread(comforts.receipts, viewer)}
    purchases = {x["id"]: x for x in await asyncio.to_thread(service.installation_history, viewer)}
    options = (("install", "Buy an Asset Installment — 1 Permission"),) + tuple(
        (key, "Saved Asset purchase " + key[:8]) for key in purchases
    )
    options += (("buy-comforts", "Buy Creature Comforts — 1 Permission"),)
    options += (
        ("frame-swap", "Plan paid Frame Swap — 4 Permissions"),
        ("ability-unlock", "Ability Unlock — supported owned Frame rule"),
        ("frame-grafting", "Frame Grafting — supported donor Frame rule"),
    )
    from girlframe.services.m3_frame_swap import FrameSwapService
    from girlframe.services.m3_personal_firearm import PersonalFirearmService

    firearms = PersonalFirearmService(service.game)
    exchanges = FrameSwapService(service.game)
    options += tuple(
        ("firearm-return:" + x["id"], "Saved Personal Firearm return")
        for x in await asyncio.to_thread(firearms.return_tasks, viewer)
    )
    options += tuple(
        ("frame-swap:" + x["id"], "Saved Frame Swap plan")
        for x in await asyncio.to_thread(exchanges.tasks, viewer)
    )

    options += (
        ("buy-privacy", "Privacy — 1 Permission"),
        ("buy-home", "Visiting Home — 2 Permissions"),
        ("retirement", "Retirement — 20 Permissions"),
    )
    from girlframe.services.m3_scene_requisitions import SceneRequisitionService

    scene_service = SceneRequisitionService(service.game)
    saved_scenes = await asyncio.to_thread(scene_service.scene_tasks, viewer)
    options += tuple(
        ("scene:" + x["id"], x["kind"].replace("_", " ").title() + " — saved scene")
        for x in saved_scenes
    )
    options += tuple(
        (
            "comfort:" + x["id"],
            "Creature Comforts — " + ("your benefit" if x["own"] else "your scene attendance"),
        )
        for x in opportunities
    )
    options += tuple(
        ("paid-comfort:" + key, "Paid Creature Comforts — " + x["state"].replace("_", " "))
        for key, x in paid.items()
    )

    async def choose(current: discord.Interaction, token: str) -> None:
        if token == "frame-swap" or token.startswith("frame-swap:"):
            from girlframe.discord_adapter.m3_frame_swap import open_plan, open_swap

            if token == "frame-swap":
                await open_swap(current, exchanges)
            else:
                await open_plan(current, exchanges, token[11:])
            return
        if token.startswith("firearm-return:"):
            from girlframe.discord_adapter.m3_personal_firearm import open_return

            await open_return(current, firearms, token[15:])
            return
        if token in ("ability-unlock", "frame-grafting"):
            from girlframe.discord_adapter.m3_personal_firearm import open_acquisition

            await open_acquisition(
                current,
                firearms,
                "ability_unlock" if token == "ability-unlock" else "frame_grafting",
            )
            return
        if token.startswith("scene:"):
            from girlframe.discord_adapter.m3_scene_requisitions import open_scene

            await open_scene(current, scene_service, token[6:])
            return
        if token in ("buy-privacy", "buy-home"):
            from girlframe.discord_adapter.m3_scene_requisitions import open_purchase

            await open_purchase(
                current, scene_service, "privacy" if token == "buy-privacy" else "visiting_home"
            )
            return
        if token == "retirement":
            from girlframe.discord_adapter.m3_retirement import open_retirement
            from girlframe.services.m3_retirement import RetirementService

            await open_retirement(current, RetirementService(service.game))
            return
        if token.startswith("comfort:"):
            await open_comfort(current, comforts, token[8:])
            return
        if token.startswith("paid-comfort:"):
            await PaidComfortPages(comforts, viewer.user_id, token[13:]).show(current)
            return
        if token == "buy-comforts":

            async def pay(response: discord.Interaction, values: dict[str, Any]) -> str:
                outcome = await asyncio.to_thread(
                    comforts.buy_comforts,
                    viewer_from_interaction(response),
                    str(response.id),
                    ActorRef.model_validate(data["actor"]),
                    data["source_sha256"],
                    values["account"],
                )
                return (
                    "Creature Comforts paid: 1 Permission. Your saved request waits "
                    "for your next actual 8+ Go Off-Duty roll. Receipt: " + str(outcome["id"])
                )

            form = NativeForm(
                viewer.user_id,
                "Buy Creature Comforts",
                "Pay 1 Permission for the optional improvement scene "
                "on your next actual 8+ ordinary Go Off-Duty roll. "
                "The actual scene precedes writing a new Girl Asset. "
                "An unused opportunity can be declined without a refund.",
                [
                    Field("account", "What improvement are you requesting?", paragraph=True),
                    Field(
                        "confirm",
                        "Confirm payment",
                        (("yes", "Pay 1 Permission for Creature Comforts"),),
                    ),
                ],
                pay,
            )
            await reply(current, form.text(), form)
            return
        if token in purchases:
            await InstallationPages(service, viewer.user_id, token).show(current)
            return
        entries = {x["key"]: x for x in data["catalog"]}
        sources = tuple(
            (key, x["name"][:65] + " — " + x["frame"][:25]) for key, x in entries.items()
        ) + (("custom", "Write my own ordinary Frame Asset"),)

        async def select_asset(selected: discord.Interaction, source: str) -> None:
            at_limit = sum(x["counts_toward_limit"] for x in data["frame_assets"]) >= 5
            replaceable = [x for x in data["frame_assets"] if x["can_replace_at_limit"]]
            if at_limit and not replaceable:
                await reply(
                    selected,
                    "Your Frame is at its Asset limit with no replaceable non-Void Asset. "
                    "Asset Installment cannot replace a Void or protected intrinsic Asset.",
                )
                return
            custom = source == "custom"
            fields = [Field("name", "Name your new Frame Asset")] if custom else []
            fields += [
                Field("description", "Describe the installed Asset", paragraph=True),
                Field("account", "Describe the actual installation", paragraph=True),
            ]
            if at_limit:
                fields.append(
                    Field(
                        "replace",
                        "Non-Void Frame Asset to replace",
                        tuple((x["id"], entity_label(x)) for x in replaceable),
                    )
                )
            fields.append(
                Field(
                    "confirm",
                    "Confirm purchase",
                    (("yes", "Pay 1 Permission and install this Asset"),),
                )
            )

            async def submit(response: discord.Interaction, values: dict[str, Any]) -> str:
                entry = entries.get(source)
                result = await asyncio.to_thread(
                    service.buy,
                    viewer_from_interaction(response),
                    str(response.id),
                    ActorRef.model_validate(data["actor"]),
                    data["source_sha256"],
                    Installation(
                        from_frame=entry["frame"] if entry else None,
                        index=entry["index"] if entry else None,
                        name=values["name"] if custom else "",
                        description=values["description"],
                        account=values["account"],
                        replace=values.get("replace", (None,))[0],
                        trigger_confirmed=True,
                    ),
                )
                return (
                    "Asset installed. 1 Permission paid; "
                    + str(result["permissions"])
                    + " remaining. Saved receipt: "
                    + str(result["id"])
                    + "."
                )

            form = NativeForm(
                viewer.user_id,
                "Confirm Asset Installment",
                "Your selected Asset is "
                + ("your own creation" if custom else entries[source]["name"])
                + ". Review the actual installation, replacement and price before paying. "
                "This grants an ordinary undamaged Asset; Frame rules and Void are separate.",
                fields,
                submit,
            )
            await reply(selected, form.text(), form)

        await Picker(
            viewer.user_id,
            "**Choose your new Frame Asset**\nPrinted Assets from any base Frame "
            "or your own creation. 1 Permission.",
            sources,
            select_asset,
        ).show(current)

    await Picker(
        viewer.user_id,
        "**Your Requisitions**\nAvailable Permissions: "
        + str(data["permissions"])
        + ". Choose a purchase or saved receipt.",
        options,
        choose,
    ).show(interaction)
