"""Canonical mark/removal receipts and actual mandatory OffDuty Tag rebuilding."""

import json
from typing import Any
from uuid import NAMESPACE_URL, uuid4, uuid5

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_disposable_psyche as rules
from girlframe.engine.m2 import GameState, PlayInput, mark_identity, spend_heat
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_girl_runtime_state import has_rule
from girlframe.engine.m3_policy import RULESET
from girlframe.services.m2_choices import ChoiceEngine
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_handler_advancements import _history
from girlframe.services.m3_play_support import periods
from girlframe.services.m3_work import related
from girlframe.services.onboarding import OnboardingStore, WorkflowError
from girlframe.services.read_only_bot import GuildViewer


def _gate(game: GameService) -> None:
    registry = Access(game.store).registry
    if registry is None:
        raise WorkflowError("M3_REVIEW_PENDING: Disposable Psyche requires actual source release")
    registry.require_available(rules.RULE)


def prepare_disposal(
    game: GameService, c: Connection, state: GameState, owner: int, prepared: PlayInput
) -> None:
    if not prepared.disposable_heat:
        return
    _gate(game)
    if prepared.parent and game.action(c, prepared.parent)["data"].get("princess_sex"):
        raise WorkflowError(
            "SOURCE_DISPOSAL_AUTHOR_REQUIRED: retain the actual Princess child author"
        )
    actor = current_ref(state, owner)
    sheet = state.sheets[actor.entity]
    identity = next((x for x in sheet.identities if x.id == prepared.identity), None)
    if identity is None:
        raise WorkflowError(
            "SOURCE_CLONE_DISPOSAL_REQUIRED: remove only an original native Identity"
        )
    rules.admit_removal(state, sheet, identity)
    from girlframe.engine.m3_ankou_feedback import RULE as feedback_rule
    from girlframe.engine.m3_ankou_feedback import final_mark

    if final_mark(state, sheet, identity.id):
        registry = Access(game.store).registry
        if registry is None:
            raise WorkflowError("SOURCE_ANKOU_FEEDBACK_REQUIRED: release the actual consumer")
        registry.require_available(feedback_rule)


def prepare_off_duty(game: GameService, state: GameState, owner: int) -> None:
    sheet = state.sheets.get(str(owner))
    if sheet is not None and has_rule(sheet, rules.RULE, "STIM-BLISSED"):
        _gate(game)


def record_disposal(
    game: GameService,
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    before: GameState,
    event: str,
) -> None:
    prepared = PlayInput.model_validate_json(json.dumps(action["data"]["prepared"]))
    if not prepared.disposable_heat:
        return
    if action["data"].get("ankou_feedback"):
        link_feedback_disposal(game, c, state, action, event)
        return
    owner = int(action["actor_id"])
    prepare_disposal(game, c, before, owner, prepared)
    actor = current_ref(before, owner)
    original = before.sheets[actor.entity]
    identity = next(x for x in original.identities if x.id == prepared.identity)
    expected = GameState.model_validate_json(before.model_dump_json())
    sheet = expected.sheets[actor.entity]
    mark_identity(
        sheet,
        identity.id,
        prepared.gain,
        prepared.pair_share,
        state=expected,
        disposable_heat=prepared.disposable_heat,
    )
    spend_heat(sheet, prepared.heat)
    actual = state.sheets[actor.entity]
    if actual.identities != sheet.identities or actual.heat != sheet.heat:
        raise WorkflowError("Retain the original actual Identity removal and complete Heat debit")
    rules.put(
        state,
        rules.Disposal(
            id=action["id"],
            actor=actor,
            identity=identity.model_copy(deep=True),
            gain=prepared.gain,
            extra=prepared.disposable_heat,
            heat_before=original.heat,
            heat_after=actual.heat,
            spent=prepared.heat,
            receipt=action["data"]["receipt"]["id"],
            event=event,
        ),
    )


def _before(game: GameService, c: Connection, event: str) -> GameState:
    sequence = c.scalar(
        sa.select(t.events.c.seq).where(
            t.events.c.campaign_id == game.store.campaign_id, t.events.c.id == event
        )
    )
    if sequence is None:
        raise WorkflowError("Recover the actual immutable source event")
    history = t.m2["m2_state_history"]
    body = c.scalar(
        sa.select(history.c.body_json)
        .join(t.events, history.c.event_id == t.events.c.id)
        .where(history.c.campaign_id == game.store.campaign_id, t.events.c.seq < sequence)
        .order_by(t.events.c.seq.desc())
        .limit(1)
    )
    if body is None:
        raise WorkflowError("Recover the actual pre-source original state")
    return GameState.model_validate_json(body)


def prove_disposal(
    game: GameService, c: Connection, state: GameState, identity: str
) -> rules.Disposal:
    value = next((x for x in rules.disposals(state) if x.id == identity), None)
    if value is None:
        raise WorkflowError("Recover the actual Disposable Psyche removal")
    action = game.action(c, value.id)
    if value.commit_event:
        return prove_feedback_disposal(game, c, state, value, action)
    before, born = _before(game, c, value.event), _history(c, game, value.event)
    event = (
        c.execute(
            sa.select(t.events).where(
                t.events.c.campaign_id == game.store.campaign_id, t.events.c.id == value.event
            )
        )
        .mappings()
        .one()
    )
    receipt = (
        c.execute(
            sa.select(t.m2["m2_receipts"]).where(
                t.m2["m2_receipts"].c.campaign_id == game.store.campaign_id,
                t.m2["m2_receipts"].c.action_id == value.id,
            )
        )
        .mappings()
        .first()
    )
    if (
        value not in rules.disposals(born)
        or receipt is None
        or receipt["id"] != value.receipt
        or json.loads(receipt["body_json"]) != action["data"].get("receipt")
        or event["kind"] != "m3.rolled"
        or action["data"]["receipt"].get("ruleset") != RULESET
        or action["data"]["receipt"].get("disposable_psyche") != value.id
        or event["actor_id"] != str(action["actor_id"])
        or json.loads(event["payload_json"]).get("action_id") != value.id
        or json.loads(event["payload_json"]).get("receipt_id") != value.receipt
        or value.actor != current_ref(before, int(action["actor_id"]))
    ):
        raise WorkflowError("Recover the actual original mark/removal and roll receipt")
    scratch = GameState.model_validate_json(born.model_dump_json())
    scratch.facts = [
        x
        for x in scratch.facts
        if not (x.get("kind") == "disposable_disposal" and x.get("id") == value.id)
    ]
    record_disposal(game, c, scratch, action, before, value.event)
    if next(x for x in rules.disposals(scratch) if x.id == value.id) != value:
        raise WorkflowError("Recover the exact original removed Identity and additional Heat")
    return value


def record_committed_disposal(
    game: GameService,
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    before: GameState,
    event: str,
) -> None:
    """A real Feedback mark is durable before any dice or later purpose/Asset changes."""
    prepared = PlayInput.model_validate_json(json.dumps(action["data"]["prepared"]))
    if not prepared.disposable_heat:
        return
    from girlframe.engine.m3_ankou_feedback import get

    value = get(state, action["data"]["ankou_feedback"])
    owner = int(action["actor_id"])
    original = before.sheets[str(owner)]
    entry = next(x for x in original.identities if x.id == prepared.identity)
    if (
        value.mark_event != event
        or value.action != action["id"]
        or value.prepared != prepared
        or value.identity != entry
        or any(x.id == entry.id for x in state.sheets[str(owner)].identities)
    ):
        raise WorkflowError("Record only the actual source-bound Ankou Identity removal")
    rules.put(
        state,
        rules.Disposal(
            id=action["id"],
            actor=value.actor,
            identity=entry.model_copy(deep=True),
            gain=prepared.gain,
            extra=prepared.disposable_heat,
            heat_before=original.heat,
            heat_after=state.sheets[str(owner)].heat,
            spent=prepared.heat,
            receipt=None,
            event=event,
            commit_event=event,
        ),
    )


def prove_feedback_disposal(
    game: GameService,
    c: Connection,
    state: GameState,
    value: rules.Disposal,
    action: dict[str, Any],
) -> rules.Disposal:
    from girlframe.services.m3_ankou_feedback import prove

    source = prove(game, c, state, action["data"].get("ankou_feedback", ""))
    born = next(
        (x for x in rules.disposals(_history(c, game, source.mark_event)) if x.id == value.id), None
    )
    fixed = tuple(k for k in rules.Disposal.model_fields if k not in ("receipt", "roll_event"))
    if (
        born is None
        or any(getattr(born, k) != getattr(value, k) for k in fixed)
        or value.commit_event != source.mark_event
        or value.event != source.mark_event
        or value.identity != source.identity
        or value.actor != source.actor
        or value.heat_after != source.heat_committed
        or value.heat_before != source.heat_before
        or born.receipt is not None
        or born.roll_event is not None
    ):
        raise WorkflowError(
            "Preserve the immutable actual pre-RNG removal and original Heat commitment"
        )
    if value.receipt is None:
        if value.roll_event is not None or source.rolled_event is not None:
            raise WorkflowError("Recover the actual later receipt linkage")
        return value
    if (
        value.roll_event != source.rolled_event
        or value.receipt != source.receipt
        or action["data"].get("receipt", {}).get("disposable_psyche") != value.id
    ):
        raise WorkflowError(
            "Prove the actual later roll, without replaying pre-Feedback resource changes"
        )
    return value


def link_feedback_disposal(
    game: GameService,
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    event: str,
) -> None:
    value = next((x for x in rules.disposals(state) if x.id == action["id"]), None)
    if value is None:
        raise WorkflowError("Recover the genuine earlier Feedback removal")
    prove_feedback_disposal(game, c, state, value, action)
    receipt = action["data"].get("receipt")
    if (
        value.receipt
        or value.roll_event
        or not receipt
        or receipt.get("disposable_psyche") != value.id
    ):
        raise WorkflowError("Link one actual post-Feedback roll to the original mark commitment")
    linked = value.model_copy(update=dict(receipt=receipt["id"], roll_event=event))
    state.facts = [
        x
        for x in state.facts
        if not (x.get("kind") == "disposable_disposal" and x.get("id") == value.id)
    ]
    rules.put(state, linked)


def _latest(c: Connection, game: GameService, identity: str) -> dict[str, Any]:
    work = t.m3["m3_required_work"]
    row = (
        c.execute(
            sa.select(work)
            .where(
                work.c.campaign_id == game.store.campaign_id,
                work.c.id == identity,
                work.c.kind == rules.KIND,
            )
            .order_by(work.c.revision.desc())
            .limit(1)
        )
        .mappings()
        .first()
    )
    if row is None:
        raise WorkflowError("Recover the genuine original Disposable Psyche OffDuty work")
    return dict(row)


def sync_off_duty(game: GameService, c: Connection, action: dict[str, Any], event: str) -> None:
    meta = action["data"].get("m3")
    if meta is None or action["data"]["play"] not in ("go_off_duty", "void_observation"):
        return
    state = load_state(c, game.store.campaign_id)
    owner = int(action["actor_id"])
    actor = current_ref(state, owner)
    sheet = state.sheets[actor.entity]
    if not has_rule(sheet, rules.RULE, "STIM-BLISSED"):
        return
    prepare_off_duty(game, state, owner)
    period = periods(game)._get(c, meta["period_id"])
    progress = period.progress.get(str(owner))
    if progress is None or progress.roll is None or progress.roll.stage != "choices":
        return
    if (
        progress.action_id != action["id"]
        or period.character_ids.get(str(owner)) != actor.incarnation
    ):
        raise WorkflowError("Retain the original actual OffDuty Girl and roll")
    identity = str(uuid5(NAMESPACE_URL, "disposable-off-duty:" + period.id + ":" + actor.token))
    work = t.m3["m3_required_work"]
    if c.scalar(
        sa.select(work.c.id).where(
            work.c.campaign_id == game.store.campaign_id, work.c.id == identity
        )
    ):
        return
    trigger = rules.Trigger(
        id=identity,
        actor=actor,
        period=period.id,
        action=action["id"],
        event=event,
        tags=tuple(x.id for x in sheet.tags),
    )
    related(
        c,
        game.store,
        dict(campaign_id=game.store.campaign_id, off_duty_id=period.id),
        identity,
        owner,
        owner,
        rules.KIND,
        dict(trigger=trigger.model_dump(mode="json")),
        event,
    )
    if not trigger.tags:
        row = _latest(c, game, identity)
        _resolve(c, game, row, event, dict(no_available_tags=True))


def _resolve(
    c: Connection, game: GameService, row: dict[str, Any], event: str, extra: dict[str, Any]
) -> None:
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
            event_id=event,
            body_json=json.dumps(json.loads(row["body_json"]) | extra, sort_keys=True),
        )
    )


def _prove_trigger(game: GameService, c: Connection, row: dict[str, Any]) -> rules.Trigger:
    value = rules.Trigger.model_validate_json(json.dumps(json.loads(row["body_json"])["trigger"]))
    source = _history(c, game, value.event)
    action = game.action(c, value.action)
    event = (
        c.execute(
            sa.select(t.events).where(
                t.events.c.campaign_id == game.store.campaign_id, t.events.c.id == value.event
            )
        )
        .mappings()
        .first()
    )
    source_choices = list(
        c.execute(
            sa.select(t.m2["m2_choices"].c.kind).where(
                t.m2["m2_choices"].c.campaign_id == game.store.campaign_id,
                t.m2["m2_choices"].c.action_id == value.action,
                t.m2["m2_choices"].c.state == "pending",
            )
        ).scalars()
    )
    payload = json.loads(event["payload_json"]) if event else {}
    choice = (
        c.execute(
            sa.select(t.m2["m2_choices"]).where(
                t.m2["m2_choices"].c.campaign_id == game.store.campaign_id,
                t.m2["m2_choices"].c.id == payload.get("choice_id"),
            )
        )
        .mappings()
        .first()
    )
    response = (
        c.execute(
            sa.select(t.m2["m2_responses"]).where(
                t.m2["m2_responses"].c.campaign_id == game.store.campaign_id,
                t.m2["m2_responses"].c.choice_id == payload.get("choice_id"),
            )
        )
        .mappings()
        .first()
    )
    receipt = (
        c.execute(
            sa.select(t.m2["m2_receipts"]).where(
                t.m2["m2_receipts"].c.campaign_id == game.store.campaign_id,
                t.m2["m2_receipts"].c.action_id == value.action,
            )
        )
        .mappings()
        .first()
    )
    if (
        choice is None
        or response is None
        or receipt is None
        or event is None
        or choice["action_id"] != value.action
        or choice["kind"] not in ("tag_window", "tag_resolution", "tag_marker_agreement")
        or response["event_id"] != value.event
        or response["actor_id"] != event["actor_id"]
        or response["actor_id"] != choice["actor_id"]
        or json.loads(receipt["body_json"]) != action["data"].get("receipt")
    ):
        raise WorkflowError(
            "Recover the actual completed Tag response and original OffDuty receipt"
        )
    first = (
        c.execute(
            sa.select(t.m3["m3_required_work"]).where(
                t.m3["m3_required_work"].c.campaign_id == game.store.campaign_id,
                t.m3["m3_required_work"].c.id == row["id"],
                t.m3["m3_required_work"].c.revision == 1,
            )
        )
        .mappings()
        .first()
    )
    if (
        first is None
        or first["event_id"] != value.event
        or json.loads(first["body_json"]).get("trigger") != value.model_dump(mode="json")
        or value.id != row["id"]
        or row["off_duty_id"] != value.period
        or row["owner_id"] != value.actor.entity
        or row["subject_id"] != value.actor.entity
        or event is None
        or event["kind"] not in ("m2.choice_resolved", "m3.choice_resolved")
        or json.loads(event["payload_json"]).get("action_id") != value.action
        or action["data"]["play"] not in ("go_off_duty", "void_observation")
        or action["data"].get("m3", {}).get("period_id") != value.period
        or not action["data"].get("receipt")
        or any(
            x in ("tag_window", "tag_resolution", "tag_marker_agreement") for x in source_choices
        )
        or value.actor != current_ref(source, int(action["actor_id"]))
        or tuple(x.id for x in source.sheets[value.actor.entity].tags) != value.tags
        or not has_rule(source.sheets[value.actor.entity], rules.RULE, "STIM-BLISSED")
    ):
        raise WorkflowError(
            "Recover the immutable actual GoOffDuty trigger, original Tags and owner"
        )
    return value


def prove_conversion(
    game: GameService, c: Connection, state: GameState, identity: str
) -> rules.Conversion:
    value = next((x for x in rules.conversions(state) if x.id == identity), None)
    if value is None:
        raise WorkflowError("Recover the actual source-owned Tag conversion")
    row = _latest(c, game, identity)
    trigger = _prove_trigger(game, c, row)
    before, born = _before(game, c, value.event), _history(c, game, value.event)
    event = (
        c.execute(
            sa.select(t.events).where(
                t.events.c.campaign_id == game.store.campaign_id, t.events.c.id == value.event
            )
        )
        .mappings()
        .first()
    )
    expected, tags, replaced, created = rules.convert(
        before.sheets[trigger.actor.entity], value.selections, identity
    )
    if (
        value not in rules.conversions(born)
        or value.trigger != trigger
        or value.tags != tags
        or value.replaced != replaced
        or value.created != created
        or event is None
        or event["kind"] != "m3.disposable_psyche_converted"
        or event["actor_id"] != trigger.actor.entity
        or row["state"] != "resolved"
        or row["event_id"] != value.event
        or json.loads(row["body_json"]).get("conversion") != value.id
        or born.sheets[trigger.actor.entity] != expected
    ):
        raise WorkflowError(
            "Recover the actual original Tags, slots, Identity result and resolved work"
        )
    _check_tags(game, c, before, trigger, value.selections)
    return value


def _check_tags(
    game: GameService,
    c: Connection,
    state: GameState,
    trigger: rules.Trigger,
    selections: tuple[rules.TagSelection, ...],
) -> None:
    sheet = state.sheets.get(trigger.actor.entity)
    if sheet is None or current_ref(state, int(trigger.actor.entity)) != trigger.actor:
        raise WorkflowError(
            "Recover the actual original Girl rather than transfer her rebuilding work"
        )
    for selection in selections:
        if selection.tag not in trigger.tags:
            raise WorkflowError("Choose a real original Tag present at this GoOffDuty source")
        tag = next((x for x in sheet.tags if x.id == selection.tag), None)
        if tag is None:
            raise WorkflowError("Recover the actual source Tag instead of inventing an Identity")
        ChoiceEngine(game).prove_tag_setter(c, state, sheet.owner, tag)
        if tag.rejection_pending or any(
            x.state == "pending"
            and x.details.get("tag") == tag.id
            and (
                x.owner == sheet.owner or x.details.get("actor") == trigger.actor.model_dump_json()
            )
            for x in state.obligations
        ):
            raise WorkflowError("Complete the actual owed Tag work; rebuilding cannot erase it")


class PsycheService:
    def __init__(self, store: OnboardingStore, game: GameService | None = None):
        self.store, self.game = store, game or GameService(store)

    def _tasks(self, c: Connection, viewer: GuildViewer) -> list[dict[str, Any]]:
        work = t.m3["m3_required_work"]
        rows = {
            x["id"]: dict(x)
            for x in c.execute(
                sa.select(work)
                .where(
                    work.c.campaign_id == self.store.campaign_id,
                    work.c.kind == rules.KIND,
                    work.c.subject_id == str(viewer.user_id),
                )
                .order_by(work.c.revision)
            ).mappings()
        }
        state = load_state(c, self.store.campaign_id)
        return [
            dict(
                id=x.id,
                revision=state.revision,
                phase="removed",
                pending=False,
                label="Your removed Identity and actual additional Heat",
            )
            for x in rules.disposals(state)
            if x.actor.entity == str(viewer.user_id)
        ] + [
            dict(
                id=x["id"],
                revision=state.revision,
                phase="pending"
                if x["state"] != "resolved"
                else "converted"
                if json.loads(x["body_json"]).get("conversion")
                else "no_tags",
                pending=x["state"] != "resolved",
                label="Your Disposable Psyche Tag rebuilding",
            )
            for x in rows.values()
        ]

    def menu(self, viewer: GuildViewer) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            return dict(tasks=self._tasks(c, viewer))

    def view(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            state = load_state(c, self.store.campaign_id)
            removed = next((x for x in rules.disposals(state) if x.id == identity), None)
            if removed is not None:
                value = prove_disposal(self.game, c, state, identity)
                if value.actor.entity != str(viewer.user_id):
                    raise WorkflowError(
                        "Only the original owner reads this private Identity source"
                    )
                return dict(
                    id=identity,
                    revision=state.revision,
                    phase="removed",
                    identity=value.identity.name,
                    gain=value.gain,
                    extra=value.extra,
                    spent=value.spent,
                    heat_after=value.heat_after,
                )
            row = _latest(c, self.game, identity)
            trigger = _prove_trigger(self.game, c, row)
            if trigger.actor.entity != str(viewer.user_id):
                raise WorkflowError("Only the original owner reads her private Tag rebuilding")
            if row["state"] == "resolved":
                if json.loads(row["body_json"]).get("no_available_tags"):
                    if trigger.tags:
                        raise WorkflowError(
                            "The original source did have Tags; finish actual conversion"
                        )
                    return dict(
                        id=identity, revision=state.revision, phase="no_tags", identities=[]
                    )
                converted = prove_conversion(self.game, c, state, identity)
                return dict(
                    id=identity,
                    revision=state.revision,
                    phase="converted",
                    identities=[x.name for x in converted.created],
                    tags=[x.label for x in converted.tags],
                )
            if current_ref(state, viewer.user_id) != trigger.actor:
                raise WorkflowError("Explicitly recover the ended original Girl's pending source")
            sheet = state.sheets[trigger.actor.entity]
            return dict(
                id=identity,
                revision=state.revision,
                phase="pending",
                tags=[
                    dict(id=x.id, label=x.label, marked=x.marked)
                    for x in sheet.tags
                    if x.id in trigger.tags
                ],
                identities=[
                    dict(id=x.id, label=x.name)
                    for x in sheet.identities
                    if not x.protected
                    and not x.paired
                    and not x.am_limiter
                    and x.id not in sheet.sedation_locked
                    and not x.obsession_sources
                ],
                count=len(
                    [x for x in sheet.identities if not x.protected or x.paired or x.am_limiter]
                ),
            )

    def convert(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        expected: int,
        selections: tuple[rules.TagSelection, ...],
    ) -> dict[str, Any]:
        selections = tuple(
            rules.TagSelection.model_validate_json(x.model_dump_json()) for x in selections
        )

        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            _gate(self.game)
            state = load_state(c, self.store.campaign_id)
            row = _latest(c, self.game, identity)
            trigger = _prove_trigger(self.game, c, row)
            if (
                trigger.actor.entity != str(viewer.user_id)
                or row["state"] == "resolved"
                or state.revision != expected
            ):
                raise WorkflowError("Use only your current original pending rebuilding source")
            period = periods(self.game)._get(c, trigger.period)
            if period.phase != "active" or period.progress[str(viewer.user_id)].recovered:
                raise WorkflowError("Complete this actual GoOffDuty rebuilding before recovery")
            _check_tags(self.game, c, state, trigger, selections)
            sheet, tags, replaced, created = rules.convert(
                state.sheets[trigger.actor.entity], selections, identity
            )
            event = str(uuid4())
            value = rules.Conversion(
                id=identity,
                trigger=trigger,
                selections=selections,
                tags=tags,
                replaced=replaced,
                created=created,
                event=event,
            )
            state.sheets[trigger.actor.entity] = sheet
            rules.put(state, value)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.disposable_psyche_converted",
                state,
                event_id=event,
                work=identity,
            )
            _resolve(c, self.game, row, event, dict(conversion=identity))
            return dict(id=identity, identities=[x.id for x in created])

        return self.store._write(
            viewer,
            key,
            "m3.disposable_psyche_converted",
            dict(
                work=identity,
                expected=expected,
                selections=[x.model_dump(mode="json") for x in selections],
            ),
            operation,
            auto_audit=False,
            authorize=lambda c: self.game.authorize(c, viewer, game=False),
        )
