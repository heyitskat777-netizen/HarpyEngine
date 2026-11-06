"""Original Handler gift → exact paid Swap → actual bonus/counter-damage/Punishment."""

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
from test_special_girl import acquire_token, complete_token
from test_succubus import restore, suspend
from test_world import initial

from girlframe.database import tables as t
from girlframe.delivery.m2_worker import GameWorker
from girlframe.discord_adapter.m2_forms import NativeForm
from girlframe.discord_adapter.m2_ui import open_choice
from girlframe.discord_adapter.m3_special_girl import open_token
from girlframe.engine import m3_class_retention as retention
from girlframe.engine import m3_frame_swap as swaps
from girlframe.engine import m3_special_girl as rules
from girlframe.engine.creation import AssetChoice
from girlframe.engine.m2 import ChoiceAnswer, PlayInput, TagState, higher
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_appearance_matrix import damages
from girlframe.engine.m3_frame_swap_state import Selection, SwapReceipt
from girlframe.engine.m3_punishments import Details
from girlframe.engine.rules_registry import Registry
from girlframe.services.m3_access import digest
from girlframe.services.m3_class_retention import proof
from girlframe.services.m3_frame_swap import FrameSwapService
from girlframe.services.m3_punishments import PunishmentService
from girlframe.services.m3_special_girl import SpecialGirlService, entitlement
from girlframe.services.onboarding import WorkflowError

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
        trigger="SYNTHETIC retained Special Girl actual Beneath/counter-damage",
        actor_type="Original Girl/Handler/target with immutable paid Class and4P Swap",
        pre_roll_sources=["Actual Status, completed original gift, source chain/current Frame"],
        roll_kind="2d6",
        allowed_modifiers=["Existing +1 only when actual actor already higher Status"],
        tier_options={"normal": ["True counter-damage mandates original Handler Punishment"]},
        choice_ownership="Original Handler authors token/discipline; affected owner chooses Asset",
        target_policy="Actual original counterattacker and original Girl, no proxy bodies",
        post_roll_effects=["Real source Asset damage and real target Punishment effect"],
        mandatory_followups=["Actual compulsory discipline and parent/chat completion"],
        handler_or_gm_intervention="Actual original Handler owns printed duty",
        test_fixture_ids=["tests/rules/test_retained_special_girl.py"],
    )
    for entry in raw["entries"]:
        if entry["id"] in NEEDED:
            entry.update(
                implementation="implemented",
                source_audit="audited",
                independent_review="approved",
                reviewer="SYNTHETIC FIVE-SOURCE TEST ONLY",
                review_reference="Not independent review or production approval",
                test_evidence=["tests/rules/test_retained_special_girl.py"],
            )
            if not entry.get("contract"):
                entry["contract"] = contract
    candidate = Registry.model_validate_json(json.dumps(raw))
    assert {x.id for x in candidate.entries if x != production.entry(x.id)} == NEEDED
    with pytest.raises(ValueError, match="review are incomplete"):
        swaps.destination(production, "THE ENFORCER")
    return production, candidate


def prepared(store, tmp_path, monkeypatch):
    _, game = service(store, girl="ALPHA", frame="THE RED QUEEN")
    production, registry = synthetic_registry()
    path = tmp_path / "SYNTHETIC-only-five-retained-special-girl-sources.json"
    path.write_text(registry.model_dump_json())
    monkeypatch.setenv("GIRLFRAME_RULES_REGISTRY", str(path))
    store.policy = store.policy.model_copy(
        update=dict(
            m3_approval=store.policy.m3_approval.model_copy(
                update=dict(
                    registry_sha256=digest(registry),
                    subsystems=store.policy.m3_approval.subsystems | {"economy", "plays", "world"},
                )
            ),
            owner_m3_rulings=store.policy.owner_m3_rulings.model_copy(
                update=dict(beneath_private_choices="affected_owner")
            ),
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
            TagState(
                id="original-marked-special-tag", label="PRIVATE_SPECIAL_TAG", giver=2, marked=True
            )
        )
        kept = next(x for x in sheet.assets if x.family == "frame" and x.intrinsic is None)
        kept.damaged = kept.void = True
        game.event(c, 2, str(uuid4()), "synthetic.actual_original_special_resources", canon)
    source = SpecialGirlService(game)
    result = acquire_token(game, source, number=955000)
    complete_token(game, source, result, number=955010)
    original = state(game)
    actor = current_ref(original, 2)
    paid = rules.held(original, actor)
    assert paid and paid.price == 2 and paid.frame == "THE RED QUEEN"
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
        account="PRIVATE_SPECIAL_SWAP",
    )
    swap.change(PLAYER, str(uuid4()), plan, data["revision"], selection=selection)
    data = swap.get(PLAYER, plan)
    args = (PLAYER, str(uuid4()), plan, data["revision"])
    kwargs = dict(purchase=True, expected=data["expected"], delivered=True)
    result = swap.change(*args, **kwargs)
    assert swap.change(*args, **kwargs) == result
    return game, source, paid, original, production


def test_retained_special_girl_original_gift_bonus_real_damage_handler_punishment_and_completion(
    ledger, tmp_path, monkeypatch
):
    game, source, paid, original, production = prepared(ledger, tmp_path, monkeypatch)
    actor = paid.actor
    canon = state(game)
    target = current_ref(canon, 3)
    swap = next(x for x in canon.requisitions if isinstance(x, SwapReceipt))
    token = rules.token(original, paid.id)
    assert token and token.phase == "complete" and token.asset
    assert token.frame == paid.frame_instance != swap.new_frame
    assert rules.token(canon, paid.id) == token
    assert next(x for x in canon.sheets["2"].assets if x.id == token.asset.id) == token.asset
    assert canon.sheets["2"].permissions == 4 and canon.sheets["2"].heat == 3
    assert canon.sheets["2"].identities == original.sheets["2"].identities
    assert canon.sheets["2"].tags == original.sheets["2"].tags
    with ledger.engine.connect() as c:
        assert proof(game, c, canon, paid) == (swap.new_frame, (paid.id, swap.id))
    menu = source.menu(PLAYER)
    with pytest.raises(WorkflowError, match="Restore"):
        source.buy(PLAYER, str(uuid4()), menu["revision"], actor, menu["frame"], "No regift/rebuy")
    gate = suspend(game, swap.id)
    suspended = state(game)
    assert rules.held(suspended, actor) is None and source.menu(PLAYER)["suspended"]
    assert rules.token(suspended, paid.id) == token
    assert next(x for x in suspended.sheets["2"].assets if x.id == token.asset.id) == token.asset
    with ledger.engine.connect() as c:
        assert entitlement(game, c, suspended, actor) is None
    restore(game, gate)
    assert rules.held(state(game), actor) == paid and not source.menu(PLAYER)["suspended"]

    async def reopen():
        own = current(2, 955020)
        await own.response.defer(ephemeral=True)
        await open_token(own, source, paid.id)
        content = str(own.edit_original_response.call_args.kwargs)
        assert token.asset.name in content and token.asset.description in content

    asyncio.run(reopen())
    with pytest.raises(WorkflowError, match="real Handler and owner"):
        source.get(OTHER, paid.id)
    assert source.get(PLAYER, paid.id)["token"] == token.model_dump(mode="json")
    assert higher(state(game), 2, 3)
    game.dice.faces = (1, 1)
    action = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play="put_someone_beneath_you",
            target=3,
            heat=0,
            context="Actual retained source confrontation",
            trigger_confirmed=True,
        ),
    )["action_id"]
    worker, gateway = GameWorker(game), Gateway()
    tick(worker, gateway, 3)
    pass_tags(game)
    receipt = game.inspect(PLAYER, action)["receipt"]
    assert receipt["pre_total"] == 3 and game.dice.calls == 1
    assert receipt["special_girl_purchase"] == paid.id
    assert receipt["pre_modifiers"] == [{"source": "Handler's Special Girl", "amount": 1}]
    with ledger.engine.connect() as c:
        meta = game.action(c, action)["data"]["beneath"]["special_girl"]
        assert meta["frame"] == swap.new_frame and meta["purchase"] == paid.id

    async def counter():
        row = next(x for x in game.choices(OTHER) if x["kind"] == "beneath_select")
        own = current(3, 955030)
        await own.response.defer(ephemeral=True)
        await open_choice(own, game, row["id"])
        form = own.edit_original_response.call_args.kwargs["view"]
        assert isinstance(form, NativeForm)
        form.values.update(options=("damage",), text="Actual counterattack on her equipment")
        await form.confirm.callback(current(3, 955031))
        assert form.completed

    asyncio.run(counter())
    selected = next(
        x for x in state(game).sheets["2"].assets if x.family == "frame" and not x.damaged
    )
    answer(game, PLAYER, "beneath_details", denied=(selected.id,))
    damaged = state(game)
    assert next(x for x in damaged.sheets["2"].assets if x.id == selected.id).damaged
    attribution = next(x for x in damages(damaged) if x.action == action and x.asset == selected.id)
    assert attribution.damager == target and attribution.target == actor
    assert game.inspect(PLAYER, action)["state"] == "awaiting_choices"
    choice = next(x for x in game.choices(ADMIN) if x["kind"] == "beneath_punishment")
    work = game.decision(ADMIN, choice["id"])["body"]["work_id"]
    discipline = PunishmentService(ledger)
    view = discipline.get(ADMIN, work)
    assert view["owner_id"] == "1" and view["subject_id"] == "3"
    with pytest.raises(WorkflowError, match="source-backed resolver"):
        game.respond(
            ADMIN,
            str(uuid4()),
            choice["id"],
            choice["revision"],
            ChoiceAnswer(flag=True, text="A note cannot replace actual Punishment"),
        )
    args = (
        ADMIN,
        "actual-retained-special-punishment",
        work,
        view["revision"],
        view["game_revision"],
        Details(kind="stimulant_injection"),
    )
    result = discipline.apply(*args)
    assert discipline.apply(*args) == result
    final = state(game)
    assert final.sheets["3"].heat == damaged.sheets["3"].heat + 7
    assert game.inspect(PLAYER, action)["state"] == "complete"
    assert game.inspect(PLAYER, action)["receipt"] == receipt and game.dice.calls == 1
    assert game.inspect(PLAYER, action)["result"]["punishment_work"] == work
    assert rules.token(final, paid.id) == token
    assert len([x for x in final.sheets["2"].assets if x.id == token.asset.id]) == 1
    assert final.sheets["2"].identities == canon.sheets["2"].identities
    assert next(x for x in final.requisitions if x.id == paid.id) == paid
    tick(worker, gateway, 5)
    with ledger.engine.connect() as c:
        assert game.lock(c, 900)["state"] == "released"
        assert "PRIVATE_" not in str(list(c.scalars(sa.select(t.events.c.payload_json))))
    forged = final.model_copy(deep=True)
    link = retention.links(forged)[0]
    wrong = link.model_copy(update=dict(event="SYNTHETIC_FORGED_SWAP"))
    forged.facts = [
        dict(x, body=wrong.model_dump_json()) if x.get("kind") == "class_rule_retained" else x
        for x in forged.facts
    ]
    with ledger.engine.connect() as c, pytest.raises(ValueError, match="retention chain"):
        source._source(c, forged, paid.id)
    assert game.rebuild() > 0 and state(game) == final
    with pytest.raises(ValueError, match="review are incomplete"):
        swaps.destination(production, "THE ENFORCER")
