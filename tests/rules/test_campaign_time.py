"""Offline campaign-time checks through real engine commands and synthetic campaigns."""

import json
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
import sqlalchemy as sa
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state
from test_medical import proposed, selection
from test_mission_service import service as setup_missions
from test_off_duty_cycle import activate, finish_routine, movement, prepared, recover_both

from girlframe.database import tables as t
from girlframe.scenes.campaign_time import (
    Anchor,
    Cut,
    Dependency,
    LateSubmission,
    Position,
    ScenePlan,
)
from girlframe.services.campaign_time import CampaignTimeService
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_off_duty import OffDutyService
from girlframe.services.m3_off_duty_cycle import CycleService
from girlframe.services.onboarding import OnboardingStore, WorkflowError
from girlframe.services.read_only_bot import GuildViewer

AFTERNOON = Position(day=4, slot="afternoon")
NIGHT = Position(day=4, slot="night")
MORNING = Position(day=7, slot="morning")
ANCHOR = Anchor(chapter="Interlude", position=AFTERNOON)


def booked(timeline, game, receipt, channel, people, *, when=AFTERNOON, late=False):
    with game.store.engine.connect() as c:
        scene = game.scene(c, channel, check_slot=False)
    return timeline.schedule(
        ADMIN,
        f"schedule-{channel}",
        channel,
        scene["id"],
        scene["revision"],
        receipt,
        ScenePlan(start=when, end=when, participants=people, allow_late_narration=late),
    )["scene"]


def test_medical_gates_parallel_cut_and_late_debrief_is_audience_scoped(ledger, monkeypatch):
    medical, game, work_id = proposed(ledger, "PRIVATE_MEDICAL_DECISION")
    game.leave_scene(OTHER, "leave-original", 900)
    timeline = CampaignTimeService(ledger)
    assert timeline.projection(PLAYER) == {"version": 1, "mode": "legacy"}
    initial = timeline.initialize(ADMIN, "anchor", ANCHOR)["receipt"]
    actions, choices, receipts = (t.m2[f"m2_{name}"] for name in ("actions", "choices", "receipts"))
    with ledger.engine.connect() as c:
        action_id, choice_id = c.execute(
            sa.select(actions.c.id, choices.c.id)
            .join_from(
                actions,
                choices,
                sa.and_(
                    actions.c.campaign_id == choices.c.campaign_id,
                    actions.c.id == choices.c.action_id,
                ),
            )
            .where(choices.c.kind == "defeat_select")
        ).one()
        play_receipt = c.scalar(sa.select(receipts.c.id).where(receipts.c.action_id == action_id))
    cut = Cut(
        target=Anchor(chapter="Briefing", position=NIGHT),
        requires=(
            Dependency(kind="work", id=work_id),
            Dependency(kind="choice", id=choice_id),
            Dependency(kind="play_receipt", id=play_receipt),
        ),
    )
    assert any(
        item["kind"] == "classify_scene" for item in timeline.preview_cut(ADMIN, cut)["blockers"]
    )
    medical_scene = booked(timeline, game, initial, 900, (2,))
    game.bind_scene(ADMIN, "bind-debrief", 901)
    debrief = booked(timeline, game, initial, 901, (3,), late=True)
    assert not timeline.projection(OTHER)["scenes"][0]["joined"]
    game.join_scene(OTHER, "attend-debrief", 901)

    game.bind_scene(ADMIN, "bind-independent", 902)
    independent = booked(timeline, game, initial, 902, (1,))
    game.close_scene(ADMIN, "close-independent", 902)
    assert timeline.projection(OTHER)["anchor"] == ANCHOR.model_dump()
    assert (
        next(x for x in timeline.projection(ADMIN)["scenes"] if x["id"] == independent)["status"]
        == "closed"
    )

    blocked = timeline.preview_cut(ADMIN, cut)
    assert {"kind": "work", "id": work_id} in blocked["blockers"]
    assert blocked["late_scenes"] == [debrief]
    with pytest.raises(WorkflowError, match="CUT_BLOCKED"):
        timeline.commit_cut(ADMIN, "commit", cut, blocked["token"])
    with pytest.raises(WorkflowError, match="appointed campaign Handler"):
        timeline.preview_cut(OTHER, cut)
    data = medical.get(ADMIN, work_id)
    assert {"route": "medical", "id": work_id, "revision": data["revision"]} in (
        timeline.projection(ADMIN)["followups"]
    )
    medical.confirm(ADMIN, "wake", work_id, data["revision"], data["game_revision"], True, "Care")
    data = medical.get(PLAYER, work_id)
    assert {"route": "medical", "id": work_id, "revision": data["revision"]} in (
        timeline.projection(PLAYER)["followups"]
    )
    other_view = timeline.projection(OTHER)
    assert {x["id"] for x in other_view["scenes"]} == {debrief}
    assert not any(
        key in json.dumps(other_view)
        for key in (
            work_id,
            medical_scene,
            "PRIVATE_MEDICAL_DECISION",
            "blockers",
        )
    )

    before_exchange = timeline.preview_cut(ADMIN, cut)

    def try_cut():
        try:
            return timeline.commit_cut(ADMIN, "commit", cut, before_exchange["token"])
        except WorkflowError as error:
            return str(error)

    with ThreadPoolExecutor(max_workers=2) as executor:
        cut_attempt = executor.submit(try_cut)
        exchange = executor.submit(
            medical.exchange,
            PLAYER,
            "exchange",
            work_id,
            data["revision"],
            data["game_revision"],
            selection(),
        )
        exchange.result()
        assert str(cut_attempt.result()).startswith(("STALE_CUT", "CUT_BLOCKED"))
    game.close_scene(ADMIN, "close-medical", 900)
    preview = timeline.preview_cut(ADMIN, cut)
    assert preview["blockers"] == [] and preview["late_scenes"] == [debrief]
    assert {x["id"] for x in preview["dependency_receipts"]} == {work_id, choice_id, play_receipt}
    before_cut_state = state(game)
    original_event = timeline._event

    def fail_after_close(*args, **kwargs):
        original_event(*args, **kwargs)
        raise RuntimeError("simulated pre-commit failure")

    with monkeypatch.context() as patch:
        patch.setattr(timeline, "_event", fail_after_close)
        with pytest.raises(RuntimeError, match="pre-commit failure"):
            timeline.commit_cut(ADMIN, "commit", cut, preview["token"])
    assert timeline.projection(OTHER)["scenes"][0]["status"] == "open"
    committed = timeline.commit_cut(ADMIN, "commit", cut, preview["token"])
    ledger.engine.dispose()
    restarted = CampaignTimeService(ledger)
    assert restarted.commit_cut(ADMIN, "commit", cut, preview["token"]) == committed
    assert restarted.projection(OTHER)["scenes"][0]["status"] == "late"
    with ledger.engine.connect() as c:
        with pytest.raises(WorkflowError, match="Bind an open"):
            game.scene(c, 901)
        assert (
            c.scalar(
                sa.select(sa.func.count())
                .select_from(t.events)
                .where(t.events.c.kind == "timeline.cut_committed")
            )
            == 1
        )

    sealed_by = committed["receipt"]
    report = LateSubmission(
        kind="mechanical", account="PRIVATE_RETROACTIVE_INJURY and roster change"
    )
    delivered = restarted.record_late(OTHER, "retroactive-injury", debrief, sealed_by, report)
    assert delivered["status"] == "handler_review"
    assert (
        restarted.record_late(OTHER, "retroactive-injury", debrief, sealed_by, report) == delivered
    )
    with pytest.raises(WorkflowError, match="appointed campaign Handler"):
        restarted.record_late(
            OTHER,
            "canon-attempt",
            debrief,
            sealed_by,
            LateSubmission(kind="narration", account="Player requests an unsupported outcome"),
        )
    restarted.record_late(
        ADMIN,
        "late-account",
        debrief,
        sealed_by,
        LateSubmission(kind="narration", account="The pilot recounted the exercise."),
    )
    with pytest.raises(WorkflowError, match="actual participants"):
        restarted.record_late(
            ADMIN,
            "invalid-knowledge",
            debrief,
            sealed_by,
            LateSubmission(kind="knowledge", account="A witness account", recipients=(2,)),
        )
    restarted.record_late(
        ADMIN,
        "private-knowledge",
        debrief,
        sealed_by,
        LateSubmission(kind="knowledge", account="PRIVATE_DEBRIEF_KNOWLEDGE", recipients=(3,)),
    )
    assert "PRIVATE_DEBRIEF_KNOWLEDGE" in json.dumps(restarted.projection(OTHER))
    assert "PRIVATE_RETROACTIVE_INJURY" in json.dumps(restarted.projection(ADMIN))
    assert "PRIVATE_DEBRIEF" not in json.dumps(restarted.projection(PLAYER))
    assert state(game) == before_cut_state
    restarted.close_late(ADMIN, "late-close", debrief, sealed_by)
    with pytest.raises(WorkflowError, match="late scene is unavailable"):
        restarted.record_late(OTHER, "after-close", debrief, sealed_by, report)
    assert restarted.projection(OTHER)["scenes"][0]["status"] == "closed"
    assert restarted.projection(OTHER)["anchor"] == cut.target.model_dump()


def test_calendar_rejects_overlapping_reservations_and_waits_for_a_future_slot(ledger):
    _, game = setup_missions(ledger)
    timeline = CampaignTimeService(ledger)
    game.close_scene(ADMIN, "close-legacy", 900)
    initial = timeline.initialize(ADMIN, "anchor", ANCHOR)["receipt"]
    assert timeline.projection(PLAYER)["scenes"] == []
    game.bind_scene(ADMIN, "future-a", 901)
    booked(timeline, game, initial, 901, (2,), when=NIGHT)
    game.bind_scene(ADMIN, "future-b", 902)
    with pytest.raises(WorkflowError, match="overlapping"):
        booked(timeline, game, initial, 902, (2,), when=NIGHT)
    booked(timeline, game, initial, 902, (3,), when=NIGHT)
    with pytest.raises(WorkflowError, match="opening slot has not arrived"):
        game.join_scene(PLAYER, "early", 901)
    cut = Cut(target=Anchor(chapter="Interlude", position=NIGHT))
    preview = timeline.preview_cut(ADMIN, cut)
    timeline.commit_cut(ADMIN, "cut-to-night", cut, preview["token"])
    with pytest.raises(WorkflowError, match="schedule this Pilot"):
        game.join_scene(PLAYER, "wrong-roster", 902)
    game.join_scene(PLAYER, "actual-join", 901)
    assert timeline.projection(PLAYER)["scenes"][0]["joined"]


def test_multiday_cut_preserves_explicit_off_duty_recovery_strain_and_world_state(ledger):
    cycle, game, period = prepared(ledger)
    timeline = CampaignTimeService(ledger)
    initial = timeline.initialize(ADMIN, "calendar-anchor", ANCHOR)["receipt"]
    booked(timeline, game, initial, 900, (2, 3))
    cut = Cut(target=Anchor(chapter="Next week", position=MORNING))
    preparing = timeline.preview_cut(ADMIN, cut)
    assert {"kind": "phase_transition_required"} in preparing["blockers"]
    assert timeline.projection(PLAYER)["cadre_phase"] == [
        {"kind": "off_duty", "phase": "preparing"}
    ]
    activate(cycle, game, period)
    recover_both(cycle, game, period)
    finish_routine(cycle, game, period)
    period_revision = cycle.review(ADMIN, period)["revision"]
    game_revision = state(game).revision
    moves = movement(game)
    assert moves
    finished = cycle.finish(ADMIN, "explicit-finish", period, period_revision, game_revision, moves)
    ledger.engine.dispose()
    restarted = CycleService(OffDutyService(MissionService(ledger)))
    assert (
        restarted.finish(ADMIN, "explicit-finish", period, period_revision, game_revision, moves)
        == finished
    )
    game.close_scene(ADMIN, "close-recovery-room", 900)
    before = state(game)
    assert len([x for x in before.strain.events if x.period_id == period and x.parent is None]) == 3
    assert before.world.completed_off_duty == (period,)
    assert timeline.projection(PLAYER)["anchor"] == ANCHOR.model_dump()
    assert timeline.projection(PLAYER)["cadre_phase"] == []
    preview = timeline.preview_cut(ADMIN, cut)
    assert preview["blockers"] == []
    timeline.commit_cut(ADMIN, "multi-day-cut", cut, preview["token"])
    assert timeline.projection(PLAYER)["anchor"] == cut.target.model_dump()
    assert timeline.projection(PLAYER)["cadre_phase"] == []
    assert state(game) == before


def test_play_safety_staleness_and_campaign_isolation(ledger):
    from test_m2_game import start

    _, game = setup_missions(ledger)
    timeline = CampaignTimeService(ledger)
    initial = timeline.initialize(ADMIN, "anchor", ANCHOR)["receipt"]
    booked(timeline, game, initial, 900, (2, 3), late=True)
    cut = Cut(target=Anchor(chapter="Briefing", position=NIGHT))
    preview = timeline.preview_cut(ADMIN, cut)
    assert preview["blockers"] == []
    ledger.safety(OTHER, "safety", ledger.status(OTHER)["revision"], pause=True)
    paused = timeline.preview_cut(ADMIN, cut)
    assert {"kind": "safety_paused"} in paused["blockers"]
    with pytest.raises(WorkflowError, match="STALE_CUT"):
        timeline.commit_cut(ADMIN, "stale-ui", cut, preview["token"])
    ledger.safety(OTHER, "resume", ledger.status(OTHER)["revision"], pause=False)
    start(game)
    assert {"kind": "play_pending"} in timeline.preview_cut(ADMIN, cut)["blockers"]
    assert not game.dice.calls

    current_policy = ledger.policy
    ledger.policy = current_policy.model_copy(update={"m3_approval": None})
    try:
        with pytest.raises(WorkflowError, match="M3_REVIEW_PENDING"):
            timeline.preview_cut(ADMIN, cut)
        assert timeline.projection(PLAYER)["anchor"] == ANCHOR.model_dump()
    finally:
        ledger.policy = current_policy

    second_policy = ledger.policy.model_copy(update={"campaign_id": uuid4(), "guild_id": 300})
    second = OnboardingStore(ledger.engine, second_policy)
    visitor = GuildViewer(user_id=2, guild_id=300, is_member=True, is_administrator=False)
    second.join(visitor, "join")
    assert CampaignTimeService(second).projection(visitor) == {"version": 1, "mode": "legacy"}
    with pytest.raises(WorkflowError):
        timeline.projection(visitor)
