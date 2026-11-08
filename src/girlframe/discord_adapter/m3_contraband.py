"""Private random finds, owned Asset choices and explicit public-sheet sharing."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.labels import entity_label
from girlframe.discord_adapter.ledger import clean
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.m3_punishments import Picker
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine.m3_requisition_state import GirlAsset
from girlframe.services.m3_contraband import ContrabandService
from girlframe.services.onboarding import WorkflowError


async def open_find(
    interaction: discord.Interaction, service: ContrabandService, identity: str
) -> None:
    data = await asyncio.to_thread(service.get, viewer_from_interaction(interaction), identity)
    options: tuple[tuple[str, str], ...] = (
        (("details", "View the saved Asset"), ("account", "View your recorded find"))
        if data["taken"] is True
        else (("account", "View your saved decision"),)
    )
    if data["taken"] is None:
        options = (
            ("add", "Add this find as a Girl Asset"),
            ("decline", "Decline the optional Asset"),
        )
    elif data["can_share"]:
        options += (("share", "Share this Asset on my public sheet"),)

    async def choose(current: discord.Interaction, operation: str) -> None:
        latest = await asyncio.to_thread(service.get, viewer_from_interaction(current), identity)
        if operation in ("details", "account"):
            if operation == "details" and latest["choice"]:
                text = (
                    "**Your saved contraband Asset**\n"
                    + clean(latest["choice"]["name"])
                    + "\n"
                    + clean(latest["choice"]["description"])
                )
            else:
                text = "**Your saved find decision**\n" + (
                    clean(latest["account"])
                    if latest["account"]
                    else "You explicitly declined the optional Asset."
                )
            await reply(current, text, picker)
            return
        if latest["actor_sha256"] is None or not latest["eligible"]:
            raise WorkflowError("Recover the original Girl before changing this saved find.")
        if operation == "share":
            if not latest["can_share"]:
                raise WorkflowError("Refresh the actual concealed Asset before sharing it.")

            async def share(response: discord.Interaction, values: dict[str, Any]) -> str:
                await asyncio.to_thread(
                    service.share,
                    viewer_from_interaction(response),
                    str(response.id),
                    identity,
                    latest["actor_sha256"],
                )
                return "This Asset is now included in your public sheet's published Assets."

            form = NativeForm(
                current.user.id,
                "Share your Asset",
                "Other sheet viewers will be able to read this Asset "
                "under your existing public Asset settings.",
                [Field("confirm", "Confirm publication", (("yes", "Share this actual Asset"),))],
                share,
            )
        else:
            if latest["taken"] is not None:
                await open_find(current, service, identity)
                return
            take = operation == "add"
            assets = latest["assets"]
            fields = []
            if take:
                fields = [
                    Field("name", "Name your contraband Girl Asset"),
                    Field("description", "Describe the Asset", paragraph=True),
                    Field("account", "Confirm how you actually found it", paragraph=True),
                ]
                if len(assets) >= 4:
                    replacements = tuple(
                        (x["id"], entity_label(x)) for x in assets if x["can_replace_at_limit"]
                    )
                    if not replacements:
                        await reply(
                            current,
                            "Your Girl has no replaceable non-Void Asset at the four-Asset limit. "
                            "You can keep this decision pending or decline the optional Asset.",
                            picker,
                        )
                        return
                    fields.append(Field("replace", "Non-Void Girl Asset to replace", replacements))
            fields.append(
                Field(
                    "confirm",
                    "Your decision",
                    (("yes", "Add the Asset" if take else "Decline the optional Asset"),),
                )
            )

            async def submit(response: discord.Interaction, values: dict[str, Any]) -> str:
                await asyncio.to_thread(
                    service.respond,
                    viewer_from_interaction(response),
                    str(response.id),
                    identity,
                    latest["find_sha256"],
                    latest["actor_sha256"],
                    take,
                    GirlAsset(
                        name=values["name"],
                        description=values["description"],
                        replace=values.get("replace", (None,))[0],
                    )
                    if take
                    else None,
                    values.get("account", ""),
                )
                return (
                    "Girl Asset added to your private sheet. Reopen this find to review it."
                    if take
                    else "Optional Asset declined. Your resources are unchanged."
                )

            form = NativeForm(
                current.user.id,
                "Your private contraband find",
                "Choose whether to record the actual find as an ordinary Girl Asset. "
                "Added Assets remain hidden in public sheet views until you explicitly share them. "
                "Normal Asset limits apply.",
                fields,
                submit,
            )
        await reply(current, form.text(), form)

    status = (
        "Choose whether to add the optional Asset."
        if data["taken"] is None
        else "Added to your private sheet."
        if data["taken"]
        else "Optional Asset declined."
    )
    picker = Picker(
        interaction.user.id, "**Your private contraband find**\n" + status, options, choose
    )
    await picker.show(interaction)


async def open_finds(interaction: discord.Interaction, service: ContrabandService) -> None:
    rows = await asyncio.to_thread(service.list, viewer_from_interaction(interaction))
    if not rows:
        await reply(interaction, "You have no saved private contraband finds.")
        return

    async def choose(current: discord.Interaction, identity: str) -> None:
        await open_find(current, service, identity)

    await Picker(
        interaction.user.id,
        "**Your private contraband finds**",
        tuple((x["id"], x["state"].title() + " — " + x["label"]) for x in rows),
        choose,
    ).show(interaction)
