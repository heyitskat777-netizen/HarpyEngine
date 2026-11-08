"""Real pre-roll NPC defenses and damaged owned Core capability, through native review."""

import asyncio
from uuid import uuid4

import pytest
from test_cast_service import change
from test_harpy_actor_plays import ready
from test_harpy_core import begin
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Gateway, answer, state, tick
from test_mission_ui import current

from girlframe.delivery.m2_worker import GameWorker
from girlframe.discord_adapter.m2_forms import NativeForm
from girlframe.discord_adapter.m3_battle import open_context
from girlframe.engine import m3_plays
from girlframe.engine.m2 import PlayInput
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_battle_state import Declaration, Defense
from girlframe.engine.m3_harpy_resources import assets, set_assets
from girlframe.engine.m3_world import update
from girlframe.engine.m3_world_state import Npc, WorldTag
from girlframe.services.m3_battle import BattleService
from girlframe.services.onboarding import WorkflowError


def source(store, *, faces=(1, 1), damaged=False):
    plays, game, cast, actor = ready(store, faces=faces, heat=1)
    target = ActorRef(kind="npc", entity="actual-defender")
    with store.transaction() as c:
        canon = state(game)
        canon.world = update(
            canon.world,
            npcs=(
                Npc(
                    id=target.entity,
                    name="Actual defender",
                    controller=3,
                    cell=(0, 0),
                    jobs=("guard",),
                    detail="Actual existing opponent",
                    revealed=True,
                    tags=(
                        WorldTag(
                            id="actual-shield-training",
                            label="Shield specialist",
                            giver_entity="actual-source-handler",
                        ),
                    ),
                ),
            ),
        )
        if damaged:
            canon = set_assets(
                canon,
                actor,
                tuple(x.model_copy(update={"damaged": True}) for x in assets(canon, actor)),
                event="actual-prior-damage",
            )
        game.event(c, 1, str(uuid4()), "synthetic.actual_combat_source", canon)
    change(cast, OTHER, "join", target)
    svc = BattleService(store)
    preview = svc.preview(PLAYER, 900)
    actual = next(x for x in preview["actors"] if x["ref"] == actor.model_dump(mode="json"))
    victim = next(x for x in preview["actors"] if x["ref"] == target.model_dump(mode="json"))
    chosen = actual["core_assets"][0]["id"]
    declared = Declaration.model_validate(
        dict(
            play="go_for_the_core",
            actor=actor,
            target=target,
            attacking_asset=chosen,
            actor_sha256=actual["sha256"],
            target_sha256=victim["sha256"],
            account="Actual opening against the source-defined opponent",
        )
    )
    offered = svc.propose(PLAYER, str(uuid4()), preview["revision"], 900, declared)
    prepared = PlayInput(
        play="go_for_the_core",
        heat=0,
        target_actor=target,
        attacking_asset=chosen,
        battle_context=offered["id"],
        context=declared.account,
        trigger_confirmed=True,
        piloting=True,
    )
    return plays, game, svc, actor, target, offered["id"], prepared


def confirm(svc, game, identity, *, defense=None, capability=False):
    return svc.confirm(
        ADMIN,
        str(uuid4()),
        state(game).revision,
        identity,
        opening=True,
        reach=True,
        outside_permission=True,
        indirect=False,
        evidence="Actual source opening and reach",
        defense=defense,
        core_capability_confirmed=capability,
    )


def roll(plays, game, actor, prepared):
    own = plays.preview(PLAYER, 900, actor)
    action = begin(plays, actor, own, prepared)
    worker, gateway = GameWorker(game), Gateway()
    tick(worker, gateway)
    for human in (ADMIN, PLAYER, OTHER):
        answer(game, human, "tag_window", options=("pass",))
    return action


def test_native_review_lists_only_actual_preexisting_npc_defense_and_low_survival(
    ledger, monkeypatch
):
    monkeypatch.setattr(m3_plays, "HEAT_IDS", (*m3_plays.HEAT_IDS, "go_for_the_core"))
    plays, game, svc, actor, target, identity, prepared = source(ledger)
    choices = svc.defenses(ADMIN, identity)
    actual = next(x for x in choices if x["value"]["source_id"] == "actual-shield-training")
    with pytest.raises(WorkflowError):
        svc.defenses(PLAYER, identity)

    async def run():
        interaction = current(1)
        await interaction.response.defer(ephemeral=True)
        await open_context(interaction, svc, identity)
        form = interaction.edit_original_response.call_args.kwargs["view"]
        assert isinstance(form, NativeForm) and "defense" in {x.key for x in form.fields}
        form.values.update(
            opening=("yes",),
            reach=("yes",),
            outside=("yes",),
            indirect=("no",),
            evidence="Actual opening and reach",
            defense=(actual["id"],),
            defense_account="The existing shield training protects against this actual strike",
            core_capability=("yes",),
        )
        await form.confirm.callback(current(1, 701))
        assert form.completed

    asyncio.run(run())
    action = roll(plays, game, actor, prepared)
    answer(
        game, OTHER, "battle_counter", flag=False, text="I explicitly decline my optional counter"
    )
    assert game.inspect(PLAYER, action)["state"] == "complete" and game.dice.calls == 1
    assert next(x for x in state(game).world.npcs if x.id == target.entity).alive


def test_high_core_actual_defense_does_not_negate_fixed_npc_death(ledger, monkeypatch):
    monkeypatch.setattr(m3_plays, "HEAT_IDS", (*m3_plays.HEAT_IDS, "go_for_the_core"))
    plays, game, svc, actor, target, identity, prepared = source(ledger, faces=(6, 6))
    choice = next(x for x in svc.defenses(ADMIN, identity) if x["value"]["kind"] == "capability")
    confirm(
        svc,
        game,
        identity,
        defense=Defense.model_validate(
            choice["value"] | {"account": "Actual source shield capability"}
        ),
    )
    action = roll(plays, game, actor, prepared)
    answer(game, OTHER, "battle_counter", flag=False, text="I decline an optional final counter")
    assert not next(x for x in state(game).world.npcs if x.id == target.entity).alive
    assert game.inspect(PLAYER, action)["state"] == "complete" and game.dice.calls == 1


def test_damaged_owned_core_asset_requires_actual_capability_before_any_roll(ledger, monkeypatch):
    monkeypatch.setattr(m3_plays, "HEAT_IDS", (*m3_plays.HEAT_IDS, "go_for_the_core"))
    plays, game, svc, actor, _, identity, prepared = source(ledger, faces=(4, 4), damaged=True)
    confirm(svc, game, identity)
    before = state(game)
    own = plays.preview(PLAYER, 900, actor)
    with pytest.raises(WorkflowError, match="damaged Asset"):
        begin(plays, actor, own, prepared)
    assert state(game) == before and game.dice.calls == 0
    # Review is immutable: a new genuine declaration carries the new factual capability.
    preview = svc.preview(PLAYER, 900)
    actual = next(x for x in preview["actors"] if x["ref"] == actor.model_dump(mode="json"))
    target = prepared.target_actor
    victim = next(x for x in preview["actors"] if x["ref"] == target.model_dump(mode="json"))
    declared = Declaration(
        play="go_for_the_core",
        actor=actor,
        target=target,
        attacking_asset=prepared.attacking_asset,
        actor_sha256=actual["sha256"],
        target_sha256=victim["sha256"],
        account="Actual damaged apparatus can still make this decisive strike",
    )
    offered = svc.propose(PLAYER, str(uuid4()), preview["revision"], 900, declared)
    confirm(svc, game, offered["id"], capability=True)
    result = roll(plays, game, actor, prepared.model_copy(update={"battle_context": offered["id"]}))
    assert game.inspect(PLAYER, result)["state"] == "complete" and game.dice.calls == 1
    assert assets(state(game), actor) == assets(before, actor)


def test_actual_handler_girl_collateral_resource_uses_real_held_asset_and_original_body(
    ledger, tmp_path, monkeypatch
):
    from test_battle_pipeline import table
    from test_enforcement_initiative import cast_target
    from test_handler_items import director, held
    from test_physical_operations import place

    import girlframe.services.m2_game as shared
    from girlframe.engine.m3_actor_bonds import current_ref, is_helpless
    from girlframe.services.m3_actors import ActorService
    from girlframe.services.m3_cast import CastService
    from girlframe.services.m3_items import prove_item
    from girlframe.services.m3_missions import MissionService

    game, worker, gateway, original, item = held(ledger, tmp_path, monkeypatch)
    target = director(game)
    cast_target(game, target)
    policy = ledger.policy
    ledger.policy = policy.model_copy(
        update=dict(
            owner_m3_rulings=policy.owner_m3_rulings.model_copy(
                update=dict(director_adjudicator="explicit_cast_director")
            )
        )
    )
    cast = CastService(ActorService(MissionService(ledger)))
    judge = ActorRef(kind="npc", entity="director")
    change(cast, OTHER, "join", judge)
    change(cast, OTHER, "adjudicate", judge)
    with ledger.transaction() as c:
        canon = place(state(game), 2)
        game.event(c, 2, str(uuid4()), "synthetic.actual_attacking_frame_position", canon)
    svc = BattleService(ledger)
    preview = svc.preview(PLAYER, 900)
    actor = current_ref(state(game), 2)
    attacker = next(x for x in preview["actors"] if x["ref"] == actor.model_dump(mode="json"))
    defender = next(x for x in preview["actors"] if x["ref"] == target.model_dump(mode="json"))
    declared = Declaration(
        play="all_out_assault",
        actor=actor,
        target=target,
        attacking_asset=attacker["assets"][0]["id"],
        target_asset=item.asset_id,
        actor_sha256=attacker["sha256"],
        target_sha256=defender["sha256"],
        account="Actual opposing carried equipment in an opening",
    )
    offered = svc.propose(PLAYER, str(uuid4()), preview["revision"], 900, declared)
    svc.confirm(
        ADMIN,
        str(uuid4()),
        state(game).revision,
        offered["id"],
        opening=True,
        reach=True,
        outside_permission=True,
        indirect=False,
        evidence=(
            "The actual original Handler body stands outside any Frame, "
            "and the owned carried apparatus is in reach"
        ),
        target_outside_frame=True,
    )
    monkeypatch.setattr(shared, "M3_HEAT_IDS", (*shared.M3_HEAT_IDS, "all_out_assault"))
    game.dice.faces = (4, 5)
    prepared = PlayInput(
        play="all_out_assault",
        heat=0,
        target_actor=target,
        attacking_asset=declared.attacking_asset,
        target_asset=declared.target_asset,
        battle_context=offered["id"],
        context=declared.account,
        piloting=True,
        trigger_confirmed=True,
    )
    action = game.begin(PLAYER, str(uuid4()), 900, state(game).sheets["2"].revision, prepared)[
        "action_id"
    ]
    tick(worker, gateway, 3)
    for human in (ADMIN, PLAYER, OTHER):
        answer(game, human, "tag_window", options=("pass",))
    table(game)
    after = state(game)
    assert game.inspect(PLAYER, action)["state"] == "complete" and game.dice.calls == 1
    assert is_helpless(after, original, actor)
    assert not after.handler_consequences and "1" not in after.sheets
    with ledger.engine.connect() as c:
        damaged = prove_item(c, game, after, item.id)
    assert __import__("json").loads(damaged.asset_json)["damaged"]
    assert damaged.source_owner == item.source_owner and damaged.asset_id == item.asset_id
