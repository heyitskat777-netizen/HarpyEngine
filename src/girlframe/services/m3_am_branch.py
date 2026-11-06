"""Source-proved actual branch NPC and original-player-owned irreversible takeover."""

import json
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_am_branch as rules
from girlframe.engine import m3_am_code as code
from girlframe.engine.m2 import ChoiceAnswer, GameState
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_am_body import prove_preparation
from girlframe.services.m3_am_code import access
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer


def _history(game: GameService, c: Connection, event: str) -> GameState:
    from girlframe.services.m3_am_scrutinized import _history as history

    return history(game, c, event)


def prove(
    game: GameService, c: Connection, state: GameState, identity: str, *, ready: bool = False
) -> rules.Branch:
    value = rules.get(state, identity)
    original = _history(game, c, value.event)
    born = rules.get(original, identity)
    mutable = {
        "assignment",
        "resulting_actor",
        "ready_event",
        "takeover_event",
        "archive",
        "npc_history",
    }
    if value.model_dump(exclude=mutable) != born.model_dump(exclude=mutable):
        raise WorkflowError("Recover the actual independent branch birth snapshot")
    from girlframe.engine.m3_am import Limiter

    expected_actor = value.resulting_actor if value.takeover_event else value.npc
    for limiter_id in value.limiter_ids:
        inherited = next(
            (
                Limiter.model_validate_json(x["body"])
                for x in original.facts
                if x.get("kind") == "am_limiter" and x.get("id") == limiter_id
            ),
            None,
        )
        current = [
            Limiter.model_validate_json(x["body"])
            for x in state.facts
            if x.get("kind") == "am_limiter" and x.get("id") == limiter_id
        ]
        if inherited is None or current != [
            inherited.model_copy(update=dict(actor=expected_actor))
        ]:
            raise WorkflowError("Recover the actual branch's inherited original Limiter source")
    preparation = prove_preparation(game, c, state, value.preparation)
    maintenance = code.session(state, value.maintenance)
    created = code.session(original, value.maintenance)
    choices, responses = t.m2["m2_choices"], t.m2["m2_responses"]
    answer = c.scalar(
        sa.select(responses.c.answer_json)
        .join(
            choices,
            sa.and_(
                choices.c.campaign_id == responses.c.campaign_id,
                choices.c.id == responses.c.choice_id,
            ),
        )
        .where(
            responses.c.campaign_id == game.store.campaign_id,
            responses.c.event_id == value.event,
            responses.c.actor_id == str(value.controller),
            choices.c.kind == "am_code_branch",
            choices.c.action_id == value.action,
        )
    )
    if (
        maintenance.branch != value.id
        or created.branch != value.id
        or "branch" not in created.selected_options
        or maintenance.actor != value.original
        or maintenance.operator != value.operator
        or preparation.maintenance != value.maintenance
        or preparation.spec.vessel != value.vessel
        or answer is None
        or json.loads(answer).get("options") != [preparation.id]
        or game.action(c, value.action)["data"]["result"]["tier"] not in ("mid", "high")
    ):
        raise WorkflowError("Recover the actual performed circuits/branch selection and vessel")
    if value.ready_event:
        reviewed = rules.get(_history(game, c, value.ready_event), identity)
        audit = c.execute(
            sa.select(t.events.c.kind, t.events.c.actor_id).where(
                t.events.c.campaign_id == game.store.campaign_id, t.events.c.id == value.ready_event
            )
        ).first()
        if (
            reviewed.assignment != value.assignment
            or reviewed.resulting_actor != value.resulting_actor
            or audit is None
            or (audit.kind, audit.actor_id) != ("m3.am_branch_assignment", str(value.controller))
        ):
            raise WorkflowError("Recover the actual Handler's existing Frame/Status source")
    if ready:
        if (
            value.assignment is None
            or value.resulting_actor is None
            or not value.ready_event
            or value.takeover_event
        ):
            raise WorkflowError(
                "Review the actual available Frame and current branch before takeover"
            )
        clone = state.model_copy(deep=True)
        actual = rules.assign(
            clone, identity, value.assignment.position, value.ready_event, value.assignment.account
        )
        if actual.assignment != value.assignment:
            raise WorkflowError(
                "The actual existing Frame/condition or Status changed; refresh its source"
            )
    if value.takeover_event:
        completed = rules.get(_history(game, c, value.takeover_event), identity)
        audit = c.execute(
            sa.select(t.events.c.kind, t.events.c.actor_id).where(
                t.events.c.campaign_id == game.store.campaign_id,
                t.events.c.id == value.takeover_event,
            )
        ).first()
        if (
            completed != value
            or audit is None
            or (audit.kind, audit.actor_id) != ("m3.am_branch_taken_over", str(value.owner))
        ):
            raise WorkflowError("Only the original owner actually takes over this branch")
        archive = next((x for x in state.career_archives if x.id == value.archive), None)
        if (
            archive is None
            or archive.actor != value.original
            or archive.ending != "am_branch_terminated"
        ):
            raise WorkflowError("Keep the actual original mind irreversibly terminated")
    return value


def projection(
    game: GameService, c: Connection, state: GameState, value: code.Maintenance
) -> dict[str, Any]:
    from girlframe.engine.m3_am_body import bodies, preparations

    return dict(
        bodies=[
            dict(id=x.id, label=x.spec.label)
            for x in preparations(state)
            if x.maintenance == value.id
            and not any(b.vessel == x.spec.vessel for b in bodies(state))
            and not x.spec.mind_assets
        ]
    )


def apply(
    game: GameService, c: Connection, state: GameState, action: dict[str, Any], answer: ChoiceAnswer
) -> None:
    value = code.session(state, action["data"]["am_code"]["maintenance"])
    if (
        len(answer.options) != 1
        or answer.denied
        or answer.fields
        or answer.flag is not None
        or answer.number is not None
        or answer.member is not None
        or not answer.text.strip()
        or len(answer.text) > 1200
        or game.immediate_work(c, value.owner)
    ):
        raise WorkflowError(
            "The real operator chooses and creates the actual appropriate-vessel branch"
        )
    prep = prove_preparation(game, c, state, answer.options[0])
    if prep.operator != value.operator or prep.controller != value.controller:
        raise WorkflowError("Use this actual original operator's prepared vessel")
    born = rules.create(state, value, prep.id, action["data"]["response_event"])
    code.put(state, value.model_copy(update=dict(branch=born.id)))


class BranchService:
    def __init__(self, game: GameService):
        self.game, self.store = game, game.store

    def _source(
        self, c: Connection, viewer: GuildViewer, identity: str
    ) -> tuple[GameState, rules.Branch]:
        access(self.game, c, viewer)
        state = load_state(c, self.store.campaign_id)
        value = prove(self.game, c, state, identity)
        if viewer.user_id not in (value.owner, value.controller):
            raise WorkflowError("This branch belongs to its original actual humans")
        return state, value

    def view(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            state, value = self._source(c, viewer, identity)
            ref = value.resulting_actor if value.takeover_event else value.npc
            assert ref is not None
            npc = (
                next((x for x in state.world.npcs if x.id == value.npc.entity), None)
                if state.world
                else None
            )
            return dict(
                revision=state.revision,
                id=value.id,
                owner=viewer.user_id == value.owner,
                controller=viewer.user_id == value.controller,
                active=bool(value.takeover_event),
                ready=bool(value.ready_event),
                branch=value.model_dump(mode="json"),
                body=rules.current_body(state, ref).model_dump(mode="json"),
                npc=npc.model_dump(mode="json")
                if npc is not None and viewer.user_id == value.controller
                else None,
                positions=tuple(range(len(state.order))) if not value.takeover_event else (),
            )

    def menu(self, viewer: GuildViewer) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            access(self.game, c, viewer)
            state = load_state(c, self.store.campaign_id)
            return dict(
                branches=[
                    dict(id=x.id, label="Actual AM branch", active=bool(x.takeover_event))
                    for x in rules.branches(state)
                    if viewer.user_id in (x.owner, x.controller)
                ]
            )

    def assign(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        expected: int,
        position: int,
        account: str,
    ) -> dict[str, Any]:
        from girlframe.services.m3_requisitions import RequisitionService

        def change(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            state, value = self._source(c, viewer, identity)
            if (
                viewer.user_id != value.controller
                or state.handler != viewer.user_id
                or state.revision != expected
            ):
                raise WorkflowError(
                    "Only the actual Handler records the available Frame and resulting Status"
                )
            RequisitionService(self.game)._safe(c, state, value.owner)
            event = str(uuid4())
            selected = rules.assign(state, identity, position, event, account)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.am_branch_assignment",
                state,
                event_id=event,
                branch=identity,
            )
            return dict(
                id=identity,
                actor=selected.resulting_actor.model_dump(mode="json")
                if selected.resulting_actor
                else None,
            )

        return self.store._write(
            viewer,
            key,
            "m3.am_branch_assign",
            dict(id=identity, expected=expected, position=position, account=account),
            change,
            auto_audit=False,
        )

    def takeover(
        self, viewer: GuildViewer, key: str, identity: str, expected: int
    ) -> dict[str, Any]:
        from girlframe.services.m3_careers import activate_branch_in_transaction, synchronize_end
        from girlframe.services.m3_requisitions import RequisitionService

        def change(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            state, value = self._source(c, viewer, identity)
            if viewer.user_id != value.owner or state.revision != expected or value.takeover_event:
                raise WorkflowError(
                    "Only the original player chooses this irreversible branch takeover"
                )
            self.game.character_binding(c, state, viewer.user_id)
            RequisitionService(self.game)._safe(c, state, viewer.user_id)
            if code.session(state, value.maintenance).phase != "complete":
                raise WorkflowError("Complete the actual circuits effects and source work first")
            event = str(uuid4())
            try:
                changed, archive = activate_branch_in_transaction(
                    c, self.game, state, branch_id=identity, event=event
                )
            except ValueError as error:
                raise WorkflowError(str(error)) from None
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.am_branch_taken_over",
                changed,
                event_id=event,
                branch=identity,
            )
            synchronize_end(c, self.game, archive)
            profile = (
                c.execute(
                    sa.select(t.characters).where(
                        t.characters.c.campaign_id == self.store.campaign_id,
                        t.characters.c.user_id == str(viewer.user_id),
                    )
                )
                .mappings()
                .one()
            )
            c.execute(
                t.snapshots.insert().values(
                    campaign_id=self.store.campaign_id,
                    user_id=str(viewer.user_id),
                    revision=profile["revision"],
                    character_id=profile["id"],
                    event_id=event,
                    public_json=profile["public_json"],
                    private_json=profile["private_json"],
                )
            )
            from girlframe.engine.drafts import DraftInput

            draft = DraftInput.model_validate(
                dict(
                    json.loads(profile["public_json"]),
                    notes=json.loads(profile["private_json"]).get("notes", ""),
                )
            )
            self.store._enqueue_sync(c, viewer.user_id, profile["revision"], draft)
            result = rules.get(changed, identity).resulting_actor
            assert result is not None
            return dict(id=identity, actor=result.model_dump(mode="json"))

        return self.store._write(
            viewer,
            key,
            "m3.am_branch_takeover",
            dict(id=identity, expected=expected),
            change,
            auto_audit=False,
        )

    def _tasks(self, c: Connection, viewer: GuildViewer) -> list[dict[str, Any]]:
        state = load_state(c, self.store.campaign_id)
        return [
            dict(
                id=x.id,
                revision=state.revision,
                pending=False,
                label="Actual AM branch and optional takeover",
                phase="active" if x.takeover_event else "NPC",
            )
            for x in rules.branches(state)
            if viewer.user_id in (x.owner, x.controller)
        ]
