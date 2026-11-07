"""Private source-owned collar acquisition, trigger and actual survival Play entry."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.ledger import clean
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine.m2 import PlayInput
from girlframe.services.m3_bomb_collar import BombCollarService


async def open_collar(
    interaction: discord.Interaction, service: BombCollarService, identity: str | None = None
) -> None:
    data = await asyncio.to_thread(service.menu, viewer_from_interaction(interaction), identity)
    if data["kind"] == "trigger":
        body = data["body"]
        if body["phase"] != "survival" or not data["own"] or data["sheet"] is None:
            await reply(
                interaction,
                "Actual bomb-collar outcome: "
                + body["phase"]
                + ".\n"
                + clean(body["account"])
                + ("\nActual survival action: " + body["action"] if body["action"] else "")
                + ("\nActual career archive: " + body["archive"] if body["archive"] else ""),
            )
            return
        sheet = data["sheet"]

        async def respond(current: discord.Interaction, values: dict[str, Any]) -> str:
            result = await asyncio.to_thread(
                service.respond,
                viewer_from_interaction(current),
                str(current.id),
                body["id"],
                data["revision"],
                PlayInput(
                    play=values["play"][0],
                    heat=int(values["heat"][0]),
                    identity=(values.get("identity") or (None,))[0],
                    gain=int(values["gain"][0]),
                    piloting=values["piloting"] == ("yes",),
                    context=values["context"],
                    trigger_confirmed=True,
                    source_work=body["id"],
                ),
            )
            return "Actual survival Play started. Continue its owned normal choices: " + str(
                result["action_id"]
            )

        await NativeForm(
            interaction.user.id,
            "Survive the actual triggered collar",
            "Your original Girl must Dive Deep or actually survive another way. "
            "Keep Your Head uses its normal traits and Handler sufficiency ruling; "
            "an insufficient escape from this actual detonation is lethal. "
            "The collar supplies no automatic injury, Helplessness or free Heat. "
            "If already started, resume the same actual Play through /choice.",
            [
                Field(
                    "play",
                    "Actual survival Play",
                    (("dive_deep", "Dive Deep"), ("keep_your_head", "Keep Your Head")),
                ),
                Field(
                    "identity",
                    "Actual unmarked Identity (optional)",
                    tuple(
                        (x["id"], clean(x["name"])) for x in sheet["identities"] if not x["marked"]
                    ),
                    0,
                    1,
                    required=False,
                ),
                Field("gain", "Heat from that Identity", tuple((str(x), str(x)) for x in range(4))),
                Field(
                    "heat",
                    "Actual Heat to spend",
                    tuple((str(x), str(x)) for x in range(min(24, sheet["heat"] + 3) + 1)),
                ),
                Field(
                    "piloting",
                    "Actual piloting context",
                    (("no", "Not piloting"), ("yes", "Actually piloting")),
                ),
                Field("context", "What you actually do to survive", paragraph=True),
            ],
            respond,
        ).present(interaction)
        return
    if data["acquisition"] is None:
        if not data["awards"]:
            await reply(interaction, "One genuine held advancement is needed for Bomb Collars.")
            return

        async def buy(current: discord.Interaction, values: dict[str, Any]) -> str:
            await asyncio.to_thread(
                service.buy,
                viewer_from_interaction(current),
                str(current.id),
                values["award"][0],
                data["revision"],
                values["account"],
            )
            return "Actual current Cadre collars supplied. Reopen this acquisition in History."

        await NativeForm(
            interaction.user.id,
            "Acquire Bomb Collars",
            "One held advancement supplies actual ordinary collars to the supported current Cadre. "
            "No weapon Asset or extra fee.",
            [
                Field(
                    "award",
                    "Actual held advancement",
                    tuple((x["id"], clean(x["label"])[:100]) for x in data["awards"]),
                ),
                Field("account", "Actual acquisition", paragraph=True),
            ],
            buy,
        ).present(interaction)
        return
    available = [x for x in data["collars"] if x["trigger"] is None]
    if not available or not data["scenes"]:
        await reply(
            interaction,
            "Actual collar acquisition saved. Trigger outcomes remain in private History. "
            "A supported original Girl must join a real response scene before a trigger.",
        )
        return

    async def trigger(current: discord.Interaction, values: dict[str, Any]) -> str:
        await asyncio.to_thread(
            service.trigger,
            viewer_from_interaction(current),
            str(current.id),
            values["collar"][0],
            data["revision"],
            int(values["scene"][0]),
            values["account"],
        )
        return "Actual collar triggered. Its original Girl owns the survival response in Inbox."

    await NativeForm(
        interaction.user.id,
        "Actual Cadre bomb collars",
        "Collars can be used like Tags but never embraced or rejected. "
        "Triggering creates a real lethal survival obligation; no automatic damage or extra roll.",
        [
            Field(
                "collar",
                "Actual original Girl's collar",
                tuple((x["id"], "Girl " + x["target"]["entity"]) for x in available),
            ),
            Field(
                "scene",
                "Actual response scene",
                tuple((str(x["channel"]), "Scene " + str(x["channel"])) for x in data["scenes"]),
            ),
            Field("account", "Actual collar trigger", paragraph=True),
        ],
        trigger,
    ).present(interaction)
