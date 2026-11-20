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
from girlframe.engine.playbooks import normalize_frame_fields
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

    def _latest(self, connection: Connection, owner: int) -> dict[str, Any] | None:
        row = (
            connection.execute(
                sa.select(t.creation_reviews)
                .where(
                    t.creation_reviews.c.campaign_id == self.store.campaign_id,
                    t.creation_reviews.c.user_id == str(owner),
                )
                .order_by(t.creation_reviews.c.revision.desc())
                .limit(1)
            )
            .mappings()
            .first()
        )
        return dict(row) if row else None

    def _current(self, connection: Connection, viewer: GuildViewer) -> CurrentReview:
        self.store.guild_member(viewer)
        self.store._membership(connection, viewer)
        return self._current_for_owner(connection, viewer.user_id)

    def _current_for_owner(self, connection: Connection, owner: int) -> CurrentReview:
        progress = CreationService(self.store)._current_for_owner(connection, owner)
        handler = HandlerService(self.store)
        setup_revision, setup = handler.current(connection)
        roster = handler._roster(connection)
        profile = json.loads(
            connection.execute(
                sa.select(t.characters.c.public_json).where(
                    t.characters.c.campaign_id == self.store.campaign_id,
                    t.characters.c.user_id == str(owner),
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
        coordination = CoordinationService(self.store).accepted(connection, owner)
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
        rank_ids = [x.user_id for x in setup.status_order]
        rank_fresh = bool(
            active_handler and len(rank_ids) >= 2 and set(rank_ids) == set(roster)
        ) and all(
            x.user_id in roster and roster[x.user_id]["revision"] == x.character_revision
            for x in setup.status_order
        )
        status = None
        status_dependencies: tuple[str, ...] = ()
        from girlframe.engine.m3_careers import binding
        from girlframe.services.m2_state import load_state

        canonical = load_state(connection, self.store.campaign_id)
        career = binding(canonical, owner)
        if career and career.previous_archive and str(owner) not in canonical.sheets:
            rank_ids = []
            if (
                active_handler
                and canonical.handler == setup.handler_id
                and career.active
                and career.status_event
                and career.status_position is not None
                and 0 <= career.status_position <= len(canonical.order)
            ):
                rank_ids = list(canonical.order)
                rank_ids.insert(career.status_position, owner)
                status_dependencies = (
                    "replacement_status:" + career.status_event,
                    "canonical_status_order:" + ",".join(map(str, rank_ids)),
                )
        elif (
            not rank_fresh
            and active_handler
            and canonical.handler == setup.handler_id
            and owner in canonical.order
        ):
            rank_ids = list(canonical.order)
            status_dependencies = ("canonical_status_order:" + ",".join(map(str, rank_ids)),)
        elif not rank_fresh:
            rank_ids = []
        if owner in rank_ids:
            position = rank_ids.index(owner)
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
            for x in bonds._latest(connection, str(owner))
            if x["state"] == "accepted" and not bonds._stale(connection, x)
        ]
        chosen = [
            x
            for x in current_bonds
            if (
                x["id"] == progress.draft.starting_bond_id
                if progress.draft.starting_bond_id
                else x["source_id"] == str(owner)
                and x["id"] != progress.draft.additional_starting_bond_id
            )
            and starting_kind(x["girl_playbook"]) == starting_kind(progress.draft.girl_playbook)
            and (
                progress.draft.girl_playbook not in ("NEWGIRL", "BONDED")
                or x["source_id"] == str(owner)
            )
        ]
        optional_second = (
            self.store.policy.owner_starting_bond_count == 2
            and self.store.policy.owner_second_starting_bond_optional
        )
        required_bonds = 1 if optional_second else self.store.policy.owner_starting_bond_count
        test_bypass = any(
            x.user_id == owner and x.character_revision == progress.character_revision
            for x in setup.starting_bond_test_bypasses
        )
        if len(chosen) != 1 and not test_bypass:
            issues.append(
                ReviewIssue(
                    code="starting_bond",
                    message="Choose an accepted starting Bond with your required role and depth.",
                )
            )
        if (required_bonds == 2 or progress.draft.additional_starting_bond_id) and not test_bypass:
            extra = next(
                (x for x in current_bonds if x["id"] == progress.draft.additional_starting_bond_id),
                None,
            )

            def counterpart(row: dict[str, Any]) -> str:
                return str(
                    row["target_id"]
                    if row["source_id"] == str(owner)
                    else row["source_id"]
                )

            if (
                extra is None
                or starting_kind(extra["girl_playbook"]) != "Personal"
                or len(chosen) != 1
                or counterpart(extra) == counterpart(chosen[0])
            ):
                issues.append(
                    ReviewIssue(
                        code="additional_starting_bond",
                        message="House rule: select a second accepted Personal Bond "
                        "with a different character."
                        + (
                            " You may clear this optional second choice instead."
                            if optional_second
                            else ""
                        ),
                    )
                )
        if progress.draft.girl_playbook == "NEWGIRL":
            cadre = handler.cadre(connection, owner)
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
        from girlframe.engine.m2_registry import registry_digest

        approval = self.store.policy.m2_approval
        release_enabled = (
            approval is not None
            and approval.registry_sha256 == registry_digest()
            and self.store.policy.owner_intense_tag_bonus is not None
        )
        issues.append(
            ReviewIssue(
                code="independent_review",
                category="review",
                message=(
                    "Scoped gameplay release is enabled. Complete and save this review, "
                    "then use /character activate. Broader rules certification remains separate."
                    if release_enabled
                    else "Independent rules review and playable activation remain pending."
                ),
            )
        )
        name = next(
            (x.value for x in progress.shared_choices if x.kind == "callsign"), profile["callsign"]
        )
        sheet = ReviewSheet(
            owner=owner,
            callsign=profile["callsign"],
            activation_callsign=name,
            character_revision=progress.character_revision,
            creation_revision=progress.revision,
            setup_revision=setup_revision,
            creation=progress.draft,
            required_starting_bonds=required_bonds,
            optional_second_starting_bond=optional_second,
            starting_bond_test_bypass=test_bypass,
            bonds=tuple(
                SheetBond(
                    id=x["id"],
                    revision=x["revision"],
                    counterpart=int(
                        x["target_id"] if x["source_id"] == str(owner) else x["source_id"]
                    ),
                    outgoing=x["source_id"] == str(owner),
                    depth=starting_kind(x["girl_playbook"]),
                    context=x["context"],
                )
                for x in sorted(current_bonds, key=lambda x: x["id"])
            ),
            shared=progress.shared_choices,
            received_court=SharedSetupService(self.store).received_court(
                connection, owner
            ),
            coordination=coordination,
            initial_conditions=self.store.policy.owner_initial_conditions,
            psych_strings=(
                tuple(
                    PsychStringAnchor(
                        kind="pilot",
                        reference=str(
                            x["target_id"]
                            if x["source_id"] == str(owner)
                            else x["source_id"]
                        ),
                        source_token=x["id"] + ":" + str(x["revision"]),
                    )
                    for x in sorted(current_bonds, key=lambda x: x["id"])
                )
                + tuple(
                    PsychStringAnchor(
                        kind="npc_role",
                        reference=f"npc:{owner}:{x.slot}",
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
            + ("handler_active:" + str(active_handler),)
            + status_dependencies,
        )
        body = sheet.model_dump(mode="json")
        fingerprint = hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()
        saved = self._latest(connection, owner)
        saved_current = saved is not None and saved["dependency_hash"] == fingerprint
        if saved is not None and not saved_current:
            previous = json.loads(saved["body_json"])
            saved_current = (
                normalize_frame_fields(previous) == body
                and hashlib.sha256(json.dumps(previous, sort_keys=True).encode()).hexdigest()
                == saved["dependency_hash"]
            )
        return CurrentReview(
            sheet,
            fingerprint,
            saved["revision"] if saved else 0,
            saved_current,
        )

    def get(self, viewer: GuildViewer) -> CurrentReview:
        with self.store.engine.connect() as connection:
            connection.exec_driver_sql("BEGIN")
            return self._current(connection, viewer)

    def saved(self, viewer: GuildViewer) -> ReviewSheet | None:
        with self.store.engine.connect() as connection:
            self.store.guild_member(viewer)
            self.store._membership(connection, viewer)
            row = self._latest(connection, viewer.user_id)
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
        *,
        additional: bool = False,
    ) -> dict[str, Any]:
        field = "additional_starting_bond_id" if additional else "starting_bond_id"
        chosen = draft.model_copy(update={field: identity})
        return CreationService(self.store).save(
            viewer,
            key,
            creation_revision,
            character_revision,
            chosen,
            expected_pair_token=draft.pair_source_token,
        )
