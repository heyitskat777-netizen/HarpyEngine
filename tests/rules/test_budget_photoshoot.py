"""Actual low Budget result records source-owned public-perception Tags."""

import asyncio

from test_ledger import ADMIN
from test_ledger import ledger as ledger
from test_m2_game import state
from test_mission_ui import current
from test_strain_effect_service import pending

from girlframe.discord_adapter.m3_strain_effects import open_effect
from girlframe.services.inbox import InboxService


def test_actual_photoshoot_native_tags_for_each_original_girl(ledger):
    effects, game, _, _ = pending(ledger)
    request = next(x for x in state(game).strain.requests if x.track == "budget")
    effects.strain.roll(ADMIN, "photoshoot-budget-die", request.id, 1, state(game).revision)
    effects.strain.choose(ADMIN, "photoshoot-budget-choice", request.id, 2, state(game).revision, 1)
    identity = request.id + ":effect"
    before = state(game)
    original_tags = {uid: len(before.sheets[str(uid)].tags) for uid in before.order}
    assert (
        next(x for x in InboxService(ledger).items(ADMIN) if x.identity == identity).task
        == "m3_strain_effect"
    )

    async def native():
        interaction = current(1, 28100)
        await interaction.response.defer(ephemeral=True)
        await open_effect(interaction, effects, identity)
        form = interaction.edit_original_response.call_args.kwargs["view"]
        assert {x.key for x in form.fields} == {
            "account",
            *("tag:" + str(uid) for uid in before.order),
        }
        form.values = {
            "account": "The actual photoshoot concluded; the public responded to each Girl",
            **{"tag:" + str(uid): "Public impression " + str(uid) for uid in before.order},
        }
        await form.confirm.callback(current(1, 28101))
        assert form.completed

    asyncio.run(native())
    after = state(game)
    for uid in before.order:
        sheet = after.sheets[str(uid)]
        assert len(sheet.tags) == original_tags[uid] + 1
        tag = sheet.tags[-1]
        assert tag.label == "Public impression " + str(uid)
        assert tag.gm_setter_appointment and tag.gm_setter_event and tag.giver_actor is None
    assert after.handler_tags == before.handler_tags
    assert effects.get(ADMIN, identity)["state"] == "resolved"
