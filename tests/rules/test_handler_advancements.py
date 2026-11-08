"""Actual distinct Void source awards and one original Handler group spend."""

import asyncio
from uuid import uuid4

import pytest
import sqlalchemy as sa
from test_enforcer_requisitions import approved
from test_handler_creation import agree, complete, save
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state
from test_mission_ui import current
from test_strain_service import prepared, ready

from girlframe.database import tables as t
from girlframe.discord_adapter.inbox import InboxView
from girlframe.discord_adapter.m3_handler_advancements import open_advancement
from girlframe.engine import m3_handler_advancements as rules
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.services.handler_setup import HandlerService
from girlframe.services.inbox import InboxService
from girlframe.services.m3_access import Access
from girlframe.services.m3_handler_advancements import HandlerAdvancementService
from girlframe.services.m3_handler_creation import HandlerCreationService
from girlframe.services.onboarding import WorkflowError


def source(store, tmp_path, monkeypatch, slot):
    strain, game = ready(store, face=6)
    approved(store, game, tmp_path, monkeypatch, extra=rules.RULES)
    strain.missions.access = Access(store)
    store.policy = store.policy.model_copy(
        update={
            "owner_m3_rulings": store.policy.owner_m3_rulings.model_copy(
                update={"handler_creation": "owned_shared_choices_preserve_existing"}
            )
        }
    )
    handler = HandlerCreationService(store)
    save(handler, complete(handler, "Scientist"))
    agree(handler)
    data = handler.view(ADMIN)
    handler.activate(ADMIN, str(uuid4()), data["revision"], data["game_revision"], True)
    with store.transaction() as c:
        initial = state(game)
        initial.sheets["2"].assets[0].void = True
        game.event(c, 1, str(uuid4()), "synthetic.actual_prior_void", initial)
    prepared(strain, game, high=frozenset({"void"}))
    while True:
        request = next(
            x
            for x in state(game).strain.requests
            if x.track == "void" and (x.kind == "endgame" or x.severity == "high")
        )
        if request.kind == "endgame":
            break
        strain.roll(ADMIN, str(uuid4()), request.id, 1, state(game).revision)
        strain.choose(ADMIN, str(uuid4()), request.id, 2, state(game).revision, 2)
    strain.choose(ADMIN, str(uuid4()), request.id, 1, state(game).revision, slot, endgame=True)
    return strain, game, HandlerAdvancementService(store), request.id + ":effect"


def native_claim(service, identity, number=31500):
    async def claim():
        inbox = InboxService(service.store)
        item = next(x for x in inbox.items(ADMIN) if x.identity == identity)
        own = current(1, number)
        own.channel_id = 999
        await own.response.defer(ephemeral=True)
        await InboxView(inbox, 1).route(own, item)
        form = own.edit_original_response.call_args.kwargs["view"]
        form.values.update(claim=("claim",), account="PRIVATE ACTUAL HANDLER AWARD")
        await form.confirm.callback(current(1, number + 1))
        assert form.completed

    asyncio.run(claim())


@pytest.mark.parametrize("slot", [6, 7])
def test_genuine_void_slots_actual_native_award_group_grants_once_and_saved_history(
    ledger, tmp_path, monkeypatch, slot
):
    strain, game, service, identity = source(ledger, tmp_path, monkeypatch, slot)
    before = state(game)
    view = service.view(ADMIN, identity)
    assert view["phase"] == "claim" and view["rule"] == f"strain.void.endgame.{slot}"
    assert ActorRef.model_validate(view["handler"]).incarnation == before.handler_persona.id
    with pytest.raises(WorkflowError, match="original Handler"):
        service.view(PLAYER, identity)
    calls = (strain.dice.calls, game.dice.calls)
    native_claim(service, identity)
    held = state(game)
    value = rules.awards(held)[0]
    assert value.phase == "held" and value.rule == f"strain.void.endgame.{slot}"
    assert held.sheets == before.sheets and value.handler.incarnation == before.handler_persona.id
    args = (
        ADMIN,
        "31501",
        identity,
        view["revision"],
        view["work_revision"],
        "PRIVATE ACTUAL HANDLER AWARD",
    )
    assert service.claim_void(*args) == dict(id=identity, phase="held")
    with pytest.raises(WorkflowError, match="unclaimed"):
        service.claim_void(
            ADMIN,
            str(uuid4()),
            identity,
            held.revision,
            service.view(ADMIN, identity)["work_revision"],
            "Cannot award twice",
        )
    assert state(game) == held
    with ledger.engine.connect() as c:
        source_work = (
            c.execute(
                sa.select(t.m3["m3_required_work"])
                .where(t.m3["m3_required_work"].c.id == identity)
                .order_by(t.m3["m3_required_work"].c.revision.desc())
                .limit(1)
            )
            .mappings()
            .one()
        )
        assert source_work["state"] == "resolved" and source_work["event_id"] == value.award_event
    selected = tuple(service.view(ADMIN, identity)["candidates"])
    expected = (
        {x["actor"]["entity"]: (1 if index == 0 else 2) for index, x in enumerate(selected)}
        if slot == 6
        else {"2": 2}
    )
    selected = tuple(x for x in selected if x["actor"]["entity"] in expected)

    async def native_spend():
        inbox = InboxService(ledger)
        item = next(
            x
            for x in inbox.items(ADMIN)
            if x.task == "m3_handler_advancements" and x.identity == identity
        )
        own = current(1, 31510)
        await own.response.defer(ephemeral=True)
        await InboxView(inbox, 1).route(own, item)
        form = own.edit_original_response.call_args.kwargs["view"]
        form.values.update(girls=tuple(x["token"] for x in selected))
        next_step = current(1, 31511)
        await form.confirm.callback(next_step)
        assert form.completed and state(game) == held
        amounts = next_step.edit_original_response.call_args.kwargs["view"]
        amounts.values.update(
            {x["token"]: (str(expected[x["actor"]["entity"]]),) for x in selected}
        )
        amounts.values.update(account="PRIVATE ACTUAL PERMISSION GRANT")
        await amounts.confirm.callback(current(1, 31512))
        assert amounts.completed

    asyncio.run(native_spend())
    final = state(game)
    receipt = rules.awards(final)[0]
    assert receipt.phase == "spent" and len(rules.awards(final)) == 1
    for uid, sheet in final.sheets.items():
        assert sheet.permissions == before.sheets[uid].permissions + expected.get(uid, 0)
        assert (
            sheet.assets == before.sheets[uid].assets
            and sheet.identities == before.sheets[uid].identities
        )
    grants = tuple(
        rules.PermissionGrant(
            actor=ActorRef.model_validate(x["actor"]), amount=expected[x["actor"]["entity"]]
        )
        for x in selected
    )
    assert service.spend_permissions(
        ADMIN, "31512", identity, held.revision, grants, "PRIVATE ACTUAL PERMISSION GRANT"
    ) == dict(id=identity, phase="spent", recipients=len(grants))
    with pytest.raises(WorkflowError, match="unspent"):
        service.spend_permissions(
            ADMIN, str(uuid4()), identity, final.revision, grants, "Cannot consume twice"
        )
    assert state(game) == final and (strain.dice.calls, game.dice.calls) == calls
    assert HandlerAdvancementService(ledger).view(ADMIN, identity)["phase"] == "spent"
    with ledger.engine.connect() as c:
        assert service._tasks(c, ADMIN) == []
        assert "PRIVATE " not in str(list(c.scalars(sa.select(t.events.c.payload_json))))

    async def saved_card():
        own = current(1, 31520)
        await own.response.defer(ephemeral=True)
        await open_advancement(own, service, identity)
        card = own.edit_original_response.call_args.kwargs
        assert card["view"] is None
        assert "PRIVATE ACTUAL HANDLER AWARD" == card["embeds"][1].description
        assert "PRIVATE ACTUAL PERMISSION GRANT" == card["embeds"][2].description

    asyncio.run(saved_card())


def test_award_stale_original_recipient_and_new_appointment_do_not_consume(
    ledger, tmp_path, monkeypatch
):
    _, game, service, identity = source(ledger, tmp_path, monkeypatch, 6)
    data = service.view(ADMIN, identity)
    service.claim_void(
        ADMIN,
        str(uuid4()),
        identity,
        data["revision"],
        data["work_revision"],
        "Actual original finite award",
    )
    original = state(game)
    girl = current_ref(original, 2)
    choice = (rules.PermissionGrant(actor=girl, amount=2),)
    with pytest.raises(WorkflowError, match="original Handler"):
        service.spend_permissions(
            OTHER, str(uuid4()), identity, original.revision, choice, "Not my award"
        )
    # An empty or repeated target selection never spends a finite source.
    with pytest.raises(WorkflowError, match="nonempty"):
        service.spend_permissions(
            ADMIN, str(uuid4()), identity, original.revision, (), "No real group"
        )
    with pytest.raises(WorkflowError, match="distinct"):
        service.spend_permissions(
            ADMIN, str(uuid4()), identity, original.revision, choice + choice, "Same original twice"
        )
    assert state(game) == original
    stale = (
        rules.PermissionGrant(
            actor=ActorRef(kind="pilot", entity=girl.entity, incarnation=str(uuid4())), amount=2
        ),
    )
    with pytest.raises(WorkflowError, match="original Girls"):
        service.spend_permissions(
            ADMIN,
            str(uuid4()),
            identity,
            original.revision,
            stale,
            "A different original cannot receive these Permissions",
        )
    assert state(game) == original and rules.awards(original)[0].phase == "held"
    appointments = HandlerService(ledger)
    with ledger.engine.connect() as c:
        revision = appointments.current(c)[0]
    appointments.appoint(ADMIN, str(uuid4()), revision, None)
    with ledger.engine.connect() as c:
        revision = appointments.current(c)[0]
    appointments.appoint(ADMIN, str(uuid4()), revision, 1)
    before = state(game)
    assert not service.view(ADMIN, identity)["current"]
    with pytest.raises(WorkflowError, match="original Handler and appointment"):
        service.spend_permissions(
            ADMIN,
            str(uuid4()),
            identity,
            before.revision,
            (rules.PermissionGrant(actor=current_ref(before, 3), amount=1),),
            "New appointment cannot inherit",
        )
    assert state(game) == before and rules.awards(before)[0].phase == "held"
