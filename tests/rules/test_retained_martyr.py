"""Paid retained source → real damage/Defeat death → original-human memorial/Strain."""

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
from test_strain import facts
from test_world import initial

from girlframe.database import tables as t
from girlframe.delivery.m2_worker import GameWorker
from girlframe.discord_adapter.m2_forms import NativeForm
from girlframe.discord_adapter.m2_ui import open_choice
from girlframe.discord_adapter.m3_martyr import open_memorial, open_purchase
from girlframe.engine import m3_class_retention as retention
from girlframe.engine import m3_frame_swap as swaps
from girlframe.engine import m3_martyr as rules
from girlframe.engine.creation import AssetChoice
from girlframe.engine.m2 import PilotSheet, PlayInput, TagState
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_frame_swap_state import Selection, SwapReceipt
from girlframe.engine.m3_physical_state import CockpitAction
from girlframe.engine.rules_registry import Registry
from girlframe.services.inbox import InboxService
from girlframe.services.m3_access import digest
from girlframe.services.m3_budget_storage import StorageService
from girlframe.services.m3_class_retention import proof
from girlframe.services.m3_frame_swap import FrameSwapService
from girlframe.services.m3_martyr import MartyrService
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_off_duty import OffDutyService
from girlframe.services.m3_physical import PhysicalService
from girlframe.services.m3_strain import StrainService
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
        trigger="SYNTHETIC retained Martyr original death and memorial",
        actor_type="Original Girl with actual original paid Class source and4P Swap",
        pre_roll_sources=["Actual body/Frame, original acquisition and retained source chain"],
        roll_kind="diceless",
        allowed_modifiers=["Actual separate source Plays retain their printed basis"],
        tier_options={"normal": ["Real death lowers Budget/Rebellion; original human memorial"]},
        choice_ownership="Original human owns deceased original memorial",
        target_policy="Actual original dead Girl and archived replacement Frame",
        post_roll_effects=["True Strain relief and persistent original-human memorial"],
        mandatory_followups=["Actual memorial, source closure and next Strain preparation"],
        handler_or_gm_intervention="Original source only",
        test_fixture_ids=["tests/rules/test_retained_martyr.py"],
    )
    for entry in raw["entries"]:
        if entry["id"] in NEEDED:
            entry.update(
                implementation="implemented",
                source_audit="audited",
                independent_review="approved",
                reviewer="SYNTHETIC FIVE-SOURCE TEST ONLY",
                review_reference="Not independent review or production approval",
                test_evidence=["tests/rules/test_retained_martyr.py"],
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
    path = tmp_path / "SYNTHETIC-only-five-retained-martyr-sources.json"
    path.write_text(registry.model_dump_json())
    monkeypatch.setenv("GIRLFRAME_RULES_REGISTRY", str(path))
    store.policy = store.policy.model_copy(
        update=dict(
            m3_approval=store.policy.m3_approval.model_copy(
                update=dict(
                    registry_sha256=digest(registry),
                    subsystems=store.policy.m3_approval.subsystems
                    | {"economy", "plays", "world", "strain", "playbooks"},
                )
            ),
            owner_m3_rulings=store.policy.owner_m3_rulings.model_copy(
                update=dict(beneath_private_choices="affected_owner")
            ),
        )
    )
    strain = StrainService(OffDutyService(MissionService(store)))
    strain.configure(
        ADMIN,
        str(uuid4()),
        state(game).revision,
        "falling_apart",
        frozenset({"void", "rebellion", "budget"}),
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
                id="original-marked-martyr-tag", label="PRIVATE_MARTYR_TAG", giver=2, marked=True
            )
        )
        kept = next(x for x in sheet.assets if x.family == "frame" and x.intrinsic is None)
        kept.damaged = kept.void = True
        game.event(c, 2, str(uuid4()), "synthetic.actual_original_martyr_resources", canon)
    source = MartyrService(game)

    async def purchase():
        own = current(2, 952001)
        await own.response.defer(ephemeral=True)
        await open_purchase(own, source)
        form = own.edit_original_response.call_args.kwargs["view"]
        assert isinstance(form, NativeForm) and "2 Permissions" in form.text()
        form.values.update(account="PRIVATE_ORIGINAL_MARTYR_SOURCE")
        await form.confirm.callback(current(2, 952002))
        assert form.completed

    asyncio.run(purchase())
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
        account="PRIVATE_MARTYR_SWAP",
    )
    swap.change(PLAYER, str(uuid4()), plan, data["revision"], selection=selection)
    data = swap.get(PLAYER, plan)
    args = (PLAYER, str(uuid4()), plan, data["revision"])
    kwargs = dict(purchase=True, expected=data["expected"], delivered=True)
    result = swap.change(*args, **kwargs)
    assert swap.change(*args, **kwargs) == result
    physical = PhysicalService(store)
    position = physical.preview(PLAYER)
    physical.operate(
        PLAYER,
        str(uuid4()),
        position["game_revision"],
        CockpitAction(
            actor=actor,
            operation="pilot",
            expected_position=position["position_sha256"],
            account="I genuinely pilot the delivered replacement Frame",
            confirmed=True,
        ),
    )
    return game, source, strain, paid, original, production


def test_retained_martyr_real_defeat_death_original_memorial_and_next_strain(
    ledger, tmp_path, monkeypatch
):
    game, source, strain, paid, original, production = prepared(ledger, tmp_path, monkeypatch)
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
        source.buy(PLAYER, str(uuid4()), menu["revision"], actor, menu["frame"], "No rebuy")
    assert state(game) == canon
    with ledger.transaction() as c:
        damaged = state(game)
        frames = [x for x in damaged.sheets["2"].assets if x.family == "frame"]
        for asset in frames[1:]:
            asset.damaged = True
        game.event(c, 2, str(uuid4()), "synthetic.actual_prior_frame_damage", damaged)
    game.dice.faces = (1, 1)
    parent = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play="put_someone_beneath_you",
            target=3,
            heat=0,
            piloting=True,
            context="Actual confrontation while piloting the replacement Frame",
            trigger_confirmed=True,
        ),
    )["action_id"]
    worker, gateway = GameWorker(game), Gateway()
    tick(worker, gateway, 3)
    pass_tags(game)
    answer(game, OTHER, "beneath_select", options=("damage",), text="My actual counterattack")
    answer(game, PLAYER, "beneath_details", denied=(frames[0].id,))
    assert all(x.damaged for x in state(game).sheets["2"].assets if x.family == "frame")
    assert game.choices(PLAYER)[0]["kind"] == "beneath_defeat"
    undamaged = sum(x.family == "girl" and not x.damaged for x in state(game).sheets["2"].assets)
    game.dice.faces = (1, 1)
    child = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play="defeat",
            heat=0,
            parent=parent,
            context="Actual source Defeat from my last usable Frame Asset loss",
            trigger_confirmed=True,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    receipt = game.inspect(PLAYER, child)["receipt"]
    assert receipt["pre_total"] == 2 + undamaged <= 7 and game.dice.calls == 2
    pre_death = state(game)

    async def die():
        row = next(x for x in game.choices(PLAYER) if x["kind"] == "defeat_select")
        own = current(2, 952003)
        await own.response.defer(ephemeral=True)
        await open_choice(own, game, row["id"])
        form = own.edit_original_response.call_args.kwargs["view"]
        form.values.update(
            options=("death",), account="The actual original Girl dies at this real Defeat"
        )
        response = current(2, 952004)
        await form.confirm.callback(response)
        assert form.completed, str(response.edit_original_response.call_args)

    asyncio.run(die())
    after = state(game)
    episode = rules.episodes(after)[0]
    archive = next(x for x in after.career_archives if x.id == episode.archive)
    archived = PilotSheet.model_validate_json(archive.sheet_json)
    assert (
        episode.actor == actor and episode.purchase == paid.id and episode.frame == swap.new_frame
    )
    assert (
        episode.frame != paid.frame_instance
        and archive.actor == actor
        and archive.ending == "death"
    )
    assert "2" not in after.sheets and 2 not in after.order
    assert archived.revision == pre_death.sheets["2"].revision + 1
    assert archived.model_dump(exclude={"revision"}) == pre_death.sheets["2"].model_dump(
        exclude={"revision"}
    )
    assert after.strain.levels == {"void": "high", "rebellion": "low", "budget": "low"}
    assert rules.budget_death_excluded(after, episode.source_event)
    with ledger.engine.connect() as c:
        assert StorageService(ledger)._reduction(c, paid.source_event) == episode.source_event
    assert next(x for x in after.requisitions if x.id == paid.id) == paid
    assert (
        game.inspect(PLAYER, child)["receipt"] == receipt
        and game.inspect(PLAYER, child)["state"] == "complete"
    )
    assert game.inspect(PLAYER, parent)["state"] == "complete"
    card = next(x for x in InboxService(ledger).items(PLAYER) if x.identity == episode.id)
    assert card.task == "m3_martyr" and card.state == "pending"
    for viewer in (OTHER, ADMIN):
        with pytest.raises(WorkflowError, match="original dead character"):
            source.get(viewer, episode.id)

    async def memorial():
        own = current(2, 952005)
        await own.response.defer(ephemeral=True)
        await open_memorial(own, source, episode.id)
        form = own.edit_original_response.call_args.kwargs["view"]
        assert not await form.interaction_check(current(1, 952006))
        form.values.update(memorial=("obscurity",), account="PRIVATE_ORIGINAL_MARTYR_MEMORIAL")
        await form.confirm.callback(current(2, 952007))
        assert form.completed
        saved = state(game)
        await form.confirm.callback(current(2, 952007))
        assert state(game) == saved
        reopened = current(2, 952008)
        await reopened.response.defer(ephemeral=True)
        await open_memorial(reopened, source, episode.id)
        content = str(reopened.edit_original_response.call_args.kwargs)
        assert "obscurity" in content and "PRIVATE_ORIGINAL_MARTYR_MEMORIAL" in content

    asyncio.run(memorial())
    assert source.get(PLAYER, episode.id)["episode"]["memorial"] == "obscurity"
    assert not source.get(PLAYER, episode.id)["can_act"]
    assert len(rules.episodes(state(game))) == 1 and game.dice.calls == 2
    tick(worker, gateway, 5)
    period = strain.periods.begin(ADMIN, str(uuid4()))["id"]
    current_state = state(game)
    count = sum(any(x.void for x in sheet.assets) for sheet in current_state.sheets.values())
    strain.prepare(
        ADMIN,
        str(uuid4()),
        period,
        1,
        current_state.revision,
        facts(
            at_least_half_have_void=2 * count >= len(current_state.order),
            no_girl_void=count == 0,
            girl_death_or_severe=False,
        ),
    )
    final = state(game)
    assert final.strain.levels["budget"] == "low"
    assert next(x for x in final.strain.requests if x.track == "budget").severity == "low"
    forged = after.model_copy(deep=True)
    link = retention.links(forged)[0]
    wrong = link.model_copy(update=dict(event="SYNTHETIC_FORGED_SWAP"))
    forged.facts = [
        dict(x, body=wrong.model_dump_json()) if x.get("kind") == "class_rule_retained" else x
        for x in forged.facts
    ]
    assert not rules.budget_death_excluded(forged, episode.source_event)
    with ledger.engine.connect() as c:
        with pytest.raises(ValueError, match="retention chain"):
            proof(game, c, forged, paid)
        assert "PRIVATE_" not in str(list(c.scalars(sa.select(t.events.c.payload_json))))
    assert game.rebuild() > 0 and state(game) == final
    with pytest.raises(ValueError, match="review are incomplete"):
        swaps.destination(production, "THE ENFORCER")
