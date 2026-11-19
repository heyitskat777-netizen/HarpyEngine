"""Real no-RNG Gorgon intent, actual owned response and source World mutations."""

from uuid import uuid4

import pytest
from test_battle_service import prepared
from test_cast_service import change
from test_ledger import ADMIN, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Gateway, answer, state, tick
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
    """Enable the candidate source IDs for synthetic runtime verification."""
    from girlframe.engine.rules_registry import Registry

    actual = Registry.require_available

    def candidate(registry, identity):
        if identity in {
            "gorgon.gorgon.attack",
            "gorgon.gorgon.collateral-damage",
            "gorgon.gorgon.warp",
            "gorgon.gorgon.gorgons-fucking-girls",
            "gorgon.gorgon.gorgons-fucking-frames",
            "gorgon-type.sentinel.sentinel-type",
            "gorgon-type.sentinel.withdraw-into-your-shell",
            "gorgon-type.jackdaw.jackdaw-type",
            "gorgon-type.jackdaw.hallucinations",
            "gorgon-type.incubus.incubus-type",
            "gorgon-type.incubus.emotional-conditioning",
            "gorgon-type.mother.mother-type",
            "gorgon-type.mother.memetic-hazard",
            "gorgon-type.growth.growth-type",
            "gorgon-type.growth.grow-unreal",
            "gorgon-type.doppleganger.doppleganger-type",
            "gorgon-type.parasite.parasite-type",
            "gorgon-type.parasite.infect",
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
    actor_void=False,
    advance=True,
    types=("incubus",),
    begin=True,
    other_cell=(0, 0),
    tag=None,
    revealed=True,
    interference=None,
):
    game, worker, gateway, _, _, _ = prepared(store, other_cell=other_cell)
    approval = store.policy.m3_approval
    store.policy = store.policy.model_copy(
        update=dict(
            m3_approval=approval.model_copy(update=dict(subsystems=approval.subsystems | {"world"}))
        )
    )
    with store.transaction() as c:
        canon = state(game)
        actual = gorgon(gorgon_class, "source-gorgon", revealed=revealed, types=types)
        if damaged:
            actual = actual.model_copy(
                update={
                    "assets": tuple(
                        x.model_copy(update={"damaged": True}) if i == 0 else x
                        for i, x in enumerate(actual.assets)
                    )
                }
            )
        if actor_void:
            actual = actual.model_copy(
                update={"assets": tuple(x.model_copy(update={"void": True}) for x in actual.assets)}
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
    targeted = kind in (
        "attack",
        "incubus_inflict",
        "mother_mutation",
        "doppleganger_bond",
        "parasite_hitch",
        "intimate_contact",
        "intimate_frame_contact",
        "sentinel_withdraw",
    )
    declaration = Declaration(
        kind=kind,
        actor=actor,
        assets=(actual["assets"][0]["id"],) if kind in ("attack", "collateral") else (),
        actor_sha256=actual["source_sha256"],
        target=ActorRef.model_validate(victim["ref"]) if targeted else None,
        target_sha256=victim["source_sha256"] if targeted else None,
        account="Actual declared source effect at the present battlefield",
        reach_confirmed=True,
        tag=tag,
        interference=interference,
    )
    if not begin:
        return game, worker, gateway, None, declaration
    action = svc.begin(ADMIN, str(uuid4()), 900, data["revision"], declaration)["action_id"]
    if advance:
        tick(worker, gateway, 3)
        with store.engine.connect() as c:
            started = game.action(c, action)["data"]["gorgon_play"]["started"]
        if not started:
            game.roll(ADMIN, str(uuid4()), action)
        with store.engine.connect() as c:
            capability = any(
                x["kind"] == "gorgon_asset_capability" for x in game.pending(c, action)
            )
        if capability and approve_capability:
            answer(
                game,
                ADMIN,
                "gorgon_asset_capability",
                flag=True,
                text="Actual source judge confirms this original attack capability and reach",
            )
    return game, worker, gateway, action, declaration


def test_sentinel_native_corruption_preserves_position_owner_privacy_and_restart(ledger):
    import asyncio

    from test_ledger import OTHER
    from test_mission_ui import current

    from girlframe.delivery.m2_worker import GameWorker
    from girlframe.discord_adapter.m2_forms import NativeForm
    from girlframe.discord_adapter.m3_gorgon_play import open_gorgon_play
    from girlframe.engine.m2 import PlayInput
    from girlframe.services.m2_game import GameService
    from girlframe.services.m3_world import WorldService
    from girlframe.services.onboarding import WorkflowError

    game, _, gateway, _, declaration = gorgon_source(
        ledger, kind="corrupt", types=("sentinel",), begin=False, other_cell=(2, 0)
    )
    service = GorgonPlayService(game)
    revision = state(game).revision
    assert "corrupt" not in service.preview(PLAYER, 900)["plays"]
    with pytest.raises(WorkflowError, match="actual owned"):
        service.begin(PLAYER, "wrong-owner", 900, revision, declaration)
    with pytest.raises(WorkflowError, match="STALE_GORGON_PLAY"):
        service.begin(ADMIN, "stale", 900, revision - 1, declaration)

    async def native_begin():
        owner = current(1)
        owner.channel_id = 900
        await owner.response.defer(ephemeral=True)
        await open_gorgon_play(owner, game)
        form = owner.edit_original_response.call_args.kwargs["view"]
        assert isinstance(form, NativeForm)
        assert not await form.interaction_check(current(2))
        form.values.update(actor=(declaration.actor.token,), play=("corrupt",))
        select = current(1, 999300)
        await select.response.defer(ephemeral=True)
        await form.confirm.callback(select)
        confirm = select.edit_original_response.call_args.kwargs["view"]
        assert isinstance(confirm, NativeForm)
        confirm.values.update(account=declaration.account, reach=("confirmed",))
        await confirm.confirm.callback(current(1, 999301))
        assert confirm.completed

    asyncio.run(native_begin())
    replay = service.begin(ADMIN, "999301", 900, revision, declaration)
    action = replay["action_id"]
    assert not state(game).world.corrupted_cells
    ledger.safety(PLAYER, "pause-before-corruption", ledger.status(PLAYER)["revision"], pause=True)
    tick(GameWorker(game), gateway, 3)
    assert not state(game).world.corrupted_cells
    ledger.safety(PLAYER, "resume-corruption", ledger.status(PLAYER)["revision"], pause=False)

    restarted = GameService(ledger, dice=game.dice)
    tick(GameWorker(restarted), gateway, 5)
    if not state(restarted).world.corrupted_cells:
        restarted.roll(ADMIN, "resume-original", action)
        tick(GameWorker(restarted), gateway, 5)
    (terrain,) = state(restarted).world.corrupted_cells
    assert (terrain.cell, terrain.sentinel, terrain.action) == ((0, 0), "source-gorgon", action)
    with ledger.engine.connect() as connection:
        source = restarted.action(connection, action)
        assert source["state"] == "complete"
        assert terrain.event == source["data"]["gorgon_play"]["advance_event"]
        assert terrain.scene == source["scene_id"]
        assert restarted.lock(connection, 900)["state"] == "released"
    with pytest.raises(WorkflowError, match="clear map square"):
        service.begin(ADMIN, "repeated-corruption", 900, state(restarted).revision, declaration)
    assert state(restarted).world.corrupted_cells == (terrain,)

    world = WorldService(MissionService(ledger))
    assert "corrupted_cells" not in world.get(PLAYER)["world"]
    assert "corrupted_cells" not in world.get(ADMIN, private=True)["world"]
    cast = CastService(ActorService(MissionService(ledger)))
    change(cast, ADMIN, "withdraw", declaration.actor)
    request = PlayInput(
        play="check_sensors", context="Synthetic current terrain", trigger_confirmed=True, heat=0
    )
    with pytest.raises(WorkflowError, match="Corrupted terrain blocks Check Your Sensors"):
        restarted.begin(
            PLAYER, "blocked-sensors", 900, state(restarted).sheets["2"].revision, request
        )
    unaffected = restarted.begin(
        OTHER, "unaffected-sensors", 900, state(restarted).sheets["3"].revision, request
    )
    assert unaffected["action_id"] != action and game.dice.calls == 0


@pytest.mark.parametrize("leave_range", (False, True))
def test_sentinel_terrain_is_one_real_native_tag_without_character_sheet_mutation(
    ledger, leave_range
):
    import asyncio

    from test_ledger import OTHER
    from test_mission_ui import current

    from girlframe.discord_adapter.m2_ui import open_choice
    from girlframe.engine.m2 import ChoiceAnswer, PlayInput
    from girlframe.engine.m3_actor_bonds import current_ref
    from girlframe.services.m2_game import GameService
    from girlframe.services.m3_movement import MovementService
    from girlframe.services.m3_sentinel import TERRAIN_TAG
    from girlframe.services.onboarding import WorkflowError

    game, worker, gateway, source, declaration = gorgon_source(
        ledger, kind="corrupt", types=("sentinel",)
    )
    tick(worker, gateway, 5)
    assert game.inspect(ADMIN, source)["state"] == "complete"
    terrain = state(game).world.corrupted_cells[0]
    change(CastService(ActorService(MissionService(ledger))), ADMIN, "withdraw", declaration.actor)
    if leave_range:
        canon = state(game)
        MovementService(game).move(
            OTHER,
            "leave-actual-square",
            canon.revision,
            900,
            current_ref(canon, OTHER.user_id),
            (1, 0),
            frame=True,
            account="I pilot my own Frame out of the changed square.",
        )
    game.dice.faces = (4, 4)
    request = PlayInput(
        play="keep_your_head",
        context="I hold steady in the changed terrain",
        trigger_confirmed=True,
        heat=0,
    )
    original = state(game).sheets["2"].tags
    action = game.begin(PLAYER, "terrain-keep", 900, state(game).sheets["2"].revision, request)[
        "action_id"
    ]
    tick(worker, gateway, 3)
    mark = next(x for x in game.choices(OTHER) if x["kind"] == "tag_window")
    tag = TERRAIN_TAG + terrain.event
    assert (tag in {x["id"] for x in game.decision(OTHER, mark["id"])["tags"]}) != leave_range
    own = next(x for x in game.choices(PLAYER) if x["kind"] == "tag_window")
    assert tag not in {x["id"] for x in game.decision(PLAYER, own["id"])["tags"]}
    gm_choice = next(x for x in game.choices(ADMIN) if x["kind"] == "tag_window")
    assert tag not in {x["id"] for x in game.decision(ADMIN, gm_choice["id"])["tags"]}
    invalid = ChoiceAnswer(
        options=("tag",),
        denied=(TERRAIN_TAG + "forged",),
        number=-1,
        text="The ground is unstable.",
    )
    with pytest.raises(WorkflowError, match="actual witnessed Corrupted terrain"):
        game.respond(OTHER, "fake-terrain", mark["id"], mark["revision"], invalid)
    if leave_range:
        before = game.inspect(PLAYER, action)["receipt"]
        with pytest.raises(WorkflowError, match="actual witnessed Corrupted terrain"):
            game.respond(
                OTHER,
                "remote-terrain-proposal",
                mark["id"],
                mark["revision"],
                invalid.model_copy(update={"denied": (tag,)}),
            )
        answer(game, ADMIN, "tag_window", options=("pass",))
        answer(game, PLAYER, "tag_window", options=("pass",))
        answer(game, OTHER, "tag_window", options=("pass",))
        keeping = next(x for x in game.choices(PLAYER) if x["kind"] == "actor_keep")
        assert game.decision(PLAYER, keeping["id"])["result"]["tier"] == "mid"
        assert game.inspect(PLAYER, action)["receipt"] == before and game.dice.calls == 1
        assert not any(x["kind"] == "sentinel_terrain_mark" for x in state(game).facts)
        return
    answer(game, ADMIN, "tag_window", options=("pass",))
    answer(game, PLAYER, "tag_window", options=("pass",))

    async def submit():
        click = current(OTHER.user_id, 78880)
        click.channel_id = 900
        await click.response.defer(ephemeral=True)
        await open_choice(click, game, mark["id"])
        form = click.edit_original_response.call_args.kwargs["view"]
        assert not await form.interaction_check(current(PLAYER.user_id))
        form.values.update(
            options=("tag",), denied=(tag,), number=("-1",), text="The ground is unstable."
        )
        sent = current(OTHER.user_id, 78881)
        await form.confirm.callback(sent)
        assert form.completed, sent.followup.send.call_args

    asyncio.run(submit())
    keeping = next(x for x in game.choices(PLAYER) if x["kind"] == "actor_keep")
    result = game.decision(PLAYER, keeping["id"])["result"]
    assert result["tier"] == "low"
    assert state(game).sheets["2"].tags == original
    assert len([x for x in state(game).facts if x["kind"] == "sentinel_terrain_mark"]) == 1
    answer(game, PLAYER, "actor_keep", options=("in_control",))
    answer(game, ADMIN, "handler_keep", flag=True, text="The actual GM rules the outcome.")
    assert game.inspect(PLAYER, action)["state"] == "complete"
    tick(worker, gateway, 5)
    ledger.engine.dispose()
    restarted = GameService(ledger, dice=game.dice)
    restarted.begin(PLAYER, "repeat-terrain-keep", 900, state(game).sheets["2"].revision, request)
    tick(type(worker)(restarted), gateway, 3)
    mark = next(x for x in restarted.choices(OTHER) if x["kind"] == "tag_window")
    assert tag not in {x["id"] for x in restarted.decision(OTHER, mark["id"])["tags"]}
    with pytest.raises(WorkflowError, match="actual witnessed Corrupted terrain"):
        restarted.respond(
            OTHER,
            "repeat-terrain",
            mark["id"],
            mark["revision"],
            invalid.model_copy(update={"denied": (tag,)}),
        )


def test_jackdaw_native_jamming_blocks_orders_until_original_girl_leaves_range(ledger):
    import asyncio
    import json

    from test_ledger import OTHER
    from test_mission_ui import current

    from girlframe.discord_adapter.m3_gorgon_play import open_gorgon_play
    from girlframe.engine.m3_actor_bonds import current_ref
    from girlframe.engine.m3_jackdaw import Range, ranges
    from girlframe.services.m2_game import GameService
    from girlframe.services.m3_movement import MovementService
    from girlframe.services.onboarding import WorkflowError

    game, worker, gateway, _, declaration = gorgon_source(
        ledger,
        kind="jackdaw_jam",
        types=("jackdaw",),
        begin=False,
        other_cell=(2, 0),
        interference=Range(cells=((0, 0), (1, 0))),
    )
    service = GorgonPlayService(game)
    revision = state(game).revision
    assert "jackdaw_jam" not in service.preview(PLAYER, 900)["plays"]
    with pytest.raises(WorkflowError, match="actual owned"):
        service.begin(PLAYER, "wrong-caller", 900, revision, declaration)
    with pytest.raises(WorkflowError, match="STALE_GORGON_PLAY"):
        service.begin(ADMIN, "stale-jackdaw", 900, revision - 1, declaration)
    forged = declaration.model_copy(update=dict(interference=Range(cells=((0, 0), (80, 80)))))
    with pytest.raises(WorkflowError, match="in-range map squares"):
        service.begin(ADMIN, "forged-reach", 900, revision, forged)

    async def native():
        owner = current(ADMIN.user_id, 78900)
        owner.channel_id = 900
        await owner.response.defer(ephemeral=True)
        await open_gorgon_play(owner, game)
        form = owner.edit_original_response.call_args.kwargs["view"]
        form.values.update(actor=(declaration.actor.token,), play=("jackdaw_jam",))
        select = current(ADMIN.user_id, 78901)
        await select.response.defer(ephemeral=True)
        await form.confirm.callback(select)
        confirm = select.edit_original_response.call_args.kwargs["view"]
        confirm.values.update(
            account=declaration.account, reach=("confirmed",), audible_range="0,0\n1,0"
        )
        sent = current(ADMIN.user_id, 78902)
        await confirm.confirm.callback(sent)
        assert confirm.completed, sent.followup.send.call_args

    asyncio.run(native())
    action = service.begin(ADMIN, "78902", 900, revision, declaration)["action_id"]
    ledger.safety(PLAYER, "pause-jackdaw", ledger.status(PLAYER)["revision"], pause=True)
    tick(worker, gateway, 3)
    assert not ranges(state(game))
    ledger.safety(PLAYER, "resume-jackdaw", ledger.status(PLAYER)["revision"], pause=False)
    tick(worker, gateway, 5)
    with ledger.engine.connect() as c:
        started = game.action(c, action)["data"]["gorgon_play"]["started"]
    if not started:
        game.roll(ADMIN, "advance-original-jackdaw", action)
    assert not ranges(state(game))
    answer(
        game,
        ADMIN,
        "gorgon_asset_capability",
        flag=True,
        text="The actual human referee verifies audible reach across these two squares.",
    )
    (interference,) = ranges(state(game))
    assert interference.action == action and interference.range.cells == ((0, 0), (1, 0))
    assert game.inspect(ADMIN, action)["state"] == "complete" and game.dice.calls == 0
    tick(worker, gateway, 5)
    change(CastService(ActorService(MissionService(ledger))), ADMIN, "withdraw", declaration.actor)
    with ledger.transaction() as c:
        canon = state(game)
        canon.facts.append(
            dict(
                kind="ordinary_handler_movement",
                actor=current_ref(canon, 1).model_dump_json(),
                cell=json.dumps((0, 0)),
                event="synthetic-position",
            )
        )
        game.event(
            c, ADMIN.user_id, "handler-present", "synthetic.original_handler_position", canon
        )
    ledger.engine.dispose()
    restarted = GameService(ledger, dice=game.dice)
    with pytest.raises(WorkflowError, match="No verified communication route"):
        restarted.issue_order(ADMIN, "jam-even-in-same-square", 900, PLAYER.user_id, "Hold here.")
    canon = state(restarted)
    MovementService(restarted).move(
        PLAYER,
        "leave-original-jackdaw-range",
        canon.revision,
        900,
        current_ref(canon, PLAYER.user_id),
        (2, 0),
        frame=True,
        account="I drive my Frame beyond the original audible range.",
    )
    order = restarted.issue_order(
        ADMIN, "receive-after-withdrawal", 900, PLAYER.user_id, "Hold here."
    )
    assert order["order_id"] and game.dice.calls == 0
    assert ranges(state(restarted)) == (interference,)
    assert not any(x["kind"] == "order_response" for x in restarted.choices(OTHER))


def test_jackdaw_catatonia_holds_original_non_pilot_without_blocking_girls(ledger):
    import asyncio

    from test_ledger import OTHER
    from test_mission_ui import current

    from girlframe.discord_adapter.m3_gorgon_play import open_gorgon_play
    from girlframe.engine.m3_actor_bonds import current_ref
    from girlframe.engine.m3_jackdaw import Range, ranges
    from girlframe.services.m3_movement import MovementService
    from girlframe.services.m3_sentinel import require_communication
    from girlframe.services.onboarding import WorkflowError

    game, worker, gateway, _, declaration = gorgon_source(
        ledger,
        kind="jackdaw_catatonia",
        types=("jackdaw",),
        npc=True,
        begin=False,
        interference=Range(cells=((0, 0),)),
    )
    npc = ActorRef(kind="npc", entity="actual-guard")
    original = state(game)
    player = current_ref(original, PLAYER.user_id)
    other = current_ref(original, OTHER.user_id)

    async def native():
        owner = current(ADMIN.user_id, 79900)
        owner.channel_id = 900
        await owner.response.defer(ephemeral=True)
        await open_gorgon_play(owner, game)
        form = owner.edit_original_response.call_args.kwargs["view"]
        form.values.update(actor=(declaration.actor.token,), play=("jackdaw_catatonia",))
        chosen = current(ADMIN.user_id, 79901)
        await chosen.response.defer(ephemeral=True)
        await form.confirm.callback(chosen)
        details = chosen.edit_original_response.call_args.kwargs["view"]
        details.values.update(
            account=declaration.account, reach=("confirmed",), audible_range="0,0"
        )
        sent = current(ADMIN.user_id, 79902)
        await details.confirm.callback(sent)
        assert details.completed, sent.followup.send.call_args

    asyncio.run(native())
    action = GorgonPlayService(game).begin(ADMIN, "79902", 900, original.revision, declaration)
    tick(worker, gateway, 5)
    if not ranges(state(game)):
        game.roll(ADMIN, "advance-catatonia", action["action_id"])
        tick(worker, gateway, 5)
    (effect,) = ranges(state(game))
    assert effect.victims == (npc,) and effect.effect == "catatonia"
    assert game.inspect(ADMIN, action["action_id"])["state"] == "complete"
    assert original.sheets == state(game).sheets and game.dice.calls == 0
    ledger.engine.dispose()
    with ledger.engine.connect() as c:
        with pytest.raises(WorkflowError, match="No verified communication route"):
            require_communication(c, ledger.campaign_id, state(game), npc, (player,))
        require_communication(c, ledger.campaign_id, state(game), other, (player,))
    movement = MovementService(game)
    with pytest.raises(WorkflowError, match="actual catatonia"):
        movement.move(
            OTHER,
            "blocked-guard",
            state(game).revision,
            900,
            npc,
            (1, 0),
            account="The actual guard tries to move.",
        )
    movement.move(
        ADMIN,
        "source-moves-out",
        state(game).revision,
        900,
        declaration.actor,
        (1, 0),
        account="The actual Jackdaw leaves its declared source square.",
    )
    promoted = movement.move(
        OTHER,
        "released-guard",
        state(game).revision,
        900,
        npc,
        (1, 0),
        account="The actual guard regains awareness and moves.",
    )
    assert promoted["destination"] == [1, 0] and ranges(state(game)) == (effect,)


def test_sentinel_prevents_orders_across_corrupted_square_boundary(ledger):
    import json

    from test_ledger import OTHER

    from girlframe.engine.m3_actor_bonds import current_ref
    from girlframe.services.onboarding import WorkflowError

    game, worker, gateway, action, declaration = gorgon_source(
        ledger,
        kind="corrupt",
        types=("sentinel",),
        other_cell=(2, 0),
    )
    tick(worker, gateway, 6)
    assert game.inspect(ADMIN, action)["state"] == "complete"
    cast = CastService(ActorService(MissionService(ledger)))
    change(cast, ADMIN, "withdraw", declaration.actor)

    def place_handler(cell):
        with ledger.transaction() as c:
            saved = state(game)
            saved.facts.append(
                dict(
                    kind="ordinary_handler_movement",
                    actor=current_ref(saved, 1).model_dump_json(),
                    cell=json.dumps(cell),
                    event="synthetic-source-position",
                )
            )
            game.event(c, 1, str(uuid4()), "synthetic.actual_handler_position", saved)

    place_handler((2, 0))
    with pytest.raises(
        WorkflowError,
        match="No verified communication route",
    ):
        game.issue_order(ADMIN, "blocked-into", 900, 2, "Move to the original waypoint.")
    place_handler((0, 0))
    with pytest.raises(
        WorkflowError,
        match="No verified communication route",
    ):
        game.issue_order(ADMIN, "blocked-out-of", 900, OTHER.user_id, "Move to the waypoint.")
    with ledger.engine.connect() as c:
        lock = game.lock(c, 900)
        assert lock is None or lock["state"] == "released"
    # Neither endpoint crosses the boundary in this actual in-person Order.
    local = game.issue_order(ADMIN, "same-square", 900, 2, "Hold your position here.")
    assert local["order_id"] and game.dice.calls == 0


@pytest.mark.parametrize(
    "kind,gorgon_type,selection,label,npc",
    [
        ("incubus_inflict", "incubus", "dysphoria", "Dysphoric", False),
        ("mother_mutation", "mother", "branch", "Branching flesh", True),
        ("doppleganger_bond", "doppleganger", "Familiar voice", "Familiar voice", False),
        ("doppleganger_bond", "doppleganger", "Uncannily kind", "Uncannily kind", True),
    ],
)
def test_native_gorgon_type_tags_create_only_the_actual_scoped_effect(
    ledger, kind, gorgon_type, selection, label, npc
):
    import asyncio

    from test_ledger import OTHER
    from test_mission_ui import current

    from girlframe.delivery.m2_worker import GameWorker
    from girlframe.discord_adapter.m2_forms import NativeForm
    from girlframe.discord_adapter.m3_gorgon_play import open_gorgon_play
    from girlframe.services.m2_game import GameService
    from girlframe.services.m3_world import WorldService
    from girlframe.services.onboarding import WorkflowError

    game, _, gateway, _, declaration = gorgon_source(
        ledger,
        kind=kind,
        types=(gorgon_type,),
        tag=selection,
        begin=False,
        npc=npc,
        target="actual-guard" if npc else "2",
        other_cell=(2, 0),
    )
    service = GorgonPlayService(game)
    preview = service.preview(ADMIN, 900)
    target = declaration.target
    caster = declaration.actor.token
    assert kind in preview["plays"]
    assert target.token in preview["typed_targets"][caster][kind]
    assert kind not in service.preview(PLAYER, 900)["plays"]
    remote = next(x for x in preview["actors"] if x["ref"]["entity"] == "3")
    invalid = declaration.model_copy(
        update=dict(
            target=ActorRef.model_validate(remote["ref"]), target_sha256=remote["source_sha256"]
        )
    )
    with pytest.raises(WorkflowError, match="actual local reach"):
        service.begin(ADMIN, "wrong-location", 900, preview["revision"], invalid)
    with pytest.raises(WorkflowError, match="actual owned"):
        service.begin(PLAYER, "wrong-controller", 900, preview["revision"], declaration)

    if kind == "doppleganger_bond" and npc:
        from girlframe.engine.m3_actor_bonds import set_depth

        with ledger.transaction() as connection:
            canon = set_depth(
                state(game), declaration.actor, declaration.target, 2, "original-bond"
            )
            game.event(connection, 1, "seed-intense", "synthetic.prior_bond", canon)
        preview = service.preview(ADMIN, 900)
        actor_data = next(x for x in preview["actors"] if x["token"] == caster)
        target_data = next(x for x in preview["actors"] if x["token"] == target.token)
        declaration = declaration.model_copy(
            update=dict(
                actor_sha256=actor_data["source_sha256"],
                target_sha256=target_data["source_sha256"],
            )
        )

    async def declare():
        owner = current(1)
        owner.channel_id = 900
        await owner.response.defer(ephemeral=True)
        await open_gorgon_play(owner, game)
        form = owner.edit_original_response.call_args.kwargs["view"]
        assert isinstance(form, NativeForm)
        form.values.update(actor=(caster,), play=(kind,))
        select = current(1, 999400)
        await select.response.defer(ephemeral=True)
        await form.confirm.callback(select)
        confirm = select.edit_original_response.call_args.kwargs["view"]
        assert isinstance(confirm, NativeForm)
        assert remote["token"] not in dict(confirm.fields[0].options)
        confirm.values.update(
            target=(target.token,),
            account=declaration.account,
            reach=("confirmed",),
        )
        if kind == "doppleganger_bond":
            confirm.values["bond_tag"] = selection
        else:
            confirm.values["tag"] = (selection,)
        await confirm.confirm.callback(current(1, 999401))
        assert confirm.completed

    asyncio.run(declare())
    action = service.begin(ADMIN, "999401", 900, preview["revision"], declaration)["action_id"]
    before = state(game)
    restarted = GameService(ledger, dice=game.dice)
    tick(GameWorker(restarted), gateway, 5)
    if not restarted.inspect(ADMIN, action)["result"]:
        restarted.roll(ADMIN, "resume-type-tag", action)
        tick(GameWorker(restarted), gateway, 5)
    after = state(restarted)
    received = restarted.inspect(OTHER if npc else PLAYER, action)["result"]
    assert received["tag_label"] == label
    assert label not in str(restarted.inspect(PLAYER if npc else OTHER, action)["result"])
    if kind == "doppleganger_bond":
        from girlframe.engine.m3_actor_bonds import depth

        level = 2 if npc else 1
        assert received["bond"] == level
        assert depth(after, declaration.actor, target) == level
        assert "bond" not in restarted.inspect(PLAYER if npc else OTHER, action)["result"]
    if npc:
        (person,) = after.world.npcs
        assert [(x.id, x.label) for x in person.tags] == [(received["tag"], label)]
        assert label not in str(WorldService(MissionService(ledger)).get(ADMIN, private=True))
        assert before.sheets == after.sheets
    else:
        (tag,) = [x for x in after.sheets["2"].tags if x.id == received["tag"]]
        assert tag.giver_actor == declaration.actor and set(tag.observers) == {1, 2}
        assert after.sheets["3"] == before.sheets["3"]
    assert game.dice.calls == 0


def test_doppleganger_cannot_declare_its_known_form_from_a_concealed_source(ledger):
    from girlframe.services.onboarding import WorkflowError

    game, _, _, _, intent = gorgon_source(
        ledger,
        kind="doppleganger_bond",
        types=("doppleganger",),
        revealed=False,
        tag="Hidden relationship",
        begin=False,
    )
    service = GorgonPlayService(game)
    preview = service.preview(ADMIN, 900)
    assert "doppleganger_bond" not in preview["plays"]
    with pytest.raises(WorkflowError, match="actual local reach"):
        service.begin(ADMIN, "unrevealed-tag-bond", 900, preview["revision"], intent)
    assert not state(game).sheets["2"].tags and game.dice.calls == 0


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


@pytest.mark.parametrize("research", [False, True])
def test_actual_core_response_kills_original_gorgon_and_stops_its_old_attack(
    ledger, tmp_path, monkeypatch, research
):
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
    if research:
        from test_enforcer_requisitions import approved
        from test_handler_ordinary import session_native
        from test_ledger import OTHER
        from test_mission_ui import current
        from test_scientist_lab import create_scientist

        from girlframe.discord_adapter.m3_handler_ordinary import open_ordinary
        from girlframe.engine.m3_handler_ordinary import RULE as ORDINARY
        from girlframe.engine.m3_scientist_dissection import records
        from girlframe.services.m3_handler_advancements import HandlerAdvancementService
        from girlframe.services.m3_handler_ordinary import HandlerOrdinaryService
        from girlframe.services.m3_scientist_dissection import DissectionService
        from girlframe.services.onboarding import WorkflowError

        approved(ledger, game, tmp_path, monkeypatch, extra=(ORDINARY,))
        tick(worker, gateway, 5)
        create_scientist(ledger)
        ordinary = HandlerOrdinaryService(ledger)
        session = session_native(ordinary, "Actual observation of the laboratory", 51400)
        service = DissectionService(game)
        original = state(game)
        account = "PRIVATE_SYNTHETIC_OBSERVATION"
        assert ordinary.menu(ADMIN)["specimens"] == (("source-gorgon", "source-gorgon"),)
        assert not ordinary.menu(OTHER)["specimens"]
        with pytest.raises(WorkflowError, match="original Scientist"):
            service.perform(
                OTHER, "wrong-scientist", session, original.revision, "source-gorgon", account
            )
        with pytest.raises(WorkflowError, match="eligible laboratory"):
            service.perform(ADMIN, "living-body", session, original.revision, "secret", account)
        with pytest.raises(WorkflowError, match="current Session"):
            service.perform(
                ADMIN, "stale-specimen", session, original.revision - 1, "source-gorgon", account
            )
        ledger.safety(PLAYER, "hold-specimen", ledger.status(PLAYER)["revision"], pause=True)
        with pytest.raises(WorkflowError, match="SAFETY_PAUSED"):
            service.perform(
                ADMIN, "paused-specimen", session, original.revision, "source-gorgon", account
            )
        ledger.safety(PLAYER, "resume-specimen", ledger.status(PLAYER)["revision"], pause=False)
        ledger.engine.dispose()

        async def dissect():
            click = current(1, 51402)
            await click.response.defer(ephemeral=True)
            await open_ordinary(click, ordinary)
            form = click.edit_original_response.call_args.kwargs["view"]
            form.values.update(
                operation=("dissection",), specimen=("source-gorgon",), account=account
            )
            await form.confirm.callback(current(1, 51403))
            assert form.completed

        import asyncio

        asyncio.run(dissect())
        receipt = service.perform(
            ADMIN, "51403", session, original.revision, "source-gorgon", account
        )
        final = state(game)
        (dissection,) = records(final)
        assert dissection.lab == "base0" and dissection.death != dissection.event
        assert HandlerAdvancementService(ledger).view(ADMIN, receipt["id"])["phase"] == "held"
        assert final.sheets == original.sheets and not ordinary.menu(ADMIN)["specimens"]
        with pytest.raises(WorkflowError, match="eligible laboratory"):
            service.perform(
                ADMIN, "repeat-dissection", session, final.revision, "source-gorgon", account
            )


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


def test_native_growth_preserves_old_damage_and_changes_actual_core_requirements(ledger):
    import asyncio

    from test_mission_ui import current

    from girlframe.delivery.m2_worker import GameWorker
    from girlframe.discord_adapter.m2_forms import NativeForm
    from girlframe.discord_adapter.m3_gorgon_play import open_gorgon_play
    from girlframe.engine.m3_growth import Adaptation, Regrowth
    from girlframe.engine.m3_world import damage_gorgon, expose_gorgon
    from girlframe.engine.m3_world_state import CorePlan
    from girlframe.services.m2_game import GameService
    from girlframe.services.m3_world import WorldService
    from girlframe.services.onboarding import WorkflowError

    game, _, gateway, _, original = gorgon_source(
        ledger, kind="warp", types=("growth",), damaged=True, begin=False
    )
    actor = original.actor
    initial = next(x for x in state(game).world.gorgons if x.id == actor.entity)
    old, new_guard, *_ = initial.assets
    assert old.damaged and not new_guard.damaged
    exposed = expose_gorgon(state(game).world, actor.entity, "Original weakness")
    assert next(x for x in exposed.gorgons if x.id == actor.entity).exposed

    def data(kind):
        options = GorgonPlayService(game).preview(ADMIN, 900)
        item = next(x for x in options["actors"] if x["token"] == actor.token)
        assert kind in options["growth"][actor.token]
        return options["revision"], item["source_sha256"]

    async def native(kind, sequence, **choices):
        owner = current(ADMIN.user_id, sequence)
        owner.channel_id = 900
        await owner.response.defer(ephemeral=True)
        await open_gorgon_play(owner, game)
        form = owner.edit_original_response.call_args.kwargs["view"]
        assert isinstance(form, NativeForm)
        form.values.update(actor=(actor.token,), play=(kind,))
        select = current(ADMIN.user_id, sequence + 1)
        await select.response.defer(ephemeral=True)
        await form.confirm.callback(select)
        confirm = select.edit_original_response.call_args.kwargs["view"]
        confirm.values.update(account=original.account, reach=("confirmed",), **choices)
        sent = current(ADMIN.user_id, sequence + 2)
        await confirm.confirm.callback(sent)
        assert confirm.completed, sent.followup.send.call_args

    service = GorgonPlayService(game)
    adapt_rev, adapt_sha = data("growth_adapt")
    guards = CorePlan(assets=(new_guard.id,), weakness="Strike between the paired new ribs")
    adaptation = Adaptation(guards=guards, tag="Hardened unexpectedly")
    declaration = original.model_copy(
        update=dict(kind="growth_adapt", actor_sha256=adapt_sha, adaptation=adaptation)
    )
    with pytest.raises(WorkflowError, match="actual owned"):
        service.begin(PLAYER, "take-grow", 900, adapt_rev, declaration)
    with pytest.raises(WorkflowError, match="STALE_GORGON_PLAY"):
        service.begin(ADMIN, "old-grow", 900, adapt_rev - 1, declaration)
    asyncio.run(
        native(
            "growth_adapt",
            92000,
            guards=guards.assets,
            weakness=guards.weakness,
            growth_tag=adaptation.tag,
        )
    )
    first = service.begin(ADMIN, "92002", 900, adapt_rev, declaration)
    assert next(x for x in state(game).world.gorgons if x.id == actor.entity) == initial
    ledger.safety(PLAYER, "hold-growth", ledger.status(PLAYER)["revision"], pause=True)
    tick(GameWorker(game), gateway, 4)
    assert next(x for x in state(game).world.gorgons if x.id == actor.entity) == initial
    ledger.safety(PLAYER, "resume-growth", ledger.status(PLAYER)["revision"], pause=False)

    def finish(action):
        recovered = GameService(ledger, dice=game.dice)
        runner = GameWorker(recovered)
        tick(runner, gateway, 5)
        with ledger.engine.connect() as c:
            receipt = recovered.action(c, action)
        if not receipt["data"]["gorgon_play"]["started"]:
            recovered.roll(ADMIN, str(uuid4()), action)
        tick(runner, gateway, 5)
        with ledger.engine.connect() as c:
            assert recovered.action(c, action)["state"] == "complete"
        return next(x for x in state(recovered).world.gorgons if x.id == actor.entity)

    adapted = finish(first["action_id"])
    assert adapted.core_plan == guards and adapted.assets == initial.assets
    assert [(tag.label, tag.giver_entity) for tag in adapted.tags] == [
        (adaptation.tag, actor.entity)
    ]
    with pytest.raises(ValueError, match="designated Core-protecting Assets"):
        expose_gorgon(state(game).world, actor.entity, "Original weakness")
    public = WorldService(MissionService(ledger)).get(PLAYER)
    assert guards.weakness not in str(public)
    assert adaptation.tag not in str(public)

    regrow_rev, regrow_sha = data("growth_regrow")
    regrowth = Regrowth(asset=old.id, name="New plates", description="Ribs fuse into plates")
    picked = original.model_copy(
        update=dict(kind="growth_regrow", actor_sha256=regrow_sha, regrowth=regrowth)
    )
    bogus = picked.model_copy(
        update=dict(regrowth=regrowth.model_copy(update=dict(asset=new_guard.id)))
    )
    with pytest.raises(WorkflowError, match="current damaged Asset"):
        service.begin(ADMIN, "undamaged", 900, regrow_rev, bogus)
    asyncio.run(
        native(
            "growth_regrow",
            92010,
            eaten=(old.id,),
            replacement=regrowth.name,
            description=regrowth.description,
        )
    )
    second = service.begin(ADMIN, "92012", 900, regrow_rev, picked)
    changed = finish(second["action_id"])
    assert changed.destroyed_assets == (old,)
    assert old.id not in {x.id for x in changed.assets}
    assert len(changed.assets) == len(initial.assets)
    new = changed.assets[0]
    assert (new.name, new.description, new.damaged) == (regrowth.name, regrowth.description, False)
    assert changed.core_plan == guards and changed.tags == adapted.tags
    world = damage_gorgon(state(game).world, actor.entity, new_guard.id, indirect=True)
    world = expose_gorgon(world, actor.entity, guards.weakness)
    assert next(x for x in world.gorgons if x.id == actor.entity).exposed
    assert game.dice.calls == 0


@pytest.mark.parametrize("escaped", [False, True])
def test_native_mother_pays_real_birth_and_only_reviewed_escape_matures(ledger, escaped):
    import asyncio

    from test_ledger import OTHER
    from test_mission_ui import current
    from test_off_duty_cycle import activate
    from test_off_duty_cycle import prepared as ready_period

    from girlframe.delivery.m2_worker import GameWorker
    from girlframe.discord_adapter.m2_forms import NativeForm
    from girlframe.discord_adapter.m3_gorgon_play import open_gorgon_play
    from girlframe.discord_adapter.m3_world import open_world
    from girlframe.engine import m3_mother_sprite as rules
    from girlframe.services.m2_game import GameService
    from girlframe.services.m3_mother_sprite import SpriteEscapeService
    from girlframe.services.m3_movement import MovementService
    from girlframe.services.m3_world import WorldService
    from girlframe.services.onboarding import WorkflowError

    mother = ActorRef(kind="gorgon", entity="original-mother")
    marker = {}
    sprite_name, sprite_asset = "Original Sprite", "Filament"

    def introduce_before_period(game):
        approval = ledger.policy.m3_approval
        ledger.policy = ledger.policy.model_copy(
            update=dict(
                m3_approval=approval.model_copy(
                    update=dict(subsystems=approval.subsystems | {"plays"})
                ),
            )
        )
        with ledger.transaction() as c:
            original = state(game)
            body = gorgon("erratic", mother.entity, revealed=True, types=("mother", "growth"))
            original.world = update(original.world, gorgons=(*original.world.gorgons, body))
            game.event(c, 1, "mother-source", "synthetic.original_mother", original)
        cast = CastService(ActorService(MissionService(ledger)))
        change(cast, ADMIN, "join", mother)
        service = GorgonPlayService(game)
        data = service.preview(ADMIN, 900)
        actual = next(x for x in data["actors"] if x["token"] == mother.token)
        assert "mother_sprite" in data["plays"]
        assert "mother_sprite" not in service.preview(PLAYER, 900)["plays"]
        cost = actual["assets"][0]["id"]
        arguments = dict(
            payment=cost,
            name=sprite_name,
            asset=sprite_asset,
            weakness="Interrupt the original filament",
        )

        async def native_birth():
            click = current(1, 93100)
            click.channel_id = 900
            await click.response.defer(ephemeral=True)
            await open_gorgon_play(click, game)
            form = click.edit_original_response.call_args.kwargs["view"]
            form.values.update(actor=(mother.token,), play=("mother_sprite",))
            selected = current(1, 93101)
            await selected.response.defer(ephemeral=True)
            await form.confirm.callback(selected)
            confirm = selected.edit_original_response.call_args.kwargs["view"]
            confirm.values.update(
                payment=(cost,),
                sprite_name=sprite_name,
                sprite_asset=sprite_asset,
                sprite_weakness=arguments["weakness"],
                account="Actual paid Sprite birth",
                reach=("confirmed",),
            )
            await confirm.confirm.callback(current(1, 93102))
            assert confirm.completed

        declaration = Declaration(
            kind="mother_sprite",
            actor=mother,
            actor_sha256=actual["source_sha256"],
            account="Actual paid Sprite birth",
            reach_confirmed=True,
            birth=rules.BirthPlan(**arguments),
        )
        with pytest.raises(WorkflowError, match="actual owned"):
            service.begin(PLAYER, "forged-sprite", 900, data["revision"], declaration)
        asyncio.run(native_birth())
        request = service.begin(ADMIN, "93102", 900, data["revision"], declaration)
        assert not rules.records(state(game))
        replay_game = GameService(ledger, dice=game.dice)
        worker, gateway = GameWorker(replay_game), Gateway()
        tick(worker, gateway, 4)
        with ledger.engine.connect() as c:
            active = game.action(c, request["action_id"])["data"]["gorgon_play"]["started"]
        if not active:
            replay_game.roll(ADMIN, "advance-birth", request["action_id"])
        tick(worker, gateway, 5)
        (birth,) = rules.records(state(game))
        marker["birth"] = birth
        canon = state(game)
        current_mother = next(x for x in canon.world.gorgons if x.id == mother.entity)
        born = next(x for x in canon.world.gorgons if x.id == birth.sprite.entity)
        assert birth.action == request["action_id"] and birth.paid_asset == cost
        assert any(x.id == cost and x.damaged for x in current_mother.assets)
        assert born.types == current_mother.types and born.follows == mother.entity
        assert born.gorgon_class == "sprite" and born.assets[0].name == sprite_asset
        assert not rules.pending(canon) and not rules.maturities(canon)
        assert sprite_name not in str(WorldService(MissionService(ledger)).get(PLAYER))

        change(cast, ADMIN, "join", birth.sprite)
        mover = MovementService(game)
        before = state(game)
        mover.move(
            ADMIN,
            "physical-sprite-flight",
            before.revision,
            900,
            birth.sprite,
            (1, 0),
            account="The Sprite escapes the current firefight.",
        )
        (move,) = rules.moves(state(game))
        marker["move"] = move
        assert (move.origin, move.destination, move.sprite) == ((0, 0), (1, 0), birth.sprite)

    cycle, game, period = ready_period(ledger, before_period=introduce_before_period)
    service = SpriteEscapeService(game)
    birth, move = marker["birth"], marker["move"]
    assert service.options(ADMIN)["options"][0][0] == move.event
    with pytest.raises(WorkflowError, match="human table adjudicator"):
        service.options(OTHER)
    with pytest.raises(WorkflowError, match="escape review before Off-Duty"):
        activate(cycle, game, period)
    assert cycle.periods.get(ADMIN, period)["phase"] == "preparing"

    adult = (
        rules.Adult(gorgon_class="dormant", extra_assets=("Outer jaw", "Veil")) if escaped else None
    )
    description = "Human GM resolves the actual Sprite's flight."
    revision = state(game).revision
    with pytest.raises(WorkflowError, match="original move"):
        service.review(ADMIN, "stale-flight", revision - 1, move.event, description, adult)

    ledger.safety(PLAYER, "pause-escape", ledger.status(PLAYER)["revision"], pause=True)
    with pytest.raises(WorkflowError, match="SAFETY_PAUSED"):
        service.review(ADMIN, "paused-flight", revision, move.event, description, adult)
    ledger.safety(PLAYER, "resume-escape", ledger.status(PLAYER)["revision"], pause=False)

    async def review():
        click = current(1, 93120)
        await click.response.defer(ephemeral=True)
        await open_world(click, WorldService(MissionService(ledger)))
        menu = click.edit_original_response.call_args.kwargs["view"]
        picked = current(1, 93121)
        await picked.response.defer(ephemeral=True)
        await menu.open_item(picked, "sprite_escape")
        form = picked.edit_original_response.call_args.kwargs["view"]
        assert isinstance(form, NativeForm)
        form.values.update(
            movement=(move.event,),
            result=("dormant",) if escaped else ("stayed",),
            assets="Outer jaw\nVeil" if escaped else "",
            account=description,
        )
        sent = current(1, 93122)
        await form.confirm.callback(sent)
        assert form.completed, sent.followup.send.call_args

    asyncio.run(review())
    saved = service.review(ADMIN, "93122", revision, move.event, description, adult)
    assert saved["escaped"] == escaped
    assert not rules.maturities(state(game))
    assert not service.options(ADMIN)["options"]

    replay_cycle = type(cycle)(type(cycle.periods)(MissionService(ledger)))
    expect = replay_cycle.review(ADMIN, period)["revision"]
    game_revision = state(game).revision
    first = replay_cycle.activate(ADMIN, "grow-next-period", period, expect, game_revision)
    assert first == replay_cycle.activate(ADMIN, "grow-next-period", period, expect, game_revision)
    final = state(game)
    body = next(x for x in final.world.gorgons if x.id == birth.sprite.entity)
    assert body.alive and body.cell == (1, 0)
    assert body.gorgon_class == ("dormant" if escaped else "sprite")
    assert body.follows == (None if escaped else mother.entity)
    assert [x.name for x in body.assets] == (
        [sprite_asset, "Outer jaw", "Veil"] if escaped else [sprite_asset]
    )
    assert body.core_plan.assets == (body.assets[0].id,)
    if escaped:
        (grown,) = rules.maturities(final)
        assert (grown.escape, grown.period) == (saved["event"], period)
    else:
        assert not rules.maturities(final)


def test_parasite_rides_actual_npc_until_owned_detachment(ledger):
    import asyncio

    from test_ledger import OTHER
    from test_mission_ui import current

    from girlframe.discord_adapter.m3_gorgon_play import open_gorgon_play
    from girlframe.engine.m3_actor_bonds import current_ref
    from girlframe.engine.m3_parasite import active, records
    from girlframe.services.m3_movement import MovementService
    from girlframe.services.onboarding import WorkflowError

    game, worker, gateway, _, declaration = gorgon_source(
        ledger,
        kind="parasite_hitch",
        types=("parasite",),
        npc=True,
        target="actual-guard",
        begin=False,
    )
    original = state(game)
    actor = declaration.actor
    host = declaration.target
    service = GorgonPlayService(game)
    preview = service.preview(ADMIN, 900)
    assert preview["parasite"] == {actor.token: {"parasite_hitch": [host.token]}}
    assert not service.preview(OTHER, 900)["parasite"]
    with pytest.raises(WorkflowError, match="owned"):
        service.begin(OTHER, "wrong-parasite-controller", 900, original.revision, declaration)
    other = current_ref(original, OTHER.user_id)
    unowned = next(x for x in preview["actors"] if x["token"] == other.token)
    with pytest.raises(WorkflowError, match="ordinary NPC"):
        service.begin(
            ADMIN,
            "wrong-parasite-host",
            900,
            original.revision,
            declaration.model_copy(
                update=dict(target=other, target_sha256=unowned["source_sha256"])
            ),
        )

    async def native():
        owner = current(ADMIN.user_id, 87200)
        owner.channel_id = 900
        await owner.response.defer(ephemeral=True)
        await open_gorgon_play(owner, game)
        form = owner.edit_original_response.call_args.kwargs["view"]
        form.values.update(actor=(actor.token,), play=("parasite_hitch",))
        chosen = current(ADMIN.user_id, 87201)
        await chosen.response.defer(ephemeral=True)
        await form.confirm.callback(chosen)
        details = chosen.edit_original_response.call_args.kwargs["view"]
        details.values.update(
            target=(host.token,), account=declaration.account, reach=("confirmed",)
        )
        sent = current(ADMIN.user_id, 87202)
        await details.confirm.callback(sent)
        assert details.completed, sent.followup.send.call_args

    asyncio.run(native())
    action = service.begin(ADMIN, "87202", 900, original.revision, declaration)
    tick(worker, gateway, 5)
    if active(state(game), actor) is None:
        game.roll(ADMIN, "advance-ride", action["action_id"])
        tick(worker, gateway, 5)

    ride = active(state(game), actor)
    assert ride is not None and (ride.host, ride.cell) == (host, (0, 0))
    assert ride.action == action["action_id"]
    assert game.inspect(ADMIN, action["action_id"])["state"] == "complete"
    assert game.dice.calls == 0
    ledger.engine.dispose()

    movement = MovementService(game)
    with pytest.raises(WorkflowError, match="detach"):
        movement.move(
            ADMIN,
            "separate-movement",
            state(game).revision,
            900,
            actor,
            (1, 0),
            account="The original Parasite tries moving independently.",
        )
    revision = state(game).revision
    trip = movement.move(
        OTHER,
        "host-moves",
        revision,
        900,
        host,
        (1, 0),
        account="The Guard takes the stairs.",
    )
    assert (
        movement.move(
            OTHER,
            "host-moves",
            revision,
            900,
            host,
            (1, 0),
            account="The Guard takes the stairs.",
        )
        == trip
    )
    current_ride = active(state(game), actor)
    assert current_ride.cell == (1, 0) and current_ride.position_event != ride.position_event
    assert next(x for x in state(game).world.gorgons if x.id == actor.entity).cell == (1, 0)
    assert state(game).sheets == original.sheets

    preview = service.preview(ADMIN, 900)
    source = next(x for x in preview["actors"] if x["token"] == actor.token)
    assert preview["parasite"] == {actor.token: {"parasite_detach": []}}
    detach = Declaration(
        kind="parasite_detach",
        actor=actor,
        actor_sha256=source["source_sha256"],
        account="The Parasite leaves its actual original host.",
        reach_confirmed=True,
    )
    command = service.begin(ADMIN, "detach-ride", 900, preview["revision"], detach)
    tick(worker, gateway, 5)
    if active(state(game), actor) is not None:
        game.roll(ADMIN, "advance-detach", command["action_id"])
        tick(worker, gateway, 5)
    (closed,) = records(state(game))
    assert closed.event == ride.event and closed.ended and closed.action == ride.action
    movement.move(
        OTHER,
        "host-alone",
        state(game).revision,
        900,
        host,
        (0, 0),
        account="The Guard leaves the Parasite on the stairs.",
    )
    assert state(game).world.npcs[0].cell == (0, 0)
    assert next(x for x in state(game).world.gorgons if x.id == actor.entity).cell == (1, 0)
    assert state(game).sheets == original.sheets and game.dice.calls == 0


@pytest.mark.parametrize(
    "die_faces,result,threshold",
    [
        ((3, 4), "mid", False),
        ((5, 5), "high", False),
        ((1, 2), "low", False),
        ((1, 2), "low", True),
    ],
)
def test_jackdaw_hallucinations_has_owned_heat_roll_and_printed_consequence(
    ledger, die_faces, result, threshold
):
    import asyncio

    from test_ledger import OTHER
    from test_m2_game import Dice, pass_tags
    from test_mission_ui import current

    from girlframe.discord_adapter.m3_gorgon_runtime import open_choice
    from girlframe.engine.m2 import ChoiceAnswer, PlayInput
    from girlframe.engine.m3_actor_bonds import current_ref
    from girlframe.engine.m3_actors import resolve
    from girlframe.engine.m3_beneath import rejection_blocked
    from girlframe.engine.m3_hallucinations import days, records
    from girlframe.engine.m3_jackdaw import Range
    from girlframe.services.m3_actors import profiles
    from girlframe.services.m3_hallucinations import DAY_GAIN, DAY_REVIEW, HEAT, OUTCOME
    from girlframe.services.m3_jackdaw import catatonic, isolation
    from girlframe.services.m3_movement import MovementService
    from girlframe.services.m3_sentinel import require_communication
    from girlframe.services.m3_void import VoidService
    from girlframe.services.onboarding import WorkflowError

    game, worker, gateway, jam, declaration = gorgon_source(
        ledger,
        kind="jackdaw_jam",
        types=("jackdaw",),
        other_cell=(2, 0),
        interference=Range(cells=((0, 0),)),
    )
    tick(worker, gateway, 5)
    assert game.inspect(ADMIN, jam)["state"] == "complete"
    game.dice = Dice(die_faces)
    remaining = None
    with ledger.transaction() as c:
        canon = state(game)
        sheet = canon.sheets[str(PLAYER.user_id)]
        sheet.heat = 2
        if threshold:
            frame = [x for x in sheet.assets if x.family == "frame"]
            remaining = frame[-1].id
            for asset in frame[:-1]:
                asset.void = True
                asset.description = "Earlier fictional damage"

        game.event(c, PLAYER.user_id, "synthetic-hallucination-heat", "synthetic.heat", canon)
    service = GorgonPlayService(game)
    preview = service.preview(ADMIN, 900)
    before = state(game)
    girl = current_ref(before, PLAYER.user_id)
    stray = current_ref(before, OTHER.user_id)
    assert preview["typed_targets"][declaration.actor.token]["jackdaw_hallucinations"] == [
        girl.token
    ]
    forms = {x["token"]: x for x in preview["actors"]}
    hallucinations = Declaration(
        kind="jackdaw_hallucinations",
        actor=declaration.actor,
        actor_sha256=forms[declaration.actor.token]["source_sha256"],
        target=girl,
        target_sha256=forms[girl.token]["source_sha256"],
        account="The original Jackdaw directs its established song at the Isolated Girl.",
        reach_confirmed=True,
    )
    with pytest.raises(WorkflowError, match="actual Girl must be Isolated"):
        service.begin(
            ADMIN,
            "outside-isolation",
            900,
            before.revision,
            hallucinations.model_copy(
                update=dict(target=stray, target_sha256=forms[stray.token]["source_sha256"])
            ),
        )
    action = service.begin(ADMIN, "hallucinations", 900, before.revision, hallucinations)[
        "action_id"
    ]
    tick(worker, gateway, 5)
    if not any(x["kind"] == HEAT for x in game.choices(PLAYER)):
        game.roll(ADMIN, "advance-hallucinations", action)
    spend = next(x for x in game.choices(PLAYER) if x["kind"] == HEAT)
    assert all(x["kind"] not in (HEAT, OUTCOME) for x in game.choices(OTHER))
    with pytest.raises(WorkflowError, match="another player"):
        game.respond(
            OTHER, "wrong-hallucinations", spend["id"], spend["revision"], ChoiceAnswer(number=1)
        )
    with pytest.raises(WorkflowError, match="Choose Heat"):
        game.respond(
            PLAYER,
            "excess-hallucination-heat",
            spend["id"],
            spend["revision"],
            ChoiceAnswer(number=100),
        )
    if result == "high":
        ledger.safety(OTHER, "pause-hallucinations", ledger.status(OTHER)["revision"], pause=True)
        with pytest.raises(WorkflowError, match="SAFETY_PAUSED"):
            game.respond(
                PLAYER,
                "paused-hallucinations",
                spend["id"],
                spend["revision"],
                ChoiceAnswer(number=1),
            )
        ledger.safety(OTHER, "resume-hallucinations", ledger.status(OTHER)["revision"], pause=False)

        async def native_heat():
            handoff = current(PLAYER.user_id, 87300)
            await handoff.response.defer(ephemeral=True)
            await open_choice(handoff, game, spend["id"])
            form = handoff.edit_original_response.call_args.kwargs["view"]
            form.values["heat"] = "1"
            await form.confirm.callback(current(PLAYER.user_id, 87301))
            assert form.completed

        asyncio.run(native_heat())
        key = "87301"
    else:
        key = "hallucination-heat"
        game.respond(PLAYER, key, spend["id"], spend["revision"], ChoiceAnswer(number=1))
    game.respond(PLAYER, key, spend["id"], spend["revision"], ChoiceAnswer(number=1))
    assert game.dice.calls == 1
    assert state(game).sheets[girl.entity].heat == before.sheets[girl.entity].heat - 1
    decision = next(x for x in game.choices(PLAYER) if x["kind"] == OUTCOME)
    ledger.engine.dispose()
    detail = game.decision(PLAYER, decision["id"])["detail"]
    assert detail["roll"]["faces"] == list(die_faces) and detail["tier"] == result
    talent = "Clockwork birds on the roof"
    fields, erased = {}, ()
    if result == "low":
        erased = tuple(list(detail["identities"])[:3])
        assert len(erased) == 3
        fields = dict(
            asset=remaining or next(iter(detail["assets"])), void_description="Turns to glass."
        )
    game.respond(
        PLAYER,
        "hallucination-outcome",
        decision["id"],
        decision["revision"],
        ChoiceAnswer(text=talent, options=erased, fields=fields),
    )
    after = state(game)
    (effect,) = records(after)
    assert (
        effect.girl == girl and effect.source == declaration.actor and effect.roll.result == result
    )
    assert game.inspect(ADMIN, action)["state"] == ("awaiting_choices" if threshold else "complete")
    assert after.sheets[stray.entity] == before.sheets[stray.entity]
    tag = next(x for x in after.sheets[girl.entity].tags if x.id == effect.tag)
    assert tag.label == ("Isolated" if result == "low" else talent)
    assert OTHER.user_id not in tag.observers
    assert rejection_blocked(after, PLAYER.user_id, tag.id) == (result == "high")
    with ledger.engine.connect() as c:
        view = resolve(after, girl, profiles(c, ledger.campaign_id), require_current_profile=False)
        assert bool(isolation(c, ledger.campaign_id, after, view)) == (result != "high")
        assert catatonic(c, ledger.campaign_id, after, view) == (result == "low")
        with pytest.raises(WorkflowError, match="No verified communication route"):
            require_communication(c, ledger.campaign_id, after, girl, (stray,))
    if result == "low":
        sheet = after.sheets[girl.entity]
        assert not set(erased) & {x.id for x in sheet.identities}
        assert next(x.name for x in sheet.identities if x.id == effect.identity) == talent
        assert effect.void_asset == fields["asset"]
        assert next(x for x in sheet.assets if x.id == effect.void_asset).void

    if threshold:
        (work,) = effect.void_work
        service = VoidService(ledger)
        assert service.get(PLAYER, work)["stage"] == "resist_pending"
        with pytest.raises(WorkflowError, match="private Void"):
            service.get(OTHER, work)
        held = next(x for x in game.choices(PLAYER) if x["kind"] == "gorgon_hallucinations_void")
        assert game.decision(PLAYER, held["id"])["detail"]["work"] == work
        original = state(game).sheets[girl.entity]
        game.dice.faces = (1, 1)
        child = game.begin(
            PLAYER,
            "resist-hallucinations",
            900,
            original.revision,
            PlayInput(
                play="keep_your_head",
                source_work=work,
                heat=original.heat,
                parent=action,
                context="The original Girl resists the actual corrupted Frame.",
                trigger_confirmed=True,
            ),
        )["action_id"]
        tick(worker, gateway, 4)
        pass_tags(game)
        answer(game, PLAYER, "actor_keep", options=("in_control",))
        answer(game, ADMIN, "handler_keep", flag=True, text="The actual resistance succeeded.")
        tick(worker, gateway, 5)
        assert game.inspect(PLAYER, child)["state"] == "complete"
        assert game.inspect(ADMIN, action)["state"] == "complete"
        assert service.get(PLAYER, work)["stage"] == "prevented"

    if result == "low" and not threshold:
        tick(worker, gateway, 5)
        gorgon_service = GorgonPlayService(game)
        preview = gorgon_service.preview(ADMIN, 900)
        assert preview["exposure_days"][effect.source.token] == {girl.token: 1}
        rows = {x["token"]: x for x in preview["actors"]}
        day = Declaration(
            kind="jackdaw_hallucinations_day",
            day=1,
            actor=effect.source,
            target=girl,
            actor_sha256=rows[effect.source.token]["source_sha256"],
            target_sha256=rows[girl.token]["source_sha256"],
            account="The next fictional day ended while the same Jackdaw remained in range.",
            reach_confirmed=True,
        )
        with pytest.raises(WorkflowError, match="next fictional day"):
            gorgon_service.begin(
                ADMIN, "skip-day", 900, preview["revision"], day.model_copy(update=dict(day=2))
            )
        started = gorgon_service.begin(ADMIN, "elapsed-day", 900, preview["revision"], day)
        tick(worker, gateway, 5)
        if not any(x["kind"] == DAY_REVIEW for x in game.choices(ADMIN)):
            game.roll(ADMIN, "advance-day", started["action_id"])
        review = next(x for x in game.choices(ADMIN) if x["kind"] == DAY_REVIEW)
        assert not days(state(game))
        assert not any(x["kind"] in (DAY_REVIEW, DAY_GAIN) for x in game.choices(PLAYER))
        with pytest.raises(WorkflowError, match="another player"):
            game.respond(
                PLAYER,
                "not-gm-day",
                review["id"],
                review["revision"],
                ChoiceAnswer(flag=True, text="The day ended."),
            )

        async def approve_day():
            handoff = current(ADMIN.user_id, 87302)
            await handoff.response.defer(ephemeral=True)
            await open_choice(handoff, game, review["id"])
            form = handoff.edit_original_response.call_args.kwargs["view"]
            form.values.update(confirmed=("yes",), account="The scene time log records a full day.")
            await form.confirm.callback(current(ADMIN.user_id, 87303))
            assert form.completed

        asyncio.run(approve_day())
        assert not days(state(game))
        ledger.engine.dispose()
        gain = next(x for x in game.choices(PLAYER) if x["kind"] == DAY_GAIN)
        choices = game.decision(PLAYER, gain["id"])["detail"]
        accepted = ChoiceAnswer(
            fields=dict(
                asset=next(iter(choices["assets"])), void_description="Crystals spread across it."
            )
        )
        first = game.respond(PLAYER, "day-void", gain["id"], gain["revision"], accepted)
        assert game.respond(PLAYER, "day-void", gain["id"], gain["revision"], accepted) == first
        (elapsed,) = days(state(game))
        assert elapsed.day == 1 and elapsed.original == action
        assert elapsed.void_asset != effect.void_asset and elapsed.review
        assert records(state(game)) == (effect,) and game.dice.calls == 1
        assert state(game).sheets[girl.entity].identities == after.sheets[girl.entity].identities
        assert gorgon_service.preview(ADMIN, 900)["exposure_days"][effect.source.token] == {
            girl.token: 2
        }
        tick(worker, gateway, 5)
        MovementService(game).move(
            ADMIN,
            "leave-exposure",
            state(game).revision,
            900,
            effect.source,
            (1, 0),
            account="The original Jackdaw leaves the square.",
        )
        preview = gorgon_service.preview(ADMIN, 900)
        assert "jackdaw_hallucinations_day" not in preview["plays"]


@pytest.mark.parametrize("finalize", [False, True])
def test_private_gorgon_contact_can_be_withdrawn_before_the_original_career_ends(ledger, finalize):
    import asyncio

    from test_ledger import OTHER
    from test_mission_ui import current
    from test_privacy_game_delivery import PrivateGateway

    from girlframe.discord_adapter.m3_gorgon_play import open_gorgon_play
    from girlframe.discord_adapter.m3_gorgon_runtime import open_choice
    from girlframe.engine.m2 import ChoiceAnswer, PilotSheet
    from girlframe.engine.m3_actor_bonds import current_ref
    from girlframe.engine.m3_actors import resolve
    from girlframe.engine.m3_physical_state import CockpitAction
    from girlframe.services.m3_actors import profiles
    from girlframe.services.m3_gorgon_contact import CONCLUSION, CONSENT, FINAL, REVIEW
    from girlframe.services.m3_physical import PhysicalService
    from girlframe.services.onboarding import WorkflowError

    game, worker, gateway, _, original = gorgon_source(
        ledger,
        kind="intimate_contact",
        npc=True,
        begin=False,
    )
    gateway = PrivateGateway()
    pilot = current_ref(state(game), PLAYER.user_id)
    outsider = current_ref(state(game), OTHER.user_id)
    source = original.actor
    service = GorgonPlayService(game)
    assert "intimate_contact" not in service.preview(ADMIN, 900)["plays"]
    current_state = state(game)
    with ledger.engine.connect() as c:
        actual = resolve(current_state, pilot, profiles(c, ledger.campaign_id))
    PhysicalService(ledger).operate(
        PLAYER,
        "leave-cockpit-before-contact",
        current_state.revision,
        CockpitAction(
            actor=pilot,
            operation="exit",
            expected_position=actual.position_sha256,
            account="I exit my parked Frame.",
            confirmed=True,
        ),
        channel=900,
    )
    cast = CastService(ActorService(MissionService(ledger)))
    change(cast, OTHER, "withdraw", outsider)
    before = state(game)
    known = service.preview(ADMIN, 900)
    assert known["typed_targets"][source.token]["intimate_contact"] == [pilot.token]
    subject = next(x for x in known["actors"] if x["token"] == pilot.token)
    declaration = original.model_copy(update=dict(target_sha256=subject["source_sha256"]))

    async def native_declaration():
        home = current(ADMIN.user_id, 87400)
        home.channel_id = 900
        await home.response.defer(ephemeral=True)
        await open_gorgon_play(home, game)
        form = home.edit_original_response.call_args.kwargs["view"]
        form.values.update(actor=(source.token,), play=("intimate_contact",))
        entered = current(ADMIN.user_id, 87401)
        await entered.response.defer(ephemeral=True)
        await form.confirm.callback(entered)
        details = entered.edit_original_response.call_args.kwargs["view"]
        details.values.update(
            target=(pilot.token,), account=declaration.account, reach=("confirmed",)
        )
        await details.confirm.callback(current(ADMIN.user_id, 87402))
        assert details.completed

    asyncio.run(native_declaration())
    action = service.begin(ADMIN, "87402", 900, before.revision, declaration)["action_id"]
    tick(worker, gateway, 5)
    if not any(x["kind"] == CONSENT for x in game.choices(PLAYER)):
        game.roll(ADMIN, "advance-contact", action)
    invite = next(x for x in game.choices(PLAYER) if x["kind"] == CONSENT)
    with pytest.raises(WorkflowError, match="no longer available"):
        game.decision(OTHER, invite["id"])
    with pytest.raises(WorkflowError, match="original source-table"):
        game.inspect(OTHER, action)
    assert state(game).sheets == before.sheets
    answer(game, PLAYER, CONSENT, flag=True)
    answer(
        game,
        ADMIN,
        REVIEW,
        flag=True,
        text="The original adult participants and reach were confirmed.",
    )
    answer(game, ADMIN, CONCLUSION, flag=True, text="Echoes in the rain")
    assert state(game).sheets == before.sheets and not state(game).career_archives
    decision = next(x for x in game.choices(PLAYER) if x["kind"] == FINAL)
    with pytest.raises(WorkflowError, match="another player"):
        game.respond(
            ADMIN, "not-owner-final", decision["id"], decision["revision"], ChoiceAnswer(flag=True)
        )
    ledger.engine.dispose()

    async def native_final():
        handoff = current(PLAYER.user_id, 87403)
        await handoff.response.defer(ephemeral=True)
        await open_choice(handoff, game, decision["id"])
        form = handoff.edit_original_response.call_args.kwargs["view"]
        form.values["choice"] = ("yes" if finalize else "no",)
        await form.confirm.callback(current(PLAYER.user_id, 87404))
        assert form.completed

    asyncio.run(native_final())
    outcome = game.respond(
        PLAYER,
        "87404",
        decision["id"],
        decision["revision"],
        ChoiceAnswer(flag=finalize),
    )
    assert game.inspect(ADMIN, action)["state"] == "complete"
    tick(worker, gateway, 5)
    with ledger.engine.connect() as c:
        assert game.lock(c, 900)["state"] == "released"
    assert {recipient for recipient, _ in gateway.private} == {ADMIN.user_id, PLAYER.user_id}
    assert set(message["kind"] for message in gateway.messages.values()) <= {"control"}
    assert all(set(message) == {"kind", "action_id"} for message in gateway.messages.values())
    assert outcome["action_id"] == action and game.dice.calls == 0
    after = state(game)
    body = next(x for x in after.world.gorgons if x.id == source.entity)
    assert body.exposed is finalize
    assert after.sheets[outsider.entity] == before.sheets[outsider.entity]
    with ledger.engine.connect() as c:
        assert OTHER.user_id not in game.scene(c, 900)["participants"]
    npc = ActorRef(kind="npc", entity="actual-guard")
    assert any(
        role.actor == npc for role in next(x for x in after.scene_casts if x.channel == 900).roles
    )
    if finalize:
        assert pilot.entity not in after.sheets
        (archive,) = after.career_archives
        assert archive.actor == pilot and archive.ending == "death"
        archived = PilotSheet.model_validate_json(archive.sheet_json)
        tag = next(x for x in archived.tags if x.label == "Echoes in the rain")
        assert tag.giver_actor == source and OTHER.user_id not in tag.observers
    else:
        assert after.sheets == before.sheets and not after.career_archives


@pytest.mark.parametrize(
    "sides,level,threshold",
    [
        ((1, 3), "low", False),
        ((3, 5), "mid", False),
        ((3, 4), "mid", True),
        ((5, 5), "high", False),
        ((5, 5), "interrupt", False),
    ],
)
def test_in_frame_gorgon_roll_uses_actual_void_frame_assets(
    ledger, sides, level, threshold, monkeypatch
):
    import asyncio

    from test_ledger import OTHER
    from test_m2_game import Dice
    from test_mission_ui import current
    from test_privacy_game_delivery import PrivateGateway
    from test_void_service import respond as respond_void

    import girlframe.services.m2_game as shared
    from girlframe.discord_adapter.m3_gorgon_contact_disclosure import open_report
    from girlframe.engine.m2 import ChoiceAnswer, PlayInput
    from girlframe.engine.m3_battle_state import Declaration as BattleDeclaration
    from girlframe.engine.m3_gorgon_frame_contact import results
    from girlframe.engine.m3_handler_consequences import active_handler
    from girlframe.services.inbox import InboxService
    from girlframe.services.m3_battle import BattleService
    from girlframe.services.m3_gorgon_contact import CONSENT, FINAL, REVIEW
    from girlframe.services.m3_gorgon_contact_disclosure import KIND, FrameContactDisclosureService
    from girlframe.services.m3_gorgon_frame_contact import (
        FRAME_CONSEQUENCE,
        FRAME_DAMAGE,
        FRAME_ROLL,
        FRAME_VOID,
    )
    from girlframe.services.m3_void import VoidService
    from girlframe.services.onboarding import WorkflowError

    game, worker, gateway, _, original = gorgon_source(
        ledger,
        kind="intimate_frame_contact",
        begin=False,
        exposed=level == "interrupt",
    )
    gateway = PrivateGateway()
    game.dice = Dice(sides)
    with ledger.transaction() as c:
        canon = state(game)
        original_assets = canon.sheets[str(PLAYER.user_id)].assets
        frame_assets = [x for x in original_assets if x.family == "frame"]
        frame = frame_assets[0]
        reserved = frame_assets[-1] if threshold else None
        already_void = tuple(frame_assets[:-1]) if threshold else (frame,)
        girl_only = next(x for x in original_assets if x.family == "girl")
        for asset in (*already_void, girl_only):
            asset.void = True
            asset.description = "An earlier fictional alteration."
        game.event(c, ADMIN.user_id, "synthetic-frame-contact-void", "synthetic.void", canon)
    service = GorgonPlayService(game)
    before = state(game)
    view = service.preview(ADMIN, 900)
    assert (
        original.target.token
        in view["typed_targets"][original.actor.token]["intimate_frame_contact"]
    )
    updated = next(x for x in view["actors"] if x["token"] == original.target.token)
    declared = original.model_copy(update=dict(target_sha256=updated["source_sha256"]))
    action = service.begin(ADMIN, "frame-contact", 900, before.revision, declared)["action_id"]
    tick(worker, gateway, 5)
    if not any(x["kind"] == CONSENT for x in game.choices(PLAYER)):
        game.roll(ADMIN, "advance-frame-contact", action)
    answer(game, PLAYER, CONSENT, flag=True)
    answer(game, ADMIN, REVIEW, flag=True, text="The original adult actors are in verified reach.")
    answer(game, PLAYER, FINAL, flag=True)
    roll = next(x for x in game.choices(ADMIN) if x["kind"] == FRAME_ROLL)
    assert game.dice.calls == 0
    rolled = game.respond(
        ADMIN, "frame-contact-roll", roll["id"], roll["revision"], ChoiceAnswer(flag=True)
    )
    assert (
        game.respond(
            ADMIN, "frame-contact-roll", roll["id"], roll["revision"], ChoiceAnswer(flag=True)
        )
        == rolled
    )
    assert game.dice.calls == 1
    ledger.engine.dispose()
    if level not in ("high", "interrupt"):
        item = next(x for x in game.choices(PLAYER) if x["kind"] == FRAME_DAMAGE)
        detail = game.decision(PLAYER, item["id"])["detail"]
        assert detail["faces"] == sides
        assert detail["bonus"] == len(already_void)
        assert detail["tier"] == ("high" if level == "interrupt" else level)
        with pytest.raises(WorkflowError, match="intact Asset"):
            answer(game, PLAYER, FRAME_DAMAGE, options=("another-original-asset",))
        if level == "mid":
            void = reserved.id if reserved else next(iter(detail["void_assets"]))
            answer(
                game,
                PLAYER,
                FRAME_DAMAGE,
                options=(frame.id,),
                flag=False,
                fields=dict(void_asset=void, void_description="Shadows gather in its surface."),
            )
        else:
            answer(game, PLAYER, FRAME_DAMAGE, options=(frame.id,))
        after_damage = state(game)
        assert next(x for x in after_damage.sheets["2"].assets if x.id == frame.id).damaged
        opened = next(
            x for x in after_damage.world.gorgons if x.id == original.actor.entity
        ).exposed
        assert opened == (level == "low")
        (record,) = results(after_damage)
        assert record.damaged_asset == frame.id
        assert record.roll.void_assets == tuple(x.id for x in already_void)
        if level == "mid":
            assert record.void_asset == void and record.punishment_if_discovered
            assert next(x for x in after_damage.sheets["2"].assets if x.id == void).void
            assert not after_damage.role_punishments
        if threshold:
            assert game.inspect(ADMIN, action)["state"] == "awaiting_choices"
            svc = VoidService(ledger)
            work = record.void_work
            assert work and svc.get(PLAYER, work)["stage"] == "resist_pending"
            original_sheet = state(game).sheets["2"]
            game.dice.faces = (1, 1)
            counter = game.begin(
                PLAYER,
                "resist-contact-threshold",
                900,
                original_sheet.revision,
                PlayInput(
                    play="keep_your_head",
                    source_work=work,
                    heat=0,
                    parent=action,
                    context="The original Girl resists the actual Frame threshold.",
                    trigger_confirmed=True,
                ),
            )["action_id"]
            tick(worker, gateway, 4)
            assert not game.choices(OTHER)
            with pytest.raises(WorkflowError, match="not visible"):
                game.inspect(OTHER, counter)
            for participant in (PLAYER, ADMIN):
                answer(game, participant, "tag_window", options=("pass",))
            answer(game, PLAYER, "actor_keep", options=("in_control",))
            answer(game, ADMIN, "handler_keep", flag=True, text="The actual resistance held.")
            tick(worker, gateway, 5)
            assert game.inspect(PLAYER, counter)["state"] == "complete"
            assert svc.get(PLAYER, work)["stage"] == "prevented"
            assert {recipient for recipient, _ in gateway.private} == {
                ADMIN.user_id,
                PLAYER.user_id,
            }
        assert game.inspect(ADMIN, action)["state"] == "complete"
    else:
        pending = next(x for x in game.choices(ADMIN) if x["kind"] == FRAME_CONSEQUENCE)
        detail = game.decision(ADMIN, pending["id"])["detail"]
        assert detail["faces"] == sides
        assert detail["bonus"] == len(already_void)
        assert detail["tier"] == ("high" if level == "interrupt" else level)
        with pytest.raises(WorkflowError, match="verified immediate outcome"):
            answer(game, ADMIN, FRAME_CONSEQUENCE, flag=True)
        assert game.inspect(ADMIN, action)["state"] == "awaiting_choices"
        assert state(game).sheets == before.sheets
        if level == "interrupt":
            monkeypatch.setattr(shared, "M3_HEAT_IDS", (*shared.M3_HEAT_IDS, "go_for_the_core"))
            answer(
                game,
                ADMIN,
                FRAME_CONSEQUENCE,
                options=("intervene",),
                text="The original Girl can make one immediate strike before the outcome.",
            )
            battle = BattleService(ledger)
            choices = battle.preview(PLAYER, 900)
            actor = next(x for x in choices["actors"] if x["owned"] and x["ref"]["kind"] == "pilot")
            gorgon = next(
                x for x in choices["actors"] if x["ref"]["entity"] == original.actor.entity
            )
            battle_request = BattleDeclaration(
                play="go_for_the_core",
                actor=original.target,
                target=original.actor,
                attacking_asset=actor["assets"][0]["id"],
                actor_sha256=actor["sha256"],
                target_sha256=gorgon["sha256"],
                account="The original Girl strikes the actual exposed Gorgon Core.",
            )
            context = battle.propose(
                PLAYER,
                "offer-intervention",
                choices["revision"],
                900,
                battle_request,
                parent=action,
            )["id"]
            battle.confirm(
                ADMIN,
                "review-intervention",
                state(game).revision,
                context,
                opening=True,
                reach=True,
                outside_permission=False,
                indirect=False,
                evidence="An actual exposed source Core within reach.",
            )
            game.dice.faces = (6, 6)
            strike = game.begin(
                PLAYER,
                "actual-intervention",
                900,
                state(game).sheets["2"].revision,
                PlayInput(
                    play="go_for_the_core",
                    heat=0,
                    piloting=True,
                    parent=action,
                    target_actor=original.actor,
                    attacking_asset=battle_request.attacking_asset,
                    battle_context=context,
                    context=battle_request.account,
                    trigger_confirmed=True,
                ),
            )["action_id"]
            tick(worker, gateway, 5)
            for participant in (PLAYER, ADMIN):
                answer(game, participant, "tag_window", options=("pass",))
            assert not game.choices(OTHER)
            tick(worker, gateway, 5)
            assert game.inspect(PLAYER, strike)["state"] == "complete"
            assert game.inspect(ADMIN, action)["state"] == "complete"
            assert game.inspect(ADMIN, action)["result"]["contact"] == "interrupted"
            after = state(game)
            assert not next(x for x in after.world.gorgons if x.id == original.actor.entity).alive
            assert after.sheets["2"].assets == before.sheets["2"].assets and not after.harpy_states
            assert not after.void_thresholds and game.dice.calls == 2
            assert {recipient for recipient, _ in gateway.private} == {
                ADMIN.user_id,
                PLAYER.user_id,
            }
            return
        answer(
            game,
            ADMIN,
            FRAME_CONSEQUENCE,
            flag=True,
            text="Both original actors survived the actual immediate aftermath.",
        )
        held = next(x for x in game.choices(PLAYER) if x["kind"] == FRAME_VOID)
        work = game.decision(PLAYER, held["id"])["detail"]["work"]
        svc = VoidService(ledger)
        saved = svc.get(PLAYER, work)
        assert saved["stage"] == "rebirth" and not saved["threshold"]["answers"]
        with pytest.raises(WorkflowError, match="private Void"):
            svc.get(OTHER, work)
        choice = saved["rebirth_choice"] | dict(
            new_identities=["Streetlights"],
            account="The original Girl authors her changed self.",
        )
        respond_void(svc, work, "save_rebirth", dict(choice=choice, account=choice["account"]))
        ledger.engine.dispose()
        assert svc.get(PLAYER, work)["rebirth_choice"] == choice
        start = svc.get(PLAYER, work)
        response = respond_void(
            svc,
            work,
            "rebirth",
            dict(choice=choice, account=choice["account"]),
            key="contact-rebirth",
            view=start,
        )
        assert (
            respond_void(
                svc,
                work,
                "rebirth",
                dict(choice=choice, account=choice["account"]),
                key="contact-rebirth",
                view=start,
            )
            == response
        )
        canon = state(game)
        assert original.target.entity not in canon.sheets
        (harpy,) = canon.harpy_states
        assert harpy.origin == original.target
        assert {x.id for x in harpy.assets} == {x.id for x in before.sheets["2"].assets}
        assert any(x.name == "Streetlights" for x in harpy.identities)
        assert game.inspect(ADMIN, action)["state"] == "complete"
    assert state(game).sheets["3"] == before.sheets["3"]
    assert not game.choices(OTHER)

    if level == "mid" and not threshold:
        tick(worker, gateway, 5)
        inbox = InboxService(ledger)
        report = FrameContactDisclosureService(game)
        assert not any(x.task == "m3_gorgon_contact_report" for x in inbox.items(PLAYER))
        cast = CastService(ActorService(MissionService(ledger)))
        handler_role = active_handler(state(game))
        change(cast, ADMIN, "join", handler_role)
        offered = next(x for x in inbox.items(PLAYER) if x.task == "m3_gorgon_contact_report")
        assert offered.identity == action
        assert not any(x.task == offered.task for x in inbox.items(OTHER))
        assert not any(x.task == offered.task for x in inbox.items(ADMIN))
        ready = report.menu(PLAYER, action)
        scene = ready["scenes"][0][0]
        with pytest.raises(WorkflowError, match="original private report"):
            report.report(OTHER, "not-my-disclosure", action, ready["revision"], scene)
        with pytest.raises(WorkflowError, match="STALE_REPORT"):
            report.report(PLAYER, "stale-report", action, ready["revision"] - 1, scene)
        assert not [x for x in state(game).obligations if x.details.get("cause") == KIND]

        async def disclose():
            handoff = current(PLAYER.user_id, 87500)
            await handoff.response.defer(ephemeral=True)
            await open_report(handoff, report, action)
            form = handoff.edit_original_response.call_args.kwargs["view"]
            form.values.update(scene=(scene,))
            await form.confirm.callback(current(PLAYER.user_id, 87501))
            assert form.completed

        asyncio.run(disclose())
        delivered = report.report(PLAYER, "87501", action, ready["revision"], scene)
        (punishment,) = [x for x in state(game).obligations if x.details.get("cause") == KIND]
        assert punishment.target == ADMIN.user_id and punishment.owner == PLAYER.user_id
        assert (
            punishment.action == action and punishment.details["disclosure"] == delivered["event"]
        )
        (known,) = [x for x in state(game).facts if x.get("kind") == KIND]
        assert known["recipient"] == handler_role.model_dump_json()
        assert not any(x.task == offered.task for x in inbox.items(PLAYER))


@pytest.mark.parametrize(
    "faces,tier,choices",
    [
        ((3, 4), "mid", ("trapped",)),
        ((5, 5), "high", ("cockpit",)),
        ((1, 2), "low", ("trapped", "void")),
        ((3, 4), "mid", ("void",)),
    ],
)
def test_sentinel_shell_real_owned_roll_and_physical_consequences(ledger, faces, tier, choices):
    import asyncio

    from test_ledger import OTHER
    from test_m2_game import Dice, pass_tags
    from test_mission_ui import current

    from girlframe.discord_adapter.m3_gorgon_runtime import open_choice
    from girlframe.engine.m2 import ChoiceAnswer, PlayInput
    from girlframe.engine.m3_actor_bonds import current_ref
    from girlframe.engine.m3_actors import resolve
    from girlframe.engine.m3_battle_state import Declaration as BattleDeclaration
    from girlframe.engine.m3_physical_state import CockpitAction
    from girlframe.engine.m3_sentinel_shell import holds, records, shell_intact
    from girlframe.engine.m3_world import damage_gorgon, expose_gorgon
    from girlframe.services.m3_actors import profiles
    from girlframe.services.m3_battle import BattleService
    from girlframe.services.m3_movement import MovementService
    from girlframe.services.m3_physical import PhysicalService
    from girlframe.services.m3_sentinel_shell import CHOOSE, HEAT, TIE, VOID
    from girlframe.services.m3_void import VoidService
    from girlframe.services.onboarding import WorkflowError

    threshold = choices == ("void",)
    game, worker, gateway, _, original = gorgon_source(
        ledger,
        kind="sentinel_withdraw",
        types=("sentinel",),
        other_cell=(1, 0) if tier != "mid" else (0, 0),
        exposed=True,
        begin=False,
    )
    game.dice = Dice(faces)
    reserved = None
    with ledger.transaction() as c:
        canon = state(game)
        canon.sheets["2"].heat = 2
        if threshold:
            frame_assets = [x for x in canon.sheets["2"].assets if x.family == "frame"]
            reserved = frame_assets[-1].id
            for asset in frame_assets[:-1]:
                asset.void = True
                asset.description = "Earlier fictional corruption"
        game.event(c, PLAYER.user_id, "synthetic-shell-heat", "synthetic.heat", canon)
    before = state(game)
    svc = GorgonPlayService(game)
    caller, girl = original.actor, original.target
    outsider = current_ref(before, OTHER.user_id)
    data = svc.preview(ADMIN, 900)
    resources = {x["token"]: x for x in data["actors"]}
    targets = data["typed_targets"][caller.token]["sentinel_withdraw"]
    assert girl.token in targets
    declared = original.model_copy(
        update=dict(target_sha256=resources[girl.token]["source_sha256"])
    )
    if tier != "mid":
        assert targets == [girl.token]
        with pytest.raises(WorkflowError, match="closest original Girl"):
            svc.begin(
                ADMIN,
                "wrong-nearest",
                900,
                before.revision,
                declared.model_copy(
                    update=dict(
                        target=outsider,
                        target_sha256=resources[outsider.token]["source_sha256"],
                    )
                ),
            )
    action = svc.begin(ADMIN, "sentinel-withdraw", 900, before.revision, declared)["action_id"]
    tick(worker, gateway, 5)
    if not any(
        x["kind"] in (HEAT, TIE) for viewer in (PLAYER, ADMIN) for x in game.choices(viewer)
    ):
        game.roll(ADMIN, "advance-sentinel", action)
    if tier == "mid":
        assert not game.choices(PLAYER) and len(targets) == 2
        answer(game, ADMIN, TIE, flag=True, text="The actual reach resolves the tied target.")
    row = next(x for x in game.choices(PLAYER) if x["kind"] == HEAT)
    with pytest.raises(WorkflowError, match="another player"):
        game.respond(
            OTHER, "forged-sentinel-heat", row["id"], row["revision"], ChoiceAnswer(number=1)
        )

    async def native_heat():
        handoff = current(PLAYER.user_id, 87600)
        await handoff.response.defer(ephemeral=True)
        await open_choice(handoff, game, row["id"])
        form = handoff.edit_original_response.call_args.kwargs["view"]
        form.values.update(heat="1")
        await form.confirm.callback(current(PLAYER.user_id, 87601))
        assert form.completed

    asyncio.run(native_heat())
    game.respond(PLAYER, "87601", row["id"], row["revision"], ChoiceAnswer(number=1))
    assert game.dice.calls == 1 and state(game).sheets["2"].heat == 1
    chooser = PLAYER if tier == "mid" else ADMIN
    pending = next(x for x in game.choices(chooser) if x["kind"] == CHOOSE)
    ledger.engine.dispose()
    detail = game.decision(chooser, pending["id"])["detail"]
    assert detail["tier"] == tier and detail["roll"]["faces"] == list(faces)
    assert detail["count"] == len(choices)
    answer(game, chooser, CHOOSE, options=choices, text="The original Sentinel ensnares the Girl.")
    if "void" in choices:
        owned = next(x for x in game.choices(PLAYER) if x["kind"] == VOID)
        fields = game.decision(PLAYER, owned["id"])["detail"]
        asset = reserved or next(iter(fields["assets"]))
        answer(game, PLAYER, VOID, options=(asset,), text="It takes on a dark iridescence.")
        assert next(x for x in state(game).sheets["2"].assets if x.id == asset).void
    if threshold:
        current_state = state(game)
        (source,) = records(current_state)
        work = source.void_work
        assert work and game.inspect(ADMIN, action)["state"] == "awaiting_choices"
        service = VoidService(ledger)
        assert service.get(PLAYER, work)["stage"] == "resist_pending"
        game.dice.faces = (1, 1)
        child = game.begin(
            PLAYER,
            "resist-shell-void",
            900,
            current_state.sheets["2"].revision,
            PlayInput(
                play="keep_your_head",
                source_work=work,
                heat=0,
                parent=action,
                context="The original Girl resists the actual Void threshold.",
                trigger_confirmed=True,
            ),
        )["action_id"]
        tick(worker, gateway, 5)
        pass_tags(game)
        answer(game, PLAYER, "actor_keep", options=("in_control",))
        answer(game, ADMIN, "handler_keep", flag=True, text="The actual resistance held.")
        assert game.inspect(PLAYER, child)["state"] == "complete"
        assert service.get(PLAYER, work)["stage"] == "prevented"
    tick(worker, gateway, 5)
    after = state(game)
    assert game.inspect(ADMIN, action)["state"] == "complete"
    assert game.dice.calls == (2 if threshold else 1)
    (record,) = records(after)
    assert record.girl == girl and record.source == caller and record.effects == choices
    body = next(x for x in after.world.gorgons if x.id == caller.entity)
    assert shell_intact(body) == (tier != "mid")
    assert body.exposed == (tier == "mid")
    assert after.sheets["3"] == before.sheets["3"]
    for effect in ("cockpit", "trapped"):
        assert holds(after, girl, effect) == (effect in choices)
        assert not holds(after, outsider, effect)

    if "trapped" in choices:
        with pytest.raises(WorkflowError, match="cannot spend Heat"):
            game.begin(
                PLAYER,
                "cannot-spend",
                900,
                after.sheets["2"].revision,
                PlayInput(
                    play="keep_your_head",
                    heat=1,
                    context="I try to break free.",
                    trigger_confirmed=True,
                ),
            )
        with pytest.raises(WorkflowError, match="needs assistance"):
            MovementService(game).move(
                PLAYER,
                "cannot-leave",
                after.revision,
                900,
                girl,
                (1, 0),
                account="The original Girl tries to leave.",
            )
    if "cockpit" in choices:
        with ledger.engine.connect() as c:
            actual = resolve(after, girl, profiles(c, ledger.campaign_id))
        assert actual.piloting is False and actual.inside_frame is True
        command = CockpitAction(
            actor=girl,
            operation="pilot",
            expected_position=actual.position_sha256,
            account="I try to resume piloting.",
            confirmed=True,
        )
        with pytest.raises(WorkflowError, match="containment"):
            PhysicalService(ledger).operate(
                PLAYER, "cannot-pilot", after.revision, command, channel=900
            )
    if record.shell_asset:
        with pytest.raises(ValueError, match="Crack the original Sentinel shell"):
            expose_gorgon(after.world, caller.entity, "Ordinary vulnerability")
        if tier == "high":
            ledger.policy = ledger.policy.model_copy(
                update={"owner_table_outcomes": "gm_discretion"}
            )
            battle = BattleService(ledger)
            scene = battle.preview(OTHER, 900)
            pilot = next(x for x in scene["actors"] if x["owned"] and x["ref"]["kind"] == "pilot")
            gorgon = next(x for x in scene["actors"] if x["ref"]["entity"] == caller.entity)
            planned = BattleDeclaration(
                play="all_out_assault",
                actor=outsider,
                target=caller,
                attacking_asset=pilot["assets"][0]["id"],
                target_asset=record.shell_asset,
                actor_sha256=pilot["sha256"],
                target_sha256=gorgon["sha256"],
                account="I crack the actual barrier over the Shell.",
            )
            context = battle.propose(OTHER, "strike-shell", scene["revision"], 900, planned)["id"]
            battle.confirm(
                ADMIN,
                "review-shell-strike",
                state(game).revision,
                context,
                opening=True,
                reach=True,
                outside_permission=False,
                indirect=False,
                evidence="The original barrier is physically reachable.",
            )
            game.dice.faces = (4, 5)
            strike = game.begin(
                OTHER,
                "crack-shell",
                900,
                after.sheets["3"].revision,
                PlayInput(
                    play="all_out_assault",
                    heat=0,
                    piloting=True,
                    target_actor=caller,
                    attacking_asset=planned.attacking_asset,
                    target_asset=planned.target_asset,
                    battle_context=context,
                    context=planned.account,
                    trigger_confirmed=True,
                ),
            )["action_id"]
            tick(worker, gateway, 4)
            pass_tags(game)
            answer(
                game, ADMIN, "battle_gm_table", flag=False, text="The actual Shell can be cracked."
            )
            tick(worker, gateway, 5)
            assert game.inspect(OTHER, strike)["state"] == "complete"
        else:
            with ledger.transaction() as c:
                canon = state(game)
                canon.world = damage_gorgon(
                    canon.world, caller.entity, record.shell_asset, indirect=False
                )
                game.event(
                    c, OTHER.user_id, "synthetic-crack-shell", "synthetic.shell_cracked", canon
                )
        held = state(game)
        assert not holds(held, girl, "trapped") and not holds(held, girl, "cockpit")
        if "cockpit" in choices:
            PhysicalService(ledger).operate(
                PLAYER, "pilot-after-crack", held.revision, command, channel=900
            )

    if tier == "mid" and "trapped" in choices:
        preview = svc.preview(ADMIN, 900)
        rows = {x["token"]: x for x in preview["actors"]}
        assert preview["typed_targets"][caller.token]["sentinel_release"] == [girl.token]
        let_go = Declaration(
            kind="sentinel_release",
            actor=caller,
            target=girl,
            actor_sha256=rows[caller.token]["source_sha256"],
            target_sha256=rows[girl.token]["source_sha256"],
            account="The original Sentinel releases its actual captive.",
            reach_confirmed=True,
        )
        response = svc.begin(ADMIN, "release-shell-captive", 900, preview["revision"], let_go)
        tick(worker, gateway, 5)
        if holds(state(game), girl, "trapped"):
            game.roll(ADMIN, "advance-captive-release", response["action_id"])
            tick(worker, gateway, 5)
        (released,) = records(state(game))
        assert released.released and released.event == record.event
        assert not holds(state(game), girl, "trapped")
        moved = MovementService(game).move(
            PLAYER,
            "move-after-captive-release",
            state(game).revision,
            900,
            girl,
            (1, 0),
            frame=True,
            account="The original Girl moves her Frame after the release.",
        )
        assert moved["destination"] == [1, 0] and game.dice.calls == 1


@pytest.mark.parametrize(
    "erase,tier", [(False, "mid"), (True, "mid"), (False, "high"), (False, "low")]
)
def test_incubus_marks_only_its_actual_known_tag_and_the_girl_owns_results(ledger, erase, tier):
    import asyncio

    from test_ledger import OTHER
    from test_m2_game import Dice
    from test_mission_ui import current
    from test_privacy_game_delivery import PrivateGateway
    from test_void_service import respond as respond_void

    from girlframe.discord_adapter.m3_gorgon_play import open_gorgon_play
    from girlframe.discord_adapter.m3_gorgon_runtime import open_choice
    from girlframe.engine.m2 import ChoiceAnswer, PlayInput, TagState
    from girlframe.engine.m3_handler_consequences import active_handler
    from girlframe.engine.m3_incubus_conditioning import get
    from girlframe.services.m3_incubus_conditioning import ERASE, HEAT, REVIEW, THRESHOLD, VOID
    from girlframe.services.m3_void import VoidService
    from girlframe.services.onboarding import WorkflowError

    game, worker, gateway, initial, applied = gorgon_source(
        ledger,
        kind="incubus_inflict",
        types=("incubus",),
        tag="touch",
    )
    tick(worker, gateway, 5)
    assert game.inspect(ADMIN, initial)["state"] == "complete"
    gateway = PrivateGateway()
    game.dice = Dice(dict(mid=(3, 4), high=(5, 5), low=(1, 2))[tier])
    hidden = "private-other-role"
    with ledger.transaction() as c:
        canon = state(game)
        original_sheet = canon.sheets["2"]
        original_sheet.heat = 2
        original_sheet.tags.append(
            TagState(
                id=hidden,
                label="Different Role's Knowledge",
                giver=ADMIN.user_id,
                giver_actor=active_handler(canon),
                observers=(1, 2),
            )
        )
        game.event(c, ADMIN.user_id, "synthetic-incubus-heat", "synthetic.heat", canon)
    before = state(game)
    actual_tag = next(x for x in before.sheets["2"].tags if x.giver_actor == applied.actor)
    service = GorgonPlayService(game)
    view = service.preview(ADMIN, 900)
    assert view["conditioning_tags"][applied.actor.token] == {
        applied.target.token: [(actual_tag.id, actual_tag.label)]
    }
    people = {x["token"]: x for x in view["actors"]}
    declared = Declaration(
        kind="incubus_conditioning",
        actor=applied.actor,
        target=applied.target,
        actor_sha256=people[applied.actor.token]["source_sha256"],
        target_sha256=people[applied.target.token]["source_sha256"],
        tag=actual_tag.id,
        account="The Incubus uses its original known Tag.",
        reach_confirmed=True,
    )
    with pytest.raises(WorkflowError, match="actual unmarked Tag"):
        service.begin(
            ADMIN,
            "unknown-to-incubus",
            900,
            before.revision,
            declared.model_copy(update=dict(tag=hidden)),
        )

    async def native():
        start = current(ADMIN.user_id, 87700)
        start.channel_id = 900
        await start.response.defer(ephemeral=True)
        await open_gorgon_play(start, game)
        form = start.edit_original_response.call_args.kwargs["view"]
        form.values.update(actor=(applied.actor.token,), play=("incubus_conditioning",))
        selected = current(ADMIN.user_id, 87701)
        await selected.response.defer(ephemeral=True)
        await form.confirm.callback(selected)
        details = selected.edit_original_response.call_args.kwargs["view"]
        options = next(x for x in details.fields if x.key == "known_tag").options
        assert len(options) == 1 and actual_tag.label in options[0][1]
        details.values.update(
            known_tag=(options[0][0],), account=declared.account, reach=("confirmed",)
        )
        await details.confirm.callback(current(ADMIN.user_id, 87702))
        assert details.completed

    asyncio.run(native())
    action = service.begin(ADMIN, "87702", 900, before.revision, declared)["action_id"]
    tick(worker, gateway, 5)
    if not any(x["kind"] == HEAT for x in game.choices(PLAYER)):
        game.roll(ADMIN, "advance-incubus", action)
    chosen = next(x for x in state(game).sheets["2"].tags if x.id == actual_tag.id)
    assert chosen.marked and game.dice.calls == 0
    assert not next(x for x in state(game).sheets["2"].tags if x.id == hidden).marked
    step = next(x for x in game.choices(PLAYER) if x["kind"] == HEAT)
    ledger.safety(OTHER, "pause-conditioning", ledger.status(OTHER)["revision"], pause=True)
    with pytest.raises(WorkflowError, match="SAFETY_PAUSED"):
        game.respond(PLAYER, "paused-heat", step["id"], step["revision"], ChoiceAnswer(number=1))
    ledger.safety(OTHER, "resume-conditioning", ledger.status(OTHER)["revision"], pause=False)
    with pytest.raises(WorkflowError, match="another player"):
        game.respond(OTHER, "wrong-heat", step["id"], step["revision"], ChoiceAnswer(number=1))
    rolled = game.respond(PLAYER, "pay-heat", step["id"], step["revision"], ChoiceAnswer(number=1))
    assert (
        game.respond(PLAYER, "pay-heat", step["id"], step["revision"], ChoiceAnswer(number=1))
        == rolled
    )
    assert game.dice.calls == 1 and state(game).sheets["2"].heat == 1
    ledger.engine.dispose()
    if tier == "low":
        review = next(x for x in game.choices(ADMIN) if x["kind"] == REVIEW)
        assert game.decision(ADMIN, review["id"])["detail"]["can_transform"]
        with pytest.raises(WorkflowError, match="verify the immediate original"):
            answer(game, ADMIN, REVIEW, flag=True)
        answer(
            game,
            ADMIN,
            REVIEW,
            flag=True,
            text="The original Girl remained conscious, alive and free in her Frame.",
        )
        choice = next(x for x in game.choices(PLAYER) if x["kind"] == THRESHOLD)
        work = game.decision(PLAYER, choice["id"])["detail"]["work"]
        service = VoidService(ledger)
        pending = service.get(PLAYER, work)
        assert pending["stage"] == "rebirth" and not pending["threshold"]["answers"]
        assert game.inspect(PLAYER, action)["state"] == "awaiting_choices"
        with pytest.raises(WorkflowError, match="private Void"):
            service.get(OTHER, work)
        rewrite = pending["rebirth_choice"] | dict(
            new_identities=["Soft Static"],
            account="I author my actual original transformation.",
        )
        respond_void(service, work, "rebirth", dict(choice=rewrite, account=rewrite["account"]))
        reborn = state(game)
        (harpy,) = reborn.harpy_states
        assert harpy.origin == applied.target and "2" not in reborn.sheets
        assert any(x.name == "Soft Static" for x in harpy.identities)
        assert game.inspect(ADMIN, action)["state"] == "complete" and game.dice.calls == 1
        assert reborn.sheets["3"] == before.sheets["3"]
        return
    if tier == "high":
        gain = next(x for x in game.choices(PLAYER) if x["kind"] == VOID)
        detail = game.decision(PLAYER, gain["id"])["detail"]
        asset = next(iter(detail["assets"]))
        result = answer(
            game, PLAYER, VOID, options=(asset,), text="It begins to pulse in darkness."
        )
        assert result["action_id"] == action
        interim = state(game)
        assert next(x for x in interim.sheets["2"].assets if x.id == asset).void
        assert get(interim, action).void_asset == asset and get(interim, action).completed is None
        assert game.inspect(PLAYER, action)["state"] == "awaiting_choices"
        game.dice.faces = (3, 4)
        child = game.begin(
            PLAYER,
            "act-on-incubus-tag",
            900,
            interim.sheets["2"].revision,
            PlayInput(
                play="keep_your_head",
                heat=0,
                parent=action,
                context="I act on the actual marked Tag while trying to keep control.",
                trigger_confirmed=True,
            ),
        )["action_id"]
        tick(worker, gateway, 5)
        assert not game.choices(OTHER)
        with pytest.raises(WorkflowError, match="not visible"):
            game.inspect(OTHER, child)
        for participant in (PLAYER, ADMIN):
            answer(game, participant, "tag_window", options=("pass",))
        answer(game, PLAYER, "actor_keep", options=("in_control",))
        answer(game, ADMIN, "handler_keep", flag=True, text="The actual response held.")
        tick(worker, gateway, 5)
        after = state(game)
        committed = get(after, action)
        assert committed.child == child and committed.completed and committed.roll.result == "high"
        assert not committed.tag_erased and game.dice.calls == 2
        assert game.inspect(ADMIN, action)["state"] == "complete"
        assert {recipient for recipient, _ in gateway.private} == {ADMIN.user_id, PLAYER.user_id}
        return
    finish = next(x for x in game.choices(PLAYER) if x["kind"] == ERASE)

    async def owned():
        handoff = current(PLAYER.user_id, 87703)
        await handoff.response.defer(ephemeral=True)
        await open_choice(handoff, game, finish["id"])
        form = handoff.edit_original_response.call_args.kwargs["view"]
        form.values.update(choice=("yes" if erase else "no",))
        await form.confirm.callback(current(PLAYER.user_id, 87704))
        assert form.completed

    asyncio.run(owned())
    after = state(game)
    committed = get(after, action)
    assert committed.girl == applied.target and committed.tag == actual_tag.id
    assert committed.roll.result == "mid" and committed.tag_erased == erase and committed.completed
    assert (actual_tag.id in {x.id for x in after.sheets["2"].tags}) is not erase
    assert after.sheets["3"] == before.sheets["3"]
    assert game.inspect(ADMIN, action)["state"] == "complete"
    with pytest.raises(WorkflowError, match="original source-table"):
        game.inspect(OTHER, action)
    tick(worker, gateway, 5)
    assert {recipient for recipient, _ in gateway.private} == {ADMIN.user_id, PLAYER.user_id}


@pytest.mark.parametrize(
    "faces,choices,threshold",
    [
        ((3, 4), ("cockpit",), False),
        ((3, 4), ("distance",), False),
        ((5, 5), ("thoughts", "reinforce"), False),
        ((5, 5), ("thoughts", "reinforce"), True),
        ((1, 2), ("tree", "underground", "time", "fill_square"), False),
    ],
)
def test_grow_unreal_pays_original_asset_and_applies_owned_tier_choices(
    ledger, faces, choices, threshold
):
    import asyncio

    from test_ledger import OTHER
    from test_m2_game import Dice, pass_tags
    from test_mission_ui import current

    from girlframe.discord_adapter.m3_gorgon_play import open_gorgon_play
    from girlframe.engine.m2 import ChoiceAnswer, PlayInput
    from girlframe.engine.m3_grow_unreal import get
    from girlframe.services.m3_grow_unreal import DAMAGE, GROW, HEAT, VOID
    from girlframe.services.m3_void import VoidService
    from girlframe.services.onboarding import WorkflowError

    far = "distance" in choices
    viewer = OTHER if far else PLAYER
    game, worker, gateway, _, original = gorgon_source(
        ledger,
        types=("growth",),
        target=str(viewer.user_id),
        other_cell=(2, 0),
        begin=False,
    )
    game.dice = Dice(faces)
    reserved = None
    with ledger.transaction() as c:
        canon = state(game)
        sheet = canon.sheets[str(viewer.user_id)]
        sheet.heat = 2
        if threshold:
            frame_assets = [x for x in sheet.assets if x.family == "frame"]
            reserved = frame_assets[-1].id
            for item in frame_assets[:-1]:
                item.void = True
        game.event(c, viewer.user_id, "synthetic-growth-heat", "synthetic.heat", canon)
    before = state(game)
    parent = next(x for x in before.world.gorgons if x.id == original.actor.entity)
    sacrifice = parent.assets[-1].id
    svc = GorgonPlayService(game)
    selection = svc.preview(ADMIN, 900)
    source_rows = {x["token"]: x for x in selection["actors"]}
    assert sacrifice in selection["shed_assets"][original.actor.token]
    declared = Declaration(
        kind="grow_unreal",
        actor=original.actor,
        target=original.target,
        shed=sacrifice,
        actor_sha256=source_rows[original.actor.token]["source_sha256"],
        target_sha256=source_rows[original.target.token]["source_sha256"],
        account="The original Growth sheds an Asset before approaching.",
        reach_confirmed=True,
    )
    with pytest.raises(WorkflowError, match="Growth Asset"):
        svc.begin(
            ADMIN,
            "not-a-growth-asset",
            900,
            before.revision,
            declared.model_copy(update=dict(shed="someone-elses-asset")),
        )

    async def native():
        home = current(ADMIN.user_id, 87800)
        home.channel_id = 900
        await home.response.defer(ephemeral=True)
        await open_gorgon_play(home, game)
        form = home.edit_original_response.call_args.kwargs["view"]
        form.values.update(actor=(original.actor.token,), play=("grow_unreal",))
        selected = current(ADMIN.user_id, 87801)
        await selected.response.defer(ephemeral=True)
        await form.confirm.callback(selected)
        details = selected.edit_original_response.call_args.kwargs["view"]
        details.values.update(
            target=(original.target.token,),
            shed=(sacrifice,),
            account=declared.account,
            reach=("confirmed",),
        )
        await details.confirm.callback(current(ADMIN.user_id, 87802))
        assert details.completed

    asyncio.run(native())
    action = svc.begin(ADMIN, "87802", 900, before.revision, declared)["action_id"]
    tick(worker, gateway, 5)
    if not any(
        x["kind"] in (HEAT, "gorgon_asset_capability")
        for user in (ADMIN, viewer)
        for x in game.choices(user)
    ):
        game.roll(ADMIN, "advance-grow-unreal", action)
    if far:
        assert not any(x["kind"] == HEAT for x in game.choices(viewer))
        answer(
            game,
            ADMIN,
            "gorgon_asset_capability",
            flag=True,
            text="The original Growth can actually reach the original distant Girl.",
        )
    retired = next(x for x in state(game).world.gorgons if x.id == parent.id)
    assert {x.id for x in retired.assets} == {x.id for x in parent.assets} - {sacrifice}
    assert any(x.id == sacrifice for x in retired.destroyed_assets) and game.dice.calls == 0
    row = next(x for x in game.choices(viewer) if x["kind"] == HEAT)
    accepted = ChoiceAnswer(number=1)
    saved = game.respond(viewer, "grow-heat", row["id"], row["revision"], accepted)
    assert game.respond(viewer, "grow-heat", row["id"], row["revision"], accepted) == saved
    ledger.engine.dispose()
    owned = next(x for x in game.choices(ADMIN) if x["kind"] == GROW)
    view = game.decision(ADMIN, owned["id"])["detail"]
    assert view["count"] == len(choices) and view["roll"]["faces"] == list(faces)
    options = {"guard": next(iter(view["guards"]))} if "reinforce" in choices else {}
    with pytest.raises(WorkflowError, match="rolled number"):
        answer(game, ADMIN, GROW, text="Too few choices.", options=())
    answer(
        game,
        ADMIN,
        GROW,
        text="The Growth changes form in the chosen order.",
        options=choices,
        fields=options,
    )
    if "thoughts" in choices:
        item = next(x for x in game.choices(viewer) if x["kind"] == VOID)
        detail = game.decision(viewer, item["id"])["detail"]
        voided = reserved or next(iter(detail["assets"]))
        assert game.inspect(ADMIN, action)["state"] == "awaiting_choices"
        answer(game, viewer, VOID, options=(voided,), text="The material echoes what the Girl saw.")
        if threshold:
            saved_case = get(state(game), action)
            work = saved_case.void_work
            assert work and game.inspect(ADMIN, action)["state"] == "awaiting_choices"
            assert not any(x["kind"] == DAMAGE for x in game.choices(viewer))
            void_service = VoidService(ledger)
            assert void_service.get(viewer, work)["stage"] == "resist_pending"
            game.dice.faces = (1, 1)
            child = game.begin(
                viewer,
                "grow-resistance",
                900,
                state(game).sheets["2"].revision,
                PlayInput(
                    play="keep_your_head",
                    heat=0,
                    parent=action,
                    source_work=work,
                    context="I resist the actual Growth-corrupted Frame.",
                    trigger_confirmed=True,
                ),
            )["action_id"]
            tick(worker, gateway, 5)
            pass_tags(game)
            answer(game, viewer, "actor_keep", options=("in_control",))
            answer(game, ADMIN, "handler_keep", flag=True, text="The resistance was sufficient.")
            tick(worker, gateway, 5)
            assert game.inspect(viewer, child)["state"] == "complete"
            assert void_service.get(viewer, work)["stage"] == "prevented"
        offered = next(x for x in game.choices(viewer) if x["kind"] == DAMAGE)
        extra = game.decision(viewer, offered["id"])["detail"]
        exact = next(iter(extra["assets"]))
        answer(game, viewer, DAMAGE, options=(exact,))
        updated = state(game)
        original_girl = updated.sheets[str(viewer.user_id)]
        assert next(x for x in original_girl.assets if x.id == voided).void
        mutated = next(x for x in updated.world.gorgons if x.id == parent.id)
        assert options["guard"] in mutated.core_plan.assets
        assert next(x for x in mutated.assets if x.id == exact).damaged
    canon = state(game)
    record = get(canon, action)
    assert (
        record.completed is not None
        and record.options == choices
        and record.sacrificed == sacrifice
    )
    assert game.inspect(ADMIN, action)["state"] == "complete"
    assert game.dice.calls == (2 if threshold else 1)
    if far:
        assert next(x for x in canon.world.gorgons if x.id == parent.id).cell == (2, 0)
    if "cockpit" in choices:
        assert record.frame_instance == canon.placements[0].frame_instance


@pytest.mark.parametrize("tier", ("no_connection", "mid", "high", "high_threshold", "low"))
def test_parasite_infect_damages_an_actual_voided_asset_before_the_owned_roll(ledger, tier):
    import asyncio

    from test_ledger import OTHER
    from test_m2_game import Dice
    from test_mission_ui import current
    from test_privacy_game_delivery import PrivateGateway

    from girlframe.discord_adapter.m2_ui import open_choice
    from girlframe.discord_adapter.m3_gorgon_runtime import open_excision
    from girlframe.engine.m2 import ChoiceAnswer, PlayInput
    from girlframe.engine.m3_parasite_infection import get
    from girlframe.engine.m3_world_state import Npc
    from girlframe.services.inbox import InboxService
    from girlframe.services.m3_parasite_excision import ExcisionService
    from girlframe.services.m3_parasite_infection import DAMAGE, HEAT, LOSS, LOW_REVIEW, VOID
    from girlframe.services.m3_void import VoidService
    from girlframe.services.onboarding import WorkflowError

    game, worker, _, _, original = gorgon_source(
        ledger,
        types=("parasite",),
        target="2",
        begin=False,
    )
    gateway = PrivateGateway()
    game.dice = Dice((1, 2) if tier == "low" else (5, 5) if tier.startswith("high") else (3, 4))
    with ledger.transaction() as c:
        canon = state(game)
        sheet = canon.sheets["2"]
        sheet.heat = 2
        connection = next(x for x in sheet.assets if x.family == "girl")
        connection.void = tier != "no_connection"
        frame = [x for x in sheet.assets if x.family == "frame"]
        if tier == "high_threshold":
            for x in frame[:-1]:
                x.void = True
        if tier == "high":
            canon.world = update(
                canon.world,
                npcs=(
                    Npc(
                        id="actual-ward-doctor",
                        name="Ward Doctor",
                        jobs=("doctor",),
                        detail="The original available doctor",
                        controller=ADMIN.user_id,
                        cell=(0, 0),
                        revealed=True,
                    ),
                ),
            )
        game.event(c, PLAYER.user_id, "synthetic-infection-connection", "synthetic.void", canon)
    if tier == "high":
        cast = CastService(ActorService(MissionService(ledger)))
        change(cast, ADMIN, "join", ActorRef(kind="npc", entity="actual-ward-doctor"))
    initial = state(game)
    service = GorgonPlayService(game)
    view = service.preview(ADMIN, 900)
    people = {x["token"]: x for x in view["actors"]}
    assert people[original.target.token]["assets"] == []
    assert original.target.token in view["typed_targets"][original.actor.token]["parasite_infect"]
    declared = Declaration(
        kind="parasite_infect",
        actor=original.actor,
        target=original.target,
        actor_sha256=people[original.actor.token]["source_sha256"],
        target_sha256=people[original.target.token]["source_sha256"],
        account="The Parasite reaches toward the original Girl.",
        reach_confirmed=True,
    )
    parent = service.begin(ADMIN, "infect-actual-girl", 900, initial.revision, declared)[
        "action_id"
    ]
    tick(worker, gateway, 5)
    if not any(x["kind"] == DAMAGE for x in game.choices(PLAYER)):
        game.roll(ADMIN, "advance-infection", parent)
    assert game.dice.calls == 0
    damage = next(x for x in game.choices(PLAYER) if x["kind"] == DAMAGE)
    with pytest.raises(WorkflowError):
        game.decision(OTHER, damage["id"])
    with pytest.raises(WorkflowError, match="Voided Asset"):
        answer(game, PLAYER, DAMAGE, options=("fake-asset",))

    async def native_damage():
        interaction = current(PLAYER.user_id, 87903)
        await interaction.response.defer(ephemeral=True)
        await open_choice(interaction, game, damage["id"])
        form = interaction.edit_original_response.call_args.kwargs["view"]
        if tier != "no_connection":
            form.values["options"] = (connection.id,)
        else:
            form.values["no_connection"] = ("confirm",)
        await form.confirm.callback(current(PLAYER.user_id, 87904))
        assert form.completed

    asyncio.run(native_damage())
    if tier == "no_connection":
        case = get(state(game), parent)
        assert case.interrupted is not None and game.dice.calls == 0
        assert game.inspect(PLAYER, parent)["state"] == "complete"
        return
    after_damage = state(game)
    assert next(x for x in after_damage.sheets["2"].assets if x.id == connection.id).damaged
    assert after_damage.sheets["2"].heat == 2 and game.dice.calls == 0
    heat = next(x for x in game.choices(PLAYER) if x["kind"] == HEAT)
    if tier == "mid":
        ledger.safety(PLAYER, "pause-infection", ledger.status(PLAYER)["revision"], pause=True)
        with pytest.raises(WorkflowError, match="SAFETY_PAUSED"):
            game.respond(
                PLAYER, "held-infection", heat["id"], heat["revision"], ChoiceAnswer(number=1)
            )
        assert game.dice.calls == 0
        ledger.safety(PLAYER, "resume-infection", ledger.status(PLAYER)["revision"], pause=False)
    with pytest.raises(WorkflowError):
        game.respond(
            PLAYER, "stale-infection", heat["id"], heat["revision"] - 1, ChoiceAnswer(number=1)
        )
    response = game.respond(
        PLAYER, "owned-infection-roll", heat["id"], heat["revision"], ChoiceAnswer(number=1)
    )
    assert (
        game.respond(
            PLAYER, "owned-infection-roll", heat["id"], heat["revision"], ChoiceAnswer(number=1)
        )
        == response
    )
    ledger.engine.dispose()
    assert game.dice.calls == 1 and state(game).sheets["2"].heat == 1
    if tier == "mid":
        answer(game, PLAYER, LOSS, options=("body",), text="A small piece of her outer ear.")
        assert get(state(game), parent).loss == "body"
    elif tier.startswith("high"):
        selected = frame[-1].id
        answer(game, PLAYER, VOID, options=(selected,), text="The alloy hums out of phase.")
        case = get(state(game), parent)
        assert case.void_asset == selected and case.surgery_required
        assert next(x for x in state(game).sheets["2"].assets if x.id == selected).void
        if tier == "high_threshold":
            assert (
                case.resolved is None
                and game.inspect(PLAYER, parent)["state"] == "awaiting_choices"
            )
            work = case.void_work
            assert VoidService(ledger).get(PLAYER, work)["stage"] == "resist_pending"
            with pytest.raises(WorkflowError):
                VoidService(ledger).get(OTHER, work)
            game.dice.faces = (1, 1)
            child = game.begin(
                PLAYER,
                "infection-resistance",
                900,
                state(game).sheets["2"].revision,
                PlayInput(
                    play="keep_your_head",
                    heat=0,
                    parent=parent,
                    source_work=work,
                    context="I resist the altered cockpit.",
                    trigger_confirmed=True,
                ),
            )["action_id"]
            tick(worker, gateway, 5)
            for participant in (PLAYER, ADMIN):
                answer(game, participant, "tag_window", options=("pass",))
            answer(game, PLAYER, "actor_keep", options=("in_control",))
            answer(game, ADMIN, "handler_keep", flag=True, text="The threshold was resisted.")
            tick(worker, gateway, 5)
            assert game.inspect(PLAYER, child)["state"] == "complete"
            assert VoidService(ledger).get(PLAYER, work)["stage"] == "prevented"
    else:
        reviewed = next(x for x in game.choices(ADMIN) if x["kind"] == LOW_REVIEW)
        detail = game.decision(ADMIN, reviewed["id"])["detail"]
        assert detail["roll"]["faces"] == [1, 2]
        with pytest.raises(WorkflowError, match="exactly three"):
            answer(game, ADMIN, LOW_REVIEW, text="Acknowledged.")
        assert get(state(game), parent).resolved is None
        assert game.inspect(PLAYER, parent)["state"] == "awaiting_choices"

        async def select_parts():
            interaction = current(ADMIN.user_id, 87906)
            await interaction.response.defer(ephemeral=True)
            await open_choice(interaction, game, reviewed["id"])
            form = interaction.edit_original_response.call_args.kwargs["view"]
            assert all(label.startswith("Original Identity") for label in detail["parts"].values())
            form.values["options"] = tuple(detail["parts"])[:3]
            await form.confirm.callback(current(ADMIN.user_id, 87907))
            assert form.completed

        asyncio.run(select_parts())
        controlled = get(state(game), parent)
        assert controlled.surgery_required and len(controlled.controlled_identities) == 3
        tick(worker, gateway, 5)
        identity = controlled.controlled_identities[0]
        cast = CastService(ActorService(MissionService(ledger)))
        change(cast, ADMIN, "withdraw", original.actor)
        with pytest.raises(WorkflowError, match="Parasite controls this Identity"):
            game.begin(
                PLAYER,
                "controlled-identity",
                900,
                state(game).sheets["2"].revision,
                PlayInput(
                    play="keep_your_head",
                    heat=0,
                    identity=identity,
                    gain=1,
                    context="I try to invoke my controlled Identity.",
                    trigger_confirmed=True,
                ),
            )
        assert game.dice.calls == 1
    assert get(state(game), parent).resolved is not None
    assert game.inspect(PLAYER, parent)["state"] == "complete"
    with pytest.raises(WorkflowError, match="original source-table"):
        game.inspect(OTHER, parent)
    tick(worker, gateway, 5)
    assert {uid for uid, _ in gateway.private} <= {ADMIN.user_id, PLAYER.user_id}
    if tier == "high":
        surgery = ExcisionService(ledger)
        inbox = InboxService(ledger)

        def surgery_items(viewer):
            return [x for x in inbox.items(viewer) if x.task == "m3_parasite_excision"]

        assert len(surgery_items(PLAYER)) == 1
        assert surgery_items(ADMIN) == surgery_items(OTHER) == []
        with pytest.raises(WorkflowError, match="unavailable"):
            surgery.get(OTHER, parent)
        initial_surgery = surgery.get(PLAYER, parent)
        doctor = next(iter(initial_surgery["options"]))
        surgery.respond(
            PLAYER,
            "first-doctor-consent",
            parent,
            initial_surgery["revision"],
            "consent",
            doctor=doctor,
        )
        assert len(surgery_items(ADMIN)) == 1 and surgery_items(OTHER) == []
        surgery.respond(
            PLAYER,
            "withdraw-doctor-consent",
            parent,
            surgery.get(PLAYER, parent)["revision"],
            "withdraw",
        )
        with pytest.raises(WorkflowError, match="unavailable"):
            surgery.respond(
                ADMIN,
                "withdrawn-excision",
                parent,
                state(game).revision,
                "performed",
                account="Cannot proceed after withdrawal.",
            )

        async def choose_surgery(viewer, interaction_id, values):
            interaction = current(viewer.user_id, interaction_id)
            await interaction.response.defer(ephemeral=True)
            await open_excision(interaction, surgery, parent)
            form = interaction.edit_original_response.call_args.kwargs["view"]
            form.values.update(values)
            await form.confirm.callback(current(viewer.user_id, interaction_id + 1))
            assert form.completed

        asyncio.run(choose_surgery(PLAYER, 87908, {"doctor": (doctor,)}))
        ledger.engine.dispose()
        asyncio.run(choose_surgery(ADMIN, 87910, {"account": "The doctor excised the Parasite."}))
        final = state(game)
        assert not get(final, parent).surgery_required
        saved = get(final, parent).excision
        assert saved.doctor.entity == "actual-ward-doctor" and saved.performed_event
        assert surgery_items(PLAYER) == surgery_items(ADMIN) == []
        assert next(x for x in final.sheets["2"].assets if x.id == selected).void


@pytest.mark.parametrize("tier", ("low", "high"))
def test_mother_local_hazard_applies_owned_ejection_or_both_high_effects(ledger, tier):
    import asyncio

    from test_ledger import OTHER
    from test_m2_game import Dice
    from test_mission_ui import current
    from test_privacy_game_delivery import PrivateGateway

    from girlframe.discord_adapter.m2_ui import open_choice
    from girlframe.engine.m2 import PlayInput
    from girlframe.engine.m3_actors import resolve
    from girlframe.engine.m3_mother_hazard import get, immune
    from girlframe.engine.m3_physical_state import CockpitAction
    from girlframe.services.m3_actors import profiles
    from girlframe.services.m3_mother_hazard import EJECT, HEAT, PICK_PLAY, VOID
    from girlframe.services.m3_physical import PhysicalService
    from girlframe.services.onboarding import WorkflowError

    game, worker, _, _, mutation = gorgon_source(
        ledger,
        kind="mother_mutation",
        types=("mother",),
        tag="branch",
        begin=False,
    )
    gateway = PrivateGateway()

    def actor():
        with ledger.engine.connect() as c:
            return resolve(state(game), mutation.target, profiles(c, ledger.campaign_id))

    def operate(operation, key):
        PhysicalService(ledger).operate(
            PLAYER,
            key,
            state(game).revision,
            CockpitAction(
                actor=mutation.target,
                operation=operation,
                expected_position=actor().position_sha256,
                account="I change cockpit occupancy in the actual same square.",
                confirmed=True,
            ),
            channel=900,
        )

    service = GorgonPlayService(game)
    operate("exit", "exit-before-mother-mutation")
    view = service.preview(ADMIN, 900)
    people = {x["token"]: x for x in view["actors"]}
    marked_source = service.begin(
        ADMIN,
        "mother-mutation-before-hazard",
        900,
        view["revision"],
        mutation.model_copy(
            update=dict(
                actor_sha256=people[mutation.actor.token]["source_sha256"],
                target_sha256=people[mutation.target.token]["source_sha256"],
            )
        ),
    )["action_id"]
    tick(worker, gateway, 5)
    if game.inspect(ADMIN, marked_source)["state"] != "complete":
        game.roll(ADMIN, "advance-mutation-before-hazard", marked_source)
        tick(worker, gateway, 5)
    tagged = next(x for x in state(game).sheets["2"].tags if x.giver_actor == mutation.actor)
    assert not tagged.marked
    operate("pilot", "enter-before-hazard")
    frame = actor().occupied_frame_instance
    assert frame and actor().piloting
    game.dice = Dice((1, 2) if tier == "low" else (5, 6))
    view = service.preview(ADMIN, 900)
    people = {x["token"]: x for x in view["actors"]}
    assert view["hazard_tags"][mutation.actor.token] == {
        mutation.target.token: [(tagged.id, tagged.label)]
    }
    hazard = Declaration(
        kind="mother_hazard",
        actor=mutation.actor,
        target=mutation.target,
        tag=tagged.id,
        actor_sha256=people[mutation.actor.token]["source_sha256"],
        target_sha256=people[mutation.target.token]["source_sha256"],
        reach_confirmed=True,
        account="The original Mother reaches the Girl in the cockpit.",
    )
    parent = service.begin(ADMIN, "actual-memetic-hazard", 900, view["revision"], hazard)[
        "action_id"
    ]
    tick(worker, gateway, 5)
    if not any(x["kind"] == HEAT for x in game.choices(PLAYER)):
        game.roll(ADMIN, "advance-memetic-hazard", parent)
    assert next(x for x in state(game).sheets["2"].tags if x.id == tagged.id).marked
    assert game.dice.calls == 0
    answer(game, PLAYER, HEAT, number=0)
    if tier == "high":
        owned = next(x for x in game.choices(PLAYER) if x["kind"] == VOID)
        selected = next(iter(game.decision(PLAYER, owned["id"])["detail"]["assets"]))
        answer(game, PLAYER, VOID, options=(selected,), text="Its surface spirals.")
        saved = get(state(game), parent)
        assert saved.void_asset == selected and saved.completed is None
        assert immune(state(game), mutation.target)
        assert game.inspect(PLAYER, parent)["state"] == "awaiting_choices"
        answer(game, ADMIN, PICK_PLAY, options=("keep_your_head",))
        still = get(state(game), parent)
        assert still.requested_play == "keep_your_head" and still.child is None
        game.dice.faces = (1, 2)
        child = game.begin(
            PLAYER,
            "hazard-owned-response",
            900,
            state(game).sheets["2"].revision,
            PlayInput(
                play="keep_your_head",
                heat=0,
                parent=parent,
                context="I attempt to stay focused.",
                trigger_confirmed=True,
            ),
        )["action_id"]
        tick(worker, gateway, 5)
        for participant in (PLAYER, ADMIN):
            answer(game, participant, "tag_window", options=("pass",))
        answer(game, PLAYER, "actor_keep", options=("in_control",))
        answer(game, ADMIN, "handler_keep", flag=True, text="The Girl holds together.")
        assert game.inspect(PLAYER, child)["state"] == "complete"
        assert game.inspect(PLAYER, parent)["state"] == "complete"
        assert get(state(game), parent).child == child and game.dice.calls == 2
        with pytest.raises(WorkflowError):
            game.inspect(OTHER, child)
        scratch = state(game)
        next(x for x in scratch.sheets["2"].assets if x.id == selected).void = False
        assert not immune(scratch, mutation.target)
        return
    choice = next(x for x in game.choices(PLAYER) if x["kind"] == EJECT)
    with pytest.raises(WorkflowError):
        game.decision(OTHER, choice["id"])
    ledger.engine.dispose()

    async def eject():
        interaction = current(PLAYER.user_id, 88100)
        await interaction.response.defer(ephemeral=True)
        await open_choice(interaction, game, choice["id"])
        form = interaction.edit_original_response.call_args.kwargs["view"]
        form.values["account"] = "I eject immediately, leaving the Frame in place."
        await form.confirm.callback(current(PLAYER.user_id, 88101))
        assert form.completed

    asyncio.run(eject())
    original = actor()
    case = get(state(game), parent)
    assert original.inside_frame is False and original.frame_instance == frame
    assert original.frame_cell == original.cell
    assert case.frame == frame and case.ejected and case.completed == case.ejected
    assert game.inspect(PLAYER, parent)["state"] == "complete" and game.dice.calls == 1
