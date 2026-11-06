"""Actual graft purchase, Keep and source-owned Punishment/restoration lifecycle."""

import asyncio
import copy
from uuid import uuid4

import pytest
from test_enforcer_requisitions import approved
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Gateway, answer, pass_tags, start, state, tick
from test_mission_service import service
from test_mission_ui import current
from test_privileges import change

from girlframe.delivery.m2_worker import GameWorker
from girlframe.discord_adapter.m3_nightmare import open_purchase
from girlframe.engine import m3_nightmare as rules
from girlframe.engine.m2 import PlayInput
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_punishments import Details
from girlframe.services.m3_nightmare import NightmareService, entitlement
from girlframe.services.m3_privileges import PrivilegeService, purchase_proof
from girlframe.services.m3_punishments import PunishmentService
from girlframe.services.onboarding import WorkflowError


def test_actual_grafted_nightmare_purchase_keep_suspend_restore_same_source(
    ledger, tmp_path, monkeypatch
):
    _, game = service(ledger, frame="WYVERN 0.4")
    approved(ledger, game, tmp_path, monkeypatch, extra=(rules.RULE,))
    ledger.policy = ledger.policy.model_copy(
        update={
            "owner_m3_rulings": ledger.policy.owner_m3_rulings.model_copy(
                update={
                    "beneath_private_choices": "affected_owner",
                    "privilege_restoration": "inflictor_condition_owner_restores",
                }
            )
        }
    )
    with ledger.transaction() as c:
        actual = state(game)
        actual.order = (3, 2)
        sheet = actual.sheets["2"]
        sheet.permissions = 6
        sheet.heat = 5
        for family in ("girl", "frame"):
            next(x for x in sheet.assets if x.family == family).void = True
        game.event(c, 1, str(uuid4()), "synthetic.prior_resources", actual)
    source = NightmareService(game)
    before = state(game)
    data = source.menu(PLAYER)
    assert data["price"] == 3 and data["kind"] == "frame_grafting"
    actor = ActorRef.model_validate(data["actor"])
    args = (
        PLAYER,
        "actual-nightmare-graft",
        data["revision"],
        actor,
        data["frame"],
        "Actual graft acquisition",
        "CONSUME",
    )
    for donor in (None, "WYVERN 0.4"):
        with pytest.raises(WorkflowError, match="Priestess donor"):
            source.buy(*args[:-1], donor)
        assert state(game) == before
    result = source.buy(*args)
    assert source.buy(*args) == result
    paid = rules.held(state(game), actor)
    assert paid and paid.donor_frame == "CONSUME" and paid.price == 3
    assert len(state(game).requisitions) == 1 and state(game).sheets["2"].permissions == 3
    assert state(game).sheets["3"] == before.sheets["3"]
    with ledger.engine.connect() as c:
        purchase_proof(c, ledger, paid)

    game.dice.faces = (3, 3)
    worker, gateway = GameWorker(game), Gateway()
    identity = start(game)
    tick(worker, gateway, 3)
    raw = copy.deepcopy(game.inspect(PLAYER, identity)["receipt"])
    assert raw["heat"] == 0 and raw["base_modifier"] == 2 and raw["pre_total"] == 8
    assert raw["nightmare_purchase"] == paid.id and game.dice.calls == 1
    pass_tags(game)
    answer(game, PLAYER, "actor_keep", options=("tough", "in_control"), denied=("desperate",))
    answer(game, ADMIN, "handler_keep", flag=True, text="Terrifying enough for this danger")
    final = game.inspect(PLAYER, identity)
    assert final["state"] == "complete" and final["receipt"] == raw
    assert set(final["result"]["positive"]) == {"terrifying", "tough", "in_control"}
    assert final["result"]["negative"] == ["desperate"] and final["result"]["enough"]
    tick(worker, gateway, 5)

    # A real social Play produces the owned discipline request for the original purchaser.
    game.dice.faces = (6, 6)
    social = game.begin(
        OTHER,
        str(uuid4()),
        900,
        state(game).sheets["3"].revision,
        PlayInput(
            play="put_someone_beneath_you",
            target=2,
            heat=0,
            context="Actual confrontation",
            trigger_confirmed=True,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    answer(
        game,
        OTHER,
        "beneath_select",
        options=("tag", "punish"),
        fields={"tag": "Actual confrontation"},
        text="Actual discipline",
    )
    work = game.decision(OTHER, game.choices(OTHER)[0]["id"])["body"]["work_id"]
    discipline = PunishmentService(ledger)
    preview = discipline.get(OTHER, work)
    assert {"id": paid.id, "name": "Nightmare Core"} in preview["choices"]["requisitions"]
    discipline.apply(
        OTHER,
        str(uuid4()),
        work,
        preview["revision"],
        preview["game_revision"],
        Details(
            kind="revoked_privileges",
            requisition=paid.id,
            restoration="Resolve the actual condition",
        ),
    )
    assert game.inspect(OTHER, social)["state"] == "complete"
    tick(worker, gateway, 5)
    suspended = state(game)
    gate = next(x for x in suspended.obligations if x.kind == "revoked_requisition")
    assert rules.held(suspended, actor) is None and source.menu(PLAYER)["suspended"]
    calls = game.dice.calls
    with pytest.raises(WorkflowError):
        start(game)  # Holding five Heat requires ordinary spending while Nightmare is suspended.
    latest = source.menu(PLAYER)
    with pytest.raises(WorkflowError, match="instead of buying twice"):
        source.buy(
            PLAYER,
            str(uuid4()),
            latest["revision"],
            actor,
            data["frame"],
            "Cannot duplicate the suspended source",
            "CONSUME",
        )
    assert state(game) == suspended and game.dice.calls == calls
    assert (
        source.buy(*args) == result
    )  # Even a purchase replay cannot duplicate a suspended source.
    restoration = PrivilegeService(ledger)
    change(restoration, OTHER, gate.id, allow=True)
    change(restoration, PLAYER, gate.id, allow=False)
    restored = state(game)
    assert rules.held(restored, actor) == paid
    assert restored.requisitions == suspended.requisitions and restored.sheets["2"].permissions == 3
    assert restored.sheets["2"].heat == 5
    identity = start(game)
    tick(worker, gateway, 3)
    again = game.inspect(PLAYER, identity)["receipt"]
    assert again["nightmare_purchase"] == paid.id and again["heat"] == 0
    assert game.dice.calls == calls + 1


def test_native_graft_form_records_eligible_donor_and_exact_three_permission_purchase(
    ledger, tmp_path, monkeypatch
):
    _, game = service(ledger, girl="ALPHA", frame="THE ENFORCER")
    approved(ledger, game, tmp_path, monkeypatch, extra=(rules.RULE,))
    with ledger.transaction() as c:
        actual = state(game)
        actual.sheets["2"].permissions = 3
        game.event(c, 1, str(uuid4()), "synthetic.prior_permissions", actual)

    async def purchase():
        own = current(2, 992001)
        await own.response.defer(ephemeral=True)
        await open_purchase(own, NightmareService(game))
        form = own.edit_original_response.call_args.kwargs["view"]
        assert "3 Permissions" in form.text() and "Frame Grafting" in form.text()
        form.values.update(donor=("JANUS",), account="Actual Priestess donor graft")
        await form.confirm.callback(current(2, 992002))
        assert form.completed

    asyncio.run(purchase())
    actual = state(game)
    paid = rules.held(actual, current_ref(actual, 2))
    assert paid and paid.kind == "frame_grafting" and paid.donor_frame == "JANUS"
    assert actual.sheets["2"].permissions == 0 and game.dice.calls == 0
    # The receipt must retain its real donor and physical Frame, even if saved data is changed.
    forged = actual.model_copy(deep=True)
    forged.requisitions[0] = paid.model_copy(update={"donor_frame": "THE ENFORCER"})
    assert rules.held(forged, paid.actor) is None
    forged = actual.model_copy(deep=True)
    forged.requisitions[0] = paid.model_copy(update={"frame_instance": "another-physical-frame"})
    assert rules.held(forged, paid.actor) is None
    forged = actual.model_copy(deep=True)
    forged.requisitions[0] = paid.model_copy(update={"donor_frame": "CONSUME"})
    with (
        ledger.engine.connect() as c,
        pytest.raises(WorkflowError, match="SOURCE_REQUISITION_MISSING"),
    ):
        entitlement(game, c, forged, paid.actor)
