"""A Director rules context is its proved current Handler body, with the same actual Bonds."""

import asyncio
from uuid import uuid4

import pytest
from test_director_service import configure, ready
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Gateway, answer, state, tick
from test_mission_ui import current
from test_ooc_tag_markers import end_handler

from girlframe.delivery.m2_worker import GameWorker
from girlframe.discord_adapter.m2_ui import open_choice
from girlframe.engine.m2 import PlayInput, TagState
from girlframe.engine.m3_actor_bond_state import BondEdge
from girlframe.engine.m3_actor_bonds import bond_ref, current_ref
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_handler_state import Draft, HandlerPersona
from girlframe.services import m3_tag_markers


def configured(store):
    svc, _, _, game, _, _, work = ready(store)
    configure(svc, work)
    return game


def test_actual_director_presence_native_gm_tag_window_uses_context_hash_and_actual_bond(ledger):
    game = configured(ledger)
    with ledger.transaction() as c:
        canon = state(game)
        canon.bonds["1:2"] = 1
        canon.sheets["2"].tags.append(
            TagState(
                id="actual-context-observed-tag",
                label="Actual observed Tag",
                giver=3,
                observers=(1, 2, 3),
            )
        )
        game.event(c, 1, str(uuid4()), "synthetic.actual_tag_context", canon)
    before = game.dice.calls
    game.dice.faces = (3, 3)
    identity = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play="keep_your_head",
            heat=0,
            context="Actual Director's presence",
            trigger_confirmed=True,
        ),
    )["action_id"]
    tick(GameWorker(game), Gateway(), 3)
    request = next(x for x in game.choices(ADMIN) if x["kind"] == "tag_window")
    decision = game.decision(ADMIN, request["id"])
    with ledger.engine.connect() as c:
        marker = m3_tag_markers.current(game, c, state(game), game.action(c, identity), 1)[0]
    assert marker.actor.incarnation == state(game).director_contexts[0].id
    assert marker.actor != current_ref(state(game), 1) and marker.bonus == 2
    assert bond_ref(state(game), marker.actor) == current_ref(state(game), 1)

    async def mark():
        caller = current(1, 99901)
        await caller.response.defer(ephemeral=True)
        await open_choice(caller, game, decision["id"])
        form = caller.edit_original_response.call_args.kwargs["view"]
        form.values.update(
            options=("tag",),
            denied=("actual-context-observed-tag",),
            number=("1",),
            text="Actual current same-body Bond",
        )
        response = current(1, 99902)
        await form.confirm.callback(response)
        assert form.completed, response.edit_original_response.call_args

    asyncio.run(mark())
    for viewer in (PLAYER, OTHER):
        answer(game, viewer, "tag_window", options=("pass",))
    with ledger.engine.connect() as c:
        applied = game.action(c, identity)["data"]["tag_marker_applied"]
    assert applied["actor"] == marker.actor.model_dump(mode="json") and applied["amount"] == 2
    assert game.dice.calls == before + 1


def test_ended_context_never_normalizes_to_a_later_body_and_raw_alias_edges_fail_closed(ledger):
    game = configured(ledger)
    original = state(game)
    ref = ActorRef(kind="handler", entity="1", incarnation=original.director_contexts[0].id)
    other = current_ref(original, 2)
    duplicate = original.model_copy(deep=True)
    duplicate.actor_bonds.append(
        BondEdge(first=ref, second=other, depth=1, source_event="unreconciled-legacy-context-edge")
    )
    before = duplicate.model_dump_json()
    with pytest.raises(ValueError, match="duplicate authority"):
        bond_ref(duplicate, ref)
    assert duplicate.model_dump_json() == before
    end_handler(game)
    ended = state(game)
    ended.handler_persona = HandlerPersona(
        id="different-actual-body",
        owner=1,
        appointment="fresh-appointment",
        draft=Draft(name="New original"),
        source_event="fresh-body-source",
    )
    ended.director_contexts[0] = ended.director_contexts[0].model_copy(update={"active": True})
    # Invalid restoration must not revive its old authority.
    assert bond_ref(ended, ref) == ref
    assert bond_ref(ended, ref) != current_ref(ended, 1)


def test_actual_handler_helplessness_survives_rules_context_end_without_transferring_to_new_body(
    ledger,
):
    from girlframe.engine.m3_actor_bonds import clear_helpless, is_helpless, make_helpless

    game = configured(ledger)
    canon = state(game)
    body = current_ref(canon, 1)
    foe = current_ref(canon, 2)
    context = ActorRef(kind="handler", entity="1", incarnation=canon.director_contexts[0].id)
    changed = make_helpless(canon, context, foe, "actual-owned-last-asset")
    assert is_helpless(changed, body, foe)
    changed.director_contexts[0] = changed.director_contexts[0].model_copy(
        update={
            "body_actor": body,
            "active": False,
            "directors": (),
            "termination_reason": "director_death",
            "termination_event": "actual-director-ended",
        }
    )
    assert is_helpless(changed, body, foe)
    repeated = make_helpless(changed, body, foe, "actual-second-source")
    assert len(repeated.helpless_conditions) == 1
    assert repeated.helpless_conditions[0].subject == context
    with pytest.raises(ValueError, match="opposing people"):
        make_helpless(changed, context, body, "not-two-people")
    recovered = clear_helpless(changed, body, "actual-body-recovery", foe)
    assert not is_helpless(recovered, context, foe)
    with ledger.transaction() as c:
        game.event(c, 1, str(uuid4()), "synthetic.actual_helpless_body", changed)
    end_handler(game)
    ended = state(game)
    ended.handler_persona = HandlerPersona(
        id="new-original-body",
        owner=1,
        appointment="fresh-body-appointment",
        draft=Draft(name="Actual replacement"),
        source_event="actual-new-body-source",
    )
    assert not is_helpless(ended, current_ref(ended, 1), foe)
