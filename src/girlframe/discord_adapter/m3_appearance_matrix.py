"""One actual native Class purchase, reviewed privately before the two-Permission payment."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.services.m3_appearance_matrix import MatrixService
from girlframe.services.onboarding import WorkflowError


async def open_matrix(
    interaction: discord.Interaction, service: MatrixService, *, channel: int | None = None
) -> None:
    channel = channel if channel is not None else int(interaction.channel_id or 0)
    data = await asyncio.to_thread(service.view, viewer_from_interaction(interaction), channel)
    if not data["context"]:
        if not data["gm"]:
            await reply(
                interaction, "The source GM must record this real scene/location context first."
            )
            return

        async def record(current: discord.Interaction, values: dict[str, Any]) -> str:
            await asyncio.to_thread(
                service.record_context,
                viewer_from_interaction(current),
                str(current.id),
                channel,
                data["revision"],
                values["location"][0],
            )
            return "Actual scene location recorded. The original Matrix owner now controls her use."

        await NativeForm(
            interaction.user.id,
            "Matrix: factual scene location",
            "Record where this actual open scene is taking place. This does not move anyone, "
            "approve an ability use, change history or supply another person's consent.",
            [
                Field(
                    "location",
                    "Actual introduced scene location",
                    tuple((x["id"], x["label"]) for x in data["locations"]),
                )
            ],
            record,
        ).present(interaction)
        return
    if data["absent"]:
        from girlframe.discord_adapter.m3_physical import open_initial
        from girlframe.services.m3_physical import PhysicalService

        await open_initial(interaction, PhysicalService(service.store))
        return
    if not data["owned"] or data["marked"]:
        await reply(
            interaction,
            "No unmarked owned Matrix is available. Its actual Go-Off-Duty start refreshes it.",
        )
        return

    async def choose(current: discord.Interaction, values: dict[str, Any]) -> str | None:
        from typing import cast

        from girlframe.engine.m3_appearance_matrix import Mode

        mode = cast(Mode, values["mode"][0])
        preview = await asyncio.to_thread(
            service.preview, viewer_from_interaction(current), data["context"], mode
        )
        repaired = (
            "; ".join(x["label"] for x in preview["repaired"])
            or "None: no eligible source-attributed damage"
        )

        async def use(actual: discord.Interaction, answer: dict[str, Any]) -> str:
            result = await asyncio.to_thread(
                service.use,
                viewer_from_interaction(actual),
                str(actual.id),
                data["context"],
                preview["revision"],
                mode,
            )
            return (
                "Matrix marked. Actual "
                + ("scene entry" if mode == "appear" else "absence with unknown endpoint")
                + " committed; "
                + str(len(result["repaired"]))
                + " actual Assets undamaged. "
                "Prior memories and consequences remain. "
                "Contradictory memories are added."
            )

        await NativeForm(
            current.user.id,
            "Matrix: exact actual result",
            f"Mode: {mode}. Destination: {preview['destination'] or 'unknown/offstage'}. "
            f"Actual source-attributed undamage: {repaired}. "
            "The mark is spent once. Tags, Status, Void, Identities and prior memories remain. "
            "After disappearing, record your actual location through physical placement review.",
            [
                Field(
                    "confirm",
                    "Commit this exact original-owned effect",
                    (("yes", "Mark Matrix and apply"),),
                )
            ],
            use,
        ).present(current)
        return None

    await NativeForm(
        interaction.user.id,
        "Appearance Matrix: original owned source",
        "Choose actual scene entry or absence. Complete pending original Plays first. "
        "The source GM's factual location is already recorded; no second approval is required.",
        [
            Field(
                "mode",
                "Actual printed scene effect",
                (("appear", "Always been here"), ("disappear", "Never been here")),
            )
        ],
        choose,
    ).present(interaction)


async def open_purchase(interaction: discord.Interaction, service: MatrixService) -> None:
    data = await asyncio.to_thread(service.menu, viewer_from_interaction(interaction))
    if not data["available"]:
        raise WorkflowError("No reviewed Appearance Matrix acquisition is available")
    if data["suspended"]:
        await reply(
            interaction, "This Class Requisition is suspended. Restore its original paid source."
        )
        return
    if data["owned"]:
        await open_matrix(interaction, service)
        return

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        await asyncio.to_thread(
            service.buy,
            viewer_from_interaction(current),
            str(current.id),
            data["revision"],
            ActorRef.model_validate(data["actor"]),
            data["frame"],
            values["account"],
            values["donor"][0] if data["donors"] else None,
        )
        return (
            f"Appearance Matrix acquired for {data['price']} Permissions."
            " Open Appearance Matrix in the actual scene."
        )

    await NativeForm(
        interaction.user.id,
        f"Appearance Matrix — {data['kind'].replace('_', ' ').title()}, "
        f"{data['price']} Permissions",
        "Original-source Appearance Matrix. Mark once for true scene entry/absence and "
        "source-attributed scene Asset undamage; ordinary Off-Duty start refreshes it.",
        (
            [Field("donor", "Choose the actual donor Frame", tuple((x, x) for x in data["donors"]))]
            if data["donors"]
            else []
        )
        + [Field("account", "Record the actual acquisition", paragraph=True)],
        submit,
    ).present(interaction)
