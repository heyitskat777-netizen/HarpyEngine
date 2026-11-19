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
from girlframe.services.m3_parasite_excision import ExcisionService


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
    if kind.startswith("hazard_"):
        await open_hazard(interaction, game, data)
        return
    if kind.startswith("infection_"):
        await open_infection(interaction, game, data)
        return
    if kind.startswith("unreal_"):
        await open_unreal(interaction, game, data)
        return
    if kind.startswith("conditioning_"):
        await open_incubus_conditioning(interaction, game, data)
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


async def open_incubus_conditioning(
    interaction: discord.Interaction,
    game: GameService,
    data: dict[str, Any],
) -> None:
    detail = data["detail"]
    kind = detail["kind"]
    if kind == "conditioning_review" and not detail.get("can_transform"):
        await reply(interaction, "The saved result needs review of the actual original body.")
        return
    if kind == "conditioning_threshold":
        from girlframe.discord_adapter.m3_void import open_void
        from girlframe.services.m3_void import VoidService

        await open_void(interaction, VoidService(game.store), detail["work"])
        return
    void = kind == "conditioning_void"
    spending = kind == "conditioning_heat"
    if spending:
        message = (
            f"The original Tag was marked. Choose what to spend from your {detail['heat']} Heat."
        )
        fields = [Field("heat", "Heat to spend")]
    elif kind == "conditioning_review":
        message = "Verify that the original Girl remained free, conscious and alive."
        fields = [
            Field("choice", "Did the original Girl remain uninterrupted?", (("yes", "Confirm"),)),
            Field("account", "Record the actual immediate aftermath", paragraph=True),
        ]
    elif void:
        if not detail["assets"]:
            await reply(interaction, "This saved Void gain needs private review.")
            return
        message = "Apply your ordinary Void gain. Your immediate Play follows this consequence."
        fields = [
            Field("asset", "Your actual Asset", tuple(detail["assets"].items())),
            Field("account", "Describe the actual Void change", paragraph=True),
        ]
    else:
        message = "The original Girl resisted. Choose whether to erase this exact marked Tag."
        fields = [Field("choice", "Erase this Tag?", (("yes", "Erase"), ("no", "Keep it")))]

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        number = None
        if spending:
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
                options=tuple(values.get("asset", ())),
                flag=None if spending or void else values["choice"][0] == "yes",
            ),
        )
        return "Your choice is saved. Recover any remaining step in the private Inbox."

    form = NativeForm(interaction.user.id, "Emotional Conditioning", message, fields, submit)
    await reply(interaction, form.text(), form)


async def open_unreal(
    interaction: discord.Interaction, game: GameService, data: dict[str, Any]
) -> None:
    detail = data["detail"]
    kind = detail["kind"]
    if kind == "unreal_threshold":
        from girlframe.discord_adapter.m3_void import open_void
        from girlframe.services.m3_void import VoidService

        await open_void(interaction, VoidService(game.store), detail["work"])
        return
    if kind == "unreal_heat":
        message = f"The Growth paid an Asset. Choose what to spend from your {detail['heat']} Heat."
        fields = [Field("heat", "Heat to spend")]
    elif kind == "unreal_grow":
        count = detail["count"]
        message = f"Choose exactly {count} forms of growth from the saved roll."
        fields = [
            Field(
                "options", "Printed growth choices", tuple(detail["options"].items()), count, count
            )
        ]
        if detail["guards"]:
            fields.append(
                Field(
                    "guard",
                    "Additional Core protector, if reinforcing",
                    tuple(detail["guards"].items()),
                    required=False,
                    minimum=0,
                )
            )
        fields.append(Field("account", "Describe the actual ordered growth", paragraph=True))
    else:
        damage = kind == "unreal_damage"
        message = (
            "Damage one actual Growth Asset, or decline." if damage else "Apply ordinary Void."
        )
        fields = [
            Field(
                "options",
                "Actual original Asset",
                tuple(detail["assets"].items()),
                minimum=0 if damage else 1,
                required=not damage,
            )
        ]
        if not damage:
            fields.append(Field("account", "Describe the actual Void change", paragraph=True))

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        number = None
        if kind == "unreal_heat":
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
                fields={"guard": values["guard"][0]} if values.get("guard") else {},
            ),
        )
        return "Your choice is saved. Any remaining consequence is in the Inbox."

    form = NativeForm(interaction.user.id, "Grow Unreal", message, fields, submit)
    await reply(interaction, form.text(), form)


async def open_infection(
    interaction: discord.Interaction, game: GameService, data: dict[str, Any]
) -> None:
    from girlframe.services.m3_parasite_infection import LOSSES

    detail = data["detail"]
    kind = detail["kind"]
    if kind == "infection_threshold":
        from girlframe.discord_adapter.m3_void import open_void
        from girlframe.services.m3_void import VoidService

        await open_void(interaction, VoidService(game.store), detail["work"])
        return
    fields: list[Field] = []
    if kind == "infection_low_review":
        if detail["transfer"]:
            message = "Pass the saved consequence to the original Parasite controller."
            fields = [Field("options", "Original choice owner", (("transfer", "Return choice"),))]
        elif len(detail["parts"]) >= 3:
            message = "Choose three original Identity slots to control until excision."
            fields = [
                Field("options", "Original sheet parts", tuple(detail["parts"].items()), 3, 3)
            ]
        else:
            await reply(
                interaction,
                "The original low roll is saved. The available parts need private human review.",
            )
            return
    elif kind == "infection_heat":
        message = f"You have {detail['heat']} available Heat. Choose how much to spend."
        fields.append(Field("heat", "Your Heat spend"))
    elif kind == "infection_loss":
        message = "Fight off the infection and record the small loss you chose for your Girl."
        fields.extend(
            (
                Field("options", "The kind of loss", tuple(LOSSES.items())),
                Field("account", "Describe your Girl's actual loss", paragraph=True),
            )
        )
    elif kind == "infection_damage":
        message = "Choose the actual Voided Asset damaged as the Parasite makes contact."
        if detail["assets"]:
            fields.append(
                Field("options", "Your actual Voided Asset", tuple(detail["assets"].items()))
            )
        else:
            message = "There is no eligible Voided Asset. Confirm that the infection cannot start."
            fields.append(
                Field(
                    "no_connection",
                    "Your actual situation",
                    (("confirm", "No eligible Voided Asset"),),
                )
            )
    elif kind == "infection_void":
        if not detail["assets"]:
            await reply(
                interaction,
                "There is no eligible Asset. The ordinary Void consequence stays pending.",
            )
            return
        message = "The Parasite partly inhabits your Girl. Choose her ordinary Void gain."
        fields.extend(
            (
                Field("options", "Your actual uncorrupted Asset", tuple(detail["assets"].items())),
                Field("account", "Describe the change", paragraph=True),
            )
        )
    else:
        return

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        heat = values.get("heat", "").strip()
        if kind == "infection_heat" and (
            not heat.isascii() or not heat.isdecimal() or len(heat) > 9
        ):
            return "Enter a whole amount of your actual Heat."
        await asyncio.to_thread(
            game.respond,
            viewer_from_interaction(current),
            str(current.id),
            data["id"],
            data["revision"],
            ChoiceAnswer(
                number=int(heat) if kind == "infection_heat" else None,
                text=values.get("account", ""),
                options=tuple(values.get("options", ())),
            ),
        )
        return "Your infection response is saved. Any remaining choice stays in your Inbox."

    form = NativeForm(interaction.user.id, "Parasite Infect", message, fields, submit)
    await reply(interaction, form.text(), form)


async def open_excision(
    interaction: discord.Interaction, service: ExcisionService, identity: str
) -> None:
    data = await asyncio.to_thread(service.get, viewer_from_interaction(interaction), identity)
    if data["patient"] and data["consent"]:
        operation = "withdraw"
        text = "You can withdraw consent before the surgery takes place."
        fields = [Field("confirm", "Your choice", (("withdraw", "Withdraw consent"),))]
    elif data["patient"] and data["options"]:
        operation = "consent"
        text = "Choose the actual doctor and scene you consent to for this surgery."
        fields = [Field("doctor", "Your doctor and scene", tuple(data["options"].items()))]
    elif data["patient"]:
        await reply(
            interaction, "Join an active scene with an available local doctor to consider surgery."
        )
        return
    else:
        operation = "performed"
        text = "Verify the actual consented surgery was performed and the Parasite was excised."
        fields = [Field("account", "Describe the performed operation and outcome", paragraph=True)]

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        updated = await asyncio.to_thread(
            service.respond,
            viewer_from_interaction(current),
            str(current.id),
            identity,
            data["revision"],
            operation,
            doctor=values["doctor"][0] if values.get("doctor") else None,
            account=values.get("account", ""),
        )
        return (
            "The original infestation was excised."
            if updated["excised"]
            else "Your choice is saved."
        )

    form = NativeForm(interaction.user.id, "Experimental Parasite Excision", text, fields, submit)
    await reply(interaction, form.text(), form)


async def open_hazard(
    interaction: discord.Interaction,
    game: GameService,
    data: dict[str, Any],
) -> None:
    detail = data["detail"]
    kind = detail["kind"]
    if kind == "hazard_heat":
        text = f"You have {detail['heat']} available Heat. Choose how much to spend."
        fields = [Field("heat", "Your Heat spend")]
    elif kind == "hazard_eject":
        text = "Your low roll is saved. You can eject your Girl from her actual Vital Frame now."
        fields = [Field("account", "Describe your immediate ejection", paragraph=True)]
    else:
        await reply(
            interaction,
            "The Hazard roll is saved. Its original consequence needs private review.",
        )
        return

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        heat = values.get("heat", "").strip()
        if kind == "hazard_heat" and (not heat.isascii() or not heat.isdecimal() or len(heat) > 9):
            return "Enter a whole amount of your actual Heat."
        answer = ChoiceAnswer(
            number=int(heat) if kind == "hazard_heat" else None,
            text=values.get("account", ""),
        )
        await asyncio.to_thread(
            game.respond,
            viewer_from_interaction(current),
            str(current.id),
            data["id"],
            data["revision"],
            answer,
        )
        return "Your Memetic Hazard response is saved."

    form = NativeForm(interaction.user.id, "Memetic Hazard", text, fields, submit)
    await reply(interaction, form.text(), form)
