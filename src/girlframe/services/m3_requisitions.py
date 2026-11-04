"""Owned source-bound purchases; canon, payment and receipt commit in one transaction."""

from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from pydantic import ValidationError
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_requisitions as rules
from girlframe.engine.creation_catalog import CATALOG
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef, ActorView
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_requisition_state import Installation
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_actors import profiles
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer


class RequisitionService:
    def __init__(self, game: GameService):
        self.game, self.store = game, game.store

    def _actor(self, c: Connection, state: GameState, viewer: GuildViewer) -> ActorView:
        ref = ActorRef(
            kind="pilot",
            entity=str(viewer.user_id),
            incarnation=self.game.character_binding(c, state, viewer.user_id),
        )
        return resolve(state, ref, profiles(c, self.store.campaign_id))

    def view(self, viewer: GuildViewer) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            state = load_state(c, self.store.campaign_id)
            actor = self._actor(c, state, viewer)
            return {
                "actor": actor.ref.model_dump(mode="json"),
                "source_sha256": actor.source_sha256,
                "frame_instance": actor.frame_instance,
                "permissions": state.sheets[actor.ref.entity].permissions,
                "frame_assets": [
                    x.model_dump(mode="json") for x in actor.assets if x.family == "frame"
                ],
                "purchases": [
                    x.model_dump(mode="json") for x in state.requisitions if x.actor == actor.ref
                ],
                "catalog": [
                    dict(key=frame + ":" + str(index), frame=frame, index=index, name=name)
                    for frame, book in CATALOG.items()
                    if book["family"] == "frame"
                    for index, name in enumerate(book["assets"])
                ],
            }

    def _safe(self, c: Connection, state: GameState, owner: int) -> None:
        locks = t.m2["m2_locks"]
        if self.game.pending_actions(c) or c.scalar(
            sa.select(locks.c.channel_id)
            .where(
                locks.c.campaign_id == self.store.campaign_id,
                locks.c.state != "released",
            )
            .limit(1)
        ):
            raise WorkflowError("Finish pending Plays and restore chat before installing an Asset.")
        if self.game.immediate_work(c, owner) or any(
            x.owner == owner
            and x.state == "pending"
            and x.kind
            in (
                "defeat",
                "helpless",
                "girl_void_threshold",
                "frame_void_threshold",
                "mockingbird_resist",
            )
            for x in state.obligations
        ):
            raise WorkflowError(
                "REQUIRED_FOLLOWUP: resolve the actual immediate sheet consequence first."
            )

    def buy(
        self, viewer: GuildViewer, key: str, actor: ActorRef, expected: str, choice: Installation
    ) -> dict[str, Any]:
        choice = Installation.model_validate_json(choice.model_dump_json())

        def access(c: Connection) -> None:
            Access(self.store).authorize(c, viewer, "economy")
            if actor.kind != "pilot" or actor.entity != str(viewer.user_id):
                raise WorkflowError("Purchase only for your actual owned Girl and Frame.")

        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            self._safe(c, state, viewer.user_id)
            current = self._actor(c, state, viewer)
            if current.ref != actor:
                raise WorkflowError("STALE_REQUISITION: recover the original character first.")
            identity, source = str(uuid4()), str(uuid4())
            state = rules.purchase(
                state,
                actor,
                profiles(c, self.store.campaign_id),
                expected,
                choice,
                identity,
                source,
            )
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.asset_installment_purchased",
                state,
                event_id=source,
                requisition_id=identity,
                cost=1,
            )
            return {
                "id": identity,
                "asset_id": state.requisitions[-1].asset_id,
                "permissions": state.sheets[actor.entity].permissions,
            }

        try:
            return self.store._write(
                viewer,
                key,
                "m3.asset_installment_purchased",
                dict(
                    actor=actor.model_dump(mode="json"),
                    expected=expected,
                    choice=choice.model_dump(mode="json"),
                ),
                operation,
                auto_audit=False,
                authorize=access,
            )
        except ValidationError:
            raise WorkflowError(
                "Invalid purchase data; review the current owned installation."
            ) from None
        except ValueError as error:
            raise WorkflowError(str(error)) from None
