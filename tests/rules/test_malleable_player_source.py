"""Affected-human source facts qualify only later genuine Tags, never inferred consent."""

import asyncio
from uuid import uuid4

import pytest
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state
from test_malleable import ordinary_tag, prepared
from test_mission_ui import current as base_interaction

from girlframe.discord_adapter.m3_malleable import open_malleable
from girlframe.engine import m3_malleable as rules
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.services.m3_malleable import prove_alteration, prove_birth
from girlframe.services.onboarding import WorkflowError


def current(user=2, identity=500):
    value = base_interaction(user, identity)
    # The genuine gameplay fixture binds channel 900, unlike the generic UI mock.
    value.channel_id = 900
    return value


def test_own_actual_alteration_future_tag_and_force_after_ending(ledger, tmp_path, monkeypatch):
    game, worker, gateway, dosing, controls = prepared(ledger, tmp_path, monkeypatch)
    actor = current_ref(state(game), 3)
    earlier = ordinary_tag(game, worker, gateway)
    assert not any(x.id == earlier for x in rules.records(state(game), rules.Birth))
    original = state(game)
    with pytest.raises(WorkflowError):
        controls.record_player_alteration(
            PLAYER,
            str(uuid4()),
            900,
            actor,
            original.revision,
            "Cannot attest another human's condition",
        )
    assert state(game) == original

    async def attest(account):
        opened = current(3, int(uuid4().int % 10**15))
        await opened.response.defer(ephemeral=True)
        await open_malleable(opened, controls)
        menu = opened.edit_original_response.call_args.kwargs["view"]
        menu.values["action"] = ("own:alteration",)
        selected = current(3, int(uuid4().int % 10**15))
        await menu.confirm.callback(selected)
        form = selected.edit_original_response.call_args.kwargs["view"]
        form.values["account"] = account
        sent = current(3, int(uuid4().int % 10**15))
        await form.confirm.callback(sent)
        assert form.completed

    asyncio.run(
        attest(
            "PRIVATE_ACTUAL_CONDITION My character is currently intoxicated "
            "by the established scene drink"
        )
    )
    fact = rules.records(state(game), rules.Alteration)[-1]
    assert fact.subject == actor and fact.controller == OTHER.user_id
    with ledger.engine.connect() as c:
        assert prove_alteration(game, c, state(game), fact.id) == fact
    assert not any(x.id == earlier for x in rules.records(state(game), rules.Birth))
    with pytest.raises(WorkflowError):
        controls.record_player_alteration(
            OTHER,
            str(uuid4()),
            900,
            actor,
            state(game).revision,
            "Cannot duplicate this ongoing condition",
        )
    later = ordinary_tag(game, worker, gateway)
    born = next(x for x in rules.records(state(game), rules.Birth) if x.id == later)
    assert born.altered_kind == "pilot" and born.altered_id == fact.id
    assert born.recipient == actor
    with ledger.engine.connect() as c:
        assert prove_birth(game, c, state(game), later) == born
    with pytest.raises(WorkflowError):
        controls.record_player_alteration(
            PLAYER,
            str(uuid4()),
            900,
            actor,
            state(game).revision,
            "Cannot end her state",
            ending=fact.id,
        )
    asyncio.run(
        attest("PRIVATE_ACTUAL_END My character's previously recorded intoxication has ended")
    )
    assert len(rules.records(state(game), rules.AlterationEnd)) == 1
    after = ordinary_tag(game, worker, gateway)
    assert not any(x.id == after for x in rules.records(state(game), rules.Birth))
    # Printed 'at any time': ending physiology cannot erase genuine birth authority.
    selected = controls.view(PLAYER, later)["replacements"][0]["id"]
    before = state(game)
    calls = game.dice.calls
    with pytest.raises(WorkflowError):
        controls.force(OTHER, str(uuid4()), later, selected, before.revision)
    with pytest.raises(WorkflowError):
        controls.view(ADMIN, later)

    async def force():
        opened = current(2, 880001)
        await opened.response.defer(ephemeral=True)
        await open_malleable(opened, controls, later)
        form = opened.edit_original_response.call_args.kwargs["view"]
        form.values["replacement"] = (selected,)
        await form.confirm.callback(current(2, 880002))
        assert form.completed

    asyncio.run(force())
    final = state(game)
    assert game.dice.calls == calls
    assert not any(x.id == later for x in final.sheets["3"].tags)
    assert any(x.id == earlier for x in final.sheets["3"].tags)
    assert any(x.id == after for x in final.sheets["3"].tags)
    assert len(final.sheets["3"].identities) == len(before.sheets["3"].identities)
    assert next(
        x for x in final.sheets["3"].identities if x.name == "PRIVATE_AUTHORED_ORDINARY_TAG"
    ).slot == next(x.slot for x in before.sheets["3"].identities if x.id == selected)
    with pytest.raises((WorkflowError, ValueError)):
        controls.force(PLAYER, str(uuid4()), later, selected, final.revision)
    assert "PRIVATE_ACTUAL_CONDITION" not in str(gateway.messages)
