"""Private native controls for an actual fictional cash offer and Order."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.ledger import clean
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.services.m3_mercenary_debt import DebtService
from girlframe.services.onboarding import WorkflowError

TITLE = "Mercenary Debt"


async def open_debt(
    interaction: discord.Interaction, service: DebtService, channel: int, actor: ActorRef
) -> None:
    viewer = viewer_from_interaction(interaction)
    data = await asyncio.to_thread(service.menu, viewer, channel, actor)
    if not data["people"]:
        await reply(interaction, "There is no eligible cash offer for this character.")
        return

    async def submit(click: discord.Interaction, values: dict[str, Any]) -> str:
        await asyncio.to_thread(
            service.offer,
            viewer_from_interaction(click),
            str(click.id),
            channel,
            actor,
            data["revision"],
            values["item"][0],
            values["person"][0],
            values["account"],
        )
        return "The original facilitator has a private verification request."

    form = NativeForm(
        interaction.user.id,
        TITLE,
        "Make a fictional cash offer and give an order.",
        [
            Field("item", "Your actual fictional cash", tuple(data["items"].items())),
            Field("person", "Original recipient", tuple(data["people"].items())),
            Field("account", "Your character’s order", paragraph=True),
        ],
        submit,
    )
    await reply(interaction, form.text(), form)


async def open_debt_response(
    interaction: discord.Interaction, service: DebtService, identity: str
) -> None:
    viewer = viewer_from_interaction(interaction)
    data = await asyncio.to_thread(service.get, viewer, identity)
    step = data["step"]
    instructions = clean(data["issuer"]) + " gives this order.\n" + clean(data["instruction"])
    if step == "verify":
        instructions += (
            "\nVerify the original cash and offer in this scene (" + clean(data["item"]) + ")."
        )
        fields = [
            Field(
                "choice", "Cash offer", (("verify", "Verify cash offer"), ("dismiss", "Dismiss"))
            ),
            Field("account", "Original source or reason", paragraph=True),
        ]
    elif step == "witness":
        instructions += "\nReview whether the Foundation noticed or the Handler found out."
        fields = [
            Field(
                "choice",
                "Original scene finding",
                (
                    ("unnoticed", "Nobody with authority noticed or found out"),
                    ("refer", "Hold for human consequence review"),
                ),
            ),
            Field("account", "Original scene evidence", paragraph=True),
        ]
    elif step == "referred":
        await reply(
            interaction,
            "The original scene still requires human review of consequences.\n"
            + clean(data["witness_account"]),
        )
        return
    elif step == "respond":
        instructions += f"\nYou have {data['current_heat']} Heat."
        fields = [
            Field(
                "choice",
                "Your response",
                (("follow", "Follow the order"), ("disobey", "Roll to Disobey Orders")),
            ),
            Field("heat", "Heat to spend only if disobeying", required=False),
            Field("account", "What you do only if following", paragraph=True, required=False),
        ]
    elif data["tier"] == "mid":
        instructions += f"\nYour saved total is {data['total']}."
        instructions += " You can disobey, give yourself a Tag, and gain Heat."
        fields = [
            Field("heat", "Heat to gain", (("1", "Gain 1 Heat"), ("2", "Gain 2 Heat"))),
            Field("account", "Your self-assigned Tag"),
        ]
    else:
        instructions += f"\nYour saved total is {data['total']}."
        instructions += " You can act now without thinking and gain 2 Heat."
        fields = [Field("account", "Your immediate action", paragraph=True)]

    async def submit(click: discord.Interaction, values: dict[str, Any]) -> str:
        choice = values.get("choice", ("act",))[0]
        raw = values.get("heat", "2" if step == "result" else "0") or "0"
        if isinstance(raw, tuple):
            raw = raw[0]
        if not raw.isascii() or not raw.isdecimal() or len(raw) > 9:
            raise WorkflowError("Enter the actual amount of Heat.")
        outcome = await asyncio.to_thread(
            service.act,
            viewer_from_interaction(click),
            str(click.id),
            identity,
            data["revision"],
            choice,
            heat=int(raw),
            account=values.get("account", ""),
        )
        if outcome["outcome"] == "cannot_disobey":
            return f"Your saved total is {outcome['total']}. You cannot disobey."
        return "The original decision is saved. Check your private Inbox for any follow-up."

    form = NativeForm(interaction.user.id, TITLE, instructions, fields, submit)
    await reply(interaction, form.text(), form)


async def open_debt_contact(
    interaction: discord.Interaction,
    service: DebtService,
    channel: int,
    subject: ActorRef,
) -> None:
    viewer = viewer_from_interaction(interaction)
    data = await asyncio.to_thread(service.contact_menu, viewer, channel, subject)
    people = data["people"]
    if not people:
        await reply(interaction, "There are no eligible contacts in this scene.")
        return
    options = tuple(
        (key, ("Stop sharing with " if active else "Share with ") + label)
        for key, (label, active) in people.items()
    )

    async def submit(click: discord.Interaction, values: dict[str, Any]) -> str:
        key = values["person"][0]
        result = await asyncio.to_thread(
            service.contact,
            viewer_from_interaction(click),
            str(click.id),
            channel,
            subject,
            data["revision"],
            key,
            not people[key][1],
        )
        return (
            "Your scene contact is saved."
            if result["active"]
            else "Your scene contact is withdrawn."
        )

    form = NativeForm(
        interaction.user.id,
        TITLE,
        "Let a known person in this scene identify your character for a potential cash offer.",
        [Field("person", "Actual scene contact", options)],
        submit,
    )
    await reply(interaction, form.text(), form)
