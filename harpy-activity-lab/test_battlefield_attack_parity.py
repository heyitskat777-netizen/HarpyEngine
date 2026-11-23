"""Battlefield declaration, independent Handler review, and saved attack choices."""

import json
from uuid import uuid4

import pytest
from girlframe.engine import m3_casualty, m3_vatgrown_plays
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_handler_play_state import Effect
from girlframe.engine.m3_physical_state import CockpitAction
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_handler_plays import HandlerPlayService
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_physical import PhysicalService
from girlframe.services.onboarding import WorkflowError
from test_battle_service import prepared
from test_enforcer_requisitions import approved
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger_fixture
from test_m2_game import pass_tags, state, tick
from test_vatgrown_plays import _learn_daily_source, ready

import mission_lab  # noqa: F401
from battlefield import Battlefield

ledger = ledger_fixture


@pytest.mark.parametrize("kind", ("assault", "core"))
def test_battlefield_attack_reviews_and_rolls_belong_to_original_owners(ledger, kind):
    game, worker, gateway, service, _, declaration = prepared(ledger)

    def battlefield():
        return Battlefield(
            MissionService(ledger),
            ADMIN,
            PLAYER,
            OTHER,
            shared=True,
            channel=900,
            private=True,
            dice=game.dice,
        )

    adapter = battlefield()
    if kind == "core":
        service.expose(
            OTHER,
            "original-owned-exposure",
            state(game).revision,
            declaration.target,
            "I voluntarily expose my occupied Frame Core.",
            willing=True,
        )
    args = {
        "revision": state(game).revision,
        "target": declaration.target.token,
        "attacking_asset": declaration.attacking_asset,
        "account": declaration.account,
    }
    if kind == "assault":
        args["target_asset"] = declaration.target_asset
    report = adapter.perform(PLAYER, "actual-attack", kind + "-declare", args)
    assert game.dice.calls == 0
    review = {
        "id": report["id"],
        "revision": state(game).revision,
        "opening": True,
        "reach": True,
        "evidence": "The original weapon reaches the actual opening.",
    }
    if kind == "core":
        review["capability"] = True
    with pytest.raises(WorkflowError):
        adapter.perform(PLAYER, "forged-attack-review", kind + "-review", review)
    adapter.perform(ADMIN, "original-attack-review", kind + "-review", review)
    game.dice.faces = (4, 5) if kind == "assault" else (1, 1)
    roll = {
        "id": report["id"],
        "sheet_revision": state(game).sheets[str(PLAYER.user_id)].revision,
    }
    if kind == "core":
        roll["heat"] = 0
    with pytest.raises(WorkflowError):
        adapter.perform(OTHER, "forged-attack-roll", kind + "-roll", roll)
    action = adapter.perform(PLAYER, "original-attack-roll", kind + "-roll", roll)[
        "action_id"
    ]
    tick(worker, gateway, 3)
    pass_tags(game)
    receipt = game.inspect(PLAYER, action)["receipt"]
    ledger.engine.dispose()
    reopened = battlefield()
    owners = (ADMIN, PLAYER, OTHER) if kind == "assault" else (OTHER,)
    for owner in owners:
        choice = next(
            row
            for row in reopened.game.choices(owner)
            if row["kind"]
            == ("battle_assault_table" if kind == "assault" else "battle_counter")
        )
        body = {
            "id": choice["id"],
            "revision": choice["revision"],
            "role": "handler" if owner == ADMIN else "pilot",
            "answer": {"flag": False, "text": "The original source assessment."},
        }
        intruder = OTHER if owner != OTHER else PLAYER
        with pytest.raises(WorkflowError):
            reopened.perform(
                intruder, "wrong-original-answer-" + str(owner.user_id), "choice", body
            )
        reopened.perform(
            owner, "actual-original-answer-" + str(owner.user_id), "choice", body
        )
    saved = reopened.game.inspect(PLAYER, action)
    assert saved["state"] == "complete" and saved["receipt"] == receipt
    assert game.dice.calls == 1


def test_learned_extra_assault_maneuver_uses_the_original_owner_and_receipt(
    ledger,
    tmp_path,
    monkeypatch,
):
    game, worker, gateway, controls = ready(
        ledger, tmp_path, monkeypatch, teacher="CASUALTY"
    )
    vat = m3_vatgrown_plays
    approved(
        ledger,
        game,
        tmp_path,
        monkeypatch,
        extra=(vat.EXPERIMENT, vat.INVESTMENT, vat.SEX, m3_casualty.BETTER),
    )
    lesson = _learn_daily_source(game, worker, gateway, controls, m3_casualty.BETTER)
    physical = PhysicalService(ledger)
    for viewer in (PLAYER, OTHER):
        actual = state(game)
        actor = current_ref(actual, viewer.user_id)
        with ledger.engine.connect() as c:
            pose = resolve(
                actual, actor, profiles(c, ledger.campaign_id)
            ).position_sha256
        physical.operate(
            viewer,
            str(uuid4()),
            actual.revision,
            CockpitAction(
                actor=actor,
                operation="pilot",
                expected_position=pose,
                confirmed=True,
                account="I actually pilot my own Frame in this scene.",
            ),
            channel=900,
        )

    def battlefield():
        return Battlefield(
            MissionService(ledger),
            ADMIN,
            PLAYER,
            OTHER,
            shared=True,
            channel=900,
            private=True,
            dice=game.dice,
        )

    adapter = battlefield()
    actual = state(game)
    actor_asset = next(
        row.id for row in actual.sheets["2"].assets if row.family == "frame"
    )
    target_asset = next(
        row.id for row in actual.sheets["3"].assets if row.family == "frame"
    )
    offered = adapter.perform(
        PLAYER,
        "learned-assault-declaration",
        "assault-declare",
        {
            "revision": actual.revision,
            "target": current_ref(actual, OTHER.user_id).token,
            "attacking_asset": actor_asset,
            "target_asset": target_asset,
            "account": "I take an opening with my own current Frame Asset.",
        },
    )
    adapter.perform(
        ADMIN,
        "learned-assault-review",
        "assault-review",
        {
            "id": offered["id"],
            "revision": state(game).revision,
            "opening": True,
            "reach": True,
            "evidence": "The real Frame reaches the opening.",
        },
    )
    review = adapter.view(PLAYER)
    assert (
        "reserves your No One Better lesson"
        in review["declarations"]["all_out_assault"]["learned_rider"]
    )
    assert 1 in review["heat_options"]
    heat = state(game).sheets["2"].heat
    game.dice.faces = (5, 6)
    calls = game.dice.calls
    action = adapter.perform(
        PLAYER,
        "learned-assault-roll",
        "assault-roll",
        {
            "id": offered["id"],
            "sheet_revision": state(game).sheets["2"].revision,
            "heat": 1,
        },
    )["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    receipt = game.inspect(PLAYER, action)["receipt"]
    ledger.engine.dispose()
    reopened = battlefield()
    choices = reopened.choices(action, PLAYER, str(PLAYER.user_id))
    extra = next(row for row in choices if row["kind"] == "engage_assault_extra")
    assert not any(
        row["id"] == extra["id"] for row in reopened.choices(action, OTHER, "2")
    )
    assert "spent lesson" in extra["prompt"] and "cover" in extra["fields"]["maneuvers"]
    assert actor_asset in {row["id"] for row in extra["fields"]["assets"]}
    data = {name: extra[name] for name in ("id", "revision", "role")} | {
        "answer": {
            "options": ["cover"],
            "fields": {"cover": actor_asset},
            "text": "My own Frame Asset provides actual cover.",
        },
    }
    with pytest.raises(WorkflowError):
        reopened.perform(OTHER, "wrong-extra-maneuver-owner", "choice", data)
    saved = reopened.perform(PLAYER, "own-earned-maneuver", "choice", data)
    assert reopened.perform(PLAYER, "own-earned-maneuver", "choice", data) == saved
    changed = state(reopened.game)
    maneuvers = [
        json.loads(row["body"])
        for row in changed.facts
        if row["kind"] == "engage_maneuver"
    ]
    assert (
        sum(
            row["source_action"] == action and row["kind"] == "cover"
            for row in maneuvers
        )
        == 1
    )
    used = next(
        row
        for row in changed.sheets["2"].girl_runtime.learned_plays
        if row.id == lesson.id
    )
    assert (
        used.rolled_event
        and game.dice.calls == calls + 1
        and changed.sheets["2"].heat == heat - 1
    )
    assert reopened.game.inspect(PLAYER, action)["receipt"] == receipt


def test_assault_last_asset_starts_only_the_actual_battlefield_defeat(ledger):
    game, worker, gateway, _, _, declaration = prepared(ledger)
    handler = HandlerPlayService(ledger)
    actual = state(game)
    frames = [row for row in actual.sheets["3"].assets if row.family == "frame"]
    last = frames[-1].id
    for row in frames[:-1]:
        key = "previous-frame-damage-" + row.id
        issued = handler.start(ADMIN, key, state(game).revision, (declaration.target,))[
            "id"
        ]
        handler.submit(
            ADMIN,
            key + "-apply",
            issued,
            state(game).revision,
            "mess",
            Effect(
                kind="damage",
                target=declaration.target,
                asset=row.id,
                account="Actual prior Frame damage.",
            ),
        )
    weapon = next(
        row.id for row in state(game).sheets["2"].assets if row.family == "frame"
    )

    def battlefield():
        return Battlefield(
            MissionService(ledger),
            ADMIN,
            PLAYER,
            OTHER,
            shared=True,
            channel=900,
            private=True,
            dice=game.dice,
        )

    field = battlefield()
    offered = field.perform(
        PLAYER,
        "last-asset-assault",
        "assault-declare",
        {
            "revision": state(game).revision,
            "target": declaration.target.token,
            "attacking_asset": weapon,
            "target_asset": last,
            "account": "Strike the last functional Asset.",
        },
    )
    field.perform(
        ADMIN,
        "last-asset-review",
        "assault-review",
        {
            "id": offered["id"],
            "revision": state(game).revision,
            "opening": True,
            "reach": True,
            "evidence": "The attack reaches the actual opening.",
        },
    )
    game.dice.faces = (4, 5)
    root = field.perform(
        PLAYER,
        "last-asset-roll",
        "assault-roll",
        {
            "id": offered["id"],
            "sheet_revision": state(game).sheets["2"].revision,
        },
    )["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    receipt = game.inspect(PLAYER, root)["receipt"]
    for viewer in (PLAYER, ADMIN, OTHER):
        table = next(
            row
            for row in field.choices(root, viewer, "2")
            if row["kind"] == "battle_assault_table"
        )
        field.perform(
            viewer,
            "last-asset-table-" + str(viewer.user_id),
            "choice",
            {name: table[name] for name in ("id", "role", "revision")}
            | {
                "answer": {
                    "flag": False,
                    "text": "The real defender has no vast advantage.",
                },
            },
        )
    ledger.engine.dispose()
    reopened = battlefield()
    choice = next(
        row
        for row in reopened.choices(root, OTHER, "2")
        if row["kind"] == "battle_defeat"
    )
    assert not any(
        row["id"] == choice["id"] for row in reopened.choices(root, PLAYER, "2")
    )
    data = {name: choice[name] for name in ("id", "role", "revision")} | {
        "answer": {"account": "My own Frame's last intact Asset failed."},
    }
    with pytest.raises(WorkflowError):
        reopened.perform(PLAYER, "wrong-defeat-owner", "choice", data)
    game.dice.faces = (2, 3)
    started = reopened.perform(OTHER, "start-actual-battle-defeat", "choice", data)
    assert (
        reopened.perform(OTHER, "start-actual-battle-defeat", "choice", data) == started
    )
    tick(worker, gateway, 3)
    pass_tags(game)
    child = started["action_id"]
    saved_child = reopened.game.inspect(OTHER, child)
    assert saved_child["play"] == "defeat" and saved_child["receipt"]["faces"] == [2, 3]
    ledger.engine.dispose()
    reopened = battlefield()
    assert reopened.game.inspect(OTHER, child)["receipt"] == saved_child["receipt"]
    assert (
        reopened.game.inspect(PLAYER, root)["receipt"] == receipt
        and game.dice.calls == 2
    )
    assert next(
        row
        for row in reopened.choices(child, OTHER, "3")
        if row["kind"] == "defeat_select"
    )
