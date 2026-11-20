"""Transactional Session Zero launch on the existing calendar and scene ledger."""

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine.campaign_opening import CampaignSeats, Opening
from girlframe.engine.session_zero import SessionZero
from girlframe.scenes.campaign_time import Anchor, Cut, Position, ScenePlan
from girlframe.services import campaign_time_history as calendar
from girlframe.services.campaign_difficulty import EVENT, historical_mission, opening
from girlframe.services.campaign_time import CampaignTimeService
from girlframe.services.onboarding import OnboardingStore, WorkflowError
from girlframe.services.read_only_bot import GuildViewer

CHAPTER = "Cadre Introduction"
DEFAULT_ROLEPLAY_DAYS = 3


def launch(
    c: Connection,
    store: OnboardingStore,
    viewer: GuildViewer,
    key: str,
    session: SessionZero,
    channel: int,
    introduction: str,
    days: int,
    *,
    reuse_empty: bool = False,
) -> Opening:
    if opening(c, store.campaign_id) is not None:
        raise WorkflowError("The campaign introduction is already open.")
    if historical_mission(c, store.campaign_id):
        raise WorkflowError("The introduction belongs before the campaign's first mission.")
    if type(days) is not int or not 2 <= days <= 7:
        raise WorkflowError("Choose two to seven fictional days for the introductory window.")
    introduction = introduction.strip()
    if not introduction or len(introduction) > 1200:
        raise WorkflowError("Write the Handler's introduction in 1–1200 characters.")
    if session.plan_proposal is None:
        raise WorkflowError("Agree on the short-term campaign plan first.")

    time = CampaignTimeService(store)
    time.game.unpaused(c)
    if time.game.pending_actions(c):
        raise WorkflowError("Resolve pending Plays before opening the introduction.")
    if time._phase(c):
        raise WorkflowError("Finish the active rules phase before opening the introduction.")
    saved = calendar.anchor(c, store.campaign_id)
    start = saved[1].position if saved else Position(day=1, slot="morning")
    earliest = start.day + days
    if earliest > 999_999:
        raise WorkflowError("There is no room left for these days on the campaign calendar.")
    plan = ScenePlan(
        chapter=CHAPTER,
        start=start,
        end=Position(day=earliest - 1, slot="night"),
        participants=session.members,
        allow_late_narration=True,
        narrative_only=True,
    )
    rows = time._scene_rows(c)
    schedules = time._scenes(c, rows)
    reserved = None
    for scene_id, row in rows.items():
        if not row["open"]:
            continue
        other = schedules.get(scene_id)
        if (
            reuse_empty
            and other is None
            and row["channel_id"] == str(channel)
            and row["revision"] == 1
            and row["participants_json"] == "[]"
        ):
            reserved = scene_id
            continue
        if other is None or (
            other.plan.overlaps(plan) and set(other.plan.participants).intersection(session.pilots)
        ):
            raise WorkflowError("Close or schedule other open scenes before the introduction.")
    if saved is None:
        store._audit(
            c,
            viewer.user_id,
            key,
            calendar.INITIALIZED,
            {"anchor": Anchor(chapter=CHAPTER, position=start).model_dump(mode="json")},
            event_index=1,
            ruleset_version="timeline-v1",
        )
    if reserved is None:
        reserved = str(
            time.game._bind_scene_in_transaction(c, viewer.user_id, key, channel, event_index=2)[
                "scene"
            ]
        )
    store._audit(
        c,
        viewer.user_id,
        key,
        calendar.SCHEDULED,
        {
            "scene": reserved,
            "channel": channel,
            "chapter": CHAPTER,
            "plan": plan.model_dump(mode="json"),
        },
        event_index=3,
        ruleset_version="timeline-v1",
    )
    assert session.handler is not None
    result = Opening(
        scene=reserved,
        channel=channel,
        handler=viewer.user_id,
        audience=session.members,
        plan=session.plan_proposal,
        goals=session.goals,
        difficulty=session.difficulty,
        introduction=introduction,
        first_mission_day=earliest,
        handler_control=session.handler.control,
        seats=session.seats or CampaignSeats(player_count=session.human_players),
    )
    store._audit(
        c,
        viewer.user_id,
        key,
        EVENT,
        result.model_dump(mode="json"),
        event_index=4,
        ruleset_version="session-zero-v1",
    )
    return result


def advance(
    c: Connection,
    store: OnboardingStore,
    viewer: GuildViewer,
    key: str,
    expected_anchor: str,
    record: Opening,
) -> dict[str, object]:
    time = CampaignTimeService(store)
    anchor_receipt, current = time._current(c)
    if anchor_receipt != expected_anchor:
        raise WorkflowError("STALE_CUT: refresh today's opening scene before moving forward.")
    if current.position.day >= record.first_mission_day:
        raise WorkflowError("The introductory window is complete.")
    next_day = current.position.day + 1
    cut = Cut(
        target=Anchor(
            chapter=CHAPTER if next_day < record.first_mission_day else "First Mission",
            position=Position(day=next_day, slot="morning"),
        )
    )
    preview, late = time._preview(c, viewer, cut)
    return time._record_cut(c, viewer, key, preview, late)


def dispatch_scene(
    c: Connection,
    store: OnboardingStore,
    viewer: GuildViewer,
    key: str,
    participants: tuple[int, ...],
) -> dict[str, int | str]:
    time = CampaignTimeService(store)
    record = opening(c, store.campaign_id)
    if record is None:
        raise WorkflowError("Recover the agreed campaign introduction first.")
    _, current = time._current(c)
    table = t.m2["m2_scenes"]
    original = c.execute(
        sa.select(table.c.id, table.c.open).where(
            table.c.campaign_id == store.campaign_id,
            table.c.channel_id == str(record.channel),
        )
    ).first()
    if original is None or original.id != record.scene or original.open:
        raise WorkflowError("Close and retain the original introduction before dispatching.")
    binding = time.game._bind_scene_in_transaction(
        c,
        viewer.user_id,
        key,
        record.channel,
        event_index=1,
    )
    plan = ScenePlan(
        start=current.position,
        end=current.position,
        participants=(*participants, viewer.user_id),
    )
    store._audit(
        c,
        viewer.user_id,
        key,
        calendar.SCHEDULED,
        {
            "scene": binding["scene"],
            "channel": record.channel,
            "chapter": current.chapter,
            "plan": plan.model_dump(mode="json"),
        },
        event_index=2,
        ruleset_version="timeline-v1",
    )
    return {"scene": binding["scene"], "channel": record.channel}
