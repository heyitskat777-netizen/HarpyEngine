"""Actual grafted Clone survives a counterpart's distinct native Identity erasure."""

import asyncio
from uuid import uuid4

import pytest
from test_changeling import define, ready, roll
from test_enforcer_requisitions import approved
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state, tick
from test_mission_ui import current

from girlframe.discord_adapter.m3_changeling import open_changeling
from girlframe.engine import m3_changeling as rules
from girlframe.engine import m3_clone_am as clone
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.services.m3_changeling import prove_fingers
from girlframe.services.m3_changeling_identity import identity_options
from girlframe.services.m3_clone_am import CloneService, prove_copy
from girlframe.services.onboarding import WorkflowError


def test_native_fingers_counter_erases_native_identity_with_actual_grafted_clone(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, controls = ready(ledger, tmp_path, monkeypatch)
    approved(
        ledger,
        game,
        tmp_path,
        monkeypatch,
        extra=(rules.BLANK, rules.STRINGS, rules.FINGERS, *rules.REQUISITIONS, clone.RULE),
    )
    actor, counterpart = current_ref(state(game), 2), current_ref(state(game), 3)
    # Real completed Blank Slate mid result provides this actual deepened-Bond String
    # before buying a copy. No all-Identity outcome is opened with a copy present.
    action = roll(game, worker, gateway, source=define(game, controls))
    assert game.inspect(PLAYER, action)["state"] == "complete"
    tick(worker, gateway, 5)
    node = next(
        x
        for x in rules.records(state(game), rules.String)
        if x.origin == "deepen" and x.subject.actor == counterpart
    )
    copies = CloneService(game)
    menu = copies.menu(PLAYER)
    before_permissions = state(game).sheets["2"].permissions
    key = str(uuid4())
    purchased = copies.buy(
        PLAYER,
        key,
        menu["revision"],
        actor,
        menu["frame"],
        "Actual paid Autocrat Clone AM graft into my original Changeling",
        "THE PRINCE",
    )
    assert purchased["cost"] == 3
    assert state(game).sheets["2"].permissions == before_permissions - 3
    born = clone.copies(state(game))[0]
    assert born.identity.name == "Perfect Copy" and born.original == actor
    with ledger.engine.connect() as c:
        prove_copy(game, c, state(game), born.ref)
        # Blank Slate now includes the actual accessible copy resource.
        for clause in ("blank_low", "blank_all"):
            assert born.identity.id in dict(
                identity_options(game, c, state(game), actor, chooser=counterpart, clause=clause)
            )
        protected = state(game).model_copy(deep=True)
        selected = protected.sheets["2"].identities[0]
        selected.protected = True
        assert selected.id not in dict(
            identity_options(
                game, c, protected, actor, chooser=counterpart, clause="fingers_counter"
            )
        )
    used = controls.fingers(
        PLAYER,
        str(uuid4()),
        state(game).revision,
        900,
        node.id,
        "question",
        "I consume the actual String for this source-owned question",
        question="What are you worried about?",
    )["id"]
    use = rules.get(state(game), used)
    controls.answer(
        OTHER,
        str(uuid4()),
        state(game).revision,
        use.question,
        "My actual answer, before my independent reciprocal choice",
    )
    view = controls.view(OTHER, used)
    assert view["counter"]
    legal = dict(view["identities"])
    assert legal and born.identity.id not in legal
    selected_id = next(iter(legal))
    snapshot = state(game).model_dump_json()
    with pytest.raises(WorkflowError):
        controls.counter(
            OTHER, str(uuid4()), state(game).revision, used, "erase", identity_id=born.identity.id
        )
    with pytest.raises(WorkflowError):
        controls.counter(
            ADMIN, str(uuid4()), state(game).revision, used, "erase", identity_id=selected_id
        )
    assert state(game).model_dump_json() == snapshot
    before = state(game)
    copy_json = clone.current(before, born.ref).model_dump_json()

    async def native_counter():
        interaction = current(3, 98701)
        interaction.channel_id = 900
        await interaction.response.defer(ephemeral=True)
        await open_changeling(interaction, controls, used)
        form = interaction.edit_original_response.call_args.kwargs["view"]
        assert any(
            key == selected_id
            for field in form.fields
            if field.key == "identity"
            for key, _ in field.options
        )
        form.values.update(kind=("erase",), identity=(selected_id,))
        submitted = current(3, 98702)
        await form.confirm.callback(submitted)
        assert form.completed

    asyncio.run(native_counter())
    after = state(game)
    assert {x.id for x in after.sheets["2"].identities} == {
        x.id for x in before.sheets["2"].identities if x.id != selected_id
    }
    assert clone.current(after, born.ref).model_dump_json() == copy_json
    assert clone.additional_identities(after, 2) == (born.identity,)
    assert after.sheets["2"].heat == before.sheets["2"].heat
    assert after.sheets["2"].permissions == before.sheets["2"].permissions
    assert after.requisitions == before.requisitions
    finished = rules.get(after, used)
    assert finished.completed_event and finished.counter_erase == selected_id
    assert rules.record(after, rules.String, node.id).spent_by == used
    with ledger.engine.connect() as c:
        prove_copy(game, c, after, born.ref)
        assert prove_fingers(game, c, after, used) == finished
    assert (
        game.dice.calls == 1
    )  # Original completed Blank Slate only; reciprocal choice is diceless.
