"""Draft acceptance: actual World Gorgon pays its literal Dormant counter, never a PC."""

import asyncio
import json
from uuid import uuid4

import pytest
import sqlalchemy as sa
from test_gorgon_runtime import candidate_source_gate as candidate_source_gate
from test_gorgon_runtime import gorgon_source
from test_ledger import ADMIN, OTHER
from test_ledger import ledger as ledger
from test_m2_game import answer, state, tick
from test_mission_ui import current

from girlframe.database import tables as t
from girlframe.discord_adapter.m2_forms import NativeForm
from girlframe.discord_adapter.m3_gorgon_runtime import open_choice
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_gorgon_dormant import inflict
from girlframe.engine.m3_gorgon_play_state import Declaration
from girlframe.services.m3_gorgon_dormant import GorgonDormantService, awakened_source
from girlframe.services.m3_gorgon_play import GorgonPlayService
from girlframe.services.onboarding import WorkflowError


def source(store, **kwargs):
    game, worker, gateway, root, _ = gorgon_source(
        store, target="opposing-gorgon", opposing=True, opposing_class="dormant", **kwargs
    )
    with store.engine.connect() as c:
        request = next(x for x in game.pending(c, root) if x["kind"] == "gorgon_dormant_void")
    work = json.loads(request["body_json"])["work_id"]
    return game, worker, gateway, root, request, work, GorgonDormantService(store, game)


def pay(service, work):
    data = service.get(ADMIN, work)
    selected = data["assets"][-1]["id"] if data["assets"] else None
    key = str(uuid4())
    result = service.respond(
        ADMIN,
        key,
        work,
        data["revision"],
        data["game_revision"],
        selected,
        "Actual geometric flesh changes in this original Gorgon Asset"
        if selected
        else "Every actual extant World Asset of this source Gorgon is already Void",
    )
    return data, selected, key, result


def finish_contest(game):
    answer(
        game,
        ADMIN,
        "gorgon_contest_assets",
        options=("opposing-gorgon:0",),
        text="Actual awakened Dormant pits its real source Asset",
    )
    answer(
        game,
        ADMIN,
        "gorgon_contest_judge",
        options=("defender",),
        fields={"asset": "source-gorgon:0"},
        text="The source judge destroys the actual losing claw",
    )


def test_actual_gorgon_cost_precedes_contest_changes_sole_world_asset_no_pilot_or_rng(ledger):
    game, _, _, root, request, work, service = source(ledger)
    before = state(game)
    assert service.get(ADMIN, work)["dive_applicable"] is False
    with pytest.raises(WorkflowError, match="controller"):
        service.get(OTHER, work)
    data, selected, key, result = pay(service, work)
    assert (
        service.respond(
            ADMIN,
            key,
            work,
            data["revision"],
            data["game_revision"],
            selected,
            "Actual geometric flesh changes in this original Gorgon Asset",
        )
        == result
    )
    after = state(game)
    original = next(x for x in before.world.gorgons if x.id == "source-gorgon")
    creature = next(x for x in after.world.gorgons if x.id == "source-gorgon")
    for previous, actual in zip(original.assets, creature.assets, strict=True):
        if actual.id == selected:
            assert actual.void and actual.description != previous.description
            assert actual.model_dump(exclude={"void", "description"}) == previous.model_dump(
                exclude={"void", "description"}
            )
        else:
            assert actual == previous
    assert after.sheets == before.sheets and after.handler_heat == before.handler_heat
    assert after.harpy_states == before.harpy_states and after.placements == before.placements
    assert len([x for x in after.facts if x.get("kind") == "dormant_awakening"]) == 1
    assert len([x for x in after.facts if x.get("kind") == "gorgon_dormant_void_paid"]) == 1
    with ledger.engine.connect() as c:
        assert [x["kind"] for x in game.pending(c, root)] == ["gorgon_contest_assets"]
        assert not c.scalar(
            sa.select(t.m2["m2_responses"].c.choice_id).where(
                t.m2["m2_responses"].c.choice_id == request["id"]
            )
        )
    finish_contest(game)
    with ledger.engine.connect() as c:
        assert game.action(c, root)["state"] == "complete"
    assert game.dice.calls == 0


def test_actual_all_void_is_proved_without_new_asset_harpy_or_false_frame(ledger):
    game, _, _, root, _, work, service = source(ledger, actor_void=True)
    before = state(game)
    data = service.get(ADMIN, work)
    assert data["already_fully_void"] and not data["assets"] and not data["dive_applicable"]
    pay(service, work)
    after = state(game)
    assert after.world == before.world and after.sheets == before.sheets
    assert (
        after.harpy_states == before.harpy_states
        and after.void_thresholds == before.void_thresholds
    )
    assert after.frame_locks == before.frame_locks and game.dice.calls == 0
    finish_contest(game)
    with ledger.engine.connect() as c:
        assert game.action(c, root)["state"] == "complete"


def test_forged_fully_void_stale_pause_and_unrelated_body_never_pay_this_source(ledger):
    game, _, _, _, _, work, service = source(ledger)
    data = service.get(ADMIN, work)
    original = state(game).model_dump_json()
    with pytest.raises(WorkflowError, match="uncorrupted"):
        service.respond(
            ADMIN,
            str(uuid4()),
            work,
            data["revision"],
            data["game_revision"],
            None,
            "False fully Void claim",
        )
    with pytest.raises(WorkflowError, match="STALE"):
        service.respond(
            ADMIN,
            str(uuid4()),
            work,
            data["revision"] - 1,
            data["game_revision"],
            data["assets"][0]["id"],
            "Actual attempted alteration",
        )
    ledger.safety(ADMIN, str(uuid4()), ledger.status(ADMIN)["revision"], pause=True)
    with pytest.raises(WorkflowError, match="PAUSED|paused"):
        pay(service, work)
    assert state(game).model_dump_json() == original
    ledger.safety(ADMIN, str(uuid4()), ledger.status(ADMIN)["revision"], pause=False)
    with pytest.raises(ValueError, match="Gorgon"):
        inflict(
            state(game),
            ActorRef(kind="pilot", entity="2", incarnation=state(game).sheets["2"].character_id),
            ActorRef(kind="gorgon", entity="opposing-gorgon"),
            work,
            data["assets"][0]["id"],
            "Cannot pay with a controller or unrelated Pilot body",
            "actual-attempt",
        )
    assert state(game).model_dump_json() == original


def test_real_capability_review_source_can_stage_cost_and_native_owner_pays(ledger):
    game, _, _, root, request, work, service = source(ledger, damaged=True)
    assert service.get(ADMIN, work)["can_act"]

    async def run():
        caller = current(1)
        await caller.response.defer(ephemeral=True)
        await open_choice(caller, game, request["id"])
        form = caller.edit_original_response.call_args.kwargs["view"]
        assert isinstance(form, NativeForm) and not await form.interaction_check(current(3))
        assert {x.key for x in form.fields} == {"asset", "description"}
        asset = form.fields[0].options[0][0]
        form.values.update(asset=(asset,), description="This source flesh becomes Void-fractal")
        await form.confirm.callback(current(1, 994100))
        assert form.completed

    asyncio.run(run())
    with ledger.engine.connect() as c:
        assert [x["kind"] for x in game.pending(c, root)] == ["gorgon_contest_assets"]
    assert game.dice.calls == 0


def test_true_prior_persistent_awakening_prevents_duplicate_cost_on_next_attack(ledger):
    game, worker, gateway, root, _, work, service = source(ledger)
    pay(service, work)
    finish_contest(game)
    tick(worker, gateway, 5)
    driver = GorgonPlayService(game)
    data = driver.preview(ADMIN, 900)
    actor = next(x for x in data["actors"] if x["ref"]["entity"] == "source-gorgon")
    target = next(x for x in data["actors"] if x["ref"]["entity"] == "opposing-gorgon")
    declared = Declaration(
        kind="attack",
        actor=ActorRef.model_validate(actor["ref"]),
        target=ActorRef.model_validate(target["ref"]),
        assets=(actor["assets"][0]["id"],),
        actor_sha256=actor["source_sha256"],
        target_sha256=target["source_sha256"],
        account="Actual next attack against the same already awakened body",
        reach_confirmed=True,
    )
    next_root = driver.begin(ADMIN, str(uuid4()), 900, data["revision"], declared)["action_id"]
    tick(worker, gateway, 3)
    with ledger.engine.connect() as c:
        assert [x["kind"] for x in game.pending(c, next_root)] == ["gorgon_contest_assets"]
        assert awakened_source(game, c, state(game), declared.target)
    assert len([x for x in state(game).facts if x.get("kind") == "dormant_awakening"]) == 1
    assert len([x for x in state(game).facts if x.get("kind") == "gorgon_dormant_void_paid"]) == 1
    assert game.dice.calls == 0


def test_abort_preserves_actual_owed_cost_and_standalone_owner_can_pay_without_contest(ledger):
    game, worker, gateway, root, _, work, service = source(ledger)
    game.abort(ADMIN, str(uuid4()), root)
    tick(worker, gateway, 5)
    assert service.get(ADMIN, work)["can_act"]
    pay(service, work)
    assert service.get(ADMIN, work)["state"] == "resolved"
    with ledger.engine.connect() as c:
        assert game.action(c, root)["state"] == "aborted"
        assert not game.pending(c, root)
    assert game.dice.calls == 0


def test_resolved_flag_without_real_world_payment_cannot_resume_or_claim_complete(ledger):
    from girlframe.services.m3_collateral import append, latest
    from girlframe.services.m3_gorgon_dormant import paid_source

    game, _, _, root, _, work, service = source(ledger)
    with ledger.transaction() as c:
        row = latest(game, c, work)
        body = json.loads(row["body_json"])
        append(
            c,
            row,
            row["event_id"],
            body | dict(phase="paid", payment_event=row["event_id"]),
            "resolved",
        )
        with pytest.raises(WorkflowError, match="actual|resolved flag"):
            paid_source(game, c, game.action(c, root), work)
    with pytest.raises(WorkflowError, match="actual|resolved flag"):
        service.get(ADMIN, work)
    assert not any(x.get("kind") == "gorgon_dormant_void_paid" for x in state(game).facts)
    with ledger.engine.connect() as c:
        assert not any(x["kind"] == "gorgon_contest_assets" for x in game.pending(c, root))


@pytest.mark.parametrize("ended_entity", ["source-gorgon", "opposing-gorgon"])
def test_recorded_original_body_ending_closes_only_debtor_cost_not_defender_death(
    ledger, ended_entity
):
    """Canonical ending source test; actual Core native hook has separate combat coverage."""
    from girlframe.engine.m3_battle import end_actor_casts
    from girlframe.engine.m3_world import update
    from girlframe.services.m3_gorgon_dormant import synchronize_endings

    game, worker, gateway, root, _, work, service = source(ledger)
    game.abort(ADMIN, str(uuid4()), root)
    tick(worker, gateway, 5)
    original = state(game)
    actual = ActorRef(kind="gorgon", entity=ended_entity)
    with ledger.transaction() as c:
        event = str(uuid4())
        changed = end_actor_casts(original, actual, event)
        changed.world = update(
            changed.world,
            gorgons=tuple(
                x.model_copy(update={"alive": False}) if x.id == ended_entity else x
                for x in changed.world.gorgons
            ),
        )
        event = game.event(
            c,
            1,
            str(uuid4()),
            "synthetic.actual_recorded_body_ending",
            changed,
            target=actual.model_dump(mode="json"),
            event_id=event,
        )
        synchronize_endings(game, c, event, ADMIN, str(uuid4()))
    data = service.get(ADMIN, work)
    assert data["state"] == ("resolved" if ended_entity == "source-gorgon" else "pending")
    assert not any(x.get("kind") == "gorgon_dormant_void_paid" for x in state(game).facts)
    if ended_entity != "source-gorgon":
        pay(service, work)
        assert service.get(ADMIN, work)["state"] == "resolved"
    assert state(game).sheets == original.sheets
    assert state(game).harpy_states == original.harpy_states
    with ledger.engine.connect() as c:
        assert game.action(c, root)["state"] == "aborted"
    assert game.dice.calls == 0


def test_unstarted_menu_and_cancelled_dormant_own_intent_do_not_awaken_body(ledger):
    game, worker, gateway, root, _ = gorgon_source(
        ledger, gorgon_class="dormant", kind="collateral", advance=False
    )
    driver = GorgonPlayService(game)
    driver.preview(ADMIN, 900)
    assert not any(x.get("kind") == "dormant_awakening" for x in state(game).facts)
    game.abort(ADMIN, str(uuid4()), root)
    tick(worker, gateway, 5)
    assert not any(x.get("kind") == "dormant_awakening" for x in state(game).facts)
    assert game.dice.calls == 0


@pytest.mark.parametrize("damaged", [False, True])
def test_genuine_own_dormant_play_wakes_once_without_attack_counter_or_dive(ledger, damaged):
    game, _, _, root, _ = gorgon_source(
        ledger, gorgon_class="dormant", kind="collateral", damaged=damaged
    )
    before = state(game)
    markers = [x for x in before.facts if x.get("kind") == "dormant_awakening"]
    assert len(markers) == 1 and markers[0]["cause"] == "own_play"
    assert markers[0]["gorgon"] == "source-gorgon"
    with ledger.engine.connect() as c:
        assert awakened_source(game, c, before, ActorRef(kind="gorgon", entity="source-gorgon"))
        assert not c.scalar(
            sa.select(t.m3["m3_required_work"].c.id).where(
                t.m3["m3_required_work"].c.kind == "gorgon_dormant_void"
            )
        )
    answer(
        game,
        ADMIN,
        "gorgon_collateral",
        options=("environment",),
        text="The actual creature actively alters this local terrain",
    )
    assert game.roll(ADMIN, str(uuid4()), root)["receipt"] is None
    assert len([x for x in state(game).facts if x.get("kind") == "dormant_awakening"]) == 1
    creature = next(x for x in state(game).world.gorgons if x.id == "source-gorgon")
    assert creature.gorgon_class == "dormant" and creature.cell == (0, 0)
    assert creature.assets == next(x for x in before.world.gorgons if x.id == creature.id).assets
    assert state(game).sheets == before.sheets and game.dice.calls == 0


def test_bare_or_repointed_own_awakening_marker_cannot_replace_actual_history(ledger):
    game, _, _, root, _ = gorgon_source(ledger, gorgon_class="dormant", kind="collateral")
    invalid = state(game).model_copy(deep=True)
    marker = next(x for x in invalid.facts if x.get("kind") == "dormant_awakening")
    with ledger.engine.connect() as c:
        intent_event = game.action(c, root)["data"]["gorgon_play"]["source_event"]
        marker["event"] = intent_event
        with pytest.raises(WorkflowError, match="marker|proof|source|awakening"):
            awakened_source(game, c, invalid, ActorRef(kind="gorgon", entity="source-gorgon"))
    assert game.dice.calls == 0


def test_policy_change_keeps_source_readable_but_blocks_unapproved_payment(ledger):
    _, _, _, _, _, work, service = source(ledger)
    data = service.get(ADMIN, work)
    old = ledger.policy
    ledger.policy = old.model_copy(
        update={"m3_approval": old.m3_approval.model_copy(update={"registry_sha256": "f" * 64})}
    )
    assert service.get(ADMIN, work)["id"] == work
    with pytest.raises(WorkflowError):
        service.respond(
            ADMIN,
            str(uuid4()),
            work,
            data["revision"],
            data["game_revision"],
            data["assets"][0]["id"],
            "The source cannot skip current policy approval",
        )
    assert service.get(ADMIN, work)["state"] == "pending"


def test_source_abort_cannot_erase_debt_by_starting_another_gorgon_play(ledger):
    game, worker, gateway, root, _, work, service = source(ledger)
    game.abort(ADMIN, str(uuid4()), root)
    tick(worker, gateway, 5)
    driver = GorgonPlayService(game)
    data = driver.preview(ADMIN, 900)
    actor = next(x for x in data["actors"] if x["ref"]["entity"] == "source-gorgon")
    target = next(x for x in data["actors"] if x["ref"]["entity"] == "opposing-gorgon")
    declared = Declaration(
        kind="attack",
        actor=ActorRef.model_validate(actor["ref"]),
        target=ActorRef.model_validate(target["ref"]),
        assets=(actor["assets"][0]["id"],),
        actor_sha256=actor["source_sha256"],
        target_sha256=target["source_sha256"],
        account="Attempt to bypass the still-owed actual original counter",
        reach_confirmed=True,
    )
    with pytest.raises(WorkflowError, match="counter-Void"):
        driver.begin(ADMIN, str(uuid4()), 900, data["revision"], declared)
    assert service.get(ADMIN, work)["state"] == "pending" and game.dice.calls == 0
    with ledger.engine.connect() as c:
        assert game.lock(c, 900)["action_id"] == root and game.lock(c, 900)["state"] == "released"


def test_aborted_source_debt_remains_private_owned_inbox_task_and_real_native_payment(ledger):
    from girlframe.discord_adapter.inbox import InboxView
    from girlframe.services.inbox import InboxService

    game, worker, gateway, root, _, work, service = source(ledger)
    game.abort(ADMIN, str(uuid4()), root)
    tick(worker, gateway, 5)
    inbox = InboxService(ledger)
    items = [x for x in inbox.items(ADMIN) if x.identity == work]
    assert len(items) == 1 and items[0].task == "gorgon_dormant_void" and items[0].incoming
    assert not any(x.identity == work for x in inbox.items(OTHER))

    async def complete():
        caller = current(1, 980901)
        await caller.response.defer(ephemeral=True)
        await InboxView(inbox, 1).route(caller, items[0])
        form = caller.edit_original_response.call_args.kwargs["view"]
        assert isinstance(form, NativeForm) and not await form.interaction_check(current(3))
        assert {x.key for x in form.fields} == {"asset", "description"}
        data = service.get(ADMIN, work)
        form.values.update(
            asset=(data["assets"][0]["id"],), description="Owned actual Void rewrite"
        )
        await form.confirm.callback(current(1, 980902))
        assert form.completed

    asyncio.run(complete())
    assert service.get(ADMIN, work)["state"] == "resolved"
    assert not any(x.identity == work for x in inbox.items(ADMIN))
    with ledger.engine.connect() as c:
        assert game.action(c, root)["state"] == "aborted"
    assert game.dice.calls == 0


def test_source_debt_blocks_mission_and_off_duty_progress_even_when_owner_has_no_pilot(ledger):
    from girlframe.services.m3_missions import MissionService
    from girlframe.services.m3_off_duty import OffDutyService

    game, worker, gateway, root, _, work, service = source(ledger)
    game.abort(ADMIN, str(uuid4()), root)
    tick(worker, gateway, 5)
    original = state(game).model_dump_json()
    missions = MissionService(ledger)
    assert 1 not in state(game).order
    with pytest.raises(WorkflowError, match="counter-Void"):
        missions.offer(ADMIN, str(uuid4()), "Actual later mission", (2, 3))
    with pytest.raises(WorkflowError, match="counter-Void"):
        OffDutyService(missions).begin(ADMIN, str(uuid4()))
    assert state(game).model_dump_json() == original
    pay(service, work)
    assert missions.offer(ADMIN, str(uuid4()), "Actual later mission", (2, 3))["id"]
    assert game.dice.calls == 0


def test_denied_actual_dormant_capability_never_awakens_or_creates_counter(ledger):
    game, _, _, root, _ = gorgon_source(
        ledger,
        gorgon_class="dormant",
        kind="collateral",
        damaged=True,
        approve_capability=False,
    )
    assert not any(x.get("kind") == "dormant_awakening" for x in state(game).facts)
    answer(
        game,
        ADMIN,
        "gorgon_asset_capability",
        flag=False,
        text="The actual damaged source resource cannot perform this declared physical effect",
    )
    assert not any(x.get("kind") == "dormant_awakening" for x in state(game).facts)
    with ledger.engine.connect() as c:
        assert game.action(c, root)["state"] == "complete"
        assert not c.scalar(
            sa.select(t.m3["m3_required_work"].c.id).where(
                t.m3["m3_required_work"].c.kind == "gorgon_dormant_void"
            )
        )
    assert game.dice.calls == 0
