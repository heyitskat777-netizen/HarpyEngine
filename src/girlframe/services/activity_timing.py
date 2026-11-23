"""Authenticated Activity access to the existing human-owned time commands."""

import json
from typing import Any

from pydantic import TypeAdapter

from girlframe.engine.m2 import PlayInput
from girlframe.scenes.campaign_time import Account, Anchor, Cut, LateSubmission, ScenePlan
from girlframe.scenes.mission_timing import Options, Rejoin, SequenceStart
from girlframe.services.campaign_time import CampaignTimeService
from girlframe.services.director_timing_review import pending_ruling
from girlframe.services.handler_setup import HandlerService
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.mission_timing import MissionTimingService
from girlframe.services.mission_timing_history import active as active_timing
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer


def _snowflake(raw: object) -> int:
    if not isinstance(raw, str) or not raw.isascii() or not raw.isdecimal() or len(raw) > 20:
        raise ValueError("Use an exact server identity.")
    value = int(raw)
    if str(value) != raw or not 0 < value < 2**64:
        raise ValueError("Use an exact server identity.")
    return value


class ActivityTiming:
    def __init__(self, game: GameService):
        self.game, self.store = game, game.store
        self.calendar = CampaignTimeService(self.store)
        self.timing = MissionTimingService(self.store)

    def view(self, viewer: GuildViewer) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            c.exec_driver_sql("BEGIN")
            view = self.calendar._projection(c, viewer)
            state = load_state(c, self.store.campaign_id)
            clock = view.get("mission_timing")
            active = active_timing(c, self.store.campaign_id) if clock else None
            try:
                self.calendar._handler(c, viewer)
            except WorkflowError:
                pass
            else:
                eligible = []
                if active is not None:
                    mission, scene = self.timing._context(c, active)
                    for uid in mission.participants:
                        try:
                            self.timing._pilot(c, mission, scene, uid)
                        except WorkflowError:
                            continue
                        eligible.append(str(uid))
                view["handler_controls"] = {
                    "pilots": [
                        {"id": str(uid), "label": state.sheets[str(uid)].callsign}
                        for uid in state.order
                        if str(uid) in state.sheets and HandlerService(self.store)._member(c, uid)
                    ],
                    "active_mission": next(
                        (
                            record
                            for record in self.calendar._phase(c)
                            if record["kind"] == "mission" and record["phase"] == "active"
                        ),
                        None,
                    ),
                    "clock_pilots": eligible,
                }
            view["viewer"] = str(viewer.user_id)
            if clock is not None and active is not None:
                clock["channel"] = str(active.channel)
                if "handler_controls" in view and (
                    ruling := pending_ruling(c, self.store.campaign_id, active.scene)
                ):
                    view["timing_ruling"] = ruling
            if clock and (sheet := state.sheets.get(str(viewer.user_id))) is not None:
                view["sheet_revision"] = sheet.revision
        return view

    def write(
        self, viewer: GuildViewer, key: str, route: str, data: dict[str, Any]
    ) -> dict[str, Any]:
        if route == "time-initialize" and data.keys() == {"anchor"}:
            return self.calendar.initialize(viewer, key, Anchor.model_validate(data["anchor"]))
        if route == "time-schedule" and data.keys() == {
            "channel",
            "scene",
            "revision",
            "anchor",
            "plan",
        }:
            plan = data["plan"]
            if not isinstance(plan, dict) or not isinstance(plan.get("participants"), list):
                raise ValueError("Select actual scheduled participants.")
            booking = ScenePlan.model_validate_json(
                json.dumps(
                    plan | {"participants": [_snowflake(uid) for uid in plan["participants"]]}
                )
            )
            return self.calendar.schedule(
                viewer,
                key,
                _snowflake(data["channel"]),
                data["scene"],
                data["revision"],
                data["anchor"],
                booking,
            )
        if route == "time-preview" and data.keys() == {"cut"}:
            return self.calendar.preview_cut(
                viewer, Cut.model_validate_json(json.dumps(data["cut"]))
            )
        if route == "time-cut" and data.keys() == {"cut", "token"}:
            return self.calendar.commit_cut(
                viewer, key, Cut.model_validate_json(json.dumps(data["cut"])), data["token"]
            )
        if route == "time-late" and data.keys() == {"scene", "cut", "entry"}:
            entry = data["entry"]
            if not isinstance(entry, dict) or not isinstance(entry.get("recipients", []), list):
                raise ValueError("Select exact late-scene recipients.")
            submission = LateSubmission.model_validate_json(
                json.dumps(
                    entry
                    | {
                        "recipients": [_snowflake(uid) for uid in entry.get("recipients", [])],
                    }
                )
            )
            return self.calendar.record_late(viewer, key, data["scene"], data["cut"], submission)
        if route == "time-late-close" and data.keys() == {"scene", "cut"}:
            return self.calendar.close_late(viewer, key, data["scene"], data["cut"])
        if route == "time-open" and data.keys() == {
            "mission",
            "revision",
            "channel",
            "scene",
            "anchor",
            "start",
        }:
            return self.timing.open(
                viewer,
                key,
                data["mission"],
                data["revision"],
                _snowflake(data["channel"]),
                data["scene"],
                data["anchor"],
                SequenceStart.model_validate(data["start"]),
            )
        if route == "time-publish" and data.keys() == {"id", "revision", "options"}:
            opts = data["options"]
            if not isinstance(opts, dict) or not isinstance(opts.get("available"), list):
                raise ValueError("Enter actual options for original Pilots.")
            if any(not isinstance(item, dict) for item in opts["available"]):
                raise ValueError("Enter an actual option.")
            options = Options.model_validate_json(
                json.dumps(
                    opts
                    | {
                        "available": [
                            item | {"pilot": _snowflake(item.get("pilot"))}
                            for item in opts["available"]
                        ]
                    }
                )
            )
            return self.timing.publish_options(viewer, key, data["id"], data["revision"], options)
        if route == "time-choose" and data.keys() == {"id", "menu", "option"}:
            return self.timing.choose(viewer, key, data["id"], data["menu"], data["option"])
        if route == "time-consequence" and data.keys() == {"id", "revision", "account"}:
            account = TypeAdapter(Account).validate_python(data["account"], strict=True)
            return self.timing.declare_consequence(
                viewer, key, data["id"], data["revision"], account
            )
        if route == "time-rejoin" and data.keys() == {"id", "revision", "rejoin"}:
            return self.timing.resolve_parallel(
                viewer, key, data["id"], data["revision"], Rejoin.model_validate(data["rejoin"])
            )
        if route == "time-close" and data.keys() == {"id", "revision"}:
            return self.timing.close(viewer, key, data["id"], data["revision"])
        if route == "time-withdraw" and data.keys() == {"id", "selection"}:
            return self.timing.withdraw_play(viewer, key, data["id"], data["selection"])
        if route == "time-begin-play" and data.keys() == {
            "channel",
            "sheet_revision",
            "selection",
            "context",
            "heat",
        }:
            if type(data["sheet_revision"]) is not int or not isinstance(data["selection"], str):
                raise ValueError("Use the active Pilot sheet and saved selection.")
            prepared = PlayInput.model_validate(
                {
                    "play": "keep_your_head",
                    "context": data["context"],
                    "trigger_confirmed": True,
                    "heat": data["heat"],
                }
            )
            return self.game.begin(
                viewer,
                key,
                _snowflake(data["channel"]),
                data["sheet_revision"],
                prepared,
                timing_selection=data["selection"],
            )
        raise ValueError("Unknown or malformed fictional time command.")
