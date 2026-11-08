"""Private original-person replacement procurement and actual installation."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.services.m3_casualty_replacement import ReplacementService


async def open_replacement(
    interaction: discord.Interaction, service: ReplacementService, identity: str | None = None
) -> None:
    viewer = viewer_from_interaction(interaction)
    if identity is None:
        data = await asyncio.to_thread(service.menu, viewer)
        options = [
            ("request:" + x["id"], "Request replacement: " + x["label"]) for x in data["missing"]
        ]
        options += [(x["id"], x["label"] + " — " + x["phase"]) for x in data["records"]]
        if not options:
            await reply(
                interaction, "No current missing non-Brain component or saved replacement package."
            )
            return

        async def select(current: discord.Interaction, values: dict[str, Any]) -> str | None:
            selected = values["operation"][0]
            if not selected.startswith("request:"):
                await open_replacement(current, service, selected)
                return None
            part = selected.removeprefix("request:")

            async def request(response: discord.Interaction, answer: dict[str, Any]) -> str:
                await asyncio.to_thread(
                    service.request,
                    viewer_from_interaction(response),
                    str(response.id),
                    data["revision"],
                    part,
                    answer["account"],
                )
                return "Request saved. The original Handler can supply and quote a component."

            await NativeForm(
                current.user.id,
                "Request an actual replacement",
                "Request a supplied component for this actual missing part.",
                [Field("account", "Your actual missing-part replacement request", paragraph=True)],
                request,
            ).present(current)
            return None

        await NativeForm(
            interaction.user.id,
            "Casualty: actual replacement packages",
            "Actual replacement packages for your original body.",
            [Field("operation", "Your original source controls", tuple(options))],
            select,
        ).present(interaction)
        return
    data = await asyncio.to_thread(service.view, viewer, identity)
    options = []
    if data["can_quote"]:
        options.append(("quote", "Record actual supplied component and source price"))
    if data["can_install"]:
        options.append(("install", "Confirm actual delivery/installation and pay exact quote"))
    if data["can_request_payment"]:
        options.append(("payment", "Request financial partner's exact quote approval"))
    quote = data["quote"]
    summary = "Original " + data["label"] + ": " + data["phase"] + "."
    if quote:
        summary += (
            " Supplied component: "
            + quote["name"]
            + ". "
            + quote["description"]
            + " Procurement: "
            + quote["procurement"]
            + " Actual quote: "
            + str(quote["price"])
            + " Permission(s)."
        )
    if data["installation"]:
        summary += " Saved installation: " + data["installation"]["account"]
    if data.get("blocked"):
        summary += " " + data["blocked"]
    if not options:
        await reply(interaction, summary)
        return

    async def choose(current: discord.Interaction, values: dict[str, Any]) -> str | None:
        selected = values["operation"][0]
        if selected == "quote":
            fields = [
                Field("name", "Actual identified newly supplied component"),
                Field("description", "Actual suitable hardware and delivery", paragraph=True),
                Field(
                    "procurement",
                    "True procurement/package and source price account",
                    paragraph=True,
                ),
                Field("price", "Actual quoted Permission cost (whole number)"),
            ]
        else:
            fields = [
                Field(
                    "account",
                    "Actual delivery and installation"
                    if selected == "install"
                    else "Your exact source-priced payment request",
                    paragraph=True,
                )
            ]

        async def submit(response: discord.Interaction, answer: dict[str, Any]) -> str:
            actor = viewer_from_interaction(response)
            if selected == "quote":
                await asyncio.to_thread(
                    service.quote,
                    actor,
                    str(response.id),
                    data["revision"],
                    data["id"],
                    answer["name"],
                    answer["description"],
                    answer["procurement"],
                    int(answer["price"]),
                )
                return "Actual supplied component and quote saved."
            assert quote is not None
            if selected == "payment":
                await asyncio.to_thread(
                    service.request_payment,
                    actor,
                    str(response.id),
                    data["revision"],
                    quote["id"],
                    answer["account"],
                )
                return "Payment approval requested. Funds are not reserved."
            await asyncio.to_thread(
                service.install,
                actor,
                str(response.id),
                data["revision"],
                quote["id"],
                answer["account"],
            )
            return "Installation and payment saved. Use cockpit controls to resume piloting."

        await NativeForm(
            current.user.id,
            "Casualty component: " + selected,
            summary + " Record only actual performed facts. Safety pause remains available.",
            fields,
            submit,
        ).present(current)
        return None

    await NativeForm(
        interaction.user.id,
        "Actual replacement: " + data["label"],
        summary,
        [Field("operation", "Your source-owned decision", tuple(options))],
        choose,
    ).present(interaction)
