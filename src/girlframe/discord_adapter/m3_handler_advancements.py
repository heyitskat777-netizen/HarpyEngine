"""Original Handler award review and explicit selected-group Permission spend."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.ledger import clean
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine.m3_handler_advancements import PermissionGrant
from girlframe.services.m3_handler_advancements import HandlerAdvancementService
from girlframe.services.onboarding import WorkflowError


async def open_advancement(
    interaction: discord.Interaction, service: HandlerAdvancementService, identity: str
) -> None:
    data = await asyncio.to_thread(service.view, viewer_from_interaction(interaction), identity)
    if data.get("acquired_rule"):
        await reply(
            interaction,
            "This advancement acquired "
            + (
                "Cute Uniforms"
                if data["acquired_rule"].endswith("cute-uniforms")
                else "Girl Insurance"
                if data["acquired_rule"].endswith("girl-insurance")
                else "Supply Drop"
            )
            + ". Its original acquisition source is saved; open the acquired rule to use it.",
        )
        return
    if data["phase"] == "spent":
        grants = "\n".join(
            f"{clean(x['label'])}: +{x['amount']} Permissions ({x['before']} → {x['after']})"
            for x in data["effects"]
        )
        embeds = [
            discord.Embed(title="Actual Permission grants", description=grants),
            discord.Embed(title="Original award", description=clean(data["account"])),
            discord.Embed(
                title="Original advancement spend", description=clean(data["spend_account"])
            ),
        ]
        content = "**Handler advancement spent**\nVoid Endgame " + data["rule"].rsplit(".", 1)[1]
        if interaction.response.is_done():
            await interaction.edit_original_response(
                content=content,
                embeds=embeds,
                view=None,
                allowed_mentions=discord.AllowedMentions.none(),
            )
        else:
            await interaction.response.send_message(
                content,
                embeds=embeds,
                ephemeral=True,
                allowed_mentions=discord.AllowedMentions.none(),
            )
        return
    if not data["current"]:
        await reply(
            interaction,
            "This original Handler's advancement source is saved. "
            "Recover its original appointment and finish any pending Play before using it.",
        )
        return
    if data["phase"] == "claim":

        async def claim(current: discord.Interaction, values: dict[str, Any]) -> str:
            await asyncio.to_thread(
                service.claim_void,
                viewer_from_interaction(current),
                str(current.id),
                identity,
                data["revision"],
                data["work_revision"],
                values["account"],
            )
            return "Your actual Handler advancement is held. Reopen requests to keep or spend it."

        await NativeForm(
            interaction.user.id,
            "Void Endgame — take a Handler advancement",
            "Take this original source award once. "
            "Taking it does not spend it or grant Permissions yet.",
            [
                Field(
                    "claim",
                    "Take this actual source award",
                    (("claim", "Take one Handler advancement"),),
                ),
                Field("account", "Describe this actual award", paragraph=True),
            ],
            claim,
        ).present(interaction)
        return
    if not data["candidates"]:
        raise WorkflowError("No actual current Girls are available for this Permission grant")

    async def select(current: discord.Interaction, values: dict[str, Any]) -> None:
        selected = [x for x in data["candidates"] if x["token"] in values["girls"]]
        await open_grant(current, service, data, selected)

    form = NativeForm(
        interaction.user.id,
        "Spend Handler advancement — Permissions",
        "Choose any number of your actual Girls. One advancement covers the whole selected group, "
        "with one or two Permissions each. Keep it unspent by leaving this form.",
        [
            Field(
                "girls",
                "Actual Girls receiving Permissions",
                tuple((x["token"], x["label"]) for x in data["candidates"]),
                1,
                len(data["candidates"]),
            )
        ],
        select,
    )
    form.add_item(AcquireSupplyDrop(form, service))
    form.add_item(AcquireCuteUniforms(form, service))
    form.add_item(AcquireGirlInsurance(form, service))
    await form.present(interaction)


async def open_grant(
    interaction: discord.Interaction,
    service: HandlerAdvancementService,
    data: dict[str, Any],
    selected: list[dict[str, Any]],
) -> None:
    if not selected:
        raise WorkflowError("Choose at least one actual original Girl")
    fields = [
        Field(
            x["token"],
            x["label"] + " — Permissions",
            (("1", "One Permission"), ("2", "Two Permissions")),
        )
        for x in selected
    ]
    fields.append(Field("account", "Describe this actual group grant", paragraph=True))

    async def spend(current: discord.Interaction, values: dict[str, Any]) -> str:
        grants = tuple(
            PermissionGrant.model_validate(
                dict(actor=x["actor"], amount=int(values[x["token"]][0]))
            )
            for x in selected
        )
        await asyncio.to_thread(
            service.spend_permissions,
            viewer_from_interaction(current),
            str(current.id),
            data["id"],
            data["revision"],
            grants,
            values["account"],
        )
        return (
            "One advancement spent. The selected original Girls received their actual Permissions."
        )

    # Selected ActorRefs and game revision remain frozen through the exact final review.
    await NativeForm(
        interaction.user.id,
        "Confirm advancement Permission grants",
        "One advancement is consumed only when you confirm all selected amounts. "
        + ", ".join(clean(x["label"]) for x in selected),
        fields,
        spend,
    ).present(interaction)


class AcquireSupplyDrop(discord.ui.Button[NativeForm]):
    def __init__(self, form: NativeForm, service: HandlerAdvancementService):
        super().__init__(label="Acquire Supply Drop instead", row=3)
        self.form, self.service = form, service

    async def callback(self, interaction: discord.Interaction) -> None:
        if not await self.form.interaction_check(interaction):
            return
        from girlframe.discord_adapter.m3_supply_drop import open_supply_drop
        from girlframe.services.m3_supply_drop import SupplyDropService

        await open_supply_drop(interaction, SupplyDropService(self.service.store))


class AcquireCuteUniforms(discord.ui.Button[NativeForm]):
    def __init__(self, form: NativeForm, service: HandlerAdvancementService):
        super().__init__(label="Acquire Cute Uniforms instead", row=3)
        self.form, self.service = form, service

    async def callback(self, interaction: discord.Interaction) -> None:
        if not await self.form.interaction_check(interaction):
            return
        from girlframe.discord_adapter.m3_cute_uniforms import open_uniforms
        from girlframe.services.m3_cute_uniforms import CuteUniformService

        await open_uniforms(interaction, CuteUniformService(self.service.store))


class AcquireGirlInsurance(discord.ui.Button[NativeForm]):
    def __init__(self, form: NativeForm, service: HandlerAdvancementService):
        super().__init__(label="Acquire Girl Insurance instead", row=3)
        self.form, self.service = form, service

    async def callback(self, interaction: discord.Interaction) -> None:
        if not await self.form.interaction_check(interaction):
            return
        from girlframe.discord_adapter.m3_girl_insurance import open_insurance
        from girlframe.services.m3_girl_insurance import GirlInsuranceService

        await open_insurance(interaction, GirlInsuranceService(self.service.store))
