"""Paid retained Sup → real Dive growth at cap → genuine full-Void Frame endpoint."""

import asyncio
import json
from pathlib import Path
from uuid import uuid4

import pytest
import sqlalchemy as sa
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Gateway, answer, pass_tags, state, tick
from test_mission_service import service
from test_mission_ui import current
from test_physical_operations import place
from test_succubus import restore, suspend
from test_void_service import respond
from test_world import initial

from girlframe.database import tables as t
from girlframe.delivery.m2_worker import GameWorker
from girlframe.discord_adapter.m2_forms import NativeForm
from girlframe.discord_adapter.m3_dive import open_dive
from girlframe.discord_adapter.m3_sup import GROW, open_purchase
from girlframe.engine import m3_class_retention as retention
from girlframe.engine import m3_frame_swap as swaps
from girlframe.engine import m3_sup as rules
from girlframe.engine.creation import AssetChoice
from girlframe.engine.m2 import AssetState, ChoiceAnswer, PlayInput, TagState
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_frame_swap_state import Selection, SwapReceipt
from girlframe.engine.m3_janus_storage import effective_assets
from girlframe.engine.m3_world_state import Asset, CorePlan, Gorgon
from girlframe.engine.rules_registry import Registry
from girlframe.services.m3_access import digest
from girlframe.services.m3_class_retention import proof
from girlframe.services.m3_frame_swap import FrameSwapService
from girlframe.services.m3_sup import SupService, offer, prove_growth
from girlframe.services.m3_void import VoidService
from girlframe.services.onboarding import WorkflowError

DESCRIPTION = "PRIVATE_RETAINED_SUP_GROWTH: actual new corrupted crystalline limbs"
NEEDED = frozenset(
    (
        rules.RULE,
        "core.core.frame-requisitions",
        "frame.enforcer.obedience-conditioning",
        "frame.enforcer.permission-trigger",
        "frame.enforcer.enforcement-initiative",
    )
)


def synthetic_registry():
    production = Registry.model_validate_json(Path("rules/registry.json").read_text())
    raw = production.model_dump(mode="json")
    contract = dict(
        trigger="SYNTHETIC retained Sup real Void gain/growth/threshold",
        actor_type="Original Girl with actual original paid Class source and4P Swap",
        pre_roll_sources=["Actual new Frame, existing cap, original source and genuine Void gain"],
        roll_kind="diceless",
        allowed_modifiers=["Original source Dive retains its actual printed roll"],
        tier_options={"normal": ["Actual new already-Void Asset instead of existing rewrite"]},
        choice_ownership="Original affected person owns growth, actual GM resolves Frame endpoint",
        target_policy="Own actual new Asset/body, source-bound current Frame only",
        post_roll_effects=[
            "Actual inventory/Void count and real mandatory full-family consequence"
        ],
        mandatory_followups=["Actual full-Void threshold and original source completion"],
        handler_or_gm_intervention="Actual source only",
        test_fixture_ids=["tests/rules/test_retained_sup.py"],
    )
    for entry in raw["entries"]:
        if entry["id"] in NEEDED:
            entry.update(
                implementation="implemented",
                source_audit="audited",
                independent_review="approved",
                reviewer="SYNTHETIC FIVE-SOURCE TEST ONLY",
                review_reference="Not independent review or production approval",
                test_evidence=["tests/rules/test_retained_sup.py"],
            )
            if not entry.get("contract"):
                entry["contract"] = contract
    candidate = Registry.model_validate_json(json.dumps(raw))
    assert {x.id for x in candidate.entries if x != production.entry(x.id)} == NEEDED
    with pytest.raises(ValueError, match="review are incomplete"):
        swaps.destination(production, "THE ENFORCER")
    return production, candidate


def prepared(store, tmp_path, monkeypatch):
    _, game = service(store, girl="ALPHA", frame="CONSUME")
    production, registry = synthetic_registry()
    path = tmp_path / "SYNTHETIC-only-five-retained-sup-sources.json"
    path.write_text(registry.model_dump_json())
    monkeypatch.setenv("GIRLFRAME_RULES_REGISTRY", str(path))
    store.policy = store.policy.model_copy(
        update=dict(
            m3_approval=store.policy.m3_approval.model_copy(
                update=dict(
                    registry_sha256=digest(registry),
                    subsystems=store.policy.m3_approval.subsystems | {"economy", "plays", "world"},
                )
            )
        )
    )
    with store.transaction() as c:
        canon = state(game)
        canon.world = initial()
        canon = place(place(canon, 2, mode="outside_frame"), 3)
        sheet = canon.sheets["2"]
        sheet.permissions, sheet.heat = 10, 3
        sheet.identities[0].marked = True
        sheet.tags.append(
            TagState(id="original-marked-sup-tag", label="PRIVATE_SUP_TAG", giver=2, marked=True)
        )
        kept = next(x for x in sheet.assets if x.family == "frame" and x.intrinsic is None)
        kept.damaged = kept.void = True
        game.event(c, 2, str(uuid4()), "synthetic.actual_original_sup_resources", canon)
    source = SupService(game)

    async def purchase():
        own = current(2, 954001)
        await own.response.defer(ephemeral=True)
        await open_purchase(own, source)
        form = own.edit_original_response.call_args.kwargs["view"]
        assert isinstance(form, NativeForm) and "2 Permissions" in form.text()
        form.values.update(account="PRIVATE_ORIGINAL_SUP_SOURCE")
        await form.confirm.callback(current(2, 954002))
        assert form.completed

    asyncio.run(purchase())
    original = state(game)
    actor = current_ref(original, 2)
    paid = rules.held(original, actor)
    assert paid and paid.price == 2 and paid.frame == "CONSUME"
    swap = FrameSwapService(game, registry)
    plan = swap.create(PLAYER, str(uuid4()), "THE ENFORCER")["id"]
    data = swap.get(PLAYER, plan)
    assert next(x for x in data["class_sources"] if x["rule"] == rules.RULE)["receipt"] == paid.id
    selection = Selection(
        frame="THE ENFORCER",
        name="Actual replacement Enforcer",
        appearance="Actual new body",
        assets=tuple(AssetChoice(name=x, description="Actual " + x) for x in data["starting"][:2]),
        retained_asset=kept.id,
        retained_rule=rules.RULE,
        retained_receipt=paid.id,
        account="PRIVATE_SUP_SWAP",
    )
    swap.change(PLAYER, str(uuid4()), plan, data["revision"], selection=selection)
    data = swap.get(PLAYER, plan)
    args = (PLAYER, str(uuid4()), plan, data["revision"])
    kwargs = dict(purchase=True, expected=data["expected"], delivered=True)
    result = swap.change(*args, **kwargs)
    assert swap.change(*args, **kwargs) == result
    return game, source, paid, original, production


def test_retained_sup_real_dive_cap_growth_full_void_abandoned_frame_and_source_completion(
    ledger, tmp_path, monkeypatch
):
    game, source, paid, original, production = prepared(ledger, tmp_path, monkeypatch)
    actor = paid.actor
    canon = state(game)
    swap = next(x for x in canon.requisitions if isinstance(x, SwapReceipt))
    assert rules.held(canon, actor) == paid and canon.sheets["2"].permissions == 4
    assert canon.sheets["2"].tags == original.sheets["2"].tags
    assert canon.sheets["2"].identities == original.sheets["2"].identities
    with ledger.engine.connect() as c:
        assert proof(game, c, canon, paid) == (swap.new_frame, (paid.id, swap.id))
    menu = source.menu(PLAYER)
    with pytest.raises(WorkflowError, match="Restore"):
        source.buy(
            PLAYER, str(uuid4()), menu["revision"], actor, menu["frame"], "No rebuy", "CONSUME"
        )
    gate = suspend(game, swap.id)
    suspended = state(game)
    assert rules.held(suspended, actor) is None and source.menu(PLAYER)["suspended"]
    with ledger.engine.connect() as c:
        assert offer(game, c, suspended, actor) is None
    restore(game, gate)
    assert rules.held(state(game), actor) == paid and not source.menu(PLAYER)["suspended"]
    with ledger.transaction() as c:
        actual = state(game)
        sheet = actual.sheets["2"]
        for number in range(5 - sum(x.family == "frame" for x in sheet.assets)):
            sheet.assets.append(
                AssetState(
                    id="prior-new-frame:" + str(number),
                    family="frame",
                    name="Actual prior installed hardware " + str(number),
                    description="Previously installed on this actual replacement Frame",
                )
            )
        frames = [x for x in sheet.assets if x.family == "frame"]
        replacement = frames[0]
        for asset in frames:
            asset.void = asset.id != replacement.id
        game.event(c, 2, str(uuid4()), "synthetic.actual_prior_partial_void_new_frame", actual)
    before = state(game)
    assert sum(x.void for x in effective_assets(before, actor) if x.family == "frame") == 4
    game.dice.faces = (4, 5)
    action = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        before.sheets["2"].revision,
        PlayInput(
            play="dive_deep",
            heat=0,
            piloting=False,
            context="Actual communion after paid Frame replacement",
            trigger_confirmed=True,
        ),
    )["action_id"]
    worker, gateway = GameWorker(game), Gateway()
    tick(worker, gateway, 3)
    pass_tags(game)
    receipt = game.inspect(PLAYER, action)["receipt"]
    answer(
        game, PLAYER, "dive_select", options=("void_and_unmark_all",), text="Actual printed source"
    )
    row = next(x for x in game.choices(PLAYER) if x["kind"] == "dive_effect")
    fields = dict(sup_name="Actual new Void limbs", sup_family="frame", sup_replace=replacement.id)
    with pytest.raises(WorkflowError):
        game.respond(
            OTHER,
            str(uuid4()),
            row["id"],
            row["revision"],
            ChoiceAnswer(fields=fields, text=DESCRIPTION),
        )

    async def grow():
        own = current(2, 954010)
        await own.response.defer(ephemeral=True)
        await open_dive(own, game, row["id"])
        form = own.edit_original_response.call_args.kwargs["view"]
        assert isinstance(form, NativeForm) and GROW in dict(form.fields[0].options)
        form.values.update(asset=(GROW,))
        selected = current(2, 954011)
        await form.confirm.callback(selected)
        growth = selected.edit_original_response.call_args.kwargs["view"]
        assert isinstance(growth, NativeForm)
        growth.values.update(
            name=fields["sup_name"],
            family=("frame",),
            replace=(replacement.id,),
            description=DESCRIPTION,
        )
        await growth.confirm.callback(current(2, 954012))
        assert growth.completed

    asyncio.run(grow())
    grown_state = state(game)
    grown = rules.growths(grown_state)[0]
    assert grown.frame == swap.new_frame != paid.frame_instance and grown.purchase == paid.id
    assert grown.choice.replace == replacement.id
    frames = [x for x in effective_assets(grown_state, actor) if x.family == "frame"]
    assert len(frames) == 5 and all(x.void for x in frames)
    assert replacement.id not in {x.id for x in grown_state.sheets["2"].assets}
    assert next(x for x in frames if x.id == grown.asset).description == DESCRIPTION
    assert grown_state.sheets["2"].permissions == before.sheets["2"].permissions == 4
    assert grown_state.sheets["2"].heat == before.sheets["2"].heat == 3
    assert grown_state.sheets["2"].tags == before.sheets["2"].tags
    assert not any(x.marked for x in grown_state.sheets["2"].identities)
    with ledger.engine.connect() as c:
        assert prove_growth(game, c, grown_state, actor, grown.event) == grown
    game.respond(
        PLAYER, "954012", row["id"], row["revision"], ChoiceAnswer(fields=fields, text=DESCRIPTION)
    )
    assert state(game) == grown_state and game.dice.calls == 1
    assert game.inspect(PLAYER, action)["state"] != "complete"
    threshold = next(x for x in game.choices(PLAYER) if x["kind"] == "dive_void_threshold")
    work = json.loads(threshold["body_json"])["work_id"]
    void = VoidService(ledger)
    assert void.get(PLAYER, work)["stage"] == "abandoned"
    actual_gorgon = Gorgon(
        id="actual-retained-sup-frame",
        name="Actual abandoned new grown Frame",
        cell=(0, 0),
        gorgon_class="aggressive",
        types=("sentinel",),
        assets=tuple(
            Asset(
                id=x.id,
                name=x.name,
                description=x.description,
                family="gorgon",
                void=x.void,
                damaged=x.damaged,
            )
            for x in frames
        ),
        core_plan=CorePlan(assets=(frames[0].id,), weakness="Its actual vulnerable core"),
    )
    respond(
        void,
        work,
        "abandoned",
        dict(
            gorgon=actual_gorgon.model_dump(mode="json"),
            account="Actual original outside Girl and Frame conversion",
        ),
        viewer=ADMIN,
    )
    final = state(game)
    assert final.sheets["2"].frame_scrapped and "2" in final.sheets
    assert game.inspect(PLAYER, action)["state"] == "complete"
    assert game.inspect(PLAYER, action)["receipt"] == receipt and game.dice.calls == 1
    actual = next(x for x in final.world.gorgons if x.id == actual_gorgon.id)
    assert {x.id for x in actual.assets} == {x.id for x in frames}
    assert next(x for x in actual.assets if x.id == grown.asset).description == DESCRIPTION
    assert (
        rules.growths(final) == (grown,)
        and next(x for x in final.requisitions if x.id == paid.id) == paid
    )
    tick(worker, gateway, 5)
    assert DESCRIPTION not in json.dumps(list(gateway.messages.values()))
    forged = grown_state.model_copy(deep=True)
    wrong = grown.model_copy(update=dict(frame=paid.frame_instance))
    forged.facts = [
        dict(x, body=wrong.model_dump_json()) if x.get("kind") == "sup_growth" else x
        for x in forged.facts
    ]
    with ledger.engine.connect() as c:
        with pytest.raises(WorkflowError, match="paid Sup"):
            prove_growth(game, c, forged, actor, grown.event)
        assert "PRIVATE_" not in str(list(c.scalars(sa.select(t.events.c.payload_json))))
        assert game.lock(c, 900)["state"] == "released"
    forged_chain = grown_state.model_copy(deep=True)
    link = retention.links(forged_chain)[0]
    wrong_link = link.model_copy(update=dict(event="SYNTHETIC_FORGED_SWAP"))
    forged_chain.facts = [
        dict(x, body=wrong_link.model_dump_json()) if x.get("kind") == "class_rule_retained" else x
        for x in forged_chain.facts
    ]
    with ledger.engine.connect() as c, pytest.raises(ValueError, match="retention chain"):
        proof(game, c, forged_chain, paid)
    assert game.rebuild() > 0 and state(game) == final
    with pytest.raises(ValueError, match="review are incomplete"):
        swaps.destination(production, "THE ENFORCER")
