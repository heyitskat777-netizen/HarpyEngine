"""Real twenty-Permission ending with atomic original receipts and safe replay."""

import asyncio
from concurrent.futures import ThreadPoolExecutor

import pytest
import sqlalchemy as sa
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger_fixture
from test_m2_game import state
from test_mission_ui import current
from test_requisition_service import ready

from girlframe.database import tables as t
from girlframe.discord_adapter.m3_retirement import open_retirement
from girlframe.engine.m2 import PilotSheet
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.services.m3_retirement import RetirementService
from girlframe.services.onboarding import WorkflowError

ledger = ledger_fixture


def setup(store, funds=25):
    _, game = ready(store)
    with store.transaction() as c:
        canon = state(game)
        canon.sheets["2"].permissions = funds
        game.event(c, 1, "synthetic-retirement-funds", "synthetic.state", canon)
    return RetirementService(game), game


def retire(service, *, key="actual-retirement", preview=None, viewer=PLAYER):
    data = preview or service.view(viewer)
    return service.retire(
        viewer,
        key,
        ActorRef.model_validate(data["actor"]),
        data["source_sha256"],
        "PRIVATE_ACTUAL_RETIREMENT",
        True,
    )


def test_actual_paid_retirement_archives_original_after_payment_and_keeps_stable_sql_identity(
    ledger,
):
    svc, game = setup(ledger)
    with ledger.engine.connect() as c:
        profile = c.scalar(sa.select(t.characters.c.id).where(t.characters.c.user_id == "2"))
    preview = svc.view(PLAYER)
    result = retire(svc, preview=preview)
    assert retire(svc, preview=preview) == result
    canon = state(game)
    assert "2" not in canon.sheets and 2 not in canon.order
    archive = canon.career_archives[-1]
    assert archive.ending == "retirement" and archive.actor == ActorRef.model_validate(
        preview["actor"]
    )
    assert PilotSheet.model_validate_json(archive.sheet_json).permissions == 5
    assert any(
        x.get("kind") == "retirement_discharge" and x.get("surgeries") == "reversed"
        for x in canon.facts
    )
    saved = svc.receipt(PLAYER, result["id"])
    assert saved["receipt"]["price"] == 20 and saved["archive_id"] == archive.id
    with ledger.engine.connect() as c:
        assert (
            c.scalar(sa.select(t.characters.c.id).where(t.characters.c.user_id == "2")) == profile
        )
        assert "PRIVATE_ACTUAL" not in str(list(c.scalars(sa.select(t.events.c.payload_json))))
    with pytest.raises(WorkflowError):
        svc.receipt(ADMIN, result["id"])
    with pytest.raises(WorkflowError):
        svc.receipt(OTHER, result["id"])


def test_funds_stale_actor_pause_and_missing_confirmation_cannot_end_the_career(ledger):
    svc, game = setup(ledger, funds=19)
    before = state(game).model_dump_json()
    with pytest.raises(WorkflowError, match="twenty"):
        retire(svc)
    assert state(game).model_dump_json() == before
    data = svc.view(PLAYER)
    with pytest.raises(WorkflowError, match="Explicitly confirm"):
        svc.retire(
            PLAYER,
            "not-confirmed",
            ActorRef.model_validate(data["actor"]),
            data["source_sha256"],
            "Must not end this Girl",
            False,
        )
    ledger.safety(OTHER, "pause-retirement", ledger.status(OTHER)["revision"], pause=True)
    with pytest.raises(WorkflowError, match="SAFETY_PAUSED"):
        retire(svc, key="paused-retire")
    assert "2" in state(game).sheets


def test_failed_retirement_rolls_back_payment_history_archive_and_scene_cleanup(
    ledger, monkeypatch
):
    svc, game = setup(ledger)
    before = state(game).model_dump_json()
    original = game.event

    def fail_after_history(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError("Synthetic retirement history failure")

    monkeypatch.setattr(game, "event", fail_after_history)
    with pytest.raises(RuntimeError, match="history failure"):
        retire(svc)
    assert state(game).model_dump_json() == before
    monkeypatch.setattr(game, "event", original)
    assert retire(svc)["ending"] == "retirement"


def test_concurrent_same_retirement_source_ends_and_charges_once(ledger):
    svc, game = setup(ledger)
    data = svc.view(PLAYER)
    with ThreadPoolExecutor(2) as pool:
        result = list(pool.map(lambda _: retire(svc, preview=data), range(2)))
    assert result[0] == result[1]
    assert len(state(game).career_archives) == len(svc.retirement_history(PLAYER)) == 1


def test_native_retirement_requires_original_owner_and_explicit_payment_confirmation(ledger):
    svc, game = setup(ledger)

    async def run():
        caller = current(2, 21101)
        await caller.response.defer(ephemeral=True)
        await open_retirement(caller, svc)
        form = caller.edit_original_response.call_args.kwargs["view"]
        assert not await form.interaction_check(current(3))
        assert "2" in state(game).sheets
        form.values.update(account="PRIVATE_ACTUAL_RETIREMENT", confirm=("yes",))
        await form.confirm.callback(current(2, 21102))
        assert form.completed

    asyncio.run(run())
    assert "2" not in state(game).sheets and state(game).career_archives[-1].ending == "retirement"
