"""Private observed-Tag dropdowns and replies owned by the original Handler human."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.ledger import clean
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.services.m2_game import GameService
from girlframe.services.m3_handler_tags import HandlerTagService
from girlframe.services.onboarding import WorkflowError


async def open_handler_tags(
    interaction: discord.Interaction,
    game: GameService,
    *,
    actor: ActorRef | None = None,
    identity: str | None = None,
    handler: ActorRef | None = None,
) -> None:
    service = HandlerTagService(game)
    viewer = viewer_from_interaction(interaction)
    if identity is not None:
        data = await asyncio.to_thread(service.get, viewer, identity)
        if data["state"] != "pending" or viewer.user_id != data["handler_controller"]:
            if data["kind"] == "attention" and viewer.user_id == data["handler_controller"]:
                await asyncio.to_thread(
                    service.read_attention, viewer, str(interaction.id), identity
                )
            await reply(
                interaction,
                "Your original Handler Tag receipt: "
                + data["kind"]
                + "; "
                + data["state"]
                + ("; " + data["response"] if data["response"] else "")
                + "\nObserved Tag: "
                + clean(data["tag_label"])
                + "\nActual request: "
                + clean(data["account"]),
            )
            return
        if data["kind"] == "helpless" and data["original_current"]:
            from girlframe.discord_adapter.m3_handler_consequences import open_consequence
            from girlframe.services.m3_handler_consequences import HandlerConsequenceService

            if not data["body_consequence"]:
                raise WorkflowError("Recover the actual original Handler consequence")
            await open_consequence(
                interaction, HandlerConsequenceService(game.store), data["body_consequence"]
            )
            return
        options = (
            (("original_handler_ended", "Close for the proved original Handler ending"),)
            if not data["original_current"]
            else (("agree", "Agree to the favour"), ("decline", "Decline the favour"))
            if data["kind"] == "favour"
            else (("pause", "Pause and control myself"), ("give_in", "Give in and act on the Tag"))
        )

        async def answer(current: discord.Interaction, values: dict[str, Any]) -> str:
            result = await asyncio.to_thread(
                service.respond,
                viewer_from_interaction(current),
                str(current.id),
                identity,
                data["revision"],
                values["response"][0],
                values["account"],
            )
            return "Your original Handler response is saved: " + str(result["state"]) + "."

        await NativeForm(
            interaction.user.id,
            "Your Handler Tag response",
            "The actual Girl spent “"
            + data["tag_label"]
            + "” to "
            + data["kind"]
            + ": "
            + data["account"]
            + ". A favour is optional; no resource reward or permission is inferred.",
            [
                Field("response", "Your actual response", options),
                Field("account", "Describe your own response", paragraph=True),
            ],
            answer,
        ).present(interaction)
        return
    channel = int(interaction.channel_id or 0)
    if actor is None:
        actors = await asyncio.to_thread(service.actors, viewer, channel)
        if not actors:
            await reply(interaction, "Join your actual Girl role to this scene first.")
            return
        if len(actors) > 1:
            from girlframe.discord_adapter.m3_punishments import Picker

            async def choose_actor(current: discord.Interaction, token: str) -> None:
                role = next(item for item in actors if item["token"] == token)
                await open_handler_tags(current, game, actor=ActorRef.model_validate(role["ref"]))

            await Picker(
                viewer.user_id,
                "Which actual Girl is acting?",
                tuple((item["token"], item["label"]) for item in actors),
                choose_actor,
            ).show(interaction)
            return
        actor = ActorRef.model_validate(actors[0]["ref"])
    data = await asyncio.to_thread(service.view, viewer, channel, actor, handler)
    if handler is None and len(data["targets"]) > 1:
        from girlframe.discord_adapter.m3_punishments import Picker

        async def choose_target(current: discord.Interaction, token: str) -> None:
            target = next(item for item in data["targets"] if item["token"] == token)
            await open_handler_tags(
                current, game, actor=actor, handler=ActorRef.model_validate(target["ref"])
            )

        await Picker(
            viewer.user_id,
            "Whose Handler Tag are you using?",
            tuple((item["token"], item["label"]) for item in data["targets"]),
            choose_target,
        ).show(interaction)
        return
    if not data["tags"]:
        await reply(interaction, "You have no currently observed Handler Tag to use.")
        return

    async def use(current: discord.Interaction, values: dict[str, Any]) -> str:
        assert actor is not None
        result = await asyncio.to_thread(
            service.use,
            viewer_from_interaction(current),
            str(current.id),
            channel,
            actor,
            data["source_sha256"],
            values["tag"][0],
            values["kind"][0],
            values["account"],
            handler_ref=ActorRef.model_validate(data["handler"]),
        )
        if result.get("consequence"):
            return (
                "Backstory Tag spent. The original Handler chooses its actual "
                "consequence in /character requests."
            )
        return "Actual Handler Tag used. " + (
            "The original Handler's attention notice is in /character requests."
            if result["state"] == "resolved"
            else "The original Handler's private reply is in /character requests."
        )

    await NativeForm(
        interaction.user.id,
        "Use an observed Handler Tag",
        "Use one actual Tag for its printed effect. "
        "Ordinary Tags are removed; persistent Tags remain. "
        "A favour may be declined; no Heat or dice are involved.",
        [
            Field(
                "tag",
                "Observed Handler Tag",
                tuple(
                    (tag["id"], tag["label"] + (" (persistent)" if tag.get("persistent") else ""))
                    for tag in data["tags"]
                ),
            ),
            Field(
                "kind",
                "What do you want?",
                (
                    ("favour", "Ask a favour — no obligation to agree"),
                    ("attention", "Attract full and undivided attention"),
                    ("compel", "Compel action on this Tag"),
                )
                + (
                    (("helpless", "Backstory Tag: cause Handler Helplessness instead"),)
                    if any(x.get("backstory_helpless") for x in data["tags"])
                    else ()
                ),
            ),
            Field("account", "Describe your actual request or action", paragraph=True),
        ],
        use,
    ).present(interaction)
