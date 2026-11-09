"""Actual nominated owned sources, invitations and real resource preparation."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine import m3_dose_up as dose
from girlframe.engine import m3_oldgen_sex as oldgen
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.services.m2_game import GameService
from girlframe.services.m3_required_plays import RequiredPlayService


async def open_required(
    interaction: discord.Interaction, game: GameService, source_id: str
) -> None:
    service = RequiredPlayService(game)
    data = await asyncio.to_thread(service.menu, viewer_from_interaction(interaction), source_id)
    link = data["link"]
    options: list[tuple[str, str]] = []
    if not data["completed"]:
        if link is None:
            if data["alpha_offered"]:
                options.append(("invite", "Propose an actual voluntary Alpha source"))
            if data["oldgen_offered"]:
                options.append(("invite_oldgen", "Propose an actual voluntary Oldgen source"))
            if data["self_dose"]:
                options.append(("self_dose", "Select your actual own self-Dose recipe"))
            options += [("link:" + x["id"], x["label"]) for x in data["accepted"]]
        elif link["action"]:
            options.append(("resume", "Resume the actual prepared nominated Play"))
        else:
            options.append(("play", "Prepare the selected nominated Play with real resources"))
    if data["pause"].get("retry"):
        options.append(("retry", "Retry actual scene permission handling"))
    summary = (
        "The nominated performance remains owed until its real source outcomes finish. "
        "The actual counterpart confirms their own source through its controls or Requests. "
        "Invitations and selection perform no Play and infer no consent. "
        + f"Scene permissions: {data['pause']['state']}."
    )
    if not data["alpha_offered"] and not data["oldgen_offered"]:
        summary = (
            "The actual nominated self-Dose remains owed until its real cocktail outcomes finish. "
            "Selecting a recipe spends no Heat and creates no drug or Contact. "
            + f"Scene permissions: {data['pause']['state']}."
        )
    if data["completed"]:
        summary = "The actual nominated performance is complete. " + summary
    if data["invitations"]:
        summary += f" Awaiting {len(data['invitations'])} actual source response(s)."
    if data["cancelled"]:
        summary += (
            " Prior unrolled cancellations remain saved; original source consent is retained."
        )
    if data["pause"].get("error"):
        summary += " " + str(data["pause"]["error"])
    if not options:
        await reply(interaction, summary)
        return

    async def choose(current: discord.Interaction, values: dict[str, Any]) -> str | None:
        selected = values["operation"][0]
        if selected == "invite":
            from girlframe.discord_adapter.m3_alpha_sex import open_alpha
            from girlframe.services.m3_alpha_sex import SexService

            await open_alpha(current, SexService(game))
        elif selected == "invite_oldgen":
            from girlframe.discord_adapter.m3_oldgen_sex import open_oldgen_sex
            from girlframe.services.m3_oldgen_sex import OldgenSexService

            await open_oldgen_sex(current, OldgenSexService(game))
        elif selected == "self_dose":
            await asyncio.to_thread(
                service.link_self_dose,
                viewer_from_interaction(current),
                str(current.id),
                source_id,
                data["revision"],
            )
            await open_required(current, game, source_id)
        elif selected.startswith("link:"):
            await asyncio.to_thread(
                service.link,
                viewer_from_interaction(current),
                str(current.id),
                source_id,
                selected.removeprefix("link:"),
                data["revision"],
            )
            await open_required(current, game, source_id)
        elif selected == "play":
            assert link is not None
            if link["rule"] == dose.RULE:
                from girlframe.discord_adapter.m3_dose_up import open_dose_up
                from girlframe.services.m3_dose_up import DoseUpService

                await open_dose_up(
                    current, DoseUpService(game.store, game), required_link=link["id"]
                )
                return None
            from girlframe.discord_adapter.m3_bonded import _play

            await _play(
                current,
                game,
                play=oldgen.PLAY if link["rule"] == oldgen.RULE else "alpha_sex",
                source=link["recipe"],
                context="",
                delegated_target=ActorRef.model_validate(link["target"]),
                channel=data["channel"],
                title="Oldgen Play" if link["rule"] == oldgen.RULE else "Alpha Play",
            )
        elif selected == "resume":
            from girlframe.discord_adapter.m2_ui import open_pending

            await open_pending(current, game)
        else:
            from girlframe.services.p1_source_pause import retry

            await asyncio.to_thread(
                retry, game, viewer_from_interaction(current), str(current.id), source_id
            )
            await open_required(current, game, source_id)
        return None

    form = NativeForm(
        interaction.user.id,
        "Nominated own-source performance",
        summary,
        [Field("operation", "Your actual source controls", tuple(options))],
        choose,
    )
    await reply(interaction, form.text(), form)
