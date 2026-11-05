"""The actual Harpy's optional Engage maneuver precedes its one real Assault outcome."""

from uuid import uuid4

import pytest
from test_harpy_actor_plays import begin, ready
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Gateway, answer, pass_tags, state, tick
from test_physical_operations import place

from girlframe.delivery.m2_worker import GameWorker
from girlframe.engine import m3_plays
from girlframe.engine.m2 import ChoiceAnswer
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_battle_state import Declaration
from girlframe.engine.m3_handler_play_state import Effect
from girlframe.services.m3_battle import BattleService
from girlframe.services.m3_handler_plays import HandlerPlayService


def rolled(store, monkeypatch, faces=(4, 4)):
    monkeypatch.setattr(m3_plays, "HEAT_IDS", (*m3_plays.HEAT_IDS, "all_out_assault"))
    plays, game, _, actor = ready(store, faces=faces)
    with store.transaction() as c:
        canon = place(state(game), 3)
        game.event(c, 3, "actual-opponent-frame", "synthetic.state", canon)
    battle = BattleService(store)
    data = battle.preview(PLAYER, 900)
    source = next(x for x in data["actors"] if x["ref"] == actor.model_dump(mode="json"))
    target = next(
        x for x in data["actors"] if x["ref"]["kind"] == "pilot" and x["ref"]["entity"] == "3"
    )
    declaration = Declaration(
        play="all_out_assault",
        actor=actor,
        target=ActorRef.model_validate(target["ref"]),
        attacking_asset=source["assets"][0]["id"],
        target_asset=target["assets"][0]["id"],
        actor_sha256=source["sha256"],
        target_sha256=target["sha256"],
        account="The actual Harpy takes an established opening",
    )
    proposed = battle.propose(PLAYER, str(uuid4()), data["revision"], 900, declaration)
    battle.confirm(
        ADMIN,
        str(uuid4()),
        state(game).revision,
        proposed["id"],
        opening=True,
        reach=True,
        outside_permission=True,
        indirect=False,
        evidence="Actual range and capability in the Conversation",
    )
    action = begin(
        plays,
        actor,
        play="all_out_assault",
        target_actor=declaration.target,
        attacking_asset=declaration.attacking_asset,
        target_asset=declaration.target_asset,
        battle_context=proposed["id"],
        piloting=True,
    )
    worker, gateway = GameWorker(game), Gateway()
    tick(worker, gateway, 3)
    pass_tags(game)
    return plays, game, worker, gateway, actor, action, declaration


@pytest.mark.parametrize("choose_extra", [False, True])
def test_real_harpy_mid_assault_extra_then_actual_target_damage_once(
    ledger, monkeypatch, choose_extra
):
    _, game, worker, gateway, actor, action, declaration = rolled(ledger, monkeypatch)
    original_pc = state(game).sheets["2"].model_copy(deep=True)
    selected = next(x for x in game.choices(PLAYER) if x["kind"] == "engage_assault_extra")
    decision = game.decision(PLAYER, selected["id"])
    assert decision["engage"]["minimum"] == 0 and decision["engage"]["maximum"] == 1
    answer(
        game,
        PLAYER,
        "engage_assault_extra",
        **(
            dict(
                options=("cover",),
                fields={"cover": declaration.attacking_asset},
                text="PRIVATE_HARPY_COVER",
            )
            if choose_extra
            else {}
        ),
    )
    for viewer in (ADMIN, PLAYER, OTHER):
        answer(game, viewer, "battle_assault_table", flag=False, text="Actual table judgment")
    assert game.inspect(PLAYER, action)["state"] == "complete"
    assert next(
        x for x in state(game).sheets["3"].assets if x.id == declaration.target_asset
    ).damaged
    assert state(game).sheets["2"] == original_pc and game.dice.calls == 1
    effects = [x for x in state(game).facts if x.get("kind") == "engage_maneuver"]
    assert len(effects) == int(choose_extra)
    tick(worker, gateway, 5)
    assert "PRIVATE_HARPY_COVER" not in str(gateway.messages)
    with ledger.engine.connect() as c:
        assert game.lock(c, 900)["state"] == "released"


def test_real_harpy_low_extra_keeps_primary_damage_and_actual_mandatory_handler_play(
    ledger, monkeypatch
):
    _, game, _, _, actor, action, declaration = rolled(ledger, monkeypatch, (1, 2))
    answer(
        game,
        PLAYER,
        "engage_assault_extra",
        options=("cover",),
        fields={"cover": declaration.attacking_asset},
        text="Actual Harpy cover before the impact",
    )
    answer(game, OTHER, "battle_low_damage", fields={"asset": declaration.attacking_asset})
    grant = next(x for x in state(game).handler_plays if x.source_action == action)
    HandlerPlayService(ledger).submit(
        ADMIN,
        str(uuid4()),
        grant.id,
        state(game).revision,
        "brief",
        Effect(kind="brief", account="Actual consequence of the original failed assault"),
    )
    assert game.inspect(PLAYER, action)["state"] == "complete" and game.dice.calls == 1
    assert state(game).world.pilots[0].assets[0].damaged


def test_real_harpy_high_extra_keeps_original_handler_selected_self_damage(ledger, monkeypatch):
    _, game, _, _, actor, action, declaration = rolled(ledger, monkeypatch, (6, 6))
    answer(
        game,
        PLAYER,
        "engage_assault_extra",
        options=("cover",),
        fields={"cover": declaration.attacking_asset},
        text="Actual high-tier cover",
    )
    for viewer in (ADMIN, PLAYER, OTHER):
        answer(game, viewer, "battle_assault_table", flag=False, text="Actual table judgment")
    answer(game, ADMIN, "battle_handler", options=("damage_actor_asset",))
    answer(game, PLAYER, "battle_actor_damage", fields={"asset": declaration.attacking_asset})
    assert game.inspect(PLAYER, action)["state"] == "complete"
    assert state(game).world.pilots[0].assets[0].damaged and game.dice.calls == 1


def test_harpy_extra_choice_rejects_unowned_asset_and_replays_exactly_once(ledger, monkeypatch):
    _, game, _, _, actor, action, declaration = rolled(ledger, monkeypatch)
    row = next(x for x in game.choices(PLAYER) if x["kind"] == "engage_assault_extra")
    original = state(game)
    from girlframe.services.onboarding import WorkflowError

    with pytest.raises(WorkflowError):
        game.respond(
            PLAYER,
            "bad-borrowed-extra",
            row["id"],
            row["revision"],
            ChoiceAnswer(
                options=("cover",),
                fields={"cover": original.sheets["2"].assets[0].id},
                text="Attempt to borrow another body's resources",
            ),
        )
    assert state(game) == original
    choice = ChoiceAnswer(
        options=("cover",),
        fields={"cover": declaration.attacking_asset},
        text="Actual source-bound extra",
    )
    first = game.respond(PLAYER, "real-extra-once", row["id"], row["revision"], choice)
    assert game.respond(PLAYER, "real-extra-once", row["id"], row["revision"], choice) == first
    assert len([x for x in state(game).facts if x.get("kind") == "engage_maneuver"]) == 1
    assert game.dice.calls == 1
