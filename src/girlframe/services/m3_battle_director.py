"""Director NPC replacement effects and real, separately accepted new Director roles."""

import json
from typing import TYPE_CHECKING, Any
from uuid import NAMESPACE_URL, uuid4, uuid5

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_battle_director as rules
from girlframe.engine import m3_npc_roles
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_battle_state import Required
from girlframe.engine.m3_world_state import Npc
from girlframe.services.handler_setup import HandlerService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_medical import MedicalService
from girlframe.services.m3_work import related
from girlframe.services.onboarding import OnboardingStore, WorkflowError
from girlframe.services.read_only_bot import GuildViewer

if TYPE_CHECKING:
    from girlframe.services.m2_game import GameService


def bind_legacy_context_bodies(
    game: "GameService", c: Connection, original: GameState
) -> GameState:
    """Bind a legacy rules context from its actual first-body history, never a successor UID."""
    from girlframe.engine.m3_handler_consequences import active_handler, same_handler_body

    state = GameState.model_validate_json(original.model_dump_json())
    current = active_handler(state)
    for index, context in enumerate(state.director_contexts):
        legacy_actor = context.body_actor is not None and context.body_actor.incarnation is None
        if (context.body_actor is not None and not legacy_actor) or (
            not context.active and context.termination_reason != "director_death"
        ):
            continue
        raw = c.scalar(
            sa.select(t.m2["m2_state_history"].c.body_json).where(
                t.m2["m2_state_history"].c.campaign_id == game.store.campaign_id,
                t.m2["m2_state_history"].c.event_id == context.source_event,
            )
        )
        source = GameState.model_validate_json(raw) if raw else None
        original_body = active_handler(source) if source is not None else None
        if current is None or original_body is None or context.handler != int(current.entity):
            raise WorkflowError(
                "SOURCE_HANDLER_BODY_MISSING: recover this actual context's original body."
            )
        assert source is not None
        first_legacy = (
            original_body.incarnation is None
            and not source.handler_archives
            and not state.handler_archives
        )
        if not same_handler_body(state, original_body) or (
            original_body != current and not first_legacy
        ):
            raise WorkflowError(
                "A replacement Handler cannot inherit this original rules context's body."
            )
        state.director_contexts[index] = context.model_copy(update={"body_actor": current})
    return state


def create_replacements(game: "GameService", c: Connection, event: str) -> None:
    raw = c.scalar(
        sa.select(t.m2["m2_state_history"].c.body_json).where(
            t.m2["m2_state_history"].c.campaign_id == game.store.campaign_id,
            t.m2["m2_state_history"].c.event_id == event,
        )
    )
    state = GameState.model_validate_json(raw) if raw else None
    if state is None:
        raise WorkflowError("Commit the actual Director body ending before replacement work.")
    for fact in state.facts:
        if fact.get("kind") != "director_body_ended" or fact.get("event") != event:
            continue
        actor = ActorRef.model_validate_json(fact["actor"])
        identity = str(
            uuid5(
                NAMESPACE_URL, "girlframe:actual-director-replacement:" + actor.token + ":" + event
            )
        )
        work = t.m3["m3_required_work"]
        if c.scalar(
            sa.select(work.c.id).where(
                work.c.campaign_id == game.store.campaign_id, work.c.id == identity
            )
        ):
            continue
        human, appointment = MedicalService(game.store)._handler(c)
        related(
            c,
            game.store,
            dict(campaign_id=game.store.campaign_id, campaign_context=True),
            identity,
            human,
            human,
            "director_replacement",
            dict(
                dead_actor=actor.model_dump(mode="json"),
                death_event=event,
                body=fact["body"],
                handler=human,
                appointment=appointment,
                source_pdf=192,
                immediate=False,
            ),
            event,
        )


def synchronize_replacement(
    game: "GameService",
    c: Connection,
    offer_id: str,
    event: str,
    viewer: GuildViewer | None,
    key: str,
) -> None:
    state = load_state(c, game.store.campaign_id)
    offer = (
        next((x for x in state.world.npc_role_offers if x.id == offer_id), None)
        if state.world
        else None
    )
    if offer is None or offer.state != "accepted" or offer.response_event != event:
        return
    table = t.m3["m3_required_work"]
    latest = {
        row["id"]: dict(row)
        for row in c.execute(
            sa.select(table)
            .where(
                table.c.campaign_id == game.store.campaign_id,
                table.c.kind == "director_replacement",
            )
            .order_by(table.c.revision)
        ).mappings()
    }
    for row in latest.values():
        body = json.loads(row["body_json"])
        if row["state"] == "resolved" or body.get("role_offer") != offer_id:
            continue
        actual = c.execute(
            sa.select(t.events.c.actor_id, t.events.c.kind, t.events.c.payload_json).where(
                t.events.c.campaign_id == game.store.campaign_id, t.events.c.id == event
            )
        ).first()
        if (
            actual is None
            or actual.actor_id != str(offer.npc.controller)
            or actual.kind != "m3.npc_role_answered"
            or json.loads(actual.payload_json).get("decision") != "accept"
        ):
            raise WorkflowError("Prove the actual new Director human's real role acceptance.")
        dead = ActorRef.model_validate_json(json.dumps(body["dead_actor"]))
        npc = (
            next((x for x in state.world.npcs if x.id == offer.npc.id and x.alive), None)
            if state.world
            else None
        )
        if (
            npc is None
            or npc.id == dead.entity
            or "director" not in npc.jobs
            or npc.controller == state.handler
        ):
            raise WorkflowError(
                "The actual accepted replacement needs a new separately played Director body."
            )
        c.execute(
            table.insert().values(
                **{
                    k: v
                    for k, v in row.items()
                    if k not in ("revision", "state", "body_json", "event_id")
                },
                revision=row["revision"] + 1,
                state="resolved",
                event_id=event,
                body_json=json.dumps(
                    body | dict(replacement=npc.id, acceptance_event=event), sort_keys=True
                ),
            )
        )


class DirectorService:
    def __init__(self, store: OnboardingStore):
        from girlframe.services.m2_game import GameService

        self.store, self.game = store, GameService(store)

    def _access(self, c: Connection, viewer: GuildViewer) -> None:
        Access(self.store).authorize(c, viewer, "plays")
        self.game.unpaused(c)

    def _row(self, c: Connection, identity: str) -> dict[str, Any]:
        table = t.m3["m3_required_work"]
        row = (
            c.execute(
                sa.select(table)
                .where(table.c.campaign_id == self.store.campaign_id, table.c.id == identity)
                .order_by(table.c.revision.desc())
                .limit(1)
            )
            .mappings()
            .first()
        )
        if row is None or row["kind"] not in (
            "director_damage",
            "director_helpless",
            "director_replacement",
        ):
            raise WorkflowError("Open the original actual Director source consequence.")
        return dict(row)

    def _source(self, c: Connection, row: dict[str, Any]) -> tuple[ActorRef, Required]:
        body = json.loads(row["body_json"])
        source = body.get("damage_source_event", row["event_id"])
        raw = c.scalar(
            sa.select(t.m2["m2_state_history"].c.body_json).where(
                t.m2["m2_state_history"].c.campaign_id == self.store.campaign_id,
                t.m2["m2_state_history"].c.event_id == source,
            )
        )
        canon = GameState.model_validate_json(raw) if raw else None
        fact = (
            next(
                (
                    x
                    for x in canon.facts
                    if x.get("kind") == "battle_damage_stage"
                    and x.get("id") == row["id"]
                    and "requirement" in x
                ),
                None,
            )
            if canon
            else None
        )
        required = Required.model_validate_json(fact["requirement"]) if fact else None
        if required is None or required.kind != row["kind"]:
            raise WorkflowError(
                "Recover this actual Director's immutable source damage/Helpless effect."
            )
        assert canon is not None
        original = rules.body(canon, required.target)
        if str(original.controller) != row["owner_id"]:
            raise WorkflowError("Recover the actual source Director's original human controller.")
        return required.target, required

    def get(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            row = self._row(c, identity)
            if row["owner_id"] != str(viewer.user_id):
                raise WorkflowError("This actual Director source belongs to another human.")
            body = json.loads(row["body_json"])
            if row["kind"] == "director_replacement":
                state = load_state(c, self.store.campaign_id)
                members = [
                    dict(id=int(uid), label="Member " + uid)
                    for uid in c.scalars(
                        sa.select(t.members.c.user_id).where(
                            t.members.c.campaign_id == self.store.campaign_id,
                            t.members.c.active.is_(True),
                            t.members.c.user_id != str(viewer.user_id),
                        )
                    )
                ]
                locations = (
                    [dict(id=x.id, name=x.name, cell=x.cell) for x in state.world.locations]
                    if state.world
                    else []
                )
                return dict(
                    id=identity,
                    kind=row["kind"],
                    revision=row["revision"],
                    game_revision=state.revision,
                    state=row["state"],
                    members=members,
                    locations=locations,
                    role_offer=body.get("role_offer"),
                )
            actor, _ = self._source(c, row)
            state = load_state(c, self.store.campaign_id)
            original = rules.body(state, actor, alive=False)
            return dict(
                id=identity,
                kind=row["kind"],
                revision=row["revision"],
                state=row["state"],
                actor=actor.model_dump(mode="json"),
                label=original.name,
                injuries=[
                    x["account"]
                    for x in state.facts
                    if x.get("kind") == "director_injury"
                    and x.get("actor") == actor.model_dump_json()
                ],
            )

    def respond(
        self, viewer: GuildViewer, key: str, identity: str, revision: int, choice: str, account: str
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            row = self._row(c, identity)
            if (
                row["owner_id"] != str(viewer.user_id)
                or row["revision"] != revision
                or row["state"] == "resolved"
            ):
                raise WorkflowError("STALE_DIRECTOR: reopen your actual owned consequence.")
            actor, required = self._source(c, row)
            state = load_state(c, self.store.campaign_id)
            state = bind_legacy_context_bodies(self.game, c, state)
            if rules.body(state, actor).controller != viewer.user_id:
                raise WorkflowError("Recover this original body's actual source controller.")
            event = str(uuid4())
            state = rules.consequence(
                state,
                actor,
                choice,
                event,
                account,
                source_work=identity,
                opponent=required.opponent,
            )
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.director_consequence",
                state,
                event_id=event,
                work_id=identity,
                choice=choice,
            )
            body = json.loads(row["body_json"])
            table = t.m3["m3_required_work"]
            c.execute(
                table.insert().values(
                    **{
                        k: v
                        for k, v in row.items()
                        if k not in ("revision", "state", "body_json", "event_id")
                    },
                    revision=revision + 1,
                    state="resolved",
                    event_id=event,
                    body_json=json.dumps(
                        body
                        | dict(
                            choice=choice, effect_event=event, damage_source_event=row["event_id"]
                        ),
                        sort_keys=True,
                    ),
                )
            )
            from girlframe.services.m3_battle import complete_damage_work, synchronize_casts
            from girlframe.services.m3_handler_void import synchronize_endings

            synchronize_endings(self.game, c, event, viewer, key)
            synchronize_casts(self.game, c, event)
            create_replacements(self.game, c, event)
            complete_damage_work(self.game, c, row, event, viewer, key)
            return dict(id=identity, state="resolved", revision=revision + 1)

        return self.store._write(
            viewer,
            key,
            "m3.director_consequence",
            dict(id=identity, revision=revision, choice=choice, account=account),
            operation,
            auto_audit=False,
            authorize=lambda c: self._access(c, viewer),
        )

    def offer(
        self, viewer: GuildViewer, key: str, identity: str, revision: int, npc: Npc
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            row = self._row(c, identity)
            body = json.loads(row["body_json"])
            human, appointment = MedicalService(self.store)._handler(c)
            if (
                row["kind"] != "director_replacement"
                or row["state"] == "resolved"
                or row["revision"] != revision
                or viewer.user_id != human
                or row["owner_id"] != str(human)
            ):
                raise WorkflowError("The actual source GM sets up this required new Director.")
            if (
                "director" not in npc.jobs
                or npc.controller == human
                or not HandlerService(self.store)._member(c, npc.controller)
            ):
                raise WorkflowError("Invite an actual different human to play the new Director.")
            state = load_state(c, self.store.campaign_id)
            assert state.world is not None
            old = ActorRef.model_validate_json(json.dumps(body["dead_actor"]))
            if npc.id == old.entity:
                raise WorkflowError("The new Director cannot inherit the dead original's identity.")
            if body.get("role_offer"):
                previous = next(
                    x for x in state.world.npc_role_offers if x.id == body["role_offer"]
                )
                if previous.state in ("pending", "accepted"):
                    raise WorkflowError("Resume the actual outstanding role invitation.")
            offer, event = str(uuid4()), str(uuid4())
            state.world = m3_npc_roles.offer(state.world, human, npc, offer, event)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.director_replacement_offered",
                state,
                event_id=event,
                work_id=identity,
                invitation_id=offer,
            )
            table = t.m3["m3_required_work"]
            c.execute(
                table.insert().values(
                    **{
                        k: v
                        for k, v in row.items()
                        if k not in ("revision", "state", "body_json", "event_id")
                    },
                    revision=revision + 1,
                    state="pending",
                    event_id=event,
                    body_json=json.dumps(
                        body | dict(role_offer=offer, appointment=appointment), sort_keys=True
                    ),
                )
            )
            return dict(id=identity, role_offer=offer, state="pending", revision=revision + 1)

        return self.store._write(
            viewer,
            key,
            "m3.director_replacement_offered",
            dict(id=identity, revision=revision, npc=npc.model_dump(mode="json")),
            operation,
            auto_audit=False,
            authorize=lambda c: self._access(c, viewer),
        )
