"""Recipient-safe mission controls derived from the native command prerequisites."""

from collections.abc import Callable
from functools import partial
from typing import Any

from sqlalchemy import Connection

from girlframe.services.campaign_difficulty import opening, session_zero_pending
from girlframe.services.campaign_time_history import anchor
from girlframe.services.handler_setup import HandlerService
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_off_duty import OffDutyService
from girlframe.services.m3_reactions import ReactionService
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer

REACTIONS = frozenset({"princess_mission_end", "doctor_obsolescence"})


class MissionControlService:
    def __init__(self, missions: MissionService):
        self.missions = missions
        self.periods = OffDutyService(missions)

    def _blocked(self, c: Connection, viewer: GuildViewer, ready: Callable[[], Any]) -> str | None:
        try:
            self.missions._authorize(c, viewer)
            self.missions._boundary(c)
            ready()
        except (ValueError, WorkflowError) as error:
            return str(error)
        return None

    def view(self, viewer: GuildViewer) -> dict[str, Any]:
        """Read controls, never reserve work or mutate state. Commands recheck atomically."""
        missions = self.missions
        directory = missions.list(viewer)
        with missions.store.engine.connect() as c:
            handler = HandlerService(missions.store).current(c)[1].handler_id
        is_handler = handler == viewer.user_id
        period = self.periods.current(viewer) if is_handler else None
        offers = []
        for listed in directory:
            saved = missions.get(viewer, listed["id"])
            mission = saved["mission"]
            row = listed | {
                "phase": mission["phase"],
                "revision": mission["revision"],
                "response": mission["responses"].get(str(viewer.user_id)),
                "success": mission["success"],
                "debrief": mission.get("debrief"),
                "pending_count": saved["pending_count"],
            }
            row["needs_response"] = (
                mission["phase"] == "offered"
                and viewer.user_id in mission["offered_to"]
                and row["response"] is None
            )
            if mission.get("introductory"):
                row["introductory"] = True
            if mission.get("hard_stake"):
                row["hard_stake"] = mission["hard_stake"]
            if is_handler:
                actions: list[str] = []
                blocked: dict[str, str] = {}
                with missions.store.engine.connect() as c:
                    actual = missions._mission(c, listed["id"])

                    checks: dict[str, Callable[[], Any]]
                    if actual.phase == "offered":
                        checks = {
                            "cancel": partial(
                                missions._cancel_ready, c, viewer, actual, actual.revision
                            ),
                            "dispatch": partial(
                                missions._dispatch_ready, c, viewer, actual, actual.revision
                            ),
                        }
                    elif actual.phase == "active":
                        checks = {
                            "debrief": partial(
                                missions._end_ready, c, viewer, actual, actual.revision
                            )
                        }
                    elif actual.phase in ("ending", "awaiting_consequences"):
                        checks = {
                            "advance": partial(
                                missions._complete_ready, c, viewer, actual, actual.revision
                            )
                        }
                    else:
                        checks = {}
                    for name, ready in checks.items():
                        reason = self._blocked(c, viewer, ready)
                        if reason is None:
                            actions.append(name)
                        else:
                            blocked[name] = reason
                    row.update(phase=actual.phase, revision=actual.revision)
                reactions = [
                    ReactionService(missions).get(viewer, item["id"])
                    for item in saved["work"]
                    if item["kind"] in REACTIONS
                ]
                row.update(
                    actions=actions,
                    blocked=blocked,
                    offered=len(mission["offered_to"]),
                    answered=len(mission["responses"]),
                    accepted=sum(x == "accept" for x in mission["responses"].values()),
                    reactions=[x for x in reactions if x["owner_id"] == str(viewer.user_id)],
                )
            offers.append(row)
        desk = None
        if is_handler:
            reason = None
            with missions.store.engine.connect() as c:
                try:
                    missions._authorize(c, viewer)
                    self.periods._begin_ready(c, viewer)
                except (ValueError, WorkflowError) as error:
                    reason = str(error)
            try:
                roster = missions.roster(viewer)
            except WorkflowError:
                roster = ()
            with missions.store.engine.connect() as c:
                offer_reason = self._blocked(c, viewer, partial(missions._not_off_duty, c))
                if offer_reason is None:
                    record = opening(c, missions.store.campaign_id)
                    current = anchor(c, missions.store.campaign_id) if record else None
                    if record is None and session_zero_pending(c, missions.store.campaign_id):
                        offer_reason = "Complete Session Zero before offering the first mission."
                    elif record and current and current[1].position.day < record.first_mission_day:
                        offer_reason = f"The first mission opens on Day {record.first_mission_day}."
            capture_targets = None
            if offer_reason is None:
                try:
                    capture_targets = missions.capture_options(viewer)
                except WorkflowError as error:
                    offer_reason = str(error)
            if offer_reason is None and not roster:
                offer_reason = "No eligible active Pilots are available for an invitation."
            if offer_reason is None and capture_targets == ():
                offer_reason = "The next mission requires a known Harpy available for conversion."
            desk = {
                "pilots": roster,
                "can_offer": offer_reason is None,
                "offer_blocker": offer_reason,
                "off_duty": period["phase"] if period else None,
                "can_begin_off_duty": reason is None,
                "off_duty_blocker": reason,
            }
            if capture_targets is not None:
                desk["capture_targets"] = capture_targets
            if offer_reason is None:
                intro, hard = missions.offer_requirements(viewer)
                if intro:
                    desk["introductory"] = True
                if hard:
                    desk["requires_hard_stake"] = True
        return {"offers": offers, "desk": desk}
