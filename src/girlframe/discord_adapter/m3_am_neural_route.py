"""Actual AM-authored powered-interface continuity and genuine self-directed occupancy."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.services.m3_am_jailbroken import JailbrokenService
from girlframe.services.m3_am_neural_route import RouteService


async def open_neural_route(
    interaction: discord.Interaction, service: RouteService, identity: str | None = None
) -> None:
    viewer = viewer_from_interaction(interaction)
    if identity is None:
        data = await asyncio.to_thread(service.menu, viewer)
        options = tuple(("view:" + x["id"], x["label"]) for x in data["routes"])
        if data["can_propose"] and data["destinations"]:
            options = (("propose", "Record actual powered interface continuity"),) + options
        if not options:
            await reply(
                interaction,
                "Establish the real reviewed spinal contact and prepare actual processing hardware "
                "before proposing continuous occupancy. Nothing has been unplugged or created.",
            )
            return

        async def choose(current: discord.Interaction, values: dict[str, Any]) -> None:
            selected = values["operation"][0]
            if selected != "propose":
                await open_neural_route(current, service, selected.split(":", 1)[1])
                return

            async def record(final: discord.Interaction, answers: dict[str, Any]) -> None:
                result = await asyncio.to_thread(
                    service.propose,
                    viewer_from_interaction(final),
                    str(final.id),
                    data["revision"],
                    answers["destination"][0],
                    answers["account"],
                )
                await open_neural_route(final, service, result["id"])

            form = NativeForm(
                current.user.id,
                "Actual continuous AM interface",
                "Your original physical jack remains where it was. Record how that actual powered "
                "AM hardware keeps the existing interface live while your mind uses this already "
                "prepared processing body. This supplies no body, circuit, backup "
                "or new capability.",
                [
                    Field(
                        "destination",
                        "Actual prepared empty hardware",
                        tuple((x["vessel"], x["label"]) for x in data["destinations"]),
                    ),
                    Field(
                        "account",
                        "Actual powered hardware and continued interface source",
                        paragraph=True,
                    ),
                ],
                record,
            )
            await reply(current, form.text(), form)

        form = NativeForm(
            interaction.user.id,
            "Your actual AM neural routes",
            "Original people, fixed physical jacks and real prepared processing hardware.",
            [Field("operation", "Actual owned source", options)],
            choose,
        )
        await reply(interaction, form.text(), form)
        return
    data = await asyncio.to_thread(service.view, viewer, identity)
    value = data["route"]
    text = (
        "Actual neural route — "
        + data["phase"]
        + ".\n"
        + value["account"]
        + "\nThe spinal contact stays at its original physical endpoints. "
        "Only an actual performed unplug expires its temporary Battery grants."
    )
    if not data["can_move"] or not data["destinations"]:
        await reply(interaction, text)
        return

    async def occupy(current: discord.Interaction, values: dict[str, Any]) -> str:
        await asyncio.to_thread(
            JailbrokenService(service.game).occupy,
            viewer_from_interaction(current),
            str(current.id),
            ActorRef.model_validate(value["actor"]),
            data["revision"],
            values["destination"][0],
            neural_route=identity,
            carried_items=tuple(values.get("carried_items", ())),
            carry_account=values.get("carry_account") if values.get("carried_items") else None,
        )
        return (
            "Actual self-directed occupancy saved with its original continuous interface source. "
            "No physical jack moved, no new roll occurred, and no temporary Asset was copied."
        )

    form = NativeForm(
        interaction.user.id,
        "Actual continuous self-directed occupancy",
        text,
        [
            Field(
                "destination",
                "Actual available processing body",
                tuple((x["vessel"], x["label"]) for x in data["destinations"]),
            ),
            *(
                [
                    Field(
                        "carried_items",
                        "Actual own objects physically conveyed",
                        tuple((x["id"], x["label"]) for x in data["carried_items"]),
                        0,
                        len(data["carried_items"]),
                        required=False,
                    ),
                    Field(
                        "carry_account",
                        "Actual separate object conveyance",
                        paragraph=True,
                        required=False,
                    ),
                ]
                if data["carried_items"]
                else []
            ),
        ],
        occupy,
    )
    await reply(interaction, form.text(), form)


async def open_code_route(
    interaction: discord.Interaction, service: RouteService, preparation: str
) -> None:
    viewer = viewer_from_interaction(interaction)
    data = await asyncio.to_thread(service.code_menu, viewer)
    source = next((x for x in data["preparations"] if x["id"] == preparation), None)
    if source is None:
        from girlframe.services.onboarding import WorkflowError

        raise WorkflowError("Use the original AM's actual idle Code hardware source")

    async def record(current: discord.Interaction, values: dict[str, Any]) -> str:
        result = await asyncio.to_thread(
            service.propose_code,
            viewer_from_interaction(current),
            str(current.id),
            source["maintenance"],
            preparation,
            data["revision"],
            values["account"],
        )
        return (
            "Actual fixed-interface continuity source saved: "
            + str(result["id"])
            + ". No movement occurred. The actual operator still confirms circuits, then chooses "
            "Body only on a genuine Code result. No extra permission, roll or Jailbroken benefit."
        )

    form = NativeForm(
        interaction.user.id,
        "Actual Code continuous interface: " + source["label"],
        "Before circuit confirmation: record the factual powered original hardware/relay keeping "
        "every existing spinal endpoint live while the same mind uses "
        "this real prepared processor. "
        "This records facts, never another person's reply or a body-transfer entitlement. "
        "If Code does not select Body, this unconsumed fact has no movement effect.",
        [Field("account", "Actual powered processing/interface continuity", paragraph=True)],
        record,
    )
    await reply(interaction, form.text(), form)
