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
    "dogrunner_ask": "Ask whether she thinks she did well",
    "dogrunner_answer": "Answer in your own words",
    "dogrunner_agree": "Agree and grant the Tag and Off-Duty reward",
    "dogrunner_disagree": "Disagree and require a Punishment",
    "insurgent_ask": "Ask whether she has suspicions",
    "insurgent_yes": "My Girl suspects the Handler",
    "insurgent_no": "My Girl has no suspicions",
    "insurgent_apply": "Choose your reaction",
    "insurgent_leave_suspicions": "Leave her suspicions alone",
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
            effects=tuple(values.get("effects", ())),
            tag=(values.get("tag") or ("",))[0],
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
    if data["phase"] == "dogrunner_answer":
        fields.append(Field("account", "Your own answer", paragraph=True))
    if data["phase"] == "dogrunner_response":
        fields.append(Field("account", "Reward Tag, if agreeing", required=False))
    if data["phase"] == "insurgent_no_suspicion":
        effects: tuple[tuple[str, str], ...] = (
            ("confess", "Confess and ask forgiveness"),
            ("lower_status", "Lower her Status"),
        )
        if data["tags"]:
            effects += (("erase_tag", "Erase a known Tag"),)
        fields.extend(
            (
                Field(
                    "effects",
                    "Choose any printed reactions",
                    effects,
                    0,
                    len(effects),
                    required=False,
                ),
                Field("account", "Your own confession, if chosen", paragraph=True, required=False),
            )
        )
        if data["tags"]:
            fields.append(
                Field(
                    "tag",
                    "Actual Tag to erase, if chosen",
                    data["tags"],
                    minimum=0,
                    required=False,
                )
            )
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
    if data["phase"] == "dogrunner_response":
        summary += "\nOriginal answer: " + clean(data["account"])
    await NativeForm(
        interaction.user.id, data["playbook"] + " private scene", summary, fields, submit
    ).present(interaction)
