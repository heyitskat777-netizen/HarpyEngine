"""Authenticated Activity entry points for the campaign's Session Zero."""

import json
from typing import Any, cast

from pydantic import TypeAdapter

from girlframe.engine.campaign_opening import DIFFICULTIES, CampaignSeats, Difficulty
from girlframe.engine.identity import Snowflake
from girlframe.engine.m3_handler_state import PLAYBOOKS
from girlframe.engine.pilot_portrayal import PILOT_CALLSIGNS, PILOT_PORTRAYALS
from girlframe.engine.playbooks import FRAME_TYPES, GIRL_TYPES
from girlframe.engine.session_zero import MAX_GROUP, CharacterNotes, HandlerProfile, StartingStatus
from girlframe.services.first_mission_briefing import FirstMissionBriefing
from girlframe.services.m3_missions import MissionService
from girlframe.services.read_only_bot import GuildViewer
from girlframe.services.session_zero import SessionZeroService

READS = frozenset({"session-zero", "session-zero-worksheet"})
WRITES = {
    "session-zero-group": {"revision", "members"},
    "session-zero-propose": {"revision", "profile"},
    "session-zero-handler-vote": {"proposal", "approve"},
    "session-zero-appoint": {"setup_revision", "proposal", "nominee"},
    "session-zero-attach": {"revision"},
    "session-zero-notes": {"revision", "notes"},
    "session-zero-plan": {"revision", "goals", "difficulty", "seats"},
    "session-zero-plan-vote": {"proposal", "approve"},
    "session-zero-open": {"revision", "introduction", "days"},
    "session-zero-advance": {"anchor"},
    "session-zero-post": {"anchor", "text"},
    "session-zero-briefing-review": {"anchor", "objective", "pilots"},
    "session-zero-briefing-offer": {"review"},
}


def _member(value: Any) -> int:
    if (
        not isinstance(value, str)
        or len(value) > 20
        or not value.isascii()
        or not value.isdecimal()
    ):
        raise ValueError("Choose an exact campaign member.")
    return TypeAdapter(Snowflake).validate_python(int(value))


class SessionZeroDesk:
    def __init__(self, service: SessionZeroService, channel: int | None):
        self.service = service
        self.channel = channel
        self.first_briefing = FirstMissionBriefing(service.store)

    def read(self, viewer: GuildViewer, route: str) -> dict[str, Any]:
        state = self.service.view(viewer)
        if route == "session-zero-worksheet":
            return {"worksheet": self.service.generate(viewer, state["revision"])}
        if (
            state.get("bot_managed")
            and state.get("opening")
            and state["opening"]["handler"] == state["handler_ready"]
            and state.get("facilitator") == viewer.user_id
        ):
            state["first_briefing"] = self.first_briefing.view(viewer)
        for key in ("nominee", "appointed", "handler_ready"):
            if state[key] is not None:
                state[key] = str(state[key])
        if state.get("facilitator") is not None:
            state["facilitator"] = str(state["facilitator"])
        for key in ("members", "group_options"):
            if key in state:
                state[key] = [str(member) for member in state[key]]
        if state.get("profile"):
            state["profile"]["member"] = str(state["profile"]["member"])
        if state.get("opening"):
            for key in ("handler", "channel", "facilitator"):
                if key in state["opening"]:
                    state["opening"][key] = str(state["opening"][key])
        state.update(viewer=str(viewer.user_id), playbooks=PLAYBOOKS, limit=MAX_GROUP)
        if state["handler_ready"] == state["viewer"] and state.get("opening") is None:
            state["pilot_generator"] = {
                "callsigns": PILOT_CALLSIGNS,
                "portrayals": tuple(item.model_dump(mode="json") for item in PILOT_PORTRAYALS),
                "girl_types": GIRL_TYPES,
                "frame_types": FRAME_TYPES,
            }
        return state

    def write(
        self, viewer: GuildViewer, key: str, route: str, data: dict[str, Any]
    ) -> dict[str, Any]:
        fields = WRITES.get(route)
        if route == "session-zero-briefing-offer" and "enable_ai" in data:
            fields = WRITES[route] | {"enable_ai"}
        if route == "session-zero-plan" and "facilitator" in data:
            fields = WRITES[route] | {"facilitator"}
            if "facilitator_only" in data:
                fields |= {"facilitator_only"}
        if route == "session-zero-plan" and "starting_status" in data:
            fields = (fields or set()) | {"starting_status"}
        if fields != data.keys():
            raise ValueError("Use the current Session Zero form.")
        service = self.service
        for field in ("revision", "setup_revision", "days"):
            if field in data and (type(data[field]) is not int or data[field] < 0):
                raise ValueError("Use the saved revision or an exact day count.")
        for field in ("proposal", "anchor", "goals", "introduction", "text", "objective", "review"):
            if field in data and not isinstance(data[field], str):
                raise ValueError("Use text and the original receipt identifiers.")
        if route.endswith("-vote"):
            if type(data["approve"]) is not bool:
                raise ValueError("Choose your own approval decision.")
            vote = service.decide_plan if route == "session-zero-plan-vote" else service.decide
            return vote(viewer, key, data["proposal"], approve=data["approve"])
        if route == "session-zero-post":
            return service.post_intro(viewer, key, data["anchor"], data["text"])
        if route == "session-zero-advance":
            return service.advance_opening(viewer, key, data["anchor"])
        if route == "session-zero-briefing-review":
            if not isinstance(data["pilots"], list) or len(data["pilots"]) > MAX_GROUP:
                raise ValueError("Choose Pilots from the approved Session Zero group.")
            pilots = tuple(_member(owner) for owner in data["pilots"])
            return self.first_briefing.review(
                viewer, key, data["anchor"], data["objective"], pilots
            )
        if route == "session-zero-briefing-offer":
            enable_ai = data.get("enable_ai", False)
            if type(enable_ai) is not bool:
                raise ValueError("Choose whether to enable the reviewed AI roles.")
            with service.store.engine.connect() as c:
                _, review = self.first_briefing.receipt(c, viewer, data["review"])
            return MissionService(service.store).offer(
                viewer,
                key,
                review["objective"],
                tuple(map(int, review["pilots"])),
                reviewed_first_briefing=data["review"],
                enable_reviewed_ai=enable_ai,
            )
        if route == "session-zero-appoint":
            return service.appoint(
                viewer, key, data["setup_revision"], data["proposal"], _member(data["nominee"])
            )
        args = (viewer, key, data["revision"])
        if route == "session-zero-group":
            if not isinstance(data["members"], list) or len(data["members"]) > MAX_GROUP:
                raise ValueError("Choose the participating campaign members.")
            return service.set_group(*args, tuple(_member(value) for value in data["members"]))
        if route == "session-zero-propose":
            raw = data["profile"]
            if not isinstance(raw, dict) or "member" not in raw:
                raise ValueError("Choose a Handler portrayal and its controller.")
            return service.propose(
                *args, HandlerProfile.model_validate(raw | {"member": _member(raw["member"])})
            )
        if route == "session-zero-attach":
            return service.attach(*args)
        if route == "session-zero-notes":
            return service.notes(*args, CharacterNotes.model_validate(data["notes"]))
        if route == "session-zero-plan":
            if data["difficulty"] not in DIFFICULTIES:
                raise ValueError("Choose Narrative, Normal or Hard difficulty.")
            mode = cast(Difficulty, data["difficulty"])
            seats = CampaignSeats.model_validate_json(json.dumps(data["seats"]))
            facilitator = _member(data["facilitator"]) if "facilitator" in data else None
            facilitator_only = data.get("facilitator_only", False)
            if type(facilitator_only) is not bool:
                raise ValueError("Choose whether the facilitator also takes a Pilot seat.")
            status = data.get("starting_status")
            if status is not None and (
                not isinstance(status, dict) or status.keys() != {"ace", "dog"}
            ):
                raise ValueError("Choose Ace and Dog from the Session Zero group.")
            return service.goals(
                *args,
                data["goals"],
                mode,
                seats,
                facilitator=facilitator,
                facilitator_only=facilitator_only,
                starting_status=(
                    StartingStatus(ace=_member(status["ace"]), dog=_member(status["dog"]))
                    if status is not None
                    else None
                ),
            )
        if route == "session-zero-open" and self.channel is not None:
            return service.complete(
                *args, self.channel, data["introduction"], data["days"], reuse_empty=True
            )
        raise ValueError("Session Zero needs its campaign-bound Activity scene.")
