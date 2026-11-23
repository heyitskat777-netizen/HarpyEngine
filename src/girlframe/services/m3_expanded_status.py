"""Review Expanded Status under the actual human rules-table appointment."""

from typing import Any
from uuid import uuid4

from sqlalchemy import Connection

from girlframe.engine import m3_expanded_status as rules
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef, ActorView
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_handler_consequences import active_handler
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access, digest
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_handler_advancements import _history
from girlframe.services.m3_medical import MedicalService
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer

EVENT = "m3.expanded_status_designated"


class ExpandedStatusService:
    def __init__(self, game: GameService):
        self.game, self.store = game, game.store

    def enabled(self) -> bool:
        approval = self.store.policy.m3_approval
        if approval is None or not {"world", "plays"} <= approval.subsystems:
            return False
        try:
            registry = Access(self.store).registry
        except WorkflowError:
            return False
        return bool(
            registry
            and approval.registry_sha256 == digest(registry)
            and self.store.policy.owner_m3_rulings is not None
            and registry.entry(rules.RULE).verified
        )

    def _authority(self, c: Connection, viewer: GuildViewer) -> str:
        access = Access(self.store)
        access.authorize(c, viewer, "world", director_response=True)
        access.authorize(c, viewer, "plays", director_response=True)
        assert access.registry is not None
        try:
            access.registry.require_available(rules.RULE)
        except ValueError as error:
            raise WorkflowError(str(error)) from None
        human, appointment = MedicalService(self.store)._handler(c)
        if human != viewer.user_id:
            raise WorkflowError("This designation belongs to the actual human GM")
        return appointment

    def view(self, c: Connection, state: GameState, actor: ActorView) -> dict[str, Any]:
        level = rules.default(state, actor)
        if level is None:
            return dict(level=None, label="Outside Foundation Status", designated=False)
        assigned = rules.designation(state, actor.ref)
        if assigned is not None:
            original = _history(c, self.game, assigned.event)
            if rules.designation(original, actor.ref) != assigned:
                raise WorkflowError("Recover the actual recorded status designation")
            level = assigned.level
        return dict(level=level, label=rules.LEVELS[level], designated=assigned is not None)

    def options(self, viewer: GuildViewer) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self._authority(c, viewer)
            state = load_state(c, self.store.campaign_id)
            bindings = profiles(c, self.store.campaign_id)
            refs = [
                current_ref(state, uid)
                for uid in state.order
                if state.sheets[str(uid)].character_id is not None
            ]
            if original := active_handler(state):
                refs.append(original)
            if state.world:
                refs.extend(ActorRef(kind="npc", entity=x.id) for x in state.world.npcs if x.alive)
                refs.extend(
                    ActorRef(kind="external_pilot", entity=x.id)
                    for x in state.world.pilots
                    if x.alive
                )
            targets = []
            for ref in refs:
                try:
                    actor = resolve(state, ref, bindings, require_current_profile=False)
                except ValueError:
                    continue
                status = self.view(c, state, actor)
                if status["level"] is not None:
                    targets.append((ref, actor.label, status["level"]))
            return dict(revision=state.revision, actors=tuple(targets))

    def designate(
        self,
        viewer: GuildViewer,
        key: str,
        expected: int,
        ref: ActorRef,
        level: rules.Level,
        account: str,
    ) -> dict[str, Any]:
        def authorize(c: Connection) -> None:
            self._authority(c, viewer)
            self.game.unpaused(c)

        def operation(c: Connection) -> dict[str, Any]:
            state = load_state(c, self.store.campaign_id)
            if state.revision != expected or self.game.pending_actions(c):
                raise WorkflowError("STALE_EXPANDED_STATUS: finish any held Play and refresh")
            actor = resolve(
                state, ref, profiles(c, self.store.campaign_id), require_current_profile=False
            )
            if rules.default(state, actor) is None:
                raise WorkflowError("This actual actor is outside Foundation Status")
            value = rules.Designation(
                actor=ref,
                level=level,
                event=str(uuid4()),
                appointment=self._authority(c, viewer),
                account=account.strip(),
            )
            state.facts.append(
                dict(
                    kind="expanded_status_designation",
                    actor=ref.token,
                    body=value.model_dump_json(),
                )
            )
            self.game.event(
                c,
                viewer.user_id,
                key,
                EVENT,
                state,
                event_id=value.event,
                subject=ref.token,
                level=level,
            )
            return dict(level=level, event=value.event, revision=state.revision)

        try:
            return self.store._write(
                viewer,
                key,
                EVENT,
                dict(
                    expected=expected, ref=ref.model_dump(mode="json"), level=level, account=account
                ),
                operation,
                auto_audit=False,
                authorize=authorize,
            )
        except ValueError as error:
            raise WorkflowError(str(error)) from None
