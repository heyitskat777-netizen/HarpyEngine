"""Owned advancement acquisition, real equipment installation and expiry fact review."""

import asyncio
from typing import Any, Literal

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.m3_punishments import Picker
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_modular import Replacement
from girlframe.services.m3_supply_drop import SupplyDropService
from girlframe.services.onboarding import WorkflowError


async def open_supply_drop(
    interaction: discord.Interaction, service: SupplyDropService, mission_id: str | None = None
) -> None:
    data = await asyncio.to_thread(service.menu, viewer_from_interaction(interaction), mission_id)
    if not data["owned"]:
        if not data["awards"]:
            await reply(interaction, "Supply Drop costs one actual held Handler advancement.")
            return

        async def buy(current: discord.Interaction, values: dict[str, Any]) -> str:
            await asyncio.to_thread(
                service.buy,
                viewer_from_interaction(current),
                str(current.id),
                values["award"][0],
                data["revision"],
                values["account"],
            )
            return "Supply Drop acquired. One advancement spent; no Permissions charged."

        await NativeForm(
            interaction.user.id,
            "Acquire Supply Drop — one Handler advancement",
            "Once per Mission, repair one actual Asset "
            "or deliver custom temporary Frame equipment.",
            [
                Field(
                    "award",
                    "Actual held advancement",
                    tuple(
                        (x["id"], x["rule"].replace("strain.void.endgame.", "Void Endgame "))
                        for x in data["awards"]
                    ),
                ),
                Field("account", "Record this actual rule acquisition", paragraph=True),
            ],
            buy,
        ).present(interaction)
        return
    if mission_id is None:
        if not data["missions"]:
            await reply(
                interaction, "Supply Drop is acquired. Use it during an actual active Mission."
            )
            return

        async def mission(current: discord.Interaction, value: str) -> None:
            await open_supply_drop(current, service, value)

        await Picker(
            interaction.user.id,
            "Supply Drop — actual Mission",
            tuple((x["id"], x["label"]) for x in data["missions"]),
            mission,
        ).show(interaction)
        return
    if data["used"]:
        await reply(interaction, "Supply Drop was already used for this Mission.")
        return
    if not data["targets"]:
        raise WorkflowError("No actual original Girl is available")

    async def choose(current: discord.Interaction, values: dict[str, Any]) -> None:
        target = next(x for x in data["targets"] if x["token"] == values["target"][0])
        await open_details(
            current,
            service,
            data,
            target,
            "repair" if values["kind"][0] == "repair" else "drop",
            values["account"],
        )

    await NativeForm(
        interaction.user.id,
        "Supply Drop — once per Mission",
        "Choose one real repair or custom temporary equipment delivery. An unfinished delivery "
        "does not consume this Mission use.",
        [
            Field(
                "kind",
                "Actual effect",
                (
                    ("repair", "Repair one actual damaged Asset"),
                    ("drop", "Deliver custom temporary Frame equipment"),
                ),
            ),
            Field(
                "target",
                "Actual original Girl",
                tuple((x["token"], x["label"]) for x in data["targets"]),
            ),
            Field("account", "Describe this actual use", paragraph=True),
        ],
        choose,
    ).present(interaction)


async def open_details(
    interaction: discord.Interaction,
    service: SupplyDropService,
    data: dict[str, Any],
    target: dict[str, Any],
    kind: Literal["repair", "drop"],
    account: str,
) -> None:
    if kind == "repair":
        if not target["damaged"]:
            raise WorkflowError("This actual Girl has no eligible damaged Asset")
        fields = [
            Field(
                "asset",
                "Actual damaged Asset",
                tuple((x["id"], x["label"]) for x in target["damaged"]),
            )
        ]
    else:
        if not target["deliverable"]:
            raise WorkflowError("Recover this actual current Frame and known delivery position")
        fields = [
            Field("name", "Custom temporary Frame Asset name"),
            Field("description", "Describe the actual equipment", paragraph=True),
        ]

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        result = await asyncio.to_thread(
            service.act,
            viewer_from_interaction(current),
            str(current.id),
            data["mission"],
            data["revision"],
            kind,
            ActorRef.model_validate(target["actor"]),
            account,
            asset=values["asset"][0] if kind == "repair" else None,
            name=values.get("name", ""),
            description=values.get("description", ""),
        )
        return "Actual Supply Drop use saved: " + str(result["phase"]) + "."

    await NativeForm(
        interaction.user.id,
        "Supply Drop — " + target["label"],
        "Delivery requires the original owner's actual receive/install choice. "
        "Temporary equipment expires at this Mission's end.",
        fields,
        submit,
    ).present(interaction)


async def open_delivery(
    interaction: discord.Interaction, service: SupplyDropService, identity: str
) -> None:
    data = await asyncio.to_thread(
        service.view_delivery, viewer_from_interaction(interaction), identity
    )
    if data["context_pending"]:

        async def context(current: discord.Interaction, values: dict[str, Any]) -> str:
            result = await asyncio.to_thread(
                service.review_expiry,
                viewer_from_interaction(current),
                str(current.id),
                identity,
                data["revision"],
                values["battle"][0] == "yes",
                values["account"],
            )
            return "Actual loss context recorded. " + (
                "Required Defeat is pending."
                if result["defeat_required"]
                else "This loss did not occur in battle."
            )

        await NativeForm(
            interaction.user.id,
            "Supply Drop expiry — actual Frame-loss context",
            "The actual temporary equipment expired, leaving no usable Frame Assets. "
            "Source facts show the Girl was piloting. Record whether the loss was in battle; "
            "a true battle loss requires the actual Defeat Play.",
            [
                Field(
                    "battle",
                    "Actual battle context at the loss",
                    (("yes", "Piloting in battle"), ("no", "Not in battle")),
                ),
                Field("account", "Record the actual factual evidence", paragraph=True),
            ],
            context,
        ).present(interaction)
        return
    if data["phase"] != "proposed":
        await reply(interaction, "Supply Drop: " + data["phase"] + " — " + data["name"])
        return
    fields = (
        [
            Field(
                "receive",
                "Your actual choice",
                (("yes", "Receive/install this actual effect"), ("no", "Decline this source")),
            )
        ]
        if data["receiver"]
        else [
            Field(
                "receive", "Original Handler control", (("no", "Cancel the undelivered proposal"),)
            )
        ]
    )
    if data["receiver"] and data["needs_replace"]:
        if not data["replacements"]:
            raise WorkflowError("Make legal Frame capacity before receiving this delivery")
        fields.append(
            Field(
                "replace",
                "Your actual non-Void capacity replacement",
                tuple((x["id"], x["label"]) for x in data["replacements"]),
            )
        )
    if data["receiver"] and data["modular"]:
        fields += [
            Field(
                "modular",
                "Your optional Modular Build repair choice",
                (("keep", "Repair the existing Asset"), ("replace", "Replace the repaired Asset")),
            ),
            Field("name", "Optional replacement name", required=False),
            Field(
                "description", "Optional replacement description", paragraph=True, required=False
            ),
        ]
    fields.append(Field("account", "Describe actual receipt or refusal", paragraph=True))

    async def receive(current: discord.Interaction, values: dict[str, Any]) -> str:
        modular = (
            Replacement(
                asset=data["asset"],
                name=values.get("name", ""),
                description=values.get("description", ""),
            )
            if values.get("modular") == ("replace",)
            else None
        )
        result = await asyncio.to_thread(
            service.receive,
            viewer_from_interaction(current),
            str(current.id),
            identity,
            data["revision"],
            values["receive"][0] == "yes",
            values["account"],
            replace=values["replace"][0] if "replace" in values else None,
            modular=modular,
        )
        return "Actual Supply Drop effect: " + str(result["phase"]) + "."

    await NativeForm(
        interaction.user.id, "Supply Drop — " + data["name"], data["description"], fields, receive
    ).present(interaction)
