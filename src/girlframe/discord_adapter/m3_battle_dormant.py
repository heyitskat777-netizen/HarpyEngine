"""Original-player controls for mandatory actual Dormant corruption and real Dive."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine.m2 import PlayInput
from girlframe.services.m3_battle_dormant import DormantService
from girlframe.services.onboarding import WorkflowError


async def open_dormant(
    interaction: discord.Interaction, service: DormantService, identity: str
) -> None:
    data = await asyncio.to_thread(service.get, viewer_from_interaction(interaction), identity)
    if data["state"] == "resolved":
        await reply(interaction, "This actual Dormant consequence is complete.")
        return
    if data.get("requires_original_role_port"):
        await reply(
            interaction,
            "The original affected role has changed. Resume its actual role's required "
            "consequence; a new Pilot sheet cannot substitute.",
        )
        return
    if not data["can_act"]:
        await reply(interaction, "The original affected Girl owns this required response.")
        return
    if data["phase"] == "thresholds":
        from girlframe.discord_adapter.m3_void import open_void
        from girlframe.engine.m3_void import FINAL
        from girlframe.services.m3_void import VoidService

        for work in data["body"]["thresholds"]:
            try:
                saved = await asyncio.to_thread(
                    VoidService(service.store).get, viewer_from_interaction(interaction), work
                )
            except WorkflowError:
                continue
            if saved["stage"] not in FINAL:
                await open_void(interaction, VoidService(service.store), work)
                return
        await reply(interaction, "Resume the source-owned Void threshold before the required Dive.")
        return
    if data["phase"] == "void":
        from girlframe.discord_adapter.m3_sup import GROW, add_growth, open_growth

        already_void = not data["assets"] and data["actor"]["kind"] == "external_pilot"
        if not data["assets"] and not already_void and not data.get("sup"):
            await reply(
                interaction,
                "No uncorrupted Asset remains. Resume the original Void-state consequence.",
            )
            return
        fields = [
            Field(
                "asset",
                "Actual Void payment",
                (("already_void", "Confirm all actual Harpy Assets are already Void"),)
                if already_void
                else add_growth(tuple((x["id"], x["name"]) for x in data["assets"]), data),
            ),
            Field(
                "description",
                "For an existing Asset: actual Void alteration",
                paragraph=True,
                required=not bool(data.get("sup")),
            ),
            Field(
                "piloting",
                "Actual own-Frame context",
                (("yes", "Inside my own Frame"), ("no", "Outside my own Frame")),
            ),
        ]
        if data.get("storage_available"):
            fields.append(
                Field(
                    "storage",
                    "Optional gained Void destination",
                    (("yes", "Store in my actual connected Harpy"),),
                    minimum=0,
                    required=False,
                )
            )
        if data.get("casualty_parts"):
            fields.extend(
                [
                    Field(
                        "casualty_part",
                        "Optional Wounded God: infected part to break",
                        tuple((x["id"], x["name"]) for x in data["casualty_parts"]),
                        minimum=0,
                        required=False,
                    ),
                    Field(
                        "casualty_site_account",
                        "Actual infected anatomical site, if resisting",
                        paragraph=True,
                        required=False,
                    ),
                ]
            )

        async def submit(current: discord.Interaction, values: dict[str, Any]) -> str | None:
            if values["asset"][0] == GROW:
                if values.get("casualty_part") or values.get("casualty_site_account", "").strip():
                    raise WorkflowError("Choose growth or an existing body's resisted onset")

                async def grow(
                    actual: discord.Interaction, fields: dict[str, str], text: str
                ) -> str:
                    await asyncio.to_thread(
                        service.alter,
                        viewer_from_interaction(actual),
                        str(actual.id),
                        identity,
                        data["revision"],
                        data["game_revision"],
                        None,
                        text,
                        piloting=values["piloting"][0] == "yes",
                        growth_fields=fields,
                    )
                    return (
                        "Actual new Void Asset grown; "
                        "complete the original threshold/required Dive."
                    )

                await open_growth(current, data, grow)
                return None
            await asyncio.to_thread(
                service.alter,
                viewer_from_interaction(current),
                str(current.id),
                identity,
                data["revision"],
                data["game_revision"],
                None if already_void else values["asset"][0],
                values["description"],
                piloting=values["piloting"][0] == "yes",
                store_void=bool(values.get("storage")),
                casualty_part=values["casualty_part"][0] if values.get("casualty_part") else None,
                casualty_site_account=values.get("casualty_site_account", ""),
            )
            return (
                "Actual Void recorded. Reopen this source consequence for any "
                "real threshold and required Dive."
            )

        title = "Dormant: actual Void"
    elif data["phase"] == "dive":
        if data["actor"]["kind"] == "external_pilot" and data.get("requires_source_role_resume"):

            async def resume(current: discord.Interaction, values: dict[str, Any]) -> str:
                await asyncio.to_thread(
                    service.resume_converted_role,
                    viewer_from_interaction(current),
                    str(current.id),
                    identity,
                    data["revision"],
                )
                return "Your Harpy rejoined. Reopen this request to make the required Dive."

            form = NativeForm(
                interaction.user.id,
                "Continue your transformed Harpy",
                "Confirm you are continuing as the same person after her actual rebirth.",
                [
                    Field(
                        "confirm",
                        "Your actual role",
                        (("yes", "Continue as my original transformed Harpy"),),
                    )
                ],
                resume,
            )
            await reply(interaction, form.text(), form)
            return
        if data["actor"]["kind"] == "external_pilot":
            from girlframe.discord_adapter.m3_actor_plays import open_actor_play
            from girlframe.engine.m3_actor_state import ActorRef

            parent = (
                dict(action_id=data["parent"], channel=data["channel"]) if data["parent"] else None
            )
            await open_actor_play(
                interaction,
                service.game,
                ActorRef.model_validate(data["actor"]),
                parent=parent,
                source_work=identity,
                channel=data["channel"],
            )
            return
        fields = [
            Field(
                "identity",
                "Optional owned Identity",
                (("none", "Do not mark an Identity"),)
                + tuple((x["id"], x["name"]) for x in data["identities"]),
            ),
            Field("gain", "Identity Heat gained", tuple((str(x), str(x)) for x in range(6))),
            Field(
                "pair_share", "Paired Heat sent to Pair", tuple((str(x), str(x)) for x in range(6))
            ),
            Field(
                "heat", "Heat to spend", tuple((str(x), str(x)) for x in range(data["heat"] + 6))
            ),
            Field(
                "piloting",
                "Actual own-Frame context",
                (("yes", "Inside my own Frame"), ("no", "Outside my own Frame")),
            ),
            Field("account", "Describe the actual forced connection", paragraph=True),
        ]

        if data.get("forbidden_dive"):
            fields = [x for x in fields if x.key not in ("identity", "gain", "pair_share", "heat")]

        async def submit(current: discord.Interaction, values: dict[str, Any]) -> str | None:
            chosen = values.get("identity", ("none",))[0]
            result = await asyncio.to_thread(
                service.game.begin,
                viewer_from_interaction(current),
                str(current.id),
                data["channel"],
                data["sheet_revision"],
                PlayInput(
                    play="dive_deep",
                    heat=int(values.get("heat", ("0",))[0]),
                    identity=None if chosen == "none" else chosen,
                    gain=int(values.get("gain", ("0",))[0]),
                    pair_share=int(values.get("pair_share", ("0",))[0]),
                    piloting=values["piloting"][0] == "yes",
                    parent=data["parent"],
                    source_work=identity,
                    context=values["account"],
                    trigger_confirmed=True,
                ),
            )
            return (
                "Actual source-required Dive started. Resume its real roll and owned choices: "
                + str(result["action_id"])
            )

        title = "Dormant: required Dive"
    else:
        await reply(interaction, "Resume the actual source-owned Dormant consequence.")
        return
    form = NativeForm(
        interaction.user.id,
        title,
        "This consequence is tied to the original source and affected Girl. "
        "Safety pause remains available."
        + (
            " This source requires a manual no-roll decision; no Heat or Identity is spent."
            if data.get("forbidden_dive")
            else ""
        ),
        fields,
        submit,
    )
    await reply(interaction, form.text(), form)
