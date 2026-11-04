"""Private paginated Asset source selection and explicit one-Permission payment."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.labels import entity_label
from girlframe.discord_adapter.ledger import clean
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.m3_punishments import Picker
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_requisition_state import Installation
from girlframe.services.m3_requisitions import RequisitionService


async def open_requisitions(interaction: discord.Interaction, service: RequisitionService) -> None:
    viewer = viewer_from_interaction(interaction)
    data = await asyncio.to_thread(service.view, viewer)
    purchases = {x["id"]: x for x in data["purchases"]}
    options = (("install", "Buy an Asset Installment — 1 Permission"),) + tuple(
        (key, "Saved Asset purchase " + key[:8]) for key in purchases
    )

    async def choose(current: discord.Interaction, token: str) -> None:
        if token in purchases:
            receipt = purchases[token]
            actual = next((x for x in data["frame_assets"] if x["id"] == receipt["asset_id"]), None)
            await reply(
                current,
                "**Your saved purchase**\n1 Permission paid. Receipt `"
                + token
                + "`.\n"
                + (
                    clean(actual["name"])
                    if actual
                    else "The original purchased Asset is not in your current Frame."
                )
                + "\n"
                + clean(receipt["installation"]["account"]),
            )
            return
        entries = {x["key"]: x for x in data["catalog"]}
        sources = tuple(
            (key, x["name"][:65] + " — " + x["frame"][:25]) for key, x in entries.items()
        ) + (("custom", "Write my own ordinary Frame Asset"),)

        async def select_asset(selected: discord.Interaction, source: str) -> None:
            custom = source == "custom"
            fields = [Field("name", "Name your new Frame Asset")] if custom else []
            fields += [
                Field("description", "Describe the installed Asset", paragraph=True),
                Field("account", "Describe the actual installation", paragraph=True),
            ]
            if len(data["frame_assets"]) >= 5:
                fields.append(
                    Field(
                        "replace",
                        "Non-Void Frame Asset to replace",
                        tuple(
                            (x["id"], entity_label(x))
                            for x in data["frame_assets"]
                            if not x["void"]
                        ),
                    )
                )
            fields.append(
                Field(
                    "confirm",
                    "Confirm purchase",
                    (("yes", "Pay 1 Permission and install this Asset"),),
                )
            )

            async def submit(response: discord.Interaction, values: dict[str, Any]) -> str:
                entry = entries.get(source)
                result = await asyncio.to_thread(
                    service.buy,
                    viewer_from_interaction(response),
                    str(response.id),
                    ActorRef.model_validate(data["actor"]),
                    data["source_sha256"],
                    Installation(
                        from_frame=entry["frame"] if entry else None,
                        index=entry["index"] if entry else None,
                        name=values["name"] if custom else "",
                        description=values["description"],
                        account=values["account"],
                        replace=values.get("replace", (None,))[0],
                        trigger_confirmed=True,
                    ),
                )
                return (
                    "Asset installed. 1 Permission paid; "
                    + str(result["permissions"])
                    + " remaining. Saved receipt: "
                    + str(result["id"])
                    + "."
                )

            form = NativeForm(
                viewer.user_id,
                "Confirm Asset Installment",
                "Your selected Asset is "
                + ("your own creation" if custom else entries[source]["name"])
                + ". Review the actual installation, replacement and price before paying. "
                "This grants an ordinary undamaged Asset; Frame rules and Void are separate.",
                fields,
                submit,
            )
            await reply(selected, form.text(), form)

        await Picker(
            viewer.user_id,
            "**Choose your new Frame Asset**\nPrinted Assets from any base Frame "
            "or your own creation. 1 Permission.",
            sources,
            select_asset,
        ).show(current)

    await Picker(
        viewer.user_id,
        "**Your Requisitions**\nAvailable Permissions: "
        + str(data["permissions"])
        + ". Choose a purchase or saved receipt.",
        options,
        choose,
    ).show(interaction)
