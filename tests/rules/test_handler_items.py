"""A Handler's proved physical object follows one body, never a new persona."""

from uuid import uuid4

import pytest
from test_enforcement_initiative import cast_target, ready
from test_items import carried_asset, transfer
from test_ledger import OTHER, PLAYER
from test_ledger import ledger as ledger_fixture
from test_m2_game import state

from girlframe.engine import m3_handler_consequences as handlers
from girlframe.engine import m3_items as items
from girlframe.engine.m2 import PlayInput
from girlframe.engine.m3_actor_bonds import current_ref, is_helpless
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_director import enter, leave
from girlframe.engine.m3_handler_state import Draft, HandlerPersona
from girlframe.engine.m3_world import update
from girlframe.engine.m3_world_state import Npc
from girlframe.services.m3_items import available_items, prove_item

ledger = ledger_fixture


def held(store, tmp_path, monkeypatch, faces=(4, 5)):
    game, worker, gateway = ready(store, tmp_path, monkeypatch, faces)
    canon = state(game)
    body = handlers.active_handler(canon)
    owner = current_ref(canon, 3)
    asset = next(x for x in canon.sheets["3"].assets if x.family == "girl")
    carried_asset(game, OTHER, asset)
    item = transfer(game, owner, body, "asset:" + asset.id)
    return game, worker, gateway, body, item


def director(game):
    with game.store.transaction() as c:
        canon = state(game)
        canon.world = update(
            canon.world,
            npcs=(
                *canon.world.npcs,
                Npc(
                    id="director",
                    name="Actual Director",
                    detail="Synthetic actual Director presence",
                    controller=3,
                    cell=(0, 0),
                    jobs=("director",),
                ),
            ),
        )
        event = str(uuid4())
        canon = enter(canon, 1, "director", event, ("Afraid", "Defiant"), event)
        game.event(c, 1, str(uuid4()), "synthetic.actual_director_presence", canon, event_id=event)
    return ActorRef(kind="handler", entity="1", incarnation=canon.director_contexts[-1].id)


def test_actual_item_body_alias_and_loss_context_have_no_proxy_or_successor_slots(
    ledger, tmp_path, monkeypatch
):
    game, _, _, body, item = held(ledger, tmp_path, monkeypatch)
    before = state(game)
    opponent = current_ref(before, 2)
    with pytest.raises(ValueError, match="printed actual Handler replacement"):
        items.damage_mechanical_asset(
            before, body, item.asset_id, "normal-damage", opponent=opponent
        )
    ref = director(game)
    canon = state(game)
    assert items.mechanical_assets(canon, ref) == items.mechanical_assets(canon, body)
    with ledger.engine.connect() as c:
        assert prove_item(c, game, canon, item.id) == item
        assert available_items(c, game, canon, ref)[0]["id"] == item.id
    snapshot = canon.model_dump_json()
    with pytest.raises(ValueError, match="inside/outside Frame facts"):
        items.damage_mechanical_asset(
            canon, ref, item.asset_id, "unknown-context", opponent=opponent
        )
    assert canon.model_dump_json() == snapshot
    with pytest.raises(ValueError, match="distinct original people"):
        items.take(
            canon,
            ref,
            body,
            (),
            item.id,
            "same-body",
            "same-body-event",
            "No teleport",
            origin_event=item.state_event,
        )
    changed = items.damage_mechanical_asset(
        canon,
        ref,
        item.asset_id,
        "real-girl-damage",
        opponent=opponent,
        inside_frame=False,
    )
    assert items.mechanical_assets(changed, body)[0].damaged
    assert items.mechanical_assets(canon, ref)[0].damaged is False
    assert is_helpless(changed, body, opponent)
    assert is_helpless(changed, ref, opponent)
    assert not changed.handler_consequences and "1" not in changed.sheets
    ended = leave(changed, 3, ref.incarnation, "director", "real-departure")
    assert items.mechanical_assets(ended, body)[0].damaged
    assert is_helpless(ended, body, opponent)
    required, request = handlers.require(
        ended,
        body,
        trigger="asset_damage",
        source_action="actual-source",
        source_event="actual-fatal-trigger",
        opponent=opponent,
        appointment="actual-appointment",
    )
    dead = handlers.apply(required, request, "death", "Actual original dies", "actual-body-death")
    dead.handler_persona = HandlerPersona(
        id="new-body",
        owner=1,
        appointment="actual-appointment",
        source_event="actual-new-body",
        draft=Draft(name="Actual new person"),
    )
    fresh = handlers.active_handler(dead)
    assert not items.same_holder(dead, ref, fresh)
    assert not items.mechanical_assets(dead, fresh)
    assert not is_helpless(dead, fresh, opponent)
    assert dead.held_items[-1].holder == body and dead.held_items[-1].id == item.id


@pytest.mark.parametrize("inside", [False, True])
def test_last_actual_handler_girl_object_transfer_uses_factual_body_context(
    ledger, tmp_path, monkeypatch, inside
):
    game, _, _, body, item = held(ledger, tmp_path, monkeypatch)
    ref = director(game)
    recipient = ActorRef(kind="npc", entity="known-guard")
    changed = transfer(game, ref, recipient, item.id, inside_frame=inside)
    canon = state(game)
    assert changed.holder == recipient and not items.mechanical_assets(canon, body)
    assert canon.item_transfers[-1].last_girl_asset
    assert canon.item_transfers[-1].inside_frame is inside
    assert is_helpless(canon, body, recipient) is (not inside)
    assert not canon.handler_consequences and "1" not in canon.sheets


def test_actual_handler_girl_grasp_is_physical_but_new_roll_needs_source_judge(
    ledger, tmp_path, monkeypatch
):
    from girlframe.engine.m3_enforcer import grasp
    from girlframe.services.m3_actors import profiles
    from girlframe.services.m3_enforcement_initiative import preview
    from girlframe.services.onboarding import WorkflowError

    game, _, _, body, _ = held(ledger, tmp_path, monkeypatch)
    ref = director(game)
    cast_target(game, ref)
    canon = state(game)
    with ledger.engine.connect() as c:
        actual = grasp(
            canon,
            current_ref(canon, 2),
            ref,
            profiles(c, ledger.campaign_id),
            "actual-grasp-source",
            "actual-grasp",
        )
    assert is_helpless(actual, body, current_ref(actual, 2))
    assert not actual.handler_consequences and "1" not in actual.sheets
    assert preview(game, PLAYER, 900)["available"] is False
    with pytest.raises(WorkflowError, match="SOURCE_JUDGE_REQUIRED"):
        game.begin(
            PLAYER,
            str(uuid4()),
            900,
            canon.sheets["2"].revision,
            PlayInput(
                play="enforcement_initiative",
                target_actor=ref,
                heat=0,
                trigger_confirmed=True,
                context="Actual same Handler Girl body in reach",
            ),
        )
    assert state(game) == canon and game.dice.calls == 0
