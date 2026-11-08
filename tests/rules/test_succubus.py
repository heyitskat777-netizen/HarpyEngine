"""Actual scoped Pilot Orders and NPC-owned normal refusal results/consequences."""

import asyncio
from uuid import uuid4

import pytest
import sqlalchemy as sa
from test_cast_service import change as cast_change
from test_enforcer_requisitions import approved
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Gateway, answer, pass_tags, state, tick
from test_mission_service import service
from test_mission_ui import current
from test_world import initial

from girlframe.database import tables as t
from girlframe.delivery.m2_worker import GameWorker
from girlframe.discord_adapter.inbox import InboxView
from girlframe.discord_adapter.m3_succubus import open_npc_order, open_succubus
from girlframe.engine import m3_privileges as privileges
from girlframe.engine import m3_succubus as rules
from girlframe.engine.m2 import PlayInput, higher
from girlframe.engine.m3_actor_bonds import current_ref, depth, set_depth
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_punishments import Details
from girlframe.engine.m3_role_punishment_state import Instruction
from girlframe.engine.m3_world_state import Npc
from girlframe.services.inbox import InboxService
from girlframe.services.m3_access import Access
from girlframe.services.m3_actors import ActorService
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_role_punishments import RolePunishmentService
from girlframe.services.m3_succubus import SuccubusService
from girlframe.services.onboarding import WorkflowError

NPC = ActorRef(kind="npc", entity="actual-guard")


def ready(store, tmp_path, monkeypatch, frame="THE ENFORCER"):
    missions, game = service(store, frame=frame)
    approved(store, game, tmp_path, monkeypatch, extra=(rules.RULE,))
    approval = store.policy.m3_approval
    store.policy = store.policy.model_copy(
        update={
            "m3_approval": approval.model_copy(
                update={"subsystems": approval.subsystems | {"world"}}
            )
        }
    )
    missions.access = Access(store)
    with store.transaction() as c:
        original = state(game)
        original.sheets["2"].permissions = 6
        original.order = (3, 2)
        original = set_depth(
            original, current_ref(original, 2), current_ref(original, 3), 2, str(uuid4())
        )
        game.event(c, 1, str(uuid4()), "synthetic.actual_existing_succubus_resources", original)
    return game, SuccubusService(game), missions


def buy(source, donor=None):
    data = source.menu(PLAYER)
    args = (
        PLAYER,
        str(uuid4()),
        data["revision"],
        ActorRef.model_validate(data["actor"]),
        data["frame"],
        "Actual owned paid Class source",
        donor,
    )
    paid = source.buy(*args)
    assert source.buy(*args) == paid
    return paid


def suspend(game, paid):
    actual = state(game)
    changed = privileges.revoke(
        actual,
        2,
        1,
        paid,
        "Actual restoration condition",
        str(uuid4()),
        str(uuid4()),
        {int(uid): x.character_id for uid, x in actual.sheets.items()},
    )
    with game.store.transaction() as c:
        game.event(c, 1, str(uuid4()), "synthetic.actual_supported_suspension", changed)
    return changed.obligations[-1].id


def restore(game, identity):
    actual = state(game)
    next(x for x in actual.obligations if x.id == identity).details["restoration_allowed"] = "true"
    changed = privileges.restore(actual, identity, actual.sheets["2"].character_id, None)
    with game.store.transaction() as c:
        game.event(c, 1, str(uuid4()), "synthetic.actual_supported_restoration", changed)


def choose(source, viewer, identity, option, account="Actual owned NPC response", **kwargs):
    data = source.inspect(viewer, identity)
    return source.choose(
        viewer, str(uuid4()), identity, data["revision"], option, account, **kwargs
    )


def test_native_scoped_pilot_order_actual_refusal_and_source_restore(ledger, tmp_path, monkeypatch):
    game, source, _ = ready(ledger, tmp_path, monkeypatch)
    before = state(game)

    async def acquire():
        own = current(2, 996001)
        await own.response.defer(ephemeral=True)
        await open_succubus(own, source)
        form = own.edit_original_response.call_args.kwargs["view"]
        assert "2 Permissions" in form.text()
        form.values.update(account="Actual native Succubus acquisition")
        await form.confirm.callback(current(2, 996002))
        assert form.completed

    asyncio.run(acquire())
    actual = state(game)
    actor = current_ref(actual, 2)
    paid = rules.held(actual, actor)
    assert paid.kind == "ability_unlock" and paid.price == 2
    assert actual.sheets["2"].permissions == before.sheets["2"].permissions - 2
    assert not higher(actual, 2, 3) and actual.order == before.order
    gate = suspend(game, paid.id)
    with pytest.raises(WorkflowError, match="active Succubus"):
        game.issue_order(PLAYER, str(uuid4()), 900, 3, "Actual source suspended")
    assert game.dice.calls == 0
    restore(game, gate)
    assert rules.held(state(game), actor) == paid
    with ledger.transaction() as c:
        canon = state(game)
        canon = set_depth(canon, actor, current_ref(canon, 3), 1, str(uuid4()))
        game.event(c, 1, str(uuid4()), "synthetic.actual_weakened_bond", canon)
    with pytest.raises(WorkflowError, match="Intense Bond"):
        game.issue_order(PLAYER, str(uuid4()), 900, 3, "Personal is insufficient")
    with ledger.transaction() as c:
        canon = state(game)
        canon = set_depth(canon, actor, current_ref(canon, 3), 2, str(uuid4()))
        game.event(c, 1, str(uuid4()), "synthetic.actual_intense_bond", canon)
    issued = game.issue_order(PLAYER, "actual-scoped-pilot-order", 900, 3, "Stand with me")
    assert game.issue_order(PLAYER, "actual-scoped-pilot-order", 900, 3, "Stand with me") == issued
    worker, gateway = GameWorker(game), Gateway()
    tick(worker, gateway, 3)
    answer(game, OTHER, "order_response", options=("disobey",))
    game.dice.faces = (6, 6)
    child = game.begin(
        OTHER,
        str(uuid4()),
        900,
        state(game).sheets["3"].revision,
        PlayInput(
            play="disobey_orders",
            order_id=issued["order_id"],
            parent=issued["action_id"],
            context="Actual refusal of the exact source Order",
            trigger_confirmed=True,
            heat=0,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    answer(game, OTHER, "actor_disobey", flag=True, text="Actually act now without thinking")
    answer(game, ADMIN, "handler_disobey", flag=False)
    assert game.inspect(OTHER, child)["state"] == "complete"
    assert game.inspect(OTHER, issued["action_id"])["state"] == "complete"
    assert game.dice.calls == 1 and state(game).order == before.order


def npc_world(game, missions):
    with game.store.transaction() as c:
        actual = state(game)
        actual.world = initial().model_copy(
            update={
                "npcs": (
                    Npc(
                        id=NPC.entity,
                        name="Actual guard",
                        jobs=("guard",),
                        detail="Actual ordinary Foundation guard",
                        controller=3,
                        cell=(0, 0),
                        revealed=True,
                        employment="foundation",
                    ),
                )
            }
        )
        actual = set_depth(actual, current_ref(actual, 2), NPC, 1, str(uuid4()))
        game.event(c, 1, str(uuid4()), "synthetic.actual_existing_npc_and_bond", actual)
    cast = CastService(ActorService(missions))
    cast_change(cast, OTHER, "join", NPC)


def issue(source, worker, gateway, *, native=False):
    if native:

        async def create():
            own = current(2, 996101)
            own.channel_id = 900
            await own.response.defer(ephemeral=True)
            await open_npc_order(own, source)
            form = own.edit_original_response.call_args.kwargs["view"]
            form.values.update(target=(NPC.token,), instruction="Actual direct Order to the guard")
            await form.confirm.callback(current(2, 996102))
            assert form.completed

        asyncio.run(create())
        with source.store.engine.connect() as c:
            identity = source._tasks(c, OTHER)[-1]["id"]
    else:
        data = source.targets(PLAYER, 900)
        result = source.issue_npc(
            PLAYER,
            str(uuid4()),
            900,
            data["revision"],
            NPC,
            data["cast"],
            "Actual direct Order to the guard",
        )
        identity = result["action_id"]
    job = worker.claim("m2_locks", ("acquiring",))
    asyncio.run(worker.acquire(job, gateway))
    return identity


def reviewed(source, identity, *, noticed=None, knows=False, punish=False):
    return choose(source, ADMIN, identity, "review", selected=noticed, knows=knows, punish=punish)


def release(worker, gateway):
    tick(worker, gateway, 5)


def refusal(source, game, worker, gateway, faces):
    identity = issue(source, worker, gateway)
    choose(source, OTHER, identity, "disobey")
    game.dice.faces = faces
    choose(source, OTHER, identity, "roll")
    return identity


def test_graft_real_npc_follow_all_refusal_branches_rank_punishment_and_once_roll(
    ledger, tmp_path, monkeypatch
):
    game, source, missions = ready(ledger, tmp_path, monkeypatch, frame="JANUS-B")
    paid = buy(source, "THE ENFORCER")
    actor = current_ref(state(game), 2)
    receipt = rules.held(state(game), actor)
    assert paid["cost"] == 3 and receipt.kind == "frame_grafting"
    npc_world(game, missions)
    before = state(game)
    worker, gateway = GameWorker(game), Gateway()
    identity = issue(source, worker, gateway, native=True)
    with pytest.raises(WorkflowError, match="owns this choice"):
        source.inspect(PLAYER, identity)

    async def real_response():
        own = current(3, 996103)
        await own.response.defer(ephemeral=True)
        inbox = InboxService(ledger)
        item = next(
            x for x in inbox.items(OTHER) if x.task == "m3_succubus" and x.identity == identity
        )
        await InboxView(inbox, 3).route(own, item)
        form = own.edit_original_response.call_args.kwargs["view"]
        form.values.update(option=("obedient",), account="The actual guard obeys")
        await form.confirm.callback(current(3, 996104))
        assert form.completed

    asyncio.run(real_response())
    assert source.inspect(OTHER, identity)["phase"] == "complete"
    assert state(game).sheets == before.sheets and game.dice.calls == 0
    release(worker, gateway)

    identity = issue(source, worker, gateway)
    choose(source, OTHER, identity, "disobey")
    gate = suspend(game, paid["id"])
    original = state(game)
    with pytest.raises(ValueError, match="active Succubus"):
        choose(source, OTHER, identity, "roll")
    assert state(game) == original and game.dice.calls == 0
    restore(game, gate)
    assert rules.held(state(game), actor) == receipt
    game.dice.faces = (4, 4)
    data = source.inspect(OTHER, identity)
    args = (OTHER, "actual-npc-roll-once", identity, data["revision"], "roll", "Actual NPC refusal")
    raw = source.choose(*args)
    assert source.choose(*args) == raw and game.dice.calls == 1
    assert SuccubusService(game).inspect(OTHER, identity)["receipt"] == raw["receipt"]
    assert raw["receipt"]["heat"] is None and raw["receipt"]["actor"] == NPC.model_dump(mode="json")
    choose(source, OTHER, identity, "tag_heat", "Actually defiant", heat_gain=2)
    assert source.inspect(ADMIN, identity)["result"]["heat_gain_applied"] == 0
    known = state(game)
    tag = rules.npc(known, NPC).tags[-1]
    # Source is suspended AFTER the real receipt; saved consequences remain real and recoverable.
    gate = suspend(game, paid["id"])
    result = reviewed(
        source, identity, noticed=current_ref(state(game), 3), knows=True, punish=True
    )
    assert rules.expanded_status(state(game), NPC) == 6
    assert rules.ordinary_higher(state(game), actor, NPC)
    discipline = RolePunishmentService(game)
    case = result["punishment"]

    def change_role(viewer, **kwargs):
        data = discipline.get(viewer, case)
        return discipline.change(viewer, str(uuid4()), case, data["revision"], **kwargs)

    change_role(
        ADMIN,
        instruction=Instruction(
            kind="quality_time",
            details_json=Details(
                kind="quality_time", tag="Actual Handler consequence"
            ).model_dump_json(),
        ),
    )
    change_role(ADMIN, scene="Actual Handler performs Quality Time with this original NPC")
    change_role(OTHER, attest=True)
    change_role(ADMIN, execute=True, account="Actual instructed NPC effect performed")
    assert state(game).role_punishments[-1].completion_event
    assert source.inspect(ADMIN, identity)["phase"] == "complete"
    assert depth(state(game), NPC, current_ref(state(game), 1)) == 1
    assert state(game).sheets == before.sheets
    restore(game, gate)
    release(worker, gateway)

    # The real rank loss is consumed: same Girl may now issue an ordinary Order without a Bond.
    with ledger.transaction() as c:
        actual = state(game)
        actual = set_depth(actual, actor, NPC, 0, str(uuid4()))
        game.event(c, 1, str(uuid4()), "synthetic.actual_bond_ended", actual)
    low = refusal(source, game, worker, gateway, (1, 1))
    with ledger.engine.connect() as c:
        assert game.action(c, low)["data"]["succubus_npc_order"]["authority"] is None
    choose(source, OTHER, low, "hesitant", "Actual guard cannot disobey and obeys hesitantly")
    reviewed(source, low, knows=True, punish=False)
    assert source.inspect(ADMIN, low)["result"]["can_disobey"] is False
    release(worker, gateway)

    high = refusal(source, game, worker, gateway, (6, 6))
    with pytest.raises(WorkflowError, match="immediate"):
        choose(source, OTHER, high, "act_now", flag=False)
    choose(source, OTHER, high, "act_now", "The actual guard acts now without thinking", flag=True)
    reviewed(source, high)
    assert source.inspect(ADMIN, high)["result"]["acted_now"] is True
    release(worker, gateway)

    rejection = refusal(source, game, worker, gateway, (4, 4))
    choose(source, OTHER, rejection, "reject_tag", tag=tag.id)
    reviewed(source, rejection)
    assert all(x.id != tag.id for x in rules.npc(state(game), NPC).tags)
    release(worker, gateway)

    follower = refusal(source, game, worker, gateway, (4, 5))
    choose(source, OTHER, follower, "follow", selected=actor)
    with pytest.raises(WorkflowError, match="owns this choice"):
        source.inspect(OTHER, follower)
    choose(
        source, PLAYER, follower, "follow", "Actual original Girl follows immediately", flag=True
    )
    reviewed(source, follower)
    final = state(game)
    assert source.inspect(ADMIN, follower)["result"]["followed"] is True
    assert game.dice.calls == 5 and final.sheets == before.sheets
    assert rules.held(final, actor) == receipt
    with ledger.engine.connect() as c:
        assert c.scalar(sa.select(sa.func.count()).select_from(t.m2["m2_receipts"])) == 5
    release(worker, gateway)
