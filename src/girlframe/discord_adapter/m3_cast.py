"""Owner-bound scene roles; joining never claims travel, consent or piloting."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.m3_actors import LABELS
from girlframe.discord_adapter.m3_punishments import Picker
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.services.m3_cast import CastService


async def open_cast(interaction: discord.Interaction, service: CastService) -> None:
    viewer, channel = viewer_from_interaction(interaction), interaction.channel_id
    if channel is None:
        await reply(interaction, "Open scene roles in its bound server channel.")
        return
    data = await asyncio.to_thread(service.view, viewer, channel)
    owned = await asyncio.to_thread(service.actors.choices, viewer)
    own_cast = {x["token"]: x for x in data["roles"] if x.get("own")}
    options: list[tuple[str, str]] = []
    actions: dict[str, tuple[str, ActorRef | None]] = {}
    for role in owned["actors"]:
        if role["token"] not in own_cast:
            token = "join:" + role["token"]
            options.append(
                (token, "Join as " + role["label"][:60] + " (" + LABELS[role["kind"]] + ")")
            )
            actions[token] = ("join", ActorRef.model_validate(role["ref"]))
    for token, role in own_cast.items():
        key = "withdraw:" + token
        options.append((key, "Withdraw " + role["label"][:75]))
        actions[key] = ("withdraw", ActorRef.model_validate(role["ref"]))
    if data["may_facilitate"] and not data["own_facilitator"]:
        options.append(("facilitate", "Join as facilitator (no fictional character)"))
        actions["facilitate"] = ("facilitate", None)
    if data["own_facilitator"]:
        options.append(("withdraw_facilitator", "Stop facilitating this scene"))
        actions["withdraw_facilitator"] = ("withdraw_facilitator", None)

    async def choose(current: discord.Interaction, token: str) -> None:
        action, ref = actions[token]

        async def submit(actor: discord.Interaction, values: dict[str, Any]) -> str:
            await asyncio.to_thread(
                service.change,
                viewer_from_interaction(actor),
                str(actor.id),
                channel,
                data["game_revision"],
                data["cast_revision"],
                action,
                ref,
            )
            return "Your scene role is saved. Reopen /mission cast to review it."

        form = NativeForm(
            viewer.user_id,
            "Confirm scene role",
            dict(options)[token] + ". This records who you control in the scene. "
            "Fictional location, piloting and consent need their own rules.",
            [Field("confirm", "Confirm", (("yes", "Save this scene role"),))],
            submit,
        )
        await reply(current, form.text(), form)

    text = "**Scene roles**\n" + "\n".join(x["label"] for x in data["roles"])
    text += "\nFacilitating and playing the Handler are separate roles."
    if not options:
        await reply(interaction, text[:1800])
        return
    await Picker(viewer.user_id, text[:1600], tuple(options), choose).show(interaction)
