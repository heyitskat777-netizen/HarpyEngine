"""Private actual branch birth, prepared source review and irreversible owner takeover."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine.m2 import ChoiceAnswer
from girlframe.services.m2_game import GameService
from girlframe.services.m3_am_branch import BranchService


async def open_choice(interaction: discord.Interaction, game: GameService, identity: str) -> None:
    data = await asyncio.to_thread(game.decision, viewer_from_interaction(interaction), identity)
    detail = data["am_code"]
    bodies = detail["branch"]["bodies"]
    if not bodies:
        from girlframe.discord_adapter.m3_am_body import open_prepare
        from girlframe.services.m3_am_body import BodyService

        await open_prepare(interaction, BodyService(game), detail["maintenance"])
        return

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        await asyncio.to_thread(
            game.respond,
            viewer_from_interaction(current),
            str(current.id),
            identity,
            data["revision"],
            ChoiceAnswer(options=tuple(values["body"]), text=values["account"]),
        )
        return (
            "Actual independent NPC branch created in that prepared vessel. "
            "Saved branch controls are private."
        )

    form = NativeForm(
        interaction.user.id,
        "Original operator: create actual AM branch",
        "Use actual prepared processing hardware. The new independent NPC "
        "is controlled by the Handler, "
        "with the Guard NPC rules and no supplied weapon. No original "
        "hardware, balances or private notes are copied.",
        [
            Field(
                "body", "Actual empty local vessel", tuple((x["id"], x["label"]) for x in bodies)
            ),
            Field("account", "Actual circuit branching and placement", paragraph=True),
        ],
        submit,
    )
    await reply(interaction, form.text(), form)


async def open_branch(
    interaction: discord.Interaction, service: BranchService, identity: str | None = None
) -> None:
    viewer = viewer_from_interaction(interaction)
    if identity is None:
        menu = await asyncio.to_thread(service.menu, viewer)
        options = tuple((x["id"], x["label"]) for x in menu["branches"])
        if not options:
            await reply(interaction, "No actual AM branch belongs to this role.")
            return

        async def select(current: discord.Interaction, values: dict[str, Any]) -> None:
            await open_branch(current, service, values["branch"][0])

        form = NativeForm(
            interaction.user.id,
            "Actual AM branches",
            "Saved independent branches and optional takeover.",
            [Field("branch", "Actual branch", options)],
            select,
        )
        await reply(interaction, form.text(), form)
        return
    data = await asyncio.to_thread(service.view, viewer, identity)
    body = data["body"]
    assets = ", ".join(x["name"] + (" [damaged]" if x["damaged"] else "") for x in body["assets"])
    text = f"Actual vessel {body['vessel']}: {assets or 'no physical Assets'}; {body['medical']}."
    if data["active"]:
        await reply(
            interaction,
            text + " Same branch is now your Girl; the original mind remains terminated.",
        )
        return
    if data["controller"]:

        async def assign(current: discord.Interaction, values: dict[str, Any]) -> str:
            await asyncio.to_thread(
                service.assign,
                viewer_from_interaction(current),
                str(current.id),
                identity,
                data["revision"],
                int(values["position"][0]),
                values["account"],
            )
            return (
                "Actual existing Frame and resulting Status recorded. Only the "
                "original player may take over."
            )

        form = NativeForm(
            interaction.user.id,
            "Actual branch takeover preparation",
            text + " Record the actual available original Enforcer Frame and "
            "resulting position; both must be colocated and unoccupied. "
            "This factual review supplies no veto over the player's printed choice.",
            [
                Field(
                    "position",
                    "Actual new Girl position",
                    tuple((str(x), str(x + 1)) for x in data["positions"]),
                ),
                Field(
                    "account", "Actual existing Frame assignment and Status facts", paragraph=True
                ),
            ],
            assign,
        )
        await reply(interaction, form.text(), form)
        return
    if not data["ready"]:
        await reply(
            interaction,
            text + " Independent NPC branch remains active. Actual Frame/Status "
            "preparation is not recorded.",
        )
        return

    async def takeover(current: discord.Interaction, values: dict[str, Any]) -> str:
        await asyncio.to_thread(
            service.takeover,
            viewer_from_interaction(current),
            str(current.id),
            identity,
            data["revision"],
        )
        return (
            "You are this actual branch as your new Girl. The original mind "
            "is irreversibly terminated."
        )

    form = NativeForm(
        interaction.user.id,
        "Original player: take over actual branch",
        text + " Taking over terminates the original permanently; no original "
        "restoration or copied balances. "
        "The branch keeps its actual postbirth state and receives the existing prepared Frame.",
        [
            Field(
                "takeover",
                "Irreversible printed choice",
                (("yes", "Take over branch; terminate original mind"),),
            )
        ],
        takeover,
    )
    await reply(interaction, form.text(), form)
