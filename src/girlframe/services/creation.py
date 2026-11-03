"""Owner-only creation progress with immutable revisions and no gameplay activation."""

import json
from dataclasses import dataclass
from typing import Any

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine.creation import CreationDraft
from girlframe.services.onboarding import OnboardingStore, WorkflowError
from girlframe.services.read_only_bot import GuildViewer


@dataclass(frozen=True)
class CreationProgress:
    revision: int
    character_revision: int
    draft: CreationDraft
    playbooks_changed: bool = False


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
            girl_playbook=profile["girl_playbook"], frame_playbook=profile["frame_playbook"]
        )
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
            return CreationProgress(0, character["revision"], empty)
        draft = CreationDraft.model_validate_json(row["body_json"])
        changed = (draft.girl_playbook, draft.frame_playbook) != (
            empty.girl_playbook,
            empty.frame_playbook,
        )
        return CreationProgress(
            row["revision"], character["revision"], empty if changed else draft, changed
        )

    def get(self, viewer: GuildViewer) -> CreationProgress:
        with self.store.engine.connect() as connection:
            return self._current(connection, viewer)

    def save(
        self,
        viewer: GuildViewer,
        key: str,
        expected_revision: int,
        character_revision: int,
        draft: CreationDraft,
    ) -> dict[str, Any]:
        self.get(viewer)  # Membership must still be valid even on inbox replay.
        draft = CreationDraft.model_validate_json(draft.model_dump_json())

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
            },
            operation,
            auto_audit=False,
        )
