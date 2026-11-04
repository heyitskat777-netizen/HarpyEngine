from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from sqlalchemy.exc import IntegrityError
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger_fixture
from test_m2_game import state
from test_mission_service import launched, service

from girlframe.database import tables as t
from girlframe.services.m3_off_duty import OffDutyService
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer

ledger = ledger_fixture


def ready(store, frame="JANUS-B"):
    missions, game = service(store, frame=frame)
    return OffDutyService(missions), game


def enable_credit(store):
    approval = store.policy.m3_approval
    store.policy = store.policy.model_copy(
        update={
            "m3_approval": approval.model_copy(
                update={"subsystems": approval.subsystems | {"playbooks"}}
            )
        }
    )


def test_start_is_private_durable_and_requires_actual_preparation_not_a_waiver(ledger):
    svc, _ = ready(ledger)
    started = svc.begin(ADMIN, "begin-off-duty")
    assert started["phase"] == "preparing"
    restarted = OffDutyService(svc.missions)
    assert restarted.begin(ADMIN, "begin-off-duty") == started
    assert svc.get(PLAYER, started["id"])["pending_count"] == 3
    assert svc.get(PLAYER, started["id"])["work"] == []
    assert {x["kind"] for x in svc.get(ADMIN, started["id"])["work"]} == {
        "off_duty_strain_start",
        "off_duty_handler_scene",
        "off_duty_status_review",
    }
    with pytest.raises(WorkflowError, match="existing Off-Duty"):
        restarted.begin(ADMIN, "new-key")
    with pytest.raises(WorkflowError, match="Off-Duty"):
        svc.missions.offer(ADMIN, "new-mission", "No phase bypass", (2,))
    outsider = GuildViewer(4, 200, True, True)
    ledger.join(outsider, "join-admin")
    with pytest.raises(WorkflowError, match="private"):
        svc.get(outsider, started["id"])
    assert not hasattr(svc, "activate") and not hasattr(svc, "resolve_work")


def test_mission_and_pause_prevent_period_start_and_player_cannot_advance_handler(ledger):
    svc, _ = ready(ledger)
    with pytest.raises(WorkflowError):
        svc.begin(PLAYER, "player-start")
    launched(svc.missions)
    with pytest.raises(WorkflowError, match="mission work"):
        svc.begin(ADMIN, "during-mission")
    ledger.safety(OTHER, "pause", ledger.status(OTHER)["revision"], pause=True)
    with pytest.raises(WorkflowError, match="SAFETY_PAUSED"):
        svc.begin(ADMIN, "paused")


def test_doctor_credit_is_owner_declared_exactly_once_private_and_restart_safe(ledger):
    svc, game = ready(ledger, "DOCTORDOCTOR MK. II")
    enable_credit(ledger)
    started = svc.begin(ADMIN, "begin")
    rev = state(game).revision
    with pytest.raises(WorkflowError):
        svc.credit(ADMIN, "not-owner", started["id"], 1, rev, 3, "Not my declaration")
    with pytest.raises(WorkflowError, match="another current"):
        svc.credit(PLAYER, "handler-recipient", started["id"], 1, rev, 1, "No NPC credit")
    result = svc.credit(PLAYER, "credit", started["id"], 1, rev, 3, "PRIVATE_CREDIT_ACCOUNT")
    assert state(game).sheets["3"].permissions == 1
    restarted = OffDutyService(svc.missions)
    assert (
        restarted.credit(PLAYER, "credit", started["id"], 1, rev, 3, "PRIVATE_CREDIT_ACCOUNT")
        == result
    )
    assert svc.get(OTHER, started["id"])["work"] == []
    with pytest.raises(WorkflowError):
        svc.credit(PLAYER, "again", started["id"], 2, state(game).revision, 3, "Again")
    with ledger.engine.connect() as c:
        assert "PRIVATE_CREDIT_ACCOUNT" not in str(
            list(c.scalars(sa.select(t.events.c.payload_json)))
        )
        assert "PRIVATE_CREDIT_ACCOUNT" not in str(
            list(c.scalars(sa.select(t.commands.c.outcome_json)))
        )
        rows = list(c.execute(sa.select(t.m3["m3_required_work"])).mappings())
        assert all(
            row["mission_id"] is None and row["off_duty_id"] == started["id"] for row in rows
        )


def test_credit_failure_rolls_back_permission_work_history_and_retry(ledger, monkeypatch):
    svc, game = ready(ledger, "DOCTORDOCTOR MK. II")
    enable_credit(ledger)
    started = svc.begin(ADMIN, "begin")
    revision = state(game).revision
    original = svc._save

    def fail(*args):
        raise RuntimeError("synthetic write failure")

    monkeypatch.setattr(svc, "_save", fail)
    with pytest.raises(RuntimeError):
        svc.credit(PLAYER, "credit", started["id"], 1, revision, 3, "Shared credit")
    assert state(game).sheets["3"].permissions == 0
    assert svc.get(PLAYER, started["id"])["revision"] == 1
    monkeypatch.setattr(svc, "_save", original)
    svc.credit(PLAYER, "credit", started["id"], 1, revision, 3, "Shared credit")
    assert state(game).sheets["3"].permissions == 1


def test_concurrent_credit_cannot_grant_twice(ledger):
    svc, game = ready(ledger, "DOCTORDOCTOR MK. II")
    enable_credit(ledger)
    started = svc.begin(ADMIN, "begin")
    revision = state(game).revision

    def attempt(key):
        try:
            return svc.credit(PLAYER, key, started["id"], 1, revision, 3, "Shared credit")
        except WorkflowError:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(attempt, ("a", "b")))
    assert sum(x is not None for x in results) == 1
    assert state(game).sheets["3"].permissions == 1


def test_off_duty_history_is_immutable_rebuildable_and_in_real_backup(ledger, tmp_path):
    from girlframe.config import Settings
    from girlframe.database.connection import create_database_engine
    from girlframe.database.maintenance import copy_database
    from girlframe.services.m3_missions import MissionService
    from girlframe.services.onboarding import OnboardingStore

    svc, _ = ready(ledger)
    started = svc.begin(ADMIN, "begin")
    saved = svc.get(ADMIN, started["id"])
    for name in ("m3_off_duty_history", "m3_required_work"):
        with ledger.transaction() as c:
            with pytest.raises(IntegrityError):
                c.execute(t.m3[name].delete())
    with ledger.transaction() as c:
        c.execute(t.m3["m3_off_duty"].update().values(phase="WRONG", body_json="{}"))
    assert svc.rebuild() == 1 and svc.get(ADMIN, started["id"]) == saved
    backup = tmp_path / "backup.db"
    copy_database(Path(ledger.engine.url.database), backup)
    engine = create_database_engine(Settings(database_url="sqlite:///" + str(backup)))
    try:
        restored = OffDutyService(
            MissionService(OnboardingStore(engine, ledger.policy), svc.missions.access.registry)
        )
        assert restored.get(ADMIN, started["id"]) == saved
    finally:
        engine.dispose()


def test_work_context_is_required_exclusive_and_bound_to_campaign(ledger):
    svc, _ = ready(ledger)
    started = svc.begin(ADMIN, "begin")
    with ledger.engine.connect() as c:
        row = dict(c.execute(sa.select(t.m3["m3_required_work"])).mappings().first())
    for updates in (
        {"off_duty_id": None},
        {"mission_id": "also-mission"},
        {"off_duty_id": str(uuid4())},
    ):
        with ledger.transaction() as c:
            with pytest.raises(IntegrityError):
                c.execute(
                    t.m3["m3_required_work"]
                    .insert()
                    .values(**(row | {"id": str(uuid4())} | updates))
                )
    assert svc.get(ADMIN, started["id"])["pending_count"] == 3


def test_0013_preserves_existing_mission_work_and_append_only_triggers(ledger):
    missions, game = service(ledger)
    identity, revision = launched(missions)
    missions.end(ADMIN, "end", identity, revision, True)
    config = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
    command.downgrade(config, "0012")
    with ledger.engine.connect() as c:
        names = set(sa.inspect(c).get_table_names()) - {"alembic_version"}
        columns = {name: [x["name"] for x in sa.inspect(c).get_columns(name)] for name in names}
        before = {name: list(c.execute(sa.text('SELECT * FROM "' + name + '"'))) for name in names}
    assert len(before) == 34 and before["m3_required_work"]
    command.upgrade(config, "head")
    command.check(config)
    with ledger.engine.connect() as c:
        for name in names:
            quoted = ", ".join('"' + column + '"' for column in columns[name])
            assert (
                list(c.execute(sa.text("SELECT " + quoted + ' FROM "' + name + '"')))
                == before[name]
            )
        assert c.scalar(sa.text("PRAGMA integrity_check")) == "ok"
        assert c.execute(sa.text("PRAGMA foreign_key_check")).all() == []
    with ledger.transaction() as c:
        with pytest.raises(IntegrityError):
            c.execute(t.m3["m3_required_work"].update().values(state="resolved"))
    assert state(game).sheets["2"].permissions == 2
