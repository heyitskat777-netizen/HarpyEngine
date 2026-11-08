"""An actual political NPC Bond becomes a real NPC Conversation, never a proxy Girl roll."""

import asyncio
from uuid import uuid4

import pytest
import sqlalchemy as sa
from handler_award_scenario import ordinary_pr_award
from test_cast_service import change as cast_change
from test_enforcer_requisitions import approved
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state
from test_mission_ui import current

from girlframe.database import tables as t
from girlframe.discord_adapter.inbox import InboxView
from girlframe.engine import m3_handler_advancements as awards
from girlframe.engine import m3_handler_ordinary as ordinary
from girlframe.engine import m3_npc_bond_play as rules
from girlframe.engine import m3_politician_bribery as politics
from girlframe.engine.m3_actor_bonds import current_ref, depth
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_world_state import Location, Npc
from girlframe.services.inbox import InboxService
from girlframe.services.m3_actors import ActorService
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_npc_bond_play import NpcBondPlayService, prove_performance, prove_request
from girlframe.services.m3_politician_bribery import BriberyService
from girlframe.services.onboarding import WorkflowError

JOB = "public_relations"
MOVE = "Smooth things over"
NPC_RULE = "npc.npc.public-relations"


def interaction(uid, channel=900):
    actual = current(uid, int(uuid4().int % 1000000000))
    actual.channel_id = channel
    return actual


def test_real_girl_bond_cost_other_npc_human_performance_addressed_receipt_and_history(
    ledger, tmp_path, monkeypatch
):
    game, _, _ = ordinary_pr_award(ledger, tmp_path, monkeypatch)
    approved(
        ledger,
        game,
        tmp_path,
        monkeypatch,
        extra=(ordinary.RULE, politics.RULE, rules.RULE, NPC_RULE),
    )
    with ledger.transaction() as c:
        canon = state(game)
        canon.world = canon.world.model_copy(
            update={
                "locations": (
                    *canon.world.locations,
                    Location(id="real-city-a", name="Capital", kind="city", cell=(0, 1)),
                    Location(id="real-city-b", name="Port", kind="city", cell=(1, 1)),
                )
            }
        )
        game.event(c, 1, "actual-initial-political-geography", "synthetic.initial_geography", canon)
    fund = BriberyService(ledger)
    award = next(x for x in awards.awards(state(game)) if x.phase == "held")
    fund_id = fund.buy(
        ADMIN,
        str(uuid4()),
        award.id,
        state(game).revision,
        tuple(
            politics.Politician(
                city="real-city-a" if i < 3 else "real-city-b",
                npc=Npc(
                    id="real-politician-" + str(i),
                    name="Minister " + str(i),
                    jobs=(JOB,),
                    detail="Actual political officeholder",
                    controller=1,
                    cell=(0, 0),
                    revealed=True,
                ),
            )
            for i in range(6)
        ),
        "Actual political fund acquisition",
    )["id"]
    fund.assign(
        PLAYER,
        str(uuid4()),
        fund_id,
        state(game).revision,
        "real-politician-0",
        "healthcare",
        "PRIVATE_POLITICAL_FEELINGS",
    )
    holder = current_ref(state(game), 2)
    npc = ActorRef(kind="npc", entity="real-politician-0")
    recipient = current_ref(state(game), 3)
    assert depth(state(game), holder, npc) == 1
    assert not politics.complete_assignments(state(game), politics.acquisitions(state(game))[0])
    # Once genuine, the relationship is a core Bond, not a continuing Bribery permission.
    approved(ledger, game, tmp_path, monkeypatch, extra=(rules.RULE, NPC_RULE))
    service = NpcBondPlayService(ledger)
    casts = CastService(ActorService(MissionService(ledger)))
    cast_change(casts, PLAYER, "withdraw", holder)
    cast_change(casts, ADMIN, "join", npc)
    before = state(game)
    with ledger.engine.connect() as c:
        action_count = c.scalar(sa.select(sa.func.count()).select_from(t.m2["m2_actions"]))
        receipt_count = c.scalar(sa.select(sa.func.count()).select_from(t.m2["m2_receipts"]))
    for ref, move in ((npc, "Place an expectation on them"), (recipient, MOVE)):
        with pytest.raises(WorkflowError):
            service.request(
                PLAYER,
                str(uuid4()),
                before.revision,
                ref,
                JOB,
                move,
                "Unsupported before Bond cost",
            )
        assert state(game) == before and depth(state(game), holder, npc) == 1
    context = "Please smooth over the committee's actual misunderstanding of the hospital findings."

    async def request_native():
        inbox = InboxService(ledger)
        task = next(
            x
            for x in inbox.items(PLAYER)
            if x.task == "m3_npc_bond_play" and x.identity.startswith("npc-bond-control:")
        )
        own = interaction(2, 902)
        await own.response.defer(ephemeral=True)
        await InboxView(inbox, 2).route(own, task)
        form = own.edit_original_response.call_args.kwargs["view"]
        form.values.update(move=(npc.token + ":" + JOB,), context=context)
        confirmed = interaction(2, 902)
        await form.confirm.callback(confirmed)
        assert form.completed, confirmed.edit_original_response.call_args
        return confirmed

    requested = asyncio.run(request_native())
    request = rules.requests(state(game))[0]
    assert request.holder == holder and request.npc == npc and request.controller == 1
    assert (
        request.before_depth == 1
        and request.after_depth == 0
        and depth(state(game), holder, npc) == 0
    )
    inbox = InboxService(ledger)
    holder_item = next(
        x for x in inbox.items(PLAYER) if x.task == "m3_npc_bond_play" and x.identity == request.id
    )
    npc_item = next(
        x for x in inbox.items(ADMIN) if x.task == "m3_npc_bond_play" and x.identity == request.id
    )
    assert (holder_item.state, holder_item.incoming) == ("pending", False) and inbox.page(
        PLAYER, "waiting", selected_key=holder_item.key
    ).item == holder_item
    assert (npc_item.state, npc_item.incoming) == ("pending", True) and inbox.page(
        ADMIN, "you", selected_key=npc_item.key
    ).item == npc_item
    after_cost = state(game)
    expected = service.request(PLAYER, str(requested.id), before.revision, npc, JOB, MOVE, context)
    assert expected["id"] == request.id and state(game) == after_cost
    with pytest.raises(WorkflowError):
        service.request(PLAYER, str(uuid4()), after_cost.revision, npc, JOB, MOVE, context)
    assert service.menu(PLAYER, request.id)["can_perform"] is False
    with pytest.raises(WorkflowError):
        service.menu(OTHER, request.id)
    with ledger.engine.connect() as c:
        prove_request(game, c, state(game), request.id)
        work = (
            c.execute(
                sa.select(t.m3["m3_required_work"]).where(
                    t.m3["m3_required_work"].c.id == request.id
                )
            )
            .mappings()
            .one()
        )
        assert work["state"] == "pending" and work["owner_id"] == "1" and work["subject_id"] == "2"
    rendition = (
        "PRIVATE_RENDITION: Minister 0 turns to the committee contact: "
        '"The evidence is sound; I will explain the corrected hospital figures myself."'
    )
    with pytest.raises(WorkflowError):
        service.perform(
            PLAYER, str(uuid4()), request.id, state(game).revision, 900, (recipient,), rendition
        )
    ledger.safety(OTHER, "actual-pause-for-npc-scene", ledger.status(OTHER)["revision"], pause=True)
    with pytest.raises(WorkflowError, match="SAFETY_PAUSED"):
        service.perform(
            ADMIN, str(uuid4()), request.id, state(game).revision, 900, (recipient,), rendition
        )
    ledger.safety(
        OTHER, "actual-resume-for-npc-scene", ledger.status(OTHER)["revision"], pause=False
    )
    real_event = service.game.event

    def interrupted(*args, **kwargs):
        real_event(*args, **kwargs)
        raise WorkflowError("INTERRUPTED_ACTUAL_NPC_PERFORMANCE")

    with monkeypatch.context() as patch:
        patch.setattr(service.game, "event", interrupted)
        with pytest.raises(WorkflowError, match="INTERRUPTED_ACTUAL_NPC_PERFORMANCE"):
            service.perform(
                ADMIN, str(uuid4()), request.id, state(game).revision, 900, (recipient,), rendition
            )
    assert state(game) == after_cost and not rules.performances(state(game))

    async def perform_native():
        inbox = InboxService(ledger)
        task = next(
            x
            for x in inbox.items(ADMIN)
            if x.task == "m3_npc_bond_play" and x.identity == request.id
        )
        own = interaction(1, 902)
        await own.response.defer(ephemeral=True)
        await InboxView(inbox, 1).route(own, task)
        picker = own.edit_original_response.call_args.kwargs["view"]
        chosen = interaction(1)
        await chosen.response.defer(ephemeral=True)
        await picker.open_item(chosen, "900")
        form = chosen.edit_original_response.call_args.kwargs["view"]
        form.values.update(recipients=(recipient.token,), rendition=rendition)
        confirmed = interaction(1)
        await form.confirm.callback(confirmed)
        assert form.completed, confirmed.edit_original_response.call_args
        return confirmed

    performed = asyncio.run(perform_native())
    final = state(game)
    assert len(rules.performances(final)) == 1 and final.sheets == before.sheets
    assert depth(final, holder, npc) == 0
    service.perform(
        ADMIN, str(performed.id), request.id, after_cost.revision, 900, (recipient,), rendition
    )
    assert state(game) == final
    assert service.menu(PLAYER, request.id)["rendition"] is None
    assert service.menu(OTHER, request.id)["rendition"] == rendition
    assert service.menu(OTHER, request.id)["cost"] is None
    assert service.menu(OTHER, request.id)["holder"] is None
    cast_change(casts, PLAYER, "join", holder)
    assert service.menu(PLAYER, request.id)["rendition"] is None

    async def reopen():
        inbox = InboxService(ledger)
        task = next(
            x
            for x in inbox.items(OTHER)
            if x.task == "m3_npc_bond_play" and x.identity == request.id
        )
        actual = interaction(3, 903)
        await actual.response.defer(ephemeral=True)
        await InboxView(inbox, 3).route(actual, task)
        content = actual.edit_original_response.call_args.kwargs["content"]
        assert (
            "The evidence is sound" in content and "actual performance complete" in content.lower()
        )
        assert "Bond cost" not in content
        assert not actual.edit_original_response.call_args.kwargs["allowed_mentions"].everyone

    asyncio.run(reopen())
    with ledger.engine.connect() as c:
        prove_performance(game, c, state(game), request.id)
        rows = list(
            c.execute(
                sa.select(t.m3["m3_required_work"])
                .where(t.m3["m3_required_work"].c.id == request.id)
                .order_by(t.m3["m3_required_work"].c.revision)
            ).mappings()
        )
        assert len(rows) == 2 and rows[-1]["state"] == "resolved"
        assert c.scalar(sa.select(sa.func.count()).select_from(t.m2["m2_actions"])) == action_count
        assert (
            c.scalar(sa.select(sa.func.count()).select_from(t.m2["m2_receipts"])) == receipt_count
        )
        payloads = " ".join(c.scalars(sa.select(t.events.c.payload_json)))
        assert rendition not in payloads and context not in payloads
    saved = state(game)
    with ledger.transaction() as c:
        c.execute(t.m2["m2_state"].delete())
    game.rebuild()
    assert state(game) == saved
    assert service.menu(OTHER, request.id)["rendition"] == rendition
