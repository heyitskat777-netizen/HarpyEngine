"""Actual physical item custody and immutable origin, not descriptive Asset creation."""

from uuid import uuid4

import pytest
from test_enforcement_initiative import ready, start
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger_fixture
from test_m2_game import answer, pass_tags, state, tick

from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.services.m3_items import (
    ItemService,
    available_items,
    prove_item,
    take_in_transaction,
)
from girlframe.services.onboarding import WorkflowError

ledger = ledger_fixture


def carried_asset(game, viewer, asset):
    service = ItemService(game)
    request = service.propose(
        viewer,
        str(uuid4()),
        current_ref(state(game), viewer.user_id),
        asset.name,
        "Actual existing detachable carried apparatus; "
        "never a body part, trait, or Frame installation",
        asset_id=asset.id,
    )
    service.confirm(
        ADMIN,
        str(uuid4()),
        request["id"],
        1,
        exists=True,
        account="Actual holder's established carried equipment is factually confirmed",
    )


def transfer(game, source, target, selection, **kwargs):
    with game.store.transaction() as c:
        event = str(uuid4())
        changed = take_in_transaction(
            c,
            game,
            state(game),
            source=source,
            recipient=target,
            selection=selection,
            action=str(uuid4()),
            event=event,
            account="Actual source-owned transfer",
            **kwargs,
        )
        game.event(c, 1, str(uuid4()), "synthetic.actual_transfer", changed, event_id=event)
        return changed.held_items[-1]


def test_actual_asset_to_npc_then_original_recovers_same_object_without_new_slots(
    ledger, tmp_path, monkeypatch
):
    game, _, _ = ready(ledger, tmp_path, monkeypatch)
    original = state(game)
    owner = current_ref(original, 3)
    npc = ActorRef(kind="npc", entity="known-guard")
    asset = next(x for x in original.sheets["3"].assets if x.family == "girl")
    carried_asset(game, OTHER, asset)
    item = transfer(game, owner, npc, "asset:" + asset.id)
    assert asset.id not in {x.id for x in state(game).sheets["3"].assets}
    assert item.holder == npc and item.asset_owner == npc
    with ledger.engine.connect() as c:
        assert prove_item(c, game, state(game), item.id) == item
        actual = available_items(c, game, state(game), npc)
    assert actual[0]["mechanical"]
    returned = transfer(game, npc, owner, item.id)
    assert returned.id == item.id and returned.asset_id == asset.id
    assert next(x for x in state(game).sheets["3"].assets if x.id == asset.id).name == asset.name


def test_original_holder_proposes_gm_confirms_nonmechanical_item_and_real_weapon_fact(
    ledger, tmp_path, monkeypatch
):
    game, _, _ = ready(ledger, tmp_path, monkeypatch)
    service = ItemService(game)
    holder = current_ref(state(game), 3)
    request = service.propose(
        OTHER,
        str(uuid4()),
        holder,
        "Access knife",
        "Existing blade actually on her person",
        weapon=True,
    )
    with pytest.raises(WorkflowError):
        service.confirm(OTHER, str(uuid4()), request["id"], 1, exists=True, account="Self invented")
    service.confirm(
        ADMIN,
        str(uuid4()),
        request["id"],
        1,
        exists=True,
        account="Actual established carried weapon confirmed",
    )
    item = state(game).held_items[-1]
    assert item.asset_json is None and not state(game).item_transfers
    with ledger.engine.connect() as c:
        assert available_items(c, game, state(game), holder, weapons_only=True)[-1]["id"] == item.id
    transfer(game, holder, current_ref(state(game), 2), item.id)
    assert len(state(game).sheets["2"].assets) == len(state(game).sheets["3"].assets)


def test_real_low_item_choice_transfers_then_recipient_cap_choice_and_escape_response(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway = ready(ledger, tmp_path, monkeypatch, (1, 1))
    before = state(game)
    asset = next(x for x in before.sheets["2"].assets if x.family == "girl")
    carried_asset(game, PLAYER, asset)
    identity = start(game)
    tick(worker, gateway, 3)
    pass_tags(game)
    receipt = game.inspect(PLAYER, identity)["receipt"]
    answer(game, PLAYER, "enforcer_select", options=("item", "escape"))
    answer(
        game,
        OTHER,
        "enforcer_item",
        fields={"item": "asset:" + asset.id},
        text="Target takes actual object from Enforcer",
    )
    assert asset.id in {x.id for x in state(game).sheets["2"].assets}
    answer(game, OTHER, "enforcer_receive")
    assert asset.id not in {x.id for x in state(game).sheets["2"].assets}
    transferred = state(game)
    transfer_record = transferred.item_transfers[-1]
    source, recipient = current_ref(before, 2), current_ref(before, 3)
    assert transfer_record.source == source and transfer_record.recipient == recipient
    assert transfer_record.action == identity
    assert transfer_record.source_kind == "enforcement_initiative"
    assert transfer_record.removed_asset == asset.id
    received = next(
        x for x in transferred.sheets["3"].assets if x.id == transfer_record.received_asset
    )
    assert (received.name, received.family, received.damaged, received.void) == (
        asset.name,
        asset.family,
        asset.damaged,
        asset.void,
    )
    item = next(x for x in transferred.held_items if x.id == transfer_record.item)
    assert item.holder == recipient and item.asset_owner == recipient
    assert item.asset_id == received.id and item.source_owner == source
    assert item.state_event == transfer_record.event
    with ledger.engine.connect() as c:
        assert prove_item(c, game, transferred, item.id) == item
    assert game.inspect(PLAYER, identity)["state"] != "complete"
    assert [x["kind"] for x in game.choices(OTHER)] == ["enforcer_escape"]
    assert not game.choices(PLAYER)
    answer(
        game,
        OTHER,
        "enforcer_escape",
        text="I slip my glove and escape this attempted grip; same map cell",
    )
    completed = state(game)
    assert completed.placements == before.placements
    assert completed.item_transfers == transferred.item_transfers
    assert completed.held_items == transferred.held_items
    escape = next(
        x
        for x in completed.facts
        if x.get("kind") == "enforcer_low_escape" and x.get("action") == identity
    )
    assert escape["actor"] == recipient.model_dump_json()
    assert escape["holder"] == source.model_dump_json()
    assert game.inspect(PLAYER, identity)["receipt"] == receipt
    assert game.inspect(PLAYER, identity)["state"] == "complete" and game.dice.calls == 1


def test_take_last_nonvoid_asset_opens_actual_source_void_and_printed_mockingbird_exception(
    ledger, tmp_path, monkeypatch
):
    from girlframe.engine import m3_physical as physical
    from girlframe.engine.m3_actors import resolve
    from girlframe.engine.m3_physical_state import InitialPlacement
    from girlframe.services.m3_actors import profiles

    game, worker, gateway = ready(ledger, tmp_path, monkeypatch, (1, 1))
    with ledger.transaction() as c:
        canon = state(game)
        holder = current_ref(canon, 2)
        sheet = canon.sheets["2"]
        girl = [x for x in sheet.assets if x.family == "girl"]
        assert len(girl) >= 2
        keep = girl[:2]
        keep[0] = keep[0].model_copy(update={"void": False})
        keep[1] = keep[1].model_copy(update={"void": True})
        sheet.assets = [x for x in sheet.assets if x.family != "girl"] + keep
        actual = resolve(
            canon, holder, profiles(c, ledger.campaign_id), require_current_profile=False
        )
        canon = physical.initial(
            canon,
            profiles(c, ledger.campaign_id),
            InitialPlacement(
                actor=holder,
                frame_instance=actual.frame_instance,
                girl_cell=(0, 0),
                frame_cell=(0, 0),
                mode="outside_frame",
                account="Actual outside original body",
                facts_confirmed=True,
            ),
            "actual-item-target-vessel",
            "actual-item-placement-proposal",
            "actual-item-handler-review",
        )
        game.event(c, 1, str(uuid4()), "synthetic.actual_void_prerequisite", canon)
    carried_asset(game, PLAYER, keep[0])
    identity = start(game)
    tick(worker, gateway, 3)
    pass_tags(game)
    answer(game, PLAYER, "enforcer_select", options=("item", "escape"))
    answer(
        game,
        OTHER,
        "enforcer_item",
        fields={"item": "asset:" + keep[0].id},
        text="Actual final nonvoid Asset taken",
    )
    answer(game, OTHER, "enforcer_receive")
    assert state(game).void_thresholds[-1].stage == "prevented"
    assert game.choices(OTHER)[0]["kind"] == "enforcer_escape"
    answer(game, OTHER, "enforcer_escape", text="I slip free; no map coordinate change")
    assert game.inspect(PLAYER, identity)["state"] == "complete" and game.dice.calls == 1


def test_actual_item_removal_mockingbird_threshold_uses_real_nested_keep_before_remaining_response(
    ledger, tmp_path, monkeypatch
):
    from test_void_keep import keep as actual_keep

    from girlframe.engine import m3_physical as physical
    from girlframe.engine.m2 import PlayInput
    from girlframe.engine.m3_actors import resolve
    from girlframe.engine.m3_physical_state import InitialPlacement
    from girlframe.services.m3_actors import profiles
    from girlframe.services.m3_void import VoidService

    game, worker, gateway = ready(ledger, tmp_path, monkeypatch, (1, 1))
    with ledger.transaction() as c:
        canon = state(game)
        actor = current_ref(canon, 2)
        sheet = canon.sheets["2"]
        girl = [x for x in sheet.assets if x.family == "girl"][:2]
        girl[0] = girl[0].model_copy(update={"void": False})
        girl[1] = girl[1].model_copy(update={"void": True})
        frames = [x.model_copy(update={"void": True}) for x in sheet.assets if x.family == "frame"]
        sheet.assets = frames + girl
        view = resolve(canon, actor, profiles(c, ledger.campaign_id), require_current_profile=False)
        canon = physical.initial(
            canon,
            profiles(c, ledger.campaign_id),
            InitialPlacement(
                actor=actor,
                frame_instance=view.frame_instance,
                girl_cell=(0, 0),
                frame_cell=(0, 0),
                mode="piloting",
                account="Actual original linked Frame occupancy",
                facts_confirmed=True,
            ),
            "actual-item-linked-vessel",
            "actual-item-linked-proposal",
            "actual-item-linked-confirm",
        )
        game.event(
            c,
            1,
            str(uuid4()),
            "synthetic.prior_corrupt_frame_with_new_girl_threshold_pending",
            canon,
        )
    carried_asset(game, PLAYER, girl[0])
    identity = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play="enforcement_initiative",
            target_actor=current_ref(state(game), 3),
            heat=0,
            piloting=True,
            trigger_confirmed=True,
            context="Actual Frame grasp attempt before losing carried object",
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    answer(game, PLAYER, "enforcer_select", options=("item", "escape"))
    answer(
        game,
        OTHER,
        "enforcer_item",
        fields={"item": "asset:" + girl[0].id},
        text="I take the actual object from the Enforcer",
    )
    answer(game, OTHER, "enforcer_receive")
    work = next(x for x in game.choices(PLAYER) if x["kind"] == "enforcer_void_threshold")
    detail = game.decision(PLAYER, work["id"])["enforcement"]
    assert VoidService(ledger).get(PLAYER, detail["work_id"])["stage"] == "resist_pending"
    child = actual_keep(game, worker, gateway, identity, detail["work_id"])
    assert game.inspect(PLAYER, child)["state"] == "complete" and game.dice.calls == 2
    assert game.inspect(PLAYER, identity)["state"] != "complete"
    answer(
        game, OTHER, "enforcer_escape", text="I actually slip free; no new map position is inferred"
    )
    assert game.inspect(PLAYER, identity)["state"] == "complete"


def test_earned_item_response_failure_rolls_back_and_replay_never_duplicates(
    ledger, tmp_path, monkeypatch
):
    from girlframe.engine.m2 import ChoiceAnswer

    game, worker, gateway = ready(ledger, tmp_path, monkeypatch, (1, 1))
    asset = next(x for x in state(game).sheets["2"].assets if x.family == "girl")
    carried_asset(game, PLAYER, asset)
    identity = start(game)
    tick(worker, gateway, 3)
    pass_tags(game)
    answer(game, PLAYER, "enforcer_select", options=("item", "escape"))
    answer(
        game,
        OTHER,
        "enforcer_item",
        fields={"item": "asset:" + asset.id},
        text="PRIVATE_ACTUAL_ITEM_TAKING",
    )
    row = next(x for x in game.choices(OTHER) if x["kind"] == "enforcer_receive")
    old = state(game).model_dump_json()
    event = game.event

    def fail(*args, **kwargs):
        if len(args) > 3 and args[3] == "m3.choice_resolved":
            raise RuntimeError("Synthetic failure after pure transfer before committed source")
        return event(*args, **kwargs)

    monkeypatch.setattr(game, "event", fail)
    key = str(uuid4())
    with pytest.raises(RuntimeError):
        game.respond(OTHER, key, row["id"], row["revision"], ChoiceAnswer())
    assert state(game).model_dump_json() == old
    assert any(x["id"] == row["id"] and x["state"] == "pending" for x in game.choices(OTHER))
    monkeypatch.setattr(game, "event", event)
    result = game.respond(OTHER, key, row["id"], row["revision"], ChoiceAnswer())
    assert game.respond(OTHER, key, row["id"], row["revision"], ChoiceAnswer()) == result
    assert len(state(game).item_transfers) == 1 and game.dice.calls == 1
    answer(game, OTHER, "enforcer_escape", text="Actual escape; unchanged map coordinates")
    assert game.inspect(PLAYER, identity)["state"] == "complete"
    tick(worker, gateway, 6)
    assert "PRIVATE_ACTUAL_ITEM_TAKING" not in str(gateway.messages)
