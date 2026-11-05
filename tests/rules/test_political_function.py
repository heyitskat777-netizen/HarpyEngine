"""Actual political function: disclosed rights, owned attendance, Tag and ending."""

import asyncio

import pytest
import sqlalchemy as sa
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state
from test_mission_ui import current
from test_strain_effect_service import pending

from girlframe.database import tables as t
from girlframe.discord_adapter.m3_political_function import open_function
from girlframe.discord_adapter.m3_strain_effects import open_effect
from girlframe.engine.m3_political_function import get
from girlframe.engine.m3_world_state import Npc
from girlframe.services.inbox import InboxService
from girlframe.services.m3_political_function import FunctionService
from girlframe.services.m3_world import WorldService
from girlframe.services.onboarding import WorkflowError


def test_actual_function_source_notice_attendance_tag_and_completion(ledger):
    effects, game, _, _ = pending(ledger)
    WorldService(effects.strain.missions).npc(
        ADMIN,
        "actual-political-patron",
        state(game).revision,
        Npc(
            id="local-politician",
            name="Local political patron",
            jobs=("patron",),
            detail="An existing local political patron",
            controller=1,
            cell=(0, 0),
            revealed=True,
        ),
    )
    effects.strain.dice.face = 2
    request = next(x for x in state(game).strain.requests if x.track == "budget")
    effects.strain.roll(ADMIN, "political-budget-die", request.id, 1, state(game).revision)
    effects.strain.choose(ADMIN, "political-budget-column", request.id, 2, state(game).revision, 1)
    work = request.id + ":effect"
    identity = work + ":function"
    service = FunctionService(ledger)

    async def called():
        interaction = current(1, 28300)
        await interaction.response.defer(ephemeral=True)
        await open_effect(interaction, effects, work)
        form = interaction.edit_original_response.call_args.kwargs["view"]
        form.values = {
            "patron": ("local-politician",),
            "function": ("fundraiser",),
            "account": "The actual patron demands this fundraiser appearance",
        }
        await form.confirm.callback(current(1, 28301))
        assert form.completed

    asyncio.run(called())
    assert effects.get(ADMIN, work)["state"] == "resolved"
    assert get(state(game), identity).phase == "attendance"
    assert not state(game).handler_tags
    for viewer in (PLAYER, OTHER):
        assert (
            next(x for x in InboxService(ledger).items(viewer) if x.identity == identity).task
            == "m3_political_function"
        )

    async def actual_response(user, interaction_id, values):
        interaction = current(user, interaction_id)
        await interaction.response.defer(ephemeral=True)
        await open_function(interaction, service, identity)
        form = interaction.edit_original_response.call_args.kwargs["view"]
        assert "act out of line" in form.instructions
        form.values = values
        await form.confirm.callback(current(user, interaction_id + 1))
        assert form.completed

    for user in (2, 3):
        asyncio.run(
            actual_response(
                user,
                28310 + user * 2,
                {
                    "notice": ("attend",),
                    "account": "I know the disclosed Tag rights and actually attended",
                },
            )
        )
    assert get(state(game), identity).phase == "active"
    asyncio.run(
        actual_response(
            2,
            28320,
            {
                "tag": "Embarrassed",
                "account": "I actually act out of line at this function and give this Tag",
            },
        )
    )
    assert state(game).handler_tags[-1].giver_actor == get(state(game), identity).people[0]
    asyncio.run(
        actual_response(1, 28322, {"end": ("end",), "account": "The actual fundraiser has ended"})
    )
    assert get(state(game), identity).phase == "complete"
    with ledger.engine.connect() as c:
        rows = t.m3["m3_required_work"]
        row = (
            c.execute(
                sa.select(rows)
                .where(rows.c.campaign_id == ledger.campaign_id, rows.c.id == identity)
                .order_by(rows.c.revision.desc())
                .limit(1)
            )
            .mappings()
            .one()
        )
        assert row["state"] == "resolved"
    with pytest.raises(WorkflowError, match="STALE_FUNCTION"):
        service.act(
            PLAYER,
            "expired-function-right",
            identity,
            state(game).revision,
            "tag",
            "After the function",
            "Late",
        )
