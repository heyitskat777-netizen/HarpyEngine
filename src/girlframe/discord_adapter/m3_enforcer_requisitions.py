"""Private owned Enforcer acquisition and finite post-roll Master's Dog decisions."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine.m2 import ChoiceAnswer
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_enforcer_requisitions import Kind
from girlframe.services.m2_game import GameService
from girlframe.services.m3_enforcer_requisitions import EnforcerRequisitionService
from girlframe.services.onboarding import WorkflowError


async def open_acquisition(
    interaction: discord.Interaction, service: EnforcerRequisitionService, kind: Kind
) -> None:
    viewer = viewer_from_interaction(interaction)
    data = await asyncio.to_thread(service.acquisition_view, viewer, kind)
    if not data["rules"]:
        await reply(
            interaction, "No additional reviewed Enforcer Requisition is available for this Frame."
        )
        return

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        result = await asyncio.to_thread(
            service.buy_rule,
            viewer_from_interaction(current),
            str(current.id),
            ActorRef.model_validate(data["actor"]),
            data["source_sha256"],
            kind,
            values["rule"][0],
            values["account"],
        )
        return "Your actual acquired rule is saved. Receipt: " + str(result["id"])

    form = NativeForm(
        viewer.user_id,
        "Acquire Enforcer Requisition",
        "Choose an available rule and confirm its actual payment.",
        [
            Field("rule", "Choose your rule", tuple((x["id"], x["label"]) for x in data["rules"])),
            Field("account", "Describe actual acquisition", paragraph=True),
            Field(
                "payment",
                "Confirm payment",
                (("yes", "Pay " + str(data["price"]) + " Permissions"),),
            ),
        ],
        submit,
    )
    await reply(interaction, form.text(), form)


async def open_master(interaction: discord.Interaction, game: GameService, identity: str) -> None:
    viewer = viewer_from_interaction(interaction)
    data = await asyncio.to_thread(game.decision, viewer, identity)
    if data["kind"] != "enforcer_master_dog":
        raise WorkflowError("Open your actual pending Master's Dog choice.")

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        await asyncio.to_thread(
            game.respond,
            viewer_from_interaction(current),
            str(current.id),
            identity,
            data["revision"],
            ChoiceAnswer(number=int(values["amount"][0])),
        )
        return "Your post-roll choice is saved; final results and any later choices follow."

    form = NativeForm(
        viewer.user_id,
        "Master's Dog",
        "Your Intense Bond permits one optional adjustment. "
        "This settles before final result effects and does not roll new dice.",
        [
            Field("amount", "Choose once", (("2", "Add +2"), ("-2", "Apply -2"), ("0", "Decline"))),
        ],
        submit,
    )
    await reply(interaction, form.text(), form)
