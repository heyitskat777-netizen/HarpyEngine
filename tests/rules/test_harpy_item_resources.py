"""Real carried mechanical objects remain one Harpy resource authority in every consumer."""

from uuid import uuid4

import pytest
from test_harpy_actor_plays import begin, pass_tags, ready
from test_items import transfer
from test_ledger import OTHER, PLAYER
from test_ledger import ledger as ledger_fixture
from test_m2_game import Gateway, answer, state, tick
from test_personal_firearm import reviewed_registry
from test_retained_tag_permissions import reborn_with_lock
from test_world import gorgon

from girlframe.delivery.m2_worker import GameWorker
from girlframe.engine import m3_battle as battle
from girlframe.engine import m3_battle_dormant as dormant
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_dive import resources
from girlframe.engine.m3_harpy_resources import assets, set_assets
from girlframe.engine.m3_items import actual_asset
from girlframe.services.m3_access import digest
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_items import prove_item
from girlframe.services.m3_personal_firearm import PersonalFirearmService

ledger = ledger_fixture


def carried(store, tmp_path, monkeypatch, *, converted=False):
    if converted:
        game, _, _, actor, _, _ = reborn_with_lock(store)
        service = None
    else:
        service, game, _, actor = ready(store, faces=(4, 5))
    # This real extra acquired object leaves its original holder with another
    # non-Void Asset; the transfer does not discard an unrelated Void threshold.
    registry = reviewed_registry()
    path = tmp_path / "synthetic-firearm-source-only.json"
    path.write_text(registry.model_dump_json())
    monkeypatch.setenv("GIRLFRAME_RULES_REGISTRY", str(path))
    approval = store.policy.m3_approval
    store.policy = store.policy.model_copy(
        update={
            "m3_approval": approval.model_copy(
                update={
                    "registry_sha256": digest(registry),
                    "subsystems": approval.subsystems | {"economy"},
                }
            ),
        }
    )
    with store.transaction() as c:
        original = state(game)
        original.sheets["3"].permissions = 5
        game.event(c, 1, str(uuid4()), "synthetic.prior_acquisition_funds", original)
    firearm = PersonalFirearmService(game, registry)
    view = firearm.acquisition_view(OTHER, "frame_grafting")
    firearm.buy_firearm(
        OTHER,
        str(uuid4()),
        ActorRef.model_validate(view["actor"]),
        view["source_sha256"],
        "frame_grafting",
        "Actual owned pistol source",
    )
    original = state(game)
    source = current_ref(original, 3)
    asset = original.personal_firearms[-1].issues[-1].asset
    item = transfer(game, source, actor, "asset:" + asset)
    return service, game, actor, item


@pytest.mark.parametrize("converted", [False, True])
def test_actual_carried_asset_damage_and_dormant_cost_preserve_sole_source(
    ledger, tmp_path, monkeypatch, converted
):
    _, game, actor, item = carried(ledger, tmp_path, monkeypatch, converted=converted)
    with ledger.transaction() as c:
        canon = state(game)
        canon.world = canon.world.model_copy(
            update={"gorgons": (*canon.world.gorgons, gorgon("dormant", "actual-dormant"))}
        )
        game.event(c, 1, str(uuid4()), "synthetic.actual_dormant_presence", canon)
    original = state(game)
    base = (
        original.harpy_states[-1].assets
        if converted
        else next(x.assets for x in original.world.pilots if x.id == actor.entity)
    )
    assert all(x.void for x in base)
    assert next(x for x in resources(original, actor)[0] if x.id == item.asset_id).void is False
    old_source = original.sheets["3"].model_dump_json()
    old_same_human = original.sheets.get("2")
    original_item = original.held_items[-1]
    foe = current_ref(original, 3)
    damage_event = str(uuid4())
    with ledger.transaction() as c:
        bound = profiles(c, ledger.campaign_id)
        original_view = resolve(original, actor, bound)
        assert sum(x.id == item.asset_id for x in original_view.assets) == 1
        changed, needed = battle.damage(
            original,
            actor,
            item.asset_id,
            bound,
            damage_event,
            opponent=foe,
        )
        assert not needed
        game.event(
            c,
            3,
            str(uuid4()),
            "synthetic.actual_carried_asset_damage",
            changed,
            event_id=damage_event,
        )
        assert prove_item(c, game, changed, item.id) == changed.held_items[-1]
        assert resolve(changed, actor, bound).source_sha256 != original_view.source_sha256
    damaged = state(game)
    assert actual_asset(damaged, damaged.held_items[-1]).damaged
    assert damaged.held_items[-1].state_event == damage_event
    assert damaged.held_items[-1].source_event == original_item.source_event
    assert damaged.held_items[-1].source_owner == original_item.source_owner
    assert damaged.sheets["3"].model_dump_json() == old_source
    assert damaged.sheets.get("2") == old_same_human
    assert (
        damaged.harpy_states[-1].assets
        if converted
        else next(x.assets for x in damaged.world.pilots if x.id == actor.entity)
    ) == base
    snapshot = damaged.model_dump_json()
    dormant_actor = ActorRef(kind="gorgon", entity="actual-dormant")
    with ledger.engine.connect() as c:
        bindings = profiles(c, ledger.campaign_id)
    with pytest.raises(ValueError, match="uncorrupted Harpy Asset must take"):
        dormant.inflict(
            damaged,
            bindings,
            actor,
            dormant_actor,
            "actual-unpaid-work",
            None,
            "Cannot claim already fully Void",
            str(uuid4()),
            piloting=True,
        )
    assert damaged.model_dump_json() == snapshot
    paid_event = str(uuid4())
    paid, followups = dormant.inflict(
        damaged,
        bindings,
        actor,
        dormant_actor,
        "actual-paid-work",
        item.asset_id,
        "Actual carried apparatus becomes Void",
        paid_event,
        piloting=True,
    )
    assert not followups
    current_item = next(x for x in paid.held_items if x.id == item.id)
    assert actual_asset(paid, current_item).void and actual_asset(paid, current_item).damaged
    assert current_item.state_event == paid_event
    assert current_item.origin_asset_json == original_item.origin_asset_json
    with ledger.transaction() as c:
        game.event(
            c,
            2,
            str(uuid4()),
            "synthetic.actual_carried_asset_corruption",
            paid,
            event_id=paid_event,
        )
        assert prove_item(c, game, paid, item.id) == current_item
    assert (
        paid.harpy_states[-1].assets
        if converted
        else next(x.assets for x in paid.world.pilots if x.id == actor.entity)
    ) == base
    repaired = set_assets(
        paid,
        actor,
        tuple(
            x.model_copy(update={"damaged": False}) if x.id == item.asset_id else x
            for x in assets(paid, actor)
        ),
        event="actual-owned-repair-source",
    )
    assert not actual_asset(repaired, repaired.held_items[-1]).damaged
    assert actual_asset(repaired, repaired.held_items[-1]).void
    assert repaired.held_items[-1].state_event == "actual-owned-repair-source"


def test_actual_owned_harpy_dive_corrupts_held_object_without_copying_into_base(
    ledger, tmp_path, monkeypatch
):
    service, game, actor, item = carried(ledger, tmp_path, monkeypatch)
    before = state(game)
    base = before.world.pilots[-1].assets
    same_human = before.sheets["2"].model_dump_json()
    action = begin(service, actor, play="dive_deep")
    worker, gateway = GameWorker(game), Gateway()
    tick(worker, gateway, 3)
    pass_tags(game)
    answer(
        game,
        PLAYER,
        "dive_select",
        options=("void_and_unmark_all",),
        text="Actual owned Harpy connection",
    )
    answer(
        game,
        PLAYER,
        "dive_effect",
        fields={"asset": item.asset_id},
        text="Actual carried object changes in the connection",
    )
    after = state(game)
    assert actual_asset(after, after.held_items[-1]).void
    assert after.world.pilots[-1].assets == base
    assert after.sheets["2"].model_dump_json() == same_human
    assert len([x for x in assets(after, actor) if x.id == item.asset_id]) == 1
    with ledger.engine.connect() as c:
        assert prove_item(c, game, after, item.id) == after.held_items[-1]
    assert game.inspect(PLAYER, action)["state"] == "complete" and game.dice.calls == 1


def test_harpy_resource_updates_reject_new_removed_duplicate_or_reclassified_assets(
    ledger, tmp_path, monkeypatch
):
    _, game, actor, _ = carried(ledger, tmp_path, monkeypatch)
    original = state(game)
    current = assets(original, actor)
    snapshot = original.model_dump_json()
    for supplied in (
        current[:-1],
        (*current, current[-1]),
        (*current, current[-1].model_copy(update={"id": "unrelated-new-asset"})),
        tuple(
            x.model_copy(update={"name": "New ability"}) if x.id == current[-1].id else x
            for x in current
        ),
    ):
        with pytest.raises(ValueError):
            set_assets(original, actor, supplied, event="actual-event")
    assert original.model_dump_json() == snapshot
