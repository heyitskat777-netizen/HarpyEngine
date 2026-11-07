"""Owned NPC Bond weakening and actual addressed Conversation, never proxy PC Plays."""

import json
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_npc_bond_play as rules
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_bonds import change, current_ref, depth
from girlframe.engine.m3_actor_state import ActorRef, CastRole
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_battle_npc import NARRATIVE
from girlframe.engine.m3_world_state import Npc
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_battle import _cast
from girlframe.services.m3_handler_advancements import _history
from girlframe.services.m3_work import related
from girlframe.services.onboarding import OnboardingStore, WorkflowError
from girlframe.services.read_only_bot import GuildViewer


def _history_revision(game: GameService, c: Connection, revision: int) -> GameState:
    raw = c.scalar(
        sa.select(t.m2["m2_state_history"].c.body_json).where(
            t.m2["m2_state_history"].c.campaign_id == game.store.campaign_id,
            t.m2["m2_state_history"].c.revision == revision,
        )
    )
    if raw is None:
        raise WorkflowError("Recover the actual canonical NPC Bond source snapshot")
    return GameState.model_validate_json(raw)


def _npc(state: GameState, ref: ActorRef) -> Npc:
    value = (
        next((x for x in state.world.npcs if x.id == ref.entity), None)
        if state.world and ref.kind == "npc"
        else None
    )
    if value is None:
        raise WorkflowError("Choose the actual original NPC, not a PC or controller alias")
    return value


def _gate(game: GameService, job: str) -> None:
    gate = Access(game.store)
    assert gate.registry is not None
    gate.registry.require_available(rules.RULE)
    gate.registry.require_available("npc.npc." + job.replace("_", "-"))


def _work(game: GameService, c: Connection, request: rules.Request) -> dict[str, Any]:
    table = t.m3["m3_required_work"]
    rows = list(
        c.execute(
            sa.select(table)
            .where(table.c.campaign_id == game.store.campaign_id, table.c.id == request.id)
            .order_by(table.c.revision)
        ).mappings()
    )
    if not rows:
        raise WorkflowError("Recover the original NPC's source-owned required Play")
    first, last = rows[0], rows[-1]
    if (
        first["kind"] != "npc_bond_play"
        or first["event_id"] != request.event
        or first["owner_id"] != str(request.controller)
        or first["subject_id"] != request.holder.entity
        or not first["campaign_context"]
        or json.loads(first["body_json"]) != {"request": request.id}
        or any(
            first[k] != last[k]
            for k in (
                "owner_id",
                "subject_id",
                "kind",
                "campaign_context",
                "mission_id",
                "off_duty_id",
                "scene_id",
            )
        )
    ):
        raise WorkflowError("Preserve this original NPC's actual task/controller/source")
    return dict(last)


def prove_request(
    game: GameService, c: Connection, state: GameState, identity: str
) -> rules.Request:
    value = next((x for x in rules.requests(state) if x.id == identity), None)
    if value is None:
        raise WorkflowError("Recover the actual original NPC Bond request")
    _gate(game, value.job)
    born = _history(c, game, value.event)
    before = _history_revision(game, c, born.revision - 1)
    audit = c.execute(
        sa.select(t.events.c.kind, t.events.c.actor_id).where(
            t.events.c.campaign_id == game.store.campaign_id, t.events.c.id == value.event
        )
    ).first()
    npc = Npc.model_validate_json(value.original_npc_json)
    girl = before.sheets.get(value.holder.entity)
    # The existing reducer also removes this pair's legacy mirror while writing
    # the one canonical edge; every other original NPC field remains identical.
    after_npc = npc.model_copy(
        update={
            "bonds": {
                k: v
                for k, v in npc.bonds.items()
                if k != value.holder.kind + ":" + value.holder.entity
            }
        }
    )
    if (
        value not in rules.requests(born)
        or audit != ("m3.npc_bond_requested", value.holder.entity)
        or value.holder.kind != "pilot"
        or value.npc.kind != "npc"
        or girl is None
        or girl.character_id != value.holder.incarnation
        or value.npc.entity != npc.id
        or not npc.alive
        or npc.controller != value.controller
        or value.job not in npc.jobs
        or not rules.supported(value.job, value.move)
        or NARRATIVE[value.job][1] != value.source_pdf
        or _npc(before, value.npc) != npc
        or _npc(born, value.npc) != after_npc
        or depth(before, value.holder, value.npc) != value.before_depth
        or depth(born, value.holder, value.npc) != value.after_depth
        or value.after_depth != value.before_depth - 1
    ):
        raise WorkflowError("Recover the genuine original Girl/NPC and exact one-step Bond cost")
    _work(game, c, value)
    return value


def _historical_role(state: GameState, role: CastRole) -> str:
    if role.actor.kind == "pilot":
        sheet = state.sheets.get(role.actor.entity)
        if (
            sheet is None
            or sheet.character_id != role.actor.incarnation
            or int(role.actor.entity) != role.controller
        ):
            raise WorkflowError("Preserve the actual original recipient Girl and controller")
        return sheet.callsign
    actual = resolve(state, role.actor, (), require_current_profile=False)
    if actual.controller != role.controller:
        raise WorkflowError("Preserve the actual original recipient actor/controller")
    return actual.label


def prove_performance(
    game: GameService, c: Connection, state: GameState, identity: str
) -> rules.Performance:
    value = rules.done(state, identity)
    if value is None:
        raise WorkflowError("The original NPC has not actually performed this Play")
    request = prove_request(game, c, state, identity)
    born = _history(c, game, value.event)
    audit = c.execute(
        sa.select(t.events.c.kind, t.events.c.actor_id).where(
            t.events.c.campaign_id == game.store.campaign_id, t.events.c.id == value.event
        )
    ).first()
    npc = _npc(born, request.npc)
    work = _work(game, c, request)
    if (
        work["state"] != "resolved"
        or work["event_id"] != value.event
        or json.loads(work["body_json"]) != {"request": identity, "performance": value.id}
    ):
        raise WorkflowError("Finish the genuine NPC source work with its actual performance")
    if (
        value not in rules.performances(born)
        or audit != ("m3.npc_bond_performed", str(request.controller))
        or value.controller != request.controller
        or not npc.alive
        or npc.controller != request.controller
        or request.job not in npc.jobs
        or value.cast not in born.scene_casts
        or not value.cast.open
        or not any(
            x.actor == request.npc and x.controller == request.controller for x in value.cast.roles
        )
        or len(set(value.recipients)) != len(value.recipients)
        or any(x not in value.cast.roles or x.actor == request.npc for x in value.recipients)
        or value.labels != {x.actor.token: _historical_role(born, x) for x in value.recipients}
    ):
        raise WorkflowError(
            "Recover the actual job-defined NPC rendition and original scene audience"
        )
    return value


class NpcBondPlayService:
    def __init__(self, store: OnboardingStore):
        self.store, self.game = store, GameService(store)

    def _access(self, c: Connection, viewer: GuildViewer) -> None:
        Access(self.store).authorize(c, viewer, "plays")
        gate = Access(self.store)
        assert gate.registry is not None
        gate.registry.require_available(rules.RULE)

    def _write(
        self, viewer: GuildViewer, key: str, kind: str, body: dict[str, Any], operation: Any
    ) -> dict[str, Any]:
        def access(c: Connection) -> None:
            self._access(c, viewer)
            self.game.unpaused(c)

        try:
            return self.store._write(
                viewer, key, kind, body, operation, auto_audit=False, authorize=access
            )
        except ValueError as error:
            raise WorkflowError(str(error)) from None

    def request(
        self,
        viewer: GuildViewer,
        key: str,
        revision: int,
        npc: ActorRef,
        job: str,
        move: str,
        context: str,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            state = load_state(c, self.store.campaign_id)
            holder = current_ref(state, viewer.user_id)
            if holder.kind != "pilot":
                raise WorkflowError(
                    "This source adapter uses an actual original Girl-owned NPC Bond"
                )
            self.game.character_binding(c, state, viewer.user_id, require_current_profile=False)
            actual = resolve(
                state, holder, profiles(c, self.store.campaign_id), require_current_profile=False
            )
            target = _npc(state, npc)
            npc_actor = resolve(state, npc, (), require_current_profile=False)
            from girlframe.services.m3_npc_guard import _prove_branch

            _prove_branch(self.game, c, state, npc)
            if npc_actor.rules != "npc" or npc_actor.controller != target.controller:
                raise WorkflowError("Use the original NPC's actual body and controller source")
            if (
                state.revision != revision
                or not actual.alive
                or not target.alive
                or job not in target.jobs
                or not rules.supported(job, move)
            ):
                raise WorkflowError(
                    "Choose an actual current NPC job's supported Conversation move before spending"
                )
            _gate(self.game, job)
            before = _history_revision(self.game, c, state.revision)
            value = depth(state, holder, npc)
            if (
                value not in (1, 2)
                or depth(before, holder, npc) != value
                or _npc(before, npc) != target
            ):
                raise WorkflowError("Weaken only this actual canonical NPC Bond, once")
            event, identity = str(uuid4()), "npc-bond-play:" + str(uuid4())
            changed = change(state, holder, npc, -1, event)
            record = rules.Request(
                id=identity,
                holder=holder,
                npc=npc,
                controller=target.controller,
                job=job,
                move=move,
                source_pdf=NARRATIVE[job][1],
                context=context.strip(),
                before_depth=1 if value == 1 else 2,
                after_depth=0 if value == 1 else 1,
                original_npc_json=target.model_dump_json(),
                event=event,
            )
            rules.put(changed, record)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.npc_bond_requested",
                changed,
                event_id=event,
                request_id=identity,
            )
            related(
                c,
                self.store,
                dict(campaign_id=self.store.campaign_id, campaign_context=True),
                identity,
                target.controller,
                viewer.user_id,
                "npc_bond_play",
                dict(request=identity),
                event,
            )
            return dict(id=identity, revision=changed.revision, phase="pending")

        return self._write(
            viewer,
            key,
            "m3.npc_bond_requested",
            dict(
                revision=revision,
                npc=npc.model_dump(mode="json"),
                job=job,
                move=move,
                context=context,
            ),
            operation,
        )

    def perform(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        channel: int,
        recipients: tuple[ActorRef, ...],
        rendition: str,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            state = load_state(c, self.store.campaign_id)
            request = prove_request(self.game, c, state, identity)
            row = _work(self.game, c, request)
            cast = _cast(self.game, c, state, channel)
            npc = _npc(state, request.npc)
            npc_actor = resolve(state, request.npc, (), require_current_profile=False)
            from girlframe.services.m3_npc_guard import _prove_branch

            _prove_branch(self.game, c, state, request.npc)
            if npc_actor.rules != "npc" or npc_actor.controller != request.controller:
                raise WorkflowError("Use this actual original NPC body and human controller")
            if (
                state.revision != revision
                or viewer.user_id != request.controller
                or npc.controller != request.controller
                or not npc.alive
                or request.job not in npc.jobs
                or row["state"] != "pending"
                or rules.done(state, identity)
                or not any(
                    x.actor == request.npc and x.controller == viewer.user_id for x in cast.roles
                )
                or not recipients
                or len(set(recipients)) != len(recipients)
            ):
                raise WorkflowError(
                    "The original NPC's current human performs this saved Play in its real scene"
                )
            roles = tuple(x for x in cast.roles if x.actor in recipients and x.actor != request.npc)
            if {x.actor for x in roles} != set(recipients):
                raise WorkflowError(
                    "Address actual original scene recipients, not an OOC cast or later roster"
                )
            # This finite local Conversation port never supplies travel or remote hardware.
            for role in roles:
                target = resolve(
                    state,
                    role.actor,
                    profiles(c, self.store.campaign_id),
                    require_current_profile=False,
                )
                if target.cell is None or target.cell != npc_actor.cell:
                    raise WorkflowError(
                        "SOURCE_NPC_CONTACT_REQUIRED: establish actual Conversation contact first"
                    )
            event = str(uuid4())
            value = rules.Performance(
                id="npc-bond-performance:" + event,
                request=identity,
                event=event,
                controller=viewer.user_id,
                cast=cast,
                recipients=roles,
                labels={x.actor.token: _historical_role(state, x) for x in roles},
                rendition=rendition.strip(),
            )
            rules.put(state, value)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.npc_bond_performed",
                state,
                event_id=event,
                request_id=identity,
            )
            c.execute(
                t.m3["m3_required_work"]
                .insert()
                .values(
                    **{
                        k: v
                        for k, v in row.items()
                        if k not in ("revision", "state", "body_json", "event_id")
                    },
                    revision=row["revision"] + 1,
                    state="resolved",
                    body_json=json.dumps(dict(request=identity, performance=value.id)),
                    event_id=event,
                )
            )
            return dict(id=identity, revision=state.revision, phase="complete")

        return self._write(
            viewer,
            key,
            "m3.npc_bond_performed",
            dict(
                id=identity,
                revision=revision,
                channel=channel,
                recipients=[x.model_dump(mode="json") for x in recipients],
                rendition=rendition,
            ),
            operation,
        )

    def menu(self, viewer: GuildViewer, identity: str | None = None) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self._access(c, viewer)
            state = load_state(c, self.store.campaign_id)
            if identity is None or identity.startswith("npc-bond-control:"):
                holder = current_ref(state, viewer.user_id)
                if holder.kind != "pilot" or (
                    identity and identity != "npc-bond-control:" + holder.token
                ):
                    raise WorkflowError("Use your actual original Girl's own NPC Bonds")
                self.game.character_binding(c, state, viewer.user_id, require_current_profile=False)
                rows = []
                for npc in state.world.npcs if state.world else ():
                    ref = ActorRef(kind="npc", entity=npc.id)
                    if npc.alive and depth(state, holder, ref) > 0:
                        rows.append(
                            dict(
                                ref=ref.model_dump(mode="json"),
                                token=ref.token,
                                label=npc.name,
                                depth=depth(state, holder, ref),
                                moves=[
                                    dict(job=x, move=NARRATIVE[x][0], pdf=NARRATIVE[x][1])
                                    for x in npc.jobs
                                    if x in NARRATIVE
                                ],
                            )
                        )
                return dict(
                    id="npc-bond-control:" + holder.token,
                    revision=state.revision,
                    control=True,
                    npcs=rows,
                )
            request = prove_request(self.game, c, state, identity)
            performance = rules.done(state, identity)
            involved = viewer.user_id in (int(request.holder.entity), request.controller)
            addressed = performance is not None and any(
                x.controller == viewer.user_id for x in performance.recipients
            )
            if not involved and not addressed:
                raise WorkflowError(
                    "This NPC rendition belongs to its actual original participants"
                )
            if performance:
                performance = prove_performance(self.game, c, state, identity)
            controller = viewer.user_id == request.controller
            visible = controller or addressed
            npc = _npc(state, request.npc)
            stale = None
            if npc.controller != request.controller or not npc.alive or request.job not in npc.jobs:
                stale = "SOURCE_NPC_RECOVERY_REQUIRED: original NPC/controller/job changed"
            scenes = (
                [
                    x
                    for x in state.scene_casts
                    if x.open
                    and any(
                        r.actor == request.npc and r.controller == viewer.user_id for r in x.roles
                    )
                ]
                if controller and not performance
                else []
            )
            return dict(
                id=identity,
                revision=state.revision,
                control=False,
                phase="complete" if performance else "pending",
                holder=request.holder.model_dump(mode="json") if involved else None,
                npc=dict(
                    ref=request.npc.model_dump(mode="json"),
                    label=Npc.model_validate_json(request.original_npc_json).name,
                ),
                cost=dict(before=request.before_depth, after=request.after_depth)
                if involved
                else None,
                move=request.move,
                context=request.context if involved else None,
                can_perform=controller and not performance and stale is None,
                stale=stale if controller else None,
                rendition=performance.rendition if performance and visible else None,
                audience=list(performance.labels.values()) if performance and controller else [],
                scenes=[
                    dict(
                        id=str(x.channel),
                        label=str(x.channel),
                        recipients=[
                            dict(
                                ref=r.actor.model_dump(mode="json"),
                                token=r.actor.token,
                                label=_historical_role(state, r),
                            )
                            for r in x.roles
                            if r.actor != request.npc
                        ],
                    )
                    for x in scenes
                ],
            )

    def _tasks(self, c: Connection, viewer: GuildViewer) -> list[dict[str, Any]]:
        self.game.authorize(c, viewer, game=False)
        state = load_state(c, self.store.campaign_id)
        rows = []
        sheet = state.sheets.get(str(viewer.user_id))
        if sheet and sheet.character_id:
            holder = current_ref(state, viewer.user_id)
            rows.append(
                dict(
                    id="npc-bond-control:" + holder.token,
                    revision=state.revision,
                    label="Your NPC Bonds — request a Conversation Play",
                    phase="available",
                    pending=False,
                )
            )
        for request in rules.requests(state):
            performance = rules.done(state, request.id)
            participant = viewer.user_id in (int(request.holder.entity), request.controller)
            addressed = performance is not None and any(
                x.controller == viewer.user_id for x in performance.recipients
            )
            if participant or addressed:
                rows.append(
                    dict(
                        id=request.id,
                        revision=state.revision,
                        label="NPC Play: " + request.move,
                        phase="complete" if performance else "pending",
                        pending=performance is None and viewer.user_id == request.controller,
                    )
                )
        return rows
