"""Read committed timing at the existing Director and Handler trust boundaries."""

from sqlalchemy import Connection

from girlframe.ai.director import SceneClock, SceneTime
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.services import campaign_time_history as calendar
from girlframe.services import mission_timing_history as timing
from girlframe.services.mission_timing import MissionTimingService
from girlframe.services.onboarding import OnboardingStore, WorkflowError


def scene_time(c: Connection, campaign: str, scene: str) -> SceneTime | None:
    anchor = calendar.anchor(c, campaign)
    if anchor is None:
        return None
    receipt, current = anchor
    booking = calendar.booking(c, campaign, scene)
    saved = timing.current(c, campaign)
    clock = None
    if saved is not None and saved[1].scene == scene and not saved[1].closed:
        clock_receipt, active = saved
        clock = SceneClock(
            receipt=clock_receipt,
            day=active.day,
            minute=active.minute,
            deadline=active.deadline.minute,
            boundary=active.deadline.boundary,
            status=active.deadline.status(active.minute),
            consequence_recorded=active.consequence_receipt is not None,
        )
    return SceneTime(
        anchor_receipt=receipt,
        position=current.position,
        start=booking.start if booking else None,
        end=booking.end if booking else None,
        clock=clock,
    )


def require_clock_audience(
    c: Connection,
    store: OnboardingStore,
    scene: str,
    receipt: str,
    recipients: tuple[ActorRef, ...],
) -> None:
    latest = timing.current(c, store.campaign_id)
    if latest is None or latest[0] != receipt or latest[1].scene != scene or latest[1].closed:
        raise WorkflowError("STALE_HANDLER_CLOCK: review the current clock before replying.")
    service = MissionTimingService(store)
    mission, row = service._context(c, latest[1])
    original = service.missions._source_characters(c, mission)
    for actor in recipients:
        if actor.kind != "pilot" or original.get(actor.entity) != actor.incarnation:
            raise WorkflowError("HANDLER_CLOCK_AUDIENCE: choose an original dispatched Pilot.")
        service._pilot(c, mission, row, int(actor.entity))


def handler_time(
    c: Connection, store: OnboardingStore, scene: str, source: ActorRef
) -> SceneTime | None:
    current = scene_time(c, store.campaign_id, scene)
    if current is None or current.start is None or current.end is None:
        return None
    if not current.start.order <= current.position.order <= current.end.order:
        return None
    if current.clock is not None:
        try:
            require_clock_audience(c, store, scene, current.clock.receipt, (source,))
        except WorkflowError:
            return current.model_copy(update={"clock": None})
    return current
