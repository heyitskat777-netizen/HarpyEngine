"""Owner-only creation progress with immutable revisions and no gameplay activation."""

import json
from dataclasses import dataclass
from typing import Any

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine.bonds import starting_kind
from girlframe.engine.creation import CreationDraft
from girlframe.engine.frame_setup import frame_setup
from girlframe.engine.pair_assets import PairChoice
from girlframe.engine.shared_setup import AcceptedSetup
from girlframe.services.bonds import BondService
from girlframe.services.handler_setup import HandlerService
from girlframe.services.onboarding import OnboardingStore, WorkflowError
from girlframe.services.pair_assets import PairService
from girlframe.services.read_only_bot import GuildViewer
from girlframe.services.shared_setup import SharedSetupService


@dataclass(frozen=True)
class CreationProgress:
    revision: int
    character_revision: int
    draft: CreationDraft
    playbooks_changed: bool = False
    pair_choice: PairChoice | None = None
    shared_choices: tuple[AcceptedSetup, ...] = ()


class CreationService:
    def __init__(self, store: OnboardingStore):
        self.store = store

    def _current(self, connection: Connection, viewer: GuildViewer) -> CreationProgress:
        self.store.guild_member(viewer)
        self.store._membership(connection, viewer)
        character = (
            connection.execute(
                sa.select(t.characters).where(
                    t.characters.c.campaign_id == self.store.campaign_id,
                    t.characters.c.user_id == str(viewer.user_id),
                )
            )
            .mappings()
            .first()
        )
        if character is None:
            raise WorkflowError("Save a character draft with /character create first.")
        profile = json.loads(character["public_json"])
        empty = CreationDraft(
            girl_playbook=profile["girl_playbook"],
            frame_playbook=profile["frame_playbook"],
            frame_setup=frame_setup(profile["frame_playbook"]),
        )
        pair = (
            PairService(self.store).for_owner(connection, viewer)
            if empty.girl_playbook == "BONDED"
            else None
        )
        empty = empty.model_copy(update={"pair_source_token": pair.token if pair else None})
        shared = SharedSetupService(self.store).accepted_for(connection, viewer.user_id)
        empty = empty.model_copy(update={"shared_tokens": tuple(x.token for x in shared)})
        row = (
            connection.execute(
                sa.select(t.creation_drafts)
                .where(
                    t.creation_drafts.c.campaign_id == self.store.campaign_id,
                    t.creation_drafts.c.user_id == str(viewer.user_id),
                )
                .order_by(t.creation_drafts.c.revision.desc())
                .limit(1)
            )
            .mappings()
            .first()
        )
        if row is None:
            return CreationProgress(
                0, character["revision"], empty, pair_choice=pair, shared_choices=shared
            )
        draft = CreationDraft.model_validate_json(row["body_json"])
        changed = (draft.girl_playbook, draft.frame_playbook) != (
            empty.girl_playbook,
            empty.frame_playbook,
        )
        draft = (
            empty
            if changed
            else draft.model_copy(update={"frame_setup": frame_setup(draft.frame_playbook)})
        )
        if draft.girl_playbook == "BONDED":
            draft = draft.model_copy(
                update={
                    "pair_source_token": pair.token if pair else None,
                    "pair_asset_descriptions": tuple(
                        x
                        for x in draft.pair_asset_descriptions
                        if pair is not None and x.name in pair.names
                    ),
                }
            )
        draft = draft.model_copy(update={"shared_tokens": tuple(x.token for x in shared)})
        return CreationProgress(
            row["revision"], character["revision"], draft, changed, pair, shared
        )

    def get(self, viewer: GuildViewer) -> CreationProgress:
        with self.store.engine.connect() as connection:
            return self._current(connection, viewer)

    def cadre(self, viewer: GuildViewer) -> dict[int, dict[str, Any]]:
        with self.store.engine.connect() as connection:
            connection.exec_driver_sql("BEGIN")
            progress = self._current(connection, viewer)
            if progress.draft.girl_playbook != "NEWGIRL":
                raise WorkflowError("Prior-mission declarations are a Newgirl creation step.")
            handler = HandlerService(self.store)
            roster = handler._roster(connection)
            return {
                uid: {
                    "revision": revision,
                    "label": roster[uid]["callsign"] if uid in roster else "Handler",
                }
                for uid, revision in handler.cadre(connection, viewer.user_id).items()
            }

    def save(
        self,
        viewer: GuildViewer,
        key: str,
        expected_revision: int,
        character_revision: int,
        draft: CreationDraft,
        *,
        expected_pair_token: str | None = None,
    ) -> dict[str, Any]:
        self.get(viewer)  # Membership must still be valid even on inbox replay.
        draft = CreationDraft.model_validate_json(draft.model_dump_json())
        draft = draft.model_copy(update={"frame_setup": frame_setup(draft.frame_playbook)})

        def authorize(connection: Connection) -> None:
            from girlframe.services.m2_state import active

            if active(connection, self.store.campaign_id, viewer.user_id):
                raise WorkflowError(
                    "ACTIVE_CHARACTER: creation editors cannot reset an activated character."
                )
            current = self._current(connection, viewer)
            token = current.pair_choice.token if current.pair_choice else None
            if token != expected_pair_token or draft.pair_source_token != token:
                raise WorkflowError("STALE_PAIR: reopen /character build; Pair selection changed.")
            if draft.shared_tokens != current.draft.shared_tokens:
                raise WorkflowError("STALE_SETUP: reopen /character build; shared choices changed.")
            names = set(current.pair_choice.names) if current.pair_choice else set()
            if not {x.name for x in draft.pair_asset_descriptions} <= names:
                raise WorkflowError("Describe only the Girl Assets selected by your current Pair.")
            if draft.girl_playbook == "NEWGIRL":
                cadre = HandlerService(self.store).cadre(connection, viewer.user_id)
                declarations = {x.user_id: x.character_revision for x in draft.prior_missions}
                if any(uid not in cadre or cadre[uid] != rev for uid, rev in declarations.items()):
                    raise WorkflowError("STALE_CADRE: reopen mission history; the roster changed.")
                if draft.cadre_discussed and (not cadre or declarations != cadre):
                    raise WorkflowError(
                        "Discuss and declare history for every current Cadre counterpart."
                    )
            if draft.starting_bond_id:
                bonds = BondService(self.store)
                row = next(
                    (
                        x
                        for x in bonds._latest(connection, str(viewer.user_id))
                        if x["id"] == draft.starting_bond_id
                    ),
                    None,
                )
                if row is None or row["state"] != "accepted" or bonds._stale(connection, row):
                    raise WorkflowError("STALE_BOND: choose a current accepted starting Bond.")
                if starting_kind(row["girl_playbook"]) != starting_kind(draft.girl_playbook) or (
                    draft.girl_playbook in ("NEWGIRL", "BONDED")
                    and row["source_id"] != str(viewer.user_id)
                ):
                    raise WorkflowError(
                        "This Bond does not meet your playbook's starting role/depth."
                    )

        def operation(connection: Connection) -> dict[str, Any]:
            current = self._current(connection, viewer)
            if (
                current.revision != expected_revision
                or current.character_revision != character_revision
            ):
                raise WorkflowError("STALE_REVISION: reopen /character build; progress preserved.")
            if (draft.girl_playbook, draft.frame_playbook) != (
                current.draft.girl_playbook,
                current.draft.frame_playbook,
            ):
                raise WorkflowError("Creation choices must match your saved character playbooks.")
            result = {"revision": expected_revision + 1, "status": "creation_in_progress"}
            event = self.store._audit(
                connection, viewer.user_id, key, "character.creation_saved", result
            )
            connection.execute(
                t.creation_drafts.insert().values(
                    campaign_id=self.store.campaign_id,
                    user_id=str(viewer.user_id),
                    revision=expected_revision + 1,
                    character_revision=character_revision,
                    event_id=event,
                    body_json=draft.model_dump_json(),
                )
            )
            return result

        return self.store._write(
            viewer,
            key,
            "character.creation_saved",
            {
                "expected_revision": expected_revision,
                "character_revision": character_revision,
                "draft": draft.model_dump(mode="json"),
                "pair_token": expected_pair_token,
            },
            operation,
            auto_audit=False,
            authorize=authorize,
        )
