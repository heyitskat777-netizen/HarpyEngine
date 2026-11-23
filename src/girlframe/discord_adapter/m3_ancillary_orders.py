"""Private native controls for direct original optional-character Orders."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.ledger import clean
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.services.m3_ancillary_orders import AncillaryOrderService
from girlframe.services.onboarding import WorkflowError


async def open_ancillary_order(
    interaction: discord.Interaction,
    service: AncillaryOrderService,
    channel: int,
    actor: ActorRef,
) -> None:
    data = await asyncio.to_thread(
        service.menu, viewer_from_interaction(interaction), channel, actor
    )
    if not data["people"]:
        await reply(interaction, "There is no current original character eligible for this Order.")
        return

    async def submit(click: discord.Interaction, values: dict[str, Any]) -> str:
        reference = values.get("reference", ())
        pronouns = values.get("pronouns", ())
        await asyncio.to_thread(
            service.issue,
            viewer_from_interaction(click),
            str(click.id),
            channel,
            actor,
            data["revision"],
            values["person"][0],
            values.get("instruction", ""),
            reference=reference[0] if reference else None,
            pronouns=pronouns[0] if pronouns else None,
        )
        return "The original recipient has a private Order."

    fields = [
        Field("person", "Original recipient", tuple(data["people"].items())),
        Field(
            "instruction", "Your original Order", paragraph=True, required=not data["references"]
        ),
    ]
    if data["references"]:
        fields.extend(
            (
                Field(
                    "reference",
                    "Known person for spouse’s address directive",
                    tuple(data["references"].items()),
                    required=False,
                ),
                Field(
                    "pronouns",
                    "Which address to use",
                    (("he", "He"), ("she", "She")),
                    required=False,
                ),
            )
        )
    form = NativeForm(
        interaction.user.id,
        "Ancillary Order",
        "Write an Order or select both fields for a spouse’s address directive.",
        fields,
        submit,
    )
    await reply(interaction, form.text(), form)


async def open_order_response(
    interaction: discord.Interaction,
    service: AncillaryOrderService,
    identity: str,
) -> None:
    data = await asyncio.to_thread(service.get, viewer_from_interaction(interaction), identity)
    stage = data["stage"]
    instructions = clean(data["issuer"]) + " gives this Order.\n" + clean(data["instruction"])
    if stage == "held":
        await reply(
            interaction, "The original Refusal still needs human Status or Punishment review."
        )
        return
    choices: tuple[tuple[str, str], ...]
    fields: list[Field] = []
    if stage == "respond":
        if data["isolation"]:
            instructions += "\nUse actual movement to reach the Handler if you choose to follow."
        choices = (
            (
                (
                    "follow",
                    "Record that I heard the address directive" if data["address"] else "Follow",
                ),
            )
            if data["forbidden"]
            else (
                ("follow", "Follow"),
                ("disobey", "Roll to Disobey"),
            )
        )
        if not data["forbidden"]:
            instructions += f"\nYou have {data['heat']} Heat."
            fields.append(Field("heat", "Heat only if rolling", required=False))
        fields.append(
            Field(
                "account",
                "Confirm you heard it" if data["address"] else "What you do only if following",
                paragraph=True,
                required=False,
            )
        )
    elif stage == "tag":
        choices = (("pass", "Pass"),)
        if data["good_soldier"]:
            instructions += "\nYour saved roll includes −1 from Good Soldier."
        if data["warboy_low"]:
            instructions += "\nYour active Bond makes this a 7− result."
        if data["tags"]:
            choices += (("mark", "Mark one of my Tags"),)
            fields.extend(
                [
                    Field(
                        "tag",
                        "Your eligible Tag",
                        tuple(data["tags"].items()),
                        0,
                        1,
                        required=False,
                    ),
                    Field(
                        "direction",
                        "Tag modifier",
                        (("-1", "−1"), ("1", "+1")),
                        0,
                        1,
                        required=False,
                    ),
                    Field("account", "Why the Tag is relevant", required=False),
                ]
            )
    elif stage == "outcome":
        choices = (("act", "Apply the original result"),)
        instructions += f"\nYour saved total is {data['total']}."
        if data["level"] == "mid":
            fields.extend(
                [
                    Field("heat", "Heat to gain", (("1", "Gain 1 Heat"), ("2", "Gain 2 Heat"))),
                    Field("account", "Your new Tag"),
                ]
            )
        else:
            fields.append(Field("account", "Your immediate action", paragraph=True))
    else:
        if data["payment_pending"]:
            instructions += "\nOriginal action — " + clean(data["actual_follow"])
        choices = (
            (
                ("confirm_follow", "Confirm actual follow-through and transfer the fee"),
                ("hold", "Leave the payment pending"),
            )
            if data["payment_pending"]
            else (("unheard", "No authority noticed"), ("hold", "Keep consequences pending"))
        )
        fields.append(Field("account", "Actual scene evidence", paragraph=True))

    async def submit(click: discord.Interaction, values: dict[str, Any]) -> str:
        raw = values.get("heat", "2" if stage == "outcome" else "0") or "0"
        if isinstance(raw, tuple):
            raw = raw[0]
        if not raw.isascii() or not raw.isdecimal() or len(raw) > 9:
            raise WorkflowError("Enter your actual Heat amount.")
        await asyncio.to_thread(
            service.act,
            viewer_from_interaction(click),
            str(click.id),
            identity,
            data["revision"],
            values["choice"][0],
            heat=int(raw),
            tag=values["tag"][0] if values.get("tag") else None,
            direction=int(values["direction"][0]) if values.get("direction") else 0,
            account=values.get("account", ""),
        )
        return "Your original decision is saved."

    form = NativeForm(
        interaction.user.id,
        "Ancillary Order",
        instructions,
        [Field("choice", "Your decision", choices), *fields],
        submit,
    )
    await reply(interaction, form.text(), form)


async def open_illegal_pronouns(
    interaction: discord.Interaction,
    service: AncillaryOrderService,
    actor: ActorRef,
) -> None:
    data = await asyncio.to_thread(
        service.pronoun_menu,
        viewer_from_interaction(interaction),
        actor,
    )

    async def submit(click: discord.Interaction, values: dict[str, Any]) -> str:
        await asyncio.to_thread(
            service.set_pronouns,
            viewer_from_interaction(click),
            str(click.id),
            actor,
            data["revision"],
            values["pronouns"],
        )
        return "Your original sheet now shows the pronouns you chose."

    form = NativeForm(
        interaction.user.id,
        "Illegal Girl",
        "Choose the pronouns for your original sheet.",
        [Field("pronouns", "Your pronouns")],
        submit,
    )
    await reply(interaction, form.text(), form)
