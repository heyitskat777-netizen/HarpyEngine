"""Real Girl source controls and distinct actual AM no-roll performance accounts."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.ledger import clean
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.m3_memory_pages import MemoryForm, MemoryHistory
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine import m3_changeling_sex as rules
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.services.m3_changeling_sex import ChangelingSexService


async def open_changeling_sex(
    interaction: discord.Interaction, service: ChangelingSexService, identity: str
) -> None:
    shown = await asyncio.to_thread(service.view, viewer_from_interaction(interaction), identity)
    if shown["source"]:
        await _source(interaction, service, shown)
        return
    if not shown["can_start"]:

        async def access(current: discord.Interaction) -> None:
            await asyncio.to_thread(service.view, viewer_from_interaction(current), identity)

        text = "Actual psychic initiation: " + (
            shown["outcome"] or "waiting for its actual source human"
        )
        history = MemoryHistory(interaction.user.id, clean(text), access)
        await reply(interaction, history.text(), history)
        return
    fields = [Field("account", "Your genuine Girl-specific source proposal", paragraph=True)]
    if shown["book"] == "BONDED":
        fields.extend(
            [
                Field(
                    "route",
                    "Your actual Bonded source route",
                    (
                        ("pair", "Actual Pair"),
                        ("seven", "Actual non-Pair unrolled 7"),
                        ("delegated", "Actual non-Pair use Pair's owned Sex rule"),
                    ),
                ),
                Field(
                    "delegated_rule",
                    "Actual Pair rule ID only if choosing delegation",
                    required=False,
                ),
            ]
        )

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        await asyncio.to_thread(
            service.start,
            viewer_from_interaction(current),
            str(current.id),
            shown["revision"],
            shown["use"],
            int(current.channel_id or 0),
            values["account"],
            route=values.get("route", ("pair",))[0],
            delegated_rule=values.get("delegated_rule") or None,
        )
        return (
            "Your genuine specialized source is saved. Reopen it for its original human responses."
        )

    form = NativeForm(
        interaction.user.id,
        "Actual remote Sex source",
        "Your real Girl rule retains its original choices and costs. "
        "Each later voluntary response belongs to its actual human.",
        fields,
        submit,
    )
    await reply(interaction, form.text(), form)


async def _source(
    interaction: discord.Interaction, service: ChangelingSexService, shown: dict[str, Any]
) -> None:
    source = shown["source"]
    identity, rule = source["id"], source["rule"]
    if rule == rules.RULES["OLDGEN"]:
        from girlframe.discord_adapter.m3_oldgen_sex import open_oldgen_sex
        from girlframe.services.m3_oldgen_sex import OldgenSexService

        await open_oldgen_sex(interaction, OldgenSexService(service.game), identity)
    elif rule == rules.RULES["ALPHA"]:
        from girlframe.discord_adapter.m3_alpha_sex import open_alpha, open_consent
        from girlframe.services.m3_alpha_sex import SexService

        actual = SexService(service.game)
        if source["phase"] == "invited":
            await open_consent(interaction, actual, identity)
        else:
            await open_alpha(interaction, actual)
    elif rule == rules.RULES["PRINCESS"]:
        from girlframe.discord_adapter.m3_princess_sex import open_princess
        from girlframe.services.m3_princess_sex import SexService as Princess

        await open_princess(interaction, Princess(service.game), identity)
    elif rule == rules.RULES["STIM-BLISSED"]:
        from girlframe.discord_adapter.m3_stim_sex import open_stim
        from girlframe.services.m3_stim_sex import SexService as Stim

        await open_stim(interaction, Stim(service.game), identity)
    elif rule == rules.RULES["NEWGIRL"]:
        from girlframe.discord_adapter.m3_newgirl_sex import open_newgirl_sex
        from girlframe.services.m3_newgirl_sex import NewgirlSexService

        await open_newgirl_sex(interaction, NewgirlSexService(service.game), identity)
    elif rule == rules.RULES["VATGROWN"]:
        from girlframe.discord_adapter.m3_vatgrown_plays import open_vatgrown_plays
        from girlframe.services.m3_vatgrown_plays import VatgrownPlaysService

        await open_vatgrown_plays(interaction, VatgrownPlaysService(service.game), identity)
    elif rule == rules.RULES["CASUALTY"]:
        from girlframe.discord_adapter.m3_casualty import open_casualty
        from girlframe.services.m3_casualty import CasualtyService

        await open_casualty(interaction, CasualtyService(service.game), identity)
    elif rule == rules.RULES["MOCKINGBIRD"]:
        from girlframe.discord_adapter.m3_mockingbird_plays import open_request
        from girlframe.services.m3_mockingbird_plays import MockingbirdService

        await open_request(interaction, MockingbirdService(service.game), identity)
    elif rule == rules.RULES["BONDED"]:
        from girlframe.discord_adapter.m3_bonded import open_bonded
        from girlframe.services.m3_bonded import BondedService

        await open_bonded(interaction, BondedService(service.game), identity)
    else:
        await _am(interaction, service, identity)


async def _am(
    interaction: discord.Interaction, service: ChangelingSexService, identity: str
) -> None:
    data = await asyncio.to_thread(service.view_am, viewer_from_interaction(interaction), identity)
    source = data["body"]
    lines = ["Actual AM source: " + source["phase"], clean(source["account"])]
    lines.extend(
        ("Current same-Brain person: " if value.get("performed_by") else "Actual source role: ")
        + clean(value["account"])
        for value in data["performances"]
    )
    for gift in data["unrolled_gender"]:
        if gift["state"] == "given":
            lines.append("Mandatory Animal Tag given: " + clean(gift["tag_label"]))
        elif gift["pending"]:
            lines.append("Your mandatory Animal Tag is still required.")
        else:
            lines.append("Waiting for the original Animal's mandatory Tag.")
    fields: list[Field] = []
    if data["can_answer"]:
        fields = [
            Field(
                "accepted", "Your actual source response", (("yes", "Accept"), ("no", "Decline"))
            ),
            Field("account", "Your actual voluntary source answer", paragraph=True),
        ]
    elif data["perform"]:
        fields = [
            Field(
                "person",
                "Your actual current performed role",
                tuple(
                    (ActorRef.model_validate(value).token, "Actual " + value["kind"])
                    for value in data["perform"]
                ),
            ),
            Field("account", "Your actual performed-scene account", paragraph=True),
        ]
    elif any(value["pending"] for value in data["unrolled_gender"]):
        from girlframe.discord_adapter.p1_unrolled_sex import open_tasks

        await open_tasks(interaction, service.game, identity, source_kind="changeling_am")
        return

    async def access(current: discord.Interaction) -> None:
        await asyncio.to_thread(service.view_am, viewer_from_interaction(current), identity)

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        viewer = viewer_from_interaction(current)
        if data["can_answer"]:
            await asyncio.to_thread(
                service.am_respond,
                viewer,
                str(current.id),
                data["revision"],
                identity,
                values["accepted"] == ("yes",),
                values["account"],
            )
        else:
            actor = next(
                ActorRef.model_validate(value)
                for value in data["perform"]
                if ActorRef.model_validate(value).token == values["person"][0]
            )
            await asyncio.to_thread(
                service.am_perform,
                viewer,
                str(current.id),
                data["revision"],
                identity,
                actor,
                values["account"],
            )
        return (
            "Your actual original role's source account is saved; no dice or extra AM roll added."
        )

    if fields:
        form = MemoryForm(
            interaction.user.id,
            "Actual no-extra-roll AM source",
            "\n\n".join(lines),
            fields,
            submit,
            authorize=access,
        )
        await reply(interaction, form.text(), form)
    else:
        history = MemoryHistory(interaction.user.id, "\n\n".join(lines), access)
        await reply(interaction, history.text(), history)
