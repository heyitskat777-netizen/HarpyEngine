import asyncio
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger_fixture
from test_m2_game import state
from test_off_duty_cycle import activate, call, finish_routine, movement, recover_both, roll_for
from test_punishment_service import submit
from test_strain import facts
from test_strain_effect_service import pending, selected
from test_world import gorgon

from girlframe.engine.m2 import AssetState
from girlframe.engine.m3_core import RepairSelection
from girlframe.engine.m3_off_duty import RecoveryChoice
from girlframe.engine.m3_punishments import Details
from girlframe.engine.m3_strain_effects import Choice
from girlframe.engine.m3_world_state import Faction
from girlframe.services.inbox import InboxService
from girlframe.services.m3_off_duty_cycle import CycleService
from girlframe.services.m3_punishments import PunishmentService
from girlframe.services.m3_repairs import RepairService
from girlframe.services.onboarding import WorkflowError

ledger = ledger_fixture


def prepare_requests(effects, game, period, *, shortage=False, following=False):
    strain = effects.strain
    if following:
        strain.prepare(
            ADMIN,
            "following-prepare",
            period,
            1,
            state(game).revision,
            facts(no_girl_void=True, last_mission_success_no_frame_death_infrastructure_loss=True),
        )
    for track, face, column, choice in (
        (
            "void",
            2,
            1,
            Choice(
                rule_id="strain.void.low.2.1",
                account="An actual new arrival",
                gorgon=gorgon("dormant", "following-gorgon", (1, 1)),
            ),
        ),
        (
            "rebellion",
            1,
            1,
            Choice(
                rule_id="strain.rebellion.low.1.1",
                account="Actual organizing",
                target="city0",
                faction=Faction(
                    id="following-group" if following else "first-group",
                    name="Local organizing",
                    kind="rebel",
                    cells=((0, 4),),
                    description="Local demands",
                ),
            ),
        ),
        (
            "budget",
            4 if shortage else 5,
            2,
            Choice(
                rule_id="strain.budget.low.4.2" if shortage else "strain.budget.low.5.2",
                account="Actual repair limits" if shortage else "Actual room assignment",
                rooms=() if shortage else ((2, 3),),
            ),
        ),
    ):
        request = next((x for x in state(game).strain.requests if x.track == track), None)
        if request is None:
            continue
        strain.dice.face = face
        strain.roll(ADMIN, str(uuid4()), request.id, 1, state(game).revision)
        strain.choose(ADMIN, str(uuid4()), request.id, 2, state(game).revision, column)
        effects.apply(ADMIN, str(uuid4()), request.id + ":effect", 1, state(game).revision, choice)


def source_period(store):
    effects, game, period, first = pending(store)
    approval = store.policy.m3_approval
    store.policy = store.policy.model_copy(
        update={
            "m3_approval": approval.model_copy(
                update={"subsystems": approval.subsystems | {"plays", "economy"}}
            )
        }
    )
    effects.apply(ADMIN, "apply-actual-first", first, 1, state(game).revision, selected())
    prepare_requests(effects, game, period, shortage=True)
    return effects, CycleService(effects.strain.periods), game, period


def ready(store, *, recover=True):
    effects, cycle, game, period = source_period(store)
    activate(cycle, game, period)
    recover_both(cycle, game, period)
    finish_routine(cycle, game, period)
    call(cycle, game, ADMIN, period, "finish", movement(game))
    missions = cycle.missions
    offered = missions.offer(ADMIN, "actual-next-offer", "An actual next mission", (2, 3))
    missions.respond(PLAYER, "actual-next-yes-2", offered["id"], 1, "accept")
    missions.respond(OTHER, "actual-next-yes-3", offered["id"], 2, "accept")
    missions.start(ADMIN, "actual-next-dispatch", offered["id"], 3)
    ended = missions.end(ADMIN, "actual-next-end", offered["id"], 4, True)
    discipline = PunishmentService(store)
    for work in missions.get(ADMIN, offered["id"])["work"]:
        submit(discipline, ADMIN, work["id"], Details(kind="stimulant_injection"), str(uuid4()))
    missions.complete(ADMIN, "actual-next-complete", offered["id"], ended["revision"])
    # Synthetic combat fixture has actual intact spare armour, so this is not
    # a Defeat or an all-Frame/whole-roster Budget trigger.
    with store.transaction() as c:
        canon = state(game)
        sheet = canon.sheets["2"]
        sheet.assets.append(AssetState(id="spare", family="frame", name="Intact spare armour"))
        for asset in sheet.assets:
            if asset.id != "spare":
                asset.damaged = True
        sheet.revision += 1
        game.event(c, 1, "synthetic-combat-damage", "synthetic.fixture_combat_damage", canon)
    next_period = cycle.periods.begin(ADMIN, "actual-next-period")["id"]
    prepare_requests(effects, game, next_period, following=True)
    activate(cycle, game, next_period)
    svc = RepairService(cycle.periods)
    if recover:
        roll_for(cycle, game, next_period, PLAYER, (4, 4))
        call(cycle, game, PLAYER, next_period, "scene", None, (), "")
        call(
            cycle,
            game,
            PLAYER,
            next_period,
            "recover",
            RecoveryChoice(repairs=RepairSelection(girl=("girl:0",), frame=("frame:0",))),
        )
    return svc, cycle, game, next_period


def offer(svc, game, period, asset="frame:1", cost=1, key=None):
    return svc.offer(ADMIN, key or str(uuid4()), state(game).revision, period, 2, asset, cost)


def respond(svc, identity, *, accept=True, key=None):
    data = svc.get(PLAYER, identity)
    return svc.respond(
        PLAYER, key or str(uuid4()), identity, data["game_revision"], data["revision"], accept
    )


def test_source_event_arms_next_actual_mission_and_leaves_current_recovery_unrestricted(ledger):
    _, cycle, game, period = source_period(ledger)
    scope = state(game).repair_shortages[0]
    assert scope.source_period == period and scope.mission is scope.period is None
    assert cycle.review(PLAYER, period)["repair_limit"] is None
    activate(cycle, game, period)
    recover_both(cycle, game, period)
    assert cycle.review(PLAYER, period)["own"]["recovered"]


def test_actual_following_recovery_enforces_one_per_family_and_does_not_repair_the_rest(ledger):
    svc, cycle, game, period = ready(ledger, recover=False)
    scope = state(game).repair_shortages[0]
    assert (
        scope.mission
        and scope.dispatch_event
        and scope.mission_end_event
        and scope.period == period
    )
    assert cycle.review(PLAYER, period)["repair_limit"] == 1
    roll_for(cycle, game, period, PLAYER, (4, 4))
    call(cycle, game, PLAYER, period, "scene", None, (), "")
    before = state(game)
    for choice in (
        RecoveryChoice(),
        RecoveryChoice(repairs=RepairSelection(girl=("girl:0", "girl:1"), frame=("frame:0",))),
    ):
        with pytest.raises(WorkflowError):
            call(cycle, game, PLAYER, period, "recover", choice)
    assert state(game) == before
    call(
        cycle,
        game,
        PLAYER,
        period,
        "recover",
        RecoveryChoice(repairs=RepairSelection(girl=("girl:0",), frame=("frame:0",))),
    )
    damaged = {x.id for x in state(game).sheets["2"].assets if x.damaged}
    assert damaged == {"girl:1", "frame:1"}
    assert {x["asset"] for x in svc.eligible(ADMIN)["assets"]} == damaged
    with pytest.raises(WorkflowError):
        svc.eligible(PLAYER)


def test_exact_handler_quote_is_optional_private_and_owner_purchase_spends_once_with_no_dice(
    ledger,
):
    svc, _, game, period = ready(ledger)
    before = state(game).sheets["2"]
    calls = game.dice.calls
    quoted = offer(svc, game, period, cost=1)
    assert state(game).sheets["2"] == before
    assert svc.get(PLAYER, quoted["id"])["cost"] == 1
    assert quoted["id"] in str(InboxService(ledger).page(PLAYER))
    assert quoted["id"] not in str(InboxService(ledger).page(OTHER))
    with pytest.raises(WorkflowError):
        svc.get(OTHER, quoted["id"])
    with pytest.raises(WorkflowError):
        svc.respond(ADMIN, "not-owner", quoted["id"], state(game).revision, 1, True)
    data = svc.get(PLAYER, quoted["id"])
    result = svc.respond(
        PLAYER, "buy-once", quoted["id"], data["game_revision"], data["revision"], True
    )
    assert (
        svc.respond(PLAYER, "buy-once", quoted["id"], data["game_revision"], data["revision"], True)
        == result
    )
    sheet = state(game).sheets["2"]
    assert sheet.permissions == before.permissions - 1
    assert next(x for x in sheet.assets if x.id == "frame:1").damaged is False
    assert next(x for x in sheet.assets if x.id == "girl:1").damaged is True
    assert game.dice.calls == calls


def test_repricing_stale_sheets_and_unaffordable_offer_never_spend_or_repair(ledger):
    svc, _, game, period = ready(ledger)
    quote = offer(svc, game, period, cost=999)
    before = state(game)
    with pytest.raises(WorkflowError, match="Insufficient"):
        respond(svc, quote["id"])
    assert state(game) == before
    old = svc.get(PLAYER, quote["id"])
    svc.offer(ADMIN, "reprice", state(game).revision, period, 2, "frame:1", 1, quote["id"], 1)
    with pytest.raises(WorkflowError, match="STALE_QUOTE"):
        svc.respond(PLAYER, "stale-price", quote["id"], state(game).revision, old["revision"], True)
    with ledger.transaction() as c:
        canon = state(game)
        canon.sheets["2"].heat += 1
        canon.sheets["2"].revision += 1
        game.event(c, 1, "intervening-state", "synthetic.heat", canon)
    before = state(game)
    assert not svc.get(PLAYER, quote["id"])["available"]
    with pytest.raises(WorkflowError, match="STALE_QUOTE"):
        respond(svc, quote["id"])
    assert state(game) == before


def test_quote_rollback_pause_revocation_and_rebuild_preserve_optional_human_response(
    ledger, monkeypatch
):
    svc, _, game, period = ready(ledger)
    quote = offer(svc, game, period)
    before = state(game)
    ledger.safety(OTHER, "pause-paid-repair", ledger.status(OTHER)["revision"], pause=True)
    with pytest.raises(WorkflowError, match="SAFETY_PAUSED"):
        respond(svc, quote["id"])
    ledger.safety(OTHER, "resume-paid-repair", ledger.status(OTHER)["revision"], pause=False)
    original = svc.game.event

    def fail(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError("synthetic after-repair failure")

    monkeypatch.setattr(svc.game, "event", fail)
    with pytest.raises(RuntimeError):
        respond(svc, quote["id"], key="repair-retry")
    assert state(game) == before
    monkeypatch.setattr(svc.game, "event", original)
    game.rebuild()
    assert RepairService(svc.periods).get(PLAYER, quote["id"])["state"] == "pending"
    policy = ledger.policy
    ledger.policy = policy.model_copy(update={"m3_approval": None})
    with pytest.raises(WorkflowError, match="REVIEW_PENDING"):
        respond(svc, quote["id"])
    ledger.policy = policy
    respond(svc, quote["id"], key="repair-retry")
    assert svc.get(PLAYER, quote["id"])["state"] == "accepted"


@pytest.mark.parametrize("change_kind", ("character", "frame"))
def test_changed_character_or_frame_cannot_inherit_a_saved_repair_offer(ledger, change_kind):
    from test_actor_service import replace_profile_id

    svc, _, game, period = ready(ledger)
    quote = offer(svc, game, period)
    if change_kind == "character":
        replace_profile_id(ledger, 2)
        assert not svc.list(PLAYER)
    else:
        from girlframe.engine.m3_frame_state import FrameRuntime

        with ledger.transaction() as c:
            canon = state(game)
            canon.sheets["2"].frame_runtime = FrameRuntime(
                id="different-frame-body", generation=2, source_work="synthetic-frame-replacement"
            )
            game.event(c, 1, "synthetic-frame-change", "synthetic.fixture_frame", canon)
        assert not svc.get(PLAYER, quote["id"])["available"]
    with pytest.raises(WorkflowError):
        respond(svc, quote["id"])


def test_concurrent_two_offers_for_same_asset_cannot_charge_twice_and_decline_is_ooc(ledger):
    svc, _, game, period = ready(ledger)
    first, second = offer(svc, game, period), offer(svc, game, period)
    before = state(game).sheets["2"].permissions
    data = svc.get(PLAYER, first["id"])

    def run(item):
        try:
            svc.respond(PLAYER, str(uuid4()), item["id"], data["game_revision"], 1, True)
            return True
        except WorkflowError:
            return False

    with ThreadPoolExecutor(2) as pool:
        assert sorted(pool.map(run, (first, second))) == [False, True]
    assert state(game).sheets["2"].permissions == before - 1
    pending_quote = next(x for x in state(game).repair_quotes if x.state == "pending")
    ledger.safety(OTHER, "pause-decline", ledger.status(OTHER)["revision"], pause=True)
    respond(svc, pending_quote.id, accept=False)
    assert svc.get(PLAYER, pending_quote.id)["state"] == "declined"


def test_native_quote_and_optional_owned_purchase_require_separate_confirmations(ledger):
    from test_mission_ui import current

    from girlframe.discord_adapter.m3_repairs import open_quote, open_repairs

    svc, _, game, _ = ready(ledger)

    async def run():
        viewer = current(1)
        await viewer.response.defer(ephemeral=True)
        await open_repairs(viewer, svc)
        picker = viewer.edit_original_response.call_args.kwargs["view"]
        await picker.open_item(viewer, "offer")
        form = viewer.edit_original_response.call_args.kwargs["view"]
        form.values = {"asset": ("0",), "cost": "1"}
        before = state(game).sheets["2"]
        await form.confirm.callback(current(1, 16201))
        assert form.completed and state(game).sheets["2"] == before
        quote = state(game).repair_quotes[-1]
        owner = current(2)
        await owner.response.defer(ephemeral=True)
        await open_quote(owner, svc, quote.id)
        response = owner.edit_original_response.call_args.kwargs["view"]
        assert not await response.interaction_check(current(3))
        response.values = {"answer": ("accept",)}
        await response.confirm.callback(current(2, 16202))
        assert response.completed and state(game).sheets["2"].permissions == before.permissions - 1

    asyncio.run(run())


def test_shortage_recovery_dropdowns_choose_the_actual_free_assets(ledger):
    from test_mission_ui import current

    from girlframe.discord_adapter.m3_off_duty_cycle import open_action

    _, cycle, game, period = ready(ledger, recover=False)
    roll_for(cycle, game, period, PLAYER, (4, 4))
    call(cycle, game, PLAYER, period, "scene", None, (), "")

    async def run():
        viewer = current(2)
        await viewer.response.defer(ephemeral=True)
        await open_action(viewer, cycle, period, "recover")
        form = viewer.edit_original_response.call_args.kwargs["view"]
        fields = {x.key: x for x in form.fields}
        assert set(dict(fields["repair_girl"].options)) == {"girl:0", "girl:1"}
        assert set(dict(fields["repair_frame"].options)) == {"frame:0", "frame:1"}
        form.values.update(repairs=("yes",), repair_girl=("girl:1",), repair_frame=("frame:1",))
        await form.confirm.callback(current(2, 16203))
        assert form.completed and cycle.review(PLAYER, period)["own"]["recovered"]
        assert {x.id for x in state(game).sheets["2"].assets if x.damaged} == {"girl:0", "frame:0"}

    asyncio.run(run())


def test_pending_play_and_chat_restoration_block_purchase_before_resources_change(ledger):
    from test_m2_game import Gateway, start, tick

    from girlframe.delivery.m2_worker import GameWorker

    svc, _, game, period = ready(ledger)
    quote = offer(svc, game, period)
    held_heat = state(game).sheets["2"].heat
    action = start(game, heat=held_heat if held_heat >= 5 else 0)
    before = state(game)
    with pytest.raises(WorkflowError, match="restore chat"):
        respond(svc, quote["id"])
    assert state(game) == before
    game.abort(ADMIN, "abort-before-paid-repair", action)
    with pytest.raises(WorkflowError, match="restore chat"):
        respond(svc, quote["id"])
    tick(GameWorker(game), Gateway(), 5)
    respond(svc, quote["id"])
    assert svc.get(PLAYER, quote["id"])["state"] == "accepted"


def test_actual_period_close_ends_the_one_use_restriction_and_invalidates_unaccepted_quotes(ledger):
    svc, cycle, game, period = ready(ledger)
    quote = offer(svc, game, period)
    roll_for(cycle, game, period, OTHER, (2, 2))
    call(cycle, game, OTHER, period, "scene", None, (), "")
    call(cycle, game, OTHER, period, "recover", RecoveryChoice(repairs=RepairSelection()))
    finish_routine(cycle, game, period)
    call(cycle, game, ADMIN, period, "finish", movement(game))
    before = state(game)
    assert before.repair_shortages[0].closed and not svc.get(PLAYER, quote["id"])["available"]
    with pytest.raises(WorkflowError):
        respond(svc, quote["id"])
    assert state(game) == before
