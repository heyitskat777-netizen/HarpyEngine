"""Real shared dice → each actual human's choice → combat effects → restored chat."""

from uuid import uuid4

from test_battle_service import confirm, prepared
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import answer, pass_tags, state, tick

from girlframe.engine.m2 import PlayInput
from girlframe.engine.m3_battle_state import Declaration
from girlframe.engine.m3_handler_play_state import Effect
from girlframe.services.m3_handler_plays import HandlerPlayService


def rolled(store, monkeypatch, faces=(4, 5)):
    import girlframe.services.m2_game as shared

    monkeypatch.setattr(
        shared, "M3_HEAT_IDS", (*shared.M3_HEAT_IDS, "all_out_assault", "go_for_the_core")
    )
    game, worker, gateway, svc, data, declaration = prepared(store)
    game.dice.faces = faces
    identity = confirm(svc, game, data, declaration)
    result = game.begin(
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
            battle_context=identity,
            context=declaration.account,
            trigger_confirmed=True,
            piloting=True,
        ),
    )
    tick(worker, gateway, 3)
    pass_tags(game)
    return game, worker, gateway, result["action_id"], declaration


def table(game, *, vast=False):
    for human in (ADMIN, PLAYER, OTHER):
        answer(
            game,
            human,
            "battle_assault_table",
            flag=vast,
            text="My actual source judgment " + str(human.user_id),
        )


def test_actual_mid_allout_damages_declared_opposing_asset_once_then_restores_chat(
    ledger, monkeypatch
):
    game, worker, gateway, identity, declaration = rolled(ledger, monkeypatch)
    before = state(game)
    assert game.inspect(PLAYER, identity)["state"] != "complete"
    table(game)
    after = state(game)
    assert next(x for x in after.sheets["3"].assets if x.id == declaration.target_asset).damaged
    assert after.sheets["2"].assets == before.sheets["2"].assets
    assert game.inspect(PLAYER, identity)["state"] == "complete" and game.dice.calls == 1
    tick(worker, gateway, 5)
    with ledger.engine.connect() as c:
        assert game.lock(c, 900)["state"] == "released"


def test_only_unanimous_real_table_vast_advantage_prevents_actual_damage(ledger, monkeypatch):
    game, _, _, identity, declaration = rolled(ledger, monkeypatch)
    table(game, vast=True)
    assert not next(
        x for x in state(game).sheets["3"].assets if x.id == declaration.target_asset
    ).damaged
    assert game.inspect(PLAYER, identity)["state"] == "complete" and game.dice.calls == 1


def test_actual_high_allout_handler_chooses_and_actor_pays_owned_asset(ledger, monkeypatch):
    game, _, _, identity, declaration = rolled(ledger, monkeypatch, (6, 6))
    table(game)
    answer(game, ADMIN, "battle_handler", options=("damage_actor_asset",))
    owned = next(x for x in state(game).sheets["2"].assets if not x.damaged)
    answer(game, PLAYER, "battle_actor_damage", fields={"asset": owned.id})
    assert next(x for x in state(game).sheets["2"].assets if x.id == owned.id).damaged
    assert game.inspect(PLAYER, identity)["state"] == "complete" and game.dice.calls == 1


def test_actual_low_allout_defender_damage_then_real_mandatory_handler_play(ledger, monkeypatch):
    game, _, _, identity, _ = rolled(ledger, monkeypatch, (1, 1))
    owned = next(x for x in state(game).sheets["2"].assets if not x.damaged)
    answer(game, OTHER, "battle_low_damage", fields={"asset": owned.id})
    canon = state(game)
    grant = next(x for x in canon.handler_plays if x.source_action == identity)
    assert grant.chooser_actor is None and grant.chooser_controller == 1
    assert game.inspect(PLAYER, identity)["state"] != "complete"
    service = HandlerPlayService(ledger)
    service.submit(
        ADMIN,
        str(uuid4()),
        grant.id,
        canon.revision,
        "brief",
        Effect(kind="brief", account="Actual tactical information after the failed assault"),
    )
    assert game.inspect(PLAYER, identity)["state"] == "complete" and game.dice.calls == 1


def core(store, monkeypatch, faces, *, heat=0):
    import girlframe.services.m2_game as shared

    monkeypatch.setattr(
        shared, "M3_HEAT_IDS", (*shared.M3_HEAT_IDS, "all_out_assault", "go_for_the_core")
    )
    game, worker, gateway, svc, _, _ = prepared(store)
    with store.transaction() as c:
        canon = state(game)
        canon.sheets["2"].heat = heat
        game.event(c, 2, "actual-core-heat", "synthetic.state", canon)
    data = svc.preview(PLAYER, 900)
    actor = next(x for x in data["actors"] if x["ref"]["entity"] == "2")
    target = next(x for x in data["actors"] if x["ref"]["entity"] == "3")
    from girlframe.engine.m3_actor_state import ActorRef

    target_ref = ActorRef.model_validate_json(__import__("json").dumps(target["ref"]))
    svc.expose(
        OTHER,
        "actual-owned-core-opening",
        state(game).revision,
        target_ref,
        "I willingly expose this actual original Frame Core",
        willing=True,
    )
    data = svc.preview(PLAYER, 900)
    declaration = Declaration(
        play="go_for_the_core",
        actor=ActorRef.model_validate(actor["ref"]),
        target=target_ref,
        attacking_asset=actor["assets"][0]["id"],
        actor_sha256=actor["sha256"],
        target_sha256=target["sha256"],
        account="The actual decisive opening against the original Core",
    )
    identity = confirm(svc, game, data, declaration)
    game.dice.faces = faces
    action = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play="go_for_the_core",
            heat=heat,
            target_actor=target_ref,
            attacking_asset=declaration.attacking_asset,
            battle_context=identity,
            context=declaration.account,
            trigger_confirmed=True,
            piloting=True,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    return game, worker, gateway, action, target_ref


def test_real_mid_core_subtracts_actual_assets_and_ends_original_body_without_fake_handler_reply(
    ledger, monkeypatch
):
    game, worker, gateway, identity, target = core(ledger, monkeypatch, (6, 6))
    saved = game.inspect(PLAYER, identity)
    assert saved["receipt"]["pre_total"] == 8 and saved["state"] == "complete"
    canon = state(game)
    assert "3" not in canon.sheets
    assert canon.career_archives[-1].actor == target and canon.career_archives[-1].ending == "death"
    assert game.dice.calls == 1 and not game.choices(OTHER)
    tick(worker, gateway, 5)
    with ledger.engine.connect() as c:
        assert game.lock(c, 900)["state"] == "released"


def test_real_low_core_explicit_pass_has_no_forced_counter_or_damage(ledger, monkeypatch):
    game, _, _, identity, target = core(ledger, monkeypatch, (1, 1))
    before = state(game)
    answer(game, OTHER, "battle_counter", flag=False)
    assert state(game).sheets["3"].assets == before.sheets["3"].assets
    assert game.inspect(PLAYER, identity)["state"] == "complete" and game.dice.calls == 1


def test_real_high_core_owned_helpless_counter_then_source_original_asset_payment(
    ledger, monkeypatch
):
    game, _, _, identity, target = core(ledger, monkeypatch, (6, 6), heat=6)
    answer(game, OTHER, "battle_counter", options=("actor_helpless",))
    assert state(game).helpless_conditions[-1].foe == target
    asset = next(x for x in state(game).sheets["3"].assets if x.family == "girl" and not x.damaged)
    answer(game, OTHER, "battle_target_damage", fields={"asset": asset.id})
    assert next(x for x in state(game).sheets["3"].assets if x.id == asset.id).damaged
    assert game.inspect(PLAYER, identity)["state"] == "complete"


def test_real_core_target_controller_gets_scoped_final_handler_play_then_actual_death(
    ledger, monkeypatch
):
    game, _, _, identity, target = core(ledger, monkeypatch, (6, 6), heat=6)
    answer(game, OTHER, "battle_counter", options=("target_dies_with_handler_play",))
    canon = state(game)
    grant = next(x for x in canon.handler_plays if x.source_action == identity)
    assert grant.chooser_controller == 3 and grant.chooser_actor == target and grant.final_original
    HandlerPlayService(ledger).submit(
        OTHER,
        str(uuid4()),
        grant.id,
        canon.revision,
        "brief",
        Effect(kind="brief", account="The actual dying original Girl delivers her final warning"),
    )
    assert "3" not in state(game).sheets and state(game).career_archives[-1].actor == target
    assert game.inspect(PLAYER, identity)["state"] == "complete" and game.dice.calls == 1


def test_real_owned_counter_child_finishes_before_fixed_asset_cost_and_keeps_original_parent_held(
    ledger, monkeypatch
):
    game, worker, gateway, identity, _ = core(ledger, monkeypatch, (6, 6), heat=6)
    answer(game, OTHER, "battle_counter", options=("make_play_against_actor",))
    assert not any(x["kind"] == "battle_target_damage" for x in game.choices(OTHER))
    game.dice.faces = (4, 5)
    child = game.begin(
        OTHER,
        str(uuid4()),
        900,
        state(game).sheets["3"].revision,
        PlayInput(
            play="keep_your_head",
            heat=0,
            parent=identity,
            context="I hold my nerve against the actual original attacker",
            trigger_confirmed=True,
            piloting=True,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    answer(game, OTHER, "actor_keep", options=("in_control", "tough"), denied=("desperate",))
    assert game.inspect(PLAYER, identity)["state"] != "complete"
    answer(
        game,
        ADMIN,
        "handler_keep",
        flag=True,
        text="The real completed counter is enough in this actual exchange",
    )
    assert game.inspect(OTHER, child)["state"] == "complete" and game.dice.calls == 2
    assert any(x["kind"] == "battle_target_damage" for x in game.choices(OTHER))
    owned = next(x for x in state(game).sheets["3"].assets if x.family == "girl" and not x.damaged)
    answer(game, OTHER, "battle_target_damage", fields={"asset": owned.id})
    assert game.inspect(PLAYER, identity)["state"] == "complete"


def dormant_source(store, monkeypatch, *, close=False, prevoid_frame=False, girl=None):
    import sqlalchemy as sa
    from test_world import gorgon

    import girlframe.services.m2_game as shared
    from girlframe.database import tables as t
    from girlframe.engine.m3_actor_state import ActorRef
    from girlframe.services.m3_actors import ActorService
    from girlframe.services.m3_cast import CastService
    from girlframe.services.m3_missions import MissionService

    monkeypatch.setattr(
        shared, "M3_HEAT_IDS", (*shared.M3_HEAT_IDS, "all_out_assault", "go_for_the_core")
    )
    game, worker, gateway, svc, _, _ = prepared(store, girl=girl)
    approval = store.policy.m3_approval
    store.policy = store.policy.model_copy(
        update={
            "m3_approval": approval.model_copy(
                update={"subsystems": approval.subsystems | {"world"}}
            )
        }
    )
    with store.transaction() as c:
        canon = state(game)
        canon.world = canon.world.model_copy(
            update={
                "gorgons": canon.world.gorgons
                + (gorgon("dormant", "actual-dormant", revealed=True),)
            }
        )
        if prevoid_frame:
            frame_assets = [x for x in canon.sheets["2"].assets if x.family == "frame"]
            for asset in frame_assets[:-1]:
                asset.void = True
        game.event(c, 1, "actual-dormant-setup", "synthetic.actual_world", canon)
    casting = CastService(ActorService(MissionService(store)))
    cast = casting.view(ADMIN, 900)
    casting.change(
        ADMIN,
        "actual-dormant-cast",
        900,
        cast["game_revision"],
        cast["cast_revision"],
        "join",
        ActorRef(kind="gorgon", entity="actual-dormant"),
    )
    data = svc.preview(PLAYER, 900)
    actor = next(
        x for x in data["actors"] if x["ref"]["kind"] == "pilot" and x["ref"]["entity"] == "2"
    )
    target = next(
        x
        for x in data["actors"]
        if x["ref"]["kind"] == "gorgon" and x["ref"]["entity"] == "actual-dormant"
    )
    declaration = Declaration(
        play="all_out_assault",
        actor=ActorRef.model_validate(actor["ref"]),
        target=ActorRef.model_validate(target["ref"]),
        attacking_asset=actor["assets"][0]["id"],
        target_asset=target["assets"][0]["id"],
        actor_sha256=actor["sha256"],
        target_sha256=target["sha256"],
        account="Actual opening at the sleeping shell",
    )
    offered = svc.propose(PLAYER, str(uuid4()), data["revision"], 900, declaration)
    svc.confirm(
        ADMIN,
        str(uuid4()),
        state(game).revision,
        offered["id"],
        opening=True,
        reach=True,
        outside_permission=False,
        indirect=False,
        evidence="Actual blow forces the original Dormant awake",
        dormant_awakened=True,
        dormant_close=close,
    )
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
            battle_context=offered["id"],
            context=declaration.account,
            trigger_confirmed=True,
            piloting=True,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    with store.engine.connect() as c:
        work = c.scalar(
            sa.select(t.m3["m3_required_work"].c.id).where(
                t.m3["m3_required_work"].c.kind == "dormant_void"
            )
        )
    return game, worker, gateway, action, work


def test_real_dormant_attack_stages_exact_awakening_and_owned_cost_before_scene_can_release(
    ledger, monkeypatch
):
    from girlframe.services.m3_battle_dormant import DormantService

    game, _, _, action, work = dormant_source(ledger, monkeypatch, close=True)
    assert work and game.dice.calls == 1
    data = DormantService(ledger, game).get(PLAYER, work)
    assert data["state"] != "resolved" and game.inspect(PLAYER, action)["state"] != "complete"
    assert any(
        x.get("kind") == "dormant_awakening" and x.get("gorgon") == "actual-dormant"
        for x in state(game).facts
    )
