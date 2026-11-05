"""Revise uncommitted source choices; preserve actual effects, raw receipt and held root."""

from typing import TYPE_CHECKING, Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_actors import resolve
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_actors import profiles
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer

if TYPE_CHECKING:
    from girlframe.services.m2_game import GameService


class SexRevisionService:
    def __init__(self, game: "GameService"):
        self.game, self.store = game, game.store

    def _owned(self, c: Connection, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        action = self.game.action(c, identity)
        meta = action["data"].get("mockingbird", {})
        if meta.get("play") != "mockingbird_sex" or int(action["actor_id"]) != viewer.user_id:
            raise WorkflowError("Only the actual original caster can revise this source")
        state = load_state(c, self.store.campaign_id)
        actor = ActorRef.model_validate(meta["actor"])
        actual = resolve(
            state, actor, profiles(c, self.store.campaign_id), require_current_profile=False
        )
        if actual.controller != viewer.user_id:
            raise WorkflowError("A successor cannot revise the original person's choices")
        if (
            meta.get("sex_bond_applied")
            or meta.get("sex_effects")
            or meta.get("followups")
            or action["state"] in ("complete", "aborted")
            or not (meta.get("sex_transfer") or meta.get("sex_infection"))
        ):
            raise WorkflowError("Only an uncommitted resource selection may be revised")
        return action

    def get(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            action = self._owned(c, viewer, identity)
            return dict(
                id=identity, revision=action["revision"], receipt=action["data"]["receipt"]["id"]
            )

    def revise(self, viewer: GuildViewer, key: str, identity: str, revision: int) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            action = self._owned(c, viewer, identity)
            if action["revision"] != revision:
                raise WorkflowError("Reopen the current source selection before revising it")
            rows = self.game.pending(c, identity)
            if not rows or any(not x["kind"].startswith("mockingbird_sex_") for x in rows):
                raise WorkflowError(
                    "Finish the actual current source decision before resource revision"
                )
            event = str(uuid4())
            choices = t.m2["m2_choices"]
            c.execute(
                choices.update()
                .where(
                    choices.c.campaign_id == self.store.campaign_id,
                    choices.c.id.in_([x["id"] for x in rows]),
                    choices.c.state == "pending",
                )
                .values(state="superseded_uncommitted_choice", revision=choices.c.revision + 1)
            )
            meta = action["data"]["mockingbird"]
            meta.setdefault("sex_revisions", []).append(
                dict(
                    event=event,
                    transfer=meta.pop("sex_transfer", None),
                    infection=meta.pop("sex_infection", None),
                )
            )
            next_kind = (
                "mockingbird_sex_select"
                if action["data"]["result"]["tier"] == "mid"
                else "mockingbird_sex_infect"
            )
            self.game.request(c, action, viewer.user_id, next_kind)
            self.game.save_action(c, action)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.mockingbird_uncommitted_selection_revised",
                event_id=event,
                action_id=identity,
                receipt_id=action["data"]["receipt"]["id"],
            )
            return dict(id=identity, state=action["state"], receipt=action["data"]["receipt"]["id"])

        return self.store._write(
            viewer,
            key,
            "m3.mockingbird_uncommitted_selection_revised",
            dict(id=identity, revision=revision),
            operation,
            auto_audit=False,
            authorize=lambda c: Access(self.store).authorize(
                c, viewer, "plays", director_response=True
            ),
        )

    def _tasks(self, c: Connection, viewer: GuildViewer) -> list[dict[str, Any]]:
        self.game.authorize(c, viewer, game=False)
        actions = t.m2["m2_actions"]
        result = []
        for identity in c.scalars(
            sa.select(actions.c.id).where(
                actions.c.campaign_id == self.store.campaign_id,
                actions.c.actor_id == str(viewer.user_id),
                actions.c.state.not_in(("complete", "aborted")),
                sa.func.json_extract(actions.c.body_json, "$.mockingbird.play")
                == "mockingbird_sex",
            )
        ):
            try:
                action = self._owned(c, viewer, identity)
            except (ValueError, WorkflowError):
                continue
            result.append(
                dict(
                    id=identity,
                    revision=action["revision"],
                    kind="mockingbird_sex_revision",
                    state="uncommitted",
                    actionable=True,
                )
            )
        return result
