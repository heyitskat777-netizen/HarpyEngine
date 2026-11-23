"""Process-isolated, synthetic recovery using the shipped CLI and service boundaries."""

import hashlib
import json
import os
import sqlite3
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing, contextmanager
from pathlib import Path
from threading import Barrier
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from test_director_activity_scene import (
    activity_adapter,
    adapter,
    add_scene,
    input_command,
    launch_opening,
)
from test_ledger import ADMIN, OTHER, PLAYER, FixedDice, revision, seed
from test_m2_game import Dice, answer, setup_game, state, tick

from girlframe.ai.observation import ObservationPolicy
from girlframe.config import Settings
from girlframe.database import maintenance
from girlframe.database import tables as t
from girlframe.database.connection import create_database_engine
from girlframe.discord_adapter.config import BotPolicy, load_bot_policy
from girlframe.engine.m2 import ChoiceAnswer, PlayInput
from girlframe.services.director_observation import DirectorObservationService
from girlframe.services.ledger import CampaignLedger
from girlframe.services.m2_game import GameService
from girlframe.services.onboarding import OnboardingStore, WorkflowError
from girlframe.services.read_only_bot import GuildViewer

REPO = Path(__file__).resolve().parents[1]
REVOKED = GuildViewer(4, 200, True, False)
OUTSIDE_GUILD = GuildViewer(2, 300, True, True)
REPORT = "RECOVERY_APPROVED_CLOSED_REPORT"
DISCOVERY = "RECOVERY_PILOT_PRIVATE_DISCOVERY"
HANDLER = "RECOVERY_HANDLER_BRIEF"
OTHER_FACT = "RECOVERY_OTHER_ONLY_FACT"
SHADOW_FACT = "RECOVERY_SHADOW_HANDLER_FACT"
SHADOW_PRIVATE = "RECOVERY_SHADOW_PILOT_PRIVATE"


def child(repo, db, *args, expected=0):
    # Inherit only the platform basics. Use the selected checkout's code before
    # the installed editable package, and keep the fixture helpers importable.
    allowed = {
        key: os.environ[key]
        for key in ("PATH", "LANG", "LC_ALL", "TZ", "SYSTEMROOT")
        if key in os.environ
    }
    env = allowed | {
        "PYTHONPATH": os.pathsep.join(
            map(str, (repo / "src", repo / "tests", repo / "tests/rules"))
        ),
        "GIRLFRAME_DATABASE_URL": f"sqlite:///{db}",
    }
    argv = list(map(str, args))
    if argv[0] == __file__:
        argv = [
            "-c",
            "import runpy, sys\n"
            "sys.argv = sys.argv[1:]\n"
            "runpy.run_path(sys.argv[0], run_name='__main__')",
            *argv,
        ]
    result = subprocess.run(
        [sys.executable, *argv],
        cwd=repo,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == expected, (result.returncode, result.stdout, result.stderr)
    return result.stdout


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fingerprint(db):
    with closing(sqlite3.connect(db.as_uri() + "?mode=ro", uri=True)) as conn:
        assert conn.execute("PRAGMA integrity_check").fetchall() == [("ok",)]
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
        schema = conn.execute(
            "SELECT type,name,sql FROM sqlite_schema ORDER BY type,name"
        ).fetchall()
        tables = {}
        for kind, table, _ in schema:
            if kind == "table":
                name = table.replace('"', '""')
                tables[table] = sorted(
                    json.dumps(row) for row in conn.execute(f'SELECT * FROM "{name}"')
                )
        return hashlib.sha256(json.dumps([schema, tables], sort_keys=True).encode()).hexdigest()


def append(app, viewer, scene, key, text, channel="comms"):
    return app.submit(
        viewer, scene, input_command(app.session.observer, viewer, scene, key, text, channel)
    )["input"]


def seed_candidate(ledger, manifest):
    game, worker, gateway, _ = setup_game(ledger)
    seed(ledger, REVOKED, callsign="SYNTH_REVOKED", notes="RECOVERY_REVOKED_NOTE")
    retired = ledger.roll_basic(REVOKED, "revoked-roll", revision(ledger))
    private = ledger.roll_basic(PLAYER, "private-recovery-roll", revision(ledger))
    # Simulate a membership revocation already recorded at the backup boundary.
    with ledger.transaction() as c:
        c.execute(
            t.members.update()
            .where(
                t.members.c.campaign_id == ledger.campaign_id,
                t.members.c.user_id == str(REVOKED.user_id),
            )
            .values(active=False)
        )
    observer = DirectorObservationService(ledger, synthetic=True)
    observer.game = game
    app, _ = adapter(observer)
    game.leave_scene(OTHER, "other-leaves-origin", 900)
    with ledger.engine.connect() as c:
        origin = game.scene(c, 900)["id"]
    observer.configure_scene(ADMIN, "notice-origin", origin, 0, ObservationPolicy(mode="shadow"))
    for viewer in (ADMIN, PLAYER):
        observer.set_consent(viewer, f"consent-origin-{viewer.user_id}", origin, 1, consent=True)
    with ledger.engine.connect() as c:
        pilot = observer._authorize_input(c, PLAYER, origin, "pilot")[2]
    report = append(app, PLAYER, origin, "origin-report", REPORT)
    append(app, PLAYER, origin, "origin-private", DISCOVERY, "private")
    ref = app.session.context.record(
        ADMIN,
        "record-closeout",
        origin,
        report["source_id"],
        0,
        known_by=(pilot,),
        topic="tactical",
    )["id"]
    app.close(
        ADMIN, "close-origin", origin, 900, observer.status(ADMIN, origin).scene_revision, (ref,)
    )
    scene = add_scene(observer, 901, (ADMIN, OTHER))
    with ledger.engine.connect() as c:
        handler = observer._authorize_input(c, ADMIN, scene, "handler")[2]
        other = observer._authorize_input(c, OTHER, scene, "pilot")[2]
    launch_opening(
        app,
        scene,
        facts=[
            {"text": HANDLER, "learned_from": "Approved briefing", "known_by": [handler.token]},
            {"text": OTHER_FACT, "learned_from": "Private note", "known_by": [other.token]},
        ],
    )
    blocked = add_scene(observer, 902, (ADMIN,))
    pending_before_withdrawal = input_command(
        observer, ADMIN, blocked, "withdrawn-handler-input", "RECOVERY_WITHDRAWN_TEXT", "private"
    ).model_copy(update={"speaker": "handler"})
    app.submit(ADMIN, blocked, pending_before_withdrawal)
    observer.set_consent(ADMIN, "withdraw-blocked", blocked, 1, consent=False)

    action = game.begin(
        OTHER,
        "recovery-play",
        901,
        state(game).sheets["3"].revision,
        PlayInput(
            play="keep_your_head",
            context="Synthetic relay check",
            trigger_confirmed=True,
            heat=0,
        ),
    )["action_id"]
    tick(worker, gateway)
    for viewer in (ADMIN, OTHER):
        answer(game, viewer, "tag_window", options=("pass",))
    choice = next(x for x in game.choices(OTHER) if x["kind"] == "actor_keep")
    value = {
        "scene": scene,
        "origin": origin,
        "blocked": blocked,
        "action": action,
        "choice": choice["id"],
        "revision": choice["revision"],
        "private_roll": private.id,
        "revoked_roll": retired.id,
    }
    manifest.write_text(json.dumps(value), encoding="utf-8")


def check_views(store, facts, *, resolved=False):
    ledger = CampaignLedger(store, dice=FixedDice())
    game = GameService(ledger, dice=Dice())
    observer = DirectorObservationService(ledger, synthetic=True)
    observer.game = game
    app, _ = adapter(observer)
    scene, origin = facts["scene"], facts["origin"]
    assert ledger.draft(PLAYER)["notes"] == "OWNER_PROFILE_SECRET"
    assert "OWNER_PROFILE_SECRET" not in json.dumps(ledger.draft(OTHER, PLAYER.user_id))
    assert "RECOVERY_REVOKED_NOTE" not in json.dumps(ledger.public_export())
    assert "OWNER_PROFILE_SECRET" not in json.dumps(ledger.public_export())
    assert "OWNER_PROFILE_SECRET" not in json.dumps(ledger.list_events(OTHER))
    assert ledger.get_roll_receipt(PLAYER, facts["private_roll"]).id == facts["private_roll"]
    for actor in (OTHER, ADMIN, OUTSIDE_GUILD):
        with pytest.raises(WorkflowError):
            ledger.get_roll_receipt(actor, facts["private_roll"])
    with pytest.raises(WorkflowError):
        ledger.roll_basic(REVOKED, "revoked-roll", -1)
    with pytest.raises(WorkflowError):
        ledger.get_roll_receipt(REVOKED, facts["revoked_roll"])
    with pytest.raises(WorkflowError):
        ledger.draft(REVOKED)
    with pytest.raises(WorkflowError):
        app.timeline(OTHER, origin)
    assert DISCOVERY in json.dumps(app.timeline(PLAYER, origin))
    assert DISCOVERY not in json.dumps(app.timeline(ADMIN, origin))
    assert not app.timeline(PLAYER, origin)["open"]
    reports = json.dumps(app.read(ADMIN, scene, "reports"))
    assert REPORT in reports and DISCOVERY not in reports
    with pytest.raises(WorkflowError):
        app.read(OTHER, scene, "reports")
    handler, pilot = (app.read(viewer, scene, "opening-brief") for viewer in (ADMIN, OTHER))
    assert HANDLER in json.dumps(handler) and OTHER_FACT not in json.dumps(handler)
    assert OTHER_FACT in json.dumps(pilot) and HANDLER not in json.dumps(pilot)
    assert "GM_ONLY_MAINTENANCE_PLAN" not in json.dumps((handler, pilot))
    with pytest.raises(WorkflowError):
        app.read(REVOKED, scene, "opening-brief")
    assert app.timeline(OTHER, scene)["open"]
    assert observer.status(OTHER, scene).consented
    assert not observer.status(ADMIN, facts["blocked"]).consented
    with pytest.raises(WorkflowError):
        app.timeline(ADMIN, facts["blocked"])
    assert "3" in state(game).sheets
    action = game.inspect(OTHER, facts["action"])
    assert action["receipt"]
    assert (facts["choice"] in {x["id"] for x in game.choices(OTHER)}) is not resolved
    with pytest.raises(WorkflowError):
        respond(game, ADMIN, facts, "wrong-owner-recovery")
    with pytest.raises(WorkflowError):
        respond(game, REVOKED, facts, "revoked-recovery")
    assert game.dice.calls == 0
    return game


def respond(game, viewer, facts, key="recovery-answer"):
    return game.respond(
        viewer,
        key,
        facts["choice"],
        facts["revision"],
        ChoiceAnswer(options=("tough", "in_control"), denied=("desperate",)),
    )


def seed_shadow(store, facts, manifest):
    game = GameService(store)
    app = activity_adapter.local_fixture_director(game, activity_shadow=True)
    observer = app.session.observer
    game.bind_scene(ADMIN, "shadow-bind", 903)
    for viewer in (ADMIN, PLAYER):
        game.join_scene(viewer, f"shadow-join:{viewer.user_id}", 903)
    with store.engine.connect() as c:
        scene = game.scene(c, 903)["id"]
    app.write(
        ADMIN, "shadow-opt-in", scene, "activity-policy-save", {"enabled": True, "revision": 0}
    )
    observer.configure_scene(
        ADMIN, "shadow-notice", scene, 0, ObservationPolicy(mode="shadow", quiet_seconds=1)
    )
    for viewer in (ADMIN, PLAYER):
        observer.set_consent(viewer, f"shadow-consent:{viewer.user_id}", scene, 1, consent=True)
    with store.engine.connect() as c:
        handler = observer._authorize_input(c, ADMIN, scene, "handler")[2]
    # Existing fixture helper uses globally distinct command keys in a single scene.
    draft = {
        "location": "Shadow recovery lab",
        "situation": "A relay needs review.",
        "first_choice": "Check the relay?",
        "facts": [
            {"text": SHADOW_FACT, "learned_from": "Approved briefing", "known_by": [handler.token]}
        ],
    }
    app.write(
        ADMIN, "recovery-shadow-draft", scene, "opening-save", {"revision": 0, "draft": draft}
    )
    reviewed = app.read(ADMIN, scene, "opening")["review"]
    app.write(ADMIN, "recovery-shadow-launch", scene, "opening-launch", {"review": reviewed})
    append(app, PLAYER, scene, "shadow-private", SHADOW_PRIVATE, "private")
    append(app, PLAYER, scene, "shadow-question", "Handler, what is in scope?")
    now = store.clock()
    store.clock = lambda: now + 3
    assert (
        app.write(ADMIN, "shadow-review", scene, "activity-review-run", {})["batch"]["frontier"]
        == 2
    )
    manifest.write_text(json.dumps(facts | {"shadow_scene": scene}), encoding="utf-8")


def check_shadow(store, facts):
    app = activity_adapter.local_fixture_director(GameService(store), activity_shadow=True)
    scene = facts["shadow_scene"]
    assert app.read(ADMIN, scene, "activity-policy")["enabled"]
    assert app.read(ADMIN, scene, "status")["reviewed_sequence"] == 2
    review = json.dumps(app.read(ADMIN, scene, "activity-review"))
    assert SHADOW_FACT in review and SHADOW_PRIVATE not in review
    assert SHADOW_PRIVATE in json.dumps(app.timeline(PLAYER, scene))
    assert SHADOW_PRIVATE not in json.dumps(app.timeline(ADMIN, scene))
    with pytest.raises(WorkflowError):
        app.read(PLAYER, scene, "activity-review")
    with pytest.raises(WorkflowError):
        app.timeline(REVOKED, scene)
    assert app.write(ADMIN, "review-on-restart", scene, "activity-review-run", {}) == {
        "batch": None
    }


def probe(mode, policy_path, manifest):
    settings = Settings(database_url=os.environ["GIRLFRAME_DATABASE_URL"])
    if mode == "seed":
        command.upgrade(Config(str(Path.cwd() / "alembic.ini")), "head")
    engine = create_database_engine(settings)
    policy = (
        BotPolicy(
            application_id=100,
            guild_id=200,
            campaign_id=uuid4(),
            sandbox=policy_path.parent,
            allow_guild_administrators=True,
            status_audience_approved=True,
        )
        if mode == "seed"
        else load_bot_policy(policy_path)
    )
    store = OnboardingStore(engine, policy)
    try:
        if mode == "seed":
            # The fixture's trusted rules are part of the pinned checkpoint.
            ledger = CampaignLedger(store, dice=FixedDice())
            seed_candidate(ledger, manifest)
            policy_path.write_text(ledger.policy.model_dump_json(), encoding="utf-8")
            policy_path.chmod(0o600)
            return
        facts = json.loads(manifest.read_text(encoding="utf-8"))
        game = check_views(store, facts, resolved=mode == "resolved")
        if mode == "verify-shadow":
            check_shadow(store, facts)
        elif mode == "seed-shadow":
            seed_shadow(store, facts, manifest)
        elif mode == "interrupted-write":
            original = game.store.transaction

            @contextmanager
            def stop_before_commit():
                with original() as c:
                    yield c
                    os._exit(76)

            game.store.transaction = stop_before_commit
            respond(game, OTHER, facts)
            raise AssertionError("Expected the write to stop before commit")
        elif mode == "answer":
            receipt = respond(game, OTHER, facts)
            before = revision(CampaignLedger(store))
            assert respond(game, OTHER, facts) == receipt
            assert revision(CampaignLedger(store)) == before and game.dice.calls == 0
        elif mode == "resolved":
            before = revision(CampaignLedger(store))
            assert respond(game, OTHER, facts)["action_id"] == facts["action"]
            assert revision(CampaignLedger(store)) == before
    finally:
        engine.dispose()


def test_release_candidate_backup_restore_restart_and_rollback(tmp_path):
    pinned = Path(os.environ.get("HARPY_RECOVERY_PINNED_CHECKOUT", str(REPO))).resolve()
    seed_dir, restored_dir = tmp_path / "pinned-source", tmp_path / "clean-environment"
    seed_dir.mkdir()
    restored_dir.mkdir()
    policy, manifest = seed_dir / "policy.json", tmp_path / "synthetic-identities.json"
    source = seed_dir / "campaign.sqlite"
    child(pinned, source, __file__, "seed", policy, manifest)
    baseline = fingerprint(source)
    backup = tmp_path / "snapshots" / "pinned.sqlite"
    child(REPO, source, "-m", "girlframe", "db", "backup", "--dest", backup)
    assert fingerprint(backup) == baseline and backup.stat().st_mode & 0o777 == 0o600
    backup_sha = digest(backup)
    copied_policy = restored_dir / "policy.json"
    copied_policy.write_bytes(policy.read_bytes())
    copied_policy.chmod(0o600)
    forward = restored_dir / "campaign.sqlite"
    child(REPO, forward, "-m", "girlframe", "db", "restore", "--source", backup, "--dest", forward)
    exact = fingerprint(forward)
    assert exact == baseline
    child(
        REPO,
        forward,
        "-m",
        "girlframe",
        "db",
        "restore",
        "--source",
        backup,
        "--dest",
        forward,
        expected=1,
    )
    child(REPO, forward, __file__, "verify", copied_policy, manifest)
    child(REPO, forward, __file__, "interrupted-write", copied_policy, manifest, expected=76)
    assert fingerprint(forward) == exact
    child(REPO, forward, __file__, "seed-shadow", copied_policy, manifest)
    forward_snapshot = backup.parent / "shadow.sqlite"
    child(REPO, forward, "-m", "girlframe", "db", "backup", "--dest", forward_snapshot)
    shadow_sha = digest(forward_snapshot)
    recovered = tmp_path / "clean-shadow" / "campaign.sqlite"
    child(
        REPO,
        recovered,
        "-m",
        "girlframe",
        "db",
        "restore",
        "--source",
        forward_snapshot,
        "--dest",
        recovered,
    )
    assert fingerprint(forward_snapshot) == fingerprint(recovered)
    child(REPO, recovered, __file__, "verify-shadow", copied_policy, manifest)
    child(REPO, recovered, __file__, "answer", copied_policy, manifest)
    child(REPO, recovered, __file__, "resolved", copied_policy, manifest)
    rolled_back = tmp_path / "rollback-pinned" / "campaign.sqlite"
    child(
        pinned,
        rolled_back,
        "-m",
        "girlframe",
        "db",
        "restore",
        "--source",
        backup,
        "--dest",
        rolled_back,
    )
    child(pinned, rolled_back, __file__, "verify", copied_policy, manifest)
    assert fingerprint(rolled_back) == baseline and fingerprint(source) == baseline
    assert digest(backup) == backup_sha and digest(forward_snapshot) == shadow_sha


def test_interruption_before_backup_verification_leaves_no_published_file(tmp_path):
    source, target = tmp_path / "source.sqlite", tmp_path / "candidate.sqlite"
    child(REPO, source, "-m", "alembic", "upgrade", "head")
    program = """import os, sys
from pathlib import Path
from girlframe.database import maintenance
maintenance._verify = lambda _connection: os._exit(79)
maintenance.copy_database(Path(sys.argv[1]), Path(sys.argv[2]))
"""
    child(REPO, source, "-c", program, source, target, expected=79)
    assert not target.exists()
    (staged,) = tmp_path.glob(".harpy-db-*.pending")
    assert staged.stat().st_mode & 0o777 == 0o600
    maintenance.copy_database(source, target)
    assert fingerprint(source) == fingerprint(target) and staged.is_file()


def test_populated_pre_observation_checkpoint_upgrades_on_restore(tmp_path):
    source, backup, restored = (
        tmp_path / name for name in ("0021.sqlite", "original.sqlite", "upgraded.sqlite")
    )
    child(REPO, source, "-m", "alembic", "upgrade", "0021")
    with closing(sqlite3.connect(source)) as conn, conn:
        conn.execute(
            "INSERT INTO campaigns(id,guild_id,name) VALUES ('synthetic','200','Recovery marker')"
        )
    baseline = fingerprint(source)
    child(REPO, source, "-m", "girlframe", "db", "backup", "--dest", backup)
    child(
        REPO, restored, "-m", "girlframe", "db", "restore", "--source", backup, "--dest", restored
    )
    assert fingerprint(restored) == baseline
    child(REPO, restored, "-m", "alembic", "upgrade", "head")
    upgraded = fingerprint(restored)
    child(REPO, restored, "-m", "alembic", "upgrade", "head")
    child(REPO, restored, "-m", "alembic", "check")
    with closing(sqlite3.connect(restored)) as conn:
        assert conn.execute("SELECT name FROM campaigns WHERE id='synthetic'").fetchone() == (
            "Recovery marker",
        )
        assert conn.execute("SELECT version_num FROM alembic_version").fetchone() == ("0023",)
    assert fingerprint(restored) == upgraded
    assert fingerprint(source) == fingerprint(backup) == baseline


def test_concurrent_backup_requests_cannot_replace_winner(tmp_path, monkeypatch):
    source, target = tmp_path / "source.sqlite", tmp_path / "winner.sqlite"
    child(REPO, source, "-m", "alembic", "upgrade", "head")
    barrier = Barrier(2)
    verify = maintenance._verify

    def verify_then_wait(connection):
        verify(connection)
        barrier.wait(timeout=10)

    monkeypatch.setattr(maintenance, "_verify", verify_then_wait)

    def attempt():
        try:
            maintenance.copy_database(source, target)
        except FileExistsError:
            return "existing"
        return "published"

    with ThreadPoolExecutor(2) as pool:
        assert sorted(pool.map(lambda _: attempt(), range(2))) == ["existing", "published"]
    assert fingerprint(target) == fingerprint(source)


if __name__ == "__main__":
    probe(sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3]))
