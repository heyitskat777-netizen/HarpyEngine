"""Native private consent and playbook-specific choices."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.ledger import clean
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine.m3_handler_private_scene import Book
from girlframe.services.m3_handler_private_scene import HandlerPrivateSceneService

CHOICES = {
    "consent": "Agree to the private scene",
    "withdraw": "Decline or withdraw",
    "attest": "Confirm that the scene took place",
    "ask": "Ask for a favor",
    "accept": "Accept the favor",
    "decline": "Decline the favor",
    "fulfilled": "Submit a completed Play that fulfilled the favor",
    "failed": "Report that the favor was not completed",
    "confirm": "Confirm that the completed Play fulfilled the favor",
    "find_failed": "Find that the favor was not completed",
    "trainer_ask": "Ask how she understands the private scene",
    "trainer_yes": "I understood the scene as intimacy",
    "trainer_understands": "I understood it as conditioning",
    "install_speak": "Install Speak",
    "pass_phrase": "Leave without installing a phrase",
}


async def open_invite(
    interaction: discord.Interaction,
    service: HandlerPrivateSceneService,
    revision: int,
    channel: int,
    *,
    playbook: Book = "Mistress",
) -> None:
    async def submit(current: discord.Interaction, _: dict[str, Any]) -> str:
        await asyncio.to_thread(
            service.invite,
            viewer_from_interaction(current),
            str(current.id),
            revision,
            channel,
            playbook=playbook,
        )
        return "The original Girl can privately accept or decline."

    await NativeForm(
        interaction.user.id,
        "Offer a private scene",
        "Invite the original Girl in this one-on-one scene.",
        [Field("offer", "Your choice", (("offer", "Send the private invitation"),))],
        submit,
    ).present(interaction)


async def open_favor(
    interaction: discord.Interaction, service: HandlerPrivateSceneService, identity: str
) -> None:
    data = await asyncio.to_thread(service.menu, viewer_from_interaction(interaction), identity)
    if not data["options"]:
        await reply(interaction, "This private choice is saved. Check for the next owned step.")
        return

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        text = (
            (values.get("identity") or ("",))[0]
            if data["phase"] == "trainer_answer"
            else (values.get("account", ""))
        )
        await asyncio.to_thread(
            service.respond,
            viewer_from_interaction(current),
            str(current.id),
            identity,
            data["revision"],
            values["choice"][0],
            text=text,
            action=values.get("action", ""),
        )
        return "Your private choice is recorded."

    fields = [Field("choice", "Your choice", tuple((x, CHOICES[x]) for x in data["options"]))]
    if data["phase"] in ("favor", "owed", "review"):
        fields.append(
            Field(
                "account",
                "Favor requested" if data["phase"] == "favor" else "Outcome account",
                paragraph=True,
            )
        )
    if data["phase"] == "owed":
        fields.append(Field("action", "Completed Play reference, if fulfilled", required=False))
    if data["identities"]:
        fields.append(
            Field(
                "identity",
                "Your erased Identity, if you understood this as conditioning",
                tuple((identity, clean(label)) for identity, label in data["identities"]),
                minimum=0,
                required=False,
            )
        )
    summary = "Your original private choice."
    if data["favor"]:
        summary += "\nFavor: " + clean(data["favor"])
    if data["phase"] == "review":
        summary += "\nSubmitted Play: " + clean(data["action"])
        summary += "\nAccount: " + clean(data["account"])
    await NativeForm(
        interaction.user.id, data["playbook"] + " private scene", summary, fields, submit
    ).present(interaction)
