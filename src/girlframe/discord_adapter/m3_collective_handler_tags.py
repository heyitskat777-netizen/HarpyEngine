"""Actual collective proposals and private exact-label agreement controls."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.ledger import clean
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.services.m3_collective_handler_tags import CollectiveTagService


async def open_collective(
    interaction: discord.Interaction, service: CollectiveTagService, identity: str
) -> None:
    view = await asyncio.to_thread(service.view, viewer_from_interaction(interaction), identity)
    mode = view["state"]
    if mode == "ending_install":

        async def original_ended(current: discord.Interaction, values: dict[str, Any]) -> str:
            await asyncio.to_thread(
                service.close_uninstalled,
                viewer_from_interaction(current),
                str(current.id),
                identity,
                view["expected"],
            )
            return "The actual original Handler's ending is recorded against this Endgame."

        form = NativeForm(
            interaction.user.id,
            "Original Endgame Handler ended",
            "Review the actual original ending; the successor receives no inherited entitlement.",
            [Field("confirm", "Review actual ending", (("close", "Record actual source ending"),))],
            original_ended,
        )
    elif mode == "install":

        async def install(current: discord.Interaction, values: dict[str, Any]) -> str:
            await asyncio.to_thread(
                service.install,
                viewer_from_interaction(current),
                str(current.id),
                identity,
                view["expected"],
            )
            return (
                "The original Endgame is recorded. "
                "Actual Off-Duty opportunities appear in the Girls' requests."
            )

        form = NativeForm(
            interaction.user.id,
            "Collective Handler Tag Endgame",
            "Record future collective Tag opportunities for this original Handler.",
            [
                Field(
                    "confirm",
                    "Record actual Endgame",
                    (("record", "Record this selected Endgame"),),
                )
            ],
            install,
        )
    elif mode == "available":

        async def propose(current: discord.Interaction, values: dict[str, Any]) -> str:
            result = await asyncio.to_thread(
                service.propose,
                viewer_from_interaction(current),
                str(current.id),
                view["entitlement"],
                view["period"],
                view["expected"],
                values["tag"],
                values["account"],
            )
            return (
                "Collective Tag saved."
                if result["state"] == "given"
                else "Your exact proposal awaits the other original Girls' private agreements."
            )

        form = NativeForm(
            interaction.user.id,
            "Propose a collective Handler Tag",
            "This is optional. Every original Girl must agree to this exact wording. "
            "The proposal awaits their decisions.",
            [
                Field("tag", "Proposed Tag"),
                Field("account", "Describe the collective gift", paragraph=True),
            ],
            propose,
        )
    elif mode in ("proposed", "ending_review") and view.get("original_ended"):

        async def endings(current: discord.Interaction, values: dict[str, Any]) -> str:
            result = await asyncio.to_thread(
                service.review_endings,
                viewer_from_interaction(current),
                str(current.id),
                identity,
                view["expected"],
            )
            return "Actual original endings recorded. Proposal state: " + str(result["state"])

        form = NativeForm(
            interaction.user.id,
            "Review original participants",
            "Only proved original endings change this proposal. "
            "A successor does not supply their consent.",
            [
                Field(
                    "confirm",
                    "Review actual endings",
                    (("review", "Record the actual original endings"),),
                )
            ],
            endings,
        )
    elif mode == "proposed":
        options: tuple[tuple[str, str], ...] = (
            (("agree", "Agree to this exact Tag"),) if view["can_agree"] else ()
        )
        options += (("decline", "Decline this collective gift"),)
        if view["can_withdraw"]:
            options += (("withdraw", "Withdraw my proposal"),)

        async def respond(current: discord.Interaction, values: dict[str, Any]) -> str:
            result = await asyncio.to_thread(
                service.respond,
                viewer_from_interaction(current),
                str(current.id),
                identity,
                view["expected"],
                values["decision"][0],
            )
            return "Your decision is recorded. Collective proposal: " + str(result["state"])

        form = NativeForm(
            interaction.user.id,
            "Collective Handler Tag agreement",
            "Proposed Tag: "
            + clean(view["proposal"]["label"])
            + "\n"
            + clean(view["proposal"]["account"]),
            [Field("decision", "Your own decision", options)],
            respond,
        )
    else:
        await reply(interaction, "This original collective Tag opportunity is " + str(mode) + ".")
        return
    await reply(interaction, form.text(), form)
