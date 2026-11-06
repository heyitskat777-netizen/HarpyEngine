"""Actual hosted media PR, owned performances and true GM result controls."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.ledger import clean
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.services.m3_handler_pr import HandlerPRService


async def open_pr(
    interaction: discord.Interaction, service: HandlerPRService, identity: str | None = None
) -> None:
    data = await asyncio.to_thread(service.menu, viewer_from_interaction(interaction), identity)
    if identity is None:
        if not data["host"]:
            await reply(
                interaction, "Use the actual PR event in your requests to record your own activity."
            )
            return

        async def plan(current: discord.Interaction, values: dict[str, Any]) -> str:
            people = tuple(
                ActorRef.model_validate(x["actor"])
                for x in data["people"]
                if x["token"] in values["people"]
            )
            await asyncio.to_thread(
                service.plan,
                viewer_from_interaction(current),
                str(current.id),
                data["revision"],
                values["objective"],
                values["context"],
                people,
            )
            return (
                "PR planned. Actual hosting, Cadre activity and public result are still required."
            )

        await NativeForm(
            interaction.user.id,
            "Plan actual Foundation media PR",
            "Plan a real fundraiser/photoshoot. Planning grants no award or public posting. "
            "Activity and result may span real campaign Sessions.",
            [
                Field("objective", "Concrete Foundation public objective", paragraph=True),
                Field("context", "Actual media event context", paragraph=True),
                Field(
                    "people",
                    "Original participating Girls",
                    tuple((x["token"], x["label"]) for x in data["people"]),
                    1,
                    len(data["people"]),
                ),
            ],
            plan,
        ).present(interaction)
        return
    if data["phase"] == "complete":
        text = (
            "Actual public result: "
            + ("successful" if data["successful"] else "unsuccessful")
            + ". "
            + clean(data["public_result"] or "")
        )
        if data["award"]:
            text += " One genuine ordinary award is saved."
        elif data["successful"]:
            text += " Success is preserved without an award; ordinary slot/mark rules apply."
        if not data["claimable"]:
            await reply(interaction, text)
            return

        async def claim(current: discord.Interaction, values: dict[str, Any]) -> str:
            await asyncio.to_thread(
                service.claim,
                viewer_from_interaction(current),
                str(current.id),
                identity,
                data["revision"],
            )
            return (
                "Successful source claimed once in this actual free Session; one advancement held."
            )

        await NativeForm(
            interaction.user.id,
            "Claim saved successful PR",
            text,
            [
                Field(
                    "claim",
                    "Actual ordinary source",
                    (("claim", "Claim this successful event in the current free Session"),),
                )
            ],
            claim,
        ).present(interaction)
        return
    if data["phase"] == "result":
        if not data["judge"]:
            await reply(
                interaction, "Performed PR awaits its authorized human GM's factual result."
            )
            return

        async def resolve(current: discord.Interaction, values: dict[str, Any]) -> str:
            result = await asyncio.to_thread(
                service.resolve,
                viewer_from_interaction(current),
                str(current.id),
                identity,
                data["revision"],
                values["result"][0] == "success",
                values["account"],
            )
            return "Actual public result saved." + (
                " One ordinary advancement held."
                if result["award"]
                else " No advancement granted; the actual outcome remains saved."
            )

        activities = "\n".join(clean(x["description"]) for x in data["activities"])
        await NativeForm(
            interaction.user.id,
            "Actual PR public result",
            clean(data["objective"])
            + "\nActual Cadre activities:\n"
            + activities
            + "\nJudge the performed result; no automatic success or invented quotas.",
            [
                Field(
                    "result",
                    "Actual public result",
                    (
                        ("success", "The actual Foundation PR objective succeeded"),
                        ("failure", "The actual PR objective did not succeed"),
                    ),
                ),
                Field("account", "Concrete public outcome and factual reasons", paragraph=True),
            ],
            resolve,
        ).present(interaction)
        return
    if data["host"]:
        options = (
            (("host", "Record my actually performed hosting"),)
            if not data["hosting"]
            else (("submit", "Close actual conduct for GM result"),)
        )

        async def host(current: discord.Interaction, values: dict[str, Any]) -> str:
            if values["operation"][0] == "host":
                await asyncio.to_thread(
                    service.activity,
                    viewer_from_interaction(current),
                    str(current.id),
                    identity,
                    data["revision"],
                    values["account"],
                    hosting=True,
                )
                return "Actual original Handler hosting recorded; no award from hosting alone."
            await asyncio.to_thread(
                service.submit_result,
                viewer_from_interaction(current),
                str(current.id),
                identity,
                data["revision"],
                values["account"],
            )
            return "Performed hosting and Cadre activity sent to factual GM result review."

        await NativeForm(
            interaction.user.id,
            "Actual original Handler PR hosting",
            clean(data["context"])
            + ". Record real conduct, not a proposal or attendance acknowledgment.",
            [
                Field("operation", "Actual performed source action", options),
                Field("account", "Actual hosting/conduct outcome", paragraph=True),
            ],
            host,
        ).present(interaction)
        return
    if data["participant"]:

        async def perform(current: discord.Interaction, values: dict[str, Any]) -> str:
            await asyncio.to_thread(
                service.activity,
                viewer_from_interaction(current),
                str(current.id),
                identity,
                data["revision"],
                values["account"],
                values.get("action") or None,
            )
            return "Actual original Girl activity recorded. Activity alone grants no award."

        await NativeForm(
            interaction.user.id,
            "Your actual public PR activity",
            clean(data["objective"])
            + ". Describe your Girl's actual public performance. Recording does not move your body "
            "or post outside this private control.",
            [
                Field(
                    "account",
                    "Actual performed photo/interview/appearance activity",
                    paragraph=True,
                ),
                Field("action", "Existing completed Play id, only if applicable", required=False),
            ],
            perform,
        ).present(interaction)
        return
    await reply(interaction, "This event's actual source is saved; no action is owned here.")
