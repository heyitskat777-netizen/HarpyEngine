"""Present native mission transitions and their assigned work in the Activity."""

from uuid import UUID

from girlframe.services.m3_mission_control import MissionControlService
from girlframe.services.m3_off_duty import OffDutyService
from girlframe.services.m3_reactions import ReactionService

REACTIONS = frozenset({"princess_mission_end", "doctor_obsolescence"})


class MissionDesk:
    def __init__(self, missions):
        self.missions = missions
        self.periods = OffDutyService(missions)
        self.reactions = ReactionService(missions)

    def view(self, viewer, label, *, lifecycle):
        if lifecycle:
            return {"pilot": label, **MissionControlService(self.missions).view(viewer)}
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
                }
            )
        return {"pilot": label, "offers": offers, "desk": None}

    def perform(self, viewer, key, data):
        with self.missions.store.engine.connect() as c:
            self.missions._authorize(c, viewer)
            self.missions._handler(c, viewer)
        action = data.get("action")
        fields = data.keys() - {"action"}
        if action == "offer" and fields in (
            {"objective", "pilots"},
            {"objective", "pilots", "capture_target"},
        ):
            objective, pilots = data["objective"], data["pilots"]
            capture_target = data.get("capture_target")
            if (
                not isinstance(objective, str)
                or not isinstance(pilots, list)
                or ("capture_target" in fields and not isinstance(capture_target, str))
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
                viewer, key, objective, tuple(map(int, pilots)), capture_target=capture_target
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
            args = (viewer, key, identity, revision, game_revision)
            if work["kind"] == "doctor_obsolescence" and answer == {"confirm": True}:
                return self.reactions.doctor(*args)
            if (
                work["kind"] == "princess_mission_end"
                and answer.keys() == {"upheld", "rationale"}
                and type(answer["upheld"]) is bool
                and isinstance(answer["rationale"], str)
            ):
                return self.reactions.princess(*args, **answer)
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
