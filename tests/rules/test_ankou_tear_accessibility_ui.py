"""Physical tear eligibility is shared with writes and reflected in native controls."""

import asyncio
from types import SimpleNamespace

from test_ankou_feedback import last_source, ready
from test_ledger import PLAYER
from test_ledger import ledger as ledger
from test_mission_ui import current

from girlframe.discord_adapter.m3_ankou_feedback import open_choice
from girlframe.services.m3_ankou_feedback import _frame_accessible


def test_feedback_tear_selector_hides_inaccessible_frame_without_hiding_bond_assets(
    ledger, tmp_path, monkeypatch
):
    _, actual_game, worker, gateway, _, _ = ready(ledger, tmp_path, monkeypatch)
    last_source(actual_game, worker, gateway)
    choice = next(x for x in actual_game.choices(PLAYER) if x["kind"] == "ankou_feedback_choice")
    data = actual_game.decision(PLAYER, choice["id"])
    projected = data["ankou_feedback"]["assets"]
    assert projected and all(isinstance(x["tear_accessible"], bool) for x in projected)
    assert all(x["tear_accessible"] for x in projected if x["family"] == "girl")

    view = SimpleNamespace(cell=(0, 0), frame_cell=(1, 0), frame_instance="original")
    assert not _frame_accessible(view, "original")
    view.cell = (1, 0)
    assert _frame_accessible(view, "original")
    assert not _frame_accessible(view, "another")
    view.cell = None
    assert not _frame_accessible(view, "original")
    assets = [
        dict(
            id="remote-frame",
            name="Remote Frame",
            family="frame",
            void=False,
            tear_accessible=_frame_accessible(view, "original"),
            tear_supported=True,
            bond_replaceable=False,
        ),
        dict(
            id="body",
            name="Own body Asset",
            family="girl",
            void=False,
            tear_accessible=True,
            tear_supported=True,
            bond_replaceable=True,
        ),
        dict(
            id="void",
            name="Void",
            family="girl",
            void=True,
            tear_accessible=True,
            tear_supported=True,
            bond_replaceable=False,
        ),
    ]
    # Retain the canonical decision shape, including purpose and request text.
    data = {**data, "ankou_feedback": {**data["ankou_feedback"], "people": [], "assets": assets}}
    game = SimpleNamespace(decision=lambda viewer, identity: data)

    async def show():
        interaction = current(2, 98001)
        await interaction.response.defer(ephemeral=True)
        await open_choice(interaction, game, "actual-choice")
        form = interaction.edit_original_response.call_args.kwargs["view"]
        tear = next(x for x in form.fields if x.key == "asset")
        replacement = next(x for x in form.fields if x.key == "replace")
        assert tear.options == (("body", "Own body Asset"),)
        assert replacement.options == (("body", "Own body Asset"),)
        assert not form.completed

    asyncio.run(show())
