"""Owned world-facilitator choices for Gorgon contests and confirmed Core weakness."""

import asyncio
from typing import Any
from uuid import NAMESPACE_URL, uuid5

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.ledger import clean
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.m3_punishments import Picker
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_gorgon_combat import Contest, Exposure
from girlframe.services.m3_gorgon import GorgonService
from girlframe.services.onboarding import WorkflowError


async def open_contest(interaction: discord.Interaction, service: GorgonService) -> None:
    viewer = viewer_from_interaction(interaction)
    data = await asyncio.to_thread(service.contests, viewer)
    actors = {x["token"]: x for x in data["attackers"]}
    if not actors:
        await reply(interaction, "No eligible co-located Gorgon Asset contest is available.")
        return

    async def attacker(current: discord.Interaction, token: str) -> None:
        first = actors[token]
        targets = {x["token"]: x for x in first["targets"]}

        async def defender(selected: discord.Interaction, target_token: str) -> None:
            second = targets[target_token]
            losing = {
                str(uuid5(NAMESPACE_URL, actor["token"] + ":" + asset["id"])): (side, asset)
                for side, actor in (("attacker", first), ("defender", second))
                for asset in actor["assets"]
                if not asset["damaged"]
            }

            async def submit(response: discord.Interaction, values: dict[str, Any]) -> str:
                side, asset = losing[values["losing_asset"][0]]
                if side == values["winner"][0]:
                    raise WorkflowError("Choose an Asset from the losing Gorgon.")
                result = await asyncio.to_thread(
                    service.contest,
                    viewer_from_interaction(response),
                    str(response.id),
                    data["game_revision"],
                    Contest(
                        attacker=ActorRef.model_validate(first["ref"]),
                        defender=ActorRef.model_validate(second["ref"]),
                        attacking_assets=tuple(values["attacking_assets"]),
                        defending_assets=tuple(values["defending_assets"]),
                        attacker_sha256=first["source_sha256"],
                        defender_sha256=second["source_sha256"],
                        winner=values["winner"][0],
                        losing_asset=asset["id"],
                        approach=values["approach"][0],
                        account=values["account"],
                        trigger_confirmed=True,
                    ),
                )
                return (
                    "The losing Asset was destroyed. Both Gorgons remain alive. Saved contest: "
                    + str(result["id"])
                )

            fields = [
                Field(
                    key,
                    label,
                    tuple((x["id"], x["name"]) for x in actor["assets"] if not x["damaged"]),
                    1,
                    min(25, sum(not x["damaged"] for x in actor["assets"])),
                )
                for key, label, actor in (
                    ("attacking_assets", "Attacking Assets", first),
                    ("defending_assets", "Defending Assets", second),
                )
            ]
            fields += [
                Field(
                    "winner",
                    "Your actual Handler ruling: winner",
                    (("attacker", "Attacking Gorgon"), ("defender", "Defending Gorgon")),
                ),
                Field(
                    "losing_asset",
                    "Losing pitted Asset to destroy",
                    tuple(
                        (key, side.title() + ": " + asset["name"])
                        for key, (side, asset) in losing.items()
                    ),
                ),
                Field(
                    "approach",
                    "How was the losing Asset overcome?",
                    (("direct", "Direct attack"), ("indirect", "An actual indirect approach")),
                ),
                Field("account", "Actual contest and why this result follows", paragraph=True),
                Field(
                    "confirm",
                    "Confirm the actual consequence",
                    (("yes", "Destroy that losing Asset"),),
                ),
            ]
            form = NativeForm(
                viewer.user_id,
                "Gorgon against Gorgon",
                clean(first["label"])
                + " attacks "
                + clean(second["label"])
                + ". Pit actual Assets "
                "and choose the winner. An intact Directed guard needs an actual "
                "indirect approach. "
                "Destroying an Asset does not expose or destroy the Core automatically.",
                fields,
                submit,
            )
            await reply(selected, form.text(), form)

        await Picker(
            viewer.user_id,
            "**Choose the defending Gorgon**",
            tuple((key, x["label"]) for key, x in targets.items()),
            defender,
        ).show(current)

    await Picker(
        viewer.user_id,
        "**Choose the attacking Gorgon**",
        tuple((key, x["label"]) for key, x in actors.items()),
        attacker,
    ).show(interaction)


async def open_exposure(interaction: discord.Interaction, service: GorgonService) -> None:
    viewer = viewer_from_interaction(interaction)
    data = await asyncio.to_thread(service.cores, viewer)
    actors = {x["token"]: x for x in data["gorgons"]}
    if not actors:
        await reply(
            interaction,
            "No living unexposed Gorgon has all its actual designated guards dealt with.",
        )
        return

    async def select(current: discord.Interaction, token: str) -> None:
        actor = actors[token]

        async def submit(response: discord.Interaction, values: dict[str, Any]) -> str:
            result = await asyncio.to_thread(
                service.expose,
                viewer_from_interaction(response),
                str(response.id),
                data["game_revision"],
                Exposure(
                    actor=ActorRef.model_validate(actor["ref"]),
                    source_sha256=actor["source_sha256"],
                    account=values["account"],
                    weakness_confirmed=True,
                ),
            )
            return "The actual Core is exposed. The Gorgon remains alive. Saved source: " + str(
                result["id"]
            )

        form = NativeForm(
            viewer.user_id,
            "Confirm actual Core weakness",
            clean(actor["label"]) + ". Its designated guarding Assets are damaged or destroyed. "
            "Also confirm this actual weakness in the Conversation: " + clean(actor["weakness"]),
            [
                Field("account", "What actually fulfilled this weakness?", paragraph=True),
                Field(
                    "confirm",
                    "Confirm the actual weakness is present",
                    (("yes", "Expose this Core; do not kill the Gorgon"),),
                ),
            ],
            submit,
        )
        await reply(current, form.text(), form)

    await Picker(
        viewer.user_id,
        "**Review an actual Gorgon Core**",
        tuple((key, x["label"]) for key, x in actors.items()),
        select,
    ).show(interaction)
