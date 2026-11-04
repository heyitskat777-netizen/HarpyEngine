import json
from pathlib import Path
from uuid import uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger_fixture
from test_m2_game import setup_game, state

from girlframe.database import tables as t
from girlframe.engine.m3_policy import Approval, Rulings
from girlframe.engine.rules_registry import Registry
from girlframe.services.m3_access import digest
from girlframe.services.m3_missions import MissionService
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer

ledger = ledger_fixture


def service(store, girl="MOCKINGBIRD", frame="JANUS-B"):
    game, *_ = setup_game(store, girl=girl, frame=frame)
    registry = Registry.model_validate_json(
        (Path(__file__).resolve().parents[2] / "rules/registry.json").read_text()
    )
    store.policy = store.policy.model_copy(
        update={
            "m3_approval": Approval(
                registry_sha256=digest(registry),
                scope="rules_subset",
                subsystems=frozenset({"missions", "discipline"}),
                reviewer="synthetic fixture only",
                reference="Not independent certification",
            ),
            "owner_m3_rulings": Rulings(
                provenance="owner_approved_campaign_ruling",
                ace_bonus="current_ace",
                standard_unpriced_cost=1,
                extra_repairs="handler_quote",
                reprogramming_fallback="owner_selects_ordinary_slot",
                reprogramming_reset_marks="baseline_preserve_protected_locks",
                identity_duplicate_labels="distinct_ids",
                frame_reward_eligibility="roll_event_except_doctor_start",
                frame_reward_observation="both_routes",
                queen_reward_dog="self_only",
                frame_prisoner_reward_repeat="new_delivery_per_character",
                observation_choice_overlap="distinct_shared_list",
                observation_reprogram_owner="affected_player",
                observation_populace_controller="handler",
                director_overlap="one_presence_episode",
                director_exit_resources="retain_without_recovery",
                director_controller="separate_from_handler",
                punishment_details="inflictor_selects",
                regulation_breach_review="informed_handler",
                failure_dog_overlap="one_punishment_both_causes",
                sedation_small_set="mark_all_remaining",
                princess_ace_check="after_promotion",
                compulsory_frame_package="handler_defined",
                replacement_frame_repeat="different_playbook",
                compulsory_frame_charge="free",
                doctor_credit_recipients="current_pilots",
                sedation_duration="current_off_duty_period",
                sedation_identity_replacement="retain_slot_lock",
                strain_repeat_timing="next_period_start",
                strain_cascade_count="prior_occurrences_same_track",
                doctor_start_order="credit_before_budget",
                world_grid_steps="eight_neighbors",
                gorgon_class_change="preserve_body",
                gorgon_reappearance="preserve_old_assets_new_core_plan",
            ),
        }
    )
    return MissionService(store, registry), game


def launched(svc):
    row = svc.offer(ADMIN, "offer", "PRIVATE_OBJECTIVE", (2,))
    accepted = svc.respond(PLAYER, "accept", row["id"], 1, "accept")
    started = svc.start(ADMIN, "start", row["id"], accepted["revision"])
    return row["id"], started["revision"]


def test_mission_rewards_and_absent_dog_are_atomic_idempotent_and_durable(ledger):
    svc, game = service(ledger)
    identity, rev = launched(svc)
    first = svc.end(ADMIN, "end", identity, rev, True)
    assert first["phase"] == "awaiting_consequences" and first["rewards_committed"]
    assert state(game).sheets["2"].permissions == 2 and state(game).sheets["3"].permissions == 0
    view = svc.get(ADMIN, identity)
    assert view["pending_count"] == 1 and view["work"][0]["subject"] == 3
    restarted = MissionService(ledger, svc.access.registry)
    assert restarted.end(ADMIN, "end", identity, rev, True) == first
    with pytest.raises(WorkflowError, match="STALE_MISSION"):
        restarted.end(ADMIN, "another-end", identity, rev, True)
    with pytest.raises(WorkflowError, match="still pending"):
        restarted.complete(ADMIN, "force", identity, first["revision"])
    assert state(game).sheets["2"].permissions == 2


def test_current_ace_gets_bonus_even_when_absent(ledger):
    svc, game = service(ledger)
    with ledger.transaction() as c:
        saved = state(game)
        saved.order = (3, 2)
        game.event(c, 1, "test-rank", "synthetic.rank", saved)
    identity, rev = launched(svc)
    svc.end(ADMIN, "end", identity, rev, True)
    assert state(game).sheets["2"].permissions == 1
    assert state(game).sheets["3"].permissions == 1
    assert svc.get(ADMIN, identity)["mission"]["participants"] == [2]


def test_saved_mission_reads_survive_a_vacant_handler_appointment(ledger):
    from girlframe.services.handler_setup import HandlerService

    svc, _ = service(ledger)
    identity, revision = launched(svc)
    handler = HandlerService(ledger)
    with ledger.engine.connect() as c:
        expected = handler.current(c)[0]
    handler.appoint(ADMIN, "revoke-handler", expected, None)
    assert svc.list(PLAYER)[0]["id"] == identity
    assert svc.get(PLAYER, identity)["mission"]["phase"] == "active"
    with pytest.raises(WorkflowError):
        svc.end(ADMIN, "former-handler", identity, revision, True)


def test_pending_scene_play_cannot_be_bypassed_by_mission_end(ledger):
    from test_m2_game import start

    svc, game = service(ledger)
    identity, revision = launched(svc)
    action = start(game)
    with pytest.raises(WorkflowError, match="pending scene Play"):
        svc.end(ADMIN, "too-early", identity, revision, True)
    assert svc.get(ADMIN, identity)["mission"]["phase"] == "active"
    assert state(game).sheets["2"].permissions == 0
    game.abort(ADMIN, "explicit-recovery", action)
    assert svc.end(ADMIN, "after-recovery", identity, revision, True)["rewards_committed"]


def test_private_mission_and_metadata_have_no_administrator_override(ledger):
    svc, game = service(ledger)
    identity, rev = launched(svc)
    with pytest.raises(WorkflowError, match="visible only"):
        svc.get(OTHER, identity)
    outsider = GuildViewer(4, 200, True, True)
    ledger.join(outsider, "join-admin")
    with pytest.raises(WorkflowError, match="visible only"):
        svc.get(outsider, identity)
    assert svc.list(OTHER) == []
    assert svc.get(PLAYER, identity)["mission"]["objective"] == "PRIVATE_OBJECTIVE"
    with ledger.engine.connect() as c:
        payloads = " ".join(c.scalars(sa.select(t.events.c.payload_json)))
        outcomes = " ".join(c.scalars(sa.select(t.commands.c.outcome_json)))
    assert "PRIVATE_OBJECTIVE" not in payloads and "PRIVATE_OBJECTIVE" not in outcomes


@pytest.mark.parametrize("broken", ["approval", "rulings", "digest", "subsystem", "false_complete"])
def test_unapproved_m3_services_fail_closed(ledger, broken):
    svc, _ = service(ledger)
    approval = ledger.policy.m3_approval
    if broken == "approval":
        ledger.policy = ledger.policy.model_copy(update={"m3_approval": None})
    elif broken == "rulings":
        ledger.policy = ledger.policy.model_copy(update={"owner_m3_rulings": None})
    else:
        change = (
            {"registry_sha256": "0" * 64}
            if broken == "digest"
            else {"subsystems": frozenset({"economy"})}
            if broken == "subsystem"
            else {"scope": "core_complete"}
        )
        ledger.policy = ledger.policy.model_copy(
            update={"m3_approval": approval.model_copy(update=change)}
        )
    with pytest.raises(WorkflowError):
        svc.offer(ADMIN, "denied", "No", (2,))
    with ledger.engine.connect() as c:
        assert c.scalar(sa.select(sa.func.count()).select_from(t.m3["m3_missions"])) == 0


def test_rollback_after_permission_event_restores_all_mission_state(ledger, monkeypatch):
    svc, game = service(ledger)
    identity, rev = launched(svc)
    original = svc._save

    def fail(*args, **kwargs):
        raise RuntimeError("Synthetic commit failure")

    monkeypatch.setattr(svc, "_save", fail)
    with pytest.raises(RuntimeError):
        svc.end(ADMIN, "end", identity, rev, True)
    assert state(game).sheets["2"].permissions == 0
    assert svc.get(ADMIN, identity)["mission"]["phase"] == "active"
    monkeypatch.setattr(svc, "_save", original)
    svc.end(ADMIN, "end", identity, rev, True)
    assert state(game).sheets["2"].permissions == 2


@pytest.mark.parametrize(
    "girl,frame,success,kind",
    [
        ("PRINCESS", "JANUS-B", True, "princess_mission_end"),
        ("MOCKINGBIRD", "DOCTORDOCTOR MK. II", False, "doctor_obsolescence"),
    ],
)
def test_source_end_reactions_precede_reward_snapshot(ledger, girl, frame, success, kind):
    svc, game = service(ledger, girl, frame)
    identity, rev = launched(svc)
    result = svc.end(ADMIN, "end", identity, rev, success)
    assert result["phase"] == "ending" and not result["rewards_committed"]
    assert state(game).sheets["2"].permissions == 0
    assert any(x["kind"] == kind for x in svc.get(ADMIN, identity)["work"])
    with pytest.raises(WorkflowError, match="still pending"):
        svc.complete(ADMIN, "skip", identity, result["revision"])


def test_pause_revocation_and_other_campaign_do_not_leak_or_mutate(ledger):
    from girlframe.services.onboarding import OnboardingStore

    svc, game = service(ledger)
    identity, rev = launched(svc)
    ledger.safety(OTHER, "pause", ledger.status(OTHER)["revision"], pause=True)
    with pytest.raises(WorkflowError, match="SAFETY_PAUSED"):
        svc.end(ADMIN, "paused-end", identity, rev, True)
    assert svc.get(PLAYER, identity)["mission"]["phase"] == "active"
    ledger.safety(OTHER, "resume", ledger.status(OTHER)["revision"], pause=False)
    other_policy = ledger.policy.model_copy(update={"campaign_id": uuid4(), "guild_id": 201})
    other_store = OnboardingStore(ledger.engine, other_policy)
    other_viewer = GuildViewer(2, 201, True, False)
    other_store.join(other_viewer, "join-another-campaign")
    other = MissionService(other_store, svc.access.registry)
    with pytest.raises(WorkflowError, match="Unknown mission"):
        other.get(other_viewer, identity)
    with ledger.transaction() as c:
        c.execute(
            t.members.update()
            .where(t.members.c.campaign_id == ledger.campaign_id, t.members.c.user_id == "2")
            .values(active=False)
        )
    with pytest.raises(WorkflowError):
        svc.get(PLAYER, identity)


def test_concurrent_end_never_duplicates_rewards(ledger):
    from concurrent.futures import ThreadPoolExecutor

    svc, game = service(ledger)
    identity, rev = launched(svc)

    def finish(key):
        try:
            return svc.end(ADMIN, key, identity, rev, True)
        except WorkflowError:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(finish, ("end-a", "end-b")))
    assert sum(x is not None for x in results) == 1
    assert state(game).sheets["2"].permissions == 2


def test_immutable_history_rebuild_and_real_backup_restore(ledger, tmp_path):
    from girlframe.config import Settings
    from girlframe.database.connection import create_database_engine
    from girlframe.database.maintenance import copy_database
    from girlframe.services.onboarding import OnboardingStore

    svc, _ = service(ledger)
    identity, rev = launched(svc)
    svc.end(ADMIN, "end", identity, rev, True)
    saved = svc.get(ADMIN, identity)
    for name in ("m3_mission_history", "m3_required_work"):
        with ledger.transaction() as c:
            with pytest.raises(IntegrityError):
                c.execute(t.m3[name].delete())
    with ledger.transaction() as c:
        c.execute(
            t.m3["m3_missions"]
            .update()
            .where(
                t.m3["m3_missions"].c.campaign_id == ledger.campaign_id,
                t.m3["m3_missions"].c.id == identity,
            )
            .values(body_json=rules_dump(saved["mission"] | {"objective": "WRONG"}))
        )
    assert svc.rebuild() == 1 and svc.get(ADMIN, identity) == saved
    backup = tmp_path / "mission-backup.db"
    copy_database(Path(ledger.engine.url.database), backup)
    engine = create_database_engine(Settings(database_url="sqlite:///" + str(backup)))
    try:
        restored = MissionService(OnboardingStore(engine, ledger.policy), svc.access.registry)
        assert restored.get(ADMIN, identity) == saved
    finally:
        engine.dispose()


def rules_dump(value):
    return json.dumps(value)


def test_inbox_exposes_absent_dogs_work_without_the_private_mission_objective(ledger):
    from girlframe.services.inbox import InboxService

    svc, _ = service(ledger)
    identity, rev = launched(svc)
    inbox = InboxService(ledger)
    offer = inbox.page(PLAYER, category="missions")
    assert offer.item.task == "m3_mission"
    svc.end(ADMIN, "end", identity, rev, True)
    absent = inbox.page(OTHER, category="missions")
    assert absent.total == 1 and absent.item.source == "mission_work"
    assert "PRIVATE_OBJECTIVE" not in str(absent)
    assert len(svc.owned_work(OTHER)) == 1
    with pytest.raises(WorkflowError):
        svc.get(OTHER, identity)


def test_0012_preserves_populated_0011_and_does_not_activate_m3(ledger, monkeypatch):
    from alembic import command
    from alembic.config import Config
    from test_m2_game import start

    svc, game = service(ledger)
    action = start(game)
    ledger.roll_basic(PLAYER, "synthetic-raw-roll", ledger.status(PLAYER)["revision"])
    config = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
    # Only the three empty new tables are removed, on a synthetic disposable DB.
    command.downgrade(config, "0011")

    def snapshot():
        with ledger.engine.connect() as c:
            names = set(sa.inspect(c).get_table_names()) - {"alembic_version"}
            return {
                name: sorted(
                    tuple(row) for row in c.execute(sa.text('SELECT * FROM "' + name + '"'))
                )
                for name in names
            }

    before = snapshot()
    assert len(before) == 31 and before["m2_actions"] and before["roll_receipts"]
    disabled = ledger.policy.model_copy(update={"m3_approval": None, "owner_m3_rulings": None})
    ledger.policy = disabled
    monkeypatch.setenv("GIRLFRAME_RULES_REGISTRY", "/nonexistent/disabled-m3-registry.json")
    command.upgrade(config, "head")
    command.check(config)
    after = snapshot()
    assert len(after) == 36 and {name: after[name] for name in before} == before
    assert all(after[name] == [] for name in set(after) - set(before))
    assert game.inspect(PLAYER, action)["id"] == action
    assert MissionService(ledger).access.registry is None
    with pytest.raises(WorkflowError, match="M3_REVIEW_PENDING"):
        svc.offer(ADMIN, "not-released", "Not implicitly enabled by migration", (2,))
    with ledger.engine.connect() as c:
        assert c.scalar(sa.text("PRAGMA integrity_check")) == "ok"
        assert c.execute(sa.text("PRAGMA foreign_key_check")).all() == []
