from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
import sqlalchemy as sa
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger_fixture
from test_m2_game import state
from test_mission_service import service
from test_strain import facts

from girlframe.database import tables as t
from girlframe.engine.m3_frame_state import Package, Preferences, SuppliedAsset
from girlframe.services.m3_off_duty import OffDutyService
from girlframe.services.m3_replacement import ReplacementService
from girlframe.services.m3_strain import StrainService
from girlframe.services.onboarding import WorkflowError

ledger = ledger_fixture


class D6:
    def __init__(self, face=1):
        self.face, self.calls = face, 0

    def roll_d6(self):
        self.calls += 1
        return self.face


def ready(store, *, frame="JANUS-B", face=1):
    missions, game = service(store, frame=frame)
    approval = store.policy.m3_approval
    store.policy = store.policy.model_copy(
        update={
            "m3_approval": approval.model_copy(
                update={"subsystems": approval.subsystems | {"strain", "playbooks"}}
            )
        }
    )
    return StrainService(OffDutyService(missions), dice=D6(face)), game


def prepared(svc, game, high=frozenset()):
    svc.configure(
        ADMIN,
        "scenario",
        state(game).revision,
        "business_as_usual" if not high else "disaster_management",
        high,
    )
    period = svc.periods.begin(ADMIN, "begin")
    current = state(game)
    void_count = sum(any(a.void for a in sheet.assets) for sheet in current.sheets.values())
    result = svc.prepare(
        ADMIN,
        "prepare",
        period["id"],
        1,
        current.revision,
        facts(
            at_least_half_have_void=2 * void_count >= len(current.order),
            no_girl_void=void_count == 0,
        ),
    )
    return result["id"]


def test_three_real_dice_and_handler_column_choices_are_saved_without_false_effect_completion(
    ledger,
):
    svc, game = ready(ledger)
    identity = prepared(svc, game)
    assert len(state(game).strain.requests) == 3
    for request in tuple(state(game).strain.requests):
        revision = state(game).revision
        rolled = svc.roll(ADMIN, "roll-" + request.track, request.id, 1, revision)
        assert rolled["face"] == 1
        assert svc.roll(ADMIN, "roll-" + request.track, request.id, 1, revision) == rolled
        with pytest.raises(WorkflowError, match="already saved"):
            svc.roll(ADMIN, "reroll-" + request.track, request.id, 2, state(game).revision)
        selected = svc.choose(
            ADMIN, "choice-" + request.track, request.id, 2, state(game).revision, 1
        )
        assert selected["effects_pending"]
    assert svc.dice.calls == 3 and not state(game).strain.requests
    pending = svc.periods._pending
    with ledger.engine.connect() as c:
        work = pending(c, identity)
        assert len([x for x in work if x["kind"] == "strain_event"]) == 3
        assert any(x["kind"] == "off_duty_strain_start" for x in work)
        assert c.scalar(sa.select(sa.func.count()).select_from(t.m3["m3_missions"])) == 0
    assert svc.periods.get(ADMIN, identity)["phase"] == "preparing"
    assert not hasattr(svc, "resolve_work")


def test_severity_facts_cannot_deny_canonical_void_or_damage_and_initialization_is_once(ledger):
    svc, game = ready(ledger)
    svc.configure(ADMIN, "scenario", state(game).revision, "business_as_usual", frozenset())
    with pytest.raises(WorkflowError, match="already recorded"):
        svc.configure(
            ADMIN,
            "reset",
            state(game).revision,
            "falling_apart",
            frozenset({"void", "rebellion", "budget"}),
        )
    period = svc.periods.begin(ADMIN, "begin")
    with pytest.raises(WorkflowError, match="Void trigger"):
        svc.prepare(
            ADMIN, "false-void", period["id"], 1, state(game).revision, facts(no_girl_void=True)
        )
    with ledger.transaction() as c:
        current = state(game)
        for asset in current.sheets["2"].assets:
            if asset.family == "frame":
                asset.damaged = True
        game.event(c, 1, "damage", "synthetic.damage", current)
    with pytest.raises(WorkflowError, match="High Budget"):
        svc.prepare(
            ADMIN,
            "false-budget",
            period["id"],
            1,
            state(game).revision,
            facts(at_least_half_have_void=True),
        )
    with pytest.raises(WorkflowError, match="last mission"):
        svc.prepare(
            ADMIN,
            "false-success",
            period["id"],
            1,
            state(game).revision,
            facts(
                at_least_half_have_void=True,
                frame_full_or_all_frames_some_repairs=True,
                last_mission_success_no_frame_death_infrastructure_loss=True,
            ),
        )


def test_handler_only_scope_pause_and_stale_state_protect_rolls(ledger):
    svc, game = ready(ledger)
    identity = prepared(svc, game)
    request = state(game).strain.requests[0]
    with pytest.raises(WorkflowError):
        svc.get(PLAYER)
    with pytest.raises(WorkflowError):
        svc.roll(PLAYER, "not-handler", request.id, 1, state(game).revision)
    with pytest.raises(WorkflowError, match="STALE_STATE"):
        svc.roll(ADMIN, "stale", request.id, 1, state(game).revision - 1)
    ledger.safety(OTHER, "pause", ledger.status(OTHER)["revision"], pause=True)
    assert svc.get(ADMIN)["strain"]["requests"]
    with pytest.raises(WorkflowError, match="SAFETY_PAUSED"):
        svc.roll(ADMIN, "paused", request.id, 1, state(game).revision)
    assert svc.dice.calls == 0 and svc.periods.get(ADMIN, identity)["phase"] == "preparing"


def test_concurrent_column_selection_schedules_only_one_effect(ledger):
    svc, game = ready(ledger)
    prepared(svc, game)
    request = state(game).strain.requests[0]
    svc.roll(ADMIN, "roll", request.id, 1, state(game).revision)
    revision = state(game).revision

    def attempt(key):
        try:
            return svc.choose(ADMIN, key, request.id, 2, revision, 1)
        except WorkflowError:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(attempt, ("a", "b")))
    assert sum(x is not None for x in results) == 1
    with ledger.engine.connect() as c:
        table = t.m3["m3_required_work"]
        assert (
            c.scalar(
                sa.select(sa.func.count())
                .select_from(table)
                .where(table.c.id == request.id + ":effect")
            )
            == 1
        )


def test_rollback_after_saved_event_restores_strain_and_required_work(ledger, monkeypatch):
    import girlframe.services.m3_strain as module

    svc, game = ready(ledger)
    prepared(svc, game)
    request = state(game).strain.requests[0]
    svc.roll(ADMIN, "roll", request.id, 1, state(game).revision)
    before = state(game)
    original = module.related

    def fail(*args):
        raise RuntimeError("synthetic effect-queue failure")

    monkeypatch.setattr(module, "related", fail)
    with pytest.raises(RuntimeError):
        svc.choose(ADMIN, "choice", request.id, 2, before.revision, 1)
    assert state(game) == before
    monkeypatch.setattr(module, "related", original)
    svc.choose(ADMIN, "choice", request.id, 2, before.revision, 1)
    assert state(game).strain.events[0].column == 1


def test_high_budget_doctor_scrapping_preserves_off_duty_context_through_replacement(ledger):
    svc, game = ready(ledger, frame="DOCTORDOCTOR MK. II")
    with ledger.transaction() as c:
        current = state(game)
        current.sheets["2"].obsolescence_marked = 7
        game.event(c, 1, "seven-boxes", "synthetic.boxes", current)
    svc.configure(
        ADMIN, "scenario", state(game).revision, "disaster_management", frozenset({"budget"})
    )
    period = svc.periods.begin(ADMIN, "begin")
    with pytest.raises(WorkflowError, match="record credit"):
        svc.prepare(
            ADMIN,
            "too-early",
            period["id"],
            1,
            state(game).revision,
            facts(at_least_half_have_void=True),
        )
    declared = svc.periods.credit(
        PLAYER,
        "credit",
        period["id"],
        1,
        state(game).revision,
        3,
        "Credit to another Pilot before Budget review",
    )
    svc.prepare(
        ADMIN,
        "prepare",
        period["id"],
        declared["revision"],
        state(game).revision,
        facts(at_least_half_have_void=True),
    )
    assert state(game).sheets["2"].frame_scrapped
    assert state(game).sheets["3"].permissions == 1
    replacement = ReplacementService(svc.missions)
    identity = period["id"] + ":doctor-replacement:2"
    task = replacement.get(PLAYER, identity)
    proposed = replacement.propose(
        PLAYER,
        "proposal",
        identity,
        task["revision"],
        task["game_revision"],
        Preferences(frame="WYVERN 0.4", frame_name="New Frame", frame_appearance="New appearance"),
    )
    quote = replacement.get(ADMIN, proposed["package_id"])
    replacement.quote(
        ADMIN,
        "quote",
        proposed["package_id"],
        quote["revision"],
        quote["game_revision"],
        Package(
            assets=(
                SuppliedAsset(name="Plating", description="New plating", damaged=False, void=False),
            ),
            explanation="Handler package",
        ),
    )
    task = replacement.get(PLAYER, identity)
    replacement.apply(
        PLAYER,
        "install",
        identity,
        task["revision"],
        task["game_revision"],
        task["package_revision"],
    )
    assert not state(game).sheets["2"].frame_scrapped
    with ledger.engine.connect() as c:
        rows = list(c.execute(sa.select(t.m3["m3_required_work"])).mappings())
    assert all(row["mission_id"] is None and row["off_duty_id"] == period["id"] for row in rows)


def test_strain_history_rebuild_and_backup_preserve_dice_and_pending_requests(ledger, tmp_path):
    from girlframe.config import Settings
    from girlframe.database.connection import create_database_engine
    from girlframe.database.maintenance import copy_database
    from girlframe.services.m2_game import GameService
    from girlframe.services.m3_missions import MissionService
    from girlframe.services.onboarding import OnboardingStore

    svc, game = ready(ledger)
    prepared(svc, game)
    request = state(game).strain.requests[0]
    svc.roll(ADMIN, "roll", request.id, 1, state(game).revision)
    before = svc.get(ADMIN)
    game.rebuild()
    assert svc.get(ADMIN) == before
    backup = tmp_path / "strain-backup.db"
    copy_database(Path(ledger.engine.url.database), backup)
    engine = create_database_engine(Settings(database_url="sqlite:///" + str(backup)))
    try:
        restored = StrainService(
            OffDutyService(
                MissionService(OnboardingStore(engine, ledger.policy), svc.missions.access.registry)
            )
        )
        assert restored.get(ADMIN) == before
        assert state(GameService(restored.store)).strain.events[0].face == 1
    finally:
        engine.dispose()
