"""Private entry for the two supported learned voluntary source Plays."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_learned_sex import lessons
from girlframe.services.onboarding import WorkflowError

RULES = ("girl.princess.sex-play", "girl.stim-blissed.sex-play")


async def open_learned_sex(
    interaction: discord.Interaction, game: GameService, identity: str | None = None
) -> None:
    viewer = viewer_from_interaction(interaction)

    def available() -> tuple[dict[str, str], ...]:
        with game.store.engine.connect() as connection:
            game.authorize(connection, viewer, game=False)
            state = load_state(connection, game.store.campaign_id)
            if str(viewer.user_id) not in state.sheets:
                return ()
            actor = current_ref(state, viewer.user_id)
            return tuple(
                row for rule in RULES for row in lessons(game, connection, state, actor, rule)
            )

    choices = await asyncio.to_thread(available)

    async def open_source(current: discord.Interaction, lesson: str) -> None:
        row = next((item for item in choices if item["id"] == lesson), None)
        if row is None:
            raise WorkflowError("Reopen your available lesson or its saved invitation.")
        if row["rule_id"] == RULES[0]:
            from girlframe.discord_adapter.m3_princess_sex import open_princess
            from girlframe.services.m3_princess_sex import SexService

            await open_princess(current, SexService(game), learned_source=lesson)
        elif row["rule_id"] == RULES[1]:
            from girlframe.discord_adapter.m3_stim_sex import open_stim
            from girlframe.services.m3_stim_sex import SexService as StimSexService

            await open_stim(current, StimSexService(game), learned_source=lesson)
        else:
            raise WorkflowError("This lesson is waiting for its Play controls.")

    if identity is not None:
        await open_source(interaction, identity)
        return
    if not choices:
        await reply(
            interaction,
            "No unused Princess or Stim lesson is available. "
            "Reopen an existing invitation or Play from your inbox.",
        )
        return

    async def choose(current: discord.Interaction, values: dict[str, Any]) -> None:
        await open_source(current, values["lesson"][0])

    form = NativeForm(
        interaction.user.id,
        "Learned Plays",
        "Choose one unused lesson. The other person answers the invitation first; "
        "your roll uses the lesson once.",
        [Field("lesson", "Your lesson", tuple((row["id"], row["label"]) for row in choices))],
        choose,
    )
    await reply(interaction, form.text(), form)
