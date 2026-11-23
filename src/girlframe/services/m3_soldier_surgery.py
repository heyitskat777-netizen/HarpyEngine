"""The actual external Tag setter owns a Soldier's immediate embrace choice."""

from typing import Any
from uuid import uuid4

from sqlalchemy import Connection

from girlframe.engine import m3_actor_plays as plays
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_ancillary import SOLDIER_SIMPLIFICATION, Character, find
from girlframe.engine.m3_role_punishment_state import RolePunishment
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_ancillary_discipline import SCOPE
from girlframe.services.m3_role_punishments import case_proof, current, synchronize
from girlframe.services.onboarding import WorkflowError
from girlframe.services.p1_facilitator import require_scene_clear
from girlframe.services.p1_source_pause import require_clear
from girlframe.services.read_only_bot import GuildViewer

KIND = "soldier_external_tag"


def stage(game: GameService, state: GameState, case: RolePunishment, event: str, tag: str) -> None:
    role = find(state, case.subject)
    if (
        role is None
        or role.draft.book != "SOLDIER"
        or not any(x.id == tag and x.giver_actor == case.executor for x in role.tags)
    ):
        return
    try:
        Access(game.store).require_specialist_rule(SOLDIER_SIMPLIFICATION)
    except (ValueError, WorkflowError):
        return
    state.facts.append(
        dict(
            kind=KIND,
            id=case.id,
            source=event,
            tag=tag,
            owner=str(case.executor_controller),
        )
    )


def pending(state: GameState, case: str) -> bool:
    return any(
        x.get("kind") == KIND and x.get("id") == case and not x.get("decided") for x in state.facts
    )


class SoldierSurgeryService:
    def __init__(self, game: GameService):
        self.game, self.store = game, game.store

    def _gate(self, c: Connection, viewer: GuildViewer) -> None:
        gate = Access(self.store)
        gate.authorize(c, viewer, "discipline")
        gate.require_specialist_rule(SOLDIER_SIMPLIFICATION)

    def _source(
        self, c: Connection, state: GameState, viewer: GuildViewer, identity: str
    ) -> tuple[dict[str, str], RolePunishment, Character]:
        source = next(
            (
                x
                for x in state.facts
                if x.get("kind") == KIND
                and x.get("id") == identity
                and x.get("owner") == str(viewer.user_id)
                and not x.get("decided")
            ),
            None,
        )
        if source is None:
            raise WorkflowError("This original Tag setter choice is unavailable.")
        case = case_proof(c, self.game, identity)
        current(c, self.game, state, case)
        role = find(state, case.subject)
        if (
            viewer.user_id
            != (case.subject_controller if source.get("forced") else case.executor_controller)
            or case.effect_event != source["source"]
            or case.completion_event is not None
            or role is None
            or role.draft.book != "SOLDIER"
        ):
            raise WorkflowError("Recover the actual original Tag setter and Soldier.")
        return source, case, role

    def tasks(self, c: Connection, state: GameState, viewer: GuildViewer) -> tuple[str, ...]:
        result = []
        for fact in state.facts:
            if (
                fact.get("kind") != KIND
                or fact.get("owner") != str(viewer.user_id)
                or fact.get("decided")
            ):
                continue
            try:
                self._gate(c, viewer)
                self._source(c, state, viewer, fact["id"])
            except (ValueError, WorkflowError):
                continue
            result.append(fact["id"])
        return tuple(result)

    def get(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self._gate(c, viewer)
            state = load_state(c, self.store.campaign_id)
            fact, case, role = self._source(c, state, viewer, identity)
            exact = next(
                (x for x in role.tags if x.id == fact["tag"] and x.giver_actor == case.executor),
                None,
            )
            return dict(
                revision=state.revision,
                tag=exact.label if exact is not None else None,
                owner_replaces=bool(fact.get("forced")),
                open_slot=len(role.identities) < 2,
                replacements={
                    x.id: x.name for x in role.identities if not x.protected and not x.paired
                }
                if fact.get("forced")
                else {},
            )

    def decide(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        choice: str,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            fact, case, role = self._source(c, state, viewer, identity)
            if state.revision != revision:
                raise WorkflowError("Reopen the exact original Tag choice.")
            case_scope = next(
                (x for x in state.facts if x.get("id") == case.id and x.get("kind") == SCOPE), None
            )
            if case_scope is None:
                raise WorkflowError("Recover the original discipline scene.")
            channel = int(case_scope["channel"])
            require_scene_clear(self.game, c, channel)
            require_clear(self.game, c, channel)
            event = str(uuid4())
            if not fact.get("forced") and choice not in ("pass", "embrace"):
                raise WorkflowError("Choose whether to require embracing your actual Tag.")
            if fact.get("forced") and choice == "pass":
                raise WorkflowError("Choose an actual Identity to replace or pause the scene.")
            if choice == "pass":
                fact.update(decided=event, choice=choice)
            else:
                if choice == "embrace" and not fact.get("forced") and len(role.identities) >= 2:
                    if not any(
                        x.id == fact["tag"] and x.giver_actor == case.executor for x in role.tags
                    ):
                        raise WorkflowError("Recover the actual original Tag.")
                    fact.update(forced=event, owner=str(case.subject_controller))
                else:
                    replace = (choice,) if len(role.identities) >= 2 else ()
                    if not replace and choice != "embrace":
                        raise WorkflowError("Confirm the available original Identity slot.")
                    fact.update(decided=event, choice=choice)
                    plays.embrace(
                        state, case.subject, fact["tag"], replace, soldier_setter=case.executor
                    )
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.soldier_external_tag_answered",
                state,
                event_id=event,
                case_id=identity,
            )
            synchronize(self.game, c, None, event)
            return dict(id=identity, event=event)

        try:
            return self.store._write(
                viewer,
                key,
                KIND,
                dict(id=identity, revision=revision, choice=choice),
                operation,
                authorize=lambda c: self._gate(c, viewer),
                auto_audit=False,
            )
        except ValueError as error:
            raise WorkflowError(str(error)) from None
