"""Owned factual possession proposals and actual Handler confirmation, without Asset stats."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_actors import owned_refs
from girlframe.engine.m3_role_punishments import view
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_items import ItemService
from girlframe.services.onboarding import WorkflowError


async def open_item_proposal(
    interaction: discord.Interaction, game: GameService, *, action: str | None = None
) -> None:
    viewer = viewer_from_interaction(interaction)

    def choices() -> list[dict[str, Any]]:
        with game.store.engine.connect() as c:
            game.authorize(c, viewer, game=False)
            state = load_state(c, game.store.campaign_id)
            bound = profiles(c, game.store.campaign_id)
            return [
                dict(
                    ref=x.model_dump(mode="json"),
                    token=x.token,
                    label=view(state, x, bound).label,
                    assets=[
                        dict(id=a.id, label=a.name)
                        for a in state.sheets[x.entity].assets
                        if a.family == "girl" and not a.concealed
                    ]
                    if x.kind == "pilot"
                    else [],
                )
                for x in owned_refs(state, viewer.user_id, bound)
                if x.kind in ("pilot", "npc", "handler")
            ]

    offers = await asyncio.to_thread(choices)
    refs = {x["token"]: x for x in offers}
    if not refs:
        raise WorkflowError("Introduce an actual controlled living holder first.")

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        result = await asyncio.to_thread(
            ItemService(game).propose,
            viewer_from_interaction(current),
            str(current.id),
            ActorRef.model_validate(refs[values["holder"][0]]["ref"]),
            values["name"],
            values["description"],
            weapon=values["weapon"][0] == "yes",
            action=action,
            asset_id=values["asset"][0] or None,
        )
        return "Existing-possession proposal saved for actual Handler confirmation: " + str(
            result["id"]
        )

    await NativeForm(
        viewer.user_id,
        "Prove an existing held object",
        "Record an object already established on this person. "
        "The Handler confirms the factual evidence. "
        "Confirm an existing carried object, never a body part, trait or mounted Frame component. "
        "This grants no new mechanical Asset slots or statistics.",
        [
            Field(
                "holder",
                "Actual controlled holder",
                tuple((k, x["label"]) for k, x in refs.items()),
            ),
            Field(
                "asset",
                "Bind only an actual carried Girl Asset, if any",
                (
                    ("", "Ordinary object without Asset statistics"),
                    *tuple((a["id"], a["label"]) for holder in offers for a in holder["assets"]),
                ),
            ),
            Field("name", "Existing object name"),
            Field("description", "Evidence of existing possession", paragraph=True),
            Field(
                "weapon",
                "Established as a usable weapon on hand?",
                (("no", "No"), ("yes", "Yes; Handler must confirm")),
            ),
        ],
        submit,
    ).present(interaction)


async def open_item_fact(
    interaction: discord.Interaction, service: ItemService, identity: str
) -> None:
    viewer = viewer_from_interaction(interaction)
    data = await asyncio.to_thread(service.get, viewer, identity)
    if data["state"] == "resolved" or not data["can_confirm"]:
        await reply(
            interaction,
            "Possession proposal "
            + data["state"]
            + ". The appointed Handler owns factual confirmation.",
        )
        return
    body = data["body"]

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        result = await asyncio.to_thread(
            service.confirm,
            viewer_from_interaction(current),
            str(current.id),
            identity,
            data["revision"],
            exists=values["exists"][0] == "yes",
            account=values["account"],
        )
        return (
            "Actual possession fact " + str(result["state"]) + ". No Asset statistics were created."
        )

    await NativeForm(
        viewer.user_id,
        "Confirm existing possession",
        "Object: "
        + body["name"]
        + ". Claimed existing possession: "
        + body["description"]
        + (
            ". Usable weapon on hand is also being asserted."
            if body["weapon"]
            else ". Ordinary object."
        ),
        [
            Field(
                "exists",
                "Does this established possession fact hold?",
                (("yes", "Confirm fact"), ("no", "Reject unsupported fact")),
            ),
            Field("account", "Actual evidence and factual ruling", paragraph=True),
        ],
        submit,
    ).present(interaction)
