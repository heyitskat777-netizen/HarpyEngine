"""Native real Base acquisition, owner-authored boarding and printed ram choices."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.ledger import clean
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.services.m3_ship_base import ShipBaseService


def cell(text: str) -> tuple[int, int]:
    x, y = text.split(",")
    return int(x.strip()), int(y.strip())


async def open_ship(
    interaction: discord.Interaction, service: ShipBaseService, identity: str | None = None
) -> None:
    data = await asyncio.to_thread(service.menu, viewer_from_interaction(interaction), identity)
    if data["kind"] == "buy":

        async def buy(current: discord.Interaction, values: dict[str, Any]) -> str:
            result = await asyncio.to_thread(
                service.buy,
                viewer_from_interaction(current),
                str(current.id),
                data["award"],
                data["revision"],
                values["base"][0],
                values["account"],
            )
            return (
                "The actual existing Base can fly and is Armoured. "
                "Use its saved Ship-Base controls. " + str(result["base"])
            )

        await NativeForm(
            interaction.user.id,
            "Acquire Ship-Base",
            "Spend this actual held award on one real operational Foundation Base. No Base, person "
            "or Frame is copied. Boarding is a later actual physical action.",
            [
                Field(
                    "base",
                    "Your actual existing Base",
                    tuple((x["id"], clean(x["name"])[:100]) for x in data["bases"]),
                ),
                Field("account", "Actual existing Base advancement", paragraph=True),
            ],
            buy,
        ).present(interaction)
        return
    if data["kind"] == "ships":

        async def select_ship(current: discord.Interaction, values: dict[str, Any]) -> None:
            await open_ship(current, service, values["ship"][0])

        await NativeForm(
            interaction.user.id,
            "Actual Ship-Bases",
            "Choose an actual source ship.",
            [
                Field(
                    "ship",
                    "Existing Ship-Base",
                    tuple((x["id"], clean(x["name"])[:100]) for x in data["ships"]),
                )
            ],
            select_ship,
        ).present(interaction)
        return
    if data["kind"] == "ram":
        body = data["body"]
        text = (
            "Actual Ship-Base ram: "
            + str(body["faces"])
            + " +"
            + str(body["modifier"])
            + " = "
            + str(body["total"])
            + ". "
            + body["tier"]
            + "."
        )
        if body["phase"] == "awaiting_play":

            async def owed(current: discord.Interaction, values: dict[str, Any]) -> None:
                from girlframe.discord_adapter.m3_handler_plays import open_play
                from girlframe.services.m3_handler_plays import HandlerPlayService

                await open_play(current, HandlerPlayService(service.store), body["low_grant"])

            await NativeForm(
                interaction.user.id,
                "Actual low ram consequence",
                text + " The actual "
                "procedural GM must make a real Handler Play against the original Cadre.",
                [
                    Field(
                        "effect",
                        "Required actual consequence",
                        (("play", "Resolve the required Handler Play"),),
                    )
                ],
                owed,
            ).present(interaction)
        else:
            await reply(
                interaction, text + " Printed effects are saved.\n" + clean(body["account"])
            )
        return
    ship = data["ship"]
    operations = [("board", "Actually board your body / owned Frame")]
    if data["boardings"]:
        operations.append(("leave", "Actually disembark your body / Frame"))
    if data["owner"] and ship["condition"] != "destroyed":
        operations.extend(
            (("fly", "Fly the Base with its proved occupants"), ("ram", "Ram an actual threat"))
        )

    async def choose(current: discord.Interaction, values: dict[str, Any]) -> None:
        operation = values["operation"][0]
        if operation == "board":

            async def board(answer: discord.Interaction, fields: dict[str, Any]) -> str:
                selected = next(
                    x
                    for x in data["actors"]
                    if ActorRef.model_validate(x["ref"]).token == fields["actor"][0]
                )
                await asyncio.to_thread(
                    service.board,
                    viewer_from_interaction(answer),
                    str(answer.id),
                    data["acquisition"],
                    data["revision"],
                    ActorRef.model_validate(selected["ref"]),
                    fields["parts"][0],
                    fields["account"],
                )
                return (
                    "Your actual physical boarding is saved. Same-cell bystanders were not boarded."
                )

            await NativeForm(
                current.user.id,
                "Your actual boarding",
                "Only record your own actual controller's body/Frame entering this grounded Base. "
                "Known conflicting locations require real movement. A Handler's genuinely unknown "
                "initial location can be truthfully established by their own boarding.",
                [
                    Field(
                        "actor",
                        "Your actual original person",
                        tuple(
                            (ActorRef.model_validate(x["ref"]).token, clean(x["label"])[:100])
                            for x in data["actors"]
                        ),
                    ),
                    Field(
                        "parts",
                        "What actually boards?",
                        (
                            ("body", "Body only"),
                            ("frame", "Own Frame only"),
                            ("both", "Original Girl and her own Frame"),
                        ),
                    ),
                    Field("account", "Actual physical boarding", paragraph=True),
                ],
                board,
            ).present(current)
        elif operation == "leave":

            async def leave(answer: discord.Interaction, fields: dict[str, Any]) -> str:
                await asyncio.to_thread(
                    service.leave,
                    viewer_from_interaction(answer),
                    str(answer.id),
                    fields["boarding"][0],
                    data["revision"],
                    fields["account"],
                )
                return "Your actual disembarkation is saved at the Base's actual cell."

            await NativeForm(
                current.user.id,
                "Actual disembarkation",
                "Actually land first. This removes only your own proved physical cargo record.",
                [
                    Field(
                        "boarding",
                        "Your actual boarded body/Frame",
                        tuple(
                            (x["id"], x["parts"] + " — " + x["actor"]["kind"])
                            for x in data["boardings"]
                        ),
                    ),
                    Field("account", "Actual departure from the ship", paragraph=True),
                ],
                leave,
            ).present(current)
        elif operation == "fly":

            async def fly(answer: discord.Interaction, fields: dict[str, Any]) -> str:
                await asyncio.to_thread(
                    service.fly,
                    viewer_from_interaction(answer),
                    str(answer.id),
                    data["acquisition"],
                    data["revision"],
                    cell(fields["cell"]),
                    fields["arrival"] == ("airborne",),
                    fields["account"],
                )
                return (
                    "The actual Base and its proved cargo travelled fast. "
                    "Unboarded people stayed put."
                )

            await NativeForm(
                current.user.id,
                "Fly the actual Base",
                "The original Handler must actually be aboard at the controls. Move only recorded "
                "contained bodies and Frames. "
                "Landing cannot overwrite an existing ground location.",
                [
                    Field("cell", "Actual destination cell x,y"),
                    Field(
                        "arrival",
                        "Actual arrival",
                        (("airborne", "Remain flying"), ("land", "Actually land")),
                    ),
                    Field("account", "Actual flight and destination", paragraph=True),
                ],
                fly,
            ).present(current)
        else:

            async def target(answer: discord.Interaction, fields: dict[str, Any]) -> None:
                threat = next(
                    x
                    for x in data["threats"]
                    if ActorRef.model_validate(x["ref"]).token == fields["threat"][0]
                )

                async def ram(actual: discord.Interaction, details: dict[str, Any]) -> None:
                    basis = details["basis"][0]
                    opening = (
                        (details.get("opening") or (None,))[0] if basis == "opportunity" else None
                    )
                    result = await asyncio.to_thread(
                        service.ram,
                        viewer_from_interaction(actual),
                        str(actual.id),
                        data["acquisition"],
                        data["revision"],
                        ActorRef.model_validate(threat["ref"]),
                        basis,
                        details["asset"][0],
                        details["account"],
                        opening=opening,
                    )
                    await open_ship(actual, service, result["id"])

                await NativeForm(
                    answer.user.id,
                    "Ram — actual printed basis",
                    "Choose one modifier, never stack. +4 genuinely spends Armoured before dice, "
                    "so an 11+ then destroys an unarmoured ship. Choose the actual threat-owned "
                    "Asset conditionally damaged on an 11+. "
                    "No additional damage is invented on low.",
                    [
                        Field(
                            "basis",
                            "Single printed modifier",
                            (
                                ("plain", "+0 otherwise"),
                                ("opportunity", "+2 actual Cadre opening"),
                                ("armoured", "+4 spend actual Armoured"),
                            ),
                        ),
                        Field(
                            "opening",
                            "Actual completed Cadre maneuver (for +2)",
                            tuple(
                                (x["id"], clean(x["label"])[:100]) for x in data["opportunities"]
                            ),
                            0,
                            1,
                            required=False,
                        ),
                        Field(
                            "asset",
                            "Actual threat Asset to damage on 11+",
                            tuple((x["id"], clean(x["name"])[:100]) for x in threat["assets"]),
                        ),
                        Field(
                            "account",
                            "Actual ram/control/reach and current opening",
                            paragraph=True,
                        ),
                    ],
                    ram,
                ).present(answer)

            await NativeForm(
                current.user.id,
                "Ram a real threat",
                "Choose a present reachable "
                "ordinary Gorgon. Special Core or Dormant interactions require their own adapters.",
                [
                    Field(
                        "threat",
                        "Actual co-present threat",
                        tuple(
                            (ActorRef.model_validate(x["ref"]).token, clean(x["name"])[:100])
                            for x in data["threats"]
                        ),
                    )
                ],
                target,
            ).present(current)

    await NativeForm(
        interaction.user.id,
        clean(ship["name"]),
        "Cell: "
        + str(ship["cell"])
        + "; "
        + ship["condition"]
        + "; "
        + ("flying" if ship["airborne"] else "grounded")
        + "; "
        + ("Armoured" if ship["armoured"] else "unarmoured")
        + ". Your private boarding controls describe actual containment, "
        "not everybody at this cell.",
        [Field("operation", "Actual source operation", tuple(operations))],
        choose,
    ).present(interaction)
