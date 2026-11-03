"""Consistent owner-only readiness projection and immutable review snapshots."""

import hashlib
import json
from dataclasses import dataclass
from typing import Any

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine.bonds import starting_kind
from girlframe.engine.creation import CreationDraft
from girlframe.engine.creation_details import GirlDetails, PsychStringAnchor
from girlframe.engine.creation_review import ReviewIssue, ReviewSheet, SheetBond
from girlframe.services.bonds import BondService
from girlframe.services.creation import CreationService
from girlframe.services.creation_coordination import CoordinationService
from girlframe.services.handler_setup import HandlerService
from girlframe.services.onboarding import OnboardingStore, WorkflowError
from girlframe.services.read_only_bot import GuildViewer
from girlframe.services.shared_setup import SharedSetupService


@dataclass(frozen=True)
class CurrentReview:
    sheet: ReviewSheet
    fingerprint: str
    saved_revision: int
    saved_current: bool


class CreationReviewService:
    def __init__(self, store: OnboardingStore):
        self.store = store

    def _latest(self, connection: Connection, viewer: GuildViewer) -> dict[str, Any] | None:
        row = (
            connection.execute(
                sa.select(t.creation_reviews)
                .where(
                    t.creation_reviews.c.campaign_id == self.store.campaign_id,
                    t.creation_reviews.c.user_id == str(viewer.user_id),
                )
                .order_by(t.creation_reviews.c.revision.desc())
                .limit(1)
            )
            .mappings()
            .first()
        )
        return dict(row) if row else None

    def _current(self, connection: Connection, viewer: GuildViewer) -> CurrentReview:
        progress = CreationService(self.store)._current(connection, viewer)
        handler = HandlerService(self.store)
        setup_revision, setup = handler.current(connection)
        roster = handler._roster(connection)
        profile = json.loads(
            connection.execute(
                sa.select(t.characters.c.public_json).where(
                    t.characters.c.campaign_id == self.store.campaign_id,
                    t.characters.c.user_id == str(viewer.user_id),
                )
            ).scalar_one()
        )
        issues = [
            ReviewIssue(code="creation", message=x)
            for x in progress.draft.missing(
                progress.pair_choice.names if progress.pair_choice else ()
            )
        ]
        details = progress.draft.girl_details or GirlDetails()
        coordination = CoordinationService(self.store).accepted(connection, viewer.user_id)
        roles = {x.role for x in coordination}
        girl = progress.draft.girl_playbook
        if girl == "OLDGEN" and len(details.maxims) != 2:
            issues.append(
                ReviewIssue(code="maxims", message="Choose Oldgen's two starting maxims.")
            )
        if girl == "PRINCESS":
            if details.own_standard is None:
                issues.append(
                    ReviewIssue(code="own_standard", message="Choose your Princess standard.")
                )
            for role, label in (("princess_peer", "bonded Girl"), ("princess_handler", "Handler")):
                if role not in roles:
                    issues.append(
                        ReviewIssue(
                            code=role,
                            message="Review a Princess standard chosen by your " + label + ".",
                        )
                    )
        if girl == "VATGROWN":
            if {x.npc_slot for x in details.investors} != {
                x.slot for x in progress.draft.npc_bonds
            } or not progress.draft.npc_bonds:
                issues.append(
                    ReviewIssue(
                        code="npc_investors",
                        message="Choose desires for each starting NPC investor.",
                    )
                )
            if "vatgrown_handler" not in roles:
                issues.append(
                    ReviewIssue(
                        code="handler_investor",
                        message="Review the Handler's own investor desires.",
                    )
                )
        if self.store.policy.owner_initial_conditions is None:
            issues.append(
                ReviewIssue(
                    code="initial_conditions",
                    category="unresolved",
                    message="Initial marks, damage, NPC depth and Permissions are unresolved.",
                )
            )
        if progress.revision == 0 or progress.playbooks_changed:
            issues.append(
                ReviewIssue(code="save_creation", message="Save current creation progress.")
            )
        active_handler = setup.handler_id is not None and handler._member(
            connection, setup.handler_id
        )
        if not active_handler:
            issues.append(
                ReviewIssue(code="handler", message="Appoint an active campaign Handler.")
            )
        if setup.handler_id == viewer.user_id:
            issues.append(
                ReviewIssue(code="pilot", message="The Handler account is outside Pilot creation.")
            )
        rank_ids = [x.user_id for x in setup.status_order]
        rank_fresh = bool(
            active_handler and len(rank_ids) >= 2 and set(rank_ids) == set(roster)
        ) and all(
            x.user_id in roster and roster[x.user_id]["revision"] == x.character_revision
            for x in setup.status_order
        )
        status = None
        if rank_fresh and viewer.user_id in rank_ids:
            position = rank_ids.index(viewer.user_id)
            status = "Ace" if position == 0 else "Dog" if position == len(rank_ids) - 1 else "Wings"
        if status is None:
            issues.append(
                ReviewIssue(
                    code="status", message="Handler must confirm a current complete Status order."
                )
            )
        if progress.draft.girl_playbook == "PRINCESS" and status != "Ace":
            issues.append(ReviewIssue(code="princess_ace", message="Princess must start as Ace."))
        bonds = BondService(self.store)
        current_bonds = [
            x
            for x in bonds._latest(connection, str(viewer.user_id))
            if x["state"] == "accepted" and not bonds._stale(connection, x)
        ]
        chosen = [
            x
            for x in current_bonds
            if (
                x["id"] == progress.draft.starting_bond_id
                if progress.draft.starting_bond_id
                else x["source_id"] == str(viewer.user_id)
            )
            and starting_kind(x["girl_playbook"]) == starting_kind(progress.draft.girl_playbook)
            and (
                progress.draft.girl_playbook not in ("NEWGIRL", "BONDED")
                or x["source_id"] == str(viewer.user_id)
            )
        ]
        if len(chosen) != 1:
            issues.append(
                ReviewIssue(
                    code="starting_bond",
                    message="Choose an accepted starting Bond with your required role and depth.",
                )
            )
        if progress.draft.girl_playbook == "NEWGIRL":
            cadre = handler.cadre(connection, viewer.user_id)
            declared = {x.user_id: x.character_revision for x in progress.draft.prior_missions}
            if not cadre or declared != cadre:
                issues.append(
                    ReviewIssue(
                        code="cadre_history",
                        message="Declare zero or one shared mission with each Cadre counterpart.",
                    )
                )
            if not progress.draft.cadre_discussed:
                issues.append(
                    ReviewIssue(
                        code="cadre_discussion",
                        message="Confirm you discussed these mission histories with the Cadre.",
                    )
                )
        rulings = handler.effective_rulings(connection)
        if rulings is None:
            issues.append(
                ReviewIssue(
                    code="starting_resources",
                    category="unresolved",
                    message="Starting Heat/hunger/obsolescence require explicit campaign rulings.",
                )
            )
        elif rulings.requisition_mode != "long_game":
            issues.append(
                ReviewIssue(
                    code="starting_requisition",
                    category="unresolved",
                    message="Short-game starting Requisition selection is not implemented.",
                )
            )
        issues.append(
            ReviewIssue(
                code="independent_review",
                category="review",
                message="Independent rules review and playable activation remain pending.",
            )
        )
        name = next(
            (x.value for x in progress.shared_choices if x.kind == "callsign"), profile["callsign"]
        )
        sheet = ReviewSheet(
            owner=viewer.user_id,
            callsign=profile["callsign"],
            activation_callsign=name,
            character_revision=progress.character_revision,
            creation_revision=progress.revision,
            setup_revision=setup_revision,
            creation=progress.draft,
            bonds=tuple(
                SheetBond(
                    id=x["id"],
                    revision=x["revision"],
                    counterpart=int(
                        x["target_id"] if x["source_id"] == str(viewer.user_id) else x["source_id"]
                    ),
                    outgoing=x["source_id"] == str(viewer.user_id),
                    depth=starting_kind(x["girl_playbook"]),
                    context=x["context"],
                )
                for x in sorted(current_bonds, key=lambda x: x["id"])
            ),
            shared=progress.shared_choices,
            received_court=SharedSetupService(self.store).received_court(
                connection, viewer.user_id
            ),
            coordination=coordination,
            initial_conditions=self.store.policy.owner_initial_conditions,
            psych_strings=(
                tuple(
                    PsychStringAnchor(
                        kind="pilot",
                        reference=str(
                            x["target_id"]
                            if x["source_id"] == str(viewer.user_id)
                            else x["source_id"]
                        ),
                        source_token=x["id"] + ":" + str(x["revision"]),
                    )
                    for x in sorted(current_bonds, key=lambda x: x["id"])
                )
                + tuple(
                    PsychStringAnchor(
                        kind="npc_role",
                        reference=f"npc:{viewer.user_id}:{x.slot}",
                        source_token=f"creation:{progress.revision}",
                    )
                    for x in progress.draft.npc_bonds
                )
            )
            if progress.draft.frame_playbook == "CHANGELING"
            else (),
            status=status,
            rulings=rulings,
            issues=tuple(issues),
            dependency_tokens=tuple(
                f"pilot:{uid}:{data['revision']}" for uid, data in sorted(roster.items())
            )
            + ("handler_active:" + str(active_handler),),
        )
        fingerprint = hashlib.sha256(
            json.dumps(sheet.model_dump(mode="json"), sort_keys=True).encode()
        ).hexdigest()
        saved = self._latest(connection, viewer)
        return CurrentReview(
            sheet,
            fingerprint,
            saved["revision"] if saved else 0,
            saved is not None and saved["dependency_hash"] == fingerprint,
        )

    def get(self, viewer: GuildViewer) -> CurrentReview:
        with self.store.engine.connect() as connection:
            connection.exec_driver_sql("BEGIN")
            return self._current(connection, viewer)

    def saved(self, viewer: GuildViewer) -> ReviewSheet | None:
        with self.store.engine.connect() as connection:
            self.store.guild_member(viewer)
            self.store._membership(connection, viewer)
            row = self._latest(connection, viewer)
            return ReviewSheet.model_validate_json(row["body_json"]) if row else None

    def save(
        self, viewer: GuildViewer, key: str, expected_revision: int, fingerprint: str
    ) -> dict[str, Any]:
        def authorize(connection: Connection) -> None:
            self.store.guild_member(viewer)
            self.store._membership(connection, viewer)
            if self._current(connection, viewer).fingerprint != fingerprint:
                raise WorkflowError(
                    "STALE_REVIEW: choices or setup changed. Refresh before saving."
                )

        def operation(connection: Connection) -> dict[str, Any]:
            current = self._current(connection, viewer)
            if current.saved_revision != expected_revision:
                raise WorkflowError("STALE_REVISION: another review snapshot was saved. Refresh.")
            result = {"revision": expected_revision + 1, "state": "draft_rules_unverified"}
            event = self.store._audit(
                connection, viewer.user_id, key, "character.review_saved", result
            )
            connection.execute(
                t.creation_reviews.insert().values(
                    campaign_id=self.store.campaign_id,
                    user_id=str(viewer.user_id),
                    revision=result["revision"],
                    dependency_hash=fingerprint,
                    body_json=current.sheet.model_dump_json(),
                    event_id=event,
                )
            )
            return result

        return self.store._write(
            viewer,
            key,
            "character.review_saved",
            {"expected_revision": expected_revision, "fingerprint": fingerprint},
            operation,
            auto_audit=False,
            authorize=authorize,
        )

    def activate(self, viewer: GuildViewer) -> None:
        self.get(viewer)
        raise WorkflowError(
            "UNSUPPORTED_RULE: independent rules review and activation are not complete."
        )

    def select_bond(
        self,
        viewer: GuildViewer,
        key: str,
        creation_revision: int,
        character_revision: int,
        draft: CreationDraft,
        identity: str | None,
    ) -> dict[str, Any]:
        chosen = draft.model_copy(update={"starting_bond_id": identity})
        return CreationService(self.store).save(
            viewer,
            key,
            creation_revision,
            character_revision,
            chosen,
            expected_pair_token=draft.pair_source_token,
        )
