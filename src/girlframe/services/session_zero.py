"""Campaign-scoped Session Zero intake and group-only worksheet generation."""

import hashlib
import re
from collections.abc import Callable
from html import escape
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine.m2 import GameState
from girlframe.engine.session_zero import (
    MAX_GROUP,
    CharacterNotes,
    CharacterSubmission,
    HandlerProfile,
    SessionZero,
    SheetReference,
)
from girlframe.services.creation_review import CreationReviewService
from girlframe.services.handler_setup import HandlerService
from girlframe.services.m2_state import load_state
from girlframe.services.onboarding import OnboardingStore, WorkflowError
from girlframe.services.read_only_bot import GuildViewer

EVENT = "campaign.session_zero_saved"


class SessionZeroService:
    def __init__(self, store: OnboardingStore):
        self.store = store
        self.handler = HandlerService(store)
        self.reviews = CreationReviewService(store)

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
        admin: bool = False,
    ) -> dict[str, Any]:
        def authorize(c: Connection) -> None:
            if admin:
                self.store.administrator(viewer)
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
            self._expect(current, expected)
            if (
                not 2 <= len(members) <= MAX_GROUP
                or len(set(members)) != len(members)
                or any(type(x) is not int or not self.handler._member(c, x) for x in members)
            ):
                raise WorkflowError(
                    "Choose the distinct Handler and Pilots who joined the campaign."
                )
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
            admin=True,
        )

    def propose(
        self, viewer: GuildViewer, key: str, expected: int, profile: HandlerProfile
    ) -> dict[str, Any]:
        profile = HandlerProfile.model_validate_json(profile.model_dump_json())

        def update(c: Connection, current: SessionZero) -> SessionZero:
            self._expect(current, expected)
            if profile.member not in current.members or not self._active_group(c, current):
                raise WorkflowError("Choose an active member of this Session Zero group.")
            if profile == current.handler:
                raise WorkflowError("This Handler proposal is already open for approval.")
            return current.model_copy(
                update={
                    "handler": profile,
                    "proposal": str(uuid4()),
                    "approvals": (),
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
        if (
            current.approved
            and current.handler
            and self._active_group(c, current)
            and self.handler.current(c)[1].handler_id == current.handler.member
        ):
            return current.handler.member
        return None

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

    def goals(self, viewer: GuildViewer, key: str, expected: int, goals: str) -> dict[str, Any]:
        def update(c: Connection, current: SessionZero) -> SessionZero:
            self._expect(current, expected)
            if self._ready_handler(c, current) != viewer.user_id:
                raise WorkflowError("The approved, appointed Handler drafts the campaign goals.")
            current.goals = goals.strip()
            return current

        return self._write(viewer, key, "goals", {"expected": expected, "goals": goals}, update)

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
            if group or not admin:
                self._group_member(c, viewer, current)
            setup_revision, setup = self.handler.current(c)
            ready = self._ready_handler(c, current)
            proposal = current.handler
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
                "can_appoint": admin
                and current.approved
                and setup.handler_id is None
                and self._active_group(c, current),
            }
            if group:
                submissions = self._submissions(c, current) if ready is not None else {}
                own = current.submissions.get(str(viewer.user_id))
                result.update(
                    profile=proposal.model_dump() if proposal else None,
                    sheets=submissions,
                    own_notes=own.notes.model_dump() if own else {},
                    goals=current.goals,
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
            if profile is None or self._ready_handler(c, current) is None:
                raise WorkflowError("Approve and appoint the group's Handler before generating.")
            statuses = self._submissions(c, current)
            if not statuses or any(x != "attached" for x in statuses.values()):
                raise WorkflowError("Every listed Pilot must attach their current character sheet.")
            return _worksheet(current, profile)


def _text(value: str) -> str:
    return re.sub(r"[\\`*_{}\[\]()#+.!|]", lambda match: "\\" + match[0], escape(value))


def _worksheet(current: SessionZero, profile: HandlerProfile) -> str:
    lines = [
        "# Session Zero",
        "## Handler",
        f"**{_text(profile.name)}** · {profile.archetype}",
        "Played by " + _text(profile.player_name or f"Discord member {profile.member}"),
        f"**Appearance**\n\n{_text(profile.appearance)}",
        f"**Personality**\n\n{_text(profile.personality)}",
        "## Campaign goal draft",
        _text(current.goals)
        if current.goals
        else "Use the character goals and hooks below to agree on shared goals.",
        "## Characters and campaign input",
    ]
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
