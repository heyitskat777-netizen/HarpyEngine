"""Explicit native dispatch to existing source-authenticated Sex consumers."""

import asyncio

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine import m3_bonded as rules
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_bonded import prove
from girlframe.services.onboarding import WorkflowError


async def open_delegated(
    interaction: discord.Interaction, game: GameService, source_id: str
) -> None:
    viewer = viewer_from_interaction(interaction)
    with game.store.engine.connect() as c:
        game.authorize(c, viewer, game=False)
        state = load_state(c, game.store.campaign_id)
        source = prove(game, c, state, source_id)
        if (
            source.actor.entity != str(viewer.user_id)
            or source.route != "delegated"
            or source.target is None
            or source.phase not in ("accepted", "bound", "complete")
        ):
            raise WorkflowError("Only the actual original Bonded opens this fixed borrowed source")
        link = next(
            (x for x in rules.records(state, rules.Delegation) if x.source == source_id), None
        )
        revision = state.revision
    rule = source.delegated_rule
    if rule == "girl.am.sex-play":
        from girlframe.discord_adapter.m3_am_sex import open_am_sex
        from girlframe.services.m3_am_sex import SexService as AM

        await open_am_sex(interaction, AM(game), bonded_source=source_id)
        return
    if rule == "girl.alpha.sex-play":
        from girlframe.discord_adapter.m3_alpha_sex import open_consent
        from girlframe.discord_adapter.m3_bonded import _play
        from girlframe.services.m3_alpha_sex import SexService as Alpha

        controls = Alpha(game)
        if link is None:
            result = await asyncio.to_thread(
                controls.invite,
                viewer,
                str(interaction.id),
                source.cast.channel,
                source.target,
                revision,
                source.account,
                bonded_source=source_id,
            )
            identity = result["id"]
        else:
            identity = link.session
        data = await asyncio.to_thread(controls.view, viewer, identity)
        if data["phase"] == "accepted":
            await _play(
                interaction,
                game,
                play="alpha_sex",
                source=identity,
                context=source.account,
                delegated_target=source.target,
                channel=source.cast.channel,
            )
        else:
            await open_consent(interaction, controls, identity)
        return
    if rule == "girl.princess.sex-play":
        from girlframe.discord_adapter.m3_princess_sex import open_princess
        from girlframe.services.m3_princess_sex import SexService as Princess

        controls_princess = Princess(game)
        if link is None:
            result = await asyncio.to_thread(
                controls_princess.invite,
                viewer,
                str(interaction.id),
                source.cast.channel,
                source.target,
                revision,
                source.account,
                bonded_source=source_id,
            )
            identity = result["id"]
        else:
            identity = link.session
        await open_princess(interaction, controls_princess, identity)
    elif rule == "girl.stim-blissed.sex-play":
        from girlframe.discord_adapter.m3_stim_sex import open_stim
        from girlframe.services.m3_stim_sex import SexService as Stim

        controls_stim = Stim(game)
        if link is None:
            result = await asyncio.to_thread(
                controls_stim.invite,
                viewer,
                str(interaction.id),
                source.cast.channel,
                source.target,
                revision,
                source.account,
                bonded_source=source_id,
            )
            identity = result["id"]
        else:
            identity = link.session
        await open_stim(interaction, controls_stim, identity)
    elif rule == "girl.oldgen.sex-play":
        from girlframe.discord_adapter.m3_oldgen_sex import open_oldgen_sex
        from girlframe.services.m3_oldgen_sex import OldgenSexService

        controls_oldgen = OldgenSexService(game)
        if link is None:
            result = await asyncio.to_thread(
                controls_oldgen.invite,
                viewer,
                str(interaction.id),
                source.cast.channel,
                source.target,
                revision,
                source.account,
                bonded_source=source_id,
            )
            identity = result["id"]
        else:
            identity = link.session
        await open_oldgen_sex(interaction, controls_oldgen, identity)
    elif rule == "girl.casualty.sex-play":
        from girlframe.discord_adapter.m3_casualty import open_casualty
        from girlframe.services.m3_casualty import CasualtyService

        controls_casualty = CasualtyService(game)
        if link is None:
            result = await asyncio.to_thread(
                controls_casualty.invite,
                viewer,
                str(interaction.id),
                source.cast.channel,
                source.target,
                revision,
                source.account,
                bonded_source=source_id,
            )
            identity = result["id"]
        else:
            identity = link.session
        await open_casualty(interaction, controls_casualty, identity)
    elif rule == "girl.vatgrown.sex-play":
        from girlframe.discord_adapter.m3_vatgrown_plays import open_vatgrown_plays
        from girlframe.services.m3_vatgrown_plays import VatgrownPlaysService

        controls_vatgrown = VatgrownPlaysService(game)
        if link is None:
            result = await asyncio.to_thread(
                controls_vatgrown.invite,
                viewer,
                str(interaction.id),
                source.cast.channel,
                source.target,
                revision,
                source.account,
                bonded_source=source_id,
            )
            identity = result["id"]
        else:
            identity = link.session
        await open_vatgrown_plays(interaction, controls_vatgrown, identity)
    elif rule == "girl.newgirl.sex-play":
        from girlframe.discord_adapter.m3_newgirl_sex import open_newgirl_sex
        from girlframe.services.m3_newgirl_sex import NewgirlSexService

        controls_newgirl = NewgirlSexService(game)
        if link is None:
            result = await asyncio.to_thread(
                controls_newgirl.invite,
                viewer,
                str(interaction.id),
                source.cast.channel,
                (source.target,),
                revision,
                source.account,
                bonded_source=source_id,
            )
            identity = result["id"]
        else:
            identity = link.session
        await open_newgirl_sex(interaction, controls_newgirl, identity)
    elif rule == "girl.mockingbird.sex-play":
        from girlframe.discord_adapter.m3_mockingbird import open_mockingbird
        from girlframe.services.m3_mockingbird_plays import MockingbirdService

        if link is None:
            result = await asyncio.to_thread(
                MockingbirdService(game).propose,
                viewer,
                str(interaction.id),
                source.cast.channel,
                source.actor,
                "mockingbird_sex",
                (source.target,),
                source.account,
                bonded_source=source_id,
            )
            identity = result["id"]
        else:
            identity = link.session
        await open_mockingbird(interaction, game, identity)
    else:
        await reply(
            interaction,
            "This actual Pair rule needs its genuine source adapter; "
            "the explicit unrolled7 alternative remains available. No resources were spent.",
        )
