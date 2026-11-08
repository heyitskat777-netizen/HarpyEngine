"""Separate original Handler facts and each affected player's actual Asset choices."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.services.m3_budget_removal import RemovalService


async def open_removal(
    interaction: discord.Interaction,
    service: RemovalService,
    identity: str,
    *,
    actor: ActorRef | None = None,
) -> None:
    data = await asyncio.to_thread(
        service.view, viewer_from_interaction(interaction), identity, actor
    )
    if data["phase"] == "complete":
        await reply(
            interaction, "Every original removal and its mandatory consequences are complete."
        )
        return
    if data["gm"] and actor is None:
        available = [x for x in data["people"] if not x["removed"]]
        if not available:
            if not data["can_finish"]:
                await reply(
                    interaction,
                    "Player removals are saved. Finish pending Asset-loss work before closing.",
                )
                return

            async def finish(current: discord.Interaction, values: dict[str, Any]) -> str:
                await asyncio.to_thread(
                    service.finish,
                    viewer_from_interaction(current),
                    str(current.id),
                    identity,
                    data["game_revision"],
                )
                return "Every original removal and its actual consequences are complete."

            await NativeForm(
                interaction.user.id,
                "Budget: complete source",
                "All actual original removals and owned consequences are complete.",
                [
                    Field(
                        "confirm",
                        "Close this actual Endgame source",
                        (("yes", "Confirm completion"),),
                    )
                ],
                finish,
            ).present(interaction)
            return

        async def choose(current: discord.Interaction, values: dict[str, Any]) -> str | None:
            selected = next(
                x
                for x in available
                if ActorRef.model_validate(x["actor"]).token == values["actor"][0]
            )
            await open_removal(
                current, service, identity, actor=ActorRef.model_validate(selected["actor"])
            )
            return None

        await NativeForm(
            interaction.user.id,
            "Budget: actual loss context",
            "Record occupancy, battle and opponent facts. Players choose their own Assets.",
            [
                Field(
                    "actor",
                    "Original Girl",
                    tuple(
                        (ActorRef.model_validate(x["actor"]).token, x["label"]) for x in available
                    ),
                )
            ],
            choose,
        ).present(interaction)
        return
    if data["phase"] in ("removed", "resolved"):
        pending = [x for x in data["children"] if x["state"] != "resolved"]
        record = data.get("record")
        saved = (
            (
                "Removed Girl Asset: "
                + record["girl_asset"]["name"]
                + "\nRemoved Frame Asset: "
                + record["frame_asset"]["name"]
                + "\nMy account: "
                + record["account"]
                + "\n"
            )
            if record
            else ""
        )
        await reply(
            interaction,
            saved
            + "Your actual Asset pair is removed. "
            + (
                "Resolve your pending Defeat/Void work through the Inbox."
                if pending
                else "Your mandatory source consequences are complete."
            ),
        )
        return
    if data["gm"] and (
        data["actor"]["entity"] != str(interaction.user.id) or data["phase"] == "context"
    ):
        physical = data["physical"]
        options = (("none", "No actual opposing person"),) + tuple(
            (x["token"], x["label"]) for x in data["opponents"]
        )

        async def context(current: discord.Interaction, values: dict[str, Any]) -> str:
            token = values["opponent"][0]
            opponent = next(
                (
                    ActorRef.model_validate(x["ref"])
                    for x in data["opponents"]
                    if x["token"] == token
                ),
                None,
            )
            await asyncio.to_thread(
                service.review_context,
                viewer_from_interaction(current),
                str(current.id),
                identity,
                ActorRef.model_validate(data["actor"]),
                data["game_revision"],
                inside_frame=physical["inside_frame"],
                piloting=physical["piloting"],
                in_battle=values["battle"][0] == "yes",
                opponent=opponent,
                opponent_known=True,
                account=values["account"],
            )
            return "Actual facts saved. The original player now chooses her own Asset pair."

        await NativeForm(
            interaction.user.id,
            "Budget: source facts",
            f"Inside Frame: {physical['inside_frame']}; piloting: {physical['piloting']}. "
            "Record battle and opponent, including explicit none. Players choose Assets.",
            [
                Field("battle", "Actually in battle?", (("yes", "Yes"), ("no", "No"))),
                Field("opponent", "Actual opposing person or explicit none", options),
                Field("account", "Record the actual context", paragraph=True),
                Field(
                    "confirm",
                    "Confirm these actual source facts",
                    (("yes", "I confirm these facts"),),
                ),
            ],
            context,
        ).present(interaction)
        return
    if data["phase"] == "context":
        await reply(
            interaction,
            "The original Handler must record physical, battle and opponent facts first.",
        )
        return
    girl = [x for x in data["assets"] if x["family"] == "girl" and not x["blocked"]]
    frame = [x for x in data["assets"] if x["family"] == "frame" and not x["blocked"]]
    if not girl or not frame:
        await reply(
            interaction,
            "No eligible Asset of each family. Intrinsic, stored, temporary and held sources "
            "need their actual loss adapter. This Endgame remains pending.",
        )
        return

    async def remove(current: discord.Interaction, values: dict[str, Any]) -> str:
        result = await asyncio.to_thread(
            service.remove,
            viewer_from_interaction(current),
            str(current.id),
            identity,
            data["game_revision"],
            values["girl"][0],
            values["frame"][0],
            values["account"],
        )
        return "Your actual Girl and Frame Assets are removed. " + (
            "Your genuine required consequence work is in the Inbox."
            if result["children"]
            else "No Defeat/Void consequence was triggered by this actual loss."
        )

    await NativeForm(
        interaction.user.id,
        "Budget: remove my actual Assets",
        "Choose one Girl and one Frame Asset to remove permanently. Other Assets and marks remain.",
        [
            Field("girl", "My Girl Asset to remove", tuple((x["id"], x["name"]) for x in girl)),
            Field("frame", "My Frame Asset to remove", tuple((x["id"], x["name"]) for x in frame)),
            Field("account", "Describe my actual maintenance loss", paragraph=True),
            Field(
                "confirm",
                "Confirm removal of both selected Assets",
                (("yes", "Remove exactly this pair"),),
            ),
        ],
        remove,
    ).present(interaction)
