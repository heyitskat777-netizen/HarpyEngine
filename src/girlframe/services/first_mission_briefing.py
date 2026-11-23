"""Private, human-reviewed first mission briefing for a bot-managed opening."""

import json
from typing import Any
from uuid import UUID

from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine.campaign_opening import Opening
from girlframe.services import campaign_time_history as calendar
from girlframe.services.campaign_difficulty import briefing, historical_mission, opening
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.onboarding import OnboardingStore, WorkflowError
from girlframe.services.read_only_bot import GuildViewer
from girlframe.services.session_zero import SessionZeroService

REVIEWED = "campaign.first_mission_briefing_reviewed"


class FirstMissionBriefing:
    def __init__(self, store: OnboardingStore):
        self.store = store
        self.game = GameService(store)
        self.zero = SessionZeroService(store)

    def enable_ai(self, c: Connection, viewer: GuildViewer, key: str, mission: str) -> None:
        from girlframe.services.director_observation import DirectorObservationService

        self._context(c, viewer)
        observer = DirectorObservationService(
            self.store, activity_shadow=True, reviewed_activity_trial=True
        )
        policy = observer._activity_policy(c)
        if not policy["enabled"]:
            self.store._audit(
                c, viewer.user_id, key, observer._activity_event(),
                {"enabled": True, "revision": policy["revision"] + 1, "first_mission": mission},
                event_index=1,
            )

    def _context(self, c: Connection, viewer: GuildViewer) -> Opening:
        current = self.zero._latest(c)
        self.zero._group_member(c, viewer, current)
        record = opening(c, self.store.campaign_id)
        bot = self.store.policy.application_id
        if (
            record is None
            or record.handler != bot
            or self.zero.handler.current(c)[1].handler_id != bot
            or load_state(c, self.store.campaign_id).handler != bot
            or record.facilitator != viewer.user_id
            or current.facilitator != viewer.user_id
            or not current.plan_approved
            or current.plan_proposal != record.plan
            or not self.zero._active_group(c, current)
        ):
            raise WorkflowError(
                "The approved facilitator reviews the first briefing for HarpyEngine."
            )
        return record

    def _pilots(self, c: Connection) -> dict[str, str]:
        current = self.zero._latest(c)
        state = load_state(c, self.store.campaign_id)
        return {
            str(owner): sheet.callsign
            for owner in current.pilots
            if (sheet := state.sheets.get(str(owner))) is not None
            and not sheet.frame_scrapped
            and not self.game.immediate_work(c, owner)
        }

    def _receipts(self, viewer: GuildViewer):
        return calendar.query(self.store.campaign_id, REVIEWED).where(
            t.events.c.actor_id == str(viewer.user_id)
        )

    def view(self, viewer: GuildViewer) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            record = self._context(c, viewer)
            anchor = calendar.anchor(c, self.store.campaign_id)
            offered = historical_mission(c, self.store.campaign_id)
            row = c.execute(
                self._receipts(viewer)
                .with_only_columns(t.events.c.id, t.events.c.payload_json)
                .order_by(t.events.c.seq.desc())
                .limit(1)
            ).one_or_none()
            reviewed = json.loads(row.payload_json) if row is not None else None
            pilots = self._pilots(c)
            if reviewed is not None and (
                reviewed["plan"] != record.plan
                or anchor is None
                or reviewed["anchor"] != anchor[0]
                or not set(reviewed["pilots"]) <= pilots.keys()
                or self._characters(c, reviewed["pilots"]) != reviewed["characters"]
            ):
                reviewed = None
            return {
                "ready": anchor is not None
                and anchor[1].position.day >= record.first_mission_day
                and not offered,
                "offered": offered,
                "pilots": [{"id": owner, "name": name} for owner, name in pilots.items()],
                "review": {
                    "id": row.id,
                    "objective": reviewed["objective"],
                    "pilots": reviewed["pilots"],
                }
                if reviewed is not None
                else None,
            }

    def _characters(self, c: Connection, pilots: tuple[str, ...] | list[str]) -> dict[str, str]:
        state = load_state(c, self.store.campaign_id)
        return {
            owner: self.game.character_binding(c, state, int(owner), require_current_profile=False)
            for owner in pilots
        }

    def review(
        self, viewer: GuildViewer, key: str, anchor: str, objective: str, pilots: tuple[int, ...]
    ):
        objective = objective.strip()
        players = tuple(sorted(pilots))
        identities = tuple(map(str, players))
        if not 1 <= len(objective) <= 1200:
            raise WorkflowError("Write one introductory objective of 1–1200 characters.")
        if not players or len(set(players)) != len(players):
            raise WorkflowError("Choose distinct Pilots from the approved group.")

        def apply(c: Connection) -> dict[str, Any]:
            record = self._context(c, viewer)
            current_anchor = calendar.anchor(c, self.store.campaign_id)
            if current_anchor is None or anchor != current_anchor[0]:
                raise WorkflowError("Refresh the introduction before reviewing its first briefing.")
            self.game.unpaused(c)
            if historical_mission(c, self.store.campaign_id):
                raise WorkflowError("The first mission already has an offer.")
            briefing(c, self.store.campaign_id, players, None)
            if not set(identities) <= self._pilots(c).keys():
                raise WorkflowError("Choose current Pilots from the approved Session Zero group.")
            receipt = self.store._audit(
                c,
                viewer.user_id,
                key,
                REVIEWED,
                {
                    "plan": record.plan,
                    "anchor": anchor,
                    "pilots": identities,
                    "objective": objective,
                    "characters": self._characters(c, identities),
                },
                ruleset_version="session-zero-v1",
            )
            return {"id": receipt}

        return self.store._write(
            viewer,
            key,
            REVIEWED,
            {
                "anchor": anchor,
                "pilots": identities,
                "objective": objective,
            },
            apply,
            authorize=lambda c: self._context(c, viewer),
            auto_audit=False,
        )

    def receipt(
        self, c: Connection, viewer: GuildViewer, identity: str
    ) -> tuple[Opening, dict[str, Any]]:
        record = self._context(c, viewer)
        raw = c.scalar(
            self._receipts(viewer)
            .with_only_columns(t.events.c.payload_json)
            .where(t.events.c.id == str(UUID(identity)))
        )
        reviewed = json.loads(raw) if raw is not None else None
        if reviewed is None or reviewed["plan"] != record.plan:
            raise WorkflowError("Use your approved briefing for this opening.")
        return record, reviewed

    def confirm_offer(
        self,
        c: Connection,
        viewer: GuildViewer,
        identity: str,
        objective: str,
        pilots: tuple[int, ...],
    ) -> int:
        record, reviewed = self.receipt(c, viewer, identity)
        latest = c.scalar(
            self._receipts(viewer)
            .with_only_columns(t.events.c.id)
            .order_by(t.events.c.seq.desc())
            .limit(1)
        )
        anchor = calendar.anchor(c, self.store.campaign_id)
        if (
            latest != identity
            or anchor is None
            or reviewed["anchor"] != anchor[0]
            or objective != reviewed["objective"]
            or tuple(map(str, pilots)) != tuple(reviewed["pilots"])
            or not set(reviewed["pilots"]) <= self._pilots(c).keys()
            or self._characters(c, reviewed["pilots"]) != reviewed["characters"]
        ):
            raise WorkflowError(
                "The briefing, day or pilot sheets changed. Review the briefing again."
            )
        if historical_mission(c, self.store.campaign_id):
            raise WorkflowError("The first mission already has an offer.")
        return record.handler
