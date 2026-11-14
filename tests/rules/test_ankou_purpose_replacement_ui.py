"""Owned purpose UI shares authoritative ordinary-slot eligibility."""

import asyncio

from test_ankou_feedback import choose, last_source, ready
from test_ledger import OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import answer, state
from test_mission_ui import current

from girlframe.discord_adapter.m3_ankou_feedback import open_choice
from girlframe.engine.m2 import IdentityState
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.services.m3_ankou_feedback import _purpose_replaceable


def test_actual_purpose_uses_free_slot_and_filters_locked_replacement_contract(
    ledger, tmp_path, monkeypatch
):
    _, game, worker, gateway, _, _ = ready(ledger, tmp_path, monkeypatch)
    # Spend actual Disposable Psyche Heat to remove the last marked Identity,
    # opening an ordinary slot through the canonical committed transition.
    _, source = last_source(game, worker, gateway, extra=3)
    sheet_before = state(game).sheets["2"]
    assert not any(x.id == source.identity.id for x in sheet_before.identities)
    assert (
        len([x for x in sheet_before.identities if not x.protected or x.paired or x.am_limiter]) < 4
    )
    choose(game, "purpose", current_ref(state(game), 3))
    answer(game, OTHER, "ankou_feedback_purpose", flag=True, text="My independently given purpose")
    choice = next(x for x in game.choices(PLAYER) if x["kind"] == "ankou_feedback_identity")
    projected = game.decision(PLAYER, choice["id"])["ankou_feedback"]["identities"]
    assert projected and not any(x["purpose_replaceable"] for x in projected)

    async def place():
        opened = current(2, 98701)
        await opened.response.defer(ephemeral=True)
        await open_choice(opened, game, choice["id"])
        form = opened.edit_original_response.call_args.kwargs["view"]
        assert next(x for x in form.fields if x.key == "replace").options == ()
        response = current(2, 98702)
        await form.confirm.callback(response)
        assert form.completed, response.edit_original_response.call_args_list

    asyncio.run(place())
    assert any(
        x.name == "My independently given purpose" for x in state(game).sheets["2"].identities
    )

    # Bounded eligibility contract, not fabricated canonical lock/transition history.
    sheet = state(game).sheets["2"].model_copy(deep=True)
    eligible = IdentityState(id="ordinary", name="Ordinary")
    sheet.identities = [
        eligible,
        *(IdentityState(id=f"slot-{i}", name=f"Slot {i}") for i in range(3)),
    ]
    assert _purpose_replaceable(sheet, eligible)
    for update in (
        {"protected": True},
        {"paired": True},
        {"am_limiter": "source"},
        {"obsession_sources": ("source",)},
    ):
        assert not _purpose_replaceable(sheet, eligible.model_copy(update=update))
    sheet.sedation_locked = (eligible.id,)
    assert not _purpose_replaceable(sheet, eligible)
