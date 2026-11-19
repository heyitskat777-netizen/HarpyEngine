"""Private native decisions for a proved Voidspace passage."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.ledger import clean
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.services.m3_harpy_voidspace import APPROACHES, HarpyVoidspaceService

TITLE = "Come to Me Now Once Again"


async def open_passage(
    interaction: discord.Interaction, service: HarpyVoidspaceService, identity: str
) -> None:
    data = await asyncio.to_thread(service.get, viewer_from_interaction(interaction), identity)
    step = data["step"]
    options = tuple(APPROACHES.items())
    if step == "propose":
        text = "Record how the original Harpy and Girl entered Voidspace after their escape."
        fields = [Field("account", "Describe the actual passage", paragraph=True)]
    elif step == "verify":
        text = clean(data["account"])
        fields = [
            Field("allow", "Verify the actual passage", (("yes", "Verify"), ("no", "Decline"))),
            Field("account", "Record your factual review", paragraph=True),
        ]
    elif step == "offer":
        text = "Choose an experience for the original Girl or let her choose."
        fields = [
            Field("method", "Voidspace experience", (*options, ("delegate", "Let her choose"))),
            Field("account", "Describe what you offer", paragraph=True),
        ]
    else:
        text = clean(data["account"])
        method = data["method"]
        if method is not None:
            text += "\n" + APPROACHES[method]
        fields = [
            Field(
                "asset",
                "Your choice",
                (*((f"asset/{k}", v) for k, v in data["assets"].items()), ("decline", "Decline")),
            ),
            Field(
                "account", "Describe your alteration if accepted", paragraph=True, required=False
            ),
        ]
        if method is None:
            fields.append(Field("method", "Your chosen experience", options, required=False))

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        viewer = viewer_from_interaction(current)
        account = values.get("account", "")
        if step == "propose":
            await asyncio.to_thread(
                service.start, viewer, str(current.id), identity, data["revision"], account
            )
            return "The original human facilitator can verify the passage."
        asset = values["asset"][0] if step == "gain" else None
        allow = None
        if step == "verify":
            allow = values["allow"][0] == "yes"
        elif step == "gain":
            allow = asset != "decline"
        selection = (values.get("method") or (None,))[0]
        await asyncio.to_thread(
            service.act,
            viewer,
            str(current.id),
            identity,
            data["revision"],
            step,
            account=account,
            method=selection if selection != "delegate" else None,
            asset=asset.removeprefix("asset/") if asset and asset.startswith("asset/") else None,
            allow=allow,
        )
        return "The original decision is saved."

    form = NativeForm(interaction.user.id, TITLE, text, fields, submit)
    await reply(interaction, form.text(), form)
