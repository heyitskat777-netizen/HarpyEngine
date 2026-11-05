"""An actual Aggressive Gorgon chooses its immediate Girl hit before the Defeat die."""

import json
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_battle_state import Required
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_collateral import append, latest
from girlframe.services.onboarding import OnboardingStore, WorkflowError
from girlframe.services.read_only_bot import GuildViewer


class AggressiveService:
    def __init__(self, store: OnboardingStore):
        self.store, self.game = store, GameService(store)

    def _proof(self, c: Connection, identity: str) -> tuple[dict[str, Any], Required, int]:
        row = latest(self.game, c, identity)
        body = json.loads(row["body_json"])
        if row["kind"] != "aggressive_damage":
            raise WorkflowError("Open this actual Aggressive immediate-hit source.")
        source = body.get("damage_source_event", row["event_id"])
        raw = c.scalar(
            sa.select(t.m2["m2_state_history"].c.body_json).where(
                t.m2["m2_state_history"].c.campaign_id == self.store.campaign_id,
                t.m2["m2_state_history"].c.event_id == source,
            )
        )
        state = GameState.model_validate_json(raw) if raw else None
        fact = (
            next(
                (
                    x
                    for x in state.facts
                    if x.get("kind") == "battle_damage_stage" and x.get("id") == identity
                ),
                None,
            )
            if state
            else None
        )
        required = Required.model_validate_json(fact["requirement"]) if fact else None
        attacker = (
            next(
                (
                    x
                    for x in state.world.gorgons
                    if required and required.opponent and x.id == required.opponent.entity
                ),
                None,
            )
            if state and state.world
            else None
        )
        if (
            required is None
            or required.kind != "aggressive_damage"
            or attacker is None
            or attacker.gorgon_class != "aggressive"
            or state is None
        ):
            raise WorkflowError("Prove the exact real Aggressive last-Frame hit.")
        owner = resolve(state, ActorRef(kind="gorgon", entity=attacker.id), ()).controller
        if str(owner) != row["owner_id"] or required.target.model_dump(mode="json") != body.get(
            "owner"
        ):
            raise WorkflowError("Recover the original actual attacker/target ownership.")
        return row, required, owner

    def get(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            row, required, owner = self._proof(c, identity)
            if viewer.user_id != owner:
                raise WorkflowError(
                    "Only this actual Aggressive Gorgon's controller chooses the extra hit."
                )
            state = load_state(c, self.store.campaign_id)
            from girlframe.engine.m3_battle import intact_assets, original_ended

            ended = original_ended(state, required.target)
            return dict(
                id=identity,
                revision=row["revision"],
                game_revision=state.revision,
                state=row["state"],
                ended=ended,
                assets=[]
                if ended
                else [
                    dict(id=x.id, name=x.name)
                    for x in intact_assets(
                        state, required.target, profiles(c, self.store.campaign_id)
                    )
                    if x.family == "girl"
                ],
            )

    def respond(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        game_revision: int,
        asset: str | None,
        account: str,
    ) -> dict[str, Any]:
        def access(c: Connection) -> None:
            Access(self.store).authorize(c, viewer, "plays", director_response=True)
            self.game.unpaused(c)

        def operation(c: Connection) -> dict[str, Any]:
            row, required, owner = self._proof(c, identity)
            state = load_state(c, self.store.campaign_id)
            if (
                row["state"] != "pending"
                or revision != row["revision"]
                or state.revision != game_revision
                or viewer.user_id != owner
                or not account.strip()
            ):
                raise WorkflowError(
                    "STALE_AGGRESSIVE: the actual owner chooses this optional immediate hit."
                )
            body = json.loads(row["body_json"])
            event = str(uuid4())
            from girlframe.engine.m3_battle import intact_assets, original_ended
            from girlframe.services.m3_battle import (
                complete_damage_work,
                damage_actor,
                synchronize_damage,
            )

            followups: tuple[str, ...] = ()
            if asset is not None:
                if original_ended(state, required.target) or not any(
                    x.id == asset and x.family == "girl"
                    for x in intact_assets(
                        state, required.target, profiles(c, self.store.campaign_id)
                    )
                ):
                    raise WorkflowError(
                        "Damage an actual remaining original Girl Asset; never a successor body."
                    )
                state, followups = damage_actor(
                    self.game,
                    c,
                    state,
                    target=required.target,
                    asset_id=asset,
                    source_action=body.get("source_action"),
                    source_work=identity,
                    event=event,
                    actor=None,
                    opponent=required.opponent,
                    chooser_controller=owner,
                    occurrence="aggressive_extra",
                )
            state.facts.append(
                dict(
                    kind="aggressive_immediate_choice",
                    id=identity,
                    event=event,
                    asset=asset or "",
                    account=account,
                    owner=str(owner),
                )
            )
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.aggressive_immediate_choice",
                state,
                event_id=event,
                source_work=identity,
                damaged=asset is not None,
            )
            append(
                c,
                row,
                event,
                body
                | dict(
                    damage_source_event=body.get("damage_source_event", row["event_id"]),
                    choice="damage" if asset else "pass",
                    followups=followups,
                ),
                "resolved",
            )
            synchronize_damage(self.game, c, event)
            complete_damage_work(self.game, c, row, event, viewer, key)
            return dict(id=identity, game_revision=state.revision)

        try:
            return self.store._write(
                viewer,
                key,
                "m3.aggressive_immediate_choice",
                dict(
                    id=identity,
                    revision=revision,
                    game_revision=game_revision,
                    asset=asset,
                    account=account,
                ),
                operation,
                authorize=access,
                auto_audit=False,
            )
        except ValueError as error:
            raise WorkflowError(str(error)) from None
