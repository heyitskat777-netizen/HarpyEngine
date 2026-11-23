"""Private invitation and printed Asset choices for the original new Harpy."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine.creation import AssetChoice
from girlframe.engine.m3_harpy_creation import FRAME_ASSETS, GIRL_ASSETS, Draft
from girlframe.services.m3_harpy_creation import HarpyCreationService
from girlframe.services.onboarding import WorkflowError


async def open_invitation(interaction: discord.Interaction, service: HarpyCreationService) -> None:
    data = await asyncio.to_thread(service.menu, viewer_from_interaction(interaction))

    async def submit(click: discord.Interaction, values: dict[str, Any]) -> str:
        x, y = values["cell"].split(",")
        await asyncio.to_thread(
            service.invite,
            viewer_from_interaction(click),
            str(click.id),
            data["revision"],
            int(values["controller"][0]),
            (int(x), int(y)),
        )
        return "The new Harpy invitation is in the original controller's private Inbox."

    await NativeForm(
        interaction.user.id,
        "Invite a new Harpy controller",
        "Choose the original controller and the Harpy's starting map square.",
        [
            Field("controller", "Original controller", data["members"]),
            Field("cell", "Starting square (x,y)"),
        ],
        submit,
    ).present(interaction)


async def open_creation(
    interaction: discord.Interaction, service: HarpyCreationService, identity: str
) -> None:
    data = await asyncio.to_thread(service.get, viewer_from_interaction(interaction), identity)
    if data["offer"].phase != "offered":
        await reply(interaction, "This original invitation has already been answered.")
        return

    async def choose(click: discord.Interaction, values: dict[str, Any]) -> str | None:
        if values["choice"] == ("decline",):
            await asyncio.to_thread(
                service.respond,
                viewer_from_interaction(click),
                str(click.id),
                identity,
                data["revision"],
                None,
            )
            return "The original invitation is declined."
        girl, frame = values.get("girl", ()), values.get("frame", ())
        if len(girl) != 3 or len(frame) != 4:
            raise WorkflowError("Choose exactly three Harpy Assets and four Frame Assets")
        selected = tuple(
            (x, family) for family, choices in (("girl", girl), ("frame", frame)) for x in choices
        )

        async def submit(final: discord.Interaction, descriptions: dict[str, Any]) -> str:
            resources: dict[str, list[AssetChoice]] = {"girl": [], "frame": []}
            for index, (name, family) in enumerate(selected):
                resources[family].append(
                    AssetChoice(name=name, description=descriptions[str(index)])
                )
            draft = Draft.model_validate(
                dict(
                    name=descriptions["name"],
                    girl=tuple(resources["girl"]),
                    frame=tuple(resources["frame"]),
                )
            )
            await asyncio.to_thread(
                service.respond,
                viewer_from_interaction(final),
                str(final.id),
                identity,
                data["revision"],
                draft,
            )
            return "Your Harpy and starting Assets are saved. Review the runtime before a Play."

        await NativeForm(
            click.user.id,
            "Describe your original Harpy",
            "Describe the selected Assets.",
            [
                Field("name", "Harpy name"),
                *[
                    Field(str(i), name, paragraph=True)
                    for i, (name, _family) in enumerate(selected)
                ],
            ],
            submit,
        ).present(click)
        return None

    form = NativeForm(
        interaction.user.id,
        "New Harpy invitation",
        "Choose your actual starting Assets or decline.",
        [
            Field(
                "choice",
                "Your response",
                (("accept", "Accept and choose Assets"), ("decline", "Decline")),
            ),
            Field(
                "girl",
                "Three Harpy Assets",
                tuple((x, x) for x in GIRL_ASSETS),
                0,
                3,
                required=False,
            ),
            Field(
                "frame",
                "Four Frame Assets",
                tuple((x, x) for x in FRAME_ASSETS),
                0,
                4,
                required=False,
            ),
        ],
        choose,
    )
    await form.present(interaction)
