"""Private Call invitation, actual guest-owned consequence and Gorgon correspondence."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.m3_dive import LABELS, MANIFESTATIONS
from girlframe.discord_adapter.onboarding import reply
from girlframe.services.m3_mockingbird_communion import CallService


async def open_call(interaction: discord.Interaction, service: CallService, identity: str) -> None:
    value = await asyncio.to_thread(service.get, viewer_from_interaction(interaction), identity)
    if not value["can_act"]:
        await reply(
            interaction,
            "This source Call is "
            + value["phase"]
            + ". The next choice belongs to its actual original human.",
        )
        return
    instructions = value["message"] if value["kind"] == "relay" else value["account"]
    phase = value["phase"]
    if phase == "invite":
        fields = [
            Field(
                "decision",
                "Your own response",
                (
                    ("accept", "Reply" if value["kind"] == "relay" else "Accept actual boarding"),
                    ("decline", "Decline / no reply"),
                ),
            ),
            Field(
                "account",
                "Your actual reply"
                if value["kind"] == "relay"
                else "Describe your own acceptance/contact or refusal",
                paragraph=True,
            ),
        ]
    elif phase == "effect":
        fields = [
            Field(
                "option",
                "Choose your one actual Dive consequence",
                tuple((x, LABELS[x]) for x in value["options"]),
            ),
            Field("account", "Describe your own connection", paragraph=True),
        ]
    elif phase == "npc":
        fields = [
            Field("npc_" + str(i), "Actual manifestation: " + x["label"], MANIFESTATIONS)
            for i, x in enumerate(value["npcs"])
        ]
        fields.append(Field("account", "Describe the actual nearby changes", paragraph=True))
    else:
        effect = value["effect"]
        if value["option"] == "table_replaces_identity":
            instructions += "\nActual proposed Identity: " + effect["replacement"]
            fields = [
                Field(
                    "decision",
                    "Agree with this exact table proposal",
                    (("yes", "Accept"), ("no", "Reject; revise")),
                ),
                Field("account", "Your own agreement or reason", paragraph=True),
            ]
        else:
            instructions += "\nThe actual guest asks: " + effect["question"]
            fields = [Field("account", "Your own honest answer", paragraph=True)]

    async def commit(current: discord.Interaction, data: dict[str, Any], operation: str) -> str:
        updated = await asyncio.to_thread(
            service.respond,
            viewer_from_interaction(current),
            str(current.id),
            identity,
            value["revision"],
            operation,
            data,
        )
        return (
            "Saved your actual Call response. Current step: "
            + str(updated["phase"])
            + ". Reopen the saved Inbox to continue."
        )

    async def submit(current: discord.Interaction, answers: dict[str, Any]) -> str | None:
        if phase == "invite":
            return await commit(current, dict(account=answers["account"]), answers["decision"][0])
        if phase == "table":
            return await commit(
                current,
                dict(
                    account=answers["account"],
                    accepted=answers.get("decision", ("yes",))[0] == "yes",
                ),
                "table",
            )
        if phase == "npc":
            return await commit(
                current,
                dict(
                    account=answers["account"],
                    manifestations={
                        x["id"]: answers["npc_" + str(i)][0] for i, x in enumerate(value["npcs"])
                    },
                ),
                "npc",
            )
        option = answers["option"][0]
        data = dict(option=option, account=answers["account"])
        detail: list[Field] = []
        if option == "void_and_unmark_all":
            detail = [
                Field(
                    "asset",
                    "Your actual uncorrupted Asset",
                    tuple((x["id"], x["label"]) for x in value["assets"]),
                ),
                Field("description", "Describe its actual Void alteration", paragraph=True),
            ]
            if value.get("storage_available"):
                detail.append(
                    Field(
                        "storage",
                        "Optional gained Void destination",
                        (("yes", "Store in my actual connected Harpy"),),
                        minimum=0,
                        required=False,
                    )
                )
        elif option in ("erase_identity_and_table_question", "table_replaces_identity"):
            detail = [
                Field(
                    "identity",
                    "Your actual ordinary Identity",
                    tuple((x["id"], x["label"]) for x in value["identities"]),
                ),
                Field(
                    "detail",
                    "Your question for the actual table"
                    if option.startswith("erase")
                    else "Propose its new Identity",
                    paragraph=True,
                ),
            ]
        if not detail:
            return await commit(current, data, "effect")

        async def complete(final: discord.Interaction, details: dict[str, Any]) -> str:
            if option == "void_and_unmark_all":
                data.update(asset=details["asset"][0], description=details["description"])
                data["storage"] = bool(details.get("storage"))
            else:
                data.update(identity=details["identity"][0])
                data["question" if option.startswith("erase") else "replacement"] = details[
                    "detail"
                ]
            return await commit(final, data, "effect")

        await NativeForm(
            current.user.id, "Your actual guest consequence", instructions, detail, complete
        ).present(current)
        return None

    await NativeForm(
        interaction.user.id, "Call: actual source communion", instructions, fields, submit
    ).present(interaction)
