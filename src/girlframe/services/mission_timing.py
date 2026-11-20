"""Authorized, receipt-backed fictional minutes for an opted-in mission scene."""

from collections.abc import Callable
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine.m3_missions import Mission
from girlframe.scenes.mission_timing import (
    Clock,
    Option,
    Options,
    Rejoin,
    Ruling,
    Selected,
    SequenceStart,
)
from girlframe.services import campaign_time_history as calendar
from girlframe.services import mission_timing_history as history
from girlframe.services.handler_setup import HandlerService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_missions import MissionService
from girlframe.services.onboarding import OnboardingStore, WorkflowError
from girlframe.services.read_only_bot import GuildViewer


class MissionTimingService:
    def __init__(self, store: OnboardingStore):
        self.store = store
        self.missions = MissionService(store)
        self.game = self.missions.game

    def _write(
        self,
        viewer: GuildViewer,
        key: str,
        command: str,
        payload: dict[str, Any],
        operation: Callable[[Connection], dict[str, Any]],
        *,
        handler: bool = True,
    ) -> dict[str, Any]:
        def authorize(c: Connection) -> None:
            self.missions.access.authorize(c, viewer, "missions")
            if handler:
                self.missions._handler(c, viewer)

        def apply(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            return operation(c)

        return self.store._write(
            viewer,
            key,
            f"timeline.timing_{command}",
            payload,
            apply,
            auto_audit=False,
            authorize=authorize,
        )

    def _record(
        self,
        c: Connection,
        viewer: GuildViewer,
        key: str,
        clock: Clock,
        transition: str,
        *,
        receipt: str | None = None,
        **details: Any,
    ) -> dict[str, Any]:
        receipt = self.store._audit(
            c,
            viewer.user_id,
            key,
            history.EVENT,
            {"clock": clock.model_dump(mode="json"), "transition": transition, **details},
            event_id=receipt,
            ruleset_version="mission-timing-v1",
        )
        return {
            "id": clock.id,
            "receipt": receipt,
            "status": transition,
            "minute": clock.minute,
            "deadline_status": clock.deadline.status(clock.minute),
        } | (
            {"consequence": clock.deadline.consequence}
            if clock.consequence_receipt == receipt
            else {}
        )

    def _require_settled_play(self, c: Connection) -> None:
        if self.game.pending_actions(c):
            raise WorkflowError("Resolve the pending Play before progressing mission timing.")

    def _current(self, c: Connection, identity: str, expected: str | None = None) -> Clock:
        value = history.current(c, self.store.campaign_id)
        if value is None or value[1].closed or value[1].id != identity:
            raise WorkflowError("This timed sequence is unavailable.")
        if expected is not None and value[0] != expected:
            raise WorkflowError("STALE_TIMING: refresh the current sequence.")
        return value[1]

    def _context(self, c: Connection, clock: Clock) -> tuple[Mission, dict[str, Any]]:
        mission = self.missions._mission(c, clock.mission)
        current = calendar.anchor(c, self.store.campaign_id)
        scene = self.game.scene(c, clock.channel)
        if (
            mission.phase != "active"
            or mission.handler != self.missions._current_handler(c)
            or current is None
            or current[0] != clock.anchor
            or scene["id"] != clock.scene
        ):
            raise WorkflowError("Recover the original active mission, scene and calendar anchor.")
        return mission, scene

    def _pilot(self, c: Connection, mission: Mission, scene: dict[str, Any], pilot: int) -> None:
        if (
            pilot not in scene["participants"]
            or pilot not in mission.participants
            or str(pilot) in mission.ended_participants
            or not HandlerService(self.store)._member(c, pilot)
        ):
            raise WorkflowError("Only actual joined and dispatched Pilots may use this option.")
        original = self.missions._source_characters(c, mission).get(str(pilot))
        state = load_state(c, self.store.campaign_id)
        if (
            original is None
            or str(pilot) not in state.sheets
            or self.game.character_binding(c, state, pilot, require_current_profile=False)
            != original
        ):
            raise WorkflowError(
                "Recover the originally dispatched Pilot before timing this action."
            )

    def open(
        self,
        viewer: GuildViewer,
        key: str,
        mission_id: str,
        mission_revision: int,
        channel: int,
        scene_id: str,
        expected_anchor: str,
        start: SequenceStart,
    ) -> dict[str, Any]:
        start = SequenceStart.model_validate_json(start.model_dump_json())
        payload = {
            "mission": mission_id,
            "mission_revision": mission_revision,
            "channel": channel,
            "scene": scene_id,
            "anchor": expected_anchor,
            "start": start.model_dump(mode="json"),
        }

        def operation(c: Connection) -> dict[str, Any]:
            if history.active(c, self.store.campaign_id) is not None:
                raise WorkflowError("Finish the current timed sequence first.")
            current = calendar.anchor(c, self.store.campaign_id)
            if current is None or current[0] != expected_anchor:
                raise WorkflowError("STALE_TIMING: refresh the fictional calendar anchor.")
            clock = Clock(
                id=str(uuid4()),
                mission=mission_id,
                scene=scene_id,
                channel=channel,
                anchor=current[0],
                day=current[1].position.day,
                minute=start.minute,
                deadline=start.deadline,
            )
            mission, scene = self._context(c, clock)
            if mission.revision != mission_revision:
                raise WorkflowError("STALE_MISSION: refresh the original dispatch.")
            if not set(mission.participants).intersection(scene["participants"]):
                raise WorkflowError("A dispatched Pilot must actually join the timed scene first.")
            self._require_settled_play(c)
            return self._record(c, viewer, key, clock, "opened")

        return self._write(viewer, key, "open", payload, operation)

    def publish_options(
        self, viewer: GuildViewer, key: str, identity: str, expected: str, options: Options
    ) -> dict[str, Any]:
        options = Options.model_validate_json(options.model_dump_json())

        def operation(c: Connection) -> dict[str, Any]:
            clock = self._current(c, identity, expected)
            mission, scene = self._context(c, clock)
            if clock.selected:
                raise WorkflowError("Resolve or withdraw the committed selections first.")
            self._require_settled_play(c)
            for uid in {option.pilot for option in options.available}:
                self._pilot(c, mission, scene, uid)
            if any(
                option.minutes and clock.minute + option.minutes >= 1440
                for option in options.available
            ):
                raise WorkflowError("Publish options that finish within the fictional day.")
            receipt = str(uuid4())
            clock.menu_receipt, clock.menu, clock.ruling = receipt, options, None
            return self._record(c, viewer, key, clock, "options_published", receipt=receipt)

        return self._write(
            viewer,
            key,
            "publish",
            {"id": identity, "expected": expected, "options": options.model_dump(mode="json")},
            operation,
        )

    def _ruling(
        self, c: Connection, viewer: GuildViewer, key: str, clock: Clock, ruling: Ruling
    ) -> dict[str, Any]:
        clock.ruling = ruling
        return self._record(c, viewer, key, clock, "ruling_required") | {"reason": ruling.reason}

    def _needs_consequence(self, clock: Clock, minute: int) -> bool:
        return (
            clock.deadline.status(minute) == "missed"
            and clock.consequence_receipt is None
            and clock.deadline.consequence is None
        )

    def _advance(
        self, c: Connection, viewer: GuildViewer, key: str, clock: Clock, minute: int, **source: Any
    ) -> dict[str, Any]:
        receipt = str(uuid4())
        before = clock.minute
        clock.minute = minute
        if clock.deadline.status(minute) == "missed" and clock.consequence_receipt is None:
            if clock.deadline.consequence is None:
                raise WorkflowError("The missed deadline requires a Handler ruling.")
            clock.consequence_receipt = receipt
        clock.menu_receipt, clock.menu, clock.selected, clock.ruling = None, None, (), None
        return self._record(
            c,
            viewer,
            key,
            clock,
            "advanced",
            receipt=receipt,
            from_minute=before,
            **source,
        )

    def choose(
        self, viewer: GuildViewer, key: str, identity: str, menu_receipt: str, option_id: str
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            clock = self._current(c, identity)
            mission, scene = self._context(c, clock)
            self._pilot(c, mission, scene, viewer.user_id)
            if clock.menu is None or clock.menu_receipt != menu_receipt:
                raise WorkflowError("STALE_TIMING: refresh the published options.")
            option = next(
                (
                    x
                    for x in clock.menu.available
                    if x.id == option_id and x.pilot == viewer.user_id
                ),
                None,
            )
            if option is None:
                raise WorkflowError("Choose one of your own published options.")
            if clock.ruling is not None:
                raise WorkflowError("Wait for the Handler ruling before committing an option.")
            self._require_settled_play(c)
            if any(x.option.pilot == viewer.user_id for x in clock.selected):
                raise WorkflowError("Your choice for this exchange is already saved.")
            if option.minutes is None:
                return self._ruling(
                    c,
                    viewer,
                    key,
                    clock,
                    Ruling(reason="unknown_duration", option=option.id, pilot=viewer.user_id),
                )
            end = clock.minute + option.minutes
            if clock.menu.mode == "single" and self._needs_consequence(clock, end):
                return self._ruling(
                    c,
                    viewer,
                    key,
                    clock,
                    Ruling(reason="unknown_consequence", option=option.id, pilot=viewer.user_id),
                )
            if clock.menu.mode == "single" and option.play is None:
                return self._advance(
                    c,
                    viewer,
                    key,
                    clock,
                    end,
                    menu=menu_receipt,
                    option=option.id,
                )
            receipt = str(uuid4())
            clock.selected += (Selected(receipt=receipt, option=option),)
            return self._record(
                c,
                viewer,
                key,
                clock,
                "play_selected" if option.play else "parallel_selected",
                receipt=receipt,
            )

        return self._write(
            viewer,
            key,
            "choose",
            {"id": identity, "menu": menu_receipt, "option": option_id},
            operation,
            handler=False,
        )

    def declare_consequence(
        self, viewer: GuildViewer, key: str, identity: str, expected: str, consequence: str
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            clock = self._current(c, identity, expected)
            self._context(c, clock)
            if clock.deadline.consequence is not None:
                raise WorkflowError("The declared deadline consequence is already fixed.")
            clock.deadline.consequence = consequence
            if clock.ruling is not None and clock.ruling.reason == "unknown_consequence":
                clock.ruling = None
            receipt = str(uuid4())
            if clock.menu is not None:
                clock.menu_receipt = receipt
            return self._record(c, viewer, key, clock, "consequence_declared", receipt=receipt)

        return self._write(
            viewer,
            key,
            "consequence",
            {"id": identity, "expected": expected, "consequence": consequence},
            operation,
        )

    def resolve_parallel(
        self, viewer: GuildViewer, key: str, identity: str, expected: str, rejoin: Rejoin
    ) -> dict[str, Any]:
        rejoin = Rejoin.model_validate_json(rejoin.model_dump_json())

        def operation(c: Connection) -> dict[str, Any]:
            clock = self._current(c, identity, expected)
            mission, scene = self._context(c, clock)
            if clock.menu is None or clock.menu.mode != "parallel" or not clock.selected:
                raise WorkflowError("Record actual Pilot selections in a parallel exchange first.")
            if clock.ruling is not None:
                raise WorkflowError("Resolve the pending Handler ruling first.")
            if rejoin.minute <= clock.minute:
                raise WorkflowError("Rejoin after the common starting minute.")
            self._require_settled_play(c)
            elapsed = rejoin.minute - clock.minute
            for item in clock.selected:
                self._pilot(c, mission, scene, item.option.pilot)
                assert item.option.minutes is not None
                if not item.option.estimated and elapsed < item.option.minutes:
                    raise WorkflowError(
                        "Allow enough time for each committed fixed-duration action."
                    )
            if self._needs_consequence(clock, rejoin.minute):
                return self._ruling(
                    c,
                    viewer,
                    key,
                    clock,
                    Ruling(reason="unknown_consequence", proposed_rejoin=rejoin),
                )
            return self._advance(
                c,
                viewer,
                key,
                clock,
                rejoin.minute,
                selections=[x.receipt for x in clock.selected],
                account=rejoin.account,
            )

        return self._write(
            viewer,
            key,
            "parallel",
            {"id": identity, "expected": expected, "rejoin": rejoin.model_dump(mode="json")},
            operation,
        )

    def _play_choice(
        self, c: Connection, viewer: GuildViewer, selection: str, scene_id: str, play: str
    ) -> tuple[Clock, Option]:
        clock = history.active(c, self.store.campaign_id)
        if clock is None or clock.scene != scene_id or len(clock.selected) != 1:
            raise WorkflowError("Refresh your current timed Play selection.")
        chosen = clock.selected[0]
        if (
            chosen.receipt != selection
            or chosen.option.pilot != viewer.user_id
            or chosen.option.play != play
        ):
            raise WorkflowError("This action needs your own matching timed Play selection.")
        mission, scene = self._context(c, clock)
        self._pilot(c, mission, scene, viewer.user_id)
        return clock, chosen.option

    def _attached(self, c: Connection, selection: str) -> bool:
        table = t.m2["m2_actions"]
        return (
            c.scalar(
                sa.select(table.c.id)
                .where(
                    table.c.campaign_id == self.store.campaign_id,
                    sa.func.json_extract(table.c.body_json, "$.mission_timing") == selection,
                    sa.or_(
                        table.c.state != "aborted",
                        sa.func.json_extract(table.c.body_json, "$.shared_recovery").is_not(None),
                    ),
                )
                .limit(1)
            )
            is not None
        )

    def attach_play(
        self, c: Connection, viewer: GuildViewer, selection: str, scene_id: str, play: str
    ) -> None:
        self.missions.access.authorize(c, viewer, "missions")
        self._play_choice(c, viewer, selection, scene_id, play)
        if self._attached(c, selection):
            raise WorkflowError("Recover the original Play tied to this selection.")

    def prepare_roll(self, c: Connection, viewer: GuildViewer, action: dict[str, Any]) -> Clock:
        self.missions.access.authorize(c, viewer, "missions")
        clock, option = self._play_choice(
            c, viewer, action["data"]["mission_timing"], action["scene_id"], action["data"]["play"]
        )
        assert option.minutes is not None
        if self._needs_consequence(clock, clock.minute + option.minutes):
            raise WorkflowError("The timed Play requires a Handler ruling before rolling.")
        return clock

    def record_play(
        self,
        c: Connection,
        viewer: GuildViewer,
        action: dict[str, Any],
        play_receipt: str,
        clock: Clock,
    ) -> None:
        chosen = clock.selected[0]
        assert chosen.option.minutes is not None
        self._advance(
            c,
            viewer,
            f"mission-timing:play:{action['id']}",
            clock,
            clock.minute + chosen.option.minutes,
            selection=chosen.receipt,
            action_id=action["id"],
            play_receipt=play_receipt,
        )

    def withdraw_play(
        self, viewer: GuildViewer, key: str, identity: str, selection: str
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            clock = self._current(c, identity)
            self._play_choice(c, viewer, selection, clock.scene, "keep_your_head")
            if self._attached(c, selection):
                raise WorkflowError("Resolve or cancel the original attached Play first.")
            clock.selected = ()
            return self._record(c, viewer, key, clock, "play_withdrawn", selection=selection)

        return self._write(
            viewer,
            key,
            "withdraw",
            {"id": identity, "selection": selection},
            operation,
            handler=False,
        )

    def close(self, viewer: GuildViewer, key: str, identity: str, expected: str) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            clock = self._current(c, identity, expected)
            self._context(c, clock)
            if clock.selected or clock.ruling is not None:
                raise WorkflowError("Resolve the saved selections and rulings before closing.")
            self._require_settled_play(c)
            clock.closed = True
            clock.menu_receipt, clock.menu = None, None
            return self._record(c, viewer, key, clock, "closed")

        return self._write(viewer, key, "close", {"id": identity, "expected": expected}, operation)

    @staticmethod
    def _option_view(clock: Clock, option: Option) -> dict[str, Any]:
        arrival = clock.minute + option.minutes if option.minutes is not None else None
        return option.model_dump(mode="json") | {
            "pilot": str(option.pilot),
            "arrival_minute": arrival,
            "projected_deadline_status": clock.deadline.status(arrival)
            if arrival is not None
            else None,
        }

    def project(self, c: Connection, viewer: GuildViewer) -> dict[str, Any] | None:
        self.game.authorize(c, viewer, game=False)
        value = history.current(c, self.store.campaign_id)
        if value is None or value[1].closed:
            return None
        receipt, clock = value
        try:
            mission, scene = self._context(c, clock)
            handler = (
                viewer.user_id == mission.handler == load_state(c, self.store.campaign_id).handler
            )
            if not handler:
                self._pilot(c, mission, scene, viewer.user_id)
        except WorkflowError:
            return None
        result = {
            "id": clock.id,
            "mission": clock.mission,
            "scene": clock.scene,
            "day": clock.day,
            "revision": receipt,
            "minute": clock.minute,
            "deadline": clock.deadline.model_dump(),
            "deadline_status": clock.deadline.status(clock.minute),
            "consequence_receipt": clock.consequence_receipt,
            "menu_receipt": clock.menu_receipt,
            "mode": clock.menu.mode if clock.menu else None,
            "options": [
                self._option_view(clock, x)
                for x in (clock.menu.available if clock.menu else ())
                if handler or x.pilot == viewer.user_id
            ],
            "selected": [
                {"receipt": x.receipt, "option": x.option.id}
                for x in clock.selected
                if handler or x.option.pilot == viewer.user_id
            ],
        }
        if clock.ruling and (handler or clock.ruling.pilot == viewer.user_id):
            result["ruling"] = clock.ruling.model_dump(mode="json", exclude={"pilot"})
        return result
