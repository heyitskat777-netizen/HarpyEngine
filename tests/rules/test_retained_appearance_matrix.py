"""Original Matrix mark → paid Swap → actual reset/current-Frame undamage/absence/return."""

import asyncio
import json
from pathlib import Path
from uuid import uuid4

import pytest
import sqlalchemy as sa
import test_strain_effect_service
import test_strain_service
from test_appearance_matrix import native_use
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Dice, Gateway, answer, pass_tags, state, tick
from test_mission_service import service as mission_service
from test_mission_ui import current
from test_off_duty_cycle import activate, call
from test_off_duty_cycle import prepared as prepared_period
from test_physical_operations import place
from test_strain_service import ready as strain_ready
from test_succubus import restore, suspend

from girlframe.database import tables as t
from girlframe.delivery.m2_worker import GameWorker
from girlframe.discord_adapter.m2_forms import NativeForm
from girlframe.discord_adapter.m3_appearance_matrix import open_purchase
from girlframe.engine import m3_appearance_matrix as rules
from girlframe.engine import m3_class_retention as retention
from girlframe.engine import m3_frame_swap as swaps
from girlframe.engine.creation import AssetChoice
from girlframe.engine.m2 import PlayInput, TagState
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_frame_rewards import Claim
from girlframe.engine.m3_frame_swap_state import Selection, SwapReceipt
from girlframe.engine.m3_off_duty import RecoveryChoice
from girlframe.engine.m3_physical_state import InitialPlacement
from girlframe.engine.rules_registry import Registry
from girlframe.services.m3_access import Access, digest
from girlframe.services.m3_appearance_matrix import MatrixService, prove_mark, prove_use
from girlframe.services.m3_class_retention import proof
from girlframe.services.m3_frame_rewards import RewardService
from girlframe.services.m3_frame_swap import FrameSwapService
from girlframe.services.m3_physical import PhysicalService
from girlframe.services.onboarding import WorkflowError

MEMORY = "PRIVATE_ORIGINAL_MATRIX_MEMORY"
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
        trigger="SYNTHETIC retained Matrix actual mark/reset/current-Frame timeline effect",
        actor_type="Original actual body/Frame with exact paid Class and4P Swap",
        pre_roll_sources=["Immutable original mark, event-time source Frame and genuine start"],
        roll_kind="diceless",
        allowed_modifiers=["Existing real source Plays retain their original rolls"],
        tier_options={"normal": ["Actual presence/absence and source-attributed undamage"]},
        choice_ownership="Original owner uses; actual source GM establishes facts",
        target_policy="Same original body/current Frame, actual eligible source damage only",
        post_roll_effects=["Real location/cast/undamage, preserved history/contradictory memory"],
        mandatory_followups=["Actual source reset and factual same-body return"],
        handler_or_gm_intervention="Actual source factual review, no owner-use veto",
        test_fixture_ids=["tests/rules/test_retained_appearance_matrix.py"],
    )
    for entry in raw["entries"]:
        if entry["id"] in NEEDED:
            entry.update(
                implementation="implemented",
                source_audit="audited",
                independent_review="approved",
                reviewer="SYNTHETIC FIVE-SOURCE TEST ONLY",
                review_reference="Not independent review or production approval",
                test_evidence=["tests/rules/test_retained_appearance_matrix.py"],
            )
            if not entry.get("contract"):
                entry["contract"] = contract
    candidate = Registry.model_validate_json(json.dumps(raw))
    assert {x.id for x in candidate.entries if x != production.entry(x.id)} == NEEDED
    with pytest.raises(ValueError, match="review are incomplete"):
        swaps.destination(production, "THE ENFORCER")
    return production, candidate


def prepared(store, tmp_path, monkeypatch):
    monkeypatch.setattr(
        test_strain_service,
        "service",
        lambda store, frame: mission_service(store, girl="ALPHA", frame=frame),
    )
    monkeypatch.setattr(
        test_strain_effect_service,
        "ready",
        lambda store, face: strain_ready(store, face=face, frame="CONSUME"),
    )
    cycle, game, period = prepared_period(store)
    production, registry = synthetic_registry()
    path = tmp_path / "SYNTHETIC-only-five-retained-matrix-sources.json"
    path.write_text(registry.model_dump_json())
    monkeypatch.setenv("GIRLFRAME_RULES_REGISTRY", str(path))
    store.policy = store.policy.model_copy(
        update=dict(
            m3_approval=store.policy.m3_approval.model_copy(
                update=dict(
                    registry_sha256=digest(registry),
                    subsystems=store.policy.m3_approval.subsystems
                    | {"economy", "plays", "world", "playbooks"},
                )
            ),
            owner_m3_rulings=store.policy.owner_m3_rulings.model_copy(
                update=dict(beneath_private_choices="affected_owner")
            ),
        )
    )
    cycle.missions.access = Access(store)
    with store.transaction() as c:
        canon = state(game)
        canon = place(place(canon, 2, mode="outside_frame", cell=(2, 0)), 3)
        sheet = canon.sheets["2"]
        sheet.permissions, sheet.heat = 10, 3
        sheet.identities[0].marked = True
        sheet.tags.append(TagState(id="original-matrix-tag", label="PRIVATE_MATRIX_TAG", giver=3))
        canon.facts.append(dict(kind="synthetic_original_memory", body=MEMORY))
        game.event(c, 2, str(uuid4()), "synthetic.actual_original_matrix_resources", canon)
    source = MatrixService(game)

    async def purchase():
        own = current(2, 957001)
        await own.response.defer(ephemeral=True)
        await open_purchase(own, source)
        form = own.edit_original_response.call_args.kwargs["view"]
        assert isinstance(form, NativeForm)
        form.values.update(account="PRIVATE_ORIGINAL_MATRIX_SOURCE")
        await form.confirm.callback(current(2, 957002))
        assert form.completed

    asyncio.run(purchase())
    original = state(game)
    actor = current_ref(original, 2)
    paid = rules.held(original, actor)
    assert paid and paid.price == 2 and paid.frame == "CONSUME"
    context = source.record_context(ADMIN, str(uuid4()), 900, original.revision, "base0")["id"]
    native_use(source, "appear", 957010)
    used = state(game)
    first = rules.uses(used)[0]
    assert first.frame == paid.frame_instance and rules.mark(used, paid).marked
    swap = FrameSwapService(game, registry)
    plan = swap.create(PLAYER, str(uuid4()), "THE ENFORCER")["id"]
    data = swap.get(PLAYER, plan)
    kept = next(x for x in used.sheets["2"].assets if x.family == "frame" and x.intrinsic is None)
    selection = Selection(
        frame="THE ENFORCER",
        name="Actual replacement Enforcer",
        appearance="Actual new body",
        assets=tuple(AssetChoice(name=x, description="Actual " + x) for x in data["starting"][:2]),
        retained_asset=kept.id,
        retained_rule=rules.RULE,
        retained_receipt=paid.id,
        account="PRIVATE_MATRIX_SWAP",
    )
    swap.change(PLAYER, str(uuid4()), plan, data["revision"], selection=selection)
    data = swap.get(PLAYER, plan)
    args = (PLAYER, str(uuid4()), plan, data["revision"])
    kwargs = dict(purchase=True, expected=data["expected"], delivered=True)
    result = swap.change(*args, **kwargs)
    assert swap.change(*args, **kwargs) == result
    return game, source, cycle, period, context, paid, original, first, production


def test_retained_matrix_spent_mark_real_reset_new_frame_undamage_absence_and_original_return(
    ledger, tmp_path, monkeypatch
):
    game, source, cycle, period, context, paid, original, first, production = prepared(
        ledger, tmp_path, monkeypatch
    )
    actor = paid.actor
    canon = state(game)
    swap = next(x for x in canon.requisitions if isinstance(x, SwapReceipt))
    mark = rules.mark(canon, paid)
    assert mark.marked and mark.frame == paid.frame_instance and mark.use == first.id
    assert canon.sheets["2"].permissions == 4
    assert canon.sheets["2"].tags == original.sheets["2"].tags
    assert canon.sheets["2"].identities == original.sheets["2"].identities
    with ledger.engine.connect() as c:
        assert proof(game, c, canon, paid) == (swap.new_frame, (paid.id, swap.id))
        prove_mark(game, c, canon, paid)
        prove_use(game, c, canon, first)
    with pytest.raises((ValueError, WorkflowError), match="unmarked"):
        source.preview(PLAYER, context, "disappear")
    menu = source.menu(PLAYER)
    with pytest.raises(WorkflowError, match="Restore"):
        source.buy(
            PLAYER,
            str(uuid4()),
            menu["revision"],
            actor,
            menu["frame"],
            "No rebuy/reset",
            "CONSUME",
        )
    gate = suspend(game, swap.id)
    assert source.menu(PLAYER)["suspended"] and rules.mark(state(game), paid) == mark
    restore(game, gate)
    assert rules.mark(state(game), paid) == mark and not source.menu(PLAYER)["suspended"]
    activate(cycle, game, period)
    game.dice = Dice((2, 2))
    worker, gateway = GameWorker(game), Gateway()
    key, revision = str(uuid4()), state(game).sheets["2"].revision
    play = PlayInput(
        play="go_off_duty",
        off_duty_id=period,
        heat=0,
        context="Actual own rest starts after replacement",
        trigger_confirmed=True,
    )
    action = game.begin(PLAYER, key, 900, revision, play)["action_id"]
    reset = state(game)
    assert not rules.mark(reset, paid).marked and rules.mark(reset, paid).periods == (period,)
    assert game.dice.calls == 0
    assert game.begin(PLAYER, key, 900, revision, play)["action_id"] == action
    assert len([x for x in state(game).facts if x.get("kind") == "matrix_reset"]) == 1
    with ledger.engine.connect() as c:
        prove_mark(game, c, reset, paid)
    tick(worker, gateway)
    pass_tags(game)
    tick(worker, gateway, 8)
    reward = RewardService(cycle.periods)
    for work in cycle.periods.get(PLAYER, period)["work"]:
        if work["kind"] == "frame_off_duty_reward":
            data = reward.get(PLAYER, work["id"])
            if data["owner_id"] == "2" and data["mode"] == "conditional":
                reward.apply(
                    PLAYER,
                    str(uuid4()),
                    work["id"],
                    data["revision"],
                    data["game_revision"],
                    Claim(fulfilled=False, account="No qualifying capture occurred"),
                )
    call(cycle, game, PLAYER, period, "scene", None, (), "")
    call(cycle, game, PLAYER, period, "recover", RecoveryChoice(repair_assets=True))
    assert cycle.review(PLAYER, period)["own"]["recovered"]
    assert cycle.periods.get(ADMIN, period)["phase"] == "active"
    game.dice.faces = (1, 1)
    damage_action = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play="put_someone_beneath_you",
            target=3,
            heat=0,
            context="Actual current Frame counterattack",
            trigger_confirmed=True,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    answer(game, OTHER, "beneath_select", options=("damage",), text="Actual counterattack")
    selected = next(
        x
        for x in state(game).sheets["2"].assets
        if x.family == "frame" and x.id.startswith(swap.new_frame)
    )
    answer(game, PLAYER, "beneath_details", denied=(selected.id,))
    assert game.inspect(PLAYER, damage_action)["state"] == "complete"
    tick(worker, gateway, 5)
    before = state(game)
    damage = next(
        x for x in rules.damages(before) if x.action == damage_action and x.asset == selected.id
    )
    assert damage.frame == swap.new_frame and damage.target == actor
    assert next(x for x in before.sheets["2"].assets if x.id == selected.id).damaged
    preview = source.preview(PLAYER, context, "disappear")
    assert {x["id"] for x in preview["repaired"]} == {damage.id}
    native_use(source, "disappear", 957030)
    absent = state(game)
    latest = rules.uses(absent)[-1]
    assert (
        latest.frame == swap.new_frame
        and latest.purchase == paid.id
        and latest.repaired == (damage.id,)
    )
    assert not next(x for x in absent.sheets["2"].assets if x.id == selected.id).damaged
    assert absent.sheets["2"].tags == before.sheets["2"].tags
    assert absent.sheets["2"].identities == before.sheets["2"].identities
    assert absent.sheets["2"].heat == before.sheets["2"].heat and absent.order == before.order
    assert absent.sheets["3"] == before.sheets["3"]
    assert any(x.get("body") == MEMORY for x in absent.facts)
    body = next(x for x in absent.placements if x.actor == actor)
    assert body.girl_cell is None and body.frame_cell == (0, 0)
    assert rules.absence(absent, actor) == latest and rules.mark(absent, paid).marked
    assert any(
        x["use"] == latest.id and x["prior_memories_preserved"]
        for x in source.view(OTHER, 900)["memories"]
    )
    physical = PhysicalService(ledger)
    position = physical.preview(PLAYER)
    proposed = physical.propose(
        PLAYER,
        str(uuid4()),
        position["game_revision"],
        InitialPlacement(
            actor=actor,
            frame_instance=swap.new_frame,
            girl_cell=(0, 0),
            frame_cell=(0, 0),
            mode="outside_frame",
            account="Actual same original body's later return",
            facts_confirmed=True,
        ),
    )
    physical.decide(
        ADMIN,
        str(uuid4()),
        proposed["id"],
        1,
        "accept",
        "Actual source GM establishes original return",
    )
    final = state(game)
    returned = next(x for x in final.placements if x.actor == actor)
    assert returned.vessel_id == body.vessel_id and returned.girl_cell == (0, 0)
    assert returned.frame_instance == swap.new_frame and rules.absence(final, actor) is None
    assert rules.uses(final)[-1].returned_event and rules.mark(final, paid).marked
    assert game.dice.calls == 2 and final.sheets["2"].permissions == 4
    with ledger.engine.connect() as c:
        prove_mark(game, c, final, paid)
        prove_use(game, c, final, first)
        prove_use(game, c, final, rules.uses(final)[-1])
    forged = final.model_copy(deep=True)
    rules.put(
        forged,
        "matrix_mark",
        paid.id,
        rules.mark(forged, paid).model_copy(update=dict(marked=False)),
    )
    with ledger.engine.connect() as c, pytest.raises(WorkflowError, match="mark/reset"):
        prove_mark(game, c, forged, paid)
    forged_chain = final.model_copy(deep=True)
    link = retention.links(forged_chain)[0]
    wrong = link.model_copy(update=dict(event="SYNTHETIC_FORGED_SWAP"))
    forged_chain.facts = [
        dict(x, body=wrong.model_dump_json()) if x.get("kind") == "class_rule_retained" else x
        for x in forged_chain.facts
    ]
    with ledger.engine.connect() as c, pytest.raises(ValueError, match="retention chain"):
        proof(game, c, forged_chain, paid)
    assert next(x for x in final.requisitions if x.id == paid.id) == paid
    assert game.rebuild() > 0 and state(game) == final
    with ledger.engine.connect() as c:
        assert "PRIVATE_" not in str(list(c.scalars(sa.select(t.events.c.payload_json))))
        assert game.lock(c, 900)["state"] == "released"
    with pytest.raises(ValueError, match="review are incomplete"):
        swaps.destination(production, "THE ENFORCER")
