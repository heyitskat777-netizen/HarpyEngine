"""Campaign-scoped Session Zero intake and group-only worksheet generation."""

import hashlib
import json
import re
from collections.abc import Callable
from html import escape
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine.campaign_opening import (
    DIFFICULTY_DESCRIPTIONS,
    CampaignSeats,
    Difficulty,
    Opening,
)
from girlframe.engine.identity import Snowflake
from girlframe.engine.m2 import GameState
from girlframe.engine.session_zero import (
    MAX_GROUP,
    CharacterNotes,
    CharacterSubmission,
    HandlerProfile,
    SessionZero,
    SheetReference,
)
from girlframe.services import campaign_time_history as calendar
from girlframe.services import session_zero_opening as introduction
from girlframe.services.campaign_difficulty import historical_mission, opening
from girlframe.services.creation_review import CreationReviewService
from girlframe.services.handler_setup import HandlerService
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.onboarding import OnboardingStore, WorkflowError
from girlframe.services.read_only_bot import GuildViewer

EVENT = "campaign.session_zero_saved"
INTRO_POST = "session_zero.introductory_post"


class SessionZeroService:
    def __init__(
        self,
        store: OnboardingStore,
        *,
        group_owner: int | None = None,
        setup_organizer: int | None = None,
    ):
        self.store = store
        self.handler = HandlerService(store)
        self.reviews = CreationReviewService(store)
        self.group_owner = group_owner
        self.setup_organizer = setup_organizer

    def _bot_setup(self, c: Connection) -> bool:
        return (
            self.setup_organizer is not None
            and self.group_owner == self.store.policy.application_id
            and self.handler.current(c)[1].handler_id == self.group_owner
        )

    def _organizes_bot_setup(
        self, c: Connection, viewer: GuildViewer, current: SessionZero
    ) -> bool:
        return self._bot_setup(c) and (
            viewer.user_id == self.setup_organizer
            or (
                current.plan_approved
                and viewer.user_id == current.facilitator
                and self._active_group(c, current)
            )
        )

    def _can_manage_group(self, c: Connection, viewer: GuildViewer) -> bool:
        if self._bot_setup(c):
            self.store.guild_member(viewer)
            self.store._membership(c, viewer)
            return self._organizes_bot_setup(c, viewer, self._latest(c))
        if viewer.is_administrator and self.store.policy.allow_guild_administrators:
            return True
        if viewer.user_id == self.group_owner:
            self.handler.authorize(c, viewer)
            return True
        return False

    def _latest(self, c: Connection) -> SessionZero:
        raw = c.scalar(
            sa.select(t.events.c.payload_json)
            .where(t.events.c.campaign_id == self.store.campaign_id, t.events.c.kind == EVENT)
            .order_by(t.events.c.seq.desc())
            .limit(1)
        )
        return SessionZero.model_validate_json(raw) if raw is not None else SessionZero()

    def _group_member(self, c: Connection, viewer: GuildViewer, current: SessionZero) -> None:
        self.store.guild_member(viewer)
        self.store._membership(c, viewer)
        if viewer.user_id not in current.members:
            raise WorkflowError("Only members of this Session Zero group can access the worksheet.")

    def _active_group(self, c: Connection, current: SessionZero) -> bool:
        return all(self.handler._member(c, person) for person in current.members)

    @staticmethod
    def _expect(current: SessionZero, expected: int) -> None:
        if current.revision != expected:
            raise WorkflowError(
                "STALE_SESSION_ZERO: reopen Session Zero to see the latest changes."
            )

    def _write(
        self,
        viewer: GuildViewer,
        key: str,
        operation: str,
        payload: dict[str, Any],
        update: Callable[[Connection, SessionZero], SessionZero],
        *,
        manage_group: bool = False,
    ) -> dict[str, Any]:
        def authorize(c: Connection) -> None:
            if manage_group:
                self.store.guild_member(viewer)
                if not self._can_manage_group(c, viewer):
                    raise WorkflowError("Only the campaign organizer can set the group.")
            else:
                self._group_member(c, viewer, self._latest(c))

        def apply(c: Connection) -> dict[str, Any]:
            current = self._latest(c)
            result = update(c, current)
            result.revision = current.revision + 1
            receipt = self.store._audit(
                c,
                viewer.user_id,
                key,
                EVENT,
                result.model_dump(mode="json"),
                ruleset_version="session-zero-v1",
            )
            return {"revision": result.revision, "receipt": receipt}

        return self.store._write(
            viewer,
            key,
            "session_zero." + operation,
            payload,
            apply,
            authorize=authorize,
            auto_audit=False,
        )

    def set_group(
        self, viewer: GuildViewer, key: str, expected: int, members: tuple[int, ...]
    ) -> dict[str, Any]:
        members = tuple(sorted(members))

        def update(c: Connection, current: SessionZero) -> SessionZero:
            if opening(c, self.store.campaign_id) is not None:
                raise WorkflowError("The group's Session Zero is already complete.")
            if historical_mission(c, self.store.campaign_id):
                raise WorkflowError("Session Zero starts before the campaign's first mission.")
            self._expect(current, expected)
            if (
                not 2 <= len(members) <= MAX_GROUP
                or len(set(members)) != len(members)
                or any(type(x) is not int or not self.handler._member(c, x) for x in members)
            ):
                raise WorkflowError(
                    "Choose the distinct Handler and Pilots who joined the campaign."
                )
            if self._bot_setup(c):
                if self.setup_organizer not in members or self.group_owner in members:
                    raise WorkflowError(
                        "Include the setup organizer and human pilots. "
                        "HarpyEngine already holds the Handler seat."
                    )
            elif self.group_owner is not None and self.group_owner not in members:
                raise WorkflowError("Include the campaign's appointed Handler controller.")
            if members == current.members:
                raise WorkflowError("This group is already saved.")
            # A different audience requires fresh opt-in before sharing contributions.
            return SessionZero(members=members)

        return self._write(
            viewer,
            key,
            "group",
            {"expected": expected, "members": list(members)},
            update,
            manage_group=True,
        )

    def propose(
        self, viewer: GuildViewer, key: str, expected: int, profile: HandlerProfile
    ) -> dict[str, Any]:
        profile = HandlerProfile.model_validate_json(profile.model_dump_json())

        def update(c: Connection, current: SessionZero) -> SessionZero:
            if opening(c, self.store.campaign_id) is not None:
                raise WorkflowError("The group's Session Zero is already complete.")
            self._expect(current, expected)
            if profile.member not in current.members or not self._active_group(c, current):
                raise WorkflowError("Choose an active member of this Session Zero group.")
            if self.group_owner is not None and profile.member != self.group_owner:
                raise WorkflowError("Use the current campaign-bound Handler controller.")
            if profile == current.handler:
                raise WorkflowError("This Handler proposal is already open for approval.")
            return current.model_copy(
                update={
                    "handler": profile,
                    "proposal": str(uuid4()),
                    "approvals": (),
                    "plan_proposal": None,
                    "plan_approvals": (),
                    "seats": None,
                    "facilitator_only": current.facilitator_only
                    and current.facilitator != profile.member,
                    "submissions": {
                        uid: x
                        for uid, x in current.submissions.items()
                        if uid != str(profile.member)
                    },
                    "goals": current.goals
                    if current.handler and current.handler.member == profile.member
                    else "",
                }
            )

        return self._write(
            viewer,
            key,
            "proposal",
            {"expected": expected, "profile": profile.model_dump(mode="json")},
            update,
        )

    def decide(
        self, viewer: GuildViewer, key: str, proposal: str, *, approve: bool
    ) -> dict[str, Any]:
        def update(c: Connection, current: SessionZero) -> SessionZero:
            if opening(c, self.store.campaign_id) is not None:
                raise WorkflowError("The group's Session Zero is already complete.")
            if current.proposal != proposal or current.handler is None:
                raise WorkflowError("STALE_PROPOSAL: review the latest Handler proposal.")
            if not self._active_group(c, current):
                raise WorkflowError("Update the group after campaign membership changes.")
            approvals = set(current.approvals)
            if (viewer.user_id in approvals) == approve:
                raise WorkflowError("Your approval is already in that state.")
            if approve:
                approvals.add(viewer.user_id)
            else:
                approvals.discard(viewer.user_id)
            return current.model_copy(update={"approvals": tuple(sorted(approvals))})

        return self._write(
            viewer, key, "decision", {"proposal": proposal, "approve": approve}, update
        )

    def appoint(
        self, viewer: GuildViewer, key: str, setup_revision: int, proposal: str, nominee: int
    ) -> dict[str, Any]:
        def check(c: Connection) -> None:
            current = self._latest(c)
            if (
                current.proposal != proposal
                or current.handler is None
                or current.handler.member != nominee
                or not current.approved
                or not self._active_group(c, current)
            ):
                raise WorkflowError("Confirm the current group-approved Handler proposal first.")
            if self.handler.current(c)[1].handler_id is not None:
                raise WorkflowError(
                    "Use the existing Handler appointment review for a replacement."
                )
            if load_state(c, self.store.campaign_id).handler not in (None, nominee):
                raise WorkflowError("Resolve the existing canonical Handler through setup first.")

        return self.handler.appoint(viewer, key, setup_revision, nominee, apply_check=check)

    def _ready_handler(self, c: Connection, current: SessionZero) -> int | None:
        if self._bot_setup(c):
            if (
                current.members
                and self._active_group(c, current)
                and load_state(c, self.store.campaign_id).handler == self.group_owner
            ):
                return self.group_owner
            return None
        if (
            current.approved
            and current.handler
            and self._active_group(c, current)
            and self.handler.current(c)[1].handler_id == current.handler.member
        ):
            return current.handler.member
        return None

    def _opening_operator(self, c: Connection, current: SessionZero) -> int | None:
        handler = self._ready_handler(c, current)
        if handler is not None and self._bot_setup(c):
            return current.facilitator if current.plan_approved else None
        return handler

    def _sheet(self, c: Connection, game: GameState, owner: int) -> SheetReference:
        active = game.sheets.get(str(owner))
        if active is not None:
            return SheetReference(
                kind="active",
                version=hashlib.sha256(active.model_dump_json().encode()).hexdigest(),
                character=active.character_id or active.source_fingerprint,
                callsign=active.callsign,
                girl=active.girl,
                frame=active.frame,
            )
        # The private review is read only for freshness. Its body never enters Session Zero.
        review = self.reviews._current_for_owner(c, owner)
        if not review.saved_current or not review.sheet.ready_for_rules_review:
            raise WorkflowError("Finish and save your current /character review before attaching.")
        character = c.scalar(
            sa.select(t.characters.c.id).where(
                t.characters.c.campaign_id == self.store.campaign_id,
                t.characters.c.user_id == str(owner),
            )
        )
        if character is None:
            raise WorkflowError("Save your character before attaching its review.")
        return SheetReference(
            kind="saved_review",
            version=review.fingerprint,
            character=character,
            callsign=review.sheet.activation_callsign,
            girl=review.sheet.creation.girl_playbook,
            frame=review.sheet.creation.frame_playbook,
        )

    def _pilot(self, c: Connection, current: SessionZero, viewer: GuildViewer) -> None:
        if self._ready_handler(c, current) is None or viewer.user_id not in current.pilots:
            raise WorkflowError("Approve and appoint the Handler before attaching Pilot sheets.")

    def attach(self, viewer: GuildViewer, key: str, expected: int) -> dict[str, Any]:
        def update(c: Connection, current: SessionZero) -> SessionZero:
            self._expect(current, expected)
            self._pilot(c, current, viewer)
            sheet = self._sheet(c, load_state(c, self.store.campaign_id), viewer.user_id)
            previous = current.submissions.get(str(viewer.user_id))
            if previous and previous.sheet == sheet:
                raise WorkflowError("Your current character sheet is already attached.")
            notes = (
                previous.notes
                if previous and previous.sheet.character == sheet.character
                else CharacterNotes()
            )
            current.submissions[str(viewer.user_id)] = CharacterSubmission(sheet=sheet, notes=notes)
            return current

        return self._write(viewer, key, "attach", {"expected": expected}, update)

    def notes(
        self, viewer: GuildViewer, key: str, expected: int, notes: CharacterNotes
    ) -> dict[str, Any]:
        notes = CharacterNotes.model_validate_json(notes.model_dump_json())

        def update(c: Connection, current: SessionZero) -> SessionZero:
            self._expect(current, expected)
            self._pilot(c, current, viewer)
            submission = current.submissions.get(str(viewer.user_id))
            sheet = self._sheet(c, load_state(c, self.store.campaign_id), viewer.user_id)
            if submission is None or submission.sheet != sheet:
                raise WorkflowError("Attach your current character sheet before adding input.")
            submission.notes = notes
            return current

        return self._write(
            viewer,
            key,
            "notes",
            {"expected": expected, "notes": notes.model_dump(mode="json")},
            update,
        )

    def goals(
        self,
        viewer: GuildViewer,
        key: str,
        expected: int,
        goals: str,
        difficulty: Difficulty | None = None,
        seats: CampaignSeats | None = None,
        *,
        facilitator: Snowflake | None = None,
        facilitator_only: bool = False,
    ) -> dict[str, Any]:
        if len(goals.strip()) > 800:
            raise WorkflowError("Use at most 800 characters for the short-term goals.")

        def update(c: Connection, current: SessionZero) -> SessionZero:
            self._expect(current, expected)
            if opening(c, self.store.campaign_id) is not None:
                raise WorkflowError("The group's Session Zero is already complete.")
            bot_setup = self._bot_setup(c)
            if bot_setup:
                if not self._organizes_bot_setup(c, viewer, current) or not self._active_group(
                    c, current
                ):
                    raise WorkflowError(
                        "The campaign setup organizer drafts the plan for the active group."
                    )
                if facilitator is None:
                    raise WorkflowError("Nominate a facilitator from the group.")
            elif self._ready_handler(c, current) != viewer.user_id:
                raise WorkflowError("The approved, appointed Handler drafts the campaign goals.")
            if facilitator is not None:
                if (
                    type(facilitator) is not int
                    or facilitator not in current.members
                    or not self.handler._member(c, facilitator)
                ):
                    raise WorkflowError("Choose an active member of this Session Zero group.")
                if facilitator_only and facilitator == viewer.user_id and not bot_setup:
                    raise WorkflowError("Choose a separate member for a facilitator-only seat.")
                current.facilitator = facilitator
                current.facilitator_only = facilitator_only
            if not current.pilots:
                raise WorkflowError("Keep at least one Pilot in the group.")
            proposed_seats = seats if seats is not None else current.seats
            if proposed_seats is not None and proposed_seats.player_count != current.human_players:
                raise WorkflowError("Match the human player count to the Pilot and Handler seats.")
            current.goals = goals.strip()
            current.difficulty = difficulty if difficulty is not None else current.difficulty
            current.plan_proposal = str(uuid4()) if current.goals else None
            current.plan_approvals = ()
            if seats is not None:
                current.seats = seats
            return current

        return self._write(
            viewer,
            key,
            "goals",
            {"expected": expected, "goals": goals}
            | ({"difficulty": difficulty} if difficulty is not None else {})
            | ({"seats": seats.model_dump(mode="json")} if seats is not None else {})
            | (
                {"facilitator": facilitator, "facilitator_only": facilitator_only}
                if facilitator is not None
                else {}
            ),
            update,
        )

    def decide_plan(
        self, viewer: GuildViewer, key: str, proposal: str, *, approve: bool
    ) -> dict[str, Any]:
        def update(c: Connection, current: SessionZero) -> SessionZero:
            if opening(c, self.store.campaign_id) is not None:
                raise WorkflowError("The group's Session Zero is already complete.")
            if (
                not proposal
                or current.plan_proposal != proposal
                or not (
                    self._active_group(c, current)
                    if self._bot_setup(c)
                    else self._ready_handler(c, current) is not None
                )
            ):
                raise WorkflowError("STALE_PLAN: review the group's current goals and difficulty.")
            approvals = set(current.plan_approvals)
            if (viewer.user_id in approvals) == approve:
                raise WorkflowError("Your plan approval is already in that state.")
            if approve:
                approvals.add(viewer.user_id)
            else:
                approvals.discard(viewer.user_id)
            current.plan_approvals = tuple(sorted(approvals))
            return current

        return self._write(
            viewer,
            key,
            "plan_decision",
            {"proposal": proposal, "approve": approve},
            update,
        )

    def complete(
        self,
        viewer: GuildViewer,
        key: str,
        expected: int,
        channel: int,
        account: str,
        days: int = introduction.DEFAULT_ROLEPLAY_DAYS,
        *,
        reuse_empty: bool = False,
    ) -> dict[str, Any]:
        def update(c: Connection, current: SessionZero) -> SessionZero:
            self._expect(current, expected)
            if self._opening_operator(c, current) != viewer.user_id:
                if self._bot_setup(c):
                    raise WorkflowError("Only the approved facilitator can open the introduction.")
                raise WorkflowError("The approved and appointed Handler opens the introduction.")
            if not current.plan_approved:
                raise WorkflowError(
                    "Every group member must approve the same goals and difficulty."
                )
            if any(status != "attached" for status in self._submissions(c, current).values()):
                raise WorkflowError("Every Pilot must attach a current character sheet first.")
            introduction.launch(
                c,
                self.store,
                viewer,
                key,
                current,
                channel,
                account,
                days,
                reuse_empty=reuse_empty,
                handler=self._ready_handler(c, current),
            )
            return current

        return self._write(
            viewer,
            key,
            "complete",
            {"expected": expected, "channel": channel, "introduction": account, "days": days}
            | ({"reuse_empty": True} if reuse_empty else {}),
            update,
        )

    def advance_opening(
        self, viewer: GuildViewer, key: str, expected_anchor: str
    ) -> dict[str, Any]:
        def access(c: Connection) -> None:
            current = self._latest(c)
            self._group_member(c, viewer, current)
            if self._opening_operator(c, current) != viewer.user_id:
                if self._bot_setup(c):
                    raise WorkflowError("Only the approved facilitator advances an introductory day.")
                raise WorkflowError("Only the appointed Handler advances an introductory day.")

        def operation(c: Connection) -> dict[str, Any]:
            record = opening(c, self.store.campaign_id)
            if record is None or record.handler != self._ready_handler(c, self._latest(c)):
                raise WorkflowError("Open the group's introduction first.")
            return introduction.advance(c, self.store, viewer, key, expected_anchor, record)

        return self.store._write(
            viewer,
            key,
            "session_zero.advance_opening",
            {"anchor": expected_anchor},
            operation,
            authorize=access,
            auto_audit=False,
        )

    def post_intro(
        self, viewer: GuildViewer, key: str, expected_anchor: str, text: str
    ) -> dict[str, Any]:
        text = text.strip()
        if not text or len(text) > 1200:
            raise WorkflowError("Write 1–1200 characters of introductory roleplay.")

        def authorize(c: Connection) -> None:
            self._group_member(c, viewer, self._latest(c))
            record = opening(c, self.store.campaign_id)
            if record is None or viewer.user_id not in record.audience:
                raise WorkflowError("This introduction is private to its approved group.")
            if record.facilitator_only and viewer.user_id == record.facilitator:
                raise WorkflowError("Only the cast can post introductory roleplay.")

        def operation(c: Connection) -> dict[str, Any]:
            GameService(self.store).unpaused(c)
            record = opening(c, self.store.campaign_id)
            anchor = calendar.anchor(c, self.store.campaign_id)
            if record is None or anchor is None or anchor[0] != expected_anchor:
                raise WorkflowError("STALE_INTRODUCTION: refresh the current introductory day.")
            day = anchor[1].position.day
            if day >= record.first_mission_day:
                raise WorkflowError("The introduction has ended. Continue in the mission scene.")
            member = str(viewer.user_id)
            current = self._latest(c)
            attached = current.submissions.get(member)
            label = (
                current.handler.name
                if record.handler == viewer.user_id and current.handler
                else attached.sheet.callsign
                if attached
                else "Pilot"
            )
            receipt = self.store._audit(
                c,
                viewer.user_id,
                key,
                INTRO_POST,
                {"scene": record.scene, "day": day, "author": label, "text": text},
                ruleset_version="session-zero-v1",
            )
            return {"receipt": receipt, "day": day}

        return self.store._write(
            viewer,
            key,
            INTRO_POST,
            {"anchor": expected_anchor, "text": text},
            operation,
            authorize=authorize,
            auto_audit=False,
        )

    def _intro_posts(self, c: Connection, record: Opening) -> list[dict[str, Any]]:
        rows = c.execute(
            calendar.query(self.store.campaign_id, INTRO_POST)
            .with_only_columns(t.events.c.id, t.events.c.payload_json)
            .where(sa.func.json_extract(t.events.c.payload_json, "$.scene") == record.scene)
            .order_by(t.events.c.seq.desc())
            .limit(50)
        )
        return [{"id": row.id, **json.loads(row.payload_json)} for row in reversed(list(rows))]

    def _submissions(self, c: Connection, current: SessionZero) -> dict[int, str]:
        game = load_state(c, self.store.campaign_id)
        statuses = {}
        for uid in current.pilots:
            submission = current.submissions.get(str(uid))
            if submission is None:
                statuses[uid] = "missing"
                continue
            try:
                sheet = self._sheet(c, game, uid)
            except WorkflowError:
                statuses[uid] = "refresh"
            else:
                statuses[uid] = "attached" if sheet == submission.sheet else "refresh"
        return statuses

    def view(self, viewer: GuildViewer) -> dict[str, Any]:
        self.store.guild_member(viewer)
        admin = viewer.is_administrator and self.store.policy.allow_guild_administrators
        with self.store.engine.connect() as c:
            c.exec_driver_sql("BEGIN")
            current = self._latest(c)
            group = viewer.user_id in current.members
            manage_group = self._can_manage_group(c, viewer)
            bot_setup = self._bot_setup(c)
            if group or not manage_group:
                self._group_member(c, viewer, current)
            setup_revision, setup = self.handler.current(c)
            ready = self._ready_handler(c, current)
            proposal = current.handler
            record = opening(c, self.store.campaign_id)
            result: dict[str, Any] = {
                "revision": current.revision,
                "members": current.members,
                "admin": admin,
                "in_group": group,
                "proposal": current.proposal,
                "nominee": proposal.member if proposal else None,
                "approvals": len(current.approvals),
                "approved": current.approved,
                "own_approval": viewer.user_id in current.approvals,
                "handler_ready": ready,
                "appointed": setup.handler_id,
                "setup_revision": setup_revision,
                "can_set_group": manage_group
                and record is None
                and not historical_mission(c, self.store.campaign_id),
                "can_appoint": admin
                and current.approved
                and setup.handler_id is None
                and self._active_group(c, current),
            }
            if result["can_set_group"]:
                available = c.scalars(
                    sa.select(t.members.c.user_id).where(
                        t.members.c.campaign_id == self.store.campaign_id,
                        t.members.c.active.is_(True),
                    )
                )
                result["group_options"] = tuple(
                    sorted(
                        int(user)
                        for user in available
                        if not bot_setup or int(user) != self.group_owner
                    )
                )
            if bot_setup:
                result.update(
                    bot_managed=True,
                    required_group_member=str(self.setup_organizer),
                    can_edit_plan=group
                    and record is None
                    and self._organizes_bot_setup(c, viewer, current),
                )
            if group:
                submissions = self._submissions(c, current) if ready is not None else {}
                own = current.submissions.get(str(viewer.user_id))
                anchor = calendar.anchor(c, self.store.campaign_id) if record else None
                result.update(
                    profile=proposal.model_dump() if proposal else None,
                    sheets=submissions,
                    own_notes=own.notes.model_dump() if own else {},
                    goals=current.goals,
                    difficulty=current.difficulty,
                    difficulty_options=DIFFICULTY_DESCRIPTIONS,
                    player_count=current.human_players,
                    facilitator=current.facilitator,
                    facilitator_only=current.facilitator_only,
                    is_pilot=viewer.user_id in current.pilots,
                    seats=current.seats.model_dump(mode="json") if current.seats else None,
                    plan_proposal=current.plan_proposal,
                    plan_approvals=len(current.plan_approvals),
                    plan_approved=current.plan_approved,
                    own_plan_approval=viewer.user_id in current.plan_approvals,
                    opening=record.model_dump(mode="json", exclude={"audience"})
                    if record
                    else None,
                    opening_day=anchor[1].position.day if anchor else None,
                    opening_anchor=anchor[0] if anchor else None,
                    can_open_introduction=record is None
                    and current.plan_approved
                    and viewer.user_id == self._opening_operator(c, current)
                    and bool(submissions)
                    and all(value == "attached" for value in submissions.values()),
                    can_advance_introduction=record is not None
                    and anchor is not None
                    and anchor[1].position.day < record.first_mission_day
                    and viewer.user_id == self._opening_operator(c, current),
                    opening_posts=self._intro_posts(c, record)
                    if record and viewer.user_id in record.audience
                    else [],
                    can_generate=bool(submissions)
                    and all(x == "attached" for x in submissions.values()),
                )
            return result

    def generate(self, viewer: GuildViewer, expected: int) -> str:
        with self.store.engine.connect() as c:
            c.exec_driver_sql("BEGIN")
            current = self._latest(c)
            self._group_member(c, viewer, current)
            self._expect(current, expected)
            profile = current.handler
            if self._ready_handler(c, current) is None:
                raise WorkflowError("Approve and appoint the group's Handler before generating.")
            statuses = self._submissions(c, current)
            if not statuses or any(x != "attached" for x in statuses.values()):
                raise WorkflowError("Every listed Pilot must attach their current character sheet.")
            return _worksheet(current, profile, opening(c, self.store.campaign_id))


def _text(value: str) -> str:
    return re.sub(
        r"[\\`*_{}\[\]()#+.!|]", lambda match: "\\" + match[0], escape(value, quote=False)
    )


def _worksheet(
    current: SessionZero, profile: HandlerProfile | None, record: Opening | None = None
) -> str:
    lines = ["# Session Zero", "## Handler"]
    if profile is None:
        lines.append("**HarpyEngine**")
    else:
        lines.extend(
            [
                f"**{_text(profile.name)}** · {profile.archetype}",
                ("AI-assisted. Reviewed by " if profile.control == "ai" else "Played by ")
                + _text(profile.player_name or f"Discord member {profile.member}"),
                f"**Appearance**\n\n{_text(profile.appearance)}",
                f"**Personality**\n\n{_text(profile.personality)}",
            ]
        )
    lines.extend(
        [
            "## Campaign plan",
            f"**Difficulty** · {current.difficulty.title()}",
            f"**Human players** · {current.human_players}",
            "**Agreed short-term goals**" if current.plan_approved else "**Short-term goal draft**",
            _text(current.goals)
            if current.goals
            else "Use the character goals and hooks below to agree on shared goals.",
        ]
    )
    if current.seats and current.seats.ai_pilots:
        lines.append("## Planned AI Pilots")
        lines.extend(
            _text(pilot.callsign) + (f" · {_text(pilot.concept)}" if pilot.concept else "")
            for pilot in current.seats.ai_pilots
        )
    if current.facilitator is not None:
        lines.append(f"**Facilitator** · Discord member {current.facilitator}")
    if record is not None:
        lines.extend(
            (
                "## Cadre Introduction",
                _text(record.introduction),
                f"The first mission can start on Day {record.first_mission_day}.",
            )
        )
    lines.append("## Characters and campaign input")
    for uid in current.pilots:
        item = current.submissions[str(uid)]
        sheet = item.sheet
        lines.extend(
            (
                "### " + _text(sheet.callsign),
                f"{_text(sheet.girl)} / {_text(sheet.frame)}",
                "Active character sheet" if sheet.kind == "active" else "Saved character review",
            )
        )
        for label, value in (
            ("Character goal", item.notes.goal),
            ("Story hook", item.notes.hook),
            ("Desired spotlight", item.notes.spotlight),
        ):
            if value.strip():
                lines.append(f"**{label}**\n\n{_text(value)}")
    return "\n\n".join(lines) + "\n"
