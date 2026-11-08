"""Private native award purchase and two actual participants' dressing controls."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.services.m3_cute_uniforms import CuteUniformService


async def open_uniforms(interaction: discord.Interaction, service: CuteUniformService) -> None:
    data = await asyncio.to_thread(service.menu, viewer_from_interaction(interaction))
    if not data["owned"]:
        if not data["awards"]:
            await reply(interaction, "Cute Uniforms costs one actual held Handler advancement.")
            return

        async def buy(current: discord.Interaction, values: dict[str, Any]) -> str:
            await asyncio.to_thread(
                service.buy,
                viewer_from_interaction(current),
                str(current.id),
                values["award"][0],
                data["revision"],
                values["account"],
            )
            return "Cute Uniforms acquired. One advancement spent; no Permissions charged."

        await NativeForm(
            interaction.user.id,
            "Acquire Cute Uniforms",
            "Spend one actual held Handler advancement.",
            [
                Field(
                    "award",
                    "Actual held advancement",
                    tuple(
                        (x["id"], x["rule"].replace("strain.void.endgame.", "Void Endgame "))
                        for x in data["awards"]
                    ),
                ),
                Field("account", "Record this actual acquisition", paragraph=True),
            ],
            buy,
        ).present(interaction)
        return
    if not data["targets"]:
        await reply(interaction, "No actual current original Girl is available.")
        return

    async def propose(current: discord.Interaction, values: dict[str, Any]) -> str:
        target = next(x for x in data["targets"] if x["token"] == values["target"][0])
        await asyncio.to_thread(
            service.propose,
            viewer_from_interaction(current),
            str(current.id),
            data["revision"],
            ActorRef.model_validate(target["actor"]),
            values["name"],
            values["description"],
            values["present"][0] == "present",
        )
        return (
            "Dressing proposed. The Girl must confirm the actual dressing "
            "and co-presence in its requests."
        )

    await NativeForm(
        interaction.user.id,
        "Actually dress a Girl in a cute uniform",
        "You must actually be present with the Girl at its known location. "
        "Status and clothing change only after the Girl confirms the actual dressing.",
        [
            Field(
                "target",
                "Actual original Girl",
                tuple((x["token"], x["label"]) for x in data["targets"]),
            ),
            Field("name", "Uniform name"),
            Field("description", "Describe the actual uniform and dressing", paragraph=True),
            Field(
                "present",
                "Original Handler's actual physical presence",
                (("present", "I am actually present with this Girl"),),
            ),
        ],
        propose,
    ).present(interaction)


async def open_uniform(
    interaction: discord.Interaction, service: CuteUniformService, identity: str
) -> None:
    data = await asyncio.to_thread(service.view, viewer_from_interaction(interaction), identity)
    if data["phase"] == "worn" and str(interaction.user.id) == data["target"]:

        async def doff(current: discord.Interaction, values: dict[str, Any]) -> str:
            await asyncio.to_thread(
                service.wearing,
                viewer_from_interaction(current),
                str(current.id),
                identity,
                data["revision"],
                values["account"],
                not data["wearing"],
            )
            return "Actual clothing change recorded; no Tag rejection or Handler dressing occurred."

        await NativeForm(
            interaction.user.id,
            "Record actually taking off the uniform"
            if data["wearing"]
            else "Record actually putting the uniform back on",
            data["name"]
            + ". Record only an actual completed clothing change. This does not reject its Tag "
            "or trigger Punishment.",
            [
                Field(
                    "done",
                    "Actual completed clothing change",
                    (
                        (
                            "changed",
                            "I actually took it off"
                            if data["wearing"]
                            else "I actually put it back on",
                        ),
                    ),
                ),
                Field("account", "Describe the actual clothing change", paragraph=True),
            ],
            doff,
        ).present(interaction)
        return
    if data["phase"] != "proposed" or str(interaction.user.id) != data["target"]:
        await reply(interaction, f"{data['name']} — {data['phase']}. {data['description']}")
        return

    async def confirm(current: discord.Interaction, values: dict[str, Any]) -> str:
        accept = values["actual"][0] == "actual"
        await asyncio.to_thread(
            service.confirm,
            viewer_from_interaction(current),
            str(current.id),
            identity,
            data["revision"],
            accept,
            values["account"],
        )
        return (
            "Actual dressing confirmed; Status lowered and the worn uniform's rules now apply."
            if accept
            else "Proposal declined. No dressing, Status change or Punishment occurred."
        )

    await NativeForm(
        interaction.user.id,
        "Confirm actual uniform dressing",
        data["name"]
        + ": "
        + data["description"]
        + ". Confirm only actual completed dressing with your original Handler physically present. "
        "Leaving this form does nothing.",
        [
            Field(
                "actual",
                "Actual physical event",
                (
                    ("actual", "Handler was here and actually dressed me"),
                    ("decline", "This dressing did not happen"),
                ),
            ),
            Field("account", "Describe the actual event or declined proposal", paragraph=True),
        ],
        confirm,
    ).present(interaction)
