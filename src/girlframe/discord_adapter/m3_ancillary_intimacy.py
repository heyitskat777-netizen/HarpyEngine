"""Native private consent and decision forms for an original Ancillary Play."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.ledger import clean
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.services.m3_ancillary_intimacy import AncillaryIntimacyService
from girlframe.services.onboarding import WorkflowError

TITLE = "Private Ancillary Play"


async def open_ancillary_intimacy(
    interaction: discord.Interaction,
    service: AncillaryIntimacyService,
    channel: int,
    actor: ActorRef,
) -> None:
    data = await asyncio.to_thread(
        service.menu, viewer_from_interaction(interaction), channel, actor
    )
    if not data["people"]:
        await reply(interaction, "There is no eligible original scene participant.")
        return

    async def submit(click: discord.Interaction, values: dict[str, Any]) -> str:
        await asyncio.to_thread(
            service.offer,
            viewer_from_interaction(click),
            str(click.id),
            channel,
            actor,
            data["revision"],
            values["person"][0],
        )
        return "Your selection has a private invitation. Either participant can withdraw."

    form = NativeForm(
        interaction.user.id,
        TITLE,
        "Offer a private, fade-to-black encounter and its printed Player choices.",
        [Field("person", "Invite an original participant", tuple(data["people"].items()))],
        submit,
    )
    await reply(interaction, form.text(), form)


async def open_ancillary_intimacy_choice(
    interaction: discord.Interaction,
    service: AncillaryIntimacyService,
    identity: str,
    step: str,
) -> None:
    viewer = viewer_from_interaction(interaction)
    if step == "withdraw":
        revision = await asyncio.to_thread(service.withdrawal, viewer, identity)

        async def withdraw(click: discord.Interaction, _values: dict[str, Any]) -> str:
            await asyncio.to_thread(
                service.withdraw,
                viewer_from_interaction(click),
                str(click.id),
                identity,
                revision,
            )
            return "Your withdrawal is saved."

        form = NativeForm(
            interaction.user.id,
            TITLE,
            "Stop further choices in your original private encounter.",
            [Field("choice", "Your decision", (("withdraw", "Withdraw"),))],
            withdraw,
        )
        await reply(interaction, form.text(), form)
        return

    data = await asyncio.to_thread(service.get, viewer, identity)
    step = data["step"]
    instructions, options = {
        "consent": (
            "Accept the original private encounter and printed choices only if you want to.",
            (("yes", "Accept"), ("no", "Decline")),
        ),
        "verify": (
            "Verify that both original participant controllers agreed and the encounter occurred.",
            (("yes", "Verify"), ("no", "Decline")),
        ),
        "roll": ("Spend your actual Heat for the original saved Play.", (("roll", "Roll"),)),
        "middle": (
            "Choose the printed Helplessness effect and lift your own restriction this scene.",
            (("apply", "Apply the effect"),),
        ),
        "tag": ("Give the original character a Tag.", (("tag", "Give a Tag"),)),
        "reaffirm": ("Describe your own immediate action to reaffirm the Tag.", (("act", "Act"),)),
        "ask": ("Ask about their experience, keeping the encounter private.", (("ask", "Ask"),)),
        "answer": ("Answer the original question in your own words.", (("answer", "Answer"),)),
        "warboy_weaken": (
            "Weaken your original Bond. They can decide whether to give you a Tag.",
            (("apply", "Apply"),),
        ),
        "warboy_strong": (
            "Give the other participant a Tag and weaken each of their existing Bonds.",
            (("tag", "Give a Tag"),),
        ),
        "warboy_partner_tag": (
            "You can give the original Warboy a Tag.",
            (("tag", "Give a Tag"), ("pass", "Pass")),
        ),
        "warboy_bond": (
            "Deepen your Bond with the other participant and open their Identity choice.",
            (("apply", "Apply"),),
        ),
        "warboy_identity": (
            "You may propose a new Identity for the original Warboy.",
            (("offer", "Offer an Identity"), ("pass", "Pass")),
        ),
        "warboy_replace": (
            "Confirm the original Identity and choose a slot if needed.",
            tuple(data["replace"].items()) or (("accept", "Accept the Identity"),),
        ),
    }[step]
    first, second = data["participants"]
    instructions += "\nOriginal participants — " + clean(first) + " and " + clean(second)
    fields = [Field("choice", "Your decision", options)]
    if step == "roll":
        instructions += f" You have {data['heat']} Heat."
        fields.append(Field("heat", "Actual Heat to spend"))
    if step in (
        "tag",
        "reaffirm",
        "ask",
        "answer",
        "warboy_strong",
        "warboy_partner_tag",
        "warboy_identity",
    ):
        fields.append(
            Field(
                "account",
                "Your original response",
                paragraph=step in ("reaffirm", "ask", "answer"),
                required=step not in ("warboy_partner_tag", "warboy_identity"),
            )
        )
    if step == "warboy_replace":
        instructions += "\n" + clean(data["identity"])
    if step == "answer":
        instructions += "\n" + clean(data["account"])
    if step == "reaffirm" and data["tag"]:
        instructions += "\n" + clean(data["tag"])

    async def submit(click: discord.Interaction, values: dict[str, Any]) -> str:
        raw = str(values.get("heat", "0")).strip()
        if not raw.isascii() or not raw.isdecimal() or len(raw) > 9:
            raise WorkflowError("Enter the actual amount of Heat.")
        await asyncio.to_thread(
            service.act,
            viewer_from_interaction(click),
            str(click.id),
            identity,
            data["revision"],
            values["choice"][0],
            heat=int(raw),
            account=values.get("account", ""),
        )
        return "Your original choice is saved."

    form = NativeForm(interaction.user.id, TITLE, instructions, fields, submit)
    await reply(interaction, form.text(), form)
