"""Actual reviewed acquisition → loss → real roll → owned pistol return."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
import sqlalchemy as sa
from test_comfort_service import ready as scene_ready
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger_fixture
from test_m2_game import state
from test_mission_ui import current
from test_off_duty_cycle import activate, roll_for
from test_personal_firearm import reviewed_registry
from test_requisition_service import ready

from girlframe.database import tables as t
from girlframe.discord_adapter.m3_personal_firearm import open_acquisition, open_return
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.services.m3_access import digest
from girlframe.services.m3_personal_firearm import PersonalFirearmService, synchronize
from girlframe.services.onboarding import WorkflowError

ledger = ledger_fixture


def setup(store, tmp_path, monkeypatch, *, frame="JANUS-B", period=False, reviewed=True):
    if period:
        _, cycle, game, identity = scene_ready(store)
    else:
        _, game = ready(store, frame=frame)
        cycle, identity = None, None
    registry = reviewed_registry(approved=reviewed)
    path = tmp_path / "synthetic-reviewed-registry.json"
    path.write_text(registry.model_dump_json())
    monkeypatch.setenv("GIRLFRAME_RULES_REGISTRY", str(path))
    policy = store.policy
    store.policy = policy.model_copy(
        update={
            "m3_approval": policy.m3_approval.model_copy(
                update={
                    "registry_sha256": digest(registry),
                }
            )
        }
    )
    if cycle is not None:
        cycle.missions.access.registry = registry
    with store.transaction() as c:
        canon = state(game)
        canon.sheets["2"].permissions = 5
        game.event(c, 1, "synthetic-firearm-funds", "synthetic.state", canon)
    return PersonalFirearmService(game, registry), cycle, game, identity


def purchase(service, kind="frame_grafting", *, key="actual-ability-purchase"):
    data = service.acquisition_view(PLAYER, kind)
    return service.buy_firearm(
        PLAYER,
        key,
        ActorRef.model_validate(data["actor"]),
        data["source_sha256"],
        kind,
        "PRIVATE_ACTUAL_FIREARM_ACQUISITION",
    )


def lose(service, *, damage_only=False):
    with service.store.transaction() as c:
        canon = state(service.game)
        asset = canon.personal_firearms[0].issues[-1].asset
        if damage_only:
            next(x for x in canon.sheets["2"].assets if x.id == asset).damaged = True
        else:
            canon.sheets["2"].assets = [x for x in canon.sheets["2"].assets if x.id != asset]
        service.game.event(c, 1, "actual-issued-item-loss", "synthetic.state", canon)


def sync(service, period):
    with service.store.transaction() as c:
        actual = service.periods._get(c, period)
        history = t.m3["m3_off_duty_history"]
        event = c.scalar(
            sa.select(history.c.event_id)
            .where(history.c.campaign_id == service.store.campaign_id, history.c.id == period)
            .order_by(history.c.revision.desc())
            .limit(1)
        )
        synchronize(c, service.store, actual, event)


@pytest.mark.parametrize(
    "kind,frame,price", [("ability_unlock", "THE ENFORCER", 2), ("frame_grafting", "JANUS-B", 3)]
)
def test_actual_source_eligible_acquisition_charges_once_and_installs_one_pistol(
    ledger, tmp_path, monkeypatch, kind, frame, price
):
    service, _, game, _ = setup(ledger, tmp_path, monkeypatch, frame=frame)
    result = purchase(service, kind)
    assert result["cost"] == price and state(game).sheets["2"].permissions == 5 - price
    assert len(state(game).personal_firearms) == 1
    assert sum(x.name == "Personal Firearm" for x in state(game).sheets["2"].assets) == 1


def test_real_unreviewed_registry_gate_rejects_without_payment_or_item(
    ledger, tmp_path, monkeypatch
):
    service, _, game, _ = setup(ledger, tmp_path, monkeypatch, reviewed=False)
    before = state(game).model_dump_json()
    with pytest.raises(WorkflowError, match="implementation and review"):
        purchase(service)
    assert state(game).model_dump_json() == before


def test_actual_lost_pistol_eight_roll_then_owned_return_preserves_currency_and_known_receipt(
    ledger, tmp_path, monkeypatch
):
    service, cycle, game, period = setup(ledger, tmp_path, monkeypatch, period=True)
    purchase(service)
    lose(service)
    activate(cycle, game, period)
    action = roll_for(cycle, game, period, PLAYER, (2, 2))
    sync(service, period)
    identity = service.return_tasks(PLAYER)[0]["id"]
    data = service.return_get(PLAYER, identity)
    assert data["total"] == 8
    with pytest.raises(WorkflowError):
        service.return_get(OTHER, identity)
    result = service.claim(
        PLAYER,
        "actual-pistol-return",
        identity,
        data["revision"],
        take=True,
        account="PRIVATE_ACTUAL_REISSUE",
        expected=data["expected"],
    )
    assert (
        service.claim(
            PLAYER,
            "actual-pistol-return",
            identity,
            data["revision"],
            take=True,
            account="PRIVATE_ACTUAL_REISSUE",
            expected=data["expected"],
        )
        == result
    )
    assert len(state(game).personal_firearms[0].issues) == 2
    assert state(game).sheets["2"].permissions == 2
    assert game.inspect(PLAYER, action)["receipt"]["faces"] == [2, 2]
    with ledger.engine.connect() as c:
        assert "PRIVATE_ACTUAL" not in str(list(c.scalars(sa.select(t.events.c.payload_json))))


@pytest.mark.parametrize("damage_only,late", [(True, False), (False, True)])
def test_damage_alone_and_post_roll_loss_cannot_claim_a_known_roll(
    ledger, tmp_path, monkeypatch, damage_only, late
):
    service, cycle, game, period = setup(ledger, tmp_path, monkeypatch, period=True)
    purchase(service)
    if not late:
        lose(service, damage_only=damage_only)
    activate(cycle, game, period)
    roll_for(cycle, game, period, PLAYER, (2, 2))
    if late:
        lose(service)
    sync(service, period)
    assert not service.return_tasks(PLAYER)


def test_native_acquisition_and_return_require_owned_explicit_confirmation(
    ledger, tmp_path, monkeypatch
):
    service, cycle, game, period = setup(ledger, tmp_path, monkeypatch, period=True)

    async def acquire():
        caller = current(2, 21301)
        await caller.response.defer(ephemeral=True)
        await open_acquisition(caller, service, "frame_grafting")
        form = caller.edit_original_response.call_args.kwargs["view"]
        assert not await form.interaction_check(current(3))
        form.values.update(
            replace=("none",), account="PRIVATE_ACTUAL_FIREARM_ACQUISITION", payment=("yes",)
        )
        await form.confirm.callback(current(2, 21302))
        assert form.completed

    asyncio.run(acquire())
    lose(service)
    activate(cycle, game, period)
    roll_for(cycle, game, period, PLAYER, (2, 2))
    sync(service, period)
    identity = service.return_tasks(PLAYER)[0]["id"]

    async def retrieve():
        caller = current(2, 21303)
        await caller.response.defer(ephemeral=True)
        await open_return(caller, service, identity)
        form = caller.edit_original_response.call_args.kwargs["view"]
        form.values.update(take=("yes",), replace=("none",), account="Actual owned pickup")
        await form.confirm.callback(current(2, 21304))
        assert form.completed

    asyncio.run(retrieve())
    assert len(state(game).personal_firearms[0].issues) == 2


@pytest.mark.parametrize("observation", [False, True])
def test_actual_low_ordinary_and_eight_plus_observation_never_issue_a_replacement(
    ledger,
    tmp_path,
    monkeypatch,
    observation,
):
    service, cycle, game, period = setup(ledger, tmp_path, monkeypatch, period=True)
    purchase(service)
    lose(service)
    activate(cycle, game, period)
    if observation:
        from test_m2_game import Dice
        from test_observation_service import roll_for as observe

        from girlframe.services.m3_observation import ObservationService

        source = ObservationService(cycle.periods)
        current_period = cycle.review(ADMIN, period)
        source.order(
            ADMIN,
            str(uuid4()),
            period,
            current_period["revision"],
            state(game).revision,
            2,
            True,
            "Actual source Observation order",
        )
        game.dice = Dice((6, 6))
        observe(source, game, period)
    else:
        roll_for(cycle, game, period, PLAYER, (1, 1))
    sync(service, period)
    assert not service.return_tasks(PLAYER)
    assert len(state(game).personal_firearms[0].issues) == 1
    assert game.dice.calls == 1


def test_actual_return_pause_post_history_failure_and_concurrent_confirmation_are_atomic(
    ledger,
    tmp_path,
    monkeypatch,
):
    service, cycle, game, period = setup(ledger, tmp_path, monkeypatch, period=True)
    purchase(service)
    lose(service)
    activate(cycle, game, period)
    roll_for(cycle, game, period, PLAYER, (2, 2))
    identity = service.return_tasks(PLAYER)[0]["id"]
    data = service.return_get(PLAYER, identity)

    def claim(key):
        return service.claim(
            PLAYER,
            key,
            identity,
            data["revision"],
            take=True,
            account="Actual owned retrieval",
            expected=data["expected"],
        )

    ledger.safety(OTHER, "pause-pistol-return", ledger.status(OTHER)["revision"], pause=True)
    with pytest.raises(WorkflowError, match="SAFETY_PAUSED"):
        claim("paused-pistol-return")
    ledger.safety(OTHER, "resume-pistol-return", ledger.status(OTHER)["revision"], pause=False)
    before = state(game).model_dump_json()
    event = service.game.event

    def fail_after_history(*args, **kwargs):
        event(*args, **kwargs)
        raise RuntimeError("Synthetic failed actual return history")

    monkeypatch.setattr(service.game, "event", fail_after_history)
    with pytest.raises(RuntimeError, match="failed actual return"):
        claim("retry-actual-pistol-return")
    assert state(game).model_dump_json() == before
    monkeypatch.setattr(service.game, "event", event)

    def competing(key):
        try:
            return claim(key)
        except WorkflowError:
            return None

    with ThreadPoolExecutor(max_workers=2) as workers:
        results = list(workers.map(competing, ("actual-first-return", "actual-second-return")))
    assert sum(x is not None for x in results) == 1
    assert len(state(game).personal_firearms[0].issues) == 2
    assert state(game).sheets["2"].permissions == 2


def test_real_replacement_issue_preserves_stolen_object_custody_and_later_retrieval_is_separate(
    ledger, tmp_path, monkeypatch
):
    from girlframe.engine.m3_actor_bonds import current_ref
    from girlframe.engine.m3_world_state import Board, Npc, World
    from girlframe.services.m3_items import prove_item, take_in_transaction

    service, cycle, game, period = setup(ledger, tmp_path, monkeypatch, period=True)
    purchase(service)
    actor = current_ref(state(game), 2)
    old = state(game).personal_firearms[0].issues[-1].asset
    npc = ActorRef(kind="npc", entity="actual-pistol-custodian")
    with ledger.transaction() as c:
        canon = state(game)
        canon.world = World(
            board=Board(minimum=(-1, -1), maximum=(1, 1)),
            locations=(),
            npcs=(
                Npc(
                    id=npc.entity,
                    name="Actual pistol custodian",
                    jobs=("guard",),
                    detail="Actual distinct holder",
                    controller=1,
                    cell=(0, 0),
                    revealed=True,
                ),
            ),
        )
        game.event(c, 1, str(uuid4()), "synthetic.actual_pistol_custodian", canon)

    def move(source, target, selection):
        with ledger.transaction() as c:
            event = str(uuid4())
            changed = take_in_transaction(
                c,
                game,
                state(game),
                source=source,
                recipient=target,
                selection=selection,
                action=str(uuid4()),
                event=event,
                account="Actual original physical object transferred",
            )
            game.event(
                c,
                1,
                str(uuid4()),
                "synthetic.actual_stolen_object_transfer",
                changed,
                event_id=event,
            )
            return changed.held_items[-1]

    item = move(actor, npc, "asset:" + old)
    activate(cycle, game, period)
    roll_for(cycle, game, period, PLAYER, (2, 2))
    sync(service, period)
    work = service.return_tasks(PLAYER)[0]["id"]
    data = service.return_get(PLAYER, work)
    assert "replacement pistol" in data["replacement_notice"]
    service.claim(
        PLAYER,
        str(uuid4()),
        work,
        data["revision"],
        take=True,
        account="Actual Foundation replacement issue accepted",
        expected=data["expected"],
    )
    actual = state(game)
    replacement = actual.personal_firearms[0].issues[-1]
    assert replacement.asset != old and replacement.kind == "foundation_replacement"
    assert (
        replacement.recipient == actor
        and replacement.controller == 2
        and replacement.replaces_asset == old
    )
    with ledger.engine.connect() as c:
        assert prove_item(c, game, actual, item.id).holder == npc
    count = len(actual.sheets["2"].assets)
    returned = move(npc, actor, item.id)
    assert returned.id == item.id and returned.asset_id == old
    assert len(state(game).sheets["2"].assets) == count + 1
    assert {old, replacement.asset} <= {x.id for x in state(game).sheets["2"].assets}
    assert len(state(game).personal_firearms[0].issues) == 2
