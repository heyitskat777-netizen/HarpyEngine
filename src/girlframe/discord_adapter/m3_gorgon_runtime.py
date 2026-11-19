"""Private native controls for actual Gorgon effects and source-owned human responses."""

import asyncio
import json
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine.m2 import ChoiceAnswer
from girlframe.services.m2_game import GameService


async def open_choice(interaction: discord.Interaction, game: GameService, identity: str) -> None:
    data = await asyncio.to_thread(game.decision, viewer_from_interaction(interaction), identity)
    detail = data["detail"]
    kind = detail["kind"]
    if kind == "dormant_void":
        from girlframe.discord_adapter.m3_gorgon_dormant import open_gorgon_dormant
        from girlframe.services.m3_gorgon_dormant import GorgonDormantService

        await open_gorgon_dormant(
            interaction, GorgonDormantService(game.store, game), detail["work_id"]
        )
        return
    if kind == "hallucinations_void":
        from girlframe.discord_adapter.m3_void import open_void
        from girlframe.services.m3_void import VoidService

        await open_void(interaction, VoidService(game.store), detail["work"])
        return
    if kind.startswith("hallucinations_"):
        await open_hallucinations(interaction, game, data)
        return
    if kind == "response_play":
        from girlframe.discord_adapter.m2_ui import open_play

        await open_play(interaction, game, parent=data)
        return
    options = detail.get("options", [])
    fields: list[Field] = []
    if kind == "capability":
        options = ["capable", "incapable"]
    if kind in ("damage_asset", "contest_assets"):
        options = [x["id"] for x in detail["assets"]]
        labels = {x["id"]: x["name"] for x in detail["assets"]}
    else:
        labels = {x: x.replace("_", " ").title() for x in options}
    if not options:
        await reply(interaction, "The actual source has no currently legal resource choice.")
        return
    fields.append(
        Field(
            "options",
            "Your actual source choice",
            tuple((x, labels.get(x, x)) for x in options),
            maximum=min(25, len(options)) if kind == "contest_assets" else detail.get("maximum", 1),
        )
    )
    if kind == "contest_judge":
        assets = list(dict.fromkeys(detail["attacking_assets"] + detail["defending_assets"]))
        fields.append(Field("asset", "Actual losing Asset", tuple((x, x) for x in assets)))
        if detail.get("indirect_required"):
            fields.append(
                Field(
                    "indirect",
                    "Actual indirect approach against protector?",
                    (
                        ("yes", "Yes: explained actual indirect approach"),
                        ("no", "No: direct attack"),
                    ),
                )
            )
    if kind == "collateral":
        if detail["structures"]:
            fields.append(
                Field(
                    "structure",
                    "Structure, if chosen",
                    tuple((x["id"], x["label"]) for x in detail["structures"]),
                    minimum=0,
                    required=False,
                )
            )
        if detail["civilians"]:
            fields.append(
                Field(
                    "civilians",
                    "Civilians, if chosen",
                    tuple((x["id"], x["label"]) for x in detail["civilians"]),
                    minimum=0,
                    maximum=min(25, len(detail["civilians"])),
                    required=False,
                )
            )
    if kind == "interrupt":
        fields.append(
            Field(
                "actor",
                "Actual Girl volunteering, if Play chosen",
                tuple((str(index), x["label"]) for index, x in enumerate(detail["actors"])),
                minimum=0,
                required=False,
            )
        )
    if kind == "warp" and "evolve" in options:
        fields.extend(
            [
                Field("name", "New Asset name, if evolving", required=False),
                Field(
                    "description",
                    "New Asset description, if evolving",
                    paragraph=True,
                    required=False,
                ),
            ]
        )
    fields.append(Field("account", "Describe the actual source facts and effect", paragraph=True))

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        extras: dict[str, str] = {}
        for field in ("asset", "structure", "civilians"):
            if values.get(field):
                extras[field] = ",".join(values[field])
        if values.get("actor"):
            extras["actor"] = json.dumps(detail["actors"][int(values["actor"][0])]["ref"])
        for field in ("name", "description"):
            if values.get(field):
                extras[field] = values[field]
        answer = ChoiceAnswer(
            options=tuple(values["options"]) if kind != "capability" else (),
            text=values["account"],
            fields=extras,
            flag=(
                values["options"][0] == "capable"
                if kind == "capability"
                else values["indirect"][0] == "yes"
                if values.get("indirect")
                else None
            ),
        )
        await asyncio.to_thread(
            game.respond,
            viewer_from_interaction(current),
            str(current.id),
            identity,
            data["revision"],
            answer,
        )
        return "Your source-owned choice is saved. Remaining actual consequences stay in the inbox."

    form = NativeForm(
        interaction.user.id,
        "Gorgon: " + kind.replace("_", " "),
        "Resolve the actual declared effect. Response Plays use their own real roll and choices.",
        fields,
        submit,
    )
    await reply(interaction, form.text(), form)


async def open_hallucinations(
    interaction: discord.Interaction, game: GameService, data: dict[str, Any]
) -> None:
    detail = data["detail"]
    spend = detail["kind"] == "hallucinations_heat"
    fields: list[Field]
    if spend:
        description = f"You have {detail['heat']} Heat. Each Heat you spend adds one to the roll."
        fields = [Field("heat", "Heat to spend")]
    else:
        roll = detail["roll"]
        faces = " + ".join(str(x) for x in roll["faces"])
        description = f"Saved roll {faces} + {roll['heat']} Heat. Describe what you experienced."
        low = detail["tier"] == "low"
        fields = [Field("label", "Hallucination Identity" if low else "Hallucination Tag")]
        if low:
            if len(detail["identities"]) < 3 or not detail["assets"]:
                await reply(
                    interaction,
                    "Your saved result needs private review of the Identity or Void choices.",
                )
                return
            fields.extend(
                (
                    Field(
                        "identities",
                        "Your three Identities to erase",
                        tuple(detail["identities"].items()),
                        3,
                        3,
                    ),
                    Field("asset", "Your Asset affected by Void", tuple(detail["assets"].items())),
                    Field("void_description", "What changes about the Asset?", paragraph=True),
                )
            )

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        number = None
        if spend:
            raw = values["heat"].strip()
            if not raw.isascii() or not raw.isdecimal() or len(raw) > 9:
                return "Enter a whole amount of your current Heat."
            number = int(raw)
        answer = ChoiceAnswer(
            number=number,
            text=values.get("label", ""),
            options=tuple(values.get("identities", ())),
            fields={"asset": values["asset"][0], "void_description": values["void_description"]}
            if values.get("asset")
            else {},
        )
        await asyncio.to_thread(
            game.respond,
            viewer_from_interaction(current),
            str(current.id),
            data["id"],
            data["revision"],
            answer,
        )
        return "Your choice is saved. Open the private Inbox to recover any next step."

    form = NativeForm(interaction.user.id, "Hallucinations", description, fields, submit)
    await reply(interaction, form.text(), form)
