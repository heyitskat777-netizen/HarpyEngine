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
    if step == "soldier_rank_low" or (
        step in ("soldier_mid", "soldier_high") and not data["can_change_status"]
    ):
        await reply(interaction, "The original result awaits its actual Cadre Status authority.")
        return
    if step == "abyssal_void_hold":
        await reply(interaction, "The actual Void gain or Void Asset exchange remains pending.")
        return
    if step in ("mercenary_low_hold", "mercenary_high_hold"):
        await reply(interaction, "The original paid Order or Status consequence remains pending.")
        return
    if step == "prodigy_rank" and not data["can_change_status"]:
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
        "prodigy_rank": (
            "Set the original Prodigy’s rank to Ace."
            if data.get("become_ace")
            else "Apply the original Prodigy’s Status advance in her Cadre.",
            (("raise", "Set Ace" if data.get("become_ace") else "Apply the Status advance"),),
        ),
        "prodigy_low": (
            "You may decline the optional Tag and Status consequence.",
            (("pass", "Decline both"), ("apply", "Lower Status and apply a Tag"))
            if data.get("can_change_status")
            else (("pass", "Decline both"),),
        ),
        "mercenary_request": (
            "Ask for a small favour within the scene, or pass.",
            (("ask", "Ask a favour"), ("pass", "Pass")),
        ),
        "mercenary_low_terms": (
            "Choose the actual fictional cash, the instruction and the Mercenary’s Tag.",
            (*tuple(data.get("cash", {}).items()), ("hold", "Hold for the table")),
        ),
        "mercenary_low_action": (
            "Record your own actual action or leave the paid outcome pending.",
            (("done", "Record what I did"), ("hold", "Hold for the table")),
        ),
        "mercenary_low_verify": (
            "Verify the fictional cash and the original action before applying the effects.",
            (("confirm", "Confirm action and cash"), ("hold", "Leave pending")),
        ),
        "mercenary_reply": (
            "Choose whether to decline or describe your own actual fulfilment.",
            (("decline", "Decline"), ("did_it", "Record what I did")),
        ),
        "mercenary_verify": (
            "Verify the actual completed favour, or confirm it remains unfulfilled.",
            (("confirmed", "Verify fulfilment"), ("not_fulfilled", "Verify non-fulfilment")),
        ),
        "mercenary_give_tag": (
            "Give the other participant a Tag because the original favour was refused.",
            (("tag", "Give a Tag"),),
        ),
        "abyssal_erase_tag": (
            "Erase an eligible Identity and give the original participant a Tag as you leave.",
            tuple(data.get("identities", {}).items()),
        ),
        "abyssal_leave": (
            "Use your movement controls to leave, then confirm your departure here.",
            (("confirm", "Confirm departure"),),
        ),
        "abyssal_ask": (
            "Tell the original participant what you want.",
            (("ask", "Ask"),),
        ),
        "abyssal_reply": (
            "You can refuse or describe your own actual follow-through.",
            (("refuse", "Refuse"), ("did_it", "Record what I did")),
        ),
        "abyssal_verify": (
            "Verify the actual follow-through or record that it was unfulfilled.",
            (("yes", "Verify"), ("no", "Unfulfilled")),
        ),
        "abyssal_void_choice": (
            "Choose an original Void outcome.",
            (
                ("gain", "Make the Acolyte gain Void"),
                *((asset, "Take " + label) for asset, label in data.get("void_assets", {}).items()),
                ("review", "Hold a different transfer for the table"),
            ),
        ),
        "abyssal_gain": (
            "Choose how your original uncorrupted Girl Asset changes.",
            (*tuple(data.get("void_choices", {}).items()), ("review", "Hold for the table")),
        ),
        "abyssal_swap": (
            "Choose which eligible Asset on your own sheet the selected Voided Asset replaces.",
            (
                *tuple(data.get("void_replacements", {}).items()),
                *((("open_slot", "Use the open slot"),) if data.get("void_open_slot") else ()),
                ("review", "Hold for the table"),
            ),
        ),
        "abyssal_damage": (
            "Choose how many of the reachable Girl Assets to damage, from zero to all.",
            (("damage", "Apply damage to the selection"),),
        ),
        "soldier_mid": (
            "Raise Status, then choose whether to change the original Bond.",
            (
                ("pass", "Raise Status without changing the Bond"),
                ("deepen", "Raise Status and deepen the Bond"),
                *(
                    ((("weaken", "Raise Status and weaken the Bond"),))
                    if data.get("soldier_bond")
                    else ()
                ),
            ),
        ),
        "soldier_high": (
            "Apply the original Status loss, then choose whether to request a repair.",
            (("apply", "Apply the Status loss"),),
        ),
        "soldier_place": (
            "Set your Status using the original counterpart and take Good Soldier.",
            (("apply", "Apply the saved low result"),),
        ),
        "soldier_repair": (
            "Select an actual damaged Asset and unmarked resource, or pass.",
            (("pass", "Pass"), *tuple(data.get("own_damaged", {}).items()))
            if data.get("repair_choices")
            else (("pass", "Pass"),),
        ),
        "soldier_alone": (
            "Verify that this original Soldier actually has a moment to herself for this repair.",
            (("yes", "Verify the moment alone"), ("no", "Return the choice")),
        ),
    }[step]
    if (
        step in ("angel_space", "revolutionary_escape", "abyssal_leave")
        and not data["stepped_away"]
    ):
        await reply(interaction, instructions)
        return
    if step == "abyssal_erase_tag" and not options:
        await reply(
            interaction, "There is no eligible Identity. This original result remains open."
        )
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
    if step == "soldier_alone":
        instructions += "\nOriginal account — " + clean(data["account"])
    if step == "soldier_repair" and data["repair_choices"] and data["own_damaged"]:
        fields.extend(
            (
                Field(
                    "picks",
                    "Actual resource to mark",
                    tuple(data["repair_choices"].items()),
                    0,
                    1,
                    required=False,
                ),
                Field("account", "Describe your moment alone", paragraph=True, required=False),
            )
        )
    if step in ("abyssal_reply", "abyssal_verify"):
        instructions += "\nOriginal request — " + clean(data["account"])
    if step == "abyssal_verify":
        instructions += "\nOriginal participant’s follow-through — " + clean(data["actual_favor"])
    if step in ("abyssal_ask", "abyssal_reply", "abyssal_verify", "abyssal_erase_tag"):
        fields.append(
            Field(
                "account",
                "Actual new Tag" if step == "abyssal_erase_tag" else "Your original account",
                paragraph=step != "abyssal_erase_tag",
                required=step != "abyssal_reply",
            )
        )
    if step == "abyssal_damage" and data["assets"]:
        fields.append(
            Field(
                "picks",
                "Actual eligible Girl Assets",
                tuple(data["assets"].items()),
                0,
                min(4, len(data["assets"])),
                required=False,
            )
        )
    if step in ("mercenary_reply", "mercenary_verify"):
        instructions += "\nOriginal favour — " + clean(data["account"])
    if step == "mercenary_verify":
        instructions += "\nOriginal participant’s follow-through — " + clean(data["actual_favor"])
    if step in ("mercenary_request", "mercenary_reply", "mercenary_verify", "mercenary_give_tag"):
        fields.append(
            Field(
                "account",
                "Your original account",
                paragraph=step != "mercenary_give_tag",
                required=step not in ("mercenary_request", "mercenary_reply"),
            )
        )
    if step == "mercenary_low_terms" and data["cash"]:
        fields.append(Field("account", "Your original instruction", paragraph=True, required=False))
        fields.append(Field("paid_tag", "The original Tag", required=False))
    if step in ("mercenary_low_action", "mercenary_low_verify"):
        payment = data["pay_terms"]
        instructions += "\n" + clean(payment["label"]) + " · " + clean(payment["instruction"])
        fields.append(
            Field("account", "Original action or verification", paragraph=True, required=False)
        )
    if step == "mercenary_low_verify":
        instructions += "\nOriginal action — " + clean(data["actual_favor"])
    if step == "abyssal_gain" and data["void_choices"]:
        fields.append(Field("account", "Rewrite the chosen Asset", paragraph=True, required=False))
    if step == "prodigy_low" and data["can_change_status"]:
        fields.append(Field("account", "New Tag if choosing the effect", required=False))
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
            picks=(values["paid_tag"],)
            if values.get("paid_tag")
            else tuple(values.get("picks", ())),
        )
        return "Your original choice is saved."

    form = NativeForm(interaction.user.id, TITLE, instructions, fields, submit)
    await reply(interaction, form.text(), form)
