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
    if kind.startswith("shell_"):
        await open_shell(interaction, game, data)
        return
    if kind.startswith("contact_"):
        await open_contact(interaction, game, data)
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
    kind = detail["kind"]
    spend = kind == "hallucinations_heat"
    review_day = kind == "hallucinations_day_review"
    gain_day = kind == "hallucinations_day_gain"
    fields: list[Field]
    if spend:
        description = f"You have {detail['heat']} Heat. Each Heat you spend adds one to the roll."
        fields = [Field("heat", "Heat to spend")]
    elif review_day:
        description = (
            f"Review fictional day {detail['day']}. Confirm a full new day continuously in range."
        )
        fields = [
            Field(
                "confirmed", "Was there a full new day?", (("yes", "Confirm"), ("no", "Decline"))
            ),
            Field("account", "Record the source of the elapsed time", paragraph=True),
        ]
    elif gain_day:
        description = f"Fictional day {detail['day']} in range was approved. Apply ordinary Void."
        if not detail["assets"]:
            await reply(interaction, "The original Void gain needs private human review.")
            return
        fields = [
            Field("asset", "Your Asset affected by Void", tuple(detail["assets"].items())),
            Field("void_description", "What changes about the Asset?", paragraph=True),
        ]
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
            text=values.get("account", "") if review_day else values.get("label", ""),
            flag=values["confirmed"][0] == "yes" if review_day else None,
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


async def open_contact(
    interaction: discord.Interaction, game: GameService, data: dict[str, Any]
) -> None:
    detail = data["detail"]
    kind = detail["kind"]
    if kind == "contact_frame_void":
        from girlframe.discord_adapter.m3_void import open_void
        from girlframe.services.m3_void import VoidService

        await open_void(interaction, VoidService(game.store), detail["work"])
        return
    prompts = {
        "contact_consent": "The printed out-of-Frame effect ends the Girl's original career. "
        "Choose whether to allow the private scene to proceed. You make a final choice later.",
        "contact_review": "Verify the original consensual contact and its actual physical context.",
        "contact_conclusion": "Choose whether the original Gorgon leaves one optional Tag.",
        "contact_final": "Confirm the described scene and its printed outcome. "
        "Confirming exposes the Core and ends your original Girl's career. You may withdraw.",
    }
    if detail["in_frame"]:
        prompts.update(
            contact_consent="Choose whether to allow the original in-Frame contact. "
            "You confirm before its rule roll.",
            contact_final="Confirm the private contact before the Gorgon rolls, or withdraw.",
        )
    prompts["contact_frame_roll"] = "Roll against the actual original occupied Frame."
    fields = [Field("choice", "Your decision", (("yes", "Confirm"), ("no", "Decline")))]
    if kind in ("contact_frame_damage", "contact_frame_consequence"):
        dice = " + ".join(str(x) for x in detail["faces"])
        line = f"Saved roll {dice} + {detail['bonus']} Void-corrupted Frame Assets."
        if kind == "contact_frame_consequence":
            prompts[kind] = line + " Confirm the original actors survived the immediate aftermath."
            choices: tuple[tuple[str, str], ...] = (("yes", "Confirm both survived"),)
            if detail["can_intervene"]:
                choices += (("intervene", "Offer one immediate combat Play"),)
            fields = [
                Field("choice", "Resolve the immediate aftermath", choices),
                Field("account", "Record the actual immediate situation", paragraph=True),
            ]
        else:
            prompts[kind] = line + " Choose your original intact Asset for the damage."
            fields = [Field("asset", "Your actual Asset", tuple(detail["assets"].items()))]
        if detail["tier"] == "mid":
            if not detail["void_assets"]:
                await reply(interaction, "This saved result needs private Void review.")
                return
            fields.extend(
                (
                    Field(
                        "void_asset",
                        "Your actual uncorrupted Asset",
                        tuple(detail["void_assets"].items()),
                    ),
                    Field("void_description", "What changes about the Asset?", paragraph=True),
                    Field(
                        "choice", "Expose the Core?", (("yes", "Expose"), ("no", "Leave covered"))
                    ),
                )
            )
    if kind == "contact_review":
        fields.append(Field("account", "State the verified context", paragraph=True))
    if kind == "contact_conclusion":
        fields.append(Field("account", "Your optional Tag", required=False))

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        selection = (values.get("choice") or (None,))[0]
        await asyncio.to_thread(
            game.respond,
            viewer_from_interaction(current),
            str(current.id),
            data["id"],
            data["revision"],
            ChoiceAnswer(
                flag=selection == "yes" if selection in ("yes", "no") else None,
                options=("intervene",)
                if selection == "intervene"
                else tuple(values.get("asset", ())),
                text=values.get("account", ""),
                fields=dict(
                    void_asset=values["void_asset"][0], void_description=values["void_description"]
                )
                if values.get("void_asset")
                else {},
            ),
        )
        return "Your private choice is saved. Recover any remaining step in your Inbox."

    form = NativeForm(interaction.user.id, "Private Gorgon contact", prompts[kind], fields, submit)
    await reply(interaction, form.text(), form)


async def open_shell(
    interaction: discord.Interaction, game: GameService, data: dict[str, Any]
) -> None:
    detail = data["detail"]
    kind = detail["kind"]
    if kind == "shell_threshold":
        from girlframe.discord_adapter.m3_void import open_void
        from girlframe.services.m3_void import VoidService

        await open_void(interaction, VoidService(game.store), detail["work"])
        return
    if kind == "shell_heat":
        message = f"You have {detail['heat']} Heat. Choose what you spend on the Sentinel roll."
        fields = [Field("heat", "Heat to spend")]
    elif kind == "shell_tie":
        message = "Confirm that the proposed Girl is the actual closest in this tied situation."
        fields = [
            Field("choice", "Confirm this target?", (("yes", "Confirm"), ("no", "Decline"))),
            Field("account", "State how you verified actual reach", paragraph=True),
        ]
    elif kind == "shell_void":
        message = "Choose and describe this required ordinary Void gain."
        fields = [
            Field("options", "Your actual uncorrupted Asset", tuple(detail["assets"].items())),
            Field("account", "What changes about this Asset?", paragraph=True),
        ]
    else:
        roll = detail["roll"]
        faces = " + ".join(str(x) for x in roll["faces"])
        count = detail["count"]
        message = f"Saved roll {faces} + {roll['heat']} Heat. Choose {count} actual effects."
        labels = {
            "trapped": "Trap the Girl",
            "cockpit": "Invade the original cockpit",
            "void": "Make the original Girl gain Void",
        }
        if count > len(detail["options"]):
            await reply(interaction, "The saved outcome needs private review of actual effects.")
            return
        fields = [
            Field(
                "options",
                "Printed consequences",
                tuple((x, labels[x]) for x in detail["options"]),
                count,
                count,
            ),
            Field("account", "Describe the actual effects", paragraph=True),
        ]

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        number = None
        if kind == "shell_heat":
            heat = values["heat"].strip()
            if not heat.isascii() or not heat.isdecimal() or len(heat) > 9:
                return "Enter a whole amount of your actual Heat."
            number = int(heat)
        await asyncio.to_thread(
            game.respond,
            viewer_from_interaction(current),
            str(current.id),
            data["id"],
            data["revision"],
            ChoiceAnswer(
                number=number,
                text=values.get("account", ""),
                options=tuple(values.get("options", ())),
                flag=values["choice"][0] == "yes" if values.get("choice") else None,
            ),
        )
        return "Your choice is saved. Any remaining consequence stays in the Inbox."

    form = NativeForm(interaction.user.id, "Withdraw Into Your Shell", message, fields, submit)
    await reply(interaction, form.text(), form)
