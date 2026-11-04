import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
import sqlalchemy as sa
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger_fixture
from test_m2_game import Dice, Gateway, answer, state, tick
from test_off_duty_cycle import activate, call, finish_routine, movement, prepared, roll_for

from girlframe.database import tables as t
from girlframe.delivery.m2_worker import GameWorker
from girlframe.engine.m2 import PlayInput, TagState
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_off_duty import RecoveryChoice
from girlframe.engine.m3_requisition_state import GirlAsset
from girlframe.services.inbox import InboxService
from girlframe.services.m2_game import GameService
from girlframe.services.m3_comforts import ComfortService
from girlframe.services.m3_play_support import resume
from girlframe.services.onboarding import WorkflowError

ledger = ledger_fixture


def ready(store):
    cycle, game, period = prepared(store)
    approval = store.policy.m3_approval
    store.policy = store.policy.model_copy(
        update={
            "m3_approval": approval.model_copy(
                update={"subsystems": approval.subsystems | {"economy"}}
            )
        }
    )
    with store.transaction() as c:
        canon = state(game)
        canon.sheets["2"].permissions = 4
        game.event(c, 1, "synthetic-comforts-funds", "synthetic.permissions", canon)
    return ComfortService(game), cycle, game, period


def pay(svc, key=None):
    data = svc.view(PLAYER)
    return svc.buy_comforts(
        PLAYER,
        key or str(uuid4()),
        ActorRef.model_validate(data["actor"]),
        data["source_sha256"],
        "PRIVATE_PAID_REQUEST",
    )


def offered(store, *, count=1, faces=(2, 2)):
    svc, cycle, game, period = ready(store)
    receipts = [pay(svc) for _ in range(count)]
    activate(cycle, game, period)
    action = roll_for(cycle, game, period, PLAYER, faces)
    return svc, cycle, game, period, receipts, action


def record(svc, identity, *, together=False):
    data = svc.get(PLAYER, identity, 900)
    roles = tuple(
        ActorRef.model_validate(x["ref"])
        for x in data["roles"]
        if x["ref"]["kind"] == "pilot" and (together or x["ref"]["entity"] == "2")
    )
    return svc.record_scene(
        PLAYER,
        str(uuid4()),
        identity,
        data["revision"],
        900,
        data["cast_revision"],
        roles,
        "base0",
        "PRIVATE_SHARED_IMPROVEMENT_SCENE",
    )


def grant(svc, identity, key=None, *, data=None):
    data = data or svc.get(PLAYER, identity)
    return svc.grant(
        PLAYER,
        key or str(uuid4()),
        identity,
        data["revision"],
        data["source_sha256"],
        GirlAsset(name="PRIVATE_NEW_OUTFIT", description="PRIVATE_ASSET_REFLECTS_SCENE"),
    )


def test_actual_paid_purchase_qualifies_once_only_after_actual_named_final_roll(ledger):
    svc, cycle, game, period, receipts, action = offered(ledger)
    rows = svc.list(PLAYER)
    assert len(rows) == 1 and rows[0]["state"] == "pending"
    data = svc.get(PLAYER, rows[0]["id"])
    assert data["total"] == 8 and data["taken"] is None and data["scene"] is None
    assert state(game).sheets["2"].permissions == 3
    assert not svc.list(OTHER)
    with ledger.engine.connect() as c:
        work = svc._row(c, rows[0]["id"])
        benefit = svc._benefit(work)
        assert benefit.action == action and benefit.purchase == receipts[0]["id"]
        events = list(c.scalars(sa.select(t.events.c.id)))
        assert benefit.raw_event in events and benefit.qualification_event in events
    assert game.dice.calls == 1


def test_low_roll_retains_paid_purchase_without_a_scene_opportunity_or_asset(ledger):
    svc, cycle, game, period, receipts, action = offered(ledger, faces=(1, 1))
    assert not svc.list(PLAYER)
    assert state(game).sheets["2"].permissions == 3
    assert state(game).requisitions[-1].id == receipts[0]["id"]
    assert game.dice.calls == 1


def test_purchase_after_known_roll_does_not_retroactively_claim_it(ledger):
    svc, cycle, game, period = ready(ledger)
    activate(cycle, game, period)
    roll_for(cycle, game, period, PLAYER, (2, 2))
    pay(svc)
    assert not svc.list(PLAYER)
    roll_for(cycle, game, period, OTHER, (4, 4))
    assert not svc.list(PLAYER) and state(game).sheets["2"].permissions == 3


def test_owner_may_decline_optional_opportunity_without_a_refund_or_scene(ledger):
    svc, cycle, game, period, receipts, action = offered(ledger)
    identity = svc.list(PLAYER)[0]["id"]
    data = svc.get(PLAYER, identity)
    before = state(game)
    with pytest.raises(WorkflowError, match="other participants"):
        svc.decline(OTHER, "not-your-opportunity", identity, data["revision"], "No")
    result = svc.decline(
        PLAYER,
        "decline-actual-opportunity",
        identity,
        data["revision"],
        "I decline this optional improvement scene",
    )
    assert result["taken"] is False and state(game) == before
    assert svc.get(PLAYER, identity)["state"] == "resolved"
    assert state(game).sheets["2"].permissions == 3
    call(cycle, game, PLAYER, period, "scene", None, (), "")
    call(cycle, game, PLAYER, period, "recover", RecoveryChoice())


def test_two_paid_sources_qualify_separately_and_optional_choices_block_false_recovery(ledger):
    svc, cycle, game, period, receipts, action = offered(ledger, count=2)
    rows = svc.list(PLAYER)
    assert len(rows) == 2 and state(game).sheets["2"].permissions == 2
    call(cycle, game, PLAYER, period, "scene", None, (), "")
    with pytest.raises(WorkflowError):
        call(cycle, game, PLAYER, period, "recover", RecoveryChoice())
    for row in rows:
        svc.decline(
            PLAYER,
            str(uuid4()),
            row["id"],
            row["revision"],
            "No optional improvement scene for this paid opportunity",
        )
    call(cycle, game, PLAYER, period, "recover", RecoveryChoice())
    assert game.dice.calls == 1 and len(state(game).requisitions) == 2


def test_actual_solo_scene_then_explicit_current_asset_choice_grants_exactly_once(ledger):
    svc, cycle, game, period, receipts, action = offered(ledger)
    identity = svc.list(PLAYER)[0]["id"]
    before = state(game)
    recorded = record(svc, identity)
    assert recorded["ready"] and state(game) == before
    data = svc.get(PLAYER, identity)
    first = grant(svc, identity, "actual-gift-once", data=data)
    assert grant(svc, identity, "actual-gift-once", data=data) == first
    after = state(game)
    assert len(after.sheets["2"].assets) == len(before.sheets["2"].assets) + 1
    assert after.sheets["2"].permissions == before.sheets["2"].permissions == 3
    assert after.sheets["2"].assets[-1].family == "girl" and not after.sheets["2"].assets[-1].void
    assert svc.get(PLAYER, identity)["asset_name"] == "PRIVATE_NEW_OUTFIT"
    assert not svc.list(OTHER)
    assert ComfortService(GameService(ledger)).get(PLAYER, identity) == svc.get(PLAYER, identity)
    game.rebuild()
    assert state(game) == after
    with ledger.engine.connect() as c:
        metadata = list(c.scalars(sa.select(t.events.c.payload_json)))
        outbox = list(c.scalars(sa.select(t.m2["m2_outbox"].c.body_json)))
        assert "PRIVATE_" not in json.dumps(metadata + outbox)


def test_scene_participants_own_attendance_and_do_not_receive_private_sheet_or_cost_details(ledger):
    svc, cycle, game, period, receipts, action = offered(ledger)
    identity = svc.list(PLAYER)[0]["id"]
    record(svc, identity, together=True)
    own = svc.get(PLAYER, identity)
    assert not own["ready"] and own["scene"]["awaiting"] == 1
    with pytest.raises(WorkflowError):
        grant(svc, identity)
    other = svc.get(OTHER, identity)
    assert "PRIVATE_SHARED_IMPROVEMENT_SCENE" in str(other)
    assert "total" not in other and "girl_assets" not in other and "source_sha256" not in other
    assert "PRIVATE_PAID_REQUEST" not in str(other)
    assert len(other["scene"]["own_roles"]) == 1 and other["scene"]["own_roles"][0]["entity"] == "3"
    with pytest.raises(WorkflowError, match="other participants"):
        svc.get(ADMIN, identity)
    svc.attest(OTHER, "my-actual-attendance", identity, other["revision"])
    assert svc.get(PLAYER, identity)["ready"]
    grant(svc, identity)
    assert "PRIVATE_NEW_OUTFIT" not in str(svc.get(OTHER, identity))
    assert "PRIVATE_ASSET_REFLECTS_SCENE" not in str(svc.get(OTHER, identity))


def test_scene_attendance_is_ooc_during_pause_but_asset_grant_waits_for_resume(ledger):
    svc, cycle, game, period, receipts, action = offered(ledger)
    identity = svc.list(PLAYER)[0]["id"]
    record(svc, identity, together=True)
    ledger.safety(ADMIN, "pause-comforts", ledger.status(ADMIN)["revision"], pause=True)
    data = svc.get(OTHER, identity)
    before = state(game)
    svc.attest(OTHER, "historical-attendance-during-pause", identity, data["revision"])
    assert state(game) == before and svc.get(PLAYER, identity)["ready"]
    with pytest.raises(WorkflowError, match="SAFETY_PAUSED"):
        grant(svc, identity)
    assert state(game) == before
    ledger.safety(ADMIN, "resume-comforts", ledger.status(ADMIN)["revision"], pause=False)
    assert grant(svc, identity)["taken"]


def test_same_body_draft_edit_preserves_owed_benefit_but_replacement_body_cannot_take_it(ledger):
    svc, cycle, game, period, receipts, action = offered(ledger)
    identity = svc.list(PLAYER)[0]["id"]
    with ledger.transaction() as c:
        c.execute(
            t.characters.update()
            .where(t.characters.c.campaign_id == ledger.campaign_id, t.characters.c.user_id == "2")
            .values(revision=t.characters.c.revision + 1)
        )
    record(svc, identity)
    original = svc.get(PLAYER, identity)
    with ledger.transaction() as c:
        c.execute(
            t.characters.update()
            .where(t.characters.c.campaign_id == ledger.campaign_id, t.characters.c.user_id == "2")
            .values(id=str(uuid4()))
        )
    with pytest.raises(WorkflowError, match="STALE_ACTOR"):
        grant(svc, identity, data=original)
    assert state(game).sheets["2"].permissions == 3
    assert not any(x.get("kind") == "creature_comforts_asset" for x in state(game).facts)


def test_rollback_after_gift_history_keeps_the_same_owned_opportunity_and_paid_cost(
    ledger, monkeypatch
):
    svc, cycle, game, period, receipts, action = offered(ledger)
    identity = svc.list(PLAYER)[0]["id"]
    record(svc, identity)
    data, before = svc.get(PLAYER, identity), state(game)
    event = game.event

    def fail(*args, **kwargs):
        event(*args, **kwargs)
        raise RuntimeError("synthetic failure after gift canonical history")

    monkeypatch.setattr(game, "event", fail)
    with pytest.raises(RuntimeError):
        grant(svc, identity, "retry-actual-gift", data=data)
    assert state(game) == before and svc.get(PLAYER, identity)["taken"] is None
    monkeypatch.setattr(game, "event", event)
    grant(svc, identity, "retry-actual-gift", data=data)
    assert svc.get(PLAYER, identity)["taken"] and state(game).sheets["2"].permissions == 3


def test_inbox_requires_actual_participant_attendance_and_clears_each_owned_next_step(ledger):
    svc, cycle, game, period, receipts, action = offered(ledger)
    identity = svc.list(PLAYER)[0]["id"]
    assert any(
        x.task == "m3_comforts" and x.identity == identity
        for x in InboxService(ledger).items(PLAYER)
    )
    assert not any(x.task == "m3_comforts" for x in InboxService(ledger).items(OTHER))
    record(svc, identity, together=True)
    assert any(
        x.task == "m3_comforts" and x.identity == identity
        for x in InboxService(ledger).items(OTHER)
    )
    data = svc.get(OTHER, identity)
    svc.attest(OTHER, "actual-inbox-attendance", identity, data["revision"])
    assert not any(x.task == "m3_comforts" for x in InboxService(ledger).items(OTHER))
    assert any(x.task == "m3_comforts" for x in InboxService(ledger).items(PLAYER))
    grant(svc, identity)
    assert not any(x.task == "m3_comforts" for x in InboxService(ledger).items(PLAYER))


def test_native_paid_comforts_wait_for_actual_roll_and_owned_scene_then_write_real_asset(ledger):
    from test_mission_ui import current

    from girlframe.discord_adapter.m3_comforts import open_comfort
    from girlframe.discord_adapter.m3_requisitions import open_requisitions

    svc, cycle, game, period = ready(ledger)

    async def purchase():
        caller = current(2, 16001)
        await caller.response.defer(ephemeral=True)
        await open_requisitions(caller, svc)
        queue = caller.edit_original_response.call_args.kwargs["view"]
        assert not await queue.interaction_check(current(3))
        selected = current(2, 16002)
        await selected.response.defer(ephemeral=True)
        await queue.open_item(selected, "buy-comforts")
        form = selected.edit_original_response.call_args.kwargs["view"]
        assert not await form.interaction_check(current(3))
        assert not state(game).requisitions and state(game).sheets["2"].permissions == 4
        form.values.update(account="PRIVATE_PAID_NATIVE_REQUEST", confirm=("yes",))
        await form.confirm.callback(current(2, 16003))
        assert form.completed and state(game).sheets["2"].permissions == 3
        assert not svc.list(PLAYER) and svc.receipts(PLAYER)[0]["state"] == "waiting_for_roll"

    asyncio.run(purchase())
    activate(cycle, game, period)
    roll_for(cycle, game, period, PLAYER, (2, 2))
    identity = svc.list(PLAYER)[0]["id"]

    async def scene_and_asset():
        owner = current(2, 16004)
        owner.channel_id = 900
        await owner.response.defer(ephemeral=True)
        await open_comfort(owner, svc, identity)
        picker = owner.edit_original_response.call_args.kwargs["view"]
        selected = current(2, 16005)
        selected.channel_id = 900
        await selected.response.defer(ephemeral=True)
        await picker.open_item(selected, "scene")
        form = selected.edit_original_response.call_args.kwargs["view"]
        data = svc.get(PLAYER, identity, 900)
        role = next(
            x["token"]
            for x in data["roles"]
            if x["ref"]["kind"] == "pilot" and x["ref"]["entity"] == "2"
        )
        form.values.update(
            location=("base0",),
            participants=(role,),
            summary="PRIVATE_ACTUAL_SOLO_SCENE",
            confirm=("yes",),
        )
        await form.confirm.callback(current(2, 16006))
        assert form.completed and svc.get(PLAYER, identity)["ready"]
        owner = current(2, 16007)
        await owner.response.defer(ephemeral=True)
        await open_comfort(owner, svc, identity)
        gift = owner.edit_original_response.call_args.kwargs["view"]
        assert not await gift.interaction_check(current(3))
        gift.values.update(
            name="PRIVATE_NATIVE_OUTFIT",
            description="Reflects the actual improvement scene",
            confirm=("yes",),
        )
        await gift.confirm.callback(current(2, 16008))
        assert gift.completed and state(game).sheets["2"].assets[-1].name == "PRIVATE_NATIVE_OUTFIT"
        assert state(game).sheets["2"].permissions == 3

    asyncio.run(scene_and_asset())


def test_native_attendance_and_decline_are_private_owned_choices_and_explain_no_refund(ledger):
    from test_mission_ui import current

    from girlframe.discord_adapter.m3_comforts import open_comfort

    svc, cycle, game, period, receipts, action = offered(ledger, count=2)
    first, second = svc.list(PLAYER)
    record(svc, first["id"], together=True)

    async def run():
        other = current(3, 16101)
        await other.response.defer(ephemeral=True)
        await open_comfort(other, svc, first["id"])
        form = other.edit_original_response.call_args.kwargs["view"]
        assert not await form.interaction_check(current(2))
        form.values["confirm"] = ("yes",)
        await form.confirm.callback(current(3, 16102))
        assert form.completed and svc.get(PLAYER, first["id"])["ready"]
        owner = current(2, 16103)
        owner.channel_id = None
        await owner.response.defer(ephemeral=True)
        await open_comfort(owner, svc, second["id"])
        picker = owner.edit_original_response.call_args.kwargs["view"]
        selected = current(2, 16104)
        await selected.response.defer(ephemeral=True)
        await picker.open_item(selected, "decline")
        decline = selected.edit_original_response.call_args.kwargs["view"]
        assert "no refund" in decline.instructions
        decline.values.update(account="I decline the unused opportunity", confirm=("yes",))
        await decline.confirm.callback(current(2, 16105))
        assert decline.completed and svc.get(PLAYER, second["id"])["taken"] is False

    asyncio.run(run())
    assert state(game).sheets["2"].permissions == 2 and game.dice.calls == 1


def start_roll(game, period, faces=(2, 2)):
    game.dice = Dice(faces)
    action = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play="go_off_duty",
            context="Actual time at base",
            trigger_confirmed=True,
            heat=0,
            off_duty_id=period,
        ),
    )["action_id"]
    worker, gateway = GameWorker(game), Gateway()
    tick(worker, gateway)
    return action, worker, gateway


@pytest.mark.parametrize(
    "faces,direction,eligible,total", [((1, 2), 1, True, 9), ((2, 2), -1, False, 6)]
)
def test_actual_post_roll_tag_modifier_can_qualify_or_remove_the_paid_opportunity(
    ledger, faces, direction, eligible, total
):
    svc, cycle, game, period = ready(ledger)
    pay(svc)
    with ledger.transaction() as c:
        canon = state(game)
        canon.sheets["2"].tags.append(
            TagState(id="actual-tag", label="An observed Tag", giver=3, observers=(1, 2, 3))
        )
        game.event(c, 1, "synthetic-actual-tag", "synthetic.tag", canon)
    activate(cycle, game, period)
    action, worker, gateway = start_roll(game, period, faces)
    for viewer in (PLAYER, ADMIN):
        answer(game, viewer, "tag_window", options=("pass",))
    answer(
        game,
        OTHER,
        "tag_window",
        options=("tag",),
        denied=("actual-tag",),
        number=direction,
        text="Relevant actual scene detail",
    )
    rows = svc.list(PLAYER)
    assert bool(rows) == eligible
    assert game.inspect(PLAYER, action)["result"]["total"] == total
    if rows:
        assert svc.get(PLAYER, rows[0]["id"])["total"] == total
    assert game.dice.calls == 1 and state(game).sheets["2"].permissions == 3


def test_paid_after_known_aborted_roll_cannot_retroactively_qualify_on_resume(ledger):
    svc, cycle, game, period = ready(ledger)
    first = pay(svc)
    activate(cycle, game, period)
    action, worker, gateway = start_roll(game, period)
    receipt = game.inspect(PLAYER, action)["receipt"]
    game.abort(ADMIN, "abort-known-off-duty-before-benefit", action)
    tick(worker, gateway, 5)
    second = pay(svc)
    with ledger.engine.connect() as c:
        revision = game.action(c, action)["revision"]
    resume(game, PLAYER, "resume-known-off-duty-before-benefit", action, revision)
    tick(worker, gateway)
    for viewer in (PLAYER, OTHER, ADMIN):
        answer(game, viewer, "tag_window", options=("pass",))
    rows = svc.list(PLAYER)
    assert len(rows) == 1
    with ledger.engine.connect() as c:
        benefit = svc._benefit(svc._row(c, rows[0]["id"]))
    assert benefit.purchase == first["id"] and benefit.purchase != second["id"]
    assert game.inspect(PLAYER, action)["receipt"] == receipt and game.dice.calls == 1
    assert (
        next(x for x in svc.receipts(PLAYER) if x["id"] == second["id"])["state"]
        == "waiting_for_roll"
    )


def test_second_queued_benefit_failure_rolls_back_final_choice_and_all_new_work_without_reroll(
    ledger, monkeypatch
):
    import girlframe.services.m3_comforts as implementation

    svc, cycle, game, period = ready(ledger)
    pay(svc)
    pay(svc)
    activate(cycle, game, period)
    action, worker, gateway = start_roll(game, period)
    for viewer in (PLAYER, OTHER):
        answer(game, viewer, "tag_window", options=("pass",))
    last = next(x for x in game.choices(ADMIN) if x["kind"] == "tag_window")
    before, receipt = state(game), game.inspect(PLAYER, action)["receipt"]
    original, calls = implementation.related, []

    def fail(*args, **kwargs):
        original(*args, **kwargs)
        calls.append(1)
        if len(calls) == 2:
            raise RuntimeError("synthetic second queued benefit failure")

    from girlframe.engine.m2 import ChoiceAnswer

    monkeypatch.setattr(implementation, "related", fail)
    with pytest.raises(RuntimeError):
        game.respond(
            ADMIN,
            "retry-final-comforts-choice",
            last["id"],
            last["revision"],
            ChoiceAnswer(options=("pass",)),
        )
    assert state(game) == before and not svc.list(PLAYER)
    assert any(x["id"] == last["id"] for x in game.choices(ADMIN))
    assert game.inspect(PLAYER, action)["receipt"] == receipt and game.dice.calls == 1
    monkeypatch.setattr(implementation, "related", original)
    game.respond(
        ADMIN,
        "retry-final-comforts-choice",
        last["id"],
        last["revision"],
        ChoiceAnswer(options=("pass",)),
    )
    assert (
        len(svc.list(PLAYER)) == 2
        and state(game).sheets["2"].permissions == 2
        and game.dice.calls == 1
    )


def test_concurrent_same_gift_is_once_and_stale_distinct_gift_does_not_add_an_asset(ledger):
    svc, cycle, game, period, receipts, action = offered(ledger)
    identity = svc.list(PLAYER)[0]["id"]
    record(svc, identity)
    data, before = svc.get(PLAYER, identity), len(state(game).sheets["2"].assets)
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(
            pool.map(lambda _: grant(svc, identity, "concurrent-owned-gift", data=data), range(2))
        )
    assert outcomes[0] == outcomes[1]
    assert len(state(game).sheets["2"].assets) == before + 1
    with pytest.raises(WorkflowError, match="STALE_COMFORTS"):
        grant(svc, identity, data=data)
    assert state(game).sheets["2"].permissions == 3


def test_paid_low_roll_source_survives_real_period_end_mission_and_next_period_qualifier(ledger):
    from test_punishment_service import submit
    from test_repair_service import prepare_requests
    from test_strain_service import D6

    from girlframe.engine.m3_punishments import Details
    from girlframe.services.m3_punishments import PunishmentService
    from girlframe.services.m3_strain import StrainService
    from girlframe.services.m3_strain_effects import EffectService

    svc, cycle, game, period, receipts, first_action = offered(ledger, faces=(1, 1))
    call(cycle, game, PLAYER, period, "scene", "handler_office", (2, 1), "An actual harsh scene")
    for viewer in (PLAYER, ADMIN):
        call(cycle, game, viewer, period, "acknowledge", 2)
    call(cycle, game, PLAYER, period, "recover", RecoveryChoice())
    roll_for(cycle, game, period, OTHER, (4, 4))
    call(cycle, game, OTHER, period, "scene", None, (), "")
    call(cycle, game, OTHER, period, "recover", RecoveryChoice())
    finish_routine(cycle, game, period)
    call(cycle, game, ADMIN, period, "finish", movement(game))
    assert not svc.list(PLAYER) and svc.receipts(PLAYER)[0]["state"] == "waiting_for_roll"
    missions = cycle.missions
    offer = missions.offer(ADMIN, "comforts-next-mission", "Actual intervening mission", (2, 3))
    missions.respond(PLAYER, "comforts-accept-2", offer["id"], 1, "accept")
    missions.respond(OTHER, "comforts-accept-3", offer["id"], 2, "accept")
    missions.start(ADMIN, "comforts-dispatch", offer["id"], 3)
    ended = missions.end(ADMIN, "comforts-end-mission", offer["id"], 4, True)
    discipline = PunishmentService(ledger)
    for work in missions.get(ADMIN, offer["id"])["work"]:
        submit(discipline, ADMIN, work["id"], Details(kind="stimulant_injection"), str(uuid4()))
    missions.complete(ADMIN, "comforts-complete-mission", offer["id"], ended["revision"])
    following = cycle.periods.begin(ADMIN, "comforts-next-period")["id"]
    effects = EffectService(StrainService(cycle.periods, dice=D6()))
    prepare_requests(effects, game, following, following=True)
    activate(cycle, game, following)
    second_action = roll_for(cycle, game, following, PLAYER, (4, 4))
    rows = svc.list(PLAYER)
    assert len(rows) == 1
    with ledger.engine.connect() as c:
        benefit = svc._benefit(svc._row(c, rows[0]["id"]))
    assert benefit.purchase == receipts[0]["id"] and benefit.period == following
    assert benefit.action == second_action and benefit.action != first_action
    assert len(state(game).requisitions) == 1
    identity = rows[0]["id"]
    record(svc, identity)
    grant(svc, identity)
    call(cycle, game, PLAYER, following, "scene", None, (), "")
    call(cycle, game, PLAYER, following, "recover", RecoveryChoice())
    roll_for(cycle, game, following, OTHER, (2, 2))
    call(cycle, game, OTHER, following, "scene", None, (), "")
    call(cycle, game, OTHER, following, "recover", RecoveryChoice())
    finish_routine(cycle, game, following)
    call(cycle, game, ADMIN, following, "finish", movement(game))
    historical = svc.get(PLAYER, identity)
    assert historical["taken"] and historical["asset_name"] == "PRIVATE_NEW_OUTFIT"
    assert historical["state"] == "resolved" and "source_sha256" not in historical


def test_actual_observation_replacement_preserves_paid_comforts_for_a_future_ordinary_roll(ledger):
    from test_observation_service import roll_for as observation_roll
    from test_observation_service import setup as observation_setup

    observation, cycle, game, period = observation_setup(ledger, faces=(4, 4), hiding=False)
    approval = ledger.policy.m3_approval
    ledger.policy = ledger.policy.model_copy(
        update={
            "m3_approval": approval.model_copy(
                update={"subsystems": approval.subsystems | {"economy"}}
            )
        }
    )
    with ledger.transaction() as c:
        canon = state(game)
        canon.sheets["2"].permissions = 1
        game.event(c, 1, "synthetic-observation-funds", "synthetic.permissions", canon)
    svc = ComfortService(game)
    paid = pay(svc)
    action = observation_roll(observation, game, period)
    assert game.inspect(PLAYER, action)["result"]["total"] == 8
    assert not svc.list(PLAYER) and svc.receipts(PLAYER)[0]["id"] == paid["id"]
    assert svc.receipts(PLAYER)[0]["state"] == "waiting_for_roll"
    assert state(game).sheets["2"].permissions == 0 and game.dice.calls == 1


def test_economy_policy_revocation_blocks_even_an_owned_qualified_gift_without_erasing_it(ledger):
    svc, cycle, game, period, receipts, action = offered(ledger)
    identity = svc.list(PLAYER)[0]["id"]
    record(svc, identity)
    data, before = svc.get(PLAYER, identity), state(game)
    policy = ledger.policy
    approval = policy.m3_approval
    ledger.policy = policy.model_copy(
        update={
            "m3_approval": approval.model_copy(
                update={"subsystems": approval.subsystems - {"economy"}}
            )
        }
    )
    with pytest.raises(WorkflowError, match="M3_REVIEW_PENDING"):
        grant(svc, identity, data=data)
    assert state(game) == before and svc.get(PLAYER, identity)["ready"]
    ledger.policy = policy
    assert grant(svc, identity, data=data)["taken"]
