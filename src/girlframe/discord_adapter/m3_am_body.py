"""Private factual hardware preparation and printed original-AM-owned body return."""

import asyncio
import json
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine.m2 import AssetState, ChoiceAnswer
from girlframe.engine.m3_am_body import BodySpec
from girlframe.services.m2_game import GameService
from girlframe.services.m3_am_body import BodyService
from girlframe.services.onboarding import WorkflowError

YES = (("yes", "Yes, these are actual physical facts"), ("no", "Not confirmed"))


async def open_prepare(
    interaction: discord.Interaction, service: BodyService, maintenance: str
) -> None:
    data = await asyncio.to_thread(service.menu, viewer_from_interaction(interaction))
    source = next((x for x in data["preparations"] if x["id"] == maintenance), None)
    if source is None:
        raise WorkflowError("Use the actual original Handler's current circuit source")

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        vessel = values["vessel"].strip()
        assets = []
        for index, line in enumerate(values["assets"].splitlines()):
            if not line.strip():
                continue
            parts = tuple(x.strip() for x in line.split("|"))
            if (
                len(parts) != 4
                or parts[2] not in ("intact", "damaged")
                or parts[3] not in ("clear", "void")
            ):
                raise WorkflowError(
                    "Each actual Asset: name | source description | intact/damaged | clear/void"
                )
            assets.append(
                AssetState(
                    id=vessel + ":physical:" + str(index),
                    family="girl",
                    name=parts[0],
                    description=parts[1],
                    damaged=parts[2] == "damaged",
                    void=parts[3] == "void",
                )
            )
        spec = BodySpec.model_validate(
            dict(
                vessel=vessel,
                label=values["label"],
                source=values["source"],
                processing_confirmed=values["processing"] == ("yes",),
                unoccupied_confirmed=values["unoccupied"] == ("yes",),
                medical=values["medical"][0],
                assets=tuple(assets),
                mind_assets=tuple(values.get("mind_assets", ())),
                carried_items=tuple(values.get("carried_items", ())),
            )
        )
        await asyncio.to_thread(
            service.prepare,
            viewer_from_interaction(current),
            str(current.id),
            maintenance,
            data["revision"],
            spec,
        )
        return (
            "Actual local empty hardware and its processing/Assets saved. "
            "The original operator still owns the performed Just Code body choice."
        )

    form = NativeForm(
        interaction.user.id,
        "Actual factual body preparation",
        "Record actual available empty hardware at this circuit scene, with sufficient processing. "
        "Choose mind-linked Assets; other current Girl Assets stay with the original body. "
        "List the prepared physical Girl Assets, their actual source and current condition.",
        [
            Field("vessel", "Actual unique hardware identity"),
            Field("label", "Actual body label"),
            Field("source", "Actual hardware/processing/preparation source", paragraph=True),
            Field("processing", "Requisite processing power actually prepared", YES),
            Field("unoccupied", "This actual body is empty and available", YES),
            Field(
                "medical",
                "Actual prepared body condition",
                (
                    ("fit", "Fit"),
                    ("unconscious_injured", "Unconscious / injured"),
                ),
            ),
            Field(
                "assets",
                "One actual Asset per line: name | source | intact/damaged | clear/void",
                paragraph=True,
            ),
            *(
                [
                    Field(
                        "carried_items",
                        "Actual own objects to physically convey at transfer",
                        tuple((x["id"], x["label"]) for x in source["carried_items"]),
                        0,
                        len(source["carried_items"]),
                        required=False,
                    )
                ]
                if source["carried_items"]
                else []
            ),
            Field(
                "mind_assets",
                "Existing mind-linked Assets that remain with this same AM",
                tuple((x["id"], x["name"]) for x in source["mind_assets"]),
                0,
                len(source["mind_assets"]),
                required=False,
            ),
        ],
        submit,
    )
    await reply(interaction, form.text(), form)


async def open_choice(interaction: discord.Interaction, game: GameService, identity: str) -> None:
    data = await asyncio.to_thread(game.decision, viewer_from_interaction(interaction), identity)
    detail = data["am_code"]
    bodies = detail["body"]["bodies"]
    if not bodies:
        await open_prepare(interaction, BodyService(game), detail["maintenance"])
        return

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        await asyncio.to_thread(
            game.respond,
            viewer_from_interaction(current),
            str(current.id),
            identity,
            data["revision"],
            ChoiceAnswer(
                options=tuple(values["body"]),
                text=values["account"],
                fields={"carried_items": json.dumps(list(values["carried_items"]))}
                if values.get("carried_items")
                else {},
            ),
        )
        return (
            "Same AM transferred to the actual prepared body. Physical Assets changed; "
            "the original body and mind/history remain. Hooked return is in private body controls."
        )

    form = NativeForm(
        interaction.user.id,
        "Original operator: perform body swap",
        "Choose the suitable prepared empty body and record your performed circuits transfer. "
        "This is one printed option. Both bodies remain hooked for the AM's return.",
        [
            Field(
                "body", "Actual prepared local body", tuple((x["id"], x["label"]) for x in bodies)
            ),
            *(
                [
                    Field(
                        "carried_items",
                        "Own objects actually physically conveyed now",
                        tuple((x["id"], x["label"]) for x in detail["body"]["carried_items"]),
                        0,
                        len(detail["body"]["carried_items"]),
                        required=False,
                    )
                ]
                if detail["body"]["carried_items"]
                else []
            ),
            Field(
                "account",
                "Actual operator's performed transfer / object conveyance",
                paragraph=True,
            ),
        ],
        submit,
    )
    await reply(interaction, form.text(), form)


async def open_body(
    interaction: discord.Interaction, service: BodyService, identity: str | None = None
) -> None:
    viewer = viewer_from_interaction(interaction)
    if identity is None:
        menu = await asyncio.to_thread(service.menu, viewer)
        options = tuple(
            ("prepare:" + x["id"], "Prepare actual body: " + x["label"][:55])
            for x in menu["preparations"]
        ) + tuple(
            (
                "view:" + x["id"],
                "Read actual body / return" if not x["returned"] else "Read completed body return",
            )
            for x in menu["swaps"]
        )
        if not options:
            await reply(
                interaction, "No original body preparation or saved swap belongs to this role."
            )
            return

        async def choose(current: discord.Interaction, values: dict[str, Any]) -> None:
            kind, key = values["source"][0].split(":", 1)
            if kind == "prepare":
                await open_prepare(current, service, key)
            else:
                await open_body(current, service, key)

        form = NativeForm(
            interaction.user.id,
            "Actual AM body sources",
            "Original human-owned hardware, same mind and printed hooked return.",
            [Field("source", "Actual owned source", options)],
            choose,
        )
        await reply(interaction, form.text(), form)
        return
    data = await asyncio.to_thread(service.view, viewer, identity)
    records = []
    for body in data["bodies"]:
        actual = (
            data["current"]
            if data["current"] and data["current"]["vessel"] == body["vessel"]
            else body
        )
        resources = ", ".join(
            x["name"] + (" [damaged]" if x["damaged"] else "") + (" [Void]" if x["void"] else "")
            for x in actual["assets"]
        )
        records.append(
            f"{actual['label']} ({actual['vessel']}): "
            f"{resources or 'no physical Assets'}; {actual['medical']}"
        )
    instructions = (
        "\n".join(records) + "\nSame mind/Identities/Bonds/memories/Limiters and current Frame. "
        "Original body and inactive hardware remain real. Hooked: "
        + str(data["connection"]["connected"])
    )
    options = tuple(
        (
            [("return", "Return to original body while actually hooked")]
            if data["owner"] and not data["swap"]["returned_event"]
            else []
        )
        + (
            [("connect", "Record actual hookup"), ("disconnect", "Record actual disconnection")]
            if data["controller"] and not data["swap"]["returned_event"]
            else []
        )
    )
    if not options:
        await reply(interaction, instructions)
        return

    async def act(current: discord.Interaction, values: dict[str, Any]) -> str:
        operation = values["operation"][0]
        if operation == "return":
            await asyncio.to_thread(
                service.return_body,
                viewer_from_interaction(current),
                str(current.id),
                identity,
                data["revision"],
                carried_items=tuple(values.get("carried_items", ())),
                carry_account=values.get("account") if values.get("carried_items") else None,
            )
            return (
                "The original AM returned. The other body's latest damage remains saved. "
                "Mind, resources, current Frame and required work remain current."
            )
        await asyncio.to_thread(
            service.connection,
            viewer_from_interaction(current),
            str(current.id),
            identity,
            data["revision"],
            operation == "connect",
            values["account"],
        )
        return "Actual physical connection fact saved; no body transfer or consent was supplied."

    form = NativeForm(
        interaction.user.id,
        "Original AM body / actual hookup",
        instructions,
        [
            Field("operation", "Actual owned operation", options),
            *(
                [
                    Field(
                        "carried_items",
                        "Own objects actually physically conveyed on return",
                        tuple((x["id"], x["label"]) for x in data["carried_items"]),
                        0,
                        len(data["carried_items"]),
                        required=False,
                    )
                ]
                if data["carried_items"]
                else []
            ),
            Field(
                "account",
                "Actual physical facts / performed object conveyance",
                paragraph=True,
                required=False,
            ),
        ],
        act,
    )
    await reply(interaction, form.text(), form)
