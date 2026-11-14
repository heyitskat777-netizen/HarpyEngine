"""Actual nominated owned sources, invitations and real resource preparation."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine import m3_casualty as casualty
from girlframe.engine import m3_dose_up as dose
from girlframe.engine import m3_newgirl_sex as newgirl
from girlframe.engine import m3_oldgen_sex as oldgen
from girlframe.engine import m3_princess_sex as princess
from girlframe.engine import m3_stim_sex as stim
from girlframe.engine import m3_vatgrown_plays as vatgrown
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
            if data["processor_offered"]:
                options.append(("processor", "Prepare your actual nominated Processor Core"))
            if data["mockingbird_offered"]:
                options.append(("invite_mockingbird", "Declare an actual Mockingbird source"))
            if data["alpha_offered"]:
                options.append(("invite", "Propose an actual voluntary Alpha source"))
            if data["oldgen_offered"]:
                options.append(("invite_oldgen", "Propose an actual voluntary Oldgen source"))
            if data["newgirl_offered"]:
                options.append(("invite_newgirl", "Propose an actual voluntary Newgirl source"))
            if data["princess_offered"]:
                options.append(("invite_princess", "Propose an actual voluntary Princess source"))
            if data["stim_offered"]:
                options.append(("invite_stim", "Propose an actual voluntary Stim source"))
            if data["casualty_offered"]:
                options.append(("invite_casualty", "Propose an actual voluntary Casualty source"))
            if data["vatgrown_offered"]:
                options.append(("invite_vatgrown", "Propose an actual voluntary Vatgrown source"))
            if data["self_dose"]:
                options.append(("self_dose", "Select your actual own self-Dose recipe"))
            options += [("link:" + x["id"], x["label"]) for x in data["accepted"]]
        elif link["action"]:
            options.append(("resume", "Resume the actual prepared nominated Play"))
        else:
            options.append(("play", "Prepare the selected nominated Play with real resources"))
            if link["rule"] == princess.RULE:
                options.append(
                    ("withdraw_princess", "Withdraw this unprepared selection; Play stays owed")
                )
            if link["rule"] == stim.RULE:
                options.append(
                    ("withdraw_stim", "Withdraw this unprepared selection; Play stays owed")
                )
            if link["rule"] == "frame.ankou.processor-core":
                options.append(
                    ("withdraw_processor", "Withdraw this unprepared selection; Play stays owed")
                )
    if data["pause"].get("retry"):
        options.append(("retry", "Retry actual scene permission handling"))
    summary = (
        "The nominated performance remains owed until its real source outcomes finish. "
        "The actual counterpart confirms their own source through its controls or Requests. "
        "Invitations and selection perform no Play and infer no consent. "
        + f"Scene permissions: {data['pause']['state']}."
    )
    if not any(
        data[x]
        for x in (
            "alpha_offered",
            "oldgen_offered",
            "newgirl_offered",
            "vatgrown_offered",
            "stim_offered",
            "princess_offered",
            "casualty_offered",
            "mockingbird_offered",
            "processor_offered",
        )
    ):
        summary = (
            "The actual nominated self-Dose remains owed until its real cocktail outcomes finish. "
            "Selecting a recipe spends no Heat and creates no drug or Contact. "
            + f"Scene permissions: {data['pause']['state']}."
        )
    if data["processor_offered"]:
        summary = (
            "The nominated performance remains owed until its real source outcomes finish. "
            "Processor Core uses your actual purchased Frame rule, living minds, exemptions "
            "and real resources. Withdraw an unprepared selection to replace changed source facts; "
            "the original performance stays owed. "
            + f"Scene permissions: {data['pause']['state']}."
        )
    if data["completed"]:
        summary = "The actual nominated performance is complete. " + summary
    if data["invitations"]:
        summary += f" Awaiting {len(data['invitations'])} actual source response(s)."
    if data["cancelled"]:
        summary += " Prior unrolled cancellations remain saved; original source facts are retained."
    if data["pause"].get("error"):
        summary += " " + str(data["pause"]["error"])
    if not options:
        await reply(interaction, summary)
        return

    async def choose(current: discord.Interaction, values: dict[str, Any]) -> str | None:
        selected = values["operation"][0]
        if selected == "withdraw_princess":
            await asyncio.to_thread(
                service.withdraw_princess,
                viewer_from_interaction(current),
                str(current.id),
                link["id"],
                data["revision"],
            )
            await open_required(current, game, source_id)
        elif selected == "withdraw_stim":
            await asyncio.to_thread(
                service.withdraw_stim,
                viewer_from_interaction(current),
                str(current.id),
                link["id"],
                data["revision"],
            )
            await open_required(current, game, source_id)
        elif selected == "withdraw_processor":
            from girlframe.services.m3_required_processor import withdraw

            await asyncio.to_thread(
                withdraw,
                game,
                viewer_from_interaction(current),
                str(current.id),
                link["id"],
                data["revision"],
            )
            await open_required(current, game, source_id)
        elif selected == "processor":
            from girlframe.discord_adapter.m3_ankou import _operation
            from girlframe.services.m3_ankou import AnkouService

            controls = AnkouService(game)
            menu = await asyncio.to_thread(
                controls.menu, viewer_from_interaction(current), data["channel"]
            )
            await _operation(current, controls, menu, "processor", required_source=source_id)
        elif selected == "invite_mockingbird":
            from girlframe.discord_adapter.m3_mockingbird_plays import open_book

            await open_book(current, game, actor_ref=ActorRef.model_validate(data["actor"]))
        elif selected == "invite":
            from girlframe.discord_adapter.m3_alpha_sex import open_alpha
            from girlframe.services.m3_alpha_sex import SexService

            await open_alpha(current, SexService(game))
        elif selected == "invite_oldgen":
            from girlframe.discord_adapter.m3_oldgen_sex import open_oldgen_sex
            from girlframe.services.m3_oldgen_sex import OldgenSexService

            await open_oldgen_sex(current, OldgenSexService(game))
        elif selected == "invite_newgirl":
            from girlframe.discord_adapter.m3_newgirl_sex import open_newgirl_sex
            from girlframe.services.m3_newgirl_sex import NewgirlSexService

            await open_newgirl_sex(current, NewgirlSexService(game))
        elif selected == "invite_princess":
            from girlframe.discord_adapter.m3_princess_sex import open_princess
            from girlframe.services.m3_princess_sex import SexService as PrincessSexService

            await open_princess(current, PrincessSexService(game))
        elif selected == "invite_stim":
            from girlframe.discord_adapter.m3_stim_sex import open_stim
            from girlframe.services.m3_stim_sex import SexService as StimSexService

            await open_stim(current, StimSexService(game))
        elif selected == "invite_casualty":
            from girlframe.discord_adapter.m3_casualty import open_casualty
            from girlframe.services.m3_casualty import CasualtyService

            await open_casualty(current, CasualtyService(game))
        elif selected == "invite_vatgrown":
            from girlframe.discord_adapter.m3_vatgrown_plays import open_vatgrown_plays
            from girlframe.services.m3_vatgrown_plays import VatgrownPlaysService

            await open_vatgrown_plays(current, VatgrownPlaysService(game))
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
        elif selected == "play" and link["rule"] in (
            "girl.mockingbird.bad-at-being-a-person",
            "girl.mockingbird.sex-play",
        ):
            from girlframe.discord_adapter.m3_mockingbird_plays import open_request
            from girlframe.services.m3_mockingbird_plays import MockingbirdService

            await open_request(
                current, MockingbirdService(game), link["recipe"], continue_source=True
            )
        elif selected == "play":
            assert link is not None
            if link["rule"] == "frame.ankou.processor-core":
                from girlframe.discord_adapter.m3_ankou import _operation
                from girlframe.services.m3_ankou import AnkouService

                controls = AnkouService(game)
                menu = await asyncio.to_thread(
                    controls.menu, viewer_from_interaction(current), data["channel"]
                )
                await _operation(
                    current,
                    controls,
                    menu,
                    "processor",
                    required_source=source_id,
                    processor_recipe=link["recipe"],
                )
                return None
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
                play=casualty.PLAY
                if link["rule"] == casualty.SEX
                else princess.PLAY
                if link["rule"] == princess.RULE
                else stim.PLAY
                if link["rule"] == stim.RULE
                else vatgrown.PLAY
                if link["rule"] == vatgrown.SEX
                else newgirl.PLAY
                if link["rule"] == newgirl.RULE
                else (oldgen.PLAY if link["rule"] == oldgen.RULE else "alpha_sex"),
                source=link["recipe"],
                context="",
                delegated_target=None
                if link["rule"] in (newgirl.RULE, vatgrown.SEX)
                else ActorRef.model_validate(link["target"]),
                channel=data["channel"],
                title="Casualty Play"
                if link["rule"] == casualty.SEX
                else "Princess Play"
                if link["rule"] == princess.RULE
                else "Stim Play"
                if link["rule"] == stim.RULE
                else "Vatgrown Play"
                if link["rule"] == vatgrown.SEX
                else "Newgirl Play"
                if link["rule"] == newgirl.RULE
                else ("Oldgen Play" if link["rule"] == oldgen.RULE else "Alpha Play"),
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
