import json
from concurrent.futures import ThreadPoolExecutor

import pytest
import sqlalchemy as sa
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger_fixture
from test_m2_game import state
from test_reaction_service import mark, setup, work
from test_replacement import supplied

from girlframe.database import tables as t
from girlframe.engine.m2 import PlayInput
from girlframe.engine.m3_frame_state import Preferences
from girlframe.services.m3_replacement import COURT, ROOT, ReplacementService
from girlframe.services.onboarding import WorkflowError

ledger = ledger_fixture


def pending(store):
    reactions, missions, game, mission = setup(store, boxes=7)
    mark(reactions, work(missions, mission, "doctor_obsolescence")["id"])
    root = next(x for x in missions.owned_work(PLAYER) if x["kind"] == ROOT)
    return ReplacementService(missions), game, mission, root["id"]


def propose(svc, identity, preferences=None, key="propose"):
    current = svc.get(PLAYER, identity)
    return svc.propose(
        PLAYER,
        key,
        identity,
        current["revision"],
        current["game_revision"],
        preferences or Preferences(frame="THE ENFORCER"),
    )


def quote(svc, identity, package=None, key="quote"):
    current = svc.get(ADMIN, identity)
    return svc.quote(
        ADMIN, key, identity, current["revision"], current["game_revision"], package or supplied()
    )


def accept(svc, identity, key="replace-confirm"):
    current = svc.get(PLAYER, identity)
    return svc.apply(
        PLAYER,
        key,
        identity,
        current["revision"],
        current["game_revision"],
        current["package_revision"],
    )


def test_free_replacement_updates_canon_profile_history_and_cosmetic_intent_once(ledger):
    svc, game, mission, identity = pending(ledger)
    before = state(game).sheets["2"]
    with ledger.engine.connect() as c:
        old_private = c.scalar(
            sa.select(t.characters.c.private_json).where(t.characters.c.user_id == "2")
        )
    result = propose(svc, identity)
    assert state(game).sheets["2"].frame_scrapped
    quote(svc, result["package_id"])
    current = svc.get(PLAYER, identity)
    assert current["ready"] and state(game).sheets["2"].frame == "DOCTORDOCTOR MK. II"
    applied = accept(svc, identity)
    after = state(game).sheets["2"]
    assert after.frame == "THE ENFORCER" and not after.frame_scrapped
    assert after.permissions == before.permissions and after.heat == before.heat
    assert after.identities == before.identities
    assert (
        svc.apply(
            PLAYER,
            "replace-confirm",
            identity,
            current["revision"],
            current["game_revision"],
            current["package_revision"],
        )
        == applied
    )
    with ledger.engine.connect() as c:
        row = (
            c.execute(sa.select(t.characters).where(t.characters.c.user_id == "2")).mappings().one()
        )
        assert row["private_json"] == old_private
        assert row["revision"] == after.source_profile_revision
        assert json.loads(row["public_json"])["frame_playbook"] == "THE ENFORCER"
        sync = (
            c.execute(sa.select(t.character_sync).where(t.character_sync.c.user_id == "2"))
            .mappings()
            .one()
        )
        assert json.loads(sync["desired_json"])["frame_playbook"] == "THE ENFORCER"
        assert "notes" not in json.loads(sync["desired_json"])
        event = (
            c.execute(sa.select(t.events).where(t.events.c.kind == "m3.compulsory_frame_replaced"))
            .mappings()
            .one()
        )
        assert event["ruleset_version"] == "girlframe-m3-core-1"
        assert (
            json.loads(event["payload_json"])["rules_registry_sha256"]
            == ledger.policy.m3_approval.registry_sha256
        )
    svc.missions.complete(ADMIN, "reward", mission["id"], mission["revision"])
    assert game.begin(
        PLAYER,
        "new-frame-play",
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play="keep_your_head", context="Synthetic danger", trigger_confirmed=True, heat=0
        ),
    )["action_id"]


def test_handler_cannot_choose_frame_or_accept_and_other_player_cannot_read_package(ledger):
    svc, _, _, identity = pending(ledger)
    current = svc.get(ADMIN, identity)
    with pytest.raises(WorkflowError, match="assigned owner"):
        svc.propose(
            ADMIN,
            "forged-proposal",
            identity,
            current["revision"],
            current["game_revision"],
            Preferences(frame="THE ENFORCER"),
        )
    request = propose(svc, identity)
    with pytest.raises(WorkflowError):
        svc.get(OTHER, request["package_id"])
    quote(svc, request["package_id"])
    current = svc.get(ADMIN, identity)
    with pytest.raises(WorkflowError):
        svc.apply(
            ADMIN,
            "forged-accept",
            identity,
            current["revision"],
            current["game_revision"],
            current["package_revision"],
        )


def test_revised_package_invalidates_owner_form_and_uses_new_exact_assets(ledger):
    svc, game, _, identity = pending(ledger)
    request = propose(svc, identity)
    quote(svc, request["package_id"])
    old = svc.get(PLAYER, identity)
    quote(svc, request["package_id"], supplied(1), "revise")
    with pytest.raises(WorkflowError, match="STALE_WORK"):
        svc.apply(
            PLAYER,
            "old-form",
            identity,
            old["revision"],
            old["game_revision"],
            old["package_revision"],
        )
    accept(svc, identity)
    assert len([x for x in state(game).sheets["2"].assets if x.family == "frame"]) == 1


def test_stale_state_needs_fresh_proposal_and_supersedes_only_derived_tasks(ledger):
    svc, game, _, identity = pending(ledger)
    request = propose(svc, identity)
    quote(svc, request["package_id"])
    with ledger.transaction() as c:
        saved = state(game)
        saved.sheets["2"].heat += 1
        game.event(c, 1, "synthetic-state-change", "synthetic.change", saved)
    with pytest.raises(WorkflowError, match="STALE_PROPOSAL"):
        accept(svc, identity)
    propose(svc, identity, key="fresh-proposal")
    assert svc.get(ADMIN, request["package_id"])["state"] == "resolved"
    assert svc.get(PLAYER, identity)["state"] == "pending"
    assert state(game).sheets["2"].frame_scrapped


def test_court_recipient_has_minimal_view_and_must_actually_accept(ledger):
    svc, game, _, identity = pending(ledger)
    request = propose(
        svc, identity, Preferences(frame="THE RED QUEEN", court_role="The Knight", court_target=3)
    )
    quote(svc, request["package_id"])
    rows = svc.missions.owned_work(OTHER)
    court = next(x for x in rows if x["kind"] == COURT)
    view = svc.get(OTHER, court["id"])
    assert view["role"] == "The Knight" and "package" not in view and "preferences" not in view
    with pytest.raises(WorkflowError, match="explicitly accept"):
        accept(svc, identity)
    with pytest.raises(WorkflowError):
        svc.answer_court(PLAYER, "forged-court", court["id"], 1, view["game_revision"], True)
    svc.answer_court(OTHER, "court-yes", court["id"], 1, view["game_revision"], True)
    accept(svc, identity)
    assert state(game).sheets["2"].frame_runtime.court["The Knight"] == 3


def test_rollback_and_duplicate_concurrent_acceptance_preserve_exactly_once_effects(
    ledger, monkeypatch
):
    svc, game, _, identity = pending(ledger)
    request = propose(svc, identity)
    quote(svc, request["package_id"])
    before = state(game)
    original = svc._save

    def fail(*args, **kwargs):
        raise RuntimeError("Synthetic replacement failure")

    monkeypatch.setattr(svc, "_save", fail)
    with pytest.raises(RuntimeError):
        accept(svc, identity)
    assert state(game) == before
    monkeypatch.setattr(svc, "_save", original)
    current = svc.get(PLAYER, identity)

    def submit(key):
        try:
            return svc.apply(
                PLAYER,
                key,
                identity,
                current["revision"],
                current["game_revision"],
                current["package_revision"],
            )
        except WorkflowError:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(submit, ("first", "second")))
    assert sum(x is not None for x in results) == 1
    assert state(game).sheets["2"].frame_runtime.generation == 1


def test_pause_and_unsupported_package_never_waive_replacement(ledger):
    svc, game, _, identity = pending(ledger)
    request = propose(svc, identity)
    with pytest.raises(WorkflowError, match="UNSUPPORTED_RULE"):
        quote(svc, request["package_id"], supplied(additional_rules=("not-a-rule",)))
    ledger.safety(OTHER, "pause", ledger.status(OTHER)["revision"], pause=True)
    with pytest.raises(WorkflowError, match="SAFETY_PAUSED"):
        quote(svc, request["package_id"])
    assert (
        svc.get(PLAYER, identity)["state"] == "pending" and state(game).sheets["2"].frame_scrapped
    )


def test_obligation_cannot_be_reused_for_a_different_frame_instance(ledger):
    from girlframe.engine.m3_frame_state import FrameRuntime

    svc, game, _, identity = pending(ledger)
    with ledger.transaction() as c:
        saved = state(game)
        saved.sheets["2"].frame_runtime = FrameRuntime(
            id="different-instance", generation=2, source_work="synthetic-other-frame"
        )
        game.event(c, 1, "synthetic-new-instance", "synthetic.frame", saved)
    with pytest.raises(WorkflowError, match="STALE_FRAME"):
        propose(svc, identity)


def test_stale_court_request_can_be_declined_without_installing_a_frame(ledger):
    svc, game, _, identity = pending(ledger)
    propose(
        svc, identity, Preferences(frame="THE RED QUEEN", court_role="The Knight", court_target=3)
    )
    court = next(x for x in svc.missions.owned_work(OTHER) if x["kind"] == COURT)
    view = svc.get(OTHER, court["id"])
    with ledger.transaction() as c:
        saved = state(game)
        saved.sheets["2"].heat += 1
        game.event(c, 1, "synthetic-game-change", "synthetic.change", saved)
    with pytest.raises(WorkflowError, match="STALE_STATE"):
        svc.answer_court(OTHER, "stale-yes", court["id"], 1, view["game_revision"], True)
    result = svc.answer_court(OTHER, "decline-stale", court["id"], 1, view["game_revision"], False)
    assert result["accepted"] is False
    assert state(game).sheets["2"].frame_scrapped
    assert svc.get(PLAYER, identity)["state"] == "pending"


def test_completed_replacement_backup_and_projection_rebuild_keep_frame_and_profile(
    ledger, tmp_path
):
    from pathlib import Path

    from girlframe.config import Settings
    from girlframe.database.connection import create_database_engine
    from girlframe.database.maintenance import copy_database
    from girlframe.services.ledger import CampaignLedger
    from girlframe.services.m3_missions import MissionService
    from girlframe.services.onboarding import OnboardingStore

    svc, game, _, identity = pending(ledger)
    request = propose(svc, identity)
    quote(svc, request["package_id"])
    accept(svc, identity)
    expected = state(game)
    backup = tmp_path / "replacement-backup.db"
    copy_database(Path(ledger.engine.url.database), backup)
    engine = create_database_engine(Settings(database_url="sqlite:///" + str(backup)))
    try:
        store = OnboardingStore(engine, ledger.policy)
        restored = ReplacementService(MissionService(store, svc.missions.access.registry))
        restored.game.rebuild()
        CampaignLedger(store).rebuild_projections()
        assert state(restored.game) == expected
        assert restored.get(PLAYER, identity)["state"] == "resolved"
        assert store.draft(PLAYER)["frame_playbook"] == "THE ENFORCER"
    finally:
        engine.dispose()


def test_other_campaign_and_revoked_owner_cannot_read_or_confirm_replacement(ledger):
    from uuid import uuid4

    from girlframe.services.m3_missions import MissionService
    from girlframe.services.onboarding import OnboardingStore
    from girlframe.services.read_only_bot import GuildViewer

    svc, _, _, identity = pending(ledger)
    policy = ledger.policy.model_copy(update={"campaign_id": uuid4(), "guild_id": 201})
    isolated = OnboardingStore(ledger.engine, policy)
    outsider = GuildViewer(2, 201, True, True)
    isolated.join(outsider, "other-campaign")
    other = ReplacementService(MissionService(isolated, svc.missions.access.registry))
    with pytest.raises(WorkflowError, match="unavailable"):
        other.get(outsider, identity)
    request = propose(svc, identity)
    quote(svc, request["package_id"])
    current = svc.get(PLAYER, identity)
    with ledger.transaction() as c:
        c.execute(
            t.members.update()
            .where(t.members.c.campaign_id == ledger.campaign_id, t.members.c.user_id == "2")
            .values(active=False)
        )
    with pytest.raises(WorkflowError):
        svc.apply(
            PLAYER,
            "revoked-owner",
            identity,
            current["revision"],
            current["game_revision"],
            current["package_revision"],
        )
