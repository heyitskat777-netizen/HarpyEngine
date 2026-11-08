"""Human-owned scheduling and actual same-battle unavoidable-loss selections."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_fuel_shortage import LossSelection
from girlframe.services.m3_fuel_shortage import FuelService
from girlframe.services.onboarding import WorkflowError


def battle_fields(data: dict[str, Any]) -> list[Field]:
    """Only the actual reviewed Context's source-owned options, added to its form."""
    fields = []
    for index, source in enumerate(data["arms"], 1):
        prefix = "fuel:" + source["id"] + ":"
        if source["npcs"]:
            fields.append(
                Field(
                    prefix + "npc",
                    f"Fuel shortage {index}: actual NPC killed",
                    tuple((x["ref"]["entity"], x["label"]) for x in source["npcs"]),
                    0,
                    1,
                    required=False,
                )
            )
        if source["locations"]:
            fields.append(
                Field(
                    prefix + "site",
                    f"Fuel shortage {index}: actual site destroyed",
                    tuple((x["id"], x["label"]) for x in source["locations"]),
                    0,
                    1,
                    required=False,
                )
            )
        fields.append(
            Field(
                prefix + "account",
                f"Fuel shortage {index}: actual unavoidable loss",
                paragraph=True,
            )
        )
    return fields


def battle_losses(data: dict[str, Any], values: dict[str, Any]) -> tuple[LossSelection, ...]:
    result = []
    for source in data["arms"]:
        prefix = "fuel:" + source["id"] + ":"
        npc = tuple(values.get(prefix + "npc", ()))
        site = tuple(values.get(prefix + "site", ()))
        people = {x["ref"]["entity"]: x["ref"] for x in source["npcs"]}
        locations = {x["id"] for x in source["locations"]}
        if (
            len(npc) > 1
            or len(site) > 1
            or (npc and npc[0] not in people)
            or (site and site[0] not in locations)
        ):
            raise WorkflowError("Choose an actual available body/site from this battle source")
        result.append(
            LossSelection(
                source=source["id"],
                npc=ActorRef.model_validate(people[npc[0]]) if npc else None,
                location=site[0] if site else None,
                account=str(values.get(prefix + "account", "")),
            )
        )
    return tuple(result)


async def open_fuel_shortage(
    interaction: discord.Interaction, service: FuelService, identity: str | None = None
) -> None:
    viewer = viewer_from_interaction(interaction)
    if identity is None:
        with service.store.engine.connect() as c:
            sources = service._tasks(c, viewer)
        if not sources:
            await reply(interaction, "No saved fuel-shortage source belongs to this role.")
            return

        async def choose(current: discord.Interaction, values: dict[str, Any]) -> None:
            await open_fuel_shortage(current, service, values["source"][0])

        form = NativeForm(
            interaction.user.id,
            "Your actual fuel-shortage sources",
            "Read the original scheduling and real battle-loss records.",
            [
                Field(
                    "source",
                    "Actual source",
                    tuple(
                        (x["id"], f"Fuel shortage {index}: {x['phase']}")
                        for index, x in enumerate(sources, 1)
                    ),
                )
            ],
            choose,
        )
        await reply(interaction, form.text(), form)
        return
    data = await asyncio.to_thread(service.view, viewer, identity)
    if data["can_arm"]:

        async def arm(current: discord.Interaction, values: dict[str, Any]) -> str:
            await asyncio.to_thread(
                service.arm,
                viewer_from_interaction(current),
                str(current.id),
                identity,
                data["revision"],
            )
            return (
                "The actual fuel shortage is armed for the next genuine Cadre battle. "
                "A mission alone does not spend it. The adjudicator must record a real "
                "unavoidable loss before that battle can proceed."
            )

        form = NativeForm(
            interaction.user.id,
            "Fuel shortage — actual next battle",
            "Save this selected Strain consequence as a real future-battle obligation. "
            "No target or outcome is invented now; arming does not prevent the printed loss.",
            [Field("operation", "Actual scheduling", (("arm", "Arm the next real battle delay"),))],
            arm,
        )
        await reply(interaction, form.text(), form)
        return
    value = data["record"]
    if value["battle"] is None:
        text = (
            "Fuel shortage — armed. The next subsequent actual Cadre battle declaration "
            "must receive its real unavoidable loss at confirmation. "
            "Ordinary mission activity does not consume this source."
        )
    else:
        outcomes = []
        if value["original_npc"]:
            outcomes.append(value["original_npc"]["name"] + " was killed")
        if value["original_location"]:
            outcomes.append(value["original_location"]["name"] + " was destroyed")
        text = "Fuel shortage — " + data["phase"] + ".\n" + "; ".join(outcomes)
        text += "\n" + value["loss"]["account"]
        text += (
            "\nThe loss happened before a prevention roll. Genuine followups keep their own work."
        )
    await reply(interaction, text)
