"""Actual owned cocktail choices, vein-contact source and private drug history."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine.m2 import ChoiceAnswer, PlayInput
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.services.m2_game import GameService
from girlframe.services.m3_dose_up import DoseUpService


async def open_choice(
    interaction: discord.Interaction, game: GameService, decision: dict[str, Any]
) -> None:
    detail = decision["detail"]
    field = Field(
        "components",
        "Your printed cocktail choice",
        tuple((x[0], x[1]) for x in detail["options"]),
        minimum=detail.get("minimum", 1),
        maximum=detail.get("maximum", 1),
    )

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        await asyncio.to_thread(
            game.respond,
            viewer_from_interaction(current),
            str(current.id),
            decision["id"],
            decision["revision"],
            ChoiceAnswer(options=values["components"]),
        )
        return "Your actual Dose Up choice is saved. Each remaining human keeps their own choice."

    form = NativeForm(
        interaction.user.id,
        "Dose Up: your choice",
        "The recipient's low-result Punishment replaces dosing. Cocktail components become "
        "actual temporary Tags. OOC pause remains available.",
        [field],
        submit,
    )
    await reply(interaction, form.text(), form)


async def open_dose_up(
    interaction: discord.Interaction, service: DoseUpService, identity: str | None = None
) -> None:
    viewer = viewer_from_interaction(interaction)
    if identity is not None:
        data = await asyncio.to_thread(service.view, viewer, identity)
        text = (
            "Dose Up: "
            + data["phase"]
            + ". Components: "
            + (", ".join(data["components"]) or "none")
        )
        text += (
            ". Heat spent: "
            + str(data["heat"])
            + ". Real participated scenes: "
            + str(len(data["scenes"]))
            + "/"
            + str(data["duration"])
            + "."
        )
        await reply(interaction, text)
        return
    channel = int(interaction.channel_id or 0)
    data = await asyncio.to_thread(service.menu, viewer, channel)
    options: list[tuple[str, str]] = []
    if data["can_dose"]:
        options.append(("self", "Dose yourself"))
    if data["targets"]:
        options.append(("contact", "Record actual close vein reach"))
    options.extend(("other:" + x["id"], "Dose " + x["label"]) for x in data["contacts"])
    options.extend(("history:" + x["id"], x["label"]) for x in data["history"])
    if not options:
        await reply(
            interaction, "No current source-owned Dose Up controls or private history here."
        )
        return

    async def choose(current: discord.Interaction, values: dict[str, Any]) -> str | None:
        selected = values["action"][0]
        if selected.startswith("history:"):
            await open_dose_up(current, service, selected.removeprefix("history:"))
            return None
        if selected == "contact":

            async def contact(response: discord.Interaction, answer: dict[str, Any]) -> str:
                target = next(
                    x
                    for x in data["targets"]
                    if ActorRef.model_validate(x["ref"]).token == answer["target"][0]
                )
                await asyncio.to_thread(
                    service.record_contact,
                    viewer_from_interaction(response),
                    str(response.id),
                    channel,
                    ActorRef.model_validate(target["ref"]),
                    data["revision"],
                    answer["account"],
                )
                return "Actual vein-reach source saved. Reopen Dose Up to prepare the Play."

            form = NativeForm(
                current.user.id,
                "Actual vein reach",
                "Record actual physical reach to their vein in the real scene. A shared square "
                "alone does not establish this fact. This records no fictional or OOC consent.",
                [
                    Field(
                        "target",
                        "Actual person within reach",
                        tuple(
                            (ActorRef.model_validate(x["ref"]).token, x["label"])
                            for x in data["targets"]
                        ),
                    ),
                    Field("account", "Your actual close vein reach", paragraph=True),
                ],
                contact,
            )
        else:
            sheet = await asyncio.to_thread(service.game.sheet, viewer_from_interaction(current))
            fields = [
                Field(
                    "heat",
                    "Heat actually spent",
                    tuple((str(x), str(x)) for x in range(sheet["heat"] + 1)),
                ),
                Field("account", "Your actual dosing trigger", paragraph=True),
            ]
            if selected == "self" and data["orders"]:
                fields.append(
                    Field(
                        "order",
                        "Actual followed self-Dose Order",
                        (("none", "No dosing Order"),)
                        + tuple((x["id"], x["label"]) for x in data["orders"]),
                    )
                )

            async def play(response: discord.Interaction, answer: dict[str, Any]) -> str:
                source = next((x for x in data["contacts"] if "other:" + x["id"] == selected), None)
                order = answer.get("order", ("none",))[0]
                result = await asyncio.to_thread(
                    service.game.begin,
                    viewer_from_interaction(response),
                    str(response.id),
                    channel,
                    sheet["revision"],
                    PlayInput(
                        play="dose_up",
                        heat=int(answer["heat"][0]),
                        context=answer["account"],
                        trigger_confirmed=True,
                        source_work=source["id"] if source else None,
                        target_actor=ActorRef.model_validate(source["target"]) if source else None,
                        order_id=order if order != "none" else None,
                    ),
                )
                return "Actual Dose Up Play prepared: " + str(result["action_id"])

            form = NativeForm(
                current.user.id,
                "Dose Up",
                "Spend actual Heat and make the real Play. "
                "Drug Tags last two actual recipient-participated scenes, including this scene.",
                fields,
                play,
            )
        await reply(current, form.text(), form)
        return None

    form = NativeForm(
        viewer.user_id,
        "Dose Up controls",
        "Actual source, owned choices and private history.",
        [Field("action", "Your control", tuple(options))],
        choose,
    )
    await reply(interaction, form.text(), form)
