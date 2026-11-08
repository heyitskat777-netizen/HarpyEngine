"""Private native nuclear capability, actual drop and original owners' damage controls."""

import asyncio
from typing import Any, cast

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.ledger import clean
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine.m3_a_bomb import Option
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.services.m3_a_bomb import ABombService


def cell(text: str) -> tuple[int, int]:
    x, y = text.split(",")
    return int(x.strip()), int(y.strip())


async def open_bomb(
    interaction: discord.Interaction, service: ABombService, identity: str | None = None
) -> None:
    data = await asyncio.to_thread(service.menu, viewer_from_interaction(interaction), identity)
    if data["kind"] == "buy":

        async def buy(current: discord.Interaction, values: dict[str, Any]) -> str:
            await asyncio.to_thread(
                service.buy,
                viewer_from_interaction(current),
                str(current.id),
                data["award"],
                data["revision"],
                values["account"],
            )
            return (
                "A-Bomb acquired from the actual held award. Recover its source controls in"
                " History."
            )

        await NativeForm(
            interaction.user.id,
            "Acquire A-Bomb",
            (
                "Spend one genuine held Handler advancement. Actual nuclear device "
                "provenance and delivery are still required."
            ),
            [Field("account", "Actual advancement spend", paragraph=True)],
            buy,
        ).present(interaction)
        return
    if data["kind"] == "sources":

        async def choose(current: discord.Interaction, values: dict[str, Any]) -> None:
            await open_bomb(current, service, values["source"][0])

        await NativeForm(
            interaction.user.id,
            "A-Bomb sources",
            "Your actual original Handler acquisitions.",
            [
                Field(
                    "source", "Actual source", tuple((x["id"], x["label"]) for x in data["sources"])
                )
            ],
            choose,
        ).present(interaction)
        return
    if data["kind"] == "source":

        async def operation(current: discord.Interaction, values: dict[str, Any]) -> None:
            if values["operation"][0] == "certify":

                async def certify(answer: discord.Interaction, fields: dict[str, Any]) -> str:
                    await asyncio.to_thread(
                        service.certify_device,
                        viewer_from_interaction(answer),
                        str(answer.id),
                        data["id"],
                        data["revision"],
                        fields["item"][0],
                        cell(fields["cell"]),
                        fields["account"],
                    )
                    return "Actual nuclear capability/carry source saved. No extra Asset or charge."

                await NativeForm(
                    current.user.id,
                    "Actual nuclear device",
                    (
                        "Record actual nuclear capability of an already source-proved "
                        "carried object. Record your own truthful initial cell only if "
                        "previously unknown; known conflicting positions require actual "
                        "movement."
                    ),
                    [
                        Field(
                            "item",
                            "Actual held object",
                            tuple(
                                (x["id"], clean(x["label"])[:100])
                                for x in data["items"]
                                if not x["mechanical"]
                            ),
                        ),
                        Field("cell", "Actual release cell x,y"),
                        Field("account", "Actual nuclear/carry evidence", paragraph=True),
                    ],
                    certify,
                ).present(current)
            else:

                async def drop(answer: discord.Interaction, fields: dict[str, Any]) -> str:
                    selected = tuple(fields["options"])
                    result = await asyncio.to_thread(
                        service.drop,
                        viewer_from_interaction(answer),
                        str(answer.id),
                        data["id"],
                        data["revision"],
                        fields["device"][0],
                        cell(fields["centre"]),
                        cast(tuple[Option, Option], selected),
                        fields["delivery"],
                        mission=(fields.get("mission") or (None,))[0],
                        breaches={
                            x: fields.get("breach_account", "") for x in fields.get("zones", ())
                        },
                    )
                    return (
                        "Actual device consumed; blast and original-owner resource "
                        "effects are recoverable privately in Inbox/History. "
                    ) + str(result["id"])

                await NativeForm(
                    current.user.id,
                    "Drop the actual nuclear weapon",
                    (
                        "Actual 3x3 area; source supplies no extra dice/quota. All ordinary"
                        " casualties and resource consequences apply. Choose only actual "
                        "intersected quarantine perimeters and describe their real physical"
                        " breach."
                    ),
                    [
                        Field(
                            "device",
                            "Actual nuclear device",
                            tuple((x["id"], clean(x["account"])[:100]) for x in data["devices"]),
                        ),
                        Field("centre", "Actual drop centre x,y"),
                        Field(
                            "options",
                            "Exactly two printed options",
                            (
                                ("safe_ejection", "Safe radiation ejection"),
                                ("cores", "Expose Gorgon/Harpy Cores"),
                                ("gentle_fallout", "Gentle fallout / no Rebellion increase"),
                                ("mission_budget", "Budget exception if causal Mission succeeds"),
                            ),
                            minimum=2,
                            maximum=2,
                        ),
                        Field("delivery", "Actual delivery/performance", paragraph=True),
                        *(
                            [
                                Field(
                                    "mission",
                                    "Actual active Mission",
                                    tuple(
                                        (x["id"], clean(x["objective"])[:100])
                                        for x in data["missions"]
                                    ),
                                    minimum=0,
                                    required=False,
                                )
                            ]
                            if data["missions"]
                            else []
                        ),
                        *(
                            [
                                Field(
                                    "zones",
                                    "Actual affected quarantines",
                                    tuple(
                                        (x["id"], str(x["cells"])[:100])
                                        for x in data["quarantines"]
                                    ),
                                    minimum=0,
                                    maximum=len(data["quarantines"]),
                                    required=False,
                                ),
                                Field(
                                    "breach_account",
                                    "Actual physical perimeter breach",
                                    paragraph=True,
                                    required=False,
                                ),
                            ]
                            if data["quarantines"]
                            else []
                        ),
                    ],
                    drop,
                ).present(current)

        operations = []
        if data["items"]:
            operations.append(("certify", "Record actual carried nuclear capability"))
        if data["devices"]:
            operations.append(("drop", "Actually drop a proved nuclear device"))
        if not operations:
            await reply(
                interaction,
                (
                    "First establish the actual carried nuclear device through ordinary "
                    "owned item facts. No nuclear object is invented by a label."
                ),
            )
            return
        await NativeForm(
            interaction.user.id,
            "A-Bomb",
            "Actual source-owned controls; blast records remain private.",
            [Field("operation", "Actual operation", tuple(operations))],
            operation,
        ).present(interaction)
        return
    value = data["drop"]
    operations = [
        ("damage:" + str(index), "Choose actual affected Frame/Gorgon damage")
        for index, _ in enumerate(data["resources"])
    ]
    if data["judge"] and value["mission"] and value["causal"] is None:
        operations.append(("cause", "Record actual Mission causal facts"))
    if data["owner"] and not value["completed_event"]:
        operations.append(("finish", "Finish actual resolved effects"))
    text = (
        "Actual nuclear drop at "
        + str(value["centre"])
        + ". Options: "
        + ", ".join(value["options"])
        + ". "
        + (
            "Complete."
            if value["completed_event"]
            else "Real mandatory effects remain until resolved."
        )
    )
    if not operations:
        await reply(interaction, text)
        return

    async def effect(current: discord.Interaction, values: dict[str, Any]) -> None:
        selected = values["operation"][0]
        if selected.startswith("damage:"):
            row = data["resources"][int(selected.split(":")[1])]

            async def damage(answer: discord.Interaction, fields: dict[str, Any]) -> str:
                await asyncio.to_thread(
                    service.damage,
                    viewer_from_interaction(answer),
                    str(answer.id),
                    value["id"],
                    data["revision"],
                    ActorRef.model_validate(row["actor"]),
                    tuple(fields.get("assets", ())),
                )
                return (
                    "Actual original resources damaged. Any genuine mandatory followup "
                    "remains available through normal Inbox."
                )

            fields = (
                [
                    Field(
                        "assets",
                        "Actual undamaged losses",
                        tuple((x, row["labels"].get(x, x)) for x in row["assets"]),
                        minimum=min(2, len(row["assets"])),
                        maximum=min(2, len(row["assets"])),
                    )
                ]
                if row["assets"]
                else [
                    Field(
                        "none",
                        "No intact Assets remain",
                        (("none", "Record no invented Asset loss"),),
                    )
                ]
            )
            await NativeForm(
                current.user.id,
                "Actual blast damage",
                (
                    "Choose up to two available original resources; this choice does not "
                    "consent to being hit."
                ),
                fields,
                damage,
            ).present(current)
        elif selected == "cause":

            async def cause(answer: discord.Interaction, fields: dict[str, Any]) -> str:
                await asyncio.to_thread(
                    service.judge_mission,
                    viewer_from_interaction(answer),
                    str(answer.id),
                    value["id"],
                    data["revision"],
                    fields["causal"][0] == "yes",
                    fields["account"],
                )
                return (
                    "Real causal facts recorded; only an actual successful canonical "
                    "Mission ending can waive the direct Budget raise."
                )

            await NativeForm(
                current.user.id,
                "Actual Mission causation",
                clean(value["mission_objective"]),
                [
                    Field(
                        "causal",
                        "Did this actual drop lead to success?",
                        (
                            ("yes", "Actual causal contribution"),
                            ("no", "Did not cause successful outcome"),
                        ),
                    ),
                    Field("account", "Actual outcome evidence", paragraph=True),
                ],
                cause,
            ).present(current)
        else:
            await asyncio.to_thread(
                service.finish,
                viewer_from_interaction(current),
                str(current.id),
                value["id"],
                data["revision"],
            )
            await reply(current, "Actual resolved blast effects saved in private History.")

    await NativeForm(
        interaction.user.id,
        "Actual nuclear drop",
        text,
        [Field("operation", "Actual outstanding effects", tuple(operations))],
        effect,
    ).present(interaction)
