"""Synthetic Activity batching with real scene/Play sources; no inference or publication."""

import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from uuid import uuid4

import pytest
import sqlalchemy as sa
from alembic import command as alembic
from alembic.config import Config
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from test_ledger import ADMIN, OTHER, PLAYER, ROOT
from test_ledger import ledger as ledger
from test_m2_game import answer, pass_tags, setup_game, start, state, tick

from girlframe.ai.observation import AppendSceneInput, ObservationPolicy
from girlframe.config import Settings
from girlframe.database import tables as t
from girlframe.database.connection import create_database_engine
from girlframe.services.director_observation import DirectorObservationService
from girlframe.services.m3_work import related
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer


class Clock:
    now = 1000.0

    def __call__(self):
        return self.now


@pytest.fixture
def observed(ledger):
    game, worker, gateway, dice = setup_game(ledger)
    clock = Clock()
    ledger.clock = clock
    with ledger.engine.connect() as c:
        scene = game.scene(c, 900)["id"]
    service = DirectorObservationService(ledger, synthetic=True)
    service.configure_scene(ADMIN, "observe-config", scene, 0, ObservationPolicy(mode="shadow"))
    for viewer in (ADMIN, PLAYER, OTHER):
        service.set_consent(viewer, "consent:" + str(viewer.user_id), scene, 1, consent=True)
    return service, scene, clock, game, worker, gateway, dice


def send(service, scene, key, text="SYNTHETIC_SCENE_INPUT", viewer=PLAYER, **changes):
    values = dict(
        command_key=key,
        expected_scene_revision=service.status(viewer, scene).scene_revision,
        speaker="handler" if viewer == ADMIN else "pilot",
        text=text,
    )
    values.update(changes)
    request = AppendSceneInput(**values)
    return request, service.append_scene_input(viewer, scene, request)


def snapshots(store):
    with store.engine.connect() as c:
        return {
            name: [tuple(row) for row in c.execute(sa.select(table))]
            for name, table in t.metadata.tables.items()
        }


def test_quiet_batch_replay_concurrent_claim_ack_and_restart_without_effects(observed):
    service, scene, clock, game, _, _, dice = observed
    before = snapshots(service.store)
    request, first = send(service, scene, "message:1")
    clock.now += 40
    send(service, scene, "message:2", viewer=OTHER)
    clock.now += 30
    send(service, scene, "message:3")
    clock.now += 119
    assert service.append_scene_input(PLAYER, scene, request) == first
    assert service.claim_review(scene) is None
    assert service.status(PLAYER, scene).next_review_at == 1190.0
    clock.now += 1
    other_worker = DirectorObservationService(service.store, synthetic=True)
    with ThreadPoolExecutor(max_workers=2) as pool:
        claims = list(
            pool.map(lambda observer: observer.claim_review(scene), [service, other_worker])
        )
    batch = next(x for x in claims if x is not None)
    assert sum(x is not None for x in claims) == 1
    assert batch.reason == "quiet" and len(batch.inputs) == 3
    assert all(x.actor.entity in {"2", "3"} for x in batch.inputs)
    assert batch.publication == "blocked"
    # Default instance cannot observe merely because synthetic fixtures configured a scene.
    assert DirectorObservationService(service.store).claim_review(scene) is None
    service.store.engine.dispose()
    reopened = DirectorObservationService(service.store, synthetic=True)
    outcome = reopened.acknowledge_review(batch.run_id, batch.lease_token, success=True)
    assert reopened.acknowledge_review(batch.run_id, batch.lease_token, success=True) == outcome
    assert reopened.claim_review(scene) is None
    assert reopened.status(PLAYER, scene).pending_messages == 0
    after = snapshots(service.store)
    for name in before:
        if not name.startswith("director_") and name not in {
            t.events.name,
            t.commands.name,
            t.campaigns.name,
        }:
            assert before[name] == after[name], name
    assert (
        dice.calls == 0 and state(game).revision == json.loads(before["m2_state"][0][2])["revision"]
    )
    with service.store.engine.connect() as c:
        generic = "\n".join(c.scalars(sa.select(t.events.c.payload_json)))
        generic += "\n".join(c.scalars(sa.select(t.commands.c.outcome_json)))
        assert "SYNTHETIC_SCENE_INPUT" not in generic


def test_size_review_splits_without_losing_unread_input_and_bounds_tail(observed):
    service, scene, clock, *_ = observed
    for index in range(21):
        clock.now += 1
        send(service, scene, f"message:{index}")
    batch = service.claim_review(scene)
    assert batch.reason == "size" and len(batch.inputs) == 20
    assert batch.publication == "blocked"
    service.acknowledge_review(batch.run_id, batch.lease_token, success=True)
    assert service.status(PLAYER, scene).pending_messages == 1
    assert service.claim_review(scene) is None
    clock.now += 120
    second = service.claim_review(scene)
    assert second.reason == "quiet" and len(second.inputs) == 1
    assert second.inputs[0].sequence == 21 and len(second.recent_tail) == 3
    service.acknowledge_review(second.run_id, second.lease_token, success=True)
    assert service.claim_review(scene) is None


def test_age_review_during_continuous_conversation_does_not_publish(observed):
    service, scene, clock, *_ = observed
    for index in range(7):
        clock.now = 1000.0 + min(index * 100, 599)
        send(service, scene, f"message:{index}")
    clock.now = 1600.0
    batch = service.claim_review(scene)
    assert batch.reason == "age" and len(batch.inputs) == 7
    assert batch.publication == "blocked" and clock.now < 1599 + 120


def test_permissions_consent_scope_and_unknown_wire_authority_fail_closed(observed):
    service, scene, clock, *_ = observed
    request, _ = send(service, scene, "original")
    for viewer in (replace(PLAYER, guild_id=201), GuildViewer(44, 200, True, True)):
        with pytest.raises(WorkflowError):
            service.status(viewer, scene)
    with pytest.raises(WorkflowError, match="SYNTHETIC_ONLY"):
        DirectorObservationService(service.store).append_scene_input(PLAYER, scene, request)
    with pytest.raises(WorkflowError, match="appointed"):
        service.append_scene_input(PLAYER, scene, request.model_copy(update={"speaker": "handler"}))
    with pytest.raises(ValidationError):
        AppendSceneInput(
            command_key="fake",
            expected_scene_revision=4,
            speaker="pilot",
            text="Synthetic",
            is_administrator=True,
        )
    clock.now += 120
    batch = service.claim_review(scene)
    service.set_consent(OTHER, "withdraw", scene, 1, consent=False)
    with pytest.raises(WorkflowError, match="OBSERVATION_DISABLED"):
        service.append_scene_input(PLAYER, scene, request)
    with pytest.raises(WorkflowError, match="STALE_CLAIM"):
        service.acknowledge_review(batch.run_id, batch.lease_token, success=True)
    assert service.claim_review(scene) is None
    assert service.status(PLAYER, scene).reviewed_sequence == 0


def test_failure_expired_claim_and_new_input_leave_frontier_recoverable(observed):
    service, scene, clock, *_ = observed
    send(service, scene, "first")
    clock.now += 120
    batch = service.claim_review(scene)
    failed = service.acknowledge_review(batch.run_id, batch.lease_token, success=False)
    assert service.acknowledge_review(batch.run_id, batch.lease_token, success=False) == failed
    assert service.status(PLAYER, scene).pending_messages == 1
    retry = service.claim_review(scene)
    clock.now += 120
    with pytest.raises(WorkflowError, match="STALE_CLAIM"):
        service.acknowledge_review(retry.run_id, retry.lease_token, success=True)
    recovered = service.claim_review(scene)
    assert recovered.run_id != retry.run_id
    send(service, scene, "newer")
    with pytest.raises(WorkflowError, match="STALE_CLAIM"):
        service.acknowledge_review(recovered.run_id, recovered.lease_token, success=True)
    assert service.status(PLAYER, scene).pending_messages == 2
    clock.now += 120
    fresh = service.claim_review(scene)
    assert len(fresh.inputs) == 2
    service.acknowledge_review(fresh.run_id, fresh.lease_token, success=True)
    assert service.status(PLAYER, scene).reviewed_sequence == fresh.frontier


def test_owned_edits_invalidate_claims_and_do_not_count_revisions_as_messages(observed):
    service, scene, clock, *_ = observed
    original, outcome = send(service, scene, "initial", text="SYNTHETIC_OLD_CLAIM")
    clock.now += 120
    batch = service.claim_review(scene)
    with pytest.raises(WorkflowError, match="SOURCE_UNAVAILABLE"):
        send(
            service,
            scene,
            "foreign-edit",
            viewer=OTHER,
            source_id=outcome.source_id,
            expected_source_revision=1,
        )
    edit, edited = send(
        service,
        scene,
        "edit",
        text="SYNTHETIC_CORRECTION",
        source_id=outcome.source_id,
        expected_source_revision=1,
    )
    assert edited.source_revision == 2
    assert service.status(PLAYER, scene).pending_messages == 1
    assert service.append_scene_input(PLAYER, scene, original) == outcome
    with pytest.raises(WorkflowError, match="IDEMPOTENCY_CONFLICT"):
        service.append_scene_input(
            PLAYER, scene, edit.model_copy(update={"text": "CHANGED_INTENT"})
        )
    with pytest.raises(WorkflowError, match="STALE_CLAIM"):
        service.acknowledge_review(batch.run_id, batch.lease_token, success=True)
    clock.now += 120
    latest = service.claim_review(scene)
    assert len(latest.inputs) == 1 and latest.inputs[0].text == "SYNTHETIC_CORRECTION"
    assert "SYNTHETIC_OLD_CLAIM" not in latest.model_dump_json()


def test_pause_resume_invalidates_optional_claim_but_ooc_never_enters_batch(observed):
    service, scene, clock, *_ = observed
    before = service.status(PLAYER, scene)
    _, ignored = send(service, scene, "ooc", text="SYNTHETIC_PRIVATE_OOC", classification="ooc")
    assert ignored.status == "ignored_ooc"
    assert service.status(PLAYER, scene).generation == before.generation
    send(service, scene, "ic")
    clock.now += 120
    batch = service.claim_review(scene)
    ledger = service.store
    ledger.safety(PLAYER, "pause", 0, pause=True)
    with pytest.raises(WorkflowError, match="SAFETY_PAUSED"):
        send(service, scene, "paused")
    with pytest.raises(WorkflowError, match="SAFETY_PAUSED"):
        service.claim_review(scene)
    ledger.safety(PLAYER, "resume", ledger.status(ADMIN)["revision"], pause=False)
    with pytest.raises(WorkflowError, match="STALE_CLAIM"):
        service.acknowledge_review(batch.run_id, batch.lease_token, success=True)
    with ledger.engine.connect() as c:
        assert "SYNTHETIC_PRIVATE_OOC" not in "\n".join(
            c.scalars(sa.select(t.director["inputs"].c.body_json))
        )


def complete_keep(game, worker, gateway):
    action = start(game)
    tick(worker, gateway)
    pass_tags(game)
    answer(game, PLAYER, "actor_keep", options=("tough", "in_control"), denied=("desperate",))
    answer(game, ADMIN, "handler_keep", flag=True, text="SYNTHETIC_HANDLER_SECRET")
    assert game.inspect(PLAYER, action)["state"] == "complete"
    return action


def test_real_completed_keep_receipt_triggers_once_without_private_result_or_new_roll(observed):
    service, scene, _, game, worker, gateway, dice = observed
    action = start(game)
    tick(worker, gateway)
    pass_tags(game)
    with pytest.raises(WorkflowError, match="PLAY_PENDING"):
        service.observe_committed_play(scene, action)
    with pytest.raises(WorkflowError, match="SCENE_BUSY"):
        send(service, scene, "locked-ic")
    answer(game, PLAYER, "actor_keep", options=("tough", "in_control"), denied=("desperate",))
    with pytest.raises(WorkflowError, match="PLAY_PENDING"):
        service.observe_committed_play(scene, action)
    answer(game, ADMIN, "handler_keep", flag=True, text="SYNTHETIC_HANDLER_SECRET")
    canonical = state(game).model_dump_json()
    observed_play = service.observe_committed_play(scene, action)
    tick(worker, gateway, 5)
    send(service, scene, "after-play")
    assert service.observe_committed_play(scene, action) == observed_play
    batch = service.claim_review(scene)
    assert batch.reason == "completed_play"
    trigger = next(x for x in batch.inputs if x.kind == "completed_play")
    assert trigger.receipt_id == game.inspect(PLAYER, action)["receipt"]["id"]
    assert trigger.event_id and trigger.action_id == action
    assert "SYNTHETIC_HANDLER_SECRET" not in batch.model_dump_json()
    assert state(game).model_dump_json() == canonical and dice.calls == 1
    service.acknowledge_review(batch.run_id, batch.lease_token, success=True)
    assert service.claim_review(scene) is None


def test_required_work_prevents_a_false_completed_play_trigger(observed):
    service, scene, _, game, worker, gateway, _ = observed
    action = complete_keep(game, worker, gateway)
    with service.store.transaction() as c:
        source = game.action(c, action)["data"]["response_event"]
        related(
            c,
            service.store,
            {"campaign_id": service.store.campaign_id, "scene_id": scene},
            str(uuid4()),
            PLAYER.user_id,
            PLAYER.user_id,
            "synthetic_required_work",
            {},
            source,
        )
    with pytest.raises(WorkflowError, match="PLAY_PENDING"):
        service.observe_committed_play(scene, action)


def test_input_staging_failure_rolls_back_and_journal_is_append_only(observed, monkeypatch):
    service, scene, *_ = observed
    before = snapshots(service.store)
    original = service._save

    def fail(*args):
        original(*args)
        raise RuntimeError("SYNTHETIC_STAGING_FAILURE")

    monkeypatch.setattr(service, "_save", fail)
    with pytest.raises(RuntimeError, match="SYNTHETIC_STAGING_FAILURE"):
        send(service, scene, "atomic")
    assert snapshots(service.store) == before
    monkeypatch.setattr(service, "_save", original)
    send(service, scene, "atomic")
    with service.store.engine.begin() as c:
        with pytest.raises(IntegrityError, match="immutable"):
            c.execute(t.director["inputs"].update().values(body_json="{}"))
    with service.store.engine.begin() as c:
        with pytest.raises(IntegrityError, match="immutable"):
            c.execute(t.director["inputs"].delete())


def test_membership_policy_and_original_scene_binding_invalidate_claims(observed):
    service, scene, clock, game, *_ = observed
    send(service, scene, "initial")
    clock.now += 120
    batch = service.claim_review(scene)
    with service.store.engine.begin() as c:
        c.execute(
            t.members.update()
            .where(
                t.members.c.campaign_id == service.store.campaign_id,
                t.members.c.user_id == str(OTHER.user_id),
            )
            .values(active=False)
        )
    with pytest.raises(WorkflowError, match="STALE_CLAIM"):
        service.acknowledge_review(batch.run_id, batch.lease_token, success=True)
    assert service.claim_review(scene) is None
    service.configure_scene(ADMIN, "off", scene, 1, ObservationPolicy())
    assert service.status(PLAYER, scene).phase == "off"
    with pytest.raises(WorkflowError, match="STALE_CLAIM"):
        service.acknowledge_review(batch.run_id, batch.lease_token, success=True)
    game.close_scene(ADMIN, "close-original", 900)
    game.bind_scene(ADMIN, "rebind", 900)
    with pytest.raises(WorkflowError, match="SCENE_UNAVAILABLE"):
        service.acknowledge_review(batch.run_id, batch.lease_token, success=True)
    with pytest.raises(WorkflowError, match="SCENE_UNAVAILABLE"):
        service.status(PLAYER, scene)
    with service.store.engine.connect() as c:
        assert game.scene(c, 900)["id"] != scene
        assert c.scalar(sa.select(sa.func.count()).select_from(t.director["inputs"])) == 1


def test_populated_0021_upgrade_preserves_existing_rows(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'populated.sqlite'}"
    monkeypatch.setenv("GIRLFRAME_DATABASE_URL", url)
    config = Config(str(ROOT / "alembic.ini"))
    alembic.upgrade(config, "0021")
    engine = create_database_engine(Settings(database_url=url))
    campaign = str(uuid4())
    with engine.begin() as c:
        c.execute(t.campaigns.insert().values(id=campaign, guild_id="200", revision=7))
        c.execute(t.members.insert().values(campaign_id=campaign, user_id="2", role="player"))
        c.execute(
            t.characters.insert().values(
                campaign_id=campaign,
                user_id="2",
                id=str(uuid4()),
                revision=3,
                public_json='{"callsign":"SYNTHETIC_PRESERVED"}',
                private_json='{"notes":"SYNTHETIC_PRIVATE"}',
            )
        )
    names = set(sa.inspect(engine).get_table_names()) - {"alembic_version"}

    def rows():
        with engine.connect() as c:
            return {
                name: [tuple(row) for row in c.execute(sa.select(t.metadata.tables[name]))]
                for name in sorted(names)
            }

    before = rows()
    alembic.upgrade(config, "head")
    assert rows() == before
    with engine.connect() as c:
        assert all(
            c.scalar(sa.select(sa.func.count()).select_from(table)) == 0
            for table in t.director.values()
        )
        assert not list(c.exec_driver_sql("PRAGMA foreign_key_check"))
    engine.dispose()
