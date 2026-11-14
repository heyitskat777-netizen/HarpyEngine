"""Actual Core Bond producer → original owner's Void choice → unchanged receipt.

Synthetic-only release approval; no campaign approval is manufactured here.
"""

import json
from uuid import uuid4

import pytest
import sqlalchemy as sa
from test_enforcer_requisitions import approved
from test_janus_battery import connected, start
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import answer, pass_tags, state, tick

from girlframe.database import tables as t
from girlframe.engine import m3_harpy_bond_void as rules
from girlframe.engine.m2 import ChoiceAnswer
from girlframe.engine.m3_actor_bonds import change, current_ref, depth, set_depth
from girlframe.engine.m3_bond_operations import records
from girlframe.engine.m3_janus import BATTERY, CORE
from girlframe.services.m3_frame_control import FrameControlService
from girlframe.services.m3_harpy_bond_void import HarpyBondVoidService, prove_gain
from girlframe.services.onboarding import WorkflowError


def prepared(store, tmp_path, monkeypatch):
    game, worker, gateway, core, contact = connected(store, tmp_path, monkeypatch)
    approved(store, game, tmp_path, monkeypatch, extra=(CORE, BATTERY, rules.NATIVE_RULE))
    # The relationship genuinely predates this Play. set_depth restores known
    # Personal history and deliberately does not claim a new deepening event.
    with store.transaction() as c:
        original = state(game)
        event = str(uuid4())
        original = set_depth(original, current_ref(original, 2), core, 1, event)
        game.event(
            c, 1, str(uuid4()), "synthetic.prior_personal_core_bond", original, event_id=event
        )
    assert not rules.cases(state(game))
    return game, worker, gateway, core, contact


def deepen(game, worker, gateway, core):
    identity = start(game, core)
    tick(worker, gateway, 3)
    if game.inspect(PLAYER, identity)["state"] != "tag_window":
        game.roll(PLAYER, str(uuid4()), identity)
    pass_tags(game)
    answer(game, PLAYER, "janus_select", options=("bond", "identities"))
    return identity


def owned_choice(game, identity):
    row = next(
        x
        for x in game.choices(PLAYER)
        if x["kind"] == "harpy_bond_void" and x["action_id"] == identity
    )
    effect = next(x for x in rules.cases(state(game)) if x.source_action == identity)
    return row, effect


def save_owned(game, row, asset, *, key=None):
    return game.respond(
        PLAYER,
        key or str(uuid4()),
        row["id"],
        row["revision"],
        ChoiceAnswer(options=(asset,), text="PRIVATE_ACTUAL_SIN_REWRITE"),
    )


def test_real_battery_intense_and_capped_deepening_own_void_original_receipts_and_retries(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, core, contact = prepared(ledger, tmp_path, monkeypatch)
    identity = deepen(game, worker, gateway, core)
    row, effect = owned_choice(game, identity)
    actual = state(game)
    assert depth(actual, current_ref(actual, 2), core) == 2
    assert effect.actor == current_ref(actual, 2) and effect.controller == PLAYER.user_id
    assert effect.harpy == core and effect.harpy.entity != str(OTHER.user_id)
    assert effect.phase == "rewrite" and game.inspect(PLAYER, identity)["state"] != "complete"
    original_receipt = game.inspect(PLAYER, identity)["receipt"]
    original_heat = actual.sheets["2"].heat
    service = HarpyBondVoidService(game)
    with pytest.raises(WorkflowError):
        service.view(OTHER, effect.id)
    with pytest.raises(WorkflowError):
        service.view(ADMIN, effect.id)
    view = service.view(PLAYER, effect.id)
    asset = view["assets"][0]["id"]
    before = actual.model_dump_json()
    with pytest.raises(WorkflowError):
        game.respond(
            OTHER,
            str(uuid4()),
            row["id"],
            row["revision"],
            ChoiceAnswer(options=(asset,), text="Wrong actual controller"),
        )
    assert state(game).model_dump_json() == before
    with pytest.raises(WorkflowError):
        save_owned(game, row, "missing-actual-asset")
    assert state(game).model_dump_json() == before
    result = save_owned(game, row, asset, key="owned-sin-first")
    assert save_owned(game, row, asset, key="owned-sin-first") == result
    assert rules.get(state(game), effect.id).phase == "complete"
    assert next(x for x in state(game).sheets["2"].assets if x.id == asset).void
    assert game.inspect(PLAYER, identity)["receipt"] == original_receipt
    assert state(game).sheets["2"].heat == original_heat and game.dice.calls == 1
    assert game.inspect(PLAYER, identity)["state"] == "complete"
    with ledger.engine.connect() as c:
        assert prove_gain(game, c, state(game), effect.id).asset == asset

    # End the actual first neural contact, then establish a new real contact;
    # a second Play cannot reuse its already consumed Living Battery source.
    tick(worker, gateway, 4)
    control = FrameControlService(game)
    control.unplug(
        PLAYER, str(uuid4()), contact, state(game).revision, "Actual caster removes original jack"
    )
    caster = current_ref(state(game), 2)
    second = control.propose(
        PLAYER, str(uuid4()), 900, caster, core, "Actual neural jack is inserted for a new contact"
    )["id"]
    control.decide(
        ADMIN,
        str(uuid4()),
        second,
        state(game).revision,
        True,
        "The actual original bodies establish a fresh spinal contact",
    )
    before_heat = state(game).sheets["2"].heat
    second_id = deepen(game, worker, gateway, core)
    second_row, second_effect = owned_choice(game, second_id)
    assert second_effect.id != effect.id and second_effect.change != effect.change
    assert depth(state(game), current_ref(state(game), 2), core) == 2
    assert state(game).sheets["2"].heat == before_heat + 2
    second_receipt = game.inspect(PLAYER, second_id)["receipt"]
    second_asset = service.view(PLAYER, second_effect.id)["assets"][0]["id"]
    assert second_asset != asset
    save_owned(game, second_row, second_asset, key="owned-sin-second")
    assert game.inspect(PLAYER, second_id)["receipt"] == second_receipt
    assert game.dice.calls == 2 and len(rules.cases(state(game))) == 2
    assert sum(x.source_action == second_id for x in rules.cases(state(game))) == 1
    assert game.inspect(PLAYER, second_id)["state"] == "complete"


def test_recorded_capped_change_produces_once_but_restoring_or_weakening_does_not(
    ledger, tmp_path, monkeypatch
):
    game, _, _, core, _ = prepared(ledger, tmp_path, monkeypatch)
    original = state(game)
    actor = current_ref(original, 2)
    restored = set_depth(original, actor, core, 2, "restore-existing-history")
    assert not rules.cases(restored)
    changed = change(restored, actor, core, 1, "actual-capped-deepening")
    effect = rules.cases(changed)[0]
    operation = records(changed)[-1]
    assert operation.before_depth == operation.after_depth == 2
    rules.produce(changed, operation)
    assert rules.cases(changed) == (effect,)
    weakened = change(changed, actor, core, -1, "actual-source-weaken")
    assert rules.cases(weakened) == (effect,)
    assert not rules.cases(original)


def test_missing_owned_asset_does_not_commit_or_complete_source(ledger, tmp_path, monkeypatch):
    game, worker, gateway, core, _ = prepared(ledger, tmp_path, monkeypatch)
    identity = deepen(game, worker, gateway, core)
    row, effect = owned_choice(game, identity)
    before = state(game).model_dump_json()
    with pytest.raises(WorkflowError):
        save_owned(game, row, "absent-owned-resource")
    assert (
        state(game).model_dump_json() == before
        and rules.get(state(game), effect.id).phase == "rewrite"
    )
    assert game.inspect(PLAYER, identity)["state"] != "complete"
    assert game.dice.calls == 1
    with ledger.engine.connect() as c:
        works = (
            c.execute(
                sa.select(t.m3["m3_required_work"]).where(
                    t.m3["m3_required_work"].c.campaign_id == ledger.campaign_id,
                    t.m3["m3_required_work"].c.id == effect.id,
                )
            )
            .mappings()
            .all()
        )
        assert len(works) == 1 and works[0]["state"] == "pending"
        assert json.loads(works[0]["body_json"])["owner"] == effect.actor.model_dump(mode="json")


def test_real_battery_final_frame_asset_preserves_actual_mockingbird_threshold_and_owner(
    ledger, tmp_path, monkeypatch
):
    from girlframe.services.m3_void import VoidService

    game, worker, gateway, core, _ = prepared(ledger, tmp_path, monkeypatch)
    with ledger.transaction() as c:
        prior = state(game)
        frames = [x for x in prior.sheets["2"].assets if x.family == "frame"]
        assert len(frames) >= 2
        selected = frames[-1].id
        for asset in frames[:-1]:
            asset.void = True
            asset.description = "Synthetic prior established Void alteration"
        game.event(c, 1, str(uuid4()), "synthetic.prior_frame_corruption", prior)
    identity = deepen(game, worker, gateway, core)
    row, effect = owned_choice(game, identity)
    receipt = game.inspect(PLAYER, identity)["receipt"]
    save_owned(game, row, selected)
    gained = rules.get(state(game), effect.id)
    assert gained.phase == "threshold" and len(gained.thresholds) == 1
    assert game.inspect(PLAYER, identity)["state"] != "complete"
    assert all(x.void for x in state(game).sheets["2"].assets if x.family == "frame")
    service = VoidService(ledger)
    value = service.get(PLAYER, gained.thresholds[0])
    assert value["stage"] == "resist_pending"
    with pytest.raises(WorkflowError):
        service.get(OTHER, gained.thresholds[0])
    assert game.inspect(PLAYER, identity)["receipt"] == receipt and game.dice.calls == 1
    with ledger.engine.connect() as c:
        rows = (
            c.execute(
                sa.select(t.m3["m3_required_work"]).where(
                    t.m3["m3_required_work"].c.campaign_id == ledger.campaign_id,
                    t.m3["m3_required_work"].c.id == gained.thresholds[0],
                )
            )
            .mappings()
            .all()
        )
        assert len(rows) == 1 and rows[0]["state"] == "pending"
        body = json.loads(rows[0]["body_json"])
        assert body["reason"] == "harpy_bond_void" and body["source_action"] == identity
        assert body["owner"] == effect.actor.model_dump(mode="json")


def test_unreviewed_sin_blocks_actual_bond_choice_without_spending_original_source(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, core, _ = prepared(ledger, tmp_path, monkeypatch)
    # Restore a synthetic approval that deliberately omits this new rule.
    from girlframe.engine.rules_registry import Registry
    from girlframe.services.m3_access import digest, load_registry

    approved(ledger, game, tmp_path, monkeypatch, extra=(CORE, BATTERY))
    data = load_registry().model_dump(mode="json")
    for entry in data["entries"]:
        if entry["id"] in (rules.RULE, rules.NATIVE_RULE):
            entry.update(independent_review="pending", reviewer=None, review_reference=None)
    pending = Registry.model_validate_json(json.dumps(data))
    path = tmp_path / "synthetic-sin-unreviewed.json"
    path.write_text(pending.model_dump_json())
    monkeypatch.setenv("GIRLFRAME_RULES_REGISTRY", str(path))
    ledger.policy = ledger.policy.model_copy(
        update={
            "m3_approval": ledger.policy.m3_approval.model_copy(
                update={"registry_sha256": digest(pending)}
            )
        }
    )
    identity = start(game, core)
    tick(worker, gateway, 3)
    if game.inspect(PLAYER, identity)["state"] != "tag_window":
        game.roll(PLAYER, str(uuid4()), identity)
    pass_tags(game)
    before = state(game).model_dump_json()
    receipt = game.inspect(PLAYER, identity)["receipt"]
    with pytest.raises((WorkflowError, ValueError), match="UNSUPPORTED_RULE|M3_REVIEW_PENDING"):
        answer(game, PLAYER, "janus_select", options=("bond", "identities"))
    assert state(game).model_dump_json() == before
    assert not rules.cases(state(game))
    assert game.inspect(PLAYER, identity)["receipt"] == receipt and game.dice.calls == 1
    assert any(x["kind"] == "janus_select" for x in game.choices(PLAYER))


def test_real_battery_sin_storage_keeps_original_asset_and_proves_owned_gain(
    ledger, tmp_path, monkeypatch
):
    from girlframe.engine import m3_janus_storage as storage_rules
    from girlframe.engine.m3_janus_requisitions import STORAGE
    from girlframe.services.m3_janus_requisitions import JanusRequisitionService
    from girlframe.services.m3_janus_storage import StorageService

    game, worker, gateway, core, _ = prepared(ledger, tmp_path, monkeypatch)
    approved(ledger, game, tmp_path, monkeypatch, extra=(CORE, BATTERY, rules.RULE, STORAGE))
    with ledger.transaction() as c:
        canon = state(game)
        canon.sheets["2"].permissions = 2
        game.event(c, 1, str(uuid4()), "synthetic.actual_storage_funds", canon)
    purchases = JanusRequisitionService(game)
    menu = purchases.menu(PLAYER)
    purchases.buy_rule(
        PLAYER, str(uuid4()), menu["source_sha256"], STORAGE, "Actual paid original Void Storage"
    )
    identity = deepen(game, worker, gateway, core)
    row, effect = owned_choice(game, identity)
    asset = HarpyBondVoidService(game).view(PLAYER, effect.id)["assets"][0]["id"]
    original = next(x for x in state(game).sheets["2"].assets if x.id == asset).model_copy(
        deep=True
    )
    receipt = game.inspect(PLAYER, identity)["receipt"]
    answer_value = ChoiceAnswer(options=(asset, "storage"), text="SYNTHETIC_PRIVATE_STORED_SIN")
    result = game.respond(PLAYER, "actual-stored-sin", row["id"], row["revision"], answer_value)
    assert (
        game.respond(PLAYER, "actual-stored-sin", row["id"], row["revision"], answer_value)
        == result
    )
    assert next(x for x in state(game).sheets["2"].assets if x.id == asset) == original
    points = storage_rules.points(state(game))
    assert len(points) == 1 and points[0].source_kind == "harpy_bond_void"
    assert points[0].choice == points[0].action == effect.id
    assert StorageService(game).view(PLAYER)["points"][0]["active"]
    assert next(x for x in game.sheet(PLAYER)["assets"] if x["id"] == asset)["void"]
    assert game.inspect(PLAYER, identity)["receipt"] == receipt and game.dice.calls == 1
    assert game.inspect(PLAYER, identity)["state"] == "complete"
