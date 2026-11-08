"""Actual Low Void 1/2 source, positive entry and required ordinary Heat Dive."""

import json
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_void_frame_entry as rules
from girlframe.engine.m2 import GameState, PlayInput
from girlframe.engine.m3_actor_state import ActorRef, Model
from girlframe.engine.m3_actors import fingerprint, resolve
from girlframe.engine.m3_janus_storage import effective_assets
from girlframe.engine.m3_physical import occupied_frame
from girlframe.engine.rolls import IndexSource, OsIndex
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_dose_up import _cast
from girlframe.services.m3_handler_advancements import _history
from girlframe.services.m3_strain import StrainService
from girlframe.services.m3_void import _append
from girlframe.services.m3_work import related
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer


def _get[T: Model](state: GameState, model: type[T], identity: str) -> T:
    try:
        return rules.get(state, model, identity)
    except ValueError as error:
        raise WorkflowError(str(error)) from None


def _row(game: GameService, c: Connection, identity: str, *, first: bool = False) -> dict[str, Any]:
    table = t.m3["m3_required_work"]
    row = (
        c.execute(
            sa.select(table)
            .where(
                table.c.campaign_id == game.store.campaign_id,
                table.c.id == identity,
            )
            .order_by(table.c.revision if first else table.c.revision.desc())
            .limit(1)
        )
        .mappings()
        .first()
    )
    if row is None:
        raise WorkflowError("Recover the actual original required-work source")
    return dict(row)


def _event(game: GameService, c: Connection, identity: str) -> Any:
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
        raise WorkflowError("Recover the original canonical entry event")
    return row


def _before(game: GameService, c: Connection, identity: str) -> GameState:
    row = _event(game, c, identity)
    history = t.m2["m2_state_history"]
    body = c.scalar(
        sa.select(history.c.body_json)
        .join(t.events, history.c.event_id == t.events.c.id)
        .where(
            history.c.campaign_id == game.store.campaign_id,
            t.events.c.campaign_id == game.store.campaign_id,
            t.events.c.seq < row["seq"],
        )
        .order_by(t.events.c.seq.desc())
        .limit(1)
    )
    if body is None:
        raise WorkflowError("Recover actual prior physical source history")
    return GameState.model_validate_json(body)


def _population(game: GameService, c: Connection, row: dict[str, Any]) -> tuple[ActorRef, ...]:
    body = json.loads(row["body_json"])
    event = _event(game, c, row["event_id"])
    if (
        row["kind"] != "strain_event"
        or body.get("rule_id") != rules.RULE
        or event["kind"] != "m3.strain_option_saved"
        or json.loads(event["payload_json"]).get("rule_id") != rules.RULE
        or body.get("source_work") != json.loads(event["payload_json"]).get("work_id")
    ):
        raise WorkflowError("Use the actual selected Low Void die1 column2 source")
    source = _history(c, game, row["event_id"])
    from girlframe.services.m3_missions import MissionService
    from girlframe.services.m3_off_duty import OffDutyService

    period = OffDutyService(MissionService(game.store))._get(c, row["off_duty_id"])
    result = tuple(
        ActorRef(kind="pilot", entity=str(uid), incarnation=period.character_ids.get(str(uid)))
        for uid in period.pilots
    )
    if not result or set(source.order) != set(period.pilots):
        raise WorkflowError(
            "Recover the original actual Cadre population, without a replacement draw"
        )
    for actor in result:
        sheet = source.sheets.get(actor.entity)
        if sheet is None or sheet.character_id != actor.incarnation:
            raise WorkflowError("Recover the actual original population's incarnations")
        # The immutable source roster/character IDs prove the historical population;
        # today's profile/controller is not substituted into an old selection.
    return result


def prove_selection(
    game: GameService, c: Connection, state: GameState, identity: str
) -> rules.Selection:
    value = _get(state, rules.Selection, identity)
    row = _row(game, c, value.work, first=True)
    event = _event(game, c, value.event)
    if (
        value.population != _population(game, c, row)
        or value.source_event != row["event_id"]
        or value.period != row["off_duty_id"]
        or value.handler != int(row["owner_id"])
        or value.index >= len(value.population)
        or value.actor != value.population[value.index]
        or value.id != rules.identity(game.store.campaign_id, value.work)
        or _get(_history(c, game, value.event), rules.Selection, identity) != value
        or event["kind"] != "m3.void_frame_entry_armed"
        or event["actor_id"] != str(value.handler)
    ):
        raise WorkflowError("Preserve the original once-only random Girl and actual source")
    return value


def prove_entry(game: GameService, c: Connection, state: GameState, identity: str) -> rules.Entry:
    value = _get(state, rules.Entry, identity)
    selection = prove_selection(game, c, state, value.selection)
    born = _get(_history(c, game, value.event), rules.Entry, identity)
    stable = (
        "id",
        "selection",
        "actor",
        "frame",
        "vessel",
        "before",
        "after",
        "event",
        "source_action",
    )
    if (
        any(getattr(value, key) != getattr(born, key) for key in stable)
        or value.actor != selection.actor
        or value.id != rules.identity("entry", selection.id)
        or value.before.actor != value.actor
        or value.after.actor != value.actor
        or occupied_frame(value.before) == (value.actor, value.frame)
        or occupied_frame(value.after) != (value.actor, value.frame)
        or value.before.mode != "outside_frame"
        or value.after.source_event != value.event
        or value.before.vessel_id != value.vessel
        or value.after.vessel_id != value.vessel
    ):
        raise WorkflowError("Recover this original Girl's genuine next own-Frame entry")
    before, after = _before(game, c, value.event), _history(c, game, value.event)
    if (
        next((x for x in before.placements if x.actor == value.actor), None) != value.before
        or next((x for x in after.placements if x.actor == value.actor), None) != value.after
    ):
        raise WorkflowError("Entry must match actual before/after physical placements")
    if value.ready_event:
        ready = _get(_history(c, game, value.ready_event), rules.Entry, identity)
        if ready.prerequisites != value.prerequisites:
            raise WorkflowError("Preserve the real entry's prior Void prerequisites")
    if value.cast is not None:
        saved = _get(_history(c, game, value.venue_event or value.event), rules.Entry, identity)
        if saved.cast != value.cast:
            raise WorkflowError(
                "Preserve the actual source venue, not an inferred controller scene"
            )
    if value.child is not None:
        child = game.action(c, value.child)
        if (
            child["data"]["prepared"]["play"] != "dive_deep"
            or child["actor_id"] != value.actor.entity
            or child["data"].get("prepared", {}).get("source_work") != value.id
            or child["data"].get("void_frame_entry", {}).get("entry") != value.id
        ):
            raise WorkflowError("Recover the original actual bound required Dive")
    if value.completed_event:
        finished = _get(_history(c, game, value.completed_event), rules.Entry, identity)
        if (
            finished.completed_event != value.completed_event
            or finished.child != value.child
            or _event(game, c, value.completed_event)["kind"] != "m3.void_frame_entry_completed"
        ):
            raise WorkflowError("Only the actual completed source event closes its owed Dive")
    return value


def stage_entry(
    game: GameService,
    c: Connection,
    before: GameState,
    after: GameState,
    actor: ActorRef,
    frame: str,
    event: str,
    *,
    channel: int | None = None,
    source_action: str | None = None,
) -> None:
    old = next((x for x in before.placements if x.actor == actor), None)
    new = next((x for x in after.placements if x.actor == actor), None)
    if (
        old is None
        or new is None
        or old.mode != "outside_frame"
        or occupied_frame(new) != (actor, frame)
        or new.source_event != event
        or old.vessel_id != new.vessel_id
    ):
        return
    selections = [
        value
        for value in rules.records(before, rules.Selection)
        if value.actor == actor
        and not any(x.selection == value.id for x in rules.records(after, rules.Entry))
    ]
    if not selections:
        return
    actual = resolve(
        after, actor, profiles(c, game.store.campaign_id), require_current_profile=False
    )
    if actual.frame_instance != frame:
        raise WorkflowError("The actual next entry must be into her own current Frame")
    physical = any(
        x.get("kind") == "physical_operation"
        and x.get("source_event") == event
        and x.get("actor") == actor.model_dump_json()
        and x.get("operation") in ("cockpit_enter", "cockpit_sit")
        for x in after.facts
    )
    if not physical and source_action is None:
        raise WorkflowError("SOURCE_ENTRY_PRODUCER_REQUIRED: use the genuine physical entry source")
    if source_action is not None:
        game.action(c, source_action)  # Real source Action, never a UI-created parent identifier.
    venue = None
    if channel is not None:
        try:
            venue = _cast(game, c, after, channel)
            if not any(
                role.actor == actor and role.controller == actual.controller for role in venue.roles
            ):
                venue = None
        except (ValueError, WorkflowError):
            venue = None
    for selection in selections:
        prove_selection(game, c, before, selection.id)
        rules.put(
            after,
            rules.Entry(
                id=rules.identity("entry", selection.id),
                selection=selection.id,
                actor=actor,
                frame=frame,
                vessel=new.vessel_id,
                before=old,
                after=new,
                event=event,
                source_action=source_action,
                cast=venue,
                venue_event=event if venue else None,
            ),
        )


def synchronize_entry(game: GameService, c: Connection, event: str) -> None:
    state = load_state(c, game.store.campaign_id)
    candidates = tuple(
        value
        for value in rules.records(state, rules.Entry)
        if value.event == event and value.ready_event is None
    )
    if not candidates:
        return
    for candidate in candidates:
        entry = prove_entry(game, c, state, candidate.id)
        work = t.m3["m3_required_work"]
        prerequisites = tuple(
            row["id"]
            for row in c.execute(
                sa.select(work).where(
                    work.c.campaign_id == game.store.campaign_id,
                    work.c.kind == "void_threshold",
                    work.c.revision == 1,
                    work.c.event_id == event,
                    work.c.subject_id == entry.actor.entity,
                )
            ).mappings()
            if json.loads(row["body_json"]).get("owner") == entry.actor.model_dump(mode="json")
        )
        actual_event = str(uuid4())
        entry = entry.model_copy(update=dict(ready_event=actual_event, prerequisites=prerequisites))
        rules.put(state, entry)
        author = _event(game, c, event)["actor_id"]
        game.event(
            c,
            author,
            "void-entry-ready:" + entry.id,
            "m3.void_frame_entry_ready",
            state,
            event_id=actual_event,
            entry=entry.id,
        )
        related(
            c,
            game.store,
            dict(campaign_id=game.store.campaign_id, campaign_context=True),
            entry.id,
            int(entry.actor.entity),
            int(entry.actor.entity),
            rules.WORK,
            dict(entry=entry.id, character=entry.actor.incarnation, immediate=True),
            actual_event,
        )
    from girlframe.services.p1_source_pause import reserve

    reserve(game, c, state)


def pause_sources(state: GameState) -> tuple[dict[str, str | int], ...]:
    return rules.pause_sources(state)


def _prerequisites(game: GameService, c: Connection, entry: rules.Entry) -> tuple[str, ...]:
    from girlframe.services.m3_void import source

    pending = []
    for identity in entry.prerequisites:
        first = _row(game, c, identity, first=True)
        row, body, actor = source(game, c, identity)
        if (
            first["event_id"] != entry.event
            or actor != entry.actor
            or body.get("reason") != "physical_entry"
        ):
            raise WorkflowError("Only this entry's genuine prior Void work is a prerequisite")
        if row["state"] != "resolved":
            pending.append(identity)
    return tuple(pending)


def prerequisite_source(
    game: GameService,
    c: Connection,
    state: GameState,
    prepared: PlayInput | None = None,
    action: dict[str, Any] | None = None,
) -> str | None:
    current = action
    work = (
        prepared.source_work
        if prepared
        else (current or {}).get("data", {}).get("prepared", {}).get("source_work")
    )
    play = (
        prepared.play
        if prepared
        else (current or {}).get("data", {}).get("prepared", {}).get("play")
    )
    parent = prepared.parent if prepared else (current or {}).get("parent_id")
    seen: set[str] = set()
    while True:
        if play == "keep_your_head" and work:
            for candidate in rules.due(state):
                if work in candidate.prerequisites:
                    entry = prove_entry(game, c, state, candidate.id)
                    _prerequisites(game, c, entry)
                    return entry.id
        if not parent or parent in seen:
            return None
        seen.add(parent)
        current = game.action(c, parent)
        play = current["data"]["prepared"]["play"]
        work = current["data"].get("prepared", {}).get("source_work")
        parent = current.get("parent_id")


def _current_actor(
    game: GameService, c: Connection, state: GameState, entry: rules.Entry
) -> ActorRef:
    from girlframe.services.m3_battle_dormant import actual_actor

    actor = actual_actor(game, c, state, entry.actor)
    if actor.kind != "pilot":
        raise WorkflowError(
            "SOURCE_ENTRY_HARPY_DIVE_REQUIRED: preserve the owed Dive "
            "through the actual Harpy source"
        )
    return actor


def prepare_child(
    game: GameService,
    c: Connection,
    viewer: GuildViewer,
    state: GameState,
    prepared: PlayInput,
    channel: int,
) -> dict[str, Any] | None:
    candidate = next(
        (value for value in rules.records(state, rules.Entry) if value.id == prepared.source_work),
        None,
    )
    if candidate is None:
        return None
    entry = prove_entry(game, c, state, candidate.id)
    actor = _current_actor(game, c, state, entry)
    if (
        viewer.user_id != int(entry.actor.entity)
        or prepared.play != "dive_deep"
        or prepared.parent != entry.source_action
        or entry.completed_event
        or entry.child
        or entry.cast is None
        or entry.cast.channel != channel
        or _prerequisites(game, c, entry)
    ):
        raise WorkflowError(
            "Finish actual prior Void work, then use this exact original required Dive"
        )
    actual = resolve(state, actor, profiles(c, game.store.campaign_id))
    if (
        actual.vessel_id != entry.vessel
        or actual.frame_instance != entry.frame
        or actual.occupied_frame_instance != entry.frame
        or actual.inside_frame is not True
        or fingerprint(_cast(game, c, state, channel)) != fingerprint(entry.cast)
    ):
        raise WorkflowError("Recover this original body's real entered Frame and source scene")
    from girlframe.services.p1_source_pause import require_ready

    require_ready(game, c, state, entry.id)
    return dict(
        entry=entry.id,
        selection=entry.selection,
        actor=actor.model_dump(mode="json"),
        original_actor=entry.actor.model_dump(mode="json"),
        frame=entry.frame,
        vessel=entry.vessel,
        channel=channel,
        parent=entry.source_action,
        source_event=entry.event,
    )


def bind_child(
    game: GameService, c: Connection, state: GameState, action: dict[str, Any], event: str
) -> None:
    meta = action["data"].get("void_frame_entry")
    if meta is None:
        return
    entry = prove_entry(game, c, state, meta["entry"])
    if (
        entry.child
        or entry.completed_event
        or action["actor_id"] != entry.actor.entity
        or action["data"]["prepared"]["play"] != "dive_deep"
        or action["data"].get("prepared", {}).get("source_work") != entry.id
        or meta.get("selection") != entry.selection
        or meta.get("frame") != entry.frame
        or meta.get("vessel") != entry.vessel
        or meta.get("source_event") != entry.event
    ):
        raise WorkflowError("This actual required Dive already has its original child")
    rules.put(state, entry.model_copy(update=dict(child=action["id"])))


def pre_roll(
    game: GameService, c: Connection, state: GameState, action: dict[str, Any], event: str
) -> list[dict[str, Any]]:
    meta = action["data"].get("void_frame_entry")
    if meta is None:
        return []
    entry = prove_entry(game, c, state, meta["entry"])
    if entry.child != action["id"] or entry.roll_event or _prerequisites(game, c, entry):
        raise WorkflowError(
            "Use the actual once-only source-required Dive and prior Void completion"
        )
    actor = _current_actor(game, c, state, entry)
    actual = resolve(state, actor, profiles(c, game.store.campaign_id))
    if (
        actual.frame_instance != entry.frame
        or actual.occupied_frame_instance != entry.frame
        or actual.vessel_id != entry.vessel
        or actual.inside_frame is not True
    ):
        raise WorkflowError("Preserve the actual original entered Frame before rolling")
    assets = tuple(
        value
        for value in effective_assets(state, actor)
        if value.family in ("girl", "frame") and value.void
    )
    value = rules.RollUse(
        id=rules.identity("roll", entry.id),
        entry=entry.id,
        action=action["id"],
        actor=actor,
        frame=entry.frame,
        assets=assets,
        amount=len(assets),
        event=event,
    )
    rules.put(state, value)
    rules.put(state, entry.model_copy(update=dict(roll_event=event)))
    return [dict(source=rules.MODIFIER, amount=value.amount)]


def prove_modifier(
    game: GameService, c: Connection, state: GameState, action: dict[str, Any]
) -> int | None:
    meta = action["data"].get("void_frame_entry")
    if meta is None:
        return None
    entry = prove_entry(game, c, state, meta["entry"])
    use = _get(state, rules.RollUse, rules.identity("roll", entry.id))
    row = _event(game, c, use.event)
    receipt = action["data"].get("receipt")
    saved = c.scalar(
        sa.select(t.m2["m2_receipts"].c.body_json).where(
            t.m2["m2_receipts"].c.campaign_id == game.store.campaign_id,
            t.m2["m2_receipts"].c.action_id == action["id"],
        )
    )
    if (
        row["kind"] not in ("m2.rolled", "m3.rolled")
        or not receipt
        or saved is None
        or json.loads(saved) != receipt
        or json.loads(row["payload_json"]).get("action_id") != action["id"]
        or json.loads(row["payload_json"]).get("receipt_id") != receipt["id"]
        or use.action != action["id"]
        or entry.child != action["id"]
        or use.event != entry.roll_event
        or use.amount != len(use.assets)
        or _get(_history(c, game, use.event), rules.RollUse, use.id) != use
        or [x for x in receipt.get("pre_modifiers", ()) if x["source"] == rules.MODIFIER]
        != [dict(source=rules.MODIFIER, amount=use.amount)]
    ):
        raise WorkflowError(
            "Recover the real additive Void-Asset modifier and ordinary Heat receipt"
        )
    before = _before(game, c, use.event)
    assets = tuple(
        value
        for value in effective_assets(before, use.actor)
        if value.family in ("girl", "frame") and value.void
    )
    if assets != use.assets or use.frame != entry.frame:
        raise WorkflowError("Preserve actual still-owned Void Assets, not a substituted roll basis")
    return use.amount


def source_for_play(
    game: GameService,
    c: Connection,
    state: GameState,
    prepared: PlayInput | None = None,
    action: dict[str, Any] | None = None,
) -> str | None:
    work = (
        prepared.source_work
        if prepared
        else (action or {}).get("data", {}).get("prepared", {}).get("source_work")
    )
    for candidate in rules.due(state):
        play = (
            prepared.play
            if prepared
            else (action or {}).get("data", {}).get("prepared", {}).get("play")
        )
        if work == candidate.id and play == "dive_deep":
            prove_entry(game, c, state, candidate.id)
            return candidate.id
    parent = prepared.parent if prepared else (action or {}).get("id")
    seen: set[str] = set()
    while parent and parent not in seen:
        seen.add(parent)
        actual = game.action(c, parent)
        meta = actual["data"].get("void_frame_entry")
        if meta is not None:
            entry = prove_entry(game, c, state, meta["entry"])
            if entry.child == actual["id"]:
                return entry.id
        parent = actual.get("parent_id")
    return None


def require_pending(
    game: GameService,
    c: Connection,
    state: GameState,
    viewer: GuildViewer,
    prepared: PlayInput | None = None,
    *,
    actor: ActorRef | None = None,
) -> None:
    due = [
        value
        for value in rules.due(state)
        if value.actor == actor or actor is None and value.actor.entity == str(viewer.user_id)
    ]
    if due and not (
        source_for_play(game, c, state, prepared=prepared)
        or prerequisite_source(game, c, state, prepared=prepared)
    ):
        raise WorkflowError(
            "REQUIRED_FRAME_ENTRY_DIVE: finish the original entry's actual consequences"
        )


def release_unrolled(
    game: GameService, c: Connection, state: GameState, action: dict[str, Any], event: str
) -> None:
    meta = action["data"].get("void_frame_entry")
    if meta is None:
        return
    entry = prove_entry(game, c, state, meta["entry"])
    if entry.child != action["id"] or entry.roll_event or action["data"].get("receipt"):
        raise WorkflowError("Known source-required Dive must resume with its original receipt")
    rules.put(state, entry.model_copy(update=dict(child=None)))


def synchronize_action(
    game: GameService, c: Connection, action: dict[str, Any], event: str
) -> None:
    meta = action["data"].get("void_frame_entry")
    if meta is None or action["state"] != "complete" or game.pending(c, action["id"]):
        return
    state = load_state(c, game.store.campaign_id)
    entry = prove_entry(game, c, state, meta["entry"])
    if entry.completed_event:
        return
    prove_modifier(game, c, state, action)
    work = t.m3["m3_required_work"]
    rows = c.execute(
        sa.select(work)
        .where(work.c.campaign_id == game.store.campaign_id)
        .order_by(work.c.revision)
    ).mappings()
    latest = {row["id"]: row for row in rows}
    followups = {item["id"] for item in action["data"].get("dive", {}).get("followups", ())}
    followups.update(
        row["id"]
        for row in latest.values()
        if json.loads(row["body_json"]).get("source_action") == action["id"]
    )
    while True:
        children = {
            row["id"]
            for row in latest.values()
            if json.loads(row["body_json"]).get("source_work") in followups
        }
        if children <= followups:
            break
        followups |= children
    if any(
        identity not in latest or latest[identity]["state"] != "resolved" for identity in followups
    ):
        return
    actual = str(uuid4())
    rules.put(state, entry.model_copy(update=dict(completed_event=actual)))
    game.event(
        c,
        action["actor_id"],
        "void-entry-complete:" + entry.id,
        "m3.void_frame_entry_completed",
        state,
        event_id=actual,
        entry=entry.id,
        source_event=event,
        action_id=action["id"],
    )
    row = _row(game, c, entry.id)
    _append(
        c,
        row,
        actual,
        json.loads(row["body_json"]) | dict(action=action["id"], completed=True),
        resolved=True,
    )


class VoidFrameEntryService:
    def __init__(self, strain: StrainService, *, selector: IndexSource | None = None):
        self.strain, self.game, self.store = strain, strain.game, strain.store
        self.selector = selector if selector is not None else OsIndex()

    def arm(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        game_revision: int,
        account: str,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            row = _row(self.game, c, identity)
            self.strain._check(c, viewer, row, revision)
            state = self.strain._state(c, game_revision)
            if (
                not account.strip()
                or len(account) > 1200
                or any(value.work == identity for value in rules.records(state, rules.Selection))
            ):
                raise WorkflowError("Arm this actual future source once, without redrawing")
            population = _population(self.game, c, _row(self.game, c, identity, first=True))
            index = self.selector.choose(len(population))
            if type(index) is not int or not 0 <= index < len(population):
                raise WorkflowError("Use a genuine uniform index in the original population")
            event = str(uuid4())
            first = _row(self.game, c, identity, first=True)
            value = rules.Selection(
                id=rules.identity(self.store.campaign_id, identity),
                work=identity,
                source_event=first["event_id"],
                period=row["off_duty_id"],
                handler=viewer.user_id,
                population=population,
                index=index,
                actor=population[index],
                rng_source="os" if isinstance(self.selector, OsIndex) else "test_injected",
                account=account,
                event=event,
            )
            rules.put(state, value)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.void_frame_entry_armed",
                state,
                event_id=event,
                selection=value.id,
                work_id=identity,
            )
            self.strain._save(
                c,
                row,
                event,
                json.loads(row["body_json"]) | dict(selection=value.id),
                resolved=True,
            )
            return dict(
                id=value.id,
                actor=value.actor.model_dump(mode="json"),
                rng_source=value.rng_source,
                population_size=len(population),
                game_revision=state.revision,
            )

        def authorize(c: Connection) -> None:
            self.strain._authorize(c, viewer)
            assert self.strain.missions.access.registry is not None
            self.strain.missions.access.registry.require_available(rules.RULE)

        return self.store._write(
            viewer,
            key,
            "m3.void_frame_entry_armed",
            dict(id=identity, revision=revision, game_revision=game_revision, account=account),
            operation,
            auto_audit=False,
            authorize=authorize,
        )

    def bind_venue(
        self, viewer: GuildViewer, key: str, identity: str, revision: int, channel: int
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            Access(self.store).authorize(c, viewer, "plays", director_response=True)
            self.game.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            entry = prove_entry(self.game, c, state, identity)
            if (
                state.revision != revision
                or entry.cast is not None
                or entry.completed_event
                or viewer.user_id != int(entry.actor.entity)
            ):
                raise WorkflowError(
                    "Only the original affected owner binds the actual missing venue"
                )
            scene = _cast(self.game, c, state, channel)
            if not any(
                role.actor == entry.actor and role.controller == viewer.user_id
                for role in scene.roles
            ):
                raise WorkflowError(
                    "Join your actual original role in the real required-Dive scene"
                )
            event = str(uuid4())
            rules.put(state, entry.model_copy(update=dict(cast=scene, venue_event=event)))
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.void_frame_entry_venue",
                state,
                event_id=event,
                entry=entry.id,
            )
            from girlframe.services.p1_source_pause import reserve

            reserve(self.game, c, state)
            return dict(id=entry.id, revision=state.revision)

        return self.store._write(
            viewer,
            key,
            "m3.void_frame_entry_venue",
            dict(id=identity, revision=revision, channel=channel),
            operation,
            auto_audit=False,
        )

    def _tasks(self, c: Connection, viewer: GuildViewer) -> list[dict[str, Any]]:
        state = load_state(c, self.store.campaign_id)
        result = []
        for value in rules.records(state, rules.Selection):
            if viewer.user_id not in (value.handler, int(value.actor.entity)):
                continue
            entry = next(
                (x for x in rules.records(state, rules.Entry) if x.selection == value.id), None
            )
            result.append(
                dict(
                    id=entry.id if entry else value.id,
                    revision=state.revision,
                    label="Next-Frame-entry required Dive",
                    phase="pending" if entry and not entry.completed_event else "resolved",
                    pending=bool(
                        entry
                        and not entry.completed_event
                        and viewer.user_id == int(value.actor.entity)
                    ),
                )
            )
        return result

    def view(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            state = load_state(c, self.store.campaign_id)
            entry = next((x for x in rules.records(state, rules.Entry) if x.id == identity), None)
            selected = next(
                (
                    x
                    for x in rules.records(state, rules.Selection)
                    if x.id == (entry.selection if entry else identity)
                ),
                None,
            )
            if selected is None:
                row = _row(self.game, c, identity)
                if row["owner_id"] != str(viewer.user_id):
                    raise WorkflowError("Only the actual Handler reads the pending Strain source")
                _population(self.game, c, _row(self.game, c, identity, first=True))
                return dict(
                    id=identity,
                    type="arm",
                    revision=row["revision"],
                    game_revision=state.revision,
                    state=row["state"],
                )
            if viewer.user_id not in (selected.handler, int(selected.actor.entity)):
                raise WorkflowError(
                    "Only the original source Handler and affected person read this"
                )
            selected = prove_selection(self.game, c, state, selected.id)
            result: dict[str, Any] = dict(
                id=identity,
                type="selected",
                revision=state.revision,
                account=selected.account,
                actor=selected.actor.model_dump(mode="json"),
                population_size=len(selected.population),
                state="awaiting actual next own-Frame entry",
            )
            if entry is None:
                return result
            entry = prove_entry(self.game, c, state, entry.id)
            gap = None
            if not entry.completed_event:
                try:
                    _current_actor(self.game, c, state, entry)
                except (ValueError, WorkflowError) as error:
                    gap = str(error)
            pending = _prerequisites(self.game, c, entry) if not entry.completed_event else ()
            from girlframe.services.p1_source_pause import projection

            choices = (
                [row["id"] for row in self.game.choices(viewer) if row["action_id"] == entry.child]
                if entry.child
                else []
            )
            return result | dict(
                type="entry",
                state="complete" if entry.completed_event else "required",
                entry=entry.id,
                frame=entry.frame,
                child=entry.child,
                prerequisites=pending,
                gap=gap,
                choices=choices,
                can_bind=viewer.user_id == int(entry.actor.entity)
                and entry.cast is None
                and not entry.completed_event,
                pause=projection(self.game, c, entry.id) if entry.cast else None,
                child_descriptor=dict(
                    kind="void_frame_entry_child",
                    actor=entry.actor.model_dump(mode="json"),
                    channel=entry.cast.channel if entry.cast else None,
                    parent=entry.source_action,
                    body=dict(source_work=entry.id, allowed=["dive_deep"]),
                )
                if (
                    entry.cast
                    and not pending
                    and not gap
                    and not entry.completed_event
                    and entry.child is None
                    and viewer.user_id == int(entry.actor.entity)
                )
                else None,
            )
