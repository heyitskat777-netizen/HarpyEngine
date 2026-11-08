"""Actual Defeat injury → owned care → confirmed waking → original Girl Play exchange."""

import asyncio
from concurrent.futures import ThreadPoolExecutor

import pytest
import sqlalchemy as sa
from test_defeat_service import rolled
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import answer, state, tick
from test_mission_ui import current

from girlframe.database import tables as t
from girlframe.discord_adapter.m3_medical import open_medical
from girlframe.engine.m3_girl_runtime_state import change_playbook_runtime, has_rule
from girlframe.engine.m3_medical import Care, Exchange
from girlframe.services.m3_medical import MedicalService
from girlframe.services.onboarding import WorkflowError


def injured(store):
    game, worker, gateway, _, identity = rolled(store)
    answer(
        game,
        PLAYER,
        "defeat_select",
        options=("handler_rescue_swap_girl_play_on_waking",),
        text="Actual Handler rescue and injury",
    )
    tick(worker, gateway, 6)
    svc = MedicalService(store)
    task = svc.tasks(PLAYER)[0]
    assert task["stage"] == "need_care" and game.inspect(PLAYER, identity)["state"] == "complete"
    return svc, game, task["id"]


def proposed(store, account="Actual medical help and waking"):
    svc, game, identity = injured(store)
    data = svc.get(PLAYER, identity)
    svc.propose(
        PLAYER, "actual-medical-proposal", identity, data["revision"], Care(account=account)
    )
    return svc, game, identity


def awake(store):
    svc, game, identity = proposed(store)
    data = svc.get(ADMIN, identity)
    svc.confirm(
        ADMIN,
        "actual-medical-wake",
        identity,
        data["revision"],
        data["game_revision"],
        True,
        "Actual treatment and waking confirmed",
    )
    return svc, game, identity


def selection():
    return Exchange(
        removed="girl.mockingbird.bad-at-being-a-person",
        acquired="girl.princess.objectively-beautiful",
    )


def test_actual_waking_clears_incapacity_without_repairs_then_owned_exchange_finishes(ledger):
    svc, game, identity = proposed(ledger)
    original = state(game)
    assert original.sheets["2"].medical_state == "unconscious_injured"
    assert original.placements[0].incapacitated
    data = svc.get(ADMIN, identity)
    with pytest.raises(WorkflowError):
        svc.confirm(
            OTHER,
            "not-medical-reviewer",
            identity,
            data["revision"],
            data["game_revision"],
            True,
            "No other actor owns this confirmation",
        )
    svc.confirm(
        ADMIN,
        "confirm-original-wake",
        identity,
        data["revision"],
        data["game_revision"],
        True,
        "Actual medical facts",
    )
    canon = state(game)
    assert canon.sheets["2"].medical_state == "fit" and not canon.placements[0].incapacitated
    assert canon.sheets["2"].assets == original.sheets["2"].assets
    assert canon.placements[0].vessel_id == original.placements[0].vessel_id
    assert canon.placements[0].custody == original.placements[0].custody
    assert svc.get(PLAYER, identity)["stage"] == "choose_play"
    with ledger.engine.connect() as c:
        assert game.immediate_work(c, 2)
    data = svc.get(PLAYER, identity)
    result = svc.exchange(
        PLAYER,
        "actual-play-exchange",
        identity,
        data["revision"],
        data["game_revision"],
        selection(),
    )
    assert (
        svc.exchange(
            PLAYER,
            "actual-play-exchange",
            identity,
            data["revision"],
            data["game_revision"],
            selection(),
        )
        == result
    )
    after = state(game)
    assert after.sheets["2"].girl == "MOCKINGBIRD"
    assert has_rule(after.sheets["2"], "girl.princess.objectively-beautiful", "PRINCESS")
    assert not has_rule(after.sheets["2"], "girl.mockingbird.bad-at-being-a-person", "MOCKINGBIRD")
    assert not svc.tasks(PLAYER)
    with ledger.engine.connect() as c:
        assert not game.immediate_work(c, 2)


def test_medical_phase_and_swap_inventory_are_private_to_actual_participants(ledger):
    svc, _, identity = proposed(ledger, "PRIVATE_MEDICAL_ACCOUNT")
    assert "PRIVATE_MEDICAL_ACCOUNT" in str(svc.get(ADMIN, identity))
    with pytest.raises(WorkflowError):
        svc.get(OTHER, identity)
    data = svc.get(ADMIN, identity)
    svc.confirm(
        ADMIN,
        "wake-private-patient",
        identity,
        data["revision"],
        data["game_revision"],
        True,
        "Actual shared care evidence",
    )
    assert "choices" not in svc.get(ADMIN, identity)
    assert "choices" in svc.get(PLAYER, identity)
    with ledger.engine.connect() as c:
        assert "PRIVATE_MEDICAL" not in str(list(c.scalars(sa.select(t.events.c.payload_json))))


def test_owned_native_medical_confirmation_and_exchange_resume_after_restart(ledger):
    svc, game, identity = injured(ledger)

    async def run():
        player = current(2, 27101)
        await player.response.defer(ephemeral=True)
        await open_medical(player, svc, identity)
        form = player.edit_original_response.call_args.kwargs["view"]
        assert not await form.interaction_check(current(3))
        form.values.update(account="Actual medical assistance", vitals=("no",))
        await form.confirm.callback(current(2, 27102))
        assert form.completed
        handler = current(1, 27103)
        await handler.response.defer(ephemeral=True)
        await open_medical(handler, MedicalService(ledger), identity)
        review = handler.edit_original_response.call_args.kwargs["view"]
        review.values.update(decision=("yes",), evidence="Actual care and waking")
        await review.confirm.callback(current(1, 27104))
        assert review.completed
        await open_medical(player, MedicalService(ledger), identity)
        exchange = player.edit_original_response.call_args.kwargs["view"]
        exchange.values.update(removed=(selection().removed,), acquired=(selection().acquired,))
        await exchange.confirm.callback(current(2, 27105))
        assert exchange.completed

    asyncio.run(run())
    assert svc.get(PLAYER, identity)["stage"] == "complete" and game.dice.calls == 2


def test_unimplemented_borrow_and_used_book_cannot_be_faked_as_actual_ability(ledger):
    svc, game, identity = awake(ledger)
    data = svc.get(PLAYER, identity)
    with pytest.raises(WorkflowError, match="UNSUPPORTED_RULE"):
        svc.exchange(
            PLAYER,
            "unsupported-borrow",
            identity,
            data["revision"],
            data["game_revision"],
            Exchange(removed=selection().removed, acquired="girl.alpha.brutalize"),
        )
    with pytest.raises(WorkflowError):
        svc.exchange(
            ADMIN,
            "wrong-swap-owner",
            identity,
            data["revision"],
            data["game_revision"],
            selection(),
        )
    with ledger.transaction() as c:
        canon = state(game)
        canon.sheets["3"].girl = "PRINCESS"
        game.event(c, 1, "actual-used-target-book", "synthetic.state", canon)
    data = svc.get(PLAYER, identity)
    assert selection().acquired not in {x["id"] for x in data["choices"]["acquired"]}
    with pytest.raises(WorkflowError, match="unused base"):
        svc.exchange(
            PLAYER,
            "used-book-borrow",
            identity,
            data["revision"],
            data["game_revision"],
            selection(),
        )


def test_paused_medical_effects_wait_but_care_drafts_and_history_remain_readable(ledger):
    svc, game, identity = injured(ledger)
    ledger.safety(OTHER, "pause-medical-effects", ledger.status(OTHER)["revision"], pause=True)
    data = svc.get(PLAYER, identity)
    svc.propose(
        PLAYER,
        "paused-care-proposal",
        identity,
        data["revision"],
        Care(account="Actual care proposed"),
    )
    review = svc.get(ADMIN, identity)
    with pytest.raises(WorkflowError, match="SAFETY_PAUSED"):
        svc.confirm(
            ADMIN,
            "paused-waking",
            identity,
            review["revision"],
            review["game_revision"],
            True,
            "The pause does not select fictional outcomes",
        )
    assert state(game).sheets["2"].medical_state == "unconscious_injured"


def test_playbook_change_retains_actual_acquisitions_resets_old_masks_and_preserves_source_history(
    ledger,
):
    svc, game, identity = awake(ledger)
    data = svc.get(PLAYER, identity)
    svc.exchange(
        PLAYER,
        "borrow-before-book-change",
        identity,
        data["revision"],
        data["game_revision"],
        selection(),
    )
    original = state(game).sheets["2"]
    changed, fact = change_playbook_runtime(original, "ALPHA", "actual-new-baseline")
    assert changed.assets == original.assets and changed.identities == original.identities
    assert has_rule(changed, selection().acquired, "PRINCESS")
    assert has_rule(changed, "girl.alpha.brutalize", "ALPHA")
    assert (
        changed.girl_runtime.swaps == ()
        and selection().acquired in changed.girl_runtime.retained_rules
    )
    assert original.girl_runtime.model_dump_json() == fact["prior_runtime"]
    back, _ = change_playbook_runtime(changed, "MOCKINGBIRD", "actual-second-baseline")
    assert has_rule(back, selection().removed, "MOCKINGBIRD")
    assert has_rule(back, selection().acquired, "PRINCESS")


def test_rejected_care_changes_no_body_state_and_owner_can_propose_actual_new_help(ledger):
    svc, game, identity = proposed(ledger)
    original = state(game).model_dump_json()
    data = svc.get(ADMIN, identity)
    svc.confirm(
        ADMIN,
        "decline-unestablished-care",
        identity,
        data["revision"],
        data["game_revision"],
        False,
        "The claimed care has not happened",
    )
    assert state(game).model_dump_json() == original
    data = svc.get(PLAYER, identity)
    assert data["can_propose"] and data["stage"] == "need_care"
    svc.propose(
        PLAYER, "new-actual-care", identity, data["revision"], Care(account="New actual help")
    )
    assert svc.get(ADMIN, identity)["evidence"] == ""


def test_medical_history_survives_missing_registry_but_exchange_cannot_mutate(
    ledger, monkeypatch, tmp_path
):
    svc, game, identity = awake(ledger)
    data = svc.get(PLAYER, identity)
    original = state(game).model_dump_json()
    monkeypatch.setenv("GIRLFRAME_RULES_REGISTRY", str(tmp_path / "missing.json"))
    assert svc.get(PLAYER, identity)["stage"] == "choose_play"
    assert svc.get(PLAYER, identity)["choices"] is None
    with pytest.raises(WorkflowError, match="registry is unavailable"):
        svc.exchange(
            PLAYER,
            "missing-catalogue-swap",
            identity,
            data["revision"],
            data["game_revision"],
            selection(),
        )
    assert state(game).model_dump_json() == original


def test_changed_character_cannot_inherit_old_medical_choices(ledger):
    svc, game, identity = awake(ledger)
    with ledger.transaction() as c:
        canon = state(game)
        canon.sheets["2"].character_id = "replacement-original-character"
        game.event(c, 1, "synthetic-replacement-after-waking", "synthetic.state", canon)
    data = svc.get(PLAYER, identity)
    assert data["stale"] and not data["can_exchange"]
    with pytest.raises(WorkflowError, match="STALE_ACTOR"):
        svc.exchange(
            PLAYER,
            "wrong-character-medical-swap",
            identity,
            data["revision"],
            data["game_revision"],
            selection(),
        )


def test_waking_and_swap_both_rollback_after_history_and_retry_once_under_concurrency(
    ledger, monkeypatch
):
    svc, game, identity = proposed(ledger)
    data = svc.get(ADMIN, identity)
    original = state(game).model_dump_json()
    emit = svc.game.event

    def fail(*args, **kwargs):
        emit(*args, **kwargs)
        raise RuntimeError("Synthetic medical post-history failure")

    monkeypatch.setattr(svc.game, "event", fail)
    with pytest.raises(RuntimeError, match="post-history"):
        svc.confirm(
            ADMIN,
            "atomic-wake",
            identity,
            data["revision"],
            data["game_revision"],
            True,
            "Actual medical help",
        )
    assert state(game).model_dump_json() == original
    monkeypatch.setattr(svc.game, "event", emit)
    with ThreadPoolExecutor(2) as pool:
        outcomes = list(
            pool.map(
                lambda _: svc.confirm(
                    ADMIN,
                    "atomic-wake",
                    identity,
                    data["revision"],
                    data["game_revision"],
                    True,
                    "Actual medical help",
                ),
                range(2),
            )
        )
    assert outcomes[0] == outcomes[1]
    data = svc.get(PLAYER, identity)
    original = state(game).model_dump_json()
    monkeypatch.setattr(svc.game, "event", fail)
    with pytest.raises(RuntimeError, match="post-history"):
        svc.exchange(
            PLAYER,
            "atomic-medical-swap",
            identity,
            data["revision"],
            data["game_revision"],
            selection(),
        )
    assert state(game).model_dump_json() == original
    monkeypatch.setattr(svc.game, "event", emit)
    with ThreadPoolExecutor(2) as pool:
        outcomes = list(
            pool.map(
                lambda _: svc.exchange(
                    PLAYER,
                    "atomic-medical-swap",
                    identity,
                    data["revision"],
                    data["game_revision"],
                    selection(),
                ),
                range(2),
            )
        )
    assert outcomes[0] == outcomes[1]
    assert len(state(game).sheets["2"].girl_runtime.swaps) == 1
