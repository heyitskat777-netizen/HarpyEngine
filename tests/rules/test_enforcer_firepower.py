"""Actual paid extra hit, original Assault consequences and one shared roll."""

from uuid import uuid4

import pytest
from test_battle_pipeline import table
from test_battle_service import confirm, prepared
from test_enforcer_requisitions import approved, buy
from test_ledger import ADMIN, PLAYER
from test_ledger import ledger as ledger_fixture
from test_m2_game import answer, pass_tags, state, tick

from girlframe.engine.m2 import PlayInput
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_enforcer_requisitions import FIREPOWER

ledger = ledger_fixture


def rolled(store, tmp_path, monkeypatch, faces=(6, 6)):
    import girlframe.services.m2_game as shared

    monkeypatch.setattr(
        shared, "M3_HEAT_IDS", (*shared.M3_HEAT_IDS, "all_out_assault", "go_for_the_core")
    )
    game, worker, gateway, service, _, declaration = prepared(store)
    acquired = approved(store, game, tmp_path, monkeypatch)
    with store.transaction() as c:
        canon = state(game)
        canon.sheets["2"].permissions = 3
        game.event(c, 1, str(uuid4()), "synthetic.prior_permissions", canon)
    buy(acquired, FIREPOWER, "frame_grafting")
    view = service.preview(PLAYER, 900)
    attacker = next(
        x for x in view["actors"] if x["ref"] == declaration.actor.model_dump(mode="json")
    )
    victim = next(
        x for x in view["actors"] if x["ref"] == declaration.target.model_dump(mode="json")
    )
    declaration = declaration.model_copy(
        update={"actor_sha256": attacker["sha256"], "target_sha256": victim["sha256"]}
    )
    context = confirm(service, game, view, declaration)
    game.dice.faces = faces
    action = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play="all_out_assault",
            heat=0,
            target_actor=declaration.target,
            attacking_asset=declaration.attacking_asset,
            target_asset=declaration.target_asset,
            battle_context=context,
            context=declaration.account,
            trigger_confirmed=True,
            piloting=True,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    return game, worker, gateway, action, declaration


@pytest.mark.parametrize("take", [False, True])
def test_real_high_second_hit_is_optional_exact_source_then_original_high_consequences_finish(
    ledger, tmp_path, monkeypatch, take
):
    game, worker, gateway, action, declared = rolled(ledger, tmp_path, monkeypatch)
    initial = state(game)
    if take:
        choice = next(x for x in game.choices(PLAYER) if x["kind"] == "enforcer_firepower")
        detail = game.decision(PLAYER, choice["id"])["enforcer_firepower"]
        target = next(
            x for x in detail["targets"] if ActorRef.model_validate(x["ref"]) == declared.target
        )
        second = next(x["id"] for x in target["assets"] if x["id"] != declared.target_asset)
        answer(
            game,
            PLAYER,
            "enforcer_firepower",
            flag=True,
            fields={"target": target["token"], "asset": second},
            text="Actual additional enemy Asset hit",
        )
        assert not any(x.damaged for x in state(game).sheets["3"].assets)
        answer(
            game,
            ADMIN,
            "enforcer_firepower_confirm",
            flag=True,
            text="Actual extra enemy and relevant reachable equipment confirmed",
        )
        assert next(x for x in state(game).sheets["3"].assets if x.id == second).damaged
    else:
        answer(game, PLAYER, "enforcer_firepower", flag=False)
    table(game)
    answer(game, ADMIN, "battle_handler", options=("damage_actor_asset",))
    chosen = next(x.id for x in state(game).sheets["2"].assets if not x.damaged)
    answer(game, PLAYER, "battle_actor_damage", fields={"asset": chosen})
    after = state(game)
    assert sum(x.damaged for x in after.sheets["3"].assets) == (2 if take else 1)
    assert next(x for x in after.sheets["3"].assets if x.id == declared.target_asset).damaged
    assert next(x for x in after.sheets["2"].assets if x.id == chosen).damaged
    assert after.sheets["2"].permissions == initial.sheets["2"].permissions
    assert game.inspect(PLAYER, action)["state"] == "complete" and game.dice.calls == 1
    tick(worker, gateway, 7)
    with ledger.engine.connect() as c:
        assert game.lock(c, 900)["state"] == "released"


def test_owned_firepower_does_not_change_actual_mid_outcome(ledger, tmp_path, monkeypatch):
    game, _, _, action, declared = rolled(ledger, tmp_path, monkeypatch, (4, 5))
    assert not any(x["kind"].startswith("enforcer_firepower") for x in game.choices(PLAYER))
    table(game)
    assert sum(x.damaged for x in state(game).sheets["3"].assets) == 1
    assert game.inspect(PLAYER, action)["state"] == "complete" and game.dice.calls == 1
