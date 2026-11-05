"""Original setter-owned consent for a source-locked Girl Tag."""

from typing import Any

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine.m2 import GameState, Obligation
from girlframe.engine.m3_actors import fingerprint
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.onboarding import OnboardingStore, WorkflowError
from girlframe.services.read_only_bot import GuildViewer


class PermissionService:
    def __init__(self, store: OnboardingStore):
        self.store, self.game = store, GameService(store)

    def _gate(
        self, c: Connection, viewer: GuildViewer, identity: str
    ) -> tuple[GameState, Obligation]:
        self.game.authorize(c, viewer, game=False)
        state = load_state(c, self.store.campaign_id)
        gate = next(
            (
                x
                for x in state.obligations
                if x.id == identity
                and x.kind == "tag_rejection_permission"
                and viewer.user_id in (x.owner, x.target)
            ),
            None,
        )
        if gate is None:
            raise WorkflowError(
                "This Tag permission belongs to its original participants or is unavailable."
            )
        responses, history = t.m2["m2_responses"], t.m2["m2_state_history"]
        body = c.scalar(
            sa.select(history.c.body_json)
            .join(
                responses,
                sa.and_(
                    responses.c.event_id == history.c.event_id,
                    responses.c.campaign_id == history.c.campaign_id,
                ),
            )
            .where(
                history.c.campaign_id == self.store.campaign_id,
                responses.c.choice_id == gate.details.get("effect_choice"),
            )
        )
        original = GameState.model_validate_json(body) if body else None
        first = (
            next((x for x in original.obligations if x.id == gate.id), None) if original else None
        )
        if (
            first is None
            or first.state != "pending"
            or any(
                getattr(first, key) != getattr(gate, key)
                for key in ("id", "kind", "owner", "target", "action", "details")
            )
        ):
            raise WorkflowError(
                "SOURCE_TAG_PERMISSION_MISSING: recover the original effect and decision."
            )
        return state, gate

    def _get(self, c: Connection, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        state, gate = self._gate(c, viewer, identity)
        target = state.sheets.get(str(gate.target))
        present = bool(target and any(x.id == gate.details["tag"] for x in target.tags))
        current = True
        for owner, field in ((gate.owner, "owner_character"), (gate.target, "target_character")):
            try:
                if (
                    owner is None
                    or self.game.character_binding(c, state, owner, require_current_profile=False)
                    != gate.details[field]
                ):
                    current = False
            except WorkflowError:
                current = False
        return dict(
            id=identity,
            label=gate.details["label"],
            owner=viewer.user_id == gate.owner,
            active=gate.state == "pending" and present,
            allowed=gate.state == "fulfilled",
            can_consent=current
            and present
            and gate.state == "pending"
            and viewer.user_id == gate.owner,
            stale=not current,
            source_sha256=fingerprint(gate),
        )

    def get(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            return self._get(c, viewer, identity)

    def grant(
        self, viewer: GuildViewer, key: str, identity: str, expected: str, confirmed: bool
    ) -> dict[str, Any]:
        def access(c: Connection) -> None:
            Access(self.store).authorize(c, viewer, "plays")
            _, gate = self._gate(c, viewer, identity)
            if gate.owner != viewer.user_id:
                raise WorkflowError("Only the original setter may consent to rejecting this Tag.")

        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            data = self._get(c, viewer, identity)
            if (
                confirmed is not True
                or data["source_sha256"] != expected
                or not data["can_consent"]
            ):
                raise WorkflowError(
                    "STALE_TAG_PERMISSION: reopen the original active characters and confirm."
                )
            state, gate = self._gate(c, viewer, identity)
            gate.state = "fulfilled"
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.tag_rejection_permission_granted",
                state,
                permission_id=identity,
            )
            return dict(id=identity, allowed=True)

        return self.store._write(
            viewer,
            key,
            "m3.tag_rejection_permission_granted",
            dict(id=identity, expected=expected, confirmed=confirmed),
            operation,
            auto_audit=False,
            authorize=access,
        )
