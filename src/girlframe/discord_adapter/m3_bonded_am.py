"""Actual two-person no-roll Bonded/AM source cards; no invented circuit access."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.services.m3_bonded_am import BondedAMService


async def open_bonded_am(
    interaction: discord.Interaction,
    service: BondedAMService,
    bonded_source: str | None = None,
    identity: str | None = None,
) -> None:
    viewer = viewer_from_interaction(interaction)
    if identity is None and bonded_source is None:
        with service.store.engine.connect() as c:
            rows = service._tasks(c, viewer)
        if not rows:
            await reply(interaction, "No actual Bonded/AM no-roll source for you.")
            return

        async def select(current: discord.Interaction, values: dict[str, Any]) -> None:
            await open_bonded_am(current, service, identity=values["source"][0])

        await NativeForm(
            viewer.user_id,
            "Bonded/AM: original sources",
            "Only your actual participation and saved source are shown.",
            [Field("source", "Actual source", tuple((x["id"], x["label"]) for x in rows))],
            select,
        ).present(interaction)
        return
    if identity is None:
        assert bonded_source is not None
        data = await asyncio.to_thread(service.menu, viewer, bonded_source)
        if data["id"]:
            await open_bonded_am(interaction, service, identity=data["id"])
            return
        if not data["can_start"]:
            await reply(interaction, "The actual Bonded opens her accepted source first.")
            return

        async def start(current: discord.Interaction, values: dict[str, Any]) -> str:
            await asyncio.to_thread(
                service.start,
                viewer_from_interaction(current),
                str(current.id),
                bonded_source,
                data["revision"],
                values["account"],
            )
            return "Actual source opened. Wait for its scene pause before recording performance."

        await NativeForm(
            viewer.user_id,
            "Bonded/AM: actual no-roll source",
            "Your Pair supplies only her genuine Sex rule. You and this actual AM counterpart "
            "keep your bodies and resources. No performance, circuit access or reply is inferred.",
            [Field("account", "Actual source and participants", paragraph=True)],
            start,
        ).present(interaction)
        return
    data = await asyncio.to_thread(service.view, viewer, identity)
    options = []
    if data["can_perform"]:
        options.append(("perform", "Record my actual performed participation"))
    if data["can_withdraw"]:
        options.append(("withdraw", "Withdraw before joint effects"))
    if any(x["pending"] for x in data["unrolled_gender"]):
        options.append(("animal", "Give my actual mandatory Animal Tag"))
    if data["pause"]["retry"]:
        options.append(("retry", "Retry saved scene permissions"))
    summary = (
        "Actual source: " + data["source"]["phase"] + ". No additional roll or resource charge. "
        "Scene pause: " + data["pause"]["state"] + ". " + data["pause"]["error"]
    )
    summary += "\n" + "\n".join(x["account"] for x in data["performances"])
    if not options:
        await reply(interaction, summary)
        return

    async def choose(current: discord.Interaction, values: dict[str, Any]) -> None:
        operation = values["operation"][0]
        if operation == "retry":
            from girlframe.services.p1_source_pause import retry

            await asyncio.to_thread(
                retry, service.game, viewer_from_interaction(current), str(current.id), identity
            )
            await reply(current, "Saved permission recovery requested; reopen this source.")
        elif operation == "animal":
            from girlframe.discord_adapter.p1_unrolled_sex import open_tasks

            await open_tasks(current, service.game, identity)
        elif operation == "withdraw":

            async def withdraw(submitted: discord.Interaction, answer: dict[str, Any]) -> str:
                await asyncio.to_thread(
                    service.withdraw,
                    viewer_from_interaction(submitted),
                    str(submitted.id),
                    identity,
                    data["revision"],
                    answer["account"],
                )
                return (
                    "Source withdrawn without joint effects; saved scene permissions will restore."
                )

            await NativeForm(
                current.user.id,
                "Withdraw actual source",
                "Earlier individual accounts stay saved.",
                [Field("account", "My actual withdrawal", paragraph=True)],
                withdraw,
            ).present(current)
        else:

            async def perform(submitted: discord.Interaction, answer: dict[str, Any]) -> str:
                await asyncio.to_thread(
                    service.perform,
                    viewer_from_interaction(submitted),
                    str(submitted.id),
                    identity,
                    data["revision"],
                    answer["account"],
                    circuits_touched=answer["circuits"][0] == "yes",
                )
                return (
                    "Your own actual performance is recorded. The other person answers for herself."
                )

            await NativeForm(
                current.user.id,
                "My actual performed participation",
                "Record only your own actual participation. If circuits were accessed, use that "
                "actual person's independently eligible Code source; this card grants no circuits.",
                [
                    Field("account", "What I actually performed", paragraph=True),
                    Field(
                        "circuits",
                        "Were either person's circuits actually accessed?",
                        (
                            ("no", "No circuit access occurred"),
                            ("yes", "Circuit access occurred: separate genuine source required"),
                        ),
                    ),
                ],
                perform,
            ).present(current)

    await NativeForm(
        viewer.user_id,
        "Bonded/AM: actual performance",
        summary,
        [Field("operation", "Your actual source control", tuple(options))],
        choose,
    ).present(interaction)
