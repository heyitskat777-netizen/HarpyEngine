"""Private actual travel history; consequences use the original disclosed source."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.ledger import clean
from girlframe.discord_adapter.m2_forms import Field
from girlframe.discord_adapter.m3_memory_pages import MemoryForm, MemoryHistory
from girlframe.discord_adapter.onboarding import reply
from girlframe.services.m3_vatgrown_travel import VatgrownTravelService


async def open_vatgrown_travel(
    interaction: discord.Interaction,
    service: VatgrownTravelService,
    identity: str | None = None,
) -> None:
    viewer = viewer_from_interaction(interaction)
    if identity is None:
        tasks = await asyncio.to_thread(service.menu, viewer)
        if not tasks:
            await reply(
                interaction,
                "Record an actual unchaperoned attempt through /campaign movement first.",
            )
            return

        async def access_menu(current: discord.Interaction) -> None:
            await asyncio.to_thread(service.menu, viewer_from_interaction(current))

        async def choose(current: discord.Interaction, values: dict[str, Any]) -> None:
            await open_vatgrown_travel(current, service, values["source"][0])

        menu = MemoryForm(
            viewer.user_id,
            "Your actual travel sources",
            "Private saved history and choices.",
            [Field("source", "Original attempt", tuple((x["id"], x["label"]) for x in tasks))],
            choose,
            authorize=access_menu,
        )
        await reply(interaction, menu.text(), menu)
        return

    data = await asyncio.to_thread(service.view, viewer, identity)

    async def access(current: discord.Interaction) -> None:
        await asyncio.to_thread(service.view, viewer_from_interaction(current), identity)

    text = "\n".join(
        (
            "**Actual unchaperoned travel**",
            "Original route: "
            + clean(str(data["origin"]))
            + " → "
            + clean(str(data["destination"])),
            "Original account: " + clean(data["account"]),
            "Actual movement: " + ("Recorded" if data["performed_event"] else "Not performed"),
            "Explicit Handler disclosure: "
            + ("Recorded" if data["disclosed_event"] else "Not made"),
            "Optional Handler judgment: " + ("Recorded" if data["judgment_event"] else "Not made"),
        )
    )
    options = []
    if data["can_perform"]:
        options.append(("perform", "Actually perform the original movement"))
    if data["can_disclose"]:
        options.append(("disclose", "Explicitly disclose this source to the Handler"))
    if data["can_judge"]:
        options.append(("judge", "Open the existing optional Handler judgment"))
    if data["discipline"]:
        options.append(("discipline", "Open the actual chosen Punishment"))
    if not options:
        history = MemoryHistory(viewer.user_id, text, access)
        await reply(interaction, history.text(), history)
        return

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str | None:
        operation = values["operation"][0]
        actual_viewer = viewer_from_interaction(current)
        if operation == "perform":
            await asyncio.to_thread(
                service.perform,
                actual_viewer,
                str(current.id),
                identity,
                data["revision"],
            )
            return "Actual movement saved. The rule evidence remains an unchaperoned departure."
        if operation == "disclose":
            await asyncio.to_thread(
                service.disclose,
                actual_viewer,
                str(current.id),
                identity,
                data["revision"],
                values.get("account", ""),
            )
            return "Your explicit private disclosure is saved. The Handler owns any judgment."
        if operation == "judge":
            from girlframe.discord_adapter.m3_vatgrown_plays import open_vatgrown_plays
            from girlframe.services.m3_vatgrown_plays import VatgrownPlaysService

            await open_vatgrown_plays(
                current,
                VatgrownPlaysService(service.game),
                data["violation"],
            )
            return None
        from girlframe.discord_adapter.m3_role_punishments import open_role_punishment
        from girlframe.engine import m3_vatgrown_plays as vat
        from girlframe.services.m2_state import load_state
        from girlframe.services.m3_role_punishments import RolePunishmentService

        await asyncio.to_thread(service.view, actual_viewer, identity)
        with service.store.engine.connect() as c:
            state = load_state(c, service.store.campaign_id)
            discipline = vat.find(state, vat.Discipline, data["discipline"])
        await open_role_punishment(current, RolePunishmentService(service.game), discipline.case)
        return None

    form = MemoryForm(
        viewer.user_id,
        "Original travel source",
        text,
        [
            Field("operation", "Your actual source choice", tuple(options)),
            Field(
                "account",
                "Your explicit disclosure account (if disclosing)",
                paragraph=True,
                required=False,
            ),
        ],
        submit,
        authorize=access,
    )
    await reply(interaction, form.text(), form)
