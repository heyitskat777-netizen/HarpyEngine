"""Actual actor/profile bindings and scoped private projections, not actor impersonation."""

from typing import Any

import sqlalchemy as sa
from pydantic import ValidationError
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_actors as rules
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef, ActorView, ProfileBinding
from girlframe.engine.m3_careers import profile_character
from girlframe.services.m2_state import load_state
from girlframe.services.m3_incarnations import proof
from girlframe.services.m3_missions import MissionService
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer


def _raw_state(c: Connection, campaign: str) -> GameState:
    table = t.m2["m2_state"]
    body = c.scalar(sa.select(table.c.body_json).where(table.c.campaign_id == campaign))
    return GameState.model_validate_json(body) if body is not None else GameState()


def profiles(c: Connection, campaign: str) -> tuple[ProfileBinding, ...]:
    canon = load_state(c, campaign)
    originals = {
        (uid, revision): identity
        for uid, revision, identity in c.execute(
            sa.select(
                t.snapshots.c.user_id, t.snapshots.c.revision, t.snapshots.c.character_id
            ).where(t.snapshots.c.campaign_id == campaign)
        )
    }
    return tuple(
        ProfileBinding(
            owner=int(uid),
            character_id=profile_character(canon, int(uid), identity, revision),
            profile_revision=revision,
            source_character_id=originals.get(
                (str(uid), canon.sheets[str(uid)].source_profile_revision)
            )
            if str(uid) in canon.sheets
            else None,
            source_profile_revision=canon.sheets[str(uid)].source_profile_revision
            if str(uid) in canon.sheets
            else None,
        )
        for uid, identity, revision in c.execute(
            sa.select(
                t.characters.c.user_id,
                t.characters.c.id,
                t.characters.c.revision,
            ).where(t.characters.c.campaign_id == campaign)
        )
        if str(uid) in canon.sheets
        or not any(int(x.actor.entity) == int(uid) for x in canon.career_archives)
    )


class ActorService:
    def __init__(self, missions: MissionService):
        self.missions, self.store, self.game = missions, missions.store, missions.game

    def _actor(
        self,
        c: Connection,
        viewer: GuildViewer,
        state: GameState,
        ref: ActorRef,
        *,
        require_current_profile: bool = True,
    ) -> ActorView:
        self.game.authorize(c, viewer, game=False)
        try:
            actor = rules.resolve(
                state,
                ref,
                profiles(c, self.store.campaign_id),
                require_current_profile=require_current_profile,
            )
        except ValueError:
            raise WorkflowError(
                "This actual actor is unavailable or needs source/profile recovery."
            ) from None
        if actor.controller != viewer.user_id:
            raise WorkflowError("This actor is controlled by another human.")
        return actor

    def choices(self, viewer: GuildViewer) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            state = load_state(c, self.store.campaign_id)
            bindings = profiles(c, self.store.campaign_id)
            available, stale = [], []
            for ref in rules.owned_refs(state, viewer.user_id, bindings):
                try:
                    actor = rules.resolve(state, ref, bindings)
                except ValueError:
                    stale.append(
                        {
                            "ref": ref.model_dump(mode="json"),
                            "reason": "source/profile recovery required",
                        }
                    )
                    continue
                available.append(
                    {
                        "ref": ref.model_dump(mode="json"),
                        "token": ref.token,
                        "label": actor.label,
                        "kind": ref.kind,
                        "rules": actor.rules,
                        "girl": actor.girl,
                        "heat": actor.heat,
                    }
                )
            raw = _raw_state(c, self.store.campaign_id)
            sheet = raw.sheets.get(str(viewer.user_id))
            legacy_available = False
            if sheet is not None and sheet.character_id is None:
                try:
                    proof(
                        c, self.store.campaign_id, raw, viewer.user_id, require_current_profile=True
                    )
                except WorkflowError:
                    pass
                else:
                    legacy_available = True
            return {
                "game_revision": state.revision,
                "actors": available,
                "stale": stale,
                "legacy_binding_available": legacy_available,
            }

    def inspect(self, viewer: GuildViewer, ref: ActorRef) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            state = load_state(c, self.store.campaign_id)
            return {
                "game_revision": state.revision,
                "actor": self._actor(c, viewer, state, ref).model_dump(mode="json"),
            }

    def known(
        self,
        viewer: GuildViewer,
        perspective: ActorRef,
        *,
        require_current_profile: bool = True,
    ) -> dict[str, Any]:
        """Known references only; the particular Play must still validate legal targets."""
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            state = load_state(c, self.store.campaign_id)
            actor = self._actor(
                c, viewer, state, perspective, require_current_profile=require_current_profile
            )
            bindings = profiles(c, self.store.campaign_id)
            refs = [perspective]
            refs.extend(
                ActorRef(kind="pilot", entity=str(x.owner), incarnation=x.character_id)
                for x in bindings
                if str(x.owner) in state.sheets and x.owner in state.order
            )
            if state.handler is not None and not any(x.active for x in state.director_contexts):
                refs.append(ActorRef(kind="handler", entity=str(state.handler)))
            if state.world:
                linked = {
                    x.npc
                    for x in state.world.starting_npc_links
                    if perspective.kind == "pilot"
                    and x.owner == int(perspective.entity)
                    and x.character_id == perspective.incarnation
                }
                if perspective.kind == "handler":
                    linked.update(
                        entity
                        for context in state.director_contexts
                        if context.active and context.id == perspective.incarnation
                        for entity in context.directors
                    )
                refs.extend(
                    ActorRef(kind="npc", entity=x.id)
                    for x in state.world.npcs
                    if x.alive and (x.revealed or x.id in linked)
                )
                refs.extend(
                    ActorRef(kind="external_pilot", entity=x.id)
                    for x in state.world.pilots
                    if x.alive and x.revealed
                )
                refs.extend(
                    ActorRef(kind="gorgon", entity=x.id)
                    for x in state.world.gorgons
                    if x.alive and x.revealed
                )
            known = []
            for ref in dict.fromkeys(refs):
                try:
                    target = rules.resolve(
                        state, ref, bindings, require_current_profile=require_current_profile
                    )
                except ValueError:
                    continue
                known.append(
                    {
                        "ref": ref.model_dump(mode="json"),
                        "token": ref.token,
                        "label": target.label,
                        "kind": ref.kind,
                    }
                )
            return {
                "game_revision": state.revision,
                "perspective": actor.ref.model_dump(mode="json"),
                "actors": known,
            }

    def bind_legacy(self, viewer: GuildViewer, key: str, expected: int) -> dict[str, Any]:
        def authorize(c: Connection) -> None:
            self.missions.access.authorize(c, viewer, "world", director_response=True)
            self.game.unpaused(c)

        def operation(c: Connection) -> dict[str, Any]:
            state = _raw_state(c, self.store.campaign_id)
            sheet = state.sheets.get(str(viewer.user_id))
            locks = t.m2["m2_locks"]
            actions = t.m2["m2_actions"]
            if (
                state.revision != expected
                or sheet is None
                or sheet.owner != viewer.user_id
                # This proves an existing character identity without changing
                # resources. It may be required to resume a known aborted roll.
                or c.scalar(
                    sa.select(actions.c.id)
                    .where(
                        actions.c.campaign_id == self.store.campaign_id,
                        actions.c.state.not_in(("complete", "aborted")),
                    )
                    .limit(1)
                )
                or c.scalar(
                    sa.select(locks.c.channel_id)
                    .where(
                        locks.c.campaign_id == self.store.campaign_id, locks.c.state != "released"
                    )
                    .limit(1)
                )
            ):
                raise WorkflowError(
                    "Recover only your actual unbound legacy sheet after restoring chat."
                )
            try:
                source = proof(
                    c, self.store.campaign_id, state, viewer.user_id, require_current_profile=True
                )
            except WorkflowError:
                raise WorkflowError(
                    "SOURCE_BINDING_MISSING: recover the immutable original character snapshot."
                ) from None
            if sheet.character_id is not None:
                # A genuine canonical write may already have persisted this proof
                # while the explicit recovery form was open. Preserve its receipt.
                return {
                    "ref": ActorRef(
                        kind="pilot", entity=str(viewer.user_id), incarnation=source.character
                    ).model_dump(mode="json"),
                    "sheet_revision": sheet.revision,
                    "already_bound": True,
                }
            sheet.character_id = source.character
            sheet.revision += 1
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.actor_character_bound",
                state,
                owner=viewer.user_id,
                source_profile_revision=sheet.source_profile_revision,
                snapshot_event=source.snapshot_event,
            )
            return {
                "ref": ActorRef(
                    kind="pilot", entity=str(viewer.user_id), incarnation=sheet.character_id
                ).model_dump(mode="json"),
                "sheet_revision": sheet.revision,
            }

        try:
            return self.store._write(
                viewer,
                key,
                "m3.actor_character_bound",
                {"expected": expected},
                operation,
                auto_audit=False,
                authorize=authorize,
            )
        except ValidationError:
            raise WorkflowError(
                "Invalid actor binding; recover the actual source snapshot."
            ) from None
