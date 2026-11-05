"""Real no-RNG Gorgon intent, actual owned response and source World mutations."""

from uuid import uuid4

import pytest
from test_battle_service import prepared
from test_cast_service import change
from test_ledger import ADMIN, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import answer, state, tick
from test_world import gorgon

from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_gorgon_play_state import Declaration
from girlframe.engine.m3_world import update
from girlframe.services.m3_actors import ActorService
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_gorgon_play import GorgonPlayService
from girlframe.services.m3_missions import MissionService


@pytest.fixture(autouse=True)
def candidate_source_gate(monkeypatch):
    """Only this candidate's three reviewed source IDs bypass production availability in tests."""
    from girlframe.engine.rules_registry import Registry

    actual = Registry.require_available

    def candidate(registry, identity):
        if identity in {
            "gorgon.gorgon.attack",
            "gorgon.gorgon.collateral-damage",
            "gorgon.gorgon.warp",
        }:
            return next(x for x in registry.entries if x.id == identity)
        return actual(registry, identity)

    monkeypatch.setattr(Registry, "require_available", candidate)


def gorgon_source(
    store,
    *,
    kind="attack",
    gorgon_class="erratic",
    target=None,
    damaged=False,
    failed=False,
    exposed=False,
    opposing=False,
    npc=False,
    sprites=False,
    harpy=False,
    director=False,
    civilian=False,
    approve_capability=True,
    opposing_class="benevolent",
):
    game, worker, gateway, _, _, _ = prepared(store)
    approval = store.policy.m3_approval
    store.policy = store.policy.model_copy(
        update=dict(
            m3_approval=approval.model_copy(update=dict(subsystems=approval.subsystems | {"world"}))
        )
    )
    with store.transaction() as c:
        canon = state(game)
        actual = gorgon(gorgon_class, "source-gorgon", revealed=True)
        if damaged:
            actual = actual.model_copy(
                update={
                    "assets": tuple(
                        x.model_copy(update={"damaged": True}) if i == 0 else x
                        for i, x in enumerate(actual.assets)
                    )
                }
            )
        actual = actual.model_copy(update={"exposed": exposed, "core_strike_failed": failed})
        canon.world = update(
            canon.world,
            gorgons=canon.world.gorgons
            + (actual,)
            + ((gorgon(opposing_class, "opposing-gorgon", revealed=True),) if opposing else ()),
        )
        if npc:
            from girlframe.engine.m3_world_state import Npc

            canon.world = update(
                canon.world,
                npcs=(
                    Npc(
                        id="actual-guard",
                        name="Actual source Guard",
                        jobs=("civilian",) if civilian else ("guard",),
                        detail="An actual living original NPC",
                        controller=3,
                        cell=(0, 0),
                        revealed=True,
                    ),
                ),
            )
        if harpy:
            from girlframe.engine.m3_world_state import AdversaryPilot, Asset

            canon.world = update(
                canon.world,
                pilots=(
                    AdversaryPilot(
                        id="actual-pitted-harpy",
                        name="Actual Harpy",
                        kind="harpy",
                        girl="MOCKINGBIRD",
                        frame="JANUS",
                        controller=2,
                        cell=(0, 0),
                        revealed=True,
                        assets=(
                            Asset(
                                id="actual-harpy-frame",
                                name="Actual Frame blade",
                                family="frame",
                                description="The original living Frame resource",
                            ),
                            Asset(
                                id="actual-harpy-girl",
                                name="Actual Girl claw",
                                family="girl",
                                description="The actual original Girl capability",
                            ),
                        ),
                    ),
                ),
            )
        if sprites:
            canon.world = update(
                canon.world,
                gorgons=canon.world.gorgons
                + (gorgon("sprite", "actual-interceptor", revealed=True),),
            )
        game.event(c, 1, str(uuid4()), "synthetic.actual_gorgon_setup", canon)
    if director:
        from test_ledger import OTHER

        from girlframe.engine.m3_world_state import Npc
        from girlframe.services.m3_npc_roles import NpcRoleService
        from girlframe.services.m3_world import WorldService

        roles = NpcRoleService(WorldService(MissionService(store)))
        offered = roles.offer(
            ADMIN,
            str(uuid4()),
            state(game).revision,
            Npc(
                id="actual-director",
                name="Actual source Director",
                jobs=("director",),
                detail="The actual accepted source Director",
                controller=3,
                cell=(0, 0),
                revealed=True,
            ),
        )
        roles.respond(OTHER, str(uuid4()), offered["id"], state(game).revision, "accept")
    cast = CastService(ActorService(MissionService(store)))
    actor = ActorRef(kind="gorgon", entity="source-gorgon")
    change(cast, ADMIN, "join", actor)
    if director:
        from test_ledger import OTHER

        direct_ref = ActorRef(kind="npc", entity="actual-director")
        change(cast, OTHER, "join", direct_ref)
        change(cast, OTHER, "adjudicate", direct_ref)
    if target == "1":
        from girlframe.engine.m3_handler_consequences import active_handler

        change(cast, ADMIN, "join", active_handler(state(game)))
    if npc:
        from test_ledger import OTHER

        change(cast, OTHER, "join", ActorRef(kind="npc", entity="actual-guard"))
    if opposing:
        change(cast, ADMIN, "join", ActorRef(kind="gorgon", entity="opposing-gorgon"))
    if harpy:
        from girlframe.engine.m3_harpy_defeat_state import NativeHarpyFacts
        from girlframe.engine.m3_void_state import HarpyIdentity
        from girlframe.services.m3_harpy_defeat import HarpyDefeatService

        ref = ActorRef(kind="external_pilot", entity="actual-pitted-harpy")
        service = HarpyDefeatService(store, game=game)
        proposal = service.propose_runtime(
            PLAYER,
            str(uuid4()),
            state(game).revision,
            NativeHarpyFacts(
                actor=ref,
                linked=True,
                girl_cell=(0, 0),
                frame_cell=(0, 0),
                heat=5,
                frame_shutdown=False,
                body_incapacitated=False,
                custody="free",
                identities=(HarpyIdentity(id="actual-free", name="Free"),),
                tags=(),
                account="Actual source Harpy resources and linked body",
                facts_confirmed=True,
            ),
        )
        service.review_setup(
            ADMIN,
            str(uuid4()),
            proposal["id"],
            state(game).revision,
            True,
            "Actual original facts confirmed",
        )
        change(cast, PLAYER, "join", ref)
    svc = GorgonPlayService(game)
    data = svc.preview(ADMIN, 900)
    actual = next(x for x in data["actors"] if x["ref"] == actor.model_dump(mode="json"))
    victim = next(x for x in data["actors"] if x["ref"]["entity"] == (target or "2"))
    declaration = Declaration(
        kind=kind,
        actor=actor,
        assets=(actual["assets"][0]["id"],) if kind != "warp" else (),
        actor_sha256=actual["source_sha256"],
        target=ActorRef.model_validate(victim["ref"]) if kind == "attack" else None,
        target_sha256=victim["source_sha256"] if kind == "attack" else None,
        account="Actual declared source effect at the present battlefield",
        reach_confirmed=True,
    )
    action = svc.begin(ADMIN, str(uuid4()), 900, data["revision"], declaration)["action_id"]
    tick(worker, gateway, 3)
    with store.engine.connect() as c:
        started = game.action(c, action)["data"]["gorgon_play"]["started"]
    if not started:
        game.roll(ADMIN, str(uuid4()), action)
    with store.engine.connect() as c:
        capability = any(x["kind"] == "gorgon_asset_capability" for x in game.pending(c, action))
    if capability and approve_capability:
        answer(
            game,
            ADMIN,
            "gorgon_asset_capability",
            flag=True,
            text="Actual source judge confirms this original attack capability and reach",
        )
    return game, worker, gateway, action, declaration


def test_actual_gorgon_attack_owned_damage_no_dice_and_real_replay(ledger):
    game, worker, gateway, action, _ = gorgon_source(ledger)
    assert game.dice.calls == 0
    answer(game, PLAYER, "gorgon_defend", options=("damage",), text="I take the actual blow")
    with ledger.engine.connect() as c:
        request = next(x for x in game.pending(c, action) if x["kind"] == "gorgon_damage_asset")
    data = game.decision(PLAYER, request["id"])
    asset = data["detail"]["assets"][0]["id"]
    answer(game, PLAYER, "gorgon_damage_asset", options=(asset,), text="Actual selected Asset hit")
    assert next(x for x in state(game).sheets["2"].assets if x.id == asset).damaged
    with ledger.engine.connect() as c:
        assert game.action(c, action)["state"] == "complete"
    assert game.dice.calls == 0
    tick(worker, gateway, 5)
    with ledger.engine.connect() as c:
        assert game.lock(c, 900)["state"] == "released"


def test_actual_directed_collateral_no_interrupt_and_concrete_structure_loss(ledger):
    game, _, _, action, _ = gorgon_source(ledger, kind="collateral", gorgon_class="directed")
    answer(
        game,
        ADMIN,
        "gorgon_collateral",
        options=("structure", "electronics"),
        fields={"structure": "base0"},
        text="Actual reached Base collapses; radio tower is fried",
    )
    after = state(game)
    assert next(x for x in after.world.locations if x.id == "base0").condition == "destroyed"
    assert any(x.get("kind") == "structure_destroyed_source" for x in after.facts)
    assert any(x.get("kind") == "gorgon_electronics_altered" for x in after.facts)
    with ledger.engine.connect() as c:
        assert game.action(c, action)["state"] == "complete"
        assert not game.pending(c, action)
    assert game.dice.calls == 0


@pytest.mark.parametrize("option", ["evolve", "protect", "escalate"])
def test_warp_actual_exposed_core_and_exact_selected_mutation(ledger, option):
    game, _, _, action, _ = gorgon_source(
        ledger, kind="warp", damaged=True, failed=True, exposed=True
    )
    before = next(x for x in state(game).world.gorgons if x.id == "source-gorgon")
    answer(
        game,
        ADMIN,
        "gorgon_warp",
        options=(option,),
        fields={"name": "Evolved real claw", "description": "Actual new physical capability"}
        if option == "evolve"
        else {},
        text="Actual printed Warp effect changes the situation",
    )
    after = next(x for x in state(game).world.gorgons if x.id == "source-gorgon")
    assert len(after.assets) == len(before.assets) + int(option == "evolve")
    assert after.exposed is (option != "protect")
    assert after.assets[0].damaged
    assert game.dice.calls == 0
    with ledger.engine.connect() as c:
        assert game.action(c, action)["state"] == "complete"


def test_actual_gorgon_contest_destroys_original_losing_asset(ledger):
    game, _, _, action, declaration = gorgon_source(ledger, target="opposing-gorgon", opposing=True)
    with ledger.engine.connect() as c:
        request = next(x for x in game.pending(c, action) if x["kind"] == "gorgon_contest_assets")
    asset = game.decision(ADMIN, request["id"])["detail"]["assets"][0]["id"]
    answer(game, ADMIN, "gorgon_contest_assets", options=(asset,), text="The real opposing claw")
    answer(
        game,
        ADMIN,
        "gorgon_contest_judge",
        options=("attacker",),
        fields={"asset": asset},
        text="Actual source Handler judgment: the declared attack tears the claw away",
    )
    target = next(x for x in state(game).world.gorgons if x.id == declaration.target.entity)
    assert asset not in {x.id for x in target.assets}
    assert asset in {x.id for x in target.destroyed_assets}
    assert game.dice.calls == 0


def actual_keep_response(game, worker, gateway, parent, *, enough):
    from test_m2_game import pass_tags

    from girlframe.engine.m2 import PlayInput

    game.dice.faces = (2, 3)
    child = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play="keep_your_head",
            heat=0,
            piloting=True,
            parent=parent,
            context="I actually avoid the Gorgon attack",
            trigger_confirmed=True,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    answer(game, PLAYER, "actor_keep", options=("in_control",))
    answer(
        game,
        ADMIN,
        "handler_keep",
        flag=enough,
        text="The actual response is enough" if enough else "The actual response is not enough",
    )
    return child


@pytest.mark.parametrize("enough", [True, False])
def test_actual_attack_response_child_uses_one_real_roll_and_actual_enough(ledger, enough):
    game, worker, gateway, action, _ = gorgon_source(ledger)
    before = state(game).sheets["2"].assets
    answer(game, PLAYER, "gorgon_defend", options=("play",), text="I make my actual own response")
    child = actual_keep_response(game, worker, gateway, action, enough=enough)
    with ledger.engine.connect() as c:
        assert game.action(c, child)["state"] == "complete"
        if enough:
            assert game.action(c, action)["state"] == "complete"
        else:
            assert game.action(c, action)["state"] != "complete"
            pending = game.pending(c, action)
            assert [x["kind"] for x in pending] == ["gorgon_damage_asset"]
    if not enough:
        answer(
            game,
            PLAYER,
            "gorgon_damage_asset",
            options=(before[0].id,),
            text="The unavoided blow damages this actual Asset",
        )
    assert game.dice.calls == 1
    with ledger.engine.connect() as c:
        assert game.action(c, action)["state"] == "complete"
    assert next(x for x in state(game).sheets["2"].assets if x.id == before[0].id).damaged is (
        not enough
    )


def test_genuine_saving_play_prevents_concrete_structure_collapse(ledger):
    import json

    game, worker, gateway, action, _ = gorgon_source(ledger, kind="collateral")
    answer(
        game,
        ADMIN,
        "gorgon_collateral",
        options=("structure",),
        fields={"structure": "base0"},
        text="This actual Gorgon threatens the Base",
    )
    actor = next(
        x.actor
        for x in state(game).scene_casts[0].roles
        if x.actor.kind == "pilot" and x.actor.entity == "2"
    )
    answer(
        game,
        ADMIN,
        "gorgon_interrupt",
        options=("play",),
        fields={"actor": json.dumps(actor.model_dump(mode="json"))},
        text="The present Girl gets her actual chance to interrupt",
    )
    actual_keep_response(game, worker, gateway, action, enough=True)
    assert next(x for x in state(game).world.locations if x.id == "base0").condition == "intact"
    assert game.dice.calls == 1
    with ledger.engine.connect() as c:
        assert game.action(c, action)["state"] == "complete"


@pytest.mark.parametrize("intercept", [True, False])
def test_literal_npc_attack_death_or_actual_sprite_shield_has_no_npc_hp(ledger, intercept):
    import json

    from girlframe.services.m3_sprite import SpriteService

    game, _, _, action, _ = gorgon_source(ledger, target="actual-guard", npc=True, sprites=True)
    with ledger.engine.connect() as c:
        request = next(x for x in game.pending(c, action) if x["kind"] == "battle_sprite_intercept")
    identity = json.loads(request["body_json"])["work_id"]
    service = SpriteService(ledger)
    data = service.get(ADMIN, identity)
    selected = data["options"][0]
    service.respond(
        ADMIN,
        str(uuid4()),
        identity,
        data["revision"],
        data["game_revision"],
        ActorRef.model_validate(selected["actor"]) if intercept else None,
        selected["asset"] if intercept else None,
        "The real Sprite takes the killing blow" if intercept else "I decline interception",
    )
    after = state(game)
    assert next(x for x in after.world.npcs if x.id == "actual-guard").alive is intercept
    assert next(x for x in after.world.gorgons if x.id == "actual-interceptor").assets[
        0
    ].damaged is (intercept)
    assert not any(x.get("kind") == "npc_asset_replacement" for x in after.facts)
    assert game.dice.calls == 0
    with ledger.engine.connect() as c:
        assert game.action(c, action)["state"] == "complete"


def test_contest_actual_sprite_redirect_preserves_losing_original_asset(ledger):
    import json

    from girlframe.services.m3_sprite import SpriteService

    game, _, _, action, declaration = gorgon_source(
        ledger, target="opposing-gorgon", opposing=True, sprites=True
    )
    with ledger.engine.connect() as c:
        request = next(x for x in game.pending(c, action) if x["kind"] == "gorgon_contest_assets")
    asset = game.decision(ADMIN, request["id"])["detail"]["assets"][0]["id"]
    answer(game, ADMIN, "gorgon_contest_assets", options=(asset,), text="Actual defending Asset")
    answer(
        game,
        ADMIN,
        "gorgon_contest_judge",
        options=("attacker",),
        fields={"asset": asset},
        text="Actual source contest losing Asset",
    )
    with ledger.engine.connect() as c:
        request = next(x for x in game.pending(c, action) if x["kind"] == "battle_sprite_intercept")
    service = SpriteService(ledger)
    identity = json.loads(request["body_json"])["work_id"]
    data = service.get(ADMIN, identity)
    selected = data["options"][0]
    service.respond(
        ADMIN,
        str(uuid4()),
        identity,
        data["revision"],
        data["game_revision"],
        ActorRef.model_validate(selected["actor"]),
        selected["asset"],
        "The real Sprite leaps between the two pitted bodies",
    )
    after = state(game)
    target = next(x for x in after.world.gorgons if x.id == declaration.target.entity)
    assert asset in {x.id for x in target.assets} and not target.destroyed_assets
    assert next(x for x in after.world.gorgons if x.id == "actual-interceptor").assets[0].damaged
    with ledger.engine.connect() as c:
        assert game.action(c, action)["state"] == "complete"


def test_real_harpy_losing_last_frame_asset_requires_actual_harpy_defeat(ledger):
    import json

    import sqlalchemy as sa

    from girlframe.database import tables as t
    from girlframe.services.m3_harpy_defeat import HarpyDefeatService

    game, worker, gateway, parent, declaration = gorgon_source(
        ledger, target="actual-pitted-harpy", harpy=True
    )
    original_pc = state(game).sheets["2"].model_dump_json()
    answer(
        game,
        PLAYER,
        "gorgon_contest_assets",
        options=("actual-harpy-frame",),
        text="The actual Harpy pits her original Frame blade",
    )
    answer(
        game,
        ADMIN,
        "gorgon_contest_judge",
        options=("attacker",),
        fields={"asset": "actual-harpy-frame"},
        text="The actual original Frame blade is destroyed",
    )
    after = state(game)
    assert after.sheets["2"].model_dump_json() == original_pc
    assert "actual-harpy-frame" not in {x.id for x in after.world.pilots[0].assets}
    assert any(x.get("kind") == "harpy_asset_destroyed" for x in after.facts)
    with ledger.engine.connect() as c:
        rows = list(
            c.execute(
                sa.select(t.m3["m3_required_work"]).where(
                    t.m3["m3_required_work"].c.kind == "harpy_defeat"
                )
            ).mappings()
        )
        assert len(rows) == 1 and game.action(c, parent)["state"] != "complete"
    source = json.loads(rows[0]["body_json"])
    assert source["owner"] == declaration.target.model_dump(mode="json")
    service = HarpyDefeatService(ledger, game=game)
    game.dice.faces = (3, 4)
    child = service.begin(PLAYER, str(uuid4()), rows[0]["id"], channel=900)["action_id"]
    tick(worker, gateway, 3)
    with ledger.engine.connect() as c:
        saved = game.action(c, child)
        assert saved["data"]["receipt"]["heat"] == 0
        assert game.dice.calls == 1

    from test_harpy_defeat import choose
    from test_ledger import OTHER

    for human in (ADMIN, PLAYER, OTHER):
        choose(service, game, human, "tag_window", options=("pass",))
    girl = next(
        x.actor
        for x in state(game).scene_casts[0].roles
        if x.actor.kind == "pilot" and x.actor.entity == "3"
    )
    choose(
        service,
        game,
        PLAYER,
        "harpy_defeat_select",
        options=("message",),
        fields={"girl": girl.token},
        text="The actual Harpy's final source message",
    )
    with ledger.engine.connect() as c:
        assert game.action(c, child)["state"] == "complete"
        assert game.action(c, parent)["state"] == "complete"
    assert state(game).native_harpies[-1].frame_cell is None
    assert state(game).sheets["2"].model_dump_json() == original_pc


def test_actual_core_response_kills_original_gorgon_and_stops_its_old_attack(ledger, monkeypatch):
    from test_m2_game import pass_tags

    import girlframe.services.m2_game as shared
    from girlframe.engine.m2 import PlayInput
    from girlframe.engine.m3_battle_state import Declaration as BattleDeclaration
    from girlframe.services.m3_battle import BattleService

    monkeypatch.setattr(shared, "M3_HEAT_IDS", (*shared.M3_HEAT_IDS, "go_for_the_core"))
    game, worker, gateway, parent, _ = gorgon_source(ledger, exposed=True)
    before = state(game).sheets["2"].assets
    answer(
        game, PLAYER, "gorgon_defend", options=("play",), text="I strike the actual exposed Core"
    )
    svc = BattleService(ledger)
    data = svc.preview(PLAYER, 900)
    own = next(x for x in data["actors"] if x["ref"]["kind"] == "pilot" and x["owned"])
    target = next(x for x in data["actors"] if x["ref"]["entity"] == "source-gorgon")
    declared = BattleDeclaration(
        play="go_for_the_core",
        actor=ActorRef.model_validate(own["ref"]),
        target=ActorRef.model_validate(target["ref"]),
        attacking_asset=own["assets"][0]["id"],
        actor_sha256=own["sha256"],
        target_sha256=target["sha256"],
        account="The actual original Gorgon exposed Core is open during its attack",
    )
    context = svc.propose(PLAYER, str(uuid4()), data["revision"], 900, declared, parent=parent)[
        "id"
    ]
    svc.confirm(
        ADMIN,
        str(uuid4()),
        state(game).revision,
        context,
        opening=True,
        reach=True,
        outside_permission=False,
        indirect=False,
        evidence="Actual original exposed Core opening",
    )
    game.dice.faces = (6, 6)
    child = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play="go_for_the_core",
            heat=0,
            piloting=True,
            parent=parent,
            target_actor=declared.target,
            attacking_asset=declared.attacking_asset,
            battle_context=context,
            context=declared.account,
            trigger_confirmed=True,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    after = state(game)
    assert not next(x for x in after.world.gorgons if x.id == "source-gorgon").alive
    assert after.sheets["2"].assets == before and game.dice.calls == 1
    with ledger.engine.connect() as c:
        assert game.action(c, child)["state"] == "complete"
        assert game.action(c, parent)["state"] == "complete"


def test_actual_handler_attack_uses_owned_replacement_not_npc_death_or_fake_asset(ledger):
    from girlframe.services.m3_handler_consequences import HandlerConsequenceService

    game, _, _, action, _ = gorgon_source(ledger, target="1")
    canon = state(game)
    record = canon.handler_consequences[-1]
    service = HandlerConsequenceService(ledger)
    service.respond(
        ADMIN,
        str(uuid4()),
        record.id,
        canon.revision,
        "injury",
        "The actual original Handler suffers the source injury",
    )
    after = state(game)
    assert after.handler_injuries[-1].description == (
        "The actual original Handler suffers the source injury"
    )
    assert not after.handler_archives and "1" not in after.sheets and game.dice.calls == 0
    with ledger.engine.connect() as c:
        assert game.action(c, action)["state"] == "complete"


@pytest.mark.parametrize("choice", ["injury", "death"])
def test_gorgon_director_target_uses_actual_owned_handler_rule_and_original_body(ledger, choice):
    import json

    from test_ledger import OTHER

    from girlframe.services.m3_battle_director import DirectorService

    game, _, _, action, _ = gorgon_source(ledger, target="actual-director", director=True)
    original_pc = state(game).sheets["3"].model_dump_json()
    with ledger.engine.connect() as c:
        row = next(x for x in game.pending(c, action) if x["kind"] == "battle_director_damage")
    identity = json.loads(row["body_json"])["work_id"]
    service = DirectorService(ledger)
    data = service.get(OTHER, identity)
    service.respond(
        OTHER,
        str(uuid4()),
        identity,
        data["revision"],
        choice,
        "The actual Director chooses her own source consequence",
    )
    after = state(game)
    actual = next(x for x in after.world.npcs if x.id == "actual-director")
    assert actual.alive is (choice != "death")
    assert after.sheets["3"].model_dump_json() == original_pc
    assert not after.handler_archives and game.dice.calls == 0
    with ledger.engine.connect() as c:
        assert game.action(c, action)["state"] == "complete"


@pytest.mark.parametrize("save", [True, False])
def test_actual_named_civilian_danger_requires_real_saving_play_or_actual_death(ledger, save):
    import json

    game, worker, gateway, parent, _ = gorgon_source(
        ledger, kind="collateral", npc=True, civilian=True
    )
    original_pc = state(game).sheets["3"].model_dump_json()
    answer(
        game,
        ADMIN,
        "gorgon_collateral",
        options=("civilians",),
        fields={"civilians": "actual-guard"},
        text="The actual civilian is in physical danger",
    )
    if save:
        actor = next(
            x.actor
            for x in state(game).scene_casts[0].roles
            if x.actor.kind == "pilot" and x.actor.entity == "2"
        )
        answer(
            game,
            ADMIN,
            "gorgon_interrupt",
            options=("play",),
            fields={"actor": json.dumps(actor.model_dump(mode="json"))},
            text="The actual Girl takes her saving opportunity",
        )
        actual_keep_response(game, worker, gateway, parent, enough=True)
    else:
        answer(
            game,
            ADMIN,
            "gorgon_interrupt",
            options=("allow",),
            text="No saving Play is made for this actual danger",
        )
    after = state(game)
    assert next(x for x in after.world.npcs if x.id == "actual-guard").alive is save
    assert after.sheets["3"].model_dump_json() == original_pc
    assert game.dice.calls == int(save)
    with ledger.engine.connect() as c:
        assert game.action(c, parent)["state"] == "complete"


def test_native_actual_owner_declines_damaged_capability_without_effect_and_replay(ledger):
    import asyncio

    from test_mission_ui import current

    from girlframe.discord_adapter.m2_forms import NativeForm
    from girlframe.discord_adapter.m3_gorgon_runtime import open_choice

    game, _, _, action, _ = gorgon_source(ledger, damaged=True, approve_capability=False)
    before = state(game).sheets["2"].model_dump_json()
    with ledger.engine.connect() as c:
        request = next(x for x in game.pending(c, action) if x["kind"] == "gorgon_asset_capability")

    async def run():
        caller = current(1)
        await caller.response.defer(ephemeral=True)
        await open_choice(caller, game, request["id"])
        form = caller.edit_original_response.call_args.kwargs["view"]
        assert isinstance(form, NativeForm) and not await form.interaction_check(current(2))
        form.values.update(
            options=("incapable",), account="This damaged claw cannot reach the Girl"
        )
        await form.confirm.callback(current(1, 994411))
        assert form.completed

    asyncio.run(run())
    assert state(game).sheets["2"].model_dump_json() == before and game.dice.calls == 0
    assert game.roll(ADMIN, str(uuid4()), action)["receipt"] is None
    with ledger.engine.connect() as c:
        assert game.action(c, action)["state"] == "complete"


def test_source_director_denies_nonlocal_collateral_reach_without_fabricated_travel(ledger):
    from test_ledger import OTHER

    game, _, _, action, _ = gorgon_source(ledger, kind="collateral", director=True)
    answer(
        game,
        ADMIN,
        "gorgon_collateral",
        options=("structure",),
        fields={"structure": "base1"},
        text="The declared source effect attempts to reach that distant Base",
    )
    with ledger.engine.connect() as c:
        row = next(x for x in game.pending(c, action) if x["kind"] == "gorgon_collateral_reach")
    assert row["actor_id"] == "3"
    answer(
        game,
        OTHER,
        "gorgon_collateral_reach",
        options=("unreachable",),
        text="The actual adjudicator confirms that capability cannot reach the Base",
    )
    after = state(game)
    assert next(x for x in after.world.locations if x.id == "base1").condition == "intact"
    assert next(x for x in after.world.gorgons if x.id == "source-gorgon").cell == (0, 0)
    with ledger.engine.connect() as c:
        assert game.action(c, action)["state"] == "complete"


def test_directed_contest_requires_actual_indirect_protection_fact_before_destruction(ledger):
    from girlframe.services.onboarding import WorkflowError

    game, _, _, parent, _ = gorgon_source(
        ledger, target="opposing-gorgon", opposing=True, opposing_class="directed"
    )
    asset = "opposing-gorgon:0"
    answer(game, ADMIN, "gorgon_contest_assets", options=(asset,), text="Actual guarding Asset")
    before = state(game).model_dump_json()
    with pytest.raises(WorkflowError, match="indirect"):
        answer(
            game,
            ADMIN,
            "gorgon_contest_judge",
            options=("attacker",),
            fields={"asset": asset},
            text="An ordinary direct attack cannot defeat the active protector",
        )
    assert state(game).model_dump_json() == before
    answer(
        game,
        ADMIN,
        "gorgon_contest_judge",
        options=("attacker",),
        fields={"asset": asset},
        flag=True,
        text="Actual judge confirms the indirect source capability bypasses the guard",
    )
    target = next(x for x in state(game).world.gorgons if x.id == "opposing-gorgon")
    assert asset in {x.id for x in target.destroyed_assets} and not target.exposed
    assert game.dice.calls == 0
    with ledger.engine.connect() as c:
        assert game.action(c, parent)["state"] == "complete"


def test_actual_girl_native_dropdown_accepts_blow_and_chooses_real_owned_asset(ledger):
    import asyncio

    from test_mission_ui import current

    from girlframe.discord_adapter.m2_forms import NativeForm
    from girlframe.discord_adapter.m3_gorgon_runtime import open_choice

    game, _, _, parent, _ = gorgon_source(ledger)

    async def run():
        with ledger.engine.connect() as c:
            decision = next(x for x in game.pending(c, parent) if x["kind"] == "gorgon_defend")
        caller = current(2)
        await caller.response.defer(ephemeral=True)
        await open_choice(caller, game, decision["id"])
        form = caller.edit_original_response.call_args.kwargs["view"]
        assert isinstance(form, NativeForm) and not await form.interaction_check(current(1))
        form.values.update(options=("damage",), account="I accept the actual incoming strike")
        await form.confirm.callback(current(2, 999201))
        assert form.completed
        with ledger.engine.connect() as c:
            next_row = next(
                x for x in game.pending(c, parent) if x["kind"] == "gorgon_damage_asset"
            )
        caller = current(2)
        await caller.response.defer(ephemeral=True)
        await open_choice(caller, game, next_row["id"])
        picker = caller.edit_original_response.call_args.kwargs["view"]
        asset = picker.fields[0].options[0][0]
        assert picker.fields[0].options[0][1] != asset
        picker.values.update(
            options=(asset,), account="The actual blow damages this selected Asset"
        )
        await picker.confirm.callback(current(2, 999202))
        assert picker.completed
        return asset

    selected = asyncio.run(run())
    assert next(x for x in state(game).sheets["2"].assets if x.id == selected).damaged
    with ledger.engine.connect() as c:
        assert game.action(c, parent)["state"] == "complete"
