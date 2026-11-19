"""The original Rebel opens the attack from the actual mission scene."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine.m2 import IdentityState
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.services.m3_actors import ActorService
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_rebel_ambush import AmbushService, HuntService, SiegeService


async def open_ambush(
    interaction: discord.Interaction,
    service: AmbushService,
    identity: str,
) -> None:
    channel = int(interaction.channel_id or 0)
    data = await asyncio.to_thread(
        service.get, viewer_from_interaction(interaction), identity, channel
    )
    siege = data["siege"]
    if data["complete"]:
        await reply(interaction, "The original attack is complete.")
        return
    if data.get("inventory_actor"):
        actor = ActorRef.model_validate(data["inventory_actor"])

        async def confirm_inventory(click: discord.Interaction, values: dict[str, Any]) -> str:
            names = tuple(x.strip() for x in values.get("identities", "").splitlines() if x.strip())
            await asyncio.to_thread(
                ActorService(MissionService(service.store)).confirm_rebel_inventory,
                viewer_from_interaction(click),
                str(click.id),
                data["revision"],
                actor,
                tuple(
                    IdentityState(id=f"{actor.token}:identity:{i}", name=x, slot=i)
                    for i, x in enumerate(names)
                ),
                int(values["heat"]),
                values["account"],
                actual=True,
                siege_case=identity,
            )
            return "Resources and piloting saved. Reopen the attack in the siege scene."

        await NativeForm(
            interaction.user.id,
            "Confirm your original siege Pilot",
            "Confirm your own Rebel's starting resources and presence in the Frame at the base.",
            [
                Field(
                    "identities",
                    "Up to four existing Identities, one per line",
                    paragraph=True,
                    required=False,
                ),
                Field("heat", "Current Heat"),
                Field("account", "Describe the actual piloting and combat opening", paragraph=True),
            ],
            confirm_inventory,
        ).present(interaction)
        return
    if data["opened"]:
        await reply(interaction, "Use the original scene's battle control to resolve the Assault.")
        return
    if not data["targets"]:
        await reply(
            interaction,
            "The original Rebel can open the attack in the actual base scene."
            if siege
            else "The original Rebel can open the attack in the actual mission scene.",
        )
        return

    async def submit(click: discord.Interaction, values: dict[str, Any]) -> str:
        await asyncio.to_thread(
            service.open,
            viewer_from_interaction(click),
            str(click.id),
            identity,
            data["revision"],
            channel,
            values["target"][0],
            values["account"],
        )
        return (
            "The opening is recorded. Declare the Assault against this Girl in the battle control."
        )

    await NativeForm(
        interaction.user.id,
        "Open a Rebel siege attack" if siege else "Open the original ambush",
        "Confirm the original Ace your Rebel is attacking."
        if siege
        else "Choose an original mission participant you are attempting to capture.",
        [
            Field("target", "Original Girl", data["targets"]),
            Field("account", "Describe your actual ambush", paragraph=True),
        ],
        submit,
    ).present(interaction)


async def open_siege(
    interaction: discord.Interaction, service: SiegeService, identity: str
) -> None:
    data = await asyncio.to_thread(service.get, viewer_from_interaction(interaction), identity)
    text = f"Resolved Rebel attacks: {data['resolved']} of {data['total']}."
    if data["complete"] or data["resolved"] != data["total"]:
        await reply(interaction, text)
        return

    async def submit(click: discord.Interaction, _values: dict[str, Any]) -> str:
        await asyncio.to_thread(
            service.finish,
            viewer_from_interaction(click),
            str(click.id),
            identity,
            data["revision"],
        )
        return "The siege is resolved. Reopen Off-Duty for any remaining work."

    await NativeForm(
        interaction.user.id,
        "Finish the Rebel siege",
        text,
        [Field("decision", "Siege outcome", (("finish", "Confirm completed attacks"),))],
        submit,
    ).present(interaction)


async def open_hunt(
    interaction: discord.Interaction,
    service: HuntService,
    identity: str,
) -> None:
    data = await asyncio.to_thread(service.get, viewer_from_interaction(interaction), identity)
    status = "The original pursuit has ended." if data["ended"] else "The pursuit remains active."
    text = status + f" Resolved attempts: {data['attempts']}."
    if data["proposal"]:
        text += "\n\n" + discord.utils.escape_mentions(data["proposal"])
    if not data["choices"]:
        await reply(interaction, text)
        return

    async def submit(click: discord.Interaction, values: dict[str, Any]) -> str:
        result = await asyncio.to_thread(
            service.respond,
            viewer_from_interaction(click),
            str(click.id),
            identity,
            data["revision"],
            values["choice"][0],
            values["account"],
        )
        return (
            "The original pursuit has ended." if result["ended"] else "The pursuit remains active."
        )

    await NativeForm(
        interaction.user.id,
        "Review the Rebel pursuit",
        text,
        [
            Field("choice", "Your decision", data["choices"]),
            Field("account", "Your own account", paragraph=True),
        ],
        submit,
    ).present(interaction)
