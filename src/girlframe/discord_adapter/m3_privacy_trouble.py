"""Owned inquiry/report and voluntary disclosure after an actual protected-room death."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.ledger import clean
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.services.m3_privacy_trouble import PrivacyTroubleService


async def open_trouble(
    interaction: discord.Interaction,
    service: PrivacyTroubleService,
    identity: str,
) -> None:
    viewer = viewer_from_interaction(interaction)
    data = await asyncio.to_thread(service.get, viewer, identity)
    if data["state"] == "resolved" or not data["own"] or data["stale"]:
        text = "Actual Privacy consequence: " + data["state"] + "."
        if data["question"]:
            text += "\nQuestion: " + clean(data["question"])
        if data["disclosed"] is not None:
            text += (
                "\nThe original Girl shared a response."
                if data["disclosed"]
                else "\nThe original Girl declined disclosure."
            )
        if data["stale"]:
            text += (
                "\nRecover the original character/Handler context before changing this consequence."
            )
        await reply(interaction, text)
        return
    if data["kind"] == "privacy_inquiry_response":
        fields = [
            Field(
                "disclose",
                "Your owned response",
                (("yes", "Share my actual written response"), ("no", "Decline to disclose")),
            ),
            Field("account", "Response shared with the Handler", paragraph=True, required=False),
        ]

        async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
            await asyncio.to_thread(
                service.respond,
                viewer_from_interaction(current),
                str(current.id),
                identity,
                data["revision"],
                disclose=values["disclose"][0] == "yes",
                account=values.get("account", ""),
            )
            return "Your actual response or refusal is recorded and shared with the Handler."

        instructions = (
            "The Handler asks: " + clean(data["question"]) + "\n"
            "Only what you write in this response is shared with the Handler. "
            "Your earlier private-room scene remains private. You may decline disclosure."
        )
    else:
        choices = [("inquiry", "Conduct an actual inquiry")]
        if data["source_actor"] is not None:
            choices.append(("punishment", "Require an actual Punishment"))
        fields = [
            Field("route", "Your actual consequence", tuple(choices)),
            Field("question", "Concrete investigation question", paragraph=True, required=False),
            Field("method", "Actual inquiry method", paragraph=True, required=False),
        ]
        if data["source_actor"] is None:
            fields.extend(
                [
                    Field("report", "Concrete actual investigation report", paragraph=True),
                    Field(
                        "evidence",
                        "Evidence state",
                        (
                            ("known", "Explicit reported evidence"),
                            ("unknown", "Evidence remains unknown"),
                        ),
                    ),
                ]
            )

        async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
            result = await asyncio.to_thread(
                service.choose,
                viewer_from_interaction(current),
                str(current.id),
                identity,
                data["revision"],
                values["route"][0],
                question=values.get("question", ""),
                method=values.get("method", ""),
                report=values.get("report", ""),
                evidence=values.get("evidence", ("unknown",))[0],
            )
            return (
                "Recorded: " + str(result["state"]) + ". Reopen requests for the actual next owner."
            )

        instructions = (
            "A real Girl died during Privacy. Choose actual inquiry or discipline. "
            "You receive no private-room transcript or automatic knowledge of what happened there. "
            "For an inquiry, write a concrete question and method. "
            "A surviving original Girl supplies her own response; "
            "with no survivor, record your actual report."
        )
    form = NativeForm(viewer.user_id, "Privacy — actual consequences", instructions, fields, submit)
    await reply(interaction, form.text(), form)
