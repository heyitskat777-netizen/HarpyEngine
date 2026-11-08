"""Owned Class acquisition and actual NPC Receive/Disobey Orders controls."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.m3_punishments import Picker
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine import m3_succubus as rules
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.services.m3_succubus import SuccubusService
from girlframe.services.onboarding import WorkflowError


async def open_succubus(interaction: discord.Interaction, service: SuccubusService) -> None:
    data = await asyncio.to_thread(service.menu, viewer_from_interaction(interaction))
    if not data["available"]:
        raise WorkflowError("No reviewed Succubus Protocol source is available")
    if data["owned"]:
        if data["suspended"]:
            await reply(interaction, "Succubus Protocol is suspended. Restore the original source.")
            return

        async def choose(current: discord.Interaction, option: str) -> None:
            if option == "npc":
                await open_npc_order(current, service)
            else:
                await reply(
                    current,
                    "Use the ordinary Pilot Order command for the actual "
                    "Intense-bonded Girl. Its original recipient owns the response.",
                )

        await Picker(
            interaction.user.id,
            "Succubus Protocol — actual direct Order",
            (
                ("npc", "Give an Order to an actual NPC in this scene"),
                ("pilot", "Give an Order to an Intense-bonded Girl"),
            ),
            choose,
        ).show(interaction)
        return

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        await asyncio.to_thread(
            service.buy,
            viewer_from_interaction(current),
            str(current.id),
            data["revision"],
            ActorRef.model_validate(data["actor"]),
            data["frame"],
            values["account"],
            values["donor"][0] if data["donors"] else None,
        )
        return "Succubus Protocol acquired for your actual current Frame."

    await NativeForm(
        interaction.user.id,
        f"Succubus Protocol — {data['kind'].replace('_', ' ').title()}, "
        f"{data['price']} Permissions",
        "Your Status counts as higher only for giving orders to the exact qualifying Bond partner.",
        (
            [Field("donor", "Actual Autocrat donor Frame", tuple((x, x) for x in data["donors"]))]
            if data["donors"]
            else []
        )
        + [Field("account", "Record this actual acquisition", paragraph=True)],
        submit,
    ).present(interaction)


async def open_npc_order(interaction: discord.Interaction, service: SuccubusService) -> None:
    channel = int(interaction.channel_id or 0)
    data = await asyncio.to_thread(service.targets, viewer_from_interaction(interaction), channel)
    if not data["targets"]:
        raise WorkflowError("No actual NPC in this scene is an eligible Order recipient")

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        selected = next(x for x in data["targets"] if x["token"] == values["target"][0])
        await asyncio.to_thread(
            service.issue_npc,
            viewer_from_interaction(current),
            str(current.id),
            channel,
            data["revision"],
            ActorRef.model_validate(selected["actor"]),
            data["cast"],
            values["instruction"],
        )
        return (
            "Direct Order saved for the actual NPC. "
            "Its controller owns the Receive Orders response."
        )

    await NativeForm(
        interaction.user.id,
        "Direct Order to an actual NPC",
        "Choose the actual recipient. Its controller's Pilot resources "
        "and Status do not stand in for it.",
        [
            Field(
                "target",
                "Actual NPC recipient",
                tuple((x["token"], x["label"]) for x in data["targets"]),
            ),
            Field("instruction", "Give the actual direct Order", paragraph=True),
        ],
        submit,
    ).present(interaction)


async def open_order(
    interaction: discord.Interaction,
    service: SuccubusService,
    identity: str,
    result_option: str | None = None,
) -> None:
    data = await asyncio.to_thread(service.inspect, viewer_from_interaction(interaction), identity)
    phase = data["phase"]
    if phase == "complete":
        await reply(interaction, "This actual NPC Order response is complete.")
        return
    if phase == "punishment":
        raise WorkflowError(
            "Complete the actual Handler-owned Punishment from its existing controls"
        )
    if phase == "result" and data["result"]["tier"] == "mid" and result_option is None:
        options: tuple[tuple[str, str], ...] = (
            ("tag_heat", "Give myself a Tag and gain the printed Heat"),
            ("follow", "Tell someone to follow me"),
        )
        if data["tags"]:
            options += (("reject_tag", "Reject one of my actual Tags"),)

        async def selected(current: discord.Interaction, option: str) -> None:
            await open_order(current, service, identity, option)

        await Picker(
            interaction.user.id, "NPC Disobey Orders — choose one", options, selected
        ).show(interaction)
        return
    fields: list[Field] = []
    instructions = "Direct Order: " + data["instruction"]
    if phase == "response":
        fields.append(
            Field(
                "option",
                "Actual NPC Receive Orders response",
                rules.RESPONSES + (("disobey", "Make the real Disobey Orders Play"),),
            )
        )
    elif phase == "roll":
        fields.append(
            Field("option", "Confirm actual NPC Disobey roll", (("roll", "Roll actual 2d6"),))
        )
        instructions += (
            " This ordinary NPC has no Heat pool: zero Heat is spent; no PC resources are used."
        )
    elif phase == "result":
        instructions += f" Saved result: {data['result']['total']} ({data['result']['tier']})."
        level = data["result"]["tier"]
        if level == "low":
            fields.append(
                Field("option", "Cannot disobey: choose actual follow response", rules.RESPONSES)
            )
        elif level == "high":
            fields.append(
                Field("option", "Act now and without thinking", (("act_now", "Actually act now"),))
            )
            instructions += " The printed two Heat creates no invented NPC Heat resource."
        elif result_option == "tag_heat":
            fields.append(
                Field("heat_gain", "Printed Heat choice", (("1", "One Heat"), ("2", "Two Heat")))
            )
            instructions += (
                " Author the actual self-Tag below. This NPC has no Heat pool to increase."
            )
        elif result_option == "reject_tag":
            fields.append(
                Field(
                    "tag",
                    "Actual own Tag to reject",
                    tuple((x["id"], x["label"]) for x in data["tags"]),
                )
            )
        elif result_option == "follow":
            if not data["followers"]:
                raise WorkflowError("No actual other person is available in this source scene")
            fields.append(
                Field(
                    "selected",
                    "Tell this actual person to follow",
                    tuple((x["token"], x["label"]) for x in data["followers"]),
                )
            )
        else:
            raise WorkflowError("Choose one actual mid-result consequence")
    elif phase == "follower":
        fields.append(
            Field(
                "flag",
                "Your own immediate response",
                (("yes", "Follow immediately without thinking"), ("no", "Do not follow")),
            )
        )
    elif phase == "handler":
        fields += [
            Field(
                "witness",
                "Actual Foundation member who noticed",
                (("none", "No Foundation member noticed"),)
                + tuple((x["token"], x["label"]) for x in data["witnesses"]),
            ),
            Field(
                "knows",
                "Does the actual Handler know?",
                (("yes", "Handler discovers refusal"), ("no", "Handler does not know")),
            ),
            Field(
                "punish",
                "Actual Handler Punishment",
                (("yes", "Inflict a genuine Punishment"), ("no", "No Punishment")),
            ),
        ]
        instructions += (
            " A noticed refusal really lowers NPC Status. "
            "Discovered successful refusal requires Punishment."
        )
    fields.append(
        Field(
            "account",
            "Actual self-Tag" if result_option == "tag_heat" else "Describe this actual response",
            paragraph=True,
        )
    )

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        option = values.get(
            "option", (result_option or ("review" if phase == "handler" else "follow"),)
        )[0]
        selected_token = values.get("selected", values.get("witness", ("none",)))[0]
        selected = next(
            (
                ActorRef.model_validate(x["actor"])
                for x in data["followers"]
                if x["token"] == selected_token
            ),
            None,
        )
        result = await asyncio.to_thread(
            service.choose,
            viewer_from_interaction(current),
            str(current.id),
            identity,
            data["revision"],
            option,
            values["account"],
            tag=values["tag"][0] if "tag" in values else None,
            selected=selected,
            flag=True
            if phase == "result" and data["result"]["tier"] == "high"
            else values["flag"][0] == "yes"
            if "flag" in values
            else None,
            knows=values["knows"][0] == "yes" if "knows" in values else None,
            punish=values["punish"][0] == "yes" if "punish" in values else None,
            heat_gain=int(values["heat_gain"][0]) if "heat_gain" in values else None,
        )
        return "Actual NPC response saved. Next: " + str(result["phase"]).replace("_", " ") + "."

    await NativeForm(
        interaction.user.id, "NPC Order — " + data["target"], instructions, fields, submit
    ).present(interaction)
