"""Present native mission transitions and their assigned work in the Activity."""

from typing import Any
from uuid import UUID

import sqlalchemy as sa
from girlframe.database import tables
from girlframe.services.m3_replacement import COURT, PACKAGE, ROOTS

from girlframe.services.m3_mission_control import MissionControlService
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_off_duty import OffDutyService
from girlframe.services.m3_reactions import ReactionService
from girlframe.services.read_only_bot import GuildViewer

REACTIONS = frozenset({"princess_mission_end", "doctor_obsolescence"})

FOLLOWUPS = {
    **dict.fromkeys((*ROOTS, PACKAGE, COURT), "Open Frame replacement"),
    "supply_drop_frame_context": "Review Supply Drop loss",
    "defeat": "Open assigned Defeat",
}


class MissionDesk:
    def __init__(self, missions: MissionService):
        self.missions = missions
        self.periods = OffDutyService(missions)
        self.reactions = ReactionService(missions)

    def view(self, viewer: GuildViewer, label: str, *, lifecycle: bool) -> dict[str, Any]:
        if lifecycle:
            control = MissionControlService(self.missions).view(viewer)
            return self._file_details(viewer, {"pilot": label, **control}, lifecycle=True)
        offers = []
        for row in self.missions.list(viewer):
            saved = self.missions.get(viewer, row["id"])
            mission = saved["mission"]
            offers.append(
                row
                | {
                    "phase": mission["phase"],
                    "revision": mission["revision"],
                    "response": mission["responses"].get(str(viewer.user_id)),
                    "success": mission["success"],
                    "debrief": mission.get("debrief"),
                    "pending_count": saved["pending_count"],
                    **(
                        {"briefing_terms": mission["briefing_terms"]}
                        if "briefing_terms" in mission
                        else {}
                    ),
                }
                | {
                    field: saved[field]
                    for field in ("briefing", "briefing_needs_review")
                    if field in saved
                }
            )
        return self._file_details(viewer, {"pilot": label, "offers": offers, "desk": None}, lifecycle=False)

    def _file_details(self, viewer, payload, *, lifecycle):
        offers = payload["offers"]
        filed_at = self.filing_dates([row["id"] for row in offers])
        owned = self.missions.owned_work(viewer) if lifecycle else ()
        for row in offers:
            row["filed_at"] = filed_at.get(row["id"])
            row["followups"] = [
                {"id": work["id"], "kind": work["kind"], "label": FOLLOWUPS[work["kind"]]}
                for work in owned
                if work["mission_id"] == row["id"]
                and work["owner_id"] == str(viewer.user_id)
                and work["kind"] in FOLLOWUPS
            ]
            if row["phase"] != "offered":
                continue
            mission = self.missions.get(viewer, row["id"])["mission"]
            wait = None
            if viewer.user_id in mission["offered_to"] and row["response"] is None:
                wait = "viewer"
            elif row["response"] != "decline" or payload["desk"] is not None:
                if len(mission["responses"]) < len(mission["offered_to"]):
                    wait = "invitees"
                else:
                    wait = "dispatch" if "accept" in mission["responses"].values() else "handler_review"
            row.update(needs_response=wait == "viewer", waiting_on=wait)
        return payload

    def filing_dates(self, mission_ids):
        """Read the original offer timestamps for the viewer's visible missions."""
        if not mission_ids:
            return {}
        store = self.missions.store
        history = tables.m3["m3_mission_history"]
        events = tables.events
        with store.engine.connect() as connection:
            return dict(connection.execute(
                sa.select(history.c.id, events.c.created_utc)
                .join(events, sa.and_(
                    events.c.campaign_id == history.c.campaign_id,
                    events.c.id == history.c.event_id,
                ))
                .where(
                    history.c.campaign_id == store.campaign_id,
                    history.c.id.in_(mission_ids),
                    history.c.revision == 1,
                    events.c.kind == "m3.mission_offered",
                )
            ).tuples().all())

    def perform(self, viewer: GuildViewer, key: str, data: dict[str, Any]) -> dict[str, Any]:
        with self.missions.store.engine.connect() as c:
            self.missions._authorize(c, viewer)
            self.missions._handler(c, viewer)
        action = data.get("action")
        fields = data.keys() - {"action"}
        if action == "offer" and {"objective", "pilots"} <= fields <= {
            "objective",
            "pilots",
            "capture_target",
            "hard_stake",
            "briefing_draft",
        }:
            objective, pilots = data["objective"], data["pilots"]
            capture_target = data.get("capture_target")
            hard_stake = data.get("hard_stake")
            briefing_draft = data.get("briefing_draft")
            if (
                not isinstance(objective, str)
                or not isinstance(pilots, list)
                or ("capture_target" in fields and not isinstance(capture_target, str))
                or ("hard_stake" in fields and not isinstance(hard_stake, str))
                or ("briefing_draft" in fields and not isinstance(briefing_draft, str))
                or any(
                    not isinstance(uid, str)
                    or not uid.isascii()
                    or not uid.isdecimal()
                    or len(uid) > 20
                    or not 0 < int(uid) < 2**64
                    for uid in pilots
                )
            ):
                raise ValueError("Use the current pilot roster and an objective.")
            return self.missions.offer(
                viewer,
                key,
                objective,
                tuple(map(int, pilots)),
                capture_target=capture_target,
                hard_stake=hard_stake,
                briefing_draft=briefing_draft,
            )
        if action == "off_duty" and not fields:
            return self.periods.begin(viewer, key)
        if action == "reaction" and fields == {
            "id",
            "revision",
            "game_revision",
            "answer",
        }:
            identity, revision, game_revision = (
                data[x] for x in ("id", "revision", "game_revision")
            )
            answer = data["answer"]
            if (
                not isinstance(identity, str)
                or type(revision) is not int
                or type(game_revision) is not int
                or not isinstance(answer, dict)
            ):
                raise ValueError("Use the current reaction form.")
            work = self.reactions.get(viewer, identity)
            reaction_args = (viewer, key, identity, revision, game_revision)
            if work["kind"] == "doctor_obsolescence" and answer == {"confirm": True}:
                return self.reactions.doctor(*reaction_args)
            if (
                work["kind"] == "princess_mission_end"
                and answer.keys() == {"upheld", "rationale"}
                and type(answer["upheld"]) is bool
                and isinstance(answer["rationale"], str)
            ):
                return self.reactions.princess(*reaction_args, **answer)
            raise ValueError("Use the fields assigned by HarpyEngine.")
        if not {"id", "revision"} <= fields:
            raise ValueError("Choose a current mission.")
        if not isinstance(data.get("id"), str) or type(data.get("revision")) is not int:
            raise ValueError("Choose a current mission revision.")
        args = (viewer, key, str(UUID(data["id"])), data["revision"])
        if action == "debrief" and fields == {"id", "revision", "success", "debrief"}:
            if type(data["success"]) is not bool or not isinstance(data["debrief"], str):
                raise ValueError("Record an outcome and optional debrief.")
            return self.missions.end(*args, data["success"], debrief=data["debrief"])
        if fields == {"id", "revision"} and isinstance(action, str):
            transition = {
                "dispatch": self.missions.start,
                "cancel": self.missions.cancel,
                "advance": self.missions.complete,
            }.get(action)
            if transition:
                return transition(*args)
        raise ValueError("Choose a current mission action.")
