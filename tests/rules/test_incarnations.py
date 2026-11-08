"""Legacy identities are proved from original snapshots without rewriting their history."""

import json
from uuid import uuid4

import pytest
import sqlalchemy as sa
from test_ledger import ledger as ledger
from test_m2_game import state
from test_mission_service import service

from girlframe.database import tables as t
from girlframe.engine.m2 import GameState, PilotSheet
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.services.m3_incarnations import backfill, hydrate, identity
from girlframe.services.onboarding import WorkflowError


def legacy(store, game, change=None):
    # Simulate an old producer by APPENDING a legacy event/snapshot. Never alter history.
    canon = state(game)
    for sheet in canon.sheets.values():
        sheet.character_id = None
    if change:
        change(canon)
    canon.revision += 1
    body = canon.model_dump_json()
    with store.transaction() as c:
        event = store._audit(
            c,
            "synthetic:legacy-writer",
            str(uuid4()),
            "m2.synthetic_legacy_snapshot",
            {"game_revision": canon.revision},
        )
        c.execute(
            t.m2["m2_state_history"]
            .insert()
            .values(
                campaign_id=store.campaign_id,
                revision=canon.revision,
                body_json=body,
                event_id=event,
            )
        )
        c.execute(
            t.m2["m2_state"]
            .update()
            .where(t.m2["m2_state"].c.campaign_id == store.campaign_id)
            .values(revision=canon.revision, body_json=body)
        )
    return canon, body, event


def raw(store):
    with store.engine.connect() as c:
        return c.scalar(
            sa.select(t.m2["m2_state"].c.body_json).where(
                t.m2["m2_state"].c.campaign_id == store.campaign_id
            )
        )


def test_legacy_reads_derive_original_ids_without_changing_resources_or_persisted_history(ledger):
    _, game = service(ledger)
    original, encoded, event = legacy(
        ledger, game, lambda value: setattr(value.sheets["2"], "permissions", 7)
    )
    projected = state(game)
    assert raw(ledger) == encoded
    with ledger.engine.connect() as c:
        for uid, sheet in projected.sheets.items():
            snapshot = c.scalar(
                sa.select(t.snapshots.c.character_id).where(
                    t.snapshots.c.campaign_id == ledger.campaign_id,
                    t.snapshots.c.user_id == uid,
                    t.snapshots.c.revision == sheet.source_profile_revision,
                )
            )
            assert current_ref(projected, int(uid)).incarnation == snapshot
            assert sheet.model_copy(update={"character_id": None}) == original.sheets[uid]
        assert (
            c.scalar(
                sa.select(t.m2["m2_state_history"].c.body_json).where(
                    t.m2["m2_state_history"].c.event_id == event
                )
            )
            == encoded
        )


def test_first_real_write_records_proof_and_persists_only_identity_metadata(ledger):
    _, game = service(ledger)
    original, encoded, old_event = legacy(ledger, game)
    with ledger.transaction() as c:
        event = game.event(c, 1, "actual-next-write", "synthetic.actual_next_write", state(game))
    saved = GameState.model_validate_json(raw(ledger))
    assert all(x.character_id for x in saved.sheets.values())
    with ledger.engine.connect() as c:
        metadata = json.loads(
            c.scalar(sa.select(t.events.c.payload_json).where(t.events.c.id == event))
        )
        assert {x["owner"] for x in metadata["legacy_identity_bindings"]} == {2, 3}
        assert all(x["snapshot_event"] for x in metadata["legacy_identity_bindings"])
        assert (
            c.scalar(
                sa.select(t.m2["m2_state_history"].c.body_json).where(
                    t.m2["m2_state_history"].c.event_id == old_event
                )
            )
            == encoded
        )
    assert saved.sheets["2"].permissions == original.sheets["2"].permissions


def test_dry_run_backfill_rebuild_and_repeated_apply_do_not_reset_or_rewrite(ledger):
    _, game = service(ledger)
    _, encoded, _ = legacy(ledger, game)
    assert backfill(ledger, apply=False, key="review")["identities_found"] == 2
    assert raw(ledger) == encoded
    game.rebuild()
    assert all(x.character_id for x in state(game).sheets.values())
    result = backfill(ledger, apply=True, key="actual-backfill", operator="synthetic-operator")
    assert result["identities_persisted"] == 2
    after = raw(ledger)
    assert backfill(ledger, apply=True, key="retry")["identities_persisted"] == 0
    assert raw(ledger) == after
    game.rebuild()
    assert raw(ledger) == after


def test_missing_original_snapshot_fails_closed_without_guessing_uid(ledger):
    _, game = service(ledger)
    _, encoded, _ = legacy(
        ledger, game, lambda value: setattr(value.sheets["2"], "source_profile_revision", 999999)
    )
    with pytest.raises(WorkflowError, match="SOURCE_IDENTITY_MISSING"):
        state(game)
    with pytest.raises(WorkflowError, match="SOURCE_IDENTITY_MISSING"):
        backfill(ledger, apply=True, key="cannot-guess")
    assert raw(ledger) == encoded


def test_fresh_already_bound_state_needs_no_backfill(ledger):
    _, game = service(ledger)
    before = raw(ledger)
    assert backfill(ledger, apply=True, key="already-current")["identities_found"] == 0
    assert raw(ledger) == before


def test_replacement_draft_cannot_take_an_old_unbound_resource_sheet(ledger):
    from test_career_service import begin, ended

    careers, game, _, _, _ = ended(ledger)
    saved = state(game).career_archives[-1]
    fresh = begin(careers)
    canon = state(game)
    old = PilotSheet.model_validate_json(saved.sheet_json)
    old.character_id, old.permissions = None, 90
    canon.sheets["2"], canon.order = old, (2, 3)
    with ledger.engine.connect() as c:
        with pytest.raises(WorkflowError, match="old resources"):
            hydrate(c, ledger.campaign_id, canon)
        old.source_profile_revision = fresh["profile_revision"]
        with pytest.raises(WorkflowError, match="replacement draft"):
            identity(c, ledger.campaign_id, canon, 2, require_current_profile=False)


def test_pending_legacy_action_uses_immutable_original_binding_after_first_canonical_write(ledger):
    from test_beneath_service import ready
    from test_ledger import PLAYER
    from test_m2_game import pass_tags, tick

    from girlframe.engine.m2 import PlayInput

    game, worker, gateway = ready(ledger)
    _, encoded, old_event = legacy(ledger, game)
    action_id = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play="keep_your_head", heat=0, context="Actual old pending Play", trigger_confirmed=True
        ),
    )["action_id"]
    with ledger.transaction() as c:
        action = game.action(c, action_id)
        action["data"].pop("character_ids")
        game.save_action(c, action)
    tick(worker, gateway, 3)
    assert game.dice.calls == 1
    with ledger.engine.connect() as c:
        action = game.action(c, action_id)
        expected = game.legacy_action_bindings(c, action)
        assert expected["2"] == state(game).sheets["2"].character_id
        assert (
            c.scalar(
                sa.select(t.m2["m2_state_history"].c.body_json).where(
                    t.m2["m2_state_history"].c.event_id == old_event
                )
            )
            == encoded
        )
    pass_tags(game)
    assert game.inspect(PLAYER, action_id)["receipt"]["faces"]


def test_ending_legacy_original_records_binding_in_its_archive_without_a_new_profile_snapshot(
    ledger,
):
    from girlframe.services.m3_careers import end_in_transaction, synchronize_end

    _, game = service(ledger)
    legacy(ledger, game)
    with ledger.transaction() as c:
        canon = state(game)
        actor, event = current_ref(canon, 2), str(uuid4())
        ended = end_in_transaction(
            c,
            game,
            canon,
            actor,
            reason="execution",
            source_event=event,
            account="Actual synthetic source ending",
            archive_id="legacy-original-archive",
        )
        game.event(c, 1, "actual-ending-key", "m3.synthetic_ending", ended, event_id=event)
        synchronize_end(c, game, ended.career_archives[-1])
    assert state(game).career_archives[-1].actor == actor
    assert "2" not in state(game).sheets


def test_offline_cli_defaults_to_sanitized_dry_run_and_private_policy_only(
    ledger, tmp_path, monkeypatch, capsys
):
    import runpy
    import sys
    from pathlib import Path

    _, game = service(ledger)
    _, encoded, _ = legacy(ledger, game)
    policy = tmp_path / "private-test-policy.json"
    policy.write_text(ledger.policy.model_dump_json())
    tool = Path(__file__).resolve().parents[2] / "tools/backfill_legacy_incarnations.py"
    entry = runpy.run_path(str(tool))
    monkeypatch.setattr(
        sys,
        "argv",
        [str(tool), "--database", str(ledger.engine.url.database), "--policy", str(policy)],
    )
    capsys.readouterr()
    entry["main"]()
    output = capsys.readouterr().out
    result = json.loads(output)
    assert result["dry_run"] is True and result["identities_persisted"] == 0
    assert result["identities_found"] == 2 and raw(ledger) == encoded
    assert ledger.campaign_id not in output and "callsign" not in output
