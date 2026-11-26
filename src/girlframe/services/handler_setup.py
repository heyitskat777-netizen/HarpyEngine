"""Explicit campaign Handler authority and draft starting assignments."""

import json
from collections.abc import Callable
from typing import TYPE_CHECKING, Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine.creation_review import CreationRulings
from girlframe.engine.handler_setup import HandlerSetup, MentorAssignment, PilotRef
from girlframe.services.onboarding import OnboardingStore, WorkflowError
from girlframe.services.read_only_bot import GuildViewer

if TYPE_CHECKING:
    from girlframe.engine.m2 import GameState


def late_wing_eligible(
    state: "GameState", setup: HandlerSetup, owner: int, profile: dict[str, Any] | None
) -> bool:
    return (
        len(state.order) >= 2
        and state.handler == setup.handler_id
        and owner not in state.order
        and str(owner) not in state.sheets
        and not any(x.actor.entity == str(owner) for x in state.career_archives)
        and profile is not None
        and profile["callsign"].casefold() != "recruit"
        and profile["girl_playbook"] != "PRINCESS"
    )


def assigned_late_wing(
    state: "GameState", setup: HandlerSetup, owner: int, profile: dict[str, Any] | None
) -> bool:
    return bool(
        profile
        and late_wing_eligible(state, setup, owner, profile)
        and PilotRef(user_id=owner, character_revision=profile["revision"]) in setup.late_wings
    )


class HandlerService:
    def __init__(self, store: OnboardingStore):
        self.store = store

    def current(self, connection: Connection) -> tuple[int, HandlerSetup]:
        row = (
            connection.execute(
                sa.select(t.setup_revisions)
                .where(t.setup_revisions.c.campaign_id == self.store.campaign_id)
                .order_by(t.setup_revisions.c.revision.desc())
                .limit(1)
            )
            .mappings()
            .first()
        )
        return (
            (row["revision"], HandlerSetup.model_validate_json(row["body_json"]))
            if row
            else (0, HandlerSetup())
        )

    def appointment_preview(self, viewer: GuildViewer) -> dict[str, Any]:
        self.store.administrator(viewer)
        with self.store.engine.connect() as connection:
            self.store._binding_matches(connection)
            revision, setup = self.current(connection)
            return {"revision": revision, "handler_id": setup.handler_id}

    def _member(self, connection: Connection, user: int) -> bool:
        return (
            connection.execute(
                sa.select(t.members.c.user_id).where(
                    t.members.c.campaign_id == self.store.campaign_id,
                    t.members.c.user_id == str(user),
                    t.members.c.active.is_(True),
                )
            ).first()
            is not None
        )

    def authorize(self, connection: Connection, viewer: GuildViewer) -> None:
        self.store.guild_member(viewer)
        self.store._membership(connection, viewer)
        if self.current(connection)[1].handler_id != viewer.user_id:
            raise WorkflowError("Only the explicitly appointed campaign Handler can do this.")

    def _roster(self, connection: Connection) -> dict[int, dict[str, Any]]:
        rows = connection.execute(
            sa.select(t.characters.c.user_id, t.characters.c.revision, t.characters.c.public_json)
            .join(
                t.members,
                sa.and_(
                    t.members.c.campaign_id == t.characters.c.campaign_id,
                    t.members.c.user_id == t.characters.c.user_id,
                ),
            )
            .where(
                t.characters.c.campaign_id == self.store.campaign_id, t.members.c.active.is_(True)
            )
        )
        return {
            int(user): {"revision": revision, **json.loads(public)}
            for user, revision, public in rows
        }

    def roster(self, viewer: GuildViewer) -> dict[str, Any]:
        with self.store.engine.connect() as connection:
            self.authorize(connection, viewer)
            return {"revision": self.current(connection)[0], "pilots": self._roster(connection)}

    def cadre(self, connection: Connection, owner: int) -> dict[int, int | None]:
        result: dict[int, int | None] = {
            uid: data["revision"] for uid, data in self._roster(connection).items() if uid != owner
        }
        handler = self.current(connection)[1].handler_id
        if handler is not None and handler != owner and self._member(connection, handler):
            # One account may control both roles. Keep its actual Pilot profile
            # rather than replacing that incarnation with the Handler sentinel.
            result.setdefault(handler, None)
        return result

    def rulings(
        self, viewer: GuildViewer, key: str, expected: int, value: CreationRulings | None
    ) -> dict[str, Any]:
        if value is not None:
            value = CreationRulings.model_validate_json(value.model_dump_json())
            if value.provenance != "handler_confirmed_campaign_ruling":
                raise WorkflowError("Handler changes must record Handler confirmation provenance.")
        return self._save(
            viewer,
            key,
            expected,
            "campaign.creation_rulings",
            {"rulings": value.model_dump(mode="json") if value else None},
            lambda c: self.authorize(c, viewer),
            lambda c, previous: previous.model_copy(
                update={"creation_rulings": value, "creation_rulings_explicit": True}
            ),
        )

    def effective_rulings(self, connection: Connection) -> CreationRulings | None:
        setup = self.current(connection)[1]
        if setup.creation_rulings_explicit or setup.creation_rulings is not None:
            return setup.creation_rulings
        return self.store.policy.owner_creation_rulings

    def view(self, viewer: GuildViewer) -> dict[str, Any]:
        with self.store.engine.connect() as connection:
            self.store.guild_member(viewer)
            self.store._membership(connection, viewer)
            revision, setup = self.current(connection)
            roster = self._roster(connection)
            rulings = self.effective_rulings(connection)
            return {
                "revision": revision,
                "handler_id": setup.handler_id,
                "handler_active": setup.handler_id is not None
                and self._member(connection, setup.handler_id),
                "creation_rulings": (
                    rulings.model_dump(mode="json") if rulings is not None else None
                ),
                "status_order": [x.model_dump(mode="json") for x in setup.status_order],
                "status_stale": (
                    setup.handler_id is None or not self._member(connection, setup.handler_id)
                )
                or set(x.user_id for x in setup.status_order) != set(roster)
                or any(
                    x.user_id not in roster or roster[x.user_id]["revision"] != x.character_revision
                    for x in setup.status_order
                ),
                "mentors": [
                    x.model_dump(mode="json")
                    | {"stale": self.mentor_for(connection, x.newgirl.user_id) is None}
                    for x in setup.mentors
                    if viewer.user_id in (setup.handler_id, x.newgirl.user_id, x.mentor.user_id)
                ],
            }

    def mentor_for(self, connection: Connection, newgirl: int) -> MentorAssignment | None:
        _, setup = self.current(connection)
        if setup.handler_id is None or not self._member(connection, setup.handler_id):
            return None
        assignment = next((x for x in setup.mentors if x.newgirl.user_id == newgirl), None)
        roster = self._roster(connection)
        if assignment is None:
            return None
        for pilot in (assignment.newgirl, assignment.mentor):
            if (
                pilot.user_id not in roster
                or roster[pilot.user_id]["revision"] != pilot.character_revision
            ):
                return None
        return assignment if roster[newgirl]["girl_playbook"] == "NEWGIRL" else None

    def _save(
        self,
        viewer: GuildViewer,
        key: str,
        expected: int,
        kind: str,
        payload: dict[str, Any],
        authorize: Callable[[Connection], None],
        change: Callable[[Connection, HandlerSetup], HandlerSetup],
    ) -> dict[str, Any]:
        def operation(connection: Connection) -> dict[str, Any]:
            revision, previous = self.current(connection)
            if revision != expected:
                raise WorkflowError("STALE_REVISION: reopen setup; previous choices preserved.")
            new = change(connection, previous)
            new = HandlerSetup.model_validate_json(new.model_dump_json())
            result = {"revision": revision + 1, "operation": kind}
            event = self.store._audit(connection, viewer.user_id, key, kind, result)
            connection.execute(
                t.setup_revisions.insert().values(
                    campaign_id=self.store.campaign_id,
                    revision=revision + 1,
                    event_id=event,
                    body_json=new.model_dump_json(),
                )
            )
            return result

        return self.store._write(
            viewer,
            key,
            kind,
            {"expected": expected, **payload},
            operation,
            auto_audit=False,
            authorize=authorize,
        )

    def appoint(
        self,
        viewer: GuildViewer,
        key: str,
        expected: int,
        member: int | None,
        *,
        apply_check: Callable[[Connection], None] | None = None,
    ) -> dict[str, Any]:
        def admin(connection: Connection) -> None:
            self.store.administrator(viewer)

        def change(connection: Connection, previous: HandlerSetup) -> HandlerSetup:
            if apply_check is not None:
                apply_check(connection)
            if member == previous.handler_id:
                raise WorkflowError("This Handler appointment is already current.")
            if member is not None and not self._member(connection, member):
                raise WorkflowError("The nominated Handler must first join the campaign.")
            return HandlerSetup(handler_id=member)

        return self._save(
            viewer, key, expected, "campaign.handler_appointed", {"member": member}, admin, change
        )

    def authorize_bond_test(self, connection: Connection, viewer: GuildViewer) -> None:
        if viewer.is_administrator and self.store.policy.allow_guild_administrators:
            self.store.administrator(viewer)
        else:
            self.authorize(connection, viewer)

    def bond_test_preview(self, viewer: GuildViewer, target: int) -> dict[str, Any]:
        with self.store.engine.connect() as connection:
            self.authorize_bond_test(connection, viewer)
            revision, _ = self.current(connection)
            row = self._roster(connection).get(target)
            if row is None:
                raise WorkflowError("Choose an active Pilot with a saved character profile.")
            return {
                "revision": revision,
                "pilot": PilotRef(user_id=target, character_revision=row["revision"]),
            }

    def bond_test(
        self, viewer: GuildViewer, key: str, expected: int, pilot: PilotRef, enabled: bool
    ) -> dict[str, Any]:
        pilot = PilotRef.model_validate_json(pilot.model_dump_json())

        def change(connection: Connection, previous: HandlerSetup) -> HandlerSetup:
            from girlframe.services.m2_state import load_state

            row = self._roster(connection).get(pilot.user_id)
            if row is None or row["revision"] != pilot.character_revision:
                raise WorkflowError("STALE_PROFILE: reopen the setup test bypass.")
            if str(pilot.user_id) in load_state(connection, self.store.campaign_id).sheets:
                raise WorkflowError("Already activated; this bypass only changes draft setup.")
            remaining = tuple(
                x for x in previous.starting_bond_test_bypasses if x.user_id != pilot.user_id
            )
            return previous.model_copy(
                update={"starting_bond_test_bypasses": remaining + ((pilot,) if enabled else ())}
            )

        return self._save(
            viewer,
            key,
            expected,
            "campaign.starting_bond_test_bypass",
            {"pilot": pilot.model_dump(mode="json"), "enabled": enabled},
            lambda c: self.authorize_bond_test(c, viewer),
            change,
        )

    def mentor(
        self, viewer: GuildViewer, key: str, expected: int, newgirl: PilotRef, mentor: PilotRef
    ) -> dict[str, Any]:
        newgirl, mentor = (
            PilotRef.model_validate_json(newgirl.model_dump_json()),
            PilotRef.model_validate_json(mentor.model_dump_json()),
        )

        def change(connection: Connection, previous: HandlerSetup) -> HandlerSetup:
            roster = self._roster(connection)
            if newgirl.user_id == mentor.user_id:
                raise WorkflowError("Choose two different active Pilots.")
            for pilot in (newgirl, mentor):
                if (
                    pilot.user_id not in roster
                    or roster[pilot.user_id]["revision"] != pilot.character_revision
                ):
                    raise WorkflowError("STALE_PROFILE: reopen the Mentor assignment.")
            if roster[newgirl.user_id]["girl_playbook"] != "NEWGIRL":
                raise WorkflowError("Mentor assignment requires a Newgirl profile.")
            assignment = MentorAssignment(
                assignment_id=str(uuid4()), newgirl=newgirl, mentor=mentor
            )
            return previous.model_copy(
                update={
                    "mentors": tuple(
                        x for x in previous.mentors if x.newgirl.user_id != newgirl.user_id
                    )
                    + (assignment,)
                }
            )

        return self._save(
            viewer,
            key,
            expected,
            "campaign.mentor_assigned",
            {"newgirl": newgirl.model_dump(mode="json"), "mentor": mentor.model_dump(mode="json")},
            lambda c: self.authorize(c, viewer),
            change,
        )

    def rank(
        self, viewer: GuildViewer, key: str, expected: int, order: tuple[PilotRef, ...]
    ) -> dict[str, Any]:
        order = tuple(PilotRef.model_validate_json(x.model_dump_json()) for x in order)

        def change(connection: Connection, previous: HandlerSetup) -> HandlerSetup:
            roster = self._roster(connection)
            ids = [x.user_id for x in order]
            if len(ids) < 2:
                raise WorkflowError(
                    "UNSUPPORTED_RULE: at least two Pilots are needed for distinct Ace and Dog."
                )
            if len(set(ids)) != len(ids) or set(ids) != set(roster):
                raise WorkflowError(
                    "Rank every active Pilot exactly once, including a Handler's Pilot."
                )
            if any(roster[x.user_id]["revision"] != x.character_revision for x in order):
                raise WorkflowError("STALE_PROFILE: reopen the Status roster.")
            princesses = [
                user for user, data in roster.items() if data["girl_playbook"] == "PRINCESS"
            ]
            if len(princesses) > 1:
                raise WorkflowError(
                    "UNSUPPORTED_RULE: multiple Princesses conflict with the single starting Ace."
                )
            if princesses and ids[0] != princesses[0]:
                raise WorkflowError(
                    "Princess must begin as the Ace, at the top of the starting order."
                )
            return previous.model_copy(update={"status_order": order})

        return self._save(
            viewer,
            key,
            expected,
            "campaign.status_assigned",
            {"order": [x.model_dump(mode="json") for x in order]},
            lambda c: self.authorize(c, viewer),
            change,
        )

    def late_wing_requests(self, viewer: GuildViewer) -> list[dict[str, Any]]:
        from girlframe.services.m2_state import load_state

        with self.store.engine.connect() as connection:
            self.authorize(connection, viewer)
            revision, setup = self.current(connection)
            state = load_state(connection, self.store.campaign_id)
            return [
                {
                    "owner": str(owner),
                    "callsign": profile["callsign"],
                    "character_revision": profile["revision"],
                    "setup_revision": revision,
                    "late_wing": True,
                }
                for owner, profile in self._roster(connection).items()
                if late_wing_eligible(state, setup, owner, profile)
                and not assigned_late_wing(state, setup, owner, profile)
            ]

    def assign_late_wing(
        self, viewer: GuildViewer, key: str, expected: int, pilot: PilotRef
    ) -> dict[str, Any]:
        def change(connection: Connection, previous: HandlerSetup) -> HandlerSetup:
            from girlframe.services.m2_state import load_state

            state = load_state(connection, self.store.campaign_id)
            profile = self._roster(connection).get(pilot.user_id)
            if not late_wing_eligible(state, previous, pilot.user_id, profile):
                raise WorkflowError("Choose an eligible filed pilot for a Wing placement.")
            if profile is None or profile["revision"] != pilot.character_revision:
                raise WorkflowError("STALE_PROFILE: reopen the late enrollment request.")
            return previous.model_copy(
                update={
                    "late_wings": tuple(
                        x for x in previous.late_wings if x.user_id != pilot.user_id
                    )
                    + (pilot,)
                }
            )

        return self._save(
            viewer,
            key,
            expected,
            "campaign.late_wing_assigned",
            {"pilot": pilot.model_dump(mode="json")},
            lambda c: self.authorize(c, viewer),
            change,
        )
