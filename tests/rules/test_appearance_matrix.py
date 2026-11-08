"""Actual Matrix scene effects, attributed undamage, physical return and genuine reset."""

import asyncio
from uuid import uuid4

import pytest
from test_enforcer_requisitions import approved
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Gateway, answer, pass_tags, state, tick
from test_mission_service import service
from test_mission_ui import current
from test_physical_operations import place
from test_world import initial

from girlframe.delivery.m2_worker import GameWorker
from girlframe.discord_adapter.m2_forms import NativeForm
from girlframe.discord_adapter.m3_appearance_matrix import open_matrix, open_purchase
from girlframe.engine import m3_appearance_matrix as rules
from girlframe.engine.m2 import PlayInput, TagState
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_battle_state import Declaration
from girlframe.engine.m3_physical_state import InitialPlacement
from girlframe.services.m3_actors import ActorService, profiles
from girlframe.services.m3_appearance_matrix import MatrixService, prove_mark
from girlframe.services.m3_battle import BattleService
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_off_duty import OffDutyService
from girlframe.services.m3_physical import PhysicalService
from girlframe.services.onboarding import WorkflowError

MEMORY = "SYNTHETIC_MATRIX_MEMORY: the original remembered scene remains recorded."


def prepared(store, tmp_path, monkeypatch, *, graft=False, away=False):
    _, game = service(store, girl="ALPHA", frame="THE RED QUEEN" if graft else "JANUS-B")
    approved(store, game, tmp_path, monkeypatch, extra=(rules.RULE,))
    store.policy = store.policy.model_copy(
        update=dict(
            m3_approval=store.policy.m3_approval.model_copy(
                update=dict(
                    subsystems=store.policy.m3_approval.subsystems
                    | {"world", "playbooks", "strain"}
                )
            )
        )
    )
    with store.transaction() as c:
        actual = state(game)
        actual.world = initial()
        actual = place(actual, 2, cell=(2, 0) if away else (0, 0))
        actual = place(actual, 3)
        sheet = actual.sheets["2"]
        sheet.permissions = 6
        sheet.heat = 2
        sheet.identities[0].marked = True
        girl = [x for x in sheet.assets if x.family == "girl"]
        girl[0].damaged = True
        girl[0].void = True
        sheet.tags.append(TagState(id="prior-matrix-tag", label="Original actual Tag", giver=3))
        actual.facts.append(dict(kind="synthetic_original_memory", body=MEMORY))
        game.event(c, 1, str(uuid4()), "synthetic.actual_prior_matrix_facts", actual)
    source = MatrixService(game)
    data = source.menu(PLAYER)
    if graft:
        before = state(game).model_dump_json()
        with pytest.raises(ValueError, match="eligible Class donor"):
            source.buy(
                PLAYER,
                str(uuid4()),
                data["revision"],
                ActorRef.model_validate(data["actor"]),
                data["frame"],
                "Invalid donor cannot charge",
                "WYVERN 0.4",
            )
        assert state(game).model_dump_json() == before
        args = (
            PLAYER,
            str(uuid4()),
            data["revision"],
            ActorRef.model_validate(data["actor"]),
            data["frame"],
            "Actual Priestess Matrix graft",
            "CONSUME",
        )
        paid = source.buy(*args)
        assert source.buy(*args) == paid and paid["cost"] == 3
    else:

        async def buy():
            interaction = current(2, 909001)
            interaction.channel_id = 900
            await interaction.response.defer(ephemeral=True)
            await open_purchase(interaction, source)
            form = interaction.edit_original_response.call_args.kwargs["view"]
            assert isinstance(form, NativeForm)
            form.values["account"] = "Actual native Matrix acquisition"
            await form.confirm.callback(current(2, 909002))
            assert form.completed

        asyncio.run(buy())
        assert state(game).sheets["2"].permissions == 4
    if away:
        casts = CastService(ActorService(MissionService(store)))
        cast = casts.view(PLAYER, 900)
        casts.change(
            PLAYER,
            str(uuid4()),
            900,
            cast["game_revision"],
            cast["cast_revision"],
            "withdraw",
            current_ref(state(game), 2),
        )

    async def context():
        gm = current(1, 909005)
        gm.channel_id = 900
        await gm.response.defer(ephemeral=True)
        await open_matrix(gm, source)
        form = gm.edit_original_response.call_args.kwargs["view"]
        assert isinstance(form, NativeForm)
        form.values["location"] = ("base0",)
        await form.confirm.callback(current(1, 909006))
        assert form.completed

    asyncio.run(context())
    context_id = source.view(PLAYER, 900)["context"]
    return game, source, context_id, GameWorker(game), Gateway()


def attack(game, worker, gateway, viewer, target_user):
    source = BattleService(game.store)
    data = source.preview(viewer, 900)
    actor = next(
        x
        for x in data["actors"]
        if x["ref"]["kind"] == "pilot" and x["ref"]["entity"] == str(viewer.user_id)
    )
    target = next(
        x
        for x in data["actors"]
        if x["ref"]["kind"] == "pilot" and x["ref"]["entity"] == str(target_user)
    )
    canon = state(game)
    weapons = {
        x.id
        for x in canon.sheets[str(viewer.user_id)].assets
        if not x.damaged and x.family == "frame"
    }
    targets = {
        x.id for x in canon.sheets[str(target_user)].assets if not x.damaged and x.family == "frame"
    }
    weapon = next(x for x in actor["assets"] if x["id"] in weapons)
    asset = next(x for x in target["assets"] if x["id"] in targets)
    declaration = Declaration(
        play="all_out_assault",
        actor=ActorRef.model_validate(actor["ref"]),
        target=ActorRef.model_validate(target["ref"]),
        attacking_asset=weapon["id"],
        target_asset=asset["id"],
        actor_sha256=actor["sha256"],
        target_sha256=target["sha256"],
        account="Actual source attack in this scene",
    )
    proposed = source.propose(viewer, str(uuid4()), data["revision"], 900, declaration)
    source.confirm(
        ADMIN,
        str(uuid4()),
        state(game).revision,
        proposed["id"],
        opening=True,
        reach=True,
        outside_permission=False,
        indirect=False,
        evidence="Actual source attack and reach",
    )
    game.dice.faces = (4, 5)
    action = game.begin(
        viewer,
        str(uuid4()),
        900,
        state(game).sheets[str(viewer.user_id)].revision,
        PlayInput(
            play="all_out_assault",
            heat=0,
            target_actor=declaration.target,
            attacking_asset=weapon["id"],
            target_asset=asset["id"],
            battle_context=proposed["id"],
            context=declaration.account,
            trigger_confirmed=True,
            piloting=True,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    if any(x["kind"] == "mockingbird_risk" for x in game.choices(viewer)):
        answer(game, viewer, "mockingbird_risk")
    for human in (ADMIN, PLAYER, OTHER):
        answer(game, human, "battle_assault_table", flag=False, text="My actual tactical judgment")
    assert game.inspect(viewer, action)["state"] == "complete"
    tick(worker, gateway, 5)
    return action, asset["id"]


def native_use(source, mode, key):
    async def use():
        owner = current(2, key - 2)
        owner.channel_id = 900
        await owner.response.defer(ephemeral=True)
        await open_matrix(owner, source)
        select = owner.edit_original_response.call_args.kwargs["view"]
        assert isinstance(select, NativeForm)
        select.values["mode"] = (mode,)
        picked = current(2, key - 1)
        await select.confirm.callback(picked)
        form = picked.edit_original_response.call_args.kwargs["view"]
        assert isinstance(form, NativeForm)
        form.values["confirm"] = ("yes",)
        await form.confirm.callback(current(2, key))
        assert form.completed

    asyncio.run(use())


def test_native_matrix_disappear_real_both_direction_undamage_preserves_history_and_actual_return(
    ledger, tmp_path, monkeypatch
):
    game, source, context, worker, gateway = prepared(ledger, tmp_path, monkeypatch)
    own_attack, other_asset = attack(game, worker, gateway, PLAYER, 3)
    incoming, own_asset = attack(game, worker, gateway, OTHER, 2)
    before = state(game)
    actor = current_ref(before, 2)
    origin = next(x for x in before.placements if x.actor == actor)
    preview = source.preview(PLAYER, context, "disappear")
    assert {x["asset"] for x in preview["repaired"]} == {own_asset, other_asset}
    with pytest.raises(WorkflowError):
        source.use(OTHER, str(uuid4()), context, preview["revision"], "disappear")
    native_use(source, "disappear", 909014)
    actual = state(game)
    use = rules.uses(actual)[0]
    assert (
        use.mode == "disappear"
        and len(use.repaired) == 2
        and rules.mark(actual, rules.held(actual, actor)).marked
    )
    assert not next(x for x in actual.sheets["2"].assets if x.id == own_asset).damaged
    assert not next(x for x in actual.sheets["3"].assets if x.id == other_asset).damaged
    for uid in ("2", "3"):
        original = before.sheets[uid]
        after = actual.sheets[uid]
        assert after.identities == original.identities and after.tags == original.tags
        assert (after.heat, after.permissions, after.character_id) == (
            original.heat,
            original.permissions,
            original.character_id,
        )
        assert [(x.id, x.void, x.name, x.description) for x in after.assets] == [
            (x.id, x.void, x.name, x.description) for x in original.assets
        ]
    assert actual.sheets["2"].assets[0].damaged  # unrelated prior damage is preserved
    assert actual.order == before.order and all(
        x in actual.facts for x in before.facts if x.get("kind") != "matrix_mark"
    )
    with ledger.engine.connect() as c:
        view = resolve(actual, actor, profiles(c, ledger.campaign_id))
    assert view.cell is None and view.frame_cell is None and view.offstage_source == use.id
    assert actor not in {x.actor for cast in actual.scene_casts for x in cast.roles}
    assert source.view(OTHER, 900)["memories"][0]["timeline"] == "never present"
    # A consumed episode cannot license later damage whose own source is missing.
    unproven = type(actual).model_validate_json(actual.model_dump_json())
    next(x for x in unproven.sheets["3"].assets if x.id == other_asset).damaged = True
    assert not rules.eligible_damage(unproven, actor, use.scene)
    revision = actual.revision
    source.use(PLAYER, "909014", context, preview["revision"], "disappear")
    assert state(game).revision == revision and game.dice.calls == 2
    with pytest.raises((ValueError, WorkflowError)):
        source.use(PLAYER, str(uuid4()), context, state(game).revision, "disappear")
    # Unknown endpoint is resolved only by actual original-owner facts and true source-GM review.
    physical = PhysicalService(ledger)
    current_data = physical.preview(PLAYER)
    proposal = physical.propose(
        PLAYER,
        str(uuid4()),
        current_data["game_revision"],
        InitialPlacement(
            actor=actor,
            frame_instance=origin.frame_instance,
            girl_cell=(2, 0),
            frame_cell=(2, 0),
            mode=origin.mode,
            account="My genuine later physical whereabouts",
            facts_confirmed=True,
        ),
    )
    physical.decide(
        ADMIN,
        str(uuid4()),
        proposal["id"],
        1,
        "accept",
        "The actual GM confirms these actual facts",
    )
    returned = state(game)
    assert rules.absence(returned, actor) is None
    with ledger.engine.connect() as c:
        view = resolve(returned, actor, profiles(c, ledger.campaign_id))
    assert view.cell == (2, 0) and view.offstage_source is None
    assert next(x for x in returned.placements if x.actor == actor).vessel_id == origin.vessel_id
    assert rules.uses(returned)[0].returned_event and game.dice.calls == 2
    assert (
        game.inspect(PLAYER, own_attack)["state"]
        == game.inspect(OTHER, incoming)["state"]
        == "complete"
    )


def test_grafted_matrix_true_scene_entry_then_actual_own_go_off_duty_start_resets_once(
    ledger, tmp_path, monkeypatch
):
    game, source, context, worker, gateway = prepared(
        ledger, tmp_path, monkeypatch, graft=True, away=True
    )
    before = state(game)
    actor = current_ref(before, 2)
    original = next(x for x in before.placements if x.actor == actor)
    assert original.girl_cell == (2, 0)
    assert source.preview(PLAYER, context, "appear")["mode"] == "appear"
    native_use(source, "appear", 909024)
    actual = state(game)
    placed = next(x for x in actual.placements if x.actor == actor)
    assert (
        placed.girl_cell == placed.frame_cell == (0, 0) and placed.vessel_id == original.vessel_id
    )
    assert any(x.actor == actor for cast in actual.scene_casts for x in cast.roles)
    assert actual.sheets == before.sheets and actual.order == before.order
    assert source.view(OTHER, 900)["memories"][0]["timeline"] == "present all along"
    paid = rules.held(actual, actor)
    assert rules.mark(actual, paid).marked and game.dice.calls == 0
    # A fabricated unmarked projection has no original reset source.
    forged = type(actual).model_validate_json(actual.model_dump_json())
    rules.put(
        forged,
        "matrix_mark",
        paid.id,
        rules.mark(forged, paid).model_copy(update=dict(marked=False)),
    )
    with ledger.engine.connect() as c, pytest.raises(WorkflowError, match="mark/reset"):
        prove_mark(game, c, forged, paid)
    periods = OffDutyService(MissionService(ledger))
    period = periods.begin(ADMIN, str(uuid4()))
    assert rules.mark(state(game), paid).marked  # preparation is not the printed start
    # Existing active-period fixture isolates the real individual source, not the Strain tables.
    with ledger.transaction() as c:
        saved = periods._get(c, period["id"])
        saved.phase = "active"
        saved.revision += 1
        event = game.event(c, 1, str(uuid4()), "synthetic.actual_active_period")
        periods._save(c, saved, event)
    game.dice.faces = (1, 2)
    key = str(uuid4())
    revision = state(game).sheets["2"].revision
    prepared_play = PlayInput(
        play="go_off_duty",
        off_duty_id=period["id"],
        heat=0,
        context="My actual rest starts now",
        trigger_confirmed=True,
    )
    action = game.begin(PLAYER, key, 900, revision, prepared_play)["action_id"]
    reset = state(game)
    assert not rules.mark(reset, paid).marked and rules.mark(reset, paid).periods == (period["id"],)
    assert game.dice.calls == 0  # actual start resets before RNG, independently of its result
    assert game.begin(PLAYER, key, 900, revision, prepared_play)["action_id"] == action
    assert len([x for x in state(game).facts if x.get("kind") == "matrix_reset"]) == 1
    assert source.view(PLAYER, 900)["marked"] is False
    tick(worker, gateway, 3)
    pass_tags(game)
    assert game.inspect(PLAYER, action)["state"] == "complete" and game.dice.calls == 1
    assert source.preview(PLAYER, context, "disappear")["mode"] == "disappear"


def test_actual_on_scene_beating_records_original_inflictor_asset_and_source_once(ledger):
    from test_beneath_discipline import pending

    from girlframe.engine.m3_punishments import Details
    from girlframe.services.m3_appearance_matrix import prove_damage

    source, game, _, _, action, work = pending(ledger)
    before = state(game)
    selected = next(x for x in before.sheets["3"].assets if x.family == "girl" and not x.damaged)
    data = source.get(PLAYER, work)
    args = (
        PLAYER,
        "matrix-actual-beating",
        work,
        data["revision"],
        data["game_revision"],
        Details(kind="beating", asset=selected.id, tag="Actual scene Beating"),
    )
    result = source.apply(*args)
    actual = state(game)
    (damage,) = rules.damages(actual)
    assert damage.damager == current_ref(before, 2) and damage.target == current_ref(before, 3)
    assert damage.asset == selected.id and damage.action == action and damage.work == work
    with ledger.engine.connect() as c:
        assert damage.scene == game.action(c, action)["scene_id"]
        prove_damage(game, c, damage)
    assert rules.asset(actual, damage.target, selected.id).damaged
    assert game.inspect(PLAYER, action)["state"] == "complete"
    assert source.apply(*args) == result and rules.damages(state(game)) == (damage,)
