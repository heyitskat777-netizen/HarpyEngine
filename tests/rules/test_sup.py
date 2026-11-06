"""Actual paid Sup growth through each existing owned native Void-gain producer."""

import asyncio
import json
from uuid import uuid4

import pytest
import test_battle_service as battle_fixture
import test_budget_cleanup as cleanup_fixture
import test_dive as dive_fixture
import test_mockingbird_risk as risk_fixture
import test_mockingbird_sex_closure as sex_fixture
from test_battle_pipeline import dormant_source, table
from test_enforcer_requisitions import approved
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Gateway, answer, state, tick
from test_mission_service import service
from test_mission_ui import current

from girlframe.delivery.m2_worker import GameWorker
from girlframe.discord_adapter.m2_forms import NativeForm
from girlframe.discord_adapter.m3_dive import open_dive
from girlframe.discord_adapter.m3_sup import GROW, open_purchase
from girlframe.engine import m3_budget_cleanup as cleanup
from girlframe.engine import m3_sup as sup
from girlframe.engine.m2 import AssetState, ChoiceAnswer
from girlframe.engine.m3_actor_bonds import current_ref, depth
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_janus_storage import effective_assets
from girlframe.engine.m3_world_state import Asset, CorePlan, Gorgon
from girlframe.services.m3_access import Access
from girlframe.services.m3_battle_dormant import DormantService
from girlframe.services.m3_budget_cleanup import CleanupService
from girlframe.services.m3_sup import SupService, prove_growth
from girlframe.services.m3_void import VoidService
from girlframe.services.onboarding import WorkflowError

DESCRIPTION = "SYNTHETIC_SUP_CANARY: living tendrils replace no existing hardware unless at cap."


def purchase(game, tmp_path, monkeypatch, viewer=PLAYER, *, native_ui=False):
    approved(game.store, game, tmp_path, monkeypatch, extra=(sup.RULE,))
    with game.store.transaction() as c:
        actual = state(game)
        actual.sheets[str(viewer.user_id)].permissions = 6
        game.event(c, 1, str(uuid4()), "synthetic.actual_owned_permissions", actual)
    source = SupService(game)
    data = source.menu(viewer)
    before = state(game).sheets[str(viewer.user_id)].permissions
    if native_ui:

        async def buy():
            interaction = current(viewer.user_id, 908001)
            await interaction.response.defer(ephemeral=True)
            await open_purchase(interaction, source)
            form = interaction.edit_original_response.call_args.kwargs["view"]
            assert isinstance(form, NativeForm)
            form.values["account"] = "My actual paid Sup acquisition"
            if data["donors"]:
                form.values["donor"] = ("CONSUME",)
            await form.confirm.callback(current(viewer.user_id, 908002))
            assert form.completed

        asyncio.run(buy())
    else:
        args = (
            viewer,
            str(uuid4()),
            data["revision"],
            ActorRef.model_validate(data["actor"]),
            data["frame"],
            "My actual paid Sup acquisition",
            data["donors"][0] if data["donors"] else None,
        )
        result = source.buy(*args)
        assert source.buy(*args) == result
    actual = state(game)
    paid = sup.held(actual, current_ref(actual, viewer.user_id))
    assert paid and paid.price == (2 if not data["donors"] else 3)
    assert actual.sheets[str(viewer.user_id)].permissions == before - paid.price
    return paid


def fields(name="Actual new Void organ", family="frame", replace=""):
    return dict(sup_name=name, sup_family=family, sup_replace=replace)


def paid_ready(monkeypatch, module, tmp_path, *, viewer=PLAYER, native_ui=False):
    original = module.ready

    def ready(*args, **kwargs):
        result = original(*args, **kwargs)
        purchase(result[0], tmp_path, monkeypatch, viewer, native_ui=native_ui)
        return result

    monkeypatch.setattr(module, "ready", ready)


def test_grafted_native_dive_growth_replaces_only_cap_nonvoid_and_real_threshold_then_escape(
    ledger, tmp_path, monkeypatch
):
    def ready(store, faces=(4, 5)):
        _, game = service(store, girl="ALPHA", frame="THE RED QUEEN")
        purchase(game, tmp_path, monkeypatch, native_ui=True)
        assert SupService(game).menu(PLAYER)["price"] == 3
        with store.transaction() as c:
            actual = state(game)
            sheet = actual.sheets["2"]
            values = [x for x in sheet.assets if x.family == "frame"]
            for index in range(5 - len(values)):
                sheet.assets.append(
                    AssetState(
                        id="prior-frame:" + str(index),
                        family="frame",
                        name="Actually owned extra hardware",
                        description="Actual previously installed hardware at its sole origin",
                    )
                )
            frames = [x for x in sheet.assets if x.family == "frame"]
            for asset in frames[:-1]:
                asset.void = True
            game.event(c, 1, str(uuid4()), "synthetic.actual_prior_partial_frame_void", actual)
        game.dice.faces = faces
        return game, GameWorker(game), Gateway()

    monkeypatch.setattr(dive_fixture, "ready", ready)
    game, worker, gateway, action = dive_fixture.rolled(
        ledger, placement="inside_frame", marked=True
    )
    dive_fixture.choose(game, PLAYER, "void_and_unmark_all")
    before = state(game)
    replacement = next(x for x in before.sheets["2"].assets if x.family == "frame" and not x.void)
    row = next(x for x in game.choices(PLAYER) if x["kind"] == "dive_effect")
    with pytest.raises(WorkflowError):
        game.respond(
            OTHER,
            str(uuid4()),
            row["id"],
            row["revision"],
            ChoiceAnswer(fields=fields(replace=replacement.id), text=DESCRIPTION),
        )

    async def grow():
        owner = current(2, 908010)
        await owner.response.defer(ephemeral=True)
        await open_dive(owner, game, row["id"])
        form = owner.edit_original_response.call_args.kwargs["view"]
        assert isinstance(form, NativeForm) and GROW in dict(form.fields[0].options)
        form.values.update(asset=(GROW,))
        selected = current(2, 908011)
        await form.confirm.callback(selected)
        actual = selected.edit_original_response.call_args.kwargs["view"]
        assert isinstance(actual, NativeForm)
        actual.values.update(
            name="Actual new Void organ",
            family=("frame",),
            replace=(replacement.id,),
            description=DESCRIPTION,
        )
        await actual.confirm.callback(current(2, 908012))
        assert actual.completed

    asyncio.run(grow())
    after = state(game)
    actor = current_ref(after, 2)
    grown = sup.growths(after)[0]
    assert grown.choice.replace == replacement.id and grown.purchase == sup.held(before, actor).id
    assert replacement.id not in {x.id for x in after.sheets["2"].assets}
    frames = [x for x in effective_assets(after, actor) if x.family == "frame"]
    assert len(frames) == 5 and all(x.void for x in frames)
    assert next(x for x in frames if x.id == grown.asset).description == DESCRIPTION
    assert [x.marked for x in after.sheets["2"].identities] == [True, False, False, False]
    assert after.sheets["2"].heat == before.sheets["2"].heat
    assert after.sheets["2"].permissions == before.sheets["2"].permissions
    with ledger.engine.connect() as c:
        assert prove_growth(game, c, after, actor, grown.event) == grown
    source = next(x for x in game.choices(PLAYER) if x["kind"] == "dive_void_threshold")
    work = json.loads(source["body_json"])["work_id"]
    void = VoidService(ledger)
    data = void.get(PLAYER, work)
    assert data["stage"] == "enclosed" and game.inspect(PLAYER, action)["state"] != "complete"
    game.respond(
        PLAYER,
        "908012",
        row["id"],
        row["revision"],
        ChoiceAnswer(fields=fields(replace=replacement.id), text=DESCRIPTION),
    )
    assert len(sup.growths(state(game))) == 1 and game.dice.calls == 1
    cost = next(x["id"] for x in data["assets"] if x["family"] == "girl" and not x["damaged"])
    void.respond(
        PLAYER,
        str(uuid4()),
        work,
        data["revision"],
        data["game_revision"],
        data["expected"],
        "choose_escape",
        dict(asset=cost, account="My actual escape cost"),
    )
    data = void.get(ADMIN, work)
    gorgon = Gorgon(
        id="actual-sup-gorgon",
        name="Actual abandoned grown Frame",
        cell=(0, 0),
        gorgon_class="aggressive",
        types=("sentinel",),
        assets=tuple(
            Asset(
                id=x.id,
                name=x.name,
                description=x.description,
                family="gorgon",
                void=True,
                damaged=x.damaged,
            )
            for x in frames
        ),
        core_plan=CorePlan(assets=(frames[0].id,), weakness="Actual known weakness"),
    )
    void.respond(
        ADMIN,
        str(uuid4()),
        work,
        data["revision"],
        data["game_revision"],
        data["expected"],
        "escape",
        dict(gorgon=gorgon.model_dump(mode="json"), account="Actual physical escape"),
    )
    assert game.inspect(PLAYER, action)["state"] == "complete" and game.dice.calls == 1
    assert any(x.id == grown.asset and x.void for x in state(game).world.gorgons[0].assets)
    tick(worker, gateway, 5)
    assert DESCRIPTION not in json.dumps(list(gateway.messages.values()))


def test_native_sup_risk_grows_real_asset_then_original_keep_completes_without_new_roll(
    ledger, tmp_path, monkeypatch
):
    paid_ready(monkeypatch, risk_fixture, tmp_path, native_ui=True)
    game, worker, gateway, action = risk_fixture.begin(ledger, monkeypatch)
    before = state(game)
    receipt = game.inspect(PLAYER, action)["receipt"]
    answer(game, PLAYER, "mockingbird_risk", number=9, fields=fields(), text=DESCRIPTION)
    actual = state(game)
    assert len(actual.sheets["2"].assets) == len(before.sheets["2"].assets) + 1
    assert all(x in actual.sheets["2"].assets for x in before.sheets["2"].assets)
    assert sup.growths(actual)[0].asset in {
        x.id for x in effective_assets(actual, current_ref(actual, 2)) if x.void
    }
    assert game.inspect(PLAYER, action)["receipt"] == receipt
    answer(game, PLAYER, "actor_keep", options=("in_control", "vicious"), denied=("desperate",))
    answer(game, ADMIN, "handler_keep", flag=True, text="The actual defense is enough")
    assert game.inspect(PLAYER, action)["state"] == "complete" and game.dice.calls == 1
    tick(worker, gateway, 5)


def test_sup_sex_counterpart_owns_growth_instead_of_caster_selected_existing_asset(
    ledger, tmp_path, monkeypatch
):
    paid_ready(monkeypatch, sex_fixture, tmp_path, viewer=OTHER)
    game, _, _, action, caster, target = sex_fixture.source(ledger, monkeypatch, (6, 6))
    before = state(game)
    asset = next(x for x in before.sheets["3"].assets if not x.void)
    answer(game, PLAYER, "mockingbird_sex_infect", fields=dict(asset=asset.id))
    answer(game, OTHER, "mockingbird_sex_rewrite", fields=fields(), text=DESCRIPTION)
    actual = state(game)
    assert next(x for x in actual.sheets["3"].assets if x.id == asset.id) == asset
    assert len(actual.sheets["3"].assets) == len(before.sheets["3"].assets) + 1
    assert actual.sheets["2"].assets == before.sheets["2"].assets
    assert sup.growths(actual)[0].actor == target
    assert depth(actual, caster, target) == min(2, depth(before, caster, target) + 1)
    assert game.inspect(PLAYER, action)["state"] == "complete" and game.dice.calls == 1


def test_sup_dormant_corruption_grows_real_asset_and_preserves_original_attack_debt(
    ledger, tmp_path, monkeypatch
):
    paid_ready(monkeypatch, battle_fixture, tmp_path)
    game, worker, gateway, action, work = dormant_source(ledger, monkeypatch)
    source = DormantService(ledger, game)
    data = source.get(PLAYER, work)
    before = state(game)
    assert data["sup"]
    result = source.alter(
        PLAYER,
        str(uuid4()),
        work,
        data["revision"],
        data["game_revision"],
        None,
        DESCRIPTION,
        piloting=True,
        growth_fields=fields(),
    )
    assert result["phase"] == "complete"
    assert len(state(game).sheets["2"].assets) == len(before.sheets["2"].assets) + 1
    assert game.inspect(PLAYER, action)["state"] != "complete"
    table(game)
    assert game.inspect(PLAYER, action)["state"] == "complete" and game.dice.calls == 1
    tick(worker, gateway, 5)


def test_sup_cleanup_single_exposure_grows_new_void_asset_and_resolves_actual_source(
    ledger, tmp_path, monkeypatch
):
    original = cleanup_fixture.prepared

    def prepare(strain, game):
        purchase(game, tmp_path, monkeypatch)
        # This preexisting fixture cached its release gate before the synthetic Sup review.
        strain.missions.access = Access(game.store)
        return original(strain, game)

    monkeypatch.setattr(cleanup_fixture, "prepared", prepare)
    effects, game, mission, work, _, draw = cleanup_fixture.ready(ledger)
    cleanup_fixture.select(effects, mission, work, "exposure")
    identity = work + ":cleanup"
    source = CleanupService(ledger)
    data = source.view(PLAYER, identity)
    before = state(game)
    assert data["sup"] and draw.calls == 1
    args = (PLAYER, str(uuid4()), identity, data["revision"], "rewrite", DESCRIPTION)
    result = source.act(*args, growth_fields=fields())
    assert source.act(*args, growth_fields=fields()) == result
    actual = state(game)
    assert cleanup.get(actual, identity).phase == "complete"
    assert cleanup_fixture.resolved(ledger, identity) == "resolved"
    assert len(actual.sheets["2"].assets) == len(before.sheets["2"].assets) + 1
    assert draw.calls == 1 and len(sup.growths(actual)) == 1
