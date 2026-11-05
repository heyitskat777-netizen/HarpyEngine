"""Owned second-hit choice and factual confirmations, with real existing Asset selectors."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine.m2 import ChoiceAnswer
from girlframe.services.m2_game import GameService
from girlframe.services.onboarding import WorkflowError


async def open_firepower(
    interaction: discord.Interaction, game: GameService, identity: str
) -> None:
    viewer = viewer_from_interaction(interaction)
    data = await asyncio.to_thread(game.decision, viewer, identity)
    detail = data["enforcer_firepower"]
    kind = data["kind"]
    selections: dict[str, tuple[str, str]] = {}
    if kind == "enforcer_firepower":
        labels = [("none", "Decline the optional extra hit")]
        for target in detail["targets"]:
            for asset in target["assets"]:
                token = str(len(selections))
                selections[token] = (target["token"], asset["id"])
                labels.append((token, target["label"] + " — " + asset["label"]))
        fields = [
            Field("selection", "Choose an actual additional enemy Asset", tuple(labels)),
            Field("account", "Describe extra hit, or state decline", paragraph=True),
        ]
    elif kind == "enforcer_firepower_context":
        fields = [
            Field(
                "inside",
                "Your actual body's current context",
                (("yes", "Inside a Frame"), ("no", "Outside a Frame")),
            ),
            Field("account", "Record actual body facts", paragraph=True),
        ]
    elif kind == "enforcer_firepower_confirm":
        fields = [
            Field(
                "confirm",
                "Actual enemy and reachable/relevant Asset?",
                (("yes", "Confirmed"), ("no", "Not a supported additional hit")),
            ),
            Field("account", "Record source facts and reason", paragraph=True),
        ]
    else:
        raise WorkflowError("Open your actual pending Overwhelming Firepower response.")

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        if kind == "enforcer_firepower":
            selected = values["selection"][0]
            if selected == "none":
                answer = ChoiceAnswer(flag=False, text=values["account"])
            elif selected in selections:
                target, asset = selections[selected]
                answer = ChoiceAnswer(
                    flag=True, fields=dict(target=target, asset=asset), text=values["account"]
                )
            else:
                raise WorkflowError("Reopen the actual current Asset choices.")
        else:
            answer = ChoiceAnswer(
                flag=values["inside" if kind.endswith("context") else "confirm"][0] == "yes",
                text=values["account"],
            )
        await asyncio.to_thread(
            game.respond,
            viewer_from_interaction(current),
            str(current.id),
            identity,
            data["revision"],
            answer,
        )
        return "Your actual second-hit response is saved. Required effects remain in this Assault."

    form = NativeForm(
        viewer.user_id,
        "Overwhelming Firepower",
        "Your optional extra hit keeps its original source, "
        "judge and actual effect. It grants no extra roll.",
        fields,
        submit,
    )
    await reply(interaction, form.text(), form)
