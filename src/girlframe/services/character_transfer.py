"""Atomic owner-only creation imports and explicitly filtered display exports."""

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Literal

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe import __version__
from girlframe.database import tables as t
from girlframe.engine.character_documents import (
    CharacterDraftDocument,
    CharacterSheetDocument,
    PortableChoices,
    encode_document,
    parse_draft,
)
from girlframe.engine.creation import CreationDraft
from girlframe.engine.frame_setup import frame_setup
from girlframe.engine.m2 import GameState, PilotSheet
from girlframe.engine.m3_actor_bonds import current_ref, depth
from girlframe.engine.playbooks import normalize_frame_fields
from girlframe.services.creation import CreationProgress, CreationService
from girlframe.services.creation_review import CreationReviewService
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import active, load_state, public_sheet
from girlframe.services.onboarding import OnboardingStore, WorkflowError
from girlframe.services.read_only_bot import GuildViewer


@dataclass(frozen=True)
class ImportPreview:
    owner: int
    campaign: str
    document: CharacterDraftDocument
    digest: str
    profile_revision: int
    creation_revision: int
    context: str
    changes: tuple[str, ...]
    warnings: tuple[str, ...]


class CharacterTransferService:
    def __init__(self, store: OnboardingStore):
        self.store = store
        self.creation = CreationService(store)
        self.game = GameService(store)

    def _authorize(self, c: Connection, viewer: GuildViewer) -> None:
        self.store.guild_member(viewer)
        self.store._membership(c, viewer)
        if not self.store._binding_matches(c):
            raise WorkflowError("Campaign binding changed; reopen character setup.")

    def authorize(self, viewer: GuildViewer) -> None:
        with self.store.engine.connect() as c:
            self._authorize(c, viewer)

    def _profile(self, c: Connection, owner: int) -> dict[str, Any] | None:
        row = (
            c.execute(
                sa.select(t.characters).where(
                    t.characters.c.campaign_id == self.store.campaign_id,
                    t.characters.c.user_id == str(owner),
                )
            )
            .mappings()
            .first()
        )
        return dict(row) if row else None

    def _context(
        self, c: Connection, viewer: GuildViewer
    ) -> tuple[int, int, str, CreationProgress | None]:
        row = self._profile(c, viewer.user_id)
        progress = self.creation._current(c, viewer) if row else None
        profile_revision = row["revision"] if row else 0
        creation_revision = progress.revision if progress else 0
        bindings = {
            "profile": profile_revision,
            "creation": creation_revision,
            "pair": progress.draft.pair_source_token if progress else None,
            "shared": progress.draft.shared_tokens if progress else (),
            "primary": progress.draft.starting_bond_id if progress else None,
            "second": progress.draft.additional_starting_bond_id if progress else None,
        }
        digest = hashlib.sha256(json.dumps(bindings, sort_keys=True).encode()).hexdigest()
        return profile_revision, creation_revision, digest, progress

    @staticmethod
    def _profile_data(row: dict[str, Any] | None) -> dict[str, Any]:
        return (
            dict(normalize_frame_fields(json.loads(row["public_json"])))
            | json.loads(row["private_json"])
            if row
            else {}
        )

    def preview(self, viewer: GuildViewer, raw: bytes) -> ImportPreview:
        self.authorize(viewer)
        document = parse_draft(raw)
        with self.store.engine.connect() as c:
            c.exec_driver_sql("BEGIN")
            self._authorize(c, viewer)
            if active(c, self.store.campaign_id, viewer.user_id):
                raise WorkflowError("ACTIVE_CHARACTER: imports cannot replace an activated sheet.")
            row = self._profile(c, viewer.user_id)
            profile = self._profile_data(row)
            revision, creation_revision, context, progress = self._context(c, viewer)
            target = document.profile.as_profile(profile.get("notes", ""))
            changed_profile = target.model_dump() != profile
            if document.creation.pair_asset_descriptions and (
                changed_profile
                or progress is None
                or progress.pair_choice is None
                or not {x.name for x in document.creation.pair_asset_descriptions}
                <= set(progress.pair_choice.names)
            ):
                raise WorkflowError(
                    "PAIR_REQUIRED: Pair Asset descriptions require the actual current accepted "
                    "Pair selection. Import the base profile first, complete Pair setup, "
                    "then import descriptions without changing the profile."
                )
            changes = tuple(
                "profile." + key
                for key, value in target.model_dump().items()
                if profile.get(key) != value
            )
            old_choices = progress.draft.model_dump(mode="json") if progress else {}
            changes += tuple(
                "creation." + key
                for key, value in document.creation.model_dump(mode="json").items()
                if old_choices.get(key) != value
            )
            warnings = [
                "Imports save a draft only. Complete live coordination, save a fresh review "
                "and confirm activation separately.",
                "Imported choices replace the editable draft fields shown in this preview.",
            ]
            if changed_profile:
                warnings.append(
                    "Profile changes schedule ordinary role/nickname sync and may "
                    "stale existing Status and starting agreements; selected Bond references "
                    "must be reviewed again."
                )
            if target.girl_playbook in ("NEWGIRL", "BONDED", "PRINCESS", "VATGROWN"):
                warnings.append(
                    "Playbook choices belonging to other people still require "
                    "their actual live agreement. The file supplies none of their decisions."
                )
            return ImportPreview(
                viewer.user_id,
                self.store.campaign_id,
                document,
                hashlib.sha256(encode_document(document)).hexdigest(),
                revision,
                creation_revision,
                context,
                changes,
                tuple(warnings),
            )

    def apply(self, viewer: GuildViewer, key: str, preview: ImportPreview) -> dict[str, Any]:
        if preview.owner != viewer.user_id or preview.campaign != self.store.campaign_id:
            raise WorkflowError("This import preview belongs to another owner or campaign.")
        document = parse_draft(encode_document(preview.document))
        digest = hashlib.sha256(encode_document(document)).hexdigest()
        if digest != preview.digest:
            raise WorkflowError("IMPORT_CHANGED: preview this document again before saving.")

        def operation(c: Connection) -> dict[str, Any]:
            if active(c, self.store.campaign_id, viewer.user_id):
                raise WorkflowError("ACTIVE_CHARACTER: imports cannot replace an activated sheet.")
            revision, creation_revision, context, _ = self._context(c, viewer)
            if (revision, creation_revision, context) != (
                preview.profile_revision,
                preview.creation_revision,
                preview.context,
            ):
                raise WorkflowError("STALE_IMPORT: preview again; existing choices were preserved.")
            old_profile = self._profile_data(self._profile(c, viewer.user_id))
            profile = document.profile.as_profile(old_profile.get("notes", ""))
            profile_changed = profile.model_dump() != old_profile
            if profile_changed:
                result = self.store._save_draft_in_transaction(c, viewer, revision, profile)
                event = self.store._audit(
                    c, viewer.user_id, key + ":profile", "character.draft_saved", result
                )
                self.store._snapshot_draft(c, viewer.user_id, event)
            progress = self.creation._current(c, viewer)
            existing = progress.draft
            draft = document.to_creation(
                frame_setup=frame_setup(profile.frame_playbook),
                pair_source_token=existing.pair_source_token,
                shared_tokens=existing.shared_tokens,
                starting_bond_id=None if profile_changed else existing.starting_bond_id,
                additional_starting_bond_id=None
                if profile_changed
                else existing.additional_starting_bond_id,
                prior_missions=existing.prior_missions,
                cadre_discussed=False if profile_changed else existing.cadre_discussed,
            )
            self.creation._authorize_save(c, viewer, draft, existing.pair_source_token)
            saved = self.creation._save_in_transaction(
                c, viewer, key + ":creation", progress.revision, progress.character_revision, draft
            )
            outcome = {
                "profile_revision": progress.character_revision,
                "creation_revision": saved["revision"],
                "digest": digest,
                "status": "draft_rules_unverified",
            }
            self.store._audit(c, viewer.user_id, key, "character.document_imported", outcome)
            return outcome

        return self.store._write(
            viewer,
            key,
            "character.document_imported",
            {
                "digest": digest,
                "profile_revision": preview.profile_revision,
                "creation_revision": preview.creation_revision,
                "context": preview.context,
            },
            operation,
            auto_audit=False,
            authorize=lambda c: self._authorize(c, viewer),
        )

    def template(
        self, viewer: GuildViewer, include_private: bool = False
    ) -> CharacterDraftDocument:
        with self.store.engine.connect() as c:
            c.exec_driver_sql("BEGIN")
            self._authorize(c, viewer)
            row = self._profile(c, viewer.user_id)
            if row is None:
                raise WorkflowError("Save or import a character draft first.")
            profile = self._profile_data(row)
            progress = self.creation._current(c, viewer)
            choices = progress.draft.model_dump(mode="json")
            return CharacterDraftDocument.model_validate_json(
                json.dumps(
                    {
                        "format": "harpyengine.character-draft",
                        "schema_version": 1,
                        "profile": {
                            **{
                                key: profile[key]
                                for key in ("callsign", "girl_playbook", "frame_playbook")
                            },
                            "notes": profile.get("notes", "") if include_private else None,
                        },
                        "creation": {key: choices[key] for key in PortableChoices.model_fields},
                    }
                )
            )

    @staticmethod
    def _current_bonds(state: GameState, owner: int) -> list[dict[str, Any]]:
        subject = current_ref(state, owner)
        peers = [current_ref(state, int(key)) for key in state.sheets if int(key) != owner]
        if state.handler is not None:
            from girlframe.engine.m3_handler_consequences import active_handler

            handler = active_handler(state)
            if handler is not None:
                peers.append(handler)
        result = []
        for peer in peers:
            amount = depth(state, subject, peer)
            if amount:
                result.append(
                    {
                        "counterpart_id": peer.entity,
                        "role": peer.kind,
                        "depth": "Intense" if amount == 2 else "Personal",
                        "context": "",
                    }
                )
        return result

    def snapshot(
        self,
        viewer: GuildViewer,
        audience: Literal["owner", "public"] = "owner",
        owner: int | None = None,
        include_private: bool = False,
    ) -> CharacterSheetDocument:
        target = viewer.user_id if owner is None else owner
        if (
            audience not in ("owner", "public")
            or (audience == "owner" and target != viewer.user_id)
            or (include_private and audience != "owner")
        ):
            raise WorkflowError("Private character exports belong to their actual owner.")
        with self.store.engine.connect() as c:
            c.exec_driver_sql("BEGIN")
            self._authorize(c, viewer)
            row = self._profile(c, target)
            state = load_state(c, self.store.campaign_id)
            sheet = state.sheets.get(str(target))
            if row is None or (sheet is None and target != viewer.user_id and audience != "public"):
                raise WorkflowError("This character has no saved sheet.")
            profile = self._profile_data(row)
            if sheet is None:
                view: dict[str, Any] = {
                    key: profile[key] for key in ("callsign", "girl_playbook", "frame_playbook")
                }
                view["state"] = "draft_rules_unverified"
                revision = row["revision"]
                character_id = row["id"]
                if audience == "owner":
                    current = CreationReviewService(self.store)._current(c, viewer).sheet
                    draft = current.creation
                    revision = current.creation_revision
                    view.update(
                        callsign=current.activation_callsign,
                        profile_revision=current.character_revision,
                        creation_revision=current.creation_revision,
                        appearance=draft.girl_appearance,
                        frame_name=draft.frame_name,
                        frame_appearance=draft.frame_appearance,
                        identities=[{"name": x, "planned": True} for x in draft.identities],
                        assets=[
                            {
                                "name": x.name,
                                "description": x.description,
                                "family": family,
                                "void": family == "girl" and x.name == draft.void_asset,
                            }
                            for family, items in (
                                (
                                    "girl",
                                    draft.pair_asset_descriptions
                                    if draft.girl_playbook == "BONDED"
                                    else draft.girl_assets,
                                ),
                                ("frame", draft.frame_assets),
                            )
                            for x in items
                        ]
                        + [
                            {"name": name, "family": "frame", "planned": True}
                            for name in draft.intrinsic_frame_assets
                        ],
                        bonds=[
                            {
                                "counterpart_id": str(x.counterpart),
                                "depth": x.depth,
                                "context": "Draft agreement only: " + x.context,
                            }
                            for x in current.bonds
                        ],
                        creation_requirements=[x.message for x in current.issues],
                        starting_setup=self._starting_setup(draft),
                    )
            else:
                self.game.authorize(c, viewer, game=False)
                view = public_sheet(sheet, state)
                view["state"] = "active_m2_subset"
                revision, character_id = sheet.revision, sheet.character_id
                if audience == "owner":
                    view.update(self._owner_fields(sheet, state))
            if include_private:
                view["private_notes"] = profile.get("notes", "")
            return CharacterSheetDocument(
                engine_version=__version__,
                audience=audience,
                owner_id=str(target),
                character_id=character_id,
                revision=revision,
                sheet=view,
            )

    def _owner_fields(self, sheet: PilotSheet, state: GameState) -> dict[str, Any]:
        draft = sheet.review.creation
        frame = sheet.frame_runtime
        return {
            "heat": sheet.heat,
            "permissions": sheet.permissions,
            "appearance": draft.girl_appearance,
            "frame_name": frame.frame_name if frame else draft.frame_name,
            "frame_appearance": frame.frame_appearance if frame else draft.frame_appearance,
            "identities": [
                {"name": x.name, "marked": x.marked, "paired": x.paired} for x in sheet.identities
            ],
            "assets": [
                {
                    "name": x.name,
                    "family": x.family,
                    "description": x.description,
                    "damaged": x.damaged,
                    "void": x.void,
                    "concealed": x.concealed,
                }
                for x in sheet.assets
            ],
            "tags": [{"label": x.label, "marked": x.marked} for x in sheet.tags],
            "bonds": self._current_bonds(state, sheet.owner),
            "obsolescence_marked": sheet.obsolescence_marked,
            "status_marked": sheet.status_marked,
            "starting_setup": self._starting_setup(draft),
            "frame_scrapped": sheet.frame_scrapped,
            "medical_state": sheet.medical_state,
        }

    @staticmethod
    def _starting_setup(draft: CreationDraft) -> dict[str, Any]:
        fields = ("npc_bonds", "dna_basis", "fanbase", "girl_details")
        data = draft.model_dump(mode="json")
        return {
            "girl_playbook": draft.girl_playbook,
            "frame_playbook": draft.frame_playbook,
            **{key: data[key] for key in fields},
        }
