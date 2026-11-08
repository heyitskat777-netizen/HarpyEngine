"""Owned departure and actual source-bound Investor performance Plays."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine.m2 import PlayInput
from girlframe.services.m2_game import GameService
from girlframe.services.m3_vatgrown_plays import VatgrownPlaysService
from girlframe.services.m3_vatgrown_support import departure_order
from girlframe.services.onboarding import WorkflowError


async def open_investment_performance(
    interaction: discord.Interaction, game: GameService, investment_id: str
) -> None:
    viewer = viewer_from_interaction(interaction)
    data = await asyncio.to_thread(VatgrownPlaysService(game).view, viewer, investment_id)
    if data.get("type") != "investment":
        raise WorkflowError("Open the actual original Prime Investment outcome")
    value = data["investment"]
    sheet = await asyncio.to_thread(game.sheet, viewer)
    if (
        value["phase"] != "fulfil"
        or value["owner"]["kind"] != "pilot"
        or value["owner"]["entity"] != str(viewer.user_id)
        or value["owner"].get("incarnation") != sheet["character_id"]
        or not value.get("desire_event")
        or value.get("performance_action")
    ):
        raise WorkflowError("Only the actual original Girl starts her pending performance")
    if interaction.channel_id is None:
        raise WorkflowError("Use your actual joined performance scene channel")
    channel = interaction.channel_id
    scene = await asyncio.to_thread(game.scene_info, viewer, channel)
    if not scene["joined"]:
        raise WorkflowError("Join this actual performance scene before preparing the Play")
    identities = [
        x for x in sheet["identities"] + sheet.get("additional_identities", []) if not x["marked"]
    ]
    from girlframe.discord_adapter.m3_dampener import fields as dampener_fields
    from girlframe.discord_adapter.m3_dampener import modifier as dampener_modifier
    from girlframe.discord_adapter.m3_nightmare import keep_info
    from girlframe.services.m3_dampener import DampenerService
    from girlframe.services.m3_nightmare import NightmareService

    nightmare = await keep_info(interaction, NightmareService(game))
    fields = [
        Field(
            "identity",
            "Optional owned Identity to mark",
            tuple((x["id"], x["name"]) for x in identities),
            minimum=0,
            required=False,
        ),
        Field(
            "gain",
            "Identity Heat gained; 0 without marking",
            tuple((str(x), str(x)) for x in range(6)),
        ),
        Field("pair_share", "Paired Heat sent to Pair", tuple((str(x), str(x)) for x in range(6))),
        Field(
            "heat",
            "Heat committed; Nightmare Keep uses 0" if nightmare else "Heat committed",
            tuple((str(x), str(x)) for x in ((0,) if nightmare else range(sheet["heat"] + 6))),
        ),
        Field("piloting", "Are you actually piloting your Frame?", (("yes", "Yes"), ("no", "No"))),
        Field("context", "Actual danger, intended action and performance", paragraph=True),
        Field(
            "trigger", "Actual Keep Your Head trigger", (("yes", "The printed trigger applies"),)
        ),
    ]
    fields.extend(await dampener_fields(interaction, DampenerService(game)))

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        identity = values.get("identity", ())
        result = await asyncio.to_thread(
            game.begin,
            viewer_from_interaction(current),
            str(current.id),
            channel,
            sheet["revision"],
            PlayInput(
                play="keep_your_head",
                source_work=investment_id,
                identity=identity[0] if identity else None,
                gain=int(values["gain"][0]),
                pair_share=int(values["pair_share"][0]),
                heat=int(values["heat"][0]),
                dampener_modifier=dampener_modifier(values),
                piloting=values["piloting"][0] == "yes",
                context=values["context"],
                trigger_confirmed=values["trigger"] == ("yes",),
            ),
        )
        return (
            "Actual performance Play confirmed: "
            + str(result["action_id"])
            + ". Finish its real choices and consequences; "
            "the Investor judges fulfilment afterward."
        )

    form = NativeForm(
        interaction.user.id,
        "Prime Investment: actual performance",
        "Investor's desire: "
        + value["desire"]
        + "\nUse Keep Your Head only when its actual trigger applies. "
        "This starts a real Play; it does not declare the desire fulfilled.",
        fields,
        submit,
    )
    await reply(interaction, form.text(), form)


async def open_vatgrown_departure(
    interaction: discord.Interaction, game: GameService, session: str
) -> None:
    data = await asyncio.to_thread(
        VatgrownPlaysService(game).view, viewer_from_interaction(interaction), session
    )

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        viewer = viewer_from_interaction(current)
        order = await asyncio.to_thread(
            departure_order,
            game,
            viewer,
            str(current.id) + ":departure",
            session,
            data["revision"],
            values["departure"],
        )
        result = await asyncio.to_thread(
            game.begin,
            viewer,
            str(current.id),
            order["channel"],
            order["sheet_revision"],
            PlayInput(
                play="disobey_orders",
                order_id=order["order_id"],
                heat=int(values["heat"][0]),
                context=values["departure"],
                trigger_confirmed=True,
            ),
        )
        return "Departure awaits your real Disobey result. Play: " + str(result["action_id"])

    form = NativeForm(
        interaction.user.id,
        "Attempt to leave",
        "Resolve Disobey before leaving their side.",
        [
            Field("departure", "Your actual attempted departure", paragraph=True),
            Field("heat", "Heat committed", tuple((str(i), str(i)) for i in range(5))),
        ],
        submit,
    )
    await reply(interaction, form.text(), form)
