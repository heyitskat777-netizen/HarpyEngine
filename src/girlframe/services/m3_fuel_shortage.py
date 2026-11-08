"""Canonical future-battle scheduling and same-confirmation unavoidable fuel loss."""

import json
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_fuel_shortage as rules
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef, ProfileBinding
from girlframe.engine.m3_battle_state import Context
from girlframe.engine.m3_collateral import loss as quadrant_loss
from girlframe.engine.m3_handler_consequences import active_handler, same_handler_body
from girlframe.engine.m3_world_state import WorldTag
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_actors import profiles
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer


def _event(game: GameService, c: Connection, identity: str) -> dict[str, Any]:
    row = (
        c.execute(
            sa.select(t.events).where(
                t.events.c.campaign_id == game.store.campaign_id,
                t.events.c.id == identity,
            )
        )
        .mappings()
        .first()
    )
    if row is None:
        raise WorkflowError("Recover the actual fuel source event")
    return dict(row)


def _history(game: GameService, c: Connection, event: str) -> GameState:
    raw = c.scalar(
        sa.select(t.m2["m2_state_history"].c.body_json).where(
            t.m2["m2_state_history"].c.campaign_id == game.store.campaign_id,
            t.m2["m2_state_history"].c.event_id == event,
        )
    )
    if raw is None:
        raise WorkflowError("Recover the original fuel/battle source snapshot")
    return GameState.model_validate_json(raw)


def _before(game: GameService, c: Connection, event: str) -> GameState:
    audit = _event(game, c, event)
    history = t.m2["m2_state_history"]
    raw = c.scalar(
        sa.select(history.c.body_json)
        .join(
            t.events,
            sa.and_(
                t.events.c.campaign_id == history.c.campaign_id,
                t.events.c.id == history.c.event_id,
            ),
        )
        .where(
            t.events.c.campaign_id == game.store.campaign_id,
            t.events.c.seq < audit["seq"],
        )
        .order_by(t.events.c.seq.desc())
        .limit(1)
    )
    if raw is None:
        raise WorkflowError("Recover the real state immediately before the unavoidable loss")
    return GameState.model_validate_json(raw)


def _context(state: GameState, identity: str) -> Context:
    row = next(
        (
            x
            for x in reversed(state.facts)
            if x.get("kind") == "battle_context" and x.get("id") == identity
        ),
        None,
    )
    if row is None:
        raise WorkflowError("Open an actual battle declaration")
    return Context.model_validate_json(row["body"])


def _birth_bindings(
    game: GameService, c: Connection, state: GameState
) -> tuple[ProfileBinding, ...]:
    from girlframe.engine.m3_careers import profile_character

    result = []
    for sheet in state.sheets.values():
        original = c.scalar(
            sa.select(t.snapshots.c.character_id).where(
                t.snapshots.c.campaign_id == game.store.campaign_id,
                t.snapshots.c.user_id == str(sheet.owner),
                t.snapshots.c.revision == sheet.source_profile_revision,
            )
        )
        if original is None:
            raise WorkflowError("Recover the original battle profile snapshot")
        result.append(
            ProfileBinding(
                owner=sheet.owner,
                character_id=profile_character(
                    state, sheet.owner, original, sheet.source_profile_revision
                ),
                profile_revision=sheet.source_profile_revision,
                source_character_id=original,
                source_profile_revision=sheet.source_profile_revision,
            )
        )
    return tuple(result)


def _source(game: GameService, c: Connection, identity: str) -> tuple[dict[str, Any], str]:
    work = t.m3["m3_required_work"]
    rows = list(
        c.execute(
            sa.select(work)
            .where(
                work.c.campaign_id == game.store.campaign_id,
                work.c.id == identity,
            )
            .order_by(work.c.revision)
        ).mappings()
    )
    if not rows:
        raise WorkflowError("Open the actual selected fuel-shortage effect")
    first, latest = rows[0], rows[-1]
    if any(
        latest[k] != first[k]
        for k in (
            "kind",
            "body_json",
            "owner_id",
            "subject_id",
            "off_duty_id",
        )
    ):
        raise WorkflowError("Preserve the original fuel-shortage work and its source")
    body = json.loads(first["body_json"])
    audit = _event(game, c, first["event_id"])
    original = _history(game, c, first["event_id"])
    selected = (
        next((x for x in original.strain.events if x.id == body.get("source_work")), None)
        if original.strain
        else None
    )
    payload = json.loads(audit["payload_json"])
    handler = active_handler(original)
    if (
        first["kind"] != "strain_event"
        or body.get("rule_id") != rules.RULE
        or selected is None
        or selected.rule_id != rules.RULE
        or selected.period_id != first["off_duty_id"]
        or audit["kind"] != "m3.strain_option_saved"
        or payload.get("work_id") != selected.id
        or payload.get("rule_id") != rules.RULE
        or handler is None
        or first["owner_id"] != handler.entity
        or audit["actor_id"] != handler.entity
    ):
        raise WorkflowError("Prove the actual selected High Budget die-one column-two source")
    return dict(latest), first["event_id"]


def _proposed(game: GameService, c: Connection, context: Context) -> None:
    audit = _event(game, c, context.proposed_event)
    born = _context(_history(game, c, context.proposed_event), context.id)
    if (
        audit["kind"] != "m3.battle_proposed"
        or audit["actor_id"] != str(context.source_author or context.owner)
        or json.loads(audit["payload_json"]).get("context") != context.id
        or born.state != "proposed"
        or born.declaration != context.declaration
        or born.scene != context.scene
        or born.owner != context.owner
        or born.adjudicator != context.adjudicator
        or born.appointment != context.appointment
        or born.source_action != context.source_action
    ):
        raise WorkflowError("Preserve the genuine original battle declaration and people")


def _first_battle(game: GameService, c: Connection, arm: rules.Arm, before_seq: int) -> str | None:
    armed = _event(game, c, arm.event)["seq"]
    for row in c.execute(
        sa.select(t.events)
        .where(
            t.events.c.campaign_id == game.store.campaign_id,
            t.events.c.kind == "m3.battle_confirmed",
            t.events.c.seq > armed,
            t.events.c.seq < before_seq,
        )
        .order_by(t.events.c.seq)
    ).mappings():
        identity = json.loads(row["payload_json"]).get("context")
        if not identity:
            raise WorkflowError("Recover the actual confirmed battle source")
        context = _context(_history(game, c, row["id"]), identity)
        if rules.involves(arm, context) and _event(game, c, context.proposed_event)["seq"] > armed:
            return context.id
    return None


def prove(game: GameService, c: Connection, state: GameState, identity: str) -> rules.Arm:
    value = next((x for x in rules.records(state) if x.id == identity), None)
    if value is None:
        raise WorkflowError("Recover the actual armed fuel shortage")
    row, selected_event = _source(game, c, identity)
    born_state = _history(game, c, value.event)
    born = next((x for x in rules.records(born_state) if x.id == identity), None)
    audit = _event(game, c, value.event)
    if (
        born is None
        or born.battle is not None
        or born.model_copy(
            update=dict(
                battle=value.battle,
                battle_event=value.battle_event,
                loss=value.loss,
                original_npc=value.original_npc,
                original_location=value.original_location,
                completed_event=value.completed_event,
            )
        )
        != value
        or value.source_event != selected_event
        or value.period != row["off_duty_id"]
        or audit["kind"] != "m3.fuel_shortage_armed"
        or audit["actor_id"] != value.handler.entity
        or active_handler(born_state) != value.handler
        or value.cadre != tuple(current_ref(born_state, uid) for uid in born_state.order)
        or json.loads(audit["payload_json"]).get("work_id") != identity
        or row["state"] != "resolved"
        or row["event_id"] != value.event
    ):
        raise WorkflowError("Preserve the original canonical future-battle scheduling source")
    if value.battle is None:
        return value
    assert value.battle_event is not None and value.loss is not None
    after = _history(game, c, value.battle_event)
    saved = next((x for x in rules.records(after) if x.id == identity), None)
    battle = _context(after, value.battle)
    from girlframe.services.m3_battle import _context_proof

    _context_proof(game, c, battle)
    battle_audit = _event(game, c, value.battle_event)
    payload = json.loads(battle_audit["payload_json"])
    authored = tuple(
        rules.LossSelection.model_validate_json(json.dumps(x))
        for x in payload.get("fuel_losses", ())
    )
    if (
        saved != value.model_copy(update=dict(completed_event=None))
        or battle.confirmed_event != value.battle_event
        or not rules.involves(value, battle)
        or value.loss not in authored
        or _event(game, c, battle.proposed_event)["seq"] <= audit["seq"]
        or _first_battle(game, c, value, battle_audit["seq"]) is not None
    ):
        raise WorkflowError("Bind each source only to its genuine first subsequent Cadre battle")
    before = _before(game, c, value.battle_event)
    prior = next((x for x in rules.records(before) if x.id == identity), None)
    if prior != born or before.world is None or after.world is None:
        raise WorkflowError("Recover the actual still-armed source and pre-loss world")
    eligible_npcs, eligible_sites = rules.candidates(
        before, battle, _birth_bindings(game, c, before)
    )
    if (
        (value.original_npc is not None and value.original_npc not in eligible_npcs)
        or (value.original_location is not None and value.original_location not in eligible_sites)
        or {x.source for x in authored}
        != {x.id for x in rules.records(after) if x.battle_event == value.battle_event}
        or len({x.source for x in authored}) != len(authored)
    ):
        raise WorkflowError("Prove exact original human selections and actual battle-site victims")
    if value.loss.manifestation_source:
        prove_manifestation(game, c, before, value.loss.manifestation_source)
    try:
        expected = rules.bind(
            before,
            prior,
            battle,
            value.loss,
            value.battle_event,
            _birth_bindings(game, c, before),
        )
    except ValueError as error:
        raise WorkflowError(str(error)) from None
    assert expected.world is not None
    if saved not in rules.records(expected):
        raise WorkflowError("Preserve exact bound source, original endpoints and selected outcomes")
    if value.original_npc is not None:
        assert value.loss.npc is not None
        npc = value.original_npc
        actual = next((x for x in expected.world.npcs if x.id == npc.id), None)
        if npc not in before.world.npcs or actual not in after.world.npcs:
            raise WorkflowError("Prove the original actual NPC and exact same-event outcome")
        if value.loss.npc_outcome != "corrupt" and (
            any(any(r.actor == value.loss.npc for r in cast.roles) for cast in after.scene_casts)
            or not any(
                x.get("kind") == "battle_actor_cast_ended"
                and x.get("actor") == value.loss.npc.model_dump_json()
                and x.get("event") == value.battle_event
                for x in after.facts
            )
        ):
            raise WorkflowError("Prove the actual death/capture and same-event cast ending")
    if value.original_location is not None:
        site = value.original_location
        actual_site = next((x for x in expected.world.locations if x.id == site.id), None)
        if site not in before.world.locations or actual_site not in after.world.locations:
            raise WorkflowError("Prove the original site and exact same-event loss")
        destroyed = any(
            x.get("kind") == "structure_destroyed_source"
            and x.get("source") == identity
            and x.get("entity") == site.id
            and x.get("event") == value.battle_event
            for x in after.facts
        )
        if destroyed != (value.loss.location_outcome == "destroy"):
            raise WorkflowError("Keep real control loss separate from destruction")
        if value.loss.location_outcome != "destroy" and any(
            x.get("kind") == "quadrant_loss"
            and quadrant_loss(after, x["id"]).source == identity
            and quadrant_loss(after, x["id"]).source_event == value.battle_event
            for x in after.facts
        ):
            raise WorkflowError(
                "Intact captured/corrupted sites do not fake destroyed-Base aftermath"
            )
    if value.completed_event:
        completed = _event(game, c, value.completed_event)
        if (
            completed["kind"] != "m3.fuel_shortage_completed"
            or completed["actor_id"] != battle_audit["actor_id"]
            or identity not in json.loads(completed["payload_json"]).get("sources", ())
            or value not in rules.records(_history(game, c, value.completed_event))
        ):
            raise WorkflowError("Prove actual canonical fuel loss completion")
    return value


def prove_npc_void_tag(
    game: GameService, c: Connection, state: GameState, target: ActorRef, tag_id: str
) -> WorldTag:
    from girlframe.engine.m3_npc_void import npc_void_tag

    value = next(
        (
            x
            for x in rules.records(state)
            if "fuel:void:" + x.id == tag_id
            and x.loss is not None
            and x.loss.npc == target
            and x.loss.npc_outcome == "corrupt"
        ),
        None,
    )
    if value is None:
        raise WorkflowError("Recover the actual bound Fuel NPC Void source")
    prove(game, c, state, value.id)
    assert value.loss is not None and value.loss.threat is not None
    assert value.loss.manifestation is not None
    expected = npc_void_tag(tag_id, value.loss.manifestation, value.loss.threat.model_dump_json())
    npc = (
        next((x for x in state.world.npcs if x.id == target.entity), None) if state.world else None
    )
    actual = next((x for x in npc.tags if x.id == tag_id), None) if npc else None
    if actual is None or (actual.label, actual.giver_entity) != (
        expected.label,
        expected.giver_entity,
    ):
        raise WorkflowError("Use the actual present source-proved NPC Void Tag")
    return actual


def prove_manifestation(
    game: GameService, c: Connection, state: GameState, identity: str
) -> rules.ManifestationChoice:
    value = next((x for x in rules.manifestations(state) if x.id == identity), None)
    if value is None:
        raise WorkflowError("Recover the actual Handler's saved NPC Void choice")
    born = _history(game, c, value.event)
    audit = _event(game, c, value.event)
    context = _context(born, value.context)
    if (
        value not in rules.manifestations(born)
        or active_handler(born) != value.handler
        or audit["actor_id"] != value.handler.entity
        or audit["kind"] != "m3.fuel_manifestation_chosen"
        or json.loads(audit["payload_json"]).get("choice") != identity
        or context.proposed_event != value.proposed_event
        or context.state != "proposed"
        or value.source not in {x.id for x in pending(game, c, born, context)}
    ):
        raise WorkflowError("Prove the real original Handler's canonical manifestation choice")
    return value


def pending(
    game: GameService, c: Connection, state: GameState, context: Context
) -> tuple[rules.Arm, ...]:
    candidates = tuple(
        x for x in rules.records(state) if x.battle is None and rules.involves(x, context)
    )
    if not candidates:
        return ()
    _proposed(game, c, context)
    proposed_seq = _event(game, c, context.proposed_event)["seq"]
    result = []
    for value in candidates:
        prove(game, c, state, value.id)
        if proposed_seq > _event(game, c, value.event)["seq"]:
            result.append(value)
    return tuple(result)


def bind_battle(
    game: GameService,
    c: Connection,
    state: GameState,
    context: Context,
    event: str,
    selections: tuple[rules.LossSelection, ...] = (),
) -> bool:
    required = pending(game, c, state, context)
    if len({x.source for x in selections}) != len(selections) or {x.source for x in selections} != {
        x.id for x in required
    }:
        raise WorkflowError(
            "Choose an actual unavoidable loss for every armed fuel-shortage source"
        )
    if not required:
        return False
    if game.pending_actions(c):
        raise WorkflowError("Resolve the actual held Play before binding the next battle loss")
    # No historical confirmation can be skipped or retroactively supplied with a loss.
    limit = (
        int(
            c.scalar(
                sa.select(sa.func.max(t.events.c.seq)).where(
                    t.events.c.campaign_id == game.store.campaign_id,
                )
            )
            or 0
        )
        + 1
    )
    changed = state.model_copy(deep=True)
    bound = profiles(c, game.store.campaign_id)
    for value in required:
        if _first_battle(game, c, value, limit) is not None:
            raise WorkflowError(
                "SOURCE_FUEL_BATTLE_BINDING_REQUIRED: recover the first actual battle"
            )
        selection = next(x for x in selections if x.source == value.id)
        if selection.manifestation_source:
            prove_manifestation(game, c, changed, selection.manifestation_source)
        try:
            changed = rules.bind(changed, value, context, selection, event, bound)
        except ValueError as error:
            raise WorkflowError(str(error)) from None
    for field in GameState.model_fields:
        setattr(state, field, getattr(changed, field))
    return True


def synchronize(game: GameService, c: Connection, event: str) -> None:
    state = load_state(c, game.store.campaign_id)
    values = tuple(
        x for x in rules.records(state) if x.battle_event == event and not x.completed_event
    )
    if not values:
        return
    for value in values:
        prove(game, c, state, value.id)
    # These mirror already committed pure changes; they do not alter the saved cast revision.
    from girlframe.engine.m3_collateral import loss
    from girlframe.services.m3_battle import synchronize_casts
    from girlframe.services.m3_quadrant_loss import materialize_loss

    synchronize_casts(game, c, event)
    for fact in state.facts:
        if fact.get("kind") == "quadrant_loss":
            actual = loss(state, fact["id"])
            if actual.source_event == event and actual.source in {x.id for x in values}:
                materialize_loss(game, c, actual, event, period=None)
    completion = str(uuid4())
    for value in values:
        rules.put(state, value.model_copy(update=dict(completed_event=completion)))
    audit = _event(game, c, event)
    game.event(
        c,
        int(audit["actor_id"]),
        "fuel.complete:" + event,
        "m3.fuel_shortage_completed",
        state,
        event_id=completion,
        sources=[x.id for x in values],
        battle_event=event,
    )


def require_complete(game: GameService, c: Connection, state: GameState, actor: ActorRef) -> None:
    for value in rules.records(state):
        if actor not in value.cadre:
            continue
        if value.battle is None:
            limit = (
                int(
                    c.scalar(
                        sa.select(sa.func.max(t.events.c.seq)).where(
                            t.events.c.campaign_id == game.store.campaign_id,
                        )
                    )
                    or 0
                )
                + 1
            )
            if _first_battle(game, c, value, limit) is not None:
                prove(game, c, state, value.id)
                raise WorkflowError(
                    "SOURCE_FUEL_BATTLE_BINDING_REQUIRED: recover the actual first-battle loss"
                )
            continue
        if not value.completed_event:
            prove(game, c, state, value.id)
            raise WorkflowError("Complete the actual bound fuel-shortage loss before another Play")
        from girlframe.engine.m3_collateral import loss
        from girlframe.services.m3_quadrant_loss import LossService

        for fact in state.facts:
            if fact.get("kind") != "quadrant_loss":
                continue
            aftermath = loss(state, fact["id"])
            if (
                aftermath.source == value.id
                and aftermath.source_event == value.battle_event
                and aftermath.phase != "complete"
            ):
                prove(game, c, state, value.id)
                LossService(game.store)._proof(c, aftermath.id)
                raise WorkflowError("Resolve the actual last-Base aftermath before a new Play")


class FuelService:
    def __init__(self, game: GameService):
        self.game, self.store = game, game.store

    def _access(self, c: Connection, viewer: GuildViewer) -> None:
        Access(self.store).authorize(c, viewer, "strain", director_response=True)
        Access(self.store).authorize(c, viewer, "world", director_response=True)

    def arm(self, viewer: GuildViewer, key: str, identity: str, expected: int) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            row, source = _source(self.game, c, identity)
            original = _history(self.game, c, source)
            handler = active_handler(original)
            state = load_state(c, self.store.campaign_id)
            if (
                state.revision != expected
                or row["state"] != "pending"
                or handler is None
                or handler.entity != str(viewer.user_id)
                or not same_handler_body(state, handler)
                or any(x.id == identity for x in rules.records(state))
            ):
                raise WorkflowError("Reopen the actual original Handler's pending fuel source")
            event = str(uuid4())
            value = rules.Arm(
                id=identity,
                source_event=source,
                period=row["off_duty_id"],
                handler=handler,
                cadre=tuple(current_ref(state, uid) for uid in state.order),
                event=event,
            )
            for person in state.order:
                self.game.character_binding(c, state, person)
            rules.put(state, value)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.fuel_shortage_armed",
                state,
                event_id=event,
                work_id=identity,
            )
            c.execute(
                t.m3["m3_required_work"]
                .insert()
                .values(
                    **{k: v for k, v in row.items() if k not in ("revision", "state", "event_id")},
                    revision=row["revision"] + 1,
                    state="resolved",
                    event_id=event,
                )
            )
            return dict(id=identity, phase="armed")

        return self.store._write(
            viewer,
            key,
            "m3.fuel_shortage_arm",
            dict(id=identity, expected=expected),
            operation,
            auto_audit=False,
            authorize=lambda c: self._access(c, viewer),
        )

    def for_context(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            state = load_state(c, self.store.campaign_id)
            context = _context(state, identity)
            if viewer.user_id != context.adjudicator or context.state != "proposed":
                raise WorkflowError("Only the actual source adjudicator selects this battle's loss")
            if not any(
                x.battle is None and rules.involves(x, context) for x in rules.records(state)
            ):
                return dict(id=identity, required=False, revision=state.revision, arms=[])
            self._access(c, viewer)
            values = pending(self.game, c, state, context)
            npcs, locations = (
                rules.candidates(state, context, profiles(c, self.store.campaign_id))
                if values
                else ((), ())
            )
            available_threats = (
                rules.threats(state, context, profiles(c, self.store.campaign_id)) if values else ()
            )
            return dict(
                id=identity,
                required=bool(values),
                revision=state.revision,
                arms=[
                    dict(
                        id=x.id,
                        label="Actual armed fuel shortage",
                        npcs=[
                            dict(
                                ref=ActorRef(kind="npc", entity=p.id).model_dump(mode="json"),
                                label=p.name,
                            )
                            for p in npcs
                        ],
                        locations=[dict(id=p.id, label=p.name) for p in locations],
                        threats=[
                            dict(
                                ref=p.model_dump(mode="json"),
                                label=next(g.name for g in state.world.gorgons if g.id == p.entity),
                            )
                            for p in available_threats
                        ]
                        if state.world
                        else [],
                        handler_choice=context.adjudicator == state.handler,
                        manifestations=[
                            dict(
                                id=p.id,
                                target=p.target.model_dump(mode="json"),
                                threat=p.threat.model_dump(mode="json"),
                                manifestation=p.manifestation,
                            )
                            for p in rules.current_manifestations(state, x.id, context.id)
                            if prove_manifestation(self.game, c, state, p.id)
                        ],
                    )
                    for x in values
                ],
            )

    def manifestation_menu(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self._access(c, viewer)
            state = load_state(c, self.store.campaign_id)
            if viewer.user_id != state.handler or active_handler(state) is None:
                raise WorkflowError(
                    "Only the actual current Handler chooses NPC Void manifestation"
                )
            value = prove(self.game, c, state, identity)
            contexts = []
            latest = {
                x["id"]: Context.model_validate_json(x["body"])
                for x in state.facts
                if x.get("kind") == "battle_context"
            }
            bound = profiles(c, self.store.campaign_id)
            for context in latest.values():
                if context.state != "proposed" or identity not in {
                    x.id for x in pending(self.game, c, state, context)
                }:
                    continue
                people, _ = rules.candidates(state, context, bound)
                threats = rules.threats(state, context, bound)
                if not people or not threats:
                    continue
                contexts.append(
                    dict(
                        id=context.id,
                        label="Actual proposed battle",
                        npcs=[
                            dict(
                                ref=ActorRef(kind="npc", entity=x.id).model_dump(mode="json"),
                                label=x.name,
                            )
                            for x in people
                        ],
                        threats=[
                            dict(
                                ref=x.model_dump(mode="json"),
                                label=next(g.name for g in state.world.gorgons if g.id == x.entity),
                            )
                            for x in threats
                        ]
                        if state.world
                        else [],
                    )
                )
            return dict(id=value.id, revision=state.revision, contexts=contexts)

    def choose_manifestation(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        context_id: str,
        target: ActorRef,
        threat: ActorRef,
        manifestation: str,
        expected: int,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            handler = active_handler(state)
            if viewer.user_id != state.handler or handler is None or state.revision != expected:
                raise WorkflowError("Reopen the actual current Handler's NPC Void choice")
            context = _context(state, context_id)
            if context.state != "proposed" or identity not in {
                x.id for x in pending(self.game, c, state, context)
            }:
                raise WorkflowError("Choose a genuine still-pending battle's fuel source")
            bound = profiles(c, self.store.campaign_id)
            people, _ = rules.candidates(state, context, bound)
            npc = next((x for x in people if target == ActorRef(kind="npc", entity=x.id)), None)
            from girlframe.engine.m3_actors import resolve

            if (
                npc is None
                or threat not in rules.threats(state, context, bound)
                or npc.cell != resolve(state, threat, bound, require_current_profile=False).cell
            ):
                raise WorkflowError("Choose the actual NPC and nearby placed Gorgon threat")
            event = str(uuid4())
            choice = rules.ManifestationChoice.model_validate(
                dict(
                    id=event,
                    source=identity,
                    context=context_id,
                    proposed_event=context.proposed_event,
                    target=target,
                    threat=threat,
                    manifestation=manifestation,
                    handler=handler,
                    event=event,
                )
            )
            state.facts.append(
                dict(kind="fuel_manifestation", id=choice.id, body=choice.model_dump_json())
            )
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.fuel_manifestation_chosen",
                state,
                event_id=event,
                choice=choice.id,
                source=identity,
                context=context_id,
            )
            return dict(id=choice.id)

        return self.store._write(
            viewer,
            key,
            "m3.fuel_manifestation_choose",
            dict(
                id=identity,
                context=context_id,
                target=target.model_dump(mode="json"),
                threat=threat.model_dump(mode="json"),
                manifestation=manifestation,
                expected=expected,
            ),
            operation,
            auto_audit=False,
            authorize=lambda c: self._access(c, viewer),
        )

    def view(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self._access(c, viewer)
            row, source = _source(self.game, c, identity)
            original = _history(self.game, c, source)
            handler = active_handler(original)
            state = load_state(c, self.store.campaign_id)
            if handler is None or viewer.user_id != int(handler.entity):
                if viewer.user_id == state.handler:
                    menu = self.manifestation_menu(viewer, identity)
                    if menu["contexts"]:
                        return dict(
                            id=identity,
                            revision=state.revision,
                            phase="handler_choice",
                            record=None,
                            can_arm=False,
                            can_manifestation=True,
                        )
                raise WorkflowError("This scheduling source is private to its original Handler")
            value = next((x for x in rules.records(state) if x.id == identity), None)
            if value:
                prove(self.game, c, state, identity)
            return dict(
                id=identity,
                revision=state.revision,
                phase=value.phase if value else "select",
                record=value.model_dump(mode="json") if value else None,
                can_arm=value is None and row["state"] == "pending",
                can_manifestation=value is not None
                and value.battle is None
                and viewer.user_id == state.handler,
            )

    def _tasks(self, c: Connection, viewer: GuildViewer) -> list[dict[str, Any]]:
        self.game.authorize(c, viewer, game=False)
        state = load_state(c, self.store.campaign_id)
        result = []
        for value in rules.records(state):
            if value.handler.entity != str(viewer.user_id):
                if viewer.user_id != state.handler or value.battle is not None:
                    continue
                if not self.manifestation_menu(viewer, value.id)["contexts"]:
                    continue
            prove(self.game, c, state, value.id)
            result.append(
                dict(
                    id=value.id,
                    revision=state.revision,
                    label="Fuel shortage: " + value.phase,
                    phase=value.phase,
                    pending=False,
                    waiting=value.phase != "complete",
                )
            )
        return result
