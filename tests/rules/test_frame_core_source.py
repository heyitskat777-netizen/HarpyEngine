"""Potential Tag marking obeys the actual scene and human; no Tag is spent."""

import asyncio
from uuid import uuid4

import pytest
from test_actors import bindings
from test_battle_service import prepared
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import answer, state, tick
from test_mission_ui import current

from girlframe.discord_adapter.m3_frame_core import open_core
from girlframe.engine import m3_battle as rules
from girlframe.engine.m2 import PilotSheet, PlayInput, TagState
from girlframe.engine.m3_battle_state import Declaration
from girlframe.services.m3_battle import _cast
from girlframe.services.m3_frame_core import FrameCoreService
from girlframe.services.onboarding import WorkflowError


def source(store):
    game, worker, gateway, battle, data, old = prepared(store)
    with store.transaction() as c:
        canon = state(game)
        canon.scene_casts.append(_cast(game, c, canon, 900))
        for asset in canon.sheets["2"].assets:
            if asset.family == "girl":
                asset.damaged = True
        canon.sheets["2"].tags = [
            TagState(
                id="actual-observed-tag",
                label="Reckless",
                giver=1,
                observers=(3,),
                marked=True,
                scene_used="actual-earlier-scene",
            )
        ]
        game.event(c, 1, str(uuid4()), "synthetic.actual_exposure_facts", canon)
    return game, worker, gateway, battle, old.actor, old.target, data["scene"]


@pytest.mark.parametrize(
    "invalid",
    [
        "same_human",
        "used",
        "unobserved",
        "pending",
        "missing_scene",
        "closed_scene",
        "wrong_role_controller",
        "absent_enemy",
    ],
)
def test_tag_criterion_rejects_each_actual_marking_barrier_without_resource_change(ledger, invalid):
    game, _, _, _, target, enemy, scene = source(ledger)
    canon = state(game)
    tag = canon.sheets["2"].tags[0]
    cast = next(x for x in canon.scene_casts if x.id == scene)
    if invalid == "same_human":
        enemy, tag.observers = target, (2,)
    elif invalid == "used":
        tag.scene_used = scene
    elif invalid == "unobserved":
        tag.observers = ()
    elif invalid == "pending":
        tag.rejection_pending = True
    elif invalid == "missing_scene":
        scene = "never-existed"
    elif invalid == "closed_scene":
        canon.scene_casts = [cast.model_copy(update={"open": False})]
    elif invalid == "wrong_role_controller":
        roles = tuple(
            x.model_copy(update={"controller": 2}) if x.actor == enemy else x for x in cast.roles
        )
        canon.scene_casts = [cast.model_copy(update={"roles": roles})]
    elif invalid == "absent_enemy":
        canon.scene_casts = [
            cast.model_copy(update={"roles": tuple(x for x in cast.roles if x.actor != enemy)})
        ]
    before = canon.model_dump_json()
    with pytest.raises(ValueError, match="actual scene human"):
        rules.expose_frame(
            canon,
            target,
            bindings(canon),
            "no-source",
            "Actual facts only",
            opponent=enemy,
            tag=tag.id,
            scene=scene,
        )
    assert canon.model_dump_json() == before


def test_marked_tag_from_earlier_scene_can_supply_criterion_without_new_mark_or_modifier(ledger):
    game, _, _, _, target, enemy, scene = source(ledger)
    canon = state(game)
    changed = rules.expose_frame(
        canon,
        target,
        bindings(canon),
        "actual-tag-core",
        "Actual enemy knows this vulnerability here",
        opponent=enemy,
        tag="actual-observed-tag",
        scene=scene,
    )
    assert changed.sheets == canon.sheets
    assert rules.core_available(changed, target, enemy, bindings(changed)) == "actual-tag-core"
    assert changed.facts[-1]["body"].find(scene) >= 0


def test_native_actual_tag_exposure_precedes_one_real_core_strike_and_preserves_tag(
    ledger, monkeypatch
):
    from girlframe.services import m2_game as shared

    monkeypatch.setattr(shared, "M3_HEAT_IDS", (*shared.M3_HEAT_IDS, "go_for_the_core"))
    game, worker, gateway, battle, target, enemy, scene = source(ledger)
    service = FrameCoreService(battle)
    before = state(game)

    async def run():
        initial = current(1, 610)
        initial.channel_id = 900
        await initial.response.defer(ephemeral=True)
        await open_core(initial, service)
        first = initial.edit_original_response.call_args.kwargs["view"]
        first.values["target"] = (target.token,)
        second = current(1, 611)
        await first.confirm.callback(second)
        form = second.edit_original_response.call_args.kwargs["view"]
        assert state(game) == before and game.dice.calls == 0
        assert not await form.interaction_check(current(2, 612))
        form.values.update(
            mode=("conditions",),
            opponent=(enemy.token,),
            tag=(enemy.token + "/actual-observed-tag",),
            account="The actual enemy recognizes her observed weakness during this opening",
        )
        await form.confirm.callback(current(1, 613))

    asyncio.run(run())
    after = state(game)
    assert after.sheets == before.sheets and game.dice.calls == 0
    assert after.facts[-1]["kind"] == "battle_frame_exposure"
    data = battle.preview(OTHER, 900)
    actor = next(x for x in data["actors"] if x["ref"] == enemy.model_dump(mode="json"))
    victim = next(x for x in data["actors"] if x["ref"] == target.model_dump(mode="json"))
    declaration = Declaration(
        play="go_for_the_core",
        actor=enemy,
        target=target,
        attacking_asset=actor["assets"][0]["id"],
        actor_sha256=actor["sha256"],
        target_sha256=victim["sha256"],
        account="Actual decisive strike after source exposure",
    )
    offered = battle.propose(OTHER, str(uuid4()), data["revision"], 900, declaration)
    battle.confirm(
        ADMIN,
        str(uuid4()),
        state(game).revision,
        offered["id"],
        opening=True,
        reach=True,
        outside_permission=False,
        indirect=False,
        evidence="Actual reviewed physical strike opening",
    )
    game.dice.faces = (6, 6)
    action = game.begin(
        OTHER,
        str(uuid4()),
        900,
        state(game).sheets["3"].revision,
        PlayInput(
            play="go_for_the_core",
            target_actor=target,
            attacking_asset=declaration.attacking_asset,
            battle_context=offered["id"],
            heat=0,
            piloting=True,
            context=declaration.account,
            trigger_confirmed=True,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    for human in (ADMIN, PLAYER, OTHER):
        answer(game, human, "tag_window", options=("pass",))
    assert game.inspect(OTHER, action)["state"] == "complete" and game.dice.calls == 1
    assert target == state(game).career_archives[-1].actor
    assert (
        PilotSheet.model_validate_json(state(game).career_archives[-1].sheet_json).tags
        == before.sheets["2"].tags
    )
    tick(worker, gateway, 4)
    with ledger.engine.connect() as c:
        assert game.lock(c, 900)["state"] == "released"


def test_exposure_stale_or_wrong_owner_does_not_commit_even_valid_conditions(ledger):
    game, _, _, battle, target, enemy, scene = source(ledger)
    original = state(game)
    for viewer, revision, message in (
        (OTHER, original.revision, "adjudicator"),
        (ADMIN, original.revision - 1, "STALE_CORE"),
    ):
        with pytest.raises(WorkflowError, match=message):
            battle.expose(
                viewer,
                str(uuid4()),
                revision,
                target,
                "Original actual facts",
                opponent=enemy,
                tag="actual-observed-tag",
                scene=scene,
            )
        assert state(game) == original and game.dice.calls == 0


def test_legacy_cast_exposure_materializes_only_real_source_joins_and_replay_is_exact(ledger):
    game, _, _, battle, data, declaration = prepared(ledger)
    before = state(game)
    assert not before.scene_casts
    result = battle.expose(
        PLAYER,
        "actual-legacy-core",
        before.revision,
        declaration.actor,
        "I willingly expose my actual Frame in the real joined scene",
        willing=True,
        scene=data["scene"],
    )
    assert (
        battle.expose(
            PLAYER,
            "actual-legacy-core",
            before.revision,
            declaration.actor,
            "I willingly expose my actual Frame in the real joined scene",
            willing=True,
            scene=data["scene"],
        )
        == result
    )
    after = state(game)
    cast = after.scene_casts[0]
    assert after.sheets == before.sheets and cast.id == data["scene"]
    assert {x.actor.entity for x in cast.roles} == {"2", "3"}
    assert all(x.actor.kind == "pilot" and x.source_event for x in cast.roles)
    assert cast.facilitator == 1 and cast.facilitator_source
    assert (
        game.dice.calls == 0
        and len([x for x in after.facts if x.get("kind") == "battle_frame_exposure"]) == 1
    )
