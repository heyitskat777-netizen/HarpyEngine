import json
from concurrent.futures import ThreadPoolExecutor

import pytest
import sqlalchemy as sa
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger_fixture
from test_m2_game import state
from test_mission_service import launched, service

from girlframe.database import tables as t
from girlframe.engine.m2 import PlayInput
from girlframe.services.m3_reactions import ReactionService
from girlframe.services.onboarding import WorkflowError

ledger = ledger_fixture


def setup(store, *, girl="MOCKINGBIRD", frame="DOCTORDOCTOR MK. II", boxes=0):
    missions, game = service(store, girl=girl, frame=frame)
    store.policy = store.policy.model_copy(
        update={
            "m3_approval": store.policy.m3_approval.model_copy(
                update={"subsystems": store.policy.m3_approval.subsystems | {"playbooks"}}
            )
        }
    )
    if boxes:
        with store.transaction() as c:
            saved = state(game)
            saved.sheets["2"].obsolescence_marked = boxes
            game.event(c, 1, "synthetic-boxes", "synthetic.boxes", saved)
    identity, revision = launched(missions)
    mission = missions.end(ADMIN, "end", identity, revision, False)
    svc = ReactionService(missions)
    return svc, missions, game, mission


def work(missions, mission, kind):
    return next(x for x in missions.get(ADMIN, mission["id"])["work"] if x["kind"] == kind)


def mark(svc, identity, key="mark"):
    current = svc.get(ADMIN, identity)
    return svc.doctor(ADMIN, key, identity, current["revision"], current["game_revision"])


def test_doctor_failure_marks_once_before_rewards_and_has_no_acknowledgment_shortcut(ledger):
    svc, missions, game, mission = setup(ledger)
    task = work(missions, mission, "doctor_obsolescence")
    current = svc.get(ADMIN, task["id"])
    result = mark(svc, task["id"])
    assert state(game).sheets["2"].obsolescence_marked == 1
    assert state(game).sheets["2"].permissions == 0
    assert (
        svc.doctor(ADMIN, "mark", task["id"], current["revision"], current["game_revision"])
        == result
    )
    assert missions.complete(ADMIN, "rewards", mission["id"], mission["revision"])[
        "rewards_committed"
    ]
    assert state(game).sheets["2"].permissions == 2
    assert missions.get(ADMIN, mission["id"])["pending_count"] == 2


def test_doctor_scrapping_persists_mandatory_owner_replacement_and_blocks_missions_and_plays(
    ledger,
):
    svc, missions, game, mission = setup(ledger, boxes=7)
    task = work(missions, mission, "doctor_obsolescence")
    assert mark(svc, task["id"])["replacement_required"]
    assert state(game).sheets["2"].frame_scrapped
    owned = missions.owned_work(PLAYER)
    replacement = next(x for x in owned if x["kind"] == "doctor_frame_replacement")
    assert replacement["owner_id"] == "2"
    with pytest.raises(WorkflowError, match="still pending"):
        missions.complete(ADMIN, "skip", mission["id"], mission["revision"])
    with pytest.raises(WorkflowError):
        missions.offer(ADMIN, "scrapped-mission", "Cannot pilot", (2,))
    with pytest.raises(WorkflowError, match="scrapped"):
        game.begin(
            PLAYER,
            "scrapped-play",
            900,
            state(game).sheets["2"].revision,
            PlayInput(play="keep_your_head", context="Synthetic", trigger_confirmed=True, heat=0),
        )


def test_reactions_are_private_to_assigned_handler_and_subject_with_no_objective_leak(ledger):
    svc, missions, _, mission = setup(ledger)
    task = work(missions, mission, "doctor_obsolescence")
    assert "PRIVATE_OBJECTIVE" not in json.dumps(svc.get(PLAYER, task["id"]))
    with pytest.raises(WorkflowError, match="other participants"):
        svc.get(OTHER, task["id"])
    with pytest.raises(WorkflowError):
        svc.doctor(
            PLAYER, "not-handler", task["id"], 1, svc.get(PLAYER, task["id"])["game_revision"]
        )


def test_reaction_staleness_pause_and_subsystem_gate_never_mark_a_box(ledger):
    svc, missions, game, mission = setup(ledger)
    task = work(missions, mission, "doctor_obsolescence")
    current = svc.get(ADMIN, task["id"])
    with pytest.raises(WorkflowError, match="STALE_STATE"):
        svc.doctor(ADMIN, "stale", task["id"], 1, current["game_revision"] - 1)
    ledger.safety(OTHER, "pause", ledger.status(OTHER)["revision"], pause=True)
    with pytest.raises(WorkflowError, match="SAFETY_PAUSED"):
        mark(svc, task["id"])
    ledger.safety(OTHER, "resume", ledger.status(OTHER)["revision"], pause=False)
    ledger.policy = ledger.policy.model_copy(
        update={
            "m3_approval": ledger.policy.m3_approval.model_copy(
                update={"subsystems": frozenset({"missions"})}
            )
        }
    )
    with pytest.raises(WorkflowError, match="M3_REVIEW_PENDING"):
        mark(svc, task["id"])
    assert state(game).sheets["2"].obsolescence_marked == 0


def test_reaction_rollback_and_concurrent_duplicate_requests(ledger, monkeypatch):
    svc, missions, game, mission = setup(ledger)
    task = work(missions, mission, "doctor_obsolescence")
    original = svc._save

    def fail(*args, **kwargs):
        raise RuntimeError("Synthetic reaction write failure")

    monkeypatch.setattr(svc, "_save", fail)
    with pytest.raises(RuntimeError):
        mark(svc, task["id"])
    assert state(game).sheets["2"].obsolescence_marked == 0
    monkeypatch.setattr(svc, "_save", original)
    current = svc.get(ADMIN, task["id"])

    def submit(key):
        try:
            return svc.doctor(ADMIN, key, task["id"], 1, current["game_revision"])
        except WorkflowError:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(submit, ("first", "second")))
    assert sum(x is not None for x in results) == 1
    assert state(game).sheets["2"].obsolescence_marked == 1


def test_princess_without_upheld_standards_has_no_invented_bonus(ledger):
    svc, missions, game, mission = setup(ledger, girl="PRINCESS", frame="JANUS-B")
    task = work(missions, mission, "princess_mission_end")
    current = svc.get(ADMIN, task["id"])
    assert len(current["standards"]) == 3
    assert sum(x["is_order"] for x in current["standards"]) == 1
    ledger.policy = ledger.policy.model_copy(
        update={
            "owner_m3_rulings": ledger.policy.owner_m3_rulings.model_copy(
                update={"princess_ace_check": None}
            )
        }
    )
    with pytest.raises(WorkflowError, match="UNRESOLVED_RULING"):
        svc.princess(
            ADMIN,
            "unknown-policy",
            task["id"],
            1,
            current["game_revision"],
            upheld=True,
            rationale="Synthetic source condition",
        )
    result = svc.princess(
        ADMIN,
        "not-upheld",
        task["id"],
        1,
        current["game_revision"],
        upheld=False,
        rationale="Standards were not upheld in this synthetic example",
    )
    assert result["state"] == "resolved" and state(game).sheets["2"].permissions == 0
    assert missions.complete(ADMIN, "rewards", mission["id"], mission["revision"])[
        "rewards_committed"
    ]
    with ledger.engine.connect() as c:
        payloads = " ".join(c.scalars(sa.select(t.events.c.payload_json)))
    assert "Standards were not upheld" not in payloads


def test_princess_promotion_and_own_bonus_precede_the_final_ace_bonus(ledger):
    svc, missions, game, mission = setup(ledger, girl="PRINCESS", frame="JANUS-B")
    with ledger.transaction() as c:
        saved = state(game)
        saved.order = (3, 2)
        game.event(c, 1, "synthetic-rank", "synthetic.rank", saved)
    task = work(missions, mission, "princess_mission_end")
    current = svc.get(ADMIN, task["id"])
    result = svc.princess(
        ADMIN,
        "upheld",
        task["id"],
        1,
        current["game_revision"],
        upheld=True,
        rationale="Synthetic standards upheld",
    )
    assert state(game).order == (2, 3) and state(game).sheets["2"].permissions == 1
    assert (
        svc.princess(
            ADMIN,
            "upheld",
            task["id"],
            1,
            current["game_revision"],
            upheld=True,
            rationale="Synthetic standards upheld",
        )
        == result
    )
    missions.complete(ADMIN, "reward-snapshot", mission["id"], mission["revision"])
    assert state(game).sheets["2"].permissions == 3
    assert missions.get(ADMIN, mission["id"])["work"][0]["kind"] == "punishment"
