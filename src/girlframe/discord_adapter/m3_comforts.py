"""Native owned improvement scenes, actual attendance and explicit Girl Asset grants."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.labels import entity_label
from girlframe.discord_adapter.ledger import clean
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.m3_punishments import Picker
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_requisition_state import GirlAsset
from girlframe.services.m3_comforts import ComfortService
from girlframe.services.onboarding import WorkflowError


class PaidComfortPages(discord.ui.View):
    def __init__(self, service: ComfortService, owner: int, identity: str):
        super().__init__(timeout=600)
        self.service, self.owner, self.identity, self.index = service, owner, identity, 0

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner:
            await reply(interaction, "This paid request belongs to another player.")
            return False
        return True

    async def show(self, interaction: discord.Interaction) -> None:
        try:
            data = await asyncio.to_thread(
                self.service.paid_receipt, viewer_from_interaction(interaction), self.identity
            )
        except WorkflowError as error:
            await reply(interaction, str(error))
            return
        text = clean(data["account"])
        pages = [text[start : start + 1700] for start in range(0, len(text), 1700)]
        self.index = min(max(self.index, 0), len(pages) - 1)
        self.previous.disabled, self.next.disabled = self.index == 0, self.index == len(pages) - 1
        status = (
            "Waiting for your next actual 8+ ordinary Go Off-Duty roll."
            if data["benefit_id"] is None
            else "Opportunity: " + clean(data["state"]) + "."
        )
        await reply(
            interaction,
            "**Your paid Creature Comforts receipt**\n1 Permission paid.\n"
            + status
            + "\n"
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


async def open_comfort(
    interaction: discord.Interaction, service: ComfortService, identity: str
) -> None:
    viewer = viewer_from_interaction(interaction)
    data = await asyncio.to_thread(service.get, viewer, identity)
    if data["taken"] is not None:
        text = "**Creature Comforts — resolved**\n"
        if data["own"]:
            text += (
                ("Your Girl Asset: " + clean(data["asset_name"]))
                if data["taken"]
                else "You declined the optional scene. The paid Permission was not refunded."
            )
        else:
            text += "Your saved scene attendance remains recorded."
        await reply(interaction, text)
        return
    if not data["own"]:
        if data["scene"]["own_attested"]:
            await reply(
                interaction,
                "Your actual scene attendance is saved. "
                "The purchasing Girl chooses her Asset after all attendance is recorded.",
            )
            return

        async def attend(current: discord.Interaction, values: dict[str, Any]) -> str:
            await asyncio.to_thread(
                service.attest,
                viewer_from_interaction(current),
                str(current.id),
                identity,
                data["revision"],
            )
            return "Your actual attendance is saved. This supplies no one else's response."

        form = NativeForm(
            viewer.user_id,
            "Your improvement scene attendance",
            clean(data["scene"]["summary"])
            + "\nConfirm the actual scene in which you played your role. "
            "Each human records their own attendance.",
            [
                Field(
                    "confirm",
                    "Your actual attendance",
                    (("yes", "I participated in this actual scene"),),
                )
            ],
            attend,
        )
        await reply(interaction, form.text(), form)
        return
    if data["scene"] is not None:
        if not data["ready"]:
            await reply(
                interaction,
                "**Creature Comforts scene**\n"
                + clean(data["scene"]["summary"])
                + "\nWaiting for "
                + str(data["scene"]["awaiting"])
                + " participant(s) to confirm their own attendance. "
                "Reopen this saved opportunity after they respond.",
            )
            return
        assets = data["girl_assets"]
        if len(assets) >= 4 and not any(not x["void"] for x in assets):
            await reply(
                interaction,
                "Your Girl is at her Asset limit and every Girl Asset is Void. "
                "This grant needs legal space or a non-Void replacement; "
                "the owed benefit remains saved.",
            )
            return
        fields = [
            Field("name", "Name the new Girl Asset (up to 80 characters)"),
            Field("description", "How does it reflect the scene? (up to 700)", paragraph=True),
        ]
        if len(assets) >= 4:
            fields.append(
                Field(
                    "replace",
                    "Non-Void Girl Asset to replace",
                    tuple((x["id"], entity_label(x)) for x in assets if not x["void"]),
                )
            )
        fields.append(
            Field(
                "confirm",
                "Confirm your new Girl Asset",
                (("yes", "Write this ordinary undamaged Girl Asset"),),
            )
        )

        async def grant(current: discord.Interaction, values: dict[str, Any]) -> str:
            await asyncio.to_thread(
                service.grant,
                viewer_from_interaction(current),
                str(current.id),
                identity,
                data["revision"],
                data["source_sha256"],
                GirlAsset(
                    name=values["name"],
                    description=values["description"],
                    replace=values.get("replace", (None,))[0],
                ),
            )
            return (
                "Your Girl Asset and its actual paid source are saved. "
                "No additional Permission was charged."
            )

        form = NativeForm(
            viewer.user_id,
            "Write your Creature Comforts Asset",
            clean(data["scene"]["summary"])
            + "\nAll participating humans recorded their attendance. "
            "Write the actual improvement as an ordinary Girl Asset.",
            fields,
            grant,
        )
        await reply(interaction, form.text(), form)
        return
    channel = interaction.channel_id
    if channel:
        try:
            data = await asyncio.to_thread(service.get, viewer, identity, channel)
        except WorkflowError:
            pass
    options: tuple[tuple[str, str], ...] = (
        ("decline", "Decline this unused opportunity — no refund"),
    )
    if data.get("roles") and data.get("locations"):
        options = (("scene", "Record the actual improvement scene"),) + options

    async def choose(current: discord.Interaction, token: str) -> None:
        if token == "decline":

            async def decline(response: discord.Interaction, values: dict[str, Any]) -> str:
                await asyncio.to_thread(
                    service.decline,
                    viewer_from_interaction(response),
                    str(response.id),
                    identity,
                    data["revision"],
                    values["account"],
                )
                return (
                    "You declined this optional opportunity. "
                    "No Asset was granted and the paid Permission was not refunded."
                )

            form = NativeForm(
                viewer.user_id,
                "Decline Creature Comforts opportunity",
                "This is the next qualifying roll for your paid purchase. "
                "Declining closes this optional scene opportunity with no refund. "
                "Silence leaves the choice pending.",
                [
                    Field("account", "Record your own decision", paragraph=True),
                    Field(
                        "confirm",
                        "Confirm decline",
                        (("yes", "Decline this opportunity without a refund"),),
                    ),
                ],
                decline,
            )
        else:
            if channel is None:
                raise WorkflowError("Open the actual improvement scene in its bound channel.")
            bound_channel = channel
            roles = {x["token"]: x for x in data["roles"]}

            async def scene(response: discord.Interaction, values: dict[str, Any]) -> str:
                await asyncio.to_thread(
                    service.record_scene,
                    viewer_from_interaction(response),
                    str(response.id),
                    identity,
                    data["revision"],
                    bound_channel,
                    data["cast_revision"],
                    tuple(ActorRef.model_validate(roles[x]["ref"]) for x in values["participants"]),
                    values["location"][0],
                    values["summary"],
                )
                return (
                    "Your scene and own attendance are saved. "
                    "Other participating humans confirm through /character requests. "
                    "Reopen this opportunity to write the Asset when all attendance is recorded."
                )

            form = NativeForm(
                viewer.user_id,
                "Record actual improvement scene",
                "Record this after playing the improvement scene. "
                "Choose actual characters already at the scene's location, "
                "including your purchasing Girl. "
                "Selected participants see the summary; each human confirms their own attendance.",
                [
                    Field(
                        "location",
                        "Actual scene location",
                        tuple((x["id"], x["name"]) for x in data["locations"]),
                    ),
                    Field(
                        "participants",
                        "Actual participating roles — include your Girl",
                        tuple(
                            (
                                token,
                                role["label"][:65] + " — " + role["ref"]["kind"].replace("_", " "),
                            )
                            for token, role in roles.items()
                        ),
                        1,
                        len(roles),
                    ),
                    Field("summary", "Describe the actual improvement scene", paragraph=True),
                    Field(
                        "confirm",
                        "Your actual participation",
                        (("yes", "The scene happened; I participated"),),
                    ),
                ],
                scene,
            )
        await reply(current, form.text(), form)

    await Picker(
        viewer.user_id,
        "**Your Creature Comforts opportunity**\n"
        "The paid purchase qualified on an actual 8+ Go Off-Duty roll. "
        "Record the optional scene in its bound channel or explicitly decline it.",
        options,
        choose,
    ).show(interaction)
