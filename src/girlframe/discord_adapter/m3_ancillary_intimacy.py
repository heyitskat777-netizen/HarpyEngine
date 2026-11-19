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
REVOLUTIONARY_LABELS = {
    "erase": "Erase one eligible Identity",
    "tag": "Give a Tag",
    "remain": "Choose when they may leave",
}


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
    if step == "prodigy_rank":
        await reply(
            interaction,
            "The original Status outcome remains pending for the actual Cadre authority.",
        )
        return
    if step == "prodigy_choose" and not data["npc_bonds"]:
        await reply(interaction, "There is no current NPC Bond eligible for the original choice.")
        return
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
            tuple(data.get("replace", {}).items()) or (("accept", "Accept the Identity"),),
        ),
        "chaste": (
            "Choose your own character’s private belief about the other participant.",
            (("man", "I believe they are a man"), ("not_man", "I believe they are not a man")),
        ),
        "angel_tag": (
            "You can give the other participant a Tag. They then give you space.",
            (("tag", "Give a Tag"), ("pass", "Pass")),
        ),
        "angel_space": (
            "Use your actual movement control to give them space. "
            "Then confirm your departure here.",
            (("confirm", "Confirm my recorded departure"),),
        ),
        "angel_replace": (
            "You may replace one eligible original Identity with a new one.",
            (("pass", "Pass"), *tuple(data.get("replace", {}).items())),
        ),
        "angel_helpless": (
            "Choose whether the original character becomes Helpless against yours.",
            (("yes", "Apply"), ("no", "Pass")),
        ),
        "angel_damage": (
            "Damage one actual reachable Asset of the original other character.",
            tuple(data.get("assets", {}).items()),
        ),
        "revolutionary_clear": (
            "Unmark your eligible Identities. You can then use your movement controls to leave.",
            (("finish", "Unmark and finish"), ("leave", "Unmark and leave")),
        ),
        "revolutionary_escape": (
            "Use your movement controls to leave, then confirm your departure here.",
            (("confirm", "Confirm departure"),),
        ),
        "revolutionary_offer": (
            "Deepen your Bond and offer two printed consequences.",
            (("offer", "Offer the selected consequences"),),
        ),
        "revolutionary_choice": (
            "Choose one of the offered consequences.",
            tuple((x, REVOLUTIONARY_LABELS[x]) for x in data.get("offered", ())),
        ),
        "revolutionary_erase": (
            "Erase one eligible Identity from the original character.",
            (("erase", "Erase the selected Identity"),),
        ),
        "revolutionary_erase_two": (
            "Erase two eligible Identities. You can also deepen your Bond.",
            (("erase", "Erase two"), ("bond", "Erase two and deepen our Bond")),
        ),
        "revolutionary_tag": (
            "Give the original character the chosen Tag.",
            (("tag", "Give a Tag"),),
        ),
        "revolutionary_release": (
            "Your counterpart remains until you use this choice to let them leave.",
            (("release", "Let them leave"),),
        ),
        "prodigy_choose": (
            "Give the other participant a Tag and select a current NPC Bond.",
            tuple(data.get("npc_bonds", {}).items()),
        ),
        "prodigy_jealous": (
            "Record your original NPC’s jealous reaction toward "
            + clean(data.get("known", ""))
            + ".",
            (("confirm", "Record the actual reaction"),),
        ),
        "prodigy_low": (
            "You may decline the optional Tag and Status consequence.",
            (("pass", "Decline both"),),
        ),
    }[step]
    if step in ("angel_space", "revolutionary_escape") and not data["stepped_away"]:
        await reply(interaction, instructions)
        return
    if step == "angel_damage" and not options:
        await reply(interaction, "No supported Asset is reachable. The original effect is pending.")
        return
    if step != "prodigy_jealous":
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
    if step in ("angel_tag", "angel_replace"):
        fields.append(Field("account", "New Tag or Identity if chosen", required=False))
    if step == "revolutionary_offer":
        fields.append(Field("picks", "Choose two", tuple(REVOLUTIONARY_LABELS.items()), 2, 2))
    if step in ("revolutionary_erase", "revolutionary_erase_two"):
        count = 2 if step == "revolutionary_erase_two" else 1
        if len(data["identities"]) < count:
            await reply(
                interaction, "There are too few eligible Identities. The effect stays pending."
            )
            return
        fields.append(
            Field(
                "picks",
                "Original eligible Identities",
                tuple(data["identities"].items()),
                count,
                count,
            )
        )
    if step in ("prodigy_choose", "prodigy_jealous"):
        field_label = "Actual new Tag" if step == "prodigy_choose" else "Actual NPC reaction"
        fields.append(Field("account", field_label, paragraph=step == "prodigy_jealous"))
    if step == "revolutionary_tag":
        fields.append(Field("account", "Actual new Tag"))
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
            picks=tuple(values.get("picks", ())),
        )
        return "Your original choice is saved."

    form = NativeForm(interaction.user.id, TITLE, instructions, fields, submit)
    await reply(interaction, form.text(), form)
