"""A GM survives a fictional Handler death without inheriting its body, Bonds or Status."""

import asyncio
from uuid import uuid4

import pytest
from test_beneath_service import ready
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import answer, state, tick
from test_mission_ui import current
from test_void_keep import pending

from girlframe.discord_adapter.m2_ui import open_choice
from girlframe.engine import m3_handler_consequences as endings
from girlframe.engine.m2 import PlayInput, TagState
from girlframe.engine.m3_actor_bonds import current_ref, depth
from girlframe.services.m3_medical import MedicalService


def end_handler(game):
    before = state(game)
    actual = current_ref(before, before.handler)
    source, effect = str(uuid4()), str(uuid4())
    with game.store.transaction() as c:
        appointment = MedicalService(game.store)._handler(c)[1]
        requested, identity = endings.require(
            before,
            actual,
            trigger="asset_damage",
            source_action=None,
            source_event=source,
            appointment=appointment,
            opponent=None,
        )
        game.event(
            c, 1, str(uuid4()), "synthetic.actual_handler_damage", requested, event_id=source
        )
        changed = endings.apply(
            requested, identity, "death", "Actual original Handler dies", effect
        )
        game.event(c, 1, str(uuid4()), "synthetic.actual_handler_death", changed, event_id=effect)
    return actual


def tag_window(game, viewer):
    choice = next(x for x in game.choices(viewer) if x["kind"] == "tag_window")
    return game.decision(viewer, choice["id"])


def actual_tag(game):
    with game.store.transaction() as c:
        canon = state(game)
        canon.bonds["1:2"] = 2
        canon.sheets["2"].tags.append(
            TagState(
                id="actual-ooc-observed",
                label="Actual observed Tag",
                giver=3,
                observers=(1, 2, 3),
            )
        )
        game.event(c, 1, str(uuid4()), "synthetic.actual_tag", canon)


@pytest.mark.parametrize("operation", ["pass", "tag"])
def test_no_context_actual_handler_death_native_pass_and_one_point_mark_has_no_inherited_authority(
    ledger,
    operation,
):
    game, worker, gateway = ready(ledger, (4, 4))
    actual_tag(game)
    action = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        state(game).sheets["2"].revision,
        PlayInput(play="keep_your_head", heat=0, context="Actual danger", trigger_confirmed=True),
    )["action_id"]
    tick(worker, gateway, 3)
    old = end_handler(game)
    data = tag_window(game, ADMIN)
    assert data["own"] is None and data["tag_markers"][0]["label"].startswith("OOC facilitator")
    assert depth(state(game), old, current_ref(state(game), 2)) == 2

    async def run():
        caller = current(1, 97301)
        await caller.response.defer(ephemeral=True)
        await open_choice(caller, game, data["id"])
        form = caller.edit_original_response.call_args.kwargs["view"]
        assert not any(x.key == "fields.status" for x in form.fields)
        form.values.update(
            options=(operation,),
            denied=("actual-ooc-observed",) if operation == "tag" else (),
            number=("1",) if operation == "tag" else (),
            text="Actual relevance from the human GM" if operation == "tag" else "",
        )
        await form.confirm.callback(current(1, 97302))
        assert form.completed

    asyncio.run(run())
    for viewer in (PLAYER, OTHER):
        answer(game, viewer, "tag_window", options=("pass",))
    with ledger.engine.connect() as c:
        value = game.action(c, action)["data"]
    if operation == "tag":
        assert value["tag_marker_applied"]["actor"] is None
        assert value["tag_marker_applied"]["amount"] == 1
        assert value["modifiers"][-1]["amount"] == 1
    else:
        assert "tag_marker_applied" not in value
    assert game.dice.calls == 1


def test_void_keep_null_handler_body_still_exposes_pilot_and_ooc_native_tag_controls(ledger):
    game, worker, gateway, parent, work = pending(ledger)
    end_handler(game)
    game.dice.faces = (4, 4)
    child = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play="keep_your_head",
            source_work=work,
            parent=parent,
            heat=0,
            context="Actual post-death resistance",
            trigger_confirmed=True,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    with ledger.engine.connect() as c:
        meta = game.action(c, child)["data"]["void_keep"]
    assert meta["handler"] is None and meta["gm_controller"] == ADMIN.user_id
    for viewer in (PLAYER, OTHER, ADMIN):
        decision = tag_window(game, viewer)
        assert decision["tag_markers"]
        answer(game, viewer, "tag_window", options=("pass",))
    answer(game, PLAYER, "actor_keep", options=("in_control", "tough"), denied=("sexy",))
    answer(game, ADMIN, "handler_keep", flag=True, text="Actual human GM's result ruling")
    assert game.inspect(PLAYER, child)["state"] == "complete"
    assert game.inspect(PLAYER, parent)["state"] == "complete" and game.dice.calls == 2
