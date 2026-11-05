"""Actual first-Base-loss aftermath: employment, real replacement, transport or execution."""

import json
from typing import Any, Literal, cast
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_collateral as rules
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_world_state import Board, Cell, Gorgon, Location, World
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_collateral import append, latest
from girlframe.services.m3_medical import MedicalService
from girlframe.services.m3_work import related
from girlframe.services.onboarding import OnboardingStore, WorkflowError
from girlframe.services.read_only_bot import GuildViewer


def materialize_loss(
    game: GameService,
    c: Connection,
    value: rules.Loss,
    event: str,
    source_action: str | None = None,
    period: str | None = None,
) -> None:
    table = t.m3["m3_required_work"]
    if c.scalar(
        sa.select(table.c.id).where(
            table.c.campaign_id == game.store.campaign_id, table.c.id == value.id
        )
    ):
        return
    parent: dict[str, Any] = dict(campaign_id=game.store.campaign_id)
    parent.update(off_duty_id=period) if period else parent.update(campaign_context=True)
    active_phases = {}
    for name in ("m3_missions", "m3_off_duty"):
        table = t.m3[name]
        active_phases[name] = list(
            c.scalars(
                sa.select(table.c.id).where(
                    table.c.campaign_id == game.store.campaign_id,
                    table.c.phase.not_in(("complete", "cancelled")),
                )
            )
        )
    related(
        c,
        game.store,
        parent,
        value.id,
        value.judge,
        int(value.handler.entity) if value.handler else value.judge,
        "quadrant_loss",
        dict(
            loss=value.id,
            source_action=source_action,
            source_event=event,
            period=period,
            immediate=False,
            active_phases=active_phases,
        ),
        event,
    )


def require_aftermath_clear(state: GameState) -> None:
    ids = {x["id"] for x in state.facts if x.get("kind") == "quadrant_loss"}
    if any(rules.loss(state, x).phase != "complete" for x in ids):
        raise WorkflowError(
            "Complete the actual quadrant-loss aftermath before mission or period progression."
        )


def creation_context(
    game: GameService, c: Connection, state: GameState, identity: str, owner: int
) -> dict[str, Any]:
    service = LossService(game.store)
    row, value = service._proof(c, identity)
    human, appointment = MedicalService(game.store)._handler(c)
    if owner != human or appointment != value.appointment or value.phase != "handler":
        raise WorkflowError("Only the actual source replacement Handler setup is allowed here.")
    from girlframe.engine.m3_handler_consequences import active_handler

    if active_handler(state) is not None:
        raise WorkflowError("The original source Handler has not actually departed.")
    return dict(
        loss=identity,
        source_action=json.loads(row["body_json"]).get("source_action"),
        off_duty_id=row.get("off_duty_id"),
        mission_id=row.get("mission_id"),
        active_phases=json.loads(row["body_json"]).get("active_phases", {}),
    )


def link_creation(
    game: GameService, c: Connection, state: GameState, identity: str, creation: str, event: str
) -> GameState:
    creation_context(game, c, state, identity, int(state.handler or 0))
    value = rules.loss(state, identity)
    if value.creation is not None and value.creation != creation:
        raise WorkflowError("Resume the actual source Handler creation, not a different draft.")
    updated = GameState.model_validate_json(state.model_dump_json())
    rules.save_loss(updated, value.model_copy(update=dict(creation=creation)))
    updated.facts.append(
        dict(kind="quadrant_loss_creation", loss=identity, creation=creation, event=event)
    )
    return updated


def synchronize_handler_replacement(
    game: GameService,
    c: Connection,
    creation: str,
    event: str,
    viewer: GuildViewer | None,
    key: str,
) -> None:
    state = load_state(c, game.store.campaign_id)
    matches = [
        x
        for x in state.facts
        if x.get("kind") == "quadrant_loss_creation" and x.get("creation") == creation
    ]
    if not matches:
        return
    service = LossService(game.store)
    for fact in matches:
        row, value = service._proof(c, fact["loss"])
        if value.phase != "handler":
            continue
        persona = state.handler_persona
        actual = c.execute(
            sa.select(t.events.c.kind, t.events.c.payload_json).where(
                t.events.c.campaign_id == game.store.campaign_id, t.events.c.id == event
            )
        ).first()
        if (
            persona is None
            or persona.source_event != event
            or persona.id != creation
            or actual is None
            or actual.kind != "m3.handler_activated"
        ):
            raise WorkflowError("Finish this exact actual new Handler's owned activation.")
        ref = ActorRef(kind="handler", entity=str(persona.owner), incarnation=persona.id)
        if value.handler == ref:
            raise WorkflowError("The actual new Handler must be a different persona.")
        changed = value.model_copy(
            update=dict(
                replacement=ref,
                response_event=event,
                phase="transport" if value.outcome == "reassigned" else "complete",
            )
        )
        rules.save_loss(state, changed)
        service._save(c, row, changed, state, event, viewer, key, "m3.quadrant_handler_replaced")


class LossService:
    def __init__(self, store: OnboardingStore):
        self.store, self.game = store, GameService(store)

    def _proof(self, c: Connection, identity: str) -> tuple[dict[str, Any], rules.Loss]:
        row = latest(self.game, c, identity)
        if row["kind"] != "quadrant_loss":
            raise WorkflowError("Open the actual first Base-loss episode.")
        state = load_state(c, self.store.campaign_id)
        value = rules.loss(state, identity)
        raw = c.scalar(
            sa.select(t.m2["m2_state_history"].c.body_json).where(
                t.m2["m2_state_history"].c.campaign_id == self.store.campaign_id,
                t.m2["m2_state_history"].c.event_id == value.source_event,
            )
        )
        original = GameState.model_validate_json(raw) if raw else None
        if original is None or rules.loss(original, identity).source_event != value.source_event:
            raise WorkflowError("Recover the real original Base-loss source history.")
        if original.world is None or any(
            x.kind == "base" and x.allegiance == "foundation" and x.condition != "destroyed"
            for x in original.world.locations
        ):
            raise WorkflowError("The actual original source did not lose its last Foundation Base.")
        seq = c.scalar(
            sa.select(t.events.c.seq).where(
                t.events.c.campaign_id == self.store.campaign_id,
                t.events.c.id == value.source_event,
            )
        )
        prior = (
            c.scalar(
                sa.select(t.m2["m2_state_history"].c.body_json)
                .join(t.events, t.events.c.id == t.m2["m2_state_history"].c.event_id)
                .where(t.events.c.campaign_id == self.store.campaign_id, t.events.c.seq < seq)
                .order_by(t.events.c.seq.desc())
                .limit(1)
            )
            if seq
            else None
        )
        before = GameState.model_validate_json(prior) if prior else None
        if (
            before is None
            or before.world is None
            or not any(
                x.kind == "base" and x.allegiance == "foundation" and x.condition != "destroyed"
                for x in before.world.locations
            )
        ):
            raise WorkflowError("Prove the actual first transition from surviving Bases to zero.")
        if MedicalService(self.store)._handler(c)[1] != value.appointment:
            raise WorkflowError("Recover the changed original source adjudication appointment.")
        return row, value

    def _save(
        self,
        c: Connection,
        row: dict[str, Any],
        value: rules.Loss,
        state: GameState,
        prior: str,
        viewer: GuildViewer | None,
        key: str,
        kind: str,
    ) -> str:
        event = str(uuid4())
        human = (
            viewer.user_id
            if viewer
            else c.scalar(
                sa.select(t.events.c.actor_id).where(
                    t.events.c.campaign_id == self.store.campaign_id, t.events.c.id == prior
                )
            )
        )
        if human is None:
            raise WorkflowError("Recover the actual command source of this aftermath.")
        index = c.scalar(
            sa.select(sa.func.max(t.events.c.event_index)).where(
                t.events.c.campaign_id == self.store.campaign_id, t.events.c.command_key == key
            )
        )
        self.game.event(
            c,
            human,
            key,
            kind,
            state,
            event_id=event,
            event_index=index + 1 if index is not None else 0,
            source_work=value.id,
            source_event=prior,
        )
        append(
            c,
            row,
            event,
            json.loads(row["body_json"]),
            "resolved" if value.phase == "complete" else "pending",
        )
        return event

    def _write(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        game_revision: int,
        operation: Any,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        def access(c: Connection) -> None:
            Access(self.store).authorize(c, viewer, "plays", director_response=True)
            self.game.unpaused(c)

        def apply(c: Connection) -> dict[str, Any]:
            row, value = self._proof(c, identity)
            state = load_state(c, self.store.campaign_id)
            if (
                row["revision"] != revision
                or state.revision != game_revision
                or value.phase == "complete"
            ):
                raise WorkflowError("STALE_QUADRANT_LOSS: reopen the actual original aftermath.")
            event = str(uuid4())
            updated, changed = operation(c, state, value, event)
            rules.save_loss(updated, changed)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.quadrant_loss_changed",
                updated,
                event_id=event,
                source_work=identity,
                source_event=value.source_event,
            )
            append(
                c,
                row,
                event,
                json.loads(row["body_json"]),
                "resolved" if changed.phase == "complete" else "pending",
            )
            from girlframe.services.m3_battle import synchronize_casts
            from girlframe.services.m3_careers import synchronize_end
            from girlframe.services.m3_handler_consequences import end_body_reviews, finish_callback

            for archive in updated.handler_archives:
                if archive.source_event == event:
                    end_body_reviews(self.game, c, archive)
            for consequence in updated.handler_consequences:
                if consequence.effect_event == event:
                    finish_callback(self.game, c, consequence, event, viewer, key)
            for archive in updated.career_archives:
                if archive.source_event == event:
                    synchronize_end(c, self.game, archive, exclude_work=(identity,))
            synchronize_casts(self.game, c, event)
            return dict(id=identity, phase=changed.phase, game_revision=updated.revision)

        try:
            return self.store._write(
                viewer,
                key,
                "m3.quadrant_loss_changed",
                dict(id=identity, revision=revision, game_revision=game_revision, **payload),
                apply,
                auto_audit=False,
                authorize=access,
            )
        except ValueError as error:
            raise WorkflowError(str(error)) from None

    def _tasks(self, c: Connection, viewer: GuildViewer) -> list[dict[str, Any]]:
        state = load_state(c, self.store.campaign_id)
        identities = {x["id"] for x in state.facts if x.get("kind") == "quadrant_loss"}
        result: list[dict[str, Any]] = []
        if not identities:
            return result
        gm = MedicalService(self.store)._handler(c)[0]
        for identity in identities:
            value = rules.loss(state, identity)
            if value.phase == "complete":
                continue
            owners = (
                {value.judge}
                if value.phase in ("employment", "outcome")
                else {gm}
                if value.phase == "handler"
                else set()
            )
            if value.phase == "transport":
                owners = {gm, *[int(x.entity) for x in value.cadre]}
            if value.phase == "execution" and value.executor is not None:
                agent = (
                    next((x for x in state.world.npcs if x.id == value.executor.entity), None)
                    if state.world
                    else None
                )
                owners = {value.judge, *((agent.controller,) if agent else ())}
            if viewer.user_id in owners:
                row, _ = self._proof(c, identity)
                result.append(
                    dict(
                        id=identity,
                        revision=row["revision"],
                        label="Quadrant aftermath: " + value.phase,
                        state="pending",
                        incoming=True,
                    )
                )
        return result

    def tasks(self, viewer: GuildViewer) -> list[dict[str, Any]]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            return self._tasks(c, viewer)

    def get(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            row, value = self._proof(c, identity)
            state = load_state(c, self.store.campaign_id)
            allowed = {value.judge, *[int(x.entity) for x in value.cadre]}
            gm = MedicalService(self.store)._handler(c)[0]
            allowed.add(gm)
            if value.executor:
                executor = (
                    next((x for x in state.world.npcs if x.id == value.executor.entity), None)
                    if state.world
                    else None
                )
                if executor is not None:
                    allowed.add(executor.controller)
            if viewer.user_id not in allowed:
                raise WorkflowError("This actual aftermath belongs to its original participants.")
            agents = []
            for npc in state.world.npcs if state.world else ():
                if (
                    npc.alive
                    and set(npc.jobs) & {"guard", "director", "handler"}
                    and (npc.revealed or npc.controller == viewer.user_id or viewer.user_id == gm)
                ):
                    actual = resolve(state, ActorRef(kind="npc", entity=npc.id), ())
                    if actual.cell is not None:
                        agents.append(
                            dict(
                                ref=actual.ref.model_dump(mode="json"),
                                token=actual.ref.token,
                                label=actual.label,
                            )
                        )
            public = value.model_dump(mode="json", exclude={"new_world_json"})
            if (
                value.phase == "employment"
                and value.handler is not None
                and any(x.actor == value.handler for x in state.handler_archives)
            ):
                public["phase"] = "outcome"
            return dict(
                id=identity,
                revision=row["revision"],
                game_revision=state.revision,
                episode=public,
                procedural_gm=gm,
                agents=agents,
                new_board=json.loads(value.new_world_json)["board"]
                if value.new_world_json
                else None,
                executor_controller=next(
                    (
                        x.controller
                        for x in state.world.npcs
                        if value.executor and x.id == value.executor.entity
                    ),
                    None,
                )
                if state.world
                else None,
                owner_refs=[
                    x.model_dump(mode="json")
                    for x in (*value.cadre, *((value.replacement,) if value.replacement else ()))
                    if x.kind in ("pilot", "handler")
                    and int(x.entity) == viewer.user_id
                    and not any(a.actor == x for a in state.career_archives)
                ],
            )

    def employment(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        game_revision: int,
        decision: str,
        account: str,
    ) -> dict[str, Any]:
        def change(
            c: Connection, state: GameState, value: rules.Loss, event: str
        ) -> tuple[GameState, rules.Loss]:
            if (
                value.phase != "employment"
                or viewer.user_id != value.judge
                or decision not in ("retained", "fired", "imprisoned")
                or not account.strip()
            ):
                raise WorkflowError(
                    "The actual frozen adjudicator records the real Foundation employment decision."
                )
            if decision != "retained":
                from girlframe.engine.m3_handler_consequences import depart, same_handler_body

                if value.handler is not None and same_handler_body(state, value.handler):
                    state = depart(
                        state,
                        value.handler,
                        reason=cast(Literal["fired", "retired", "imprisoned"], decision),
                        source_work=value.id,
                        event=event,
                        appointment=value.appointment,
                        account=account,
                    )
                elif value.handler is not None and not any(
                    x.actor == value.handler for x in state.handler_archives
                ):
                    raise WorkflowError(
                        "Recover the actual original Handler before this job outcome."
                    )
            return state, value.model_copy(
                update=dict(
                    employment=decision,
                    account=account,
                    response_event=event,
                    phase="complete" if decision == "retained" else "outcome",
                )
            )

        return self._write(
            viewer,
            key,
            identity,
            revision,
            game_revision,
            change,
            dict(decision=decision, account=account),
        )

    def outcome(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        game_revision: int,
        decision: str,
        account: str,
        executor: ActorRef | None = None,
    ) -> dict[str, Any]:
        def change(
            c: Connection, state: GameState, value: rules.Loss, event: str
        ) -> tuple[GameState, rules.Loss]:
            if (
                viewer.user_id != value.judge
                or (
                    value.phase != "outcome"
                    and not (value.phase == "execution" and decision == "execution")
                    and not (
                        value.phase == "employment"
                        and value.handler is not None
                        and any(x.actor == value.handler for x in state.handler_archives)
                    )
                )
                or decision not in ("new_handler", "reassigned", "execution")
                or not account.strip()
            ):
                raise WorkflowError(
                    "The actual source adjudicator records this Cadre's true institutional outcome."
                )
            if decision == "execution":
                if executor is None or state.world is None:
                    raise WorkflowError(
                        "Choose the actual existing Foundation agent who will perform the sentence."
                    )
                npc = next(
                    (x for x in state.world.npcs if x.id == executor.entity and x.alive), None
                )
                if (
                    executor.kind != "npc"
                    or npc is None
                    or not set(npc.jobs) & {"guard", "director", "handler"}
                ):
                    raise WorkflowError(
                        "Use a real living Foundation agent, not a fictional GM body."
                    )
            return state, value.model_copy(
                update=dict(
                    outcome=decision,
                    account=account,
                    response_event=event,
                    executor=executor,
                    phase="execution" if decision == "execution" else "handler",
                )
            )

        return self._write(
            viewer,
            key,
            identity,
            revision,
            game_revision,
            change,
            dict(
                decision=decision,
                account=account,
                executor=executor.model_dump(mode="json") if executor else None,
            ),
        )

    def execute(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        game_revision: int,
        account: str,
    ) -> dict[str, Any]:
        def change(
            c: Connection, state: GameState, value: rules.Loss, event: str
        ) -> tuple[GameState, rules.Loss]:
            if value.phase != "execution" or value.executor is None or not account.strip():
                raise WorkflowError("The real source sentence must exist before actual execution.")
            bound = profiles(c, self.store.campaign_id)
            actual = resolve(state, value.executor, bound)
            if actual.controller != viewer.user_id or actual.cell is None or actual.offstage_source:
                raise WorkflowError(
                    "Only the actual present Foundation agent's controller "
                    "attests carrying out this sentence."
                )
            from girlframe.engine.m3_careers import end

            for actor in value.cadre:
                if any(x.actor == actor for x in state.career_archives):
                    continue
                target = resolve(state, actor, bound, require_current_profile=False)
                if target.cell is not None and target.cell != actual.cell:
                    raise WorkflowError(
                        "Known separated bodies cannot be executed by this agent here."
                    )
                placement = next((x for x in state.placements if x.actor == actor), None)
                if (
                    placement
                    and placement.custody
                    and placement.custody.kind in ("gorgon", "external_pilot")
                ):
                    raise WorkflowError(
                        "Actual enemy custody must resolve before a Foundation execution."
                    )
                profile = c.execute(
                    sa.select(t.characters.c.id, t.characters.c.revision).where(
                        t.characters.c.campaign_id == self.store.campaign_id,
                        t.characters.c.user_id == actor.entity,
                    )
                ).first()
                if profile is None:
                    raise WorkflowError("Recover each actual original character profile source.")
                state = end(
                    state,
                    actor,
                    reason="execution",
                    source_event=event,
                    account=account,
                    archive_id=str(uuid4()),
                    profile_id=profile.id,
                    profile_revision=profile.revision,
                )
            state.facts.append(
                dict(
                    kind="quadrant_cadre_executed",
                    loss=value.id,
                    executor=value.executor.model_dump_json(),
                    event=event,
                    account=account,
                )
            )
            return state, value.model_copy(
                update=dict(phase="complete", response_event=event, account=account)
            )

        return self._write(
            viewer, key, identity, revision, game_revision, change, dict(account=account)
        )

    def new_quadrant(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        game_revision: int,
        name: str,
        board: Board,
        locations: tuple[Location, ...],
        secret: Gorgon,
    ) -> dict[str, Any]:
        from girlframe.engine.m3_world import create

        world = create(board, locations, secret)

        def change(
            c: Connection, state: GameState, value: rules.Loss, event: str
        ) -> tuple[GameState, rules.Loss]:
            if (
                value.phase != "transport"
                or value.outcome != "reassigned"
                or viewer.user_id != MedicalService(self.store)._handler(c)[0]
                or not name.strip()
            ):
                raise WorkflowError(
                    "The actual procedural Handler records the real new quadrant setup."
                )
            oldids = (
                {
                    x.id
                    for x in (
                        *state.world.locations,
                        *state.world.gorgons,
                        *state.world.npcs,
                        *state.world.pilots,
                    )
                }
                if state.world
                else set()
            )
            # Leaving an old map is not this original body's death. Its source ID
            # must not be reused to impersonate a later quadrant's entity.
            from girlframe.engine.m3_world_state import World

            for archive in state.facts:
                if archive.get("kind") == "quadrant_world_archive":
                    old_world = World.model_validate_json(archive["world"])
                    oldids.update(
                        x.id
                        for x in (
                            *old_world.locations,
                            *old_world.gorgons,
                            *old_world.npcs,
                            *old_world.pilots,
                        )
                    )
            if any(
                x.id in oldids
                for x in (*world.locations, *world.gorgons, *world.npcs, *world.pilots)
            ):
                raise WorkflowError(
                    "New quadrant entities require distinct real IDs; preserve old-world history."
                )
            return state, value.model_copy(
                update=dict(
                    new_world_json=world.model_dump_json(),
                    quadrant=name,
                    response_event=event,
                    arrivals=(),
                )
            )

        return self._write(
            viewer,
            key,
            identity,
            revision,
            game_revision,
            change,
            dict(
                name=name,
                board=board.model_dump(mode="json"),
                locations=[x.model_dump(mode="json") for x in locations],
                secret=secret.model_dump(mode="json"),
            ),
        )

    def arrive(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        game_revision: int,
        actor: ActorRef,
        cell: Cell,
        account: str,
        *,
        frame_arrived: bool = False,
        frame_cell: Cell | None = None,
    ) -> dict[str, Any]:
        def change(
            c: Connection, state: GameState, value: rules.Loss, event: str
        ) -> tuple[GameState, rules.Loss]:
            if (
                value.phase != "transport"
                or value.new_world_json is None
                or actor not in (*value.cadre, value.replacement)
                or not account.strip()
            ):
                raise WorkflowError(
                    "Only actual source Cadre/new Handler arrival belongs to this reassignment."
                )
            actual = resolve(
                state, actor, profiles(c, self.store.campaign_id), require_current_profile=False
            )
            placement = next((x for x in state.placements if x.actor == actor), None)
            carrier = placement.occupied_frame_owner if placement else None
            cadre_carrier = (
                placement is not None
                and carrier is not None
                and carrier in value.cadre
                and (placement.custody is None or placement.custody == carrier)
            )
            if (
                actual.controller != viewer.user_id
                or actual.custody not in (None, "free")
                and not cadre_carrier
                or actual.offstage_source
            ):
                raise WorkflowError(
                    "The real original body must be free; its controller attests actual transport."
                )
            world = World.model_validate_json(value.new_world_json)
            if (
                not world.board.contains(cell)
                or frame_arrived
                and (frame_cell is None or not world.board.contains(frame_cell))
            ):
                raise WorkflowError("Record actual arrived body/Frame squares on the real new map.")
            if (
                actual.inside_frame
                and carrier is None
                and (not frame_arrived or frame_cell != cell)
            ):
                raise WorkflowError(
                    "An actual occupied Frame arrives with its original body "
                    "at the same actual square."
                )
            arrival = rules.Arrival(
                actor=actor,
                cell=cell,
                frame_arrived=frame_arrived,
                frame_cell=frame_cell,
                event=event,
                account=account,
            )
            arrivals = tuple(x for x in value.arrivals if x.actor != actor) + (arrival,)
            changed = value.model_copy(update=dict(arrivals=arrivals, response_event=event))
            needed = tuple(
                x
                for x in (*value.cadre, *((value.replacement,) if value.replacement else ()))
                if not any(a.actor == x for a in state.career_archives)
            )
            arrivals = tuple(x for x in arrivals if x.actor in needed)
            changed = changed.model_copy(update=dict(arrivals=arrivals))
            if {x.actor for x in arrivals} != set(needed):
                return state, changed
            for carried_body in state.placements:
                if (
                    carried_body.actor not in value.cadre
                    or carried_body.occupied_frame_owner is None
                ):
                    continue
                own_arrival = next((x for x in arrivals if x.actor == carried_body.actor), None)
                carrier_arrival = next(
                    (x for x in arrivals if x.actor == carried_body.occupied_frame_owner), None
                )
                if (
                    own_arrival is None
                    or carrier_arrival is None
                    or not carrier_arrival.frame_arrived
                    or own_arrival.cell != carrier_arrival.frame_cell
                ):
                    raise WorkflowError(
                        "Actual passengers and their owner-attested carrier must arrive together."
                    )
            assert state.world is not None
            state.facts.append(
                dict(
                    kind="quadrant_world_archive",
                    loss=value.id,
                    world=state.world.model_dump_json(),
                    placements=json.dumps([x.model_dump(mode="json") for x in state.placements]),
                    event=event,
                )
            )
            from girlframe.engine.m3_battle import end_actor_casts

            for original in (*state.world.npcs, *state.world.gorgons, *state.world.pilots):
                kind = (
                    "npc"
                    if original in state.world.npcs
                    else "gorgon"
                    if original in state.world.gorgons
                    else "external_pilot"
                )
                state = end_actor_casts(
                    state, ActorRef.model_validate(dict(kind=kind, entity=original.id)), event
                )
            carried = []
            for arrived in arrivals:
                if arrived.actor.kind == "pilot":
                    index = next(
                        (i for i, x in enumerate(state.placements) if x.actor == arrived.actor),
                        None,
                    )
                    if index is None:
                        from girlframe.engine.m3_physical import original_placement

                        state, _ = original_placement(
                            state,
                            profiles(c, self.store.campaign_id),
                            arrived.actor,
                            event,
                            account,
                        )
                        index = next(
                            i for i, x in enumerate(state.placements) if x.actor == arrived.actor
                        )
                    old = state.placements[index]
                    state.placements[index] = old.model_copy(
                        update=dict(
                            girl_cell=arrived.cell,
                            frame_cell=arrived.frame_cell if arrived.frame_arrived else None,
                            position_event=event,
                        )
                    )
                    runtime = state.sheets[arrived.actor.entity].frame_runtime
                    assert state.world is not None
                    if runtime and runtime.core_id and arrived.frame_arrived:
                        core = next((x for x in state.world.npcs if x.id == runtime.core_id), None)
                        if core:
                            carried.append(core.model_copy(update=dict(cell=arrived.frame_cell)))
                else:
                    state.facts.append(
                        dict(
                            kind="handler_transport_arrived",
                            actor=arrived.actor.model_dump_json(),
                            cell=json.dumps(arrived.cell),
                            event=event,
                            loss=value.id,
                        )
                    )
                state = end_actor_casts(state, arrived.actor, event)
            state.world = world.model_copy(update=dict(npcs=tuple(carried)))
            state.facts.append(
                dict(
                    kind="quadrant_reassigned",
                    loss=value.id,
                    name=value.quadrant or "",
                    event=event,
                )
            )
            return state, changed.model_copy(update=dict(phase="complete"))

        return self._write(
            viewer,
            key,
            identity,
            revision,
            game_revision,
            change,
            dict(
                actor=actor.model_dump(mode="json"),
                cell=list(cell),
                account=account,
                frame_arrived=frame_arrived,
                frame_cell=frame_cell,
            ),
        )
