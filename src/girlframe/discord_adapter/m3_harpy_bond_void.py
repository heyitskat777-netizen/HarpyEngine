"""Private original-owner Sin of Temptation choices and durable work readback."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.m3_sup import GROW, add_growth, open_growth
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine.m2 import ChoiceAnswer
from girlframe.services.m2_game import GameService
from girlframe.services.m3_harpy_bond_void import HarpyBondVoidService
from girlframe.services.onboarding import WorkflowError


async def _present(
    interaction: discord.Interaction,
    game: GameService,
    data: dict[str, Any],
    choice: dict[str, Any] | None,
) -> None:
    if data["phase"] == "complete":
        await reply(
            interaction,
            "Your original Bond's Void consequence is complete.\n"
            + (data.get("description") or "Your recorded choice is preserved."),
        )
        return
    if data["phase"] == "threshold":
        await reply(
            interaction,
            "Your alteration is saved. Complete its pending Void consequence "
            "in your requests inbox; the original Play and receipt stay preserved.",
        )
        return
    if data.get("blocked"):
        await reply(
            interaction,
            "This original consequence remains pending: "
            + (
                "the actual character needs its own resource support."
                if data["blocked"] == "PENDING_ACTUAL_RESOURCES"
                else "restore an actual uncorrupted Asset or an available Sup growth source."
            ),
        )
        return
    if data["phase"] != "rewrite":
        raise WorkflowError("Reopen this original source-owned Void consequence")
    fields = [
        Field(
            "asset",
            "Your actual Asset to alter",
            add_growth(
                tuple((x["id"], x["label"] + " · " + x["family"]) for x in data["assets"]), data
            ),
        )
    ]
    if data["storage"]:
        fields.append(
            Field(
                "storage",
                "Use your connected JANUS Void Storage?",
                (
                    ("no", "Alter this Asset permanently"),
                    ("yes", "Store this alteration in the connected Harpy"),
                ),
            )
        )
    if data.get("casualty_parts"):
        fields += [
            Field(
                "casualty_part",
                "Optional Wounded God: infected part to break",
                tuple((x["id"], x["name"]) for x in data["casualty_parts"]),
                minimum=0,
                required=False,
            ),
            Field(
                "casualty_site_account",
                "Actual infected site, if resisting",
                paragraph=True,
                required=False,
            ),
        ]
    fields.append(
        Field(
            "account",
            "Describe the actual Void alteration",
            paragraph=True,
            required=not bool(data.get("sup")),
        )
    )
    service = HarpyBondVoidService(game)

    async def save(
        current: discord.Interaction,
        account: str,
        asset: str | None,
        storage: bool,
        growth: dict[str, str],
        part: str | None,
        site: str,
    ) -> str:
        if choice is not None:
            options = ((asset,) if asset is not None else ()) + (("storage",) if storage else ())
            detail = dict(growth)
            if part:
                detail["casualty_part"] = part
            if site:
                detail["casualty_site_account"] = site
            await asyncio.to_thread(
                game.respond,
                viewer_from_interaction(current),
                str(current.id),
                choice["id"],
                choice["revision"],
                ChoiceAnswer(options=options, text=account, fields=detail),
            )
        else:
            await asyncio.to_thread(
                service.act,
                viewer_from_interaction(current),
                str(current.id),
                data["id"],
                data["revision"],
                account,
                asset,
                storage,
                growth,
                casualty_part=part,
                casualty_site_account=site,
            )
        return "Your actual Void choice is saved. Continue any pending consequence in your inbox."

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str | None:
        asset = values["asset"][0]
        storage = values.get("storage", ("no",))[0] == "yes"
        part = values["casualty_part"][0] if values.get("casualty_part") else None
        site = values.get("casualty_site_account", "")
        if asset == GROW:
            if storage or part or site.strip():
                raise WorkflowError("Choose Sup growth or existing-Asset Storage/resistance")

            async def grow(
                actual: discord.Interaction, detail: dict[str, str], account: str
            ) -> str:
                return await save(actual, account, None, False, detail, None, "")

            await open_growth(current, data, grow)
            return None
        return await save(current, values["account"], asset, storage, {}, part, site)

    await NativeForm(
        interaction.user.id,
        "Sin of Temptation — your actual Void choice",
        "Your Bond with the actual Harpy deepened to Intense or while Intense. "
        "Choose your own alteration. This does not repeat the original roll.",
        fields,
        submit,
    ).present(interaction)


async def open_choice(
    interaction: discord.Interaction, game: GameService, decision: dict[str, Any]
) -> None:
    await _present(interaction, game, decision["harpy_bond_void"], decision)


async def open_temptation(
    interaction: discord.Interaction, game: GameService, identity: str
) -> None:
    viewer = viewer_from_interaction(interaction)
    data = await asyncio.to_thread(HarpyBondVoidService(game).view, viewer, identity)
    choice = None
    if data["phase"] == "rewrite" and data["source_action"] is not None:
        rows = await asyncio.to_thread(game.choices, viewer)
        for row in rows:
            if row["kind"] != "harpy_bond_void" or row["action_id"] != data["source_action"]:
                continue
            candidate = await asyncio.to_thread(game.decision, viewer, row["id"])
            if candidate["body"].get("work_id") == identity:
                choice = candidate
                break
        if choice is None:
            await reply(
                interaction,
                "The original saved Play owns this consequence. "
                "Recover its pending response before altering it.",
            )
            return
    await _present(interaction, game, data, choice)
