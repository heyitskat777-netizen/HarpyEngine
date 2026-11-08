"""Private real collateral targets, without free-form IDs or completion acknowledgements."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine.m3_collateral import Selection, Target
from girlframe.services.m3_collateral import CollateralService


async def open_collateral(
    interaction: discord.Interaction, service: CollateralService, identity: str
) -> None:
    data = await asyncio.to_thread(service.get, viewer_from_interaction(interaction), identity)
    if data["phase"] != "choose":
        await reply(
            interaction,
            "Actual collateral is saved; its source consequences remain available in your inbox.",
        )
        return
    fields = []
    if data["structures"]:
        fields.append(
            Field(
                "structures",
                "Actual major structures destroyed",
                tuple((x["id"], x["name"]) for x in data["structures"]),
                0,
                len(data["structures"]),
                required=False,
            )
        )
    if data["objects"]:
        fields.append(
            Field(
                "objects",
                "Other actual held objects destroyed",
                tuple((x["id"], x["name"]) for x in data["objects"]),
                0,
                len(data["objects"]),
                required=False,
            )
        )
    if data["assets"]:
        fields.append(
            Field(
                "assets",
                "Actual original-scene Assets damaged",
                tuple((str(i), x["label"]) for i, x in enumerate(data["assets"])),
                0,
                len(data["assets"]),
                required=False,
            )
        )
    fields.extend(
        [
            Field(
                "ordinary",
                "Other concrete objects/environment destroyed (one per line)",
                paragraph=True,
                required=False,
            ),
            Field("account", "What actually happens?", paragraph=True),
            Field("reach", "How does this real strike reach every selected thing?", paragraph=True),
        ]
    )

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        selected = tuple(
            Target.model_validate({k: data["assets"][int(i)][k] for k in ("actor", "asset")})
            for i in values.get("assets", ())
        )
        await asyncio.to_thread(
            service.submit,
            viewer_from_interaction(current),
            str(current.id),
            identity,
            data["revision"],
            data["game_revision"],
            Selection(
                structures=values.get("structures", ()),
                objects=values.get("objects", ()),
                assets=selected,
                ordinary=tuple(
                    x.strip() for x in values.get("ordinary", "").splitlines() if x.strip()
                ),
                account=values["account"],
                reach=values["reach"],
            ),
        )
        return (
            "Concrete collateral saved; actual damage, Budget "
            "and quadrant aftermath are source-bound."
        )

    form = NativeForm(
        interaction.user.id,
        "Actual collateral consequences",
        "Choose what the real strike can reasonably destroy. "
        "Canonical structures and Assets receive their real effects.",
        fields,
        submit,
    )
    await reply(interaction, form.text(), form)
