"""Owner-authored ordinary intoxication Tag, backed by its actual original Play."""

import json
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_malleable as rules
from girlframe.engine.m2 import GameState, TagState
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_girl_runtime_state import has_rule
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_handler_advancements import _history
from girlframe.services.m3_malleable import _access, _audit, _giver
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer


def same_tag(left: TagState, right: TagState) -> bool:
    return left.model_dump(
        exclude={"marked", "scene_used", "rejection_pending"}
    ) == right.model_dump(exclude={"marked", "scene_used", "rejection_pending"})


def origin(
    game: GameService, c: Connection, state: GameState, person: int, tag: TagState
) -> tuple[str, str]:
    """Finite ordinary producers: original Beneath or target-authored owed Flirt Tag."""
    actor = current_ref(state, person)
    history = t.m2["m2_state_history"]
    rows = c.execute(
        sa.select(
            history.c.body_json,
            t.events.c.id,
            t.events.c.kind,
            t.events.c.payload_json,
            t.events.c.actor_id,
        )
        .join(t.events, history.c.event_id == t.events.c.id)
        .where(history.c.campaign_id == game.store.campaign_id)
        .order_by(t.events.c.seq)
    ).mappings()
    for row in rows:
        before = GameState.model_validate_json(row["body_json"])
        sheet = before.sheets.get(str(person))
        if sheet is None or sheet.character_id != actor.incarnation:
            continue
        born = next((x for x in sheet.tags if x.id == tag.id), None)
        if born is None:
            continue
        payload = json.loads(row["payload_json"])
        if row["kind"] not in ("m2.choice_resolved", "m3.choice_resolved") or not same_tag(
            born, tag
        ):
            break
        action_id = payload.get("action_id")
        if not isinstance(action_id, str):
            break
        action = game.action(c, action_id)
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
        beneath = (
            action["data"].get("play") == "put_someone_beneath_you"
            and str(tag.giver) == action["actor_id"]
            and choice is not None
            and choice["kind"] == "beneath_select"
        )
        flirt = (
            action["data"].get("play") == "flirt"
            and action["actor_id"] == str(person)
            and action["data"].get("prepared", {}).get("target") == tag.giver
            and choice is not None
            and choice["kind"] == "flirt_owe_tag"
            and choice["actor_id"] == str(tag.giver)
            and row["actor_id"] == str(tag.giver)
            and action["data"].get("character_ids", {}).get(str(person)) == actor.incarnation
            and action["data"].get("character_ids", {}).get(str(tag.giver))
            == current_ref(before, tag.giver).incarnation
        )
        if (
            action["state"] != "complete"
            or not (beneath or flirt)
            or choice is None
            or choice["action_id"] != action_id
            or tag.giver_actor != current_ref(before, tag.giver)
            or not c.scalar(
                sa.select(t.m2["m2_receipts"].c.action_id).where(
                    t.m2["m2_receipts"].c.campaign_id == game.store.campaign_id,
                    t.m2["m2_receipts"].c.action_id == action_id,
                )
            )
        ):
            break
        return row["id"], action_id
    raise WorkflowError(
        "Use the exact existing ordinary Tag from its completed original authored Play"
    )


def prove(
    game: GameService, c: Connection, state: GameState, value: rules.IntoxicationTag
) -> TagState:
    _audit(game, c, value.event, "m3.malleable_intoxication_tag", value.controller)
    born = _history(c, game, value.event)
    if (
        value not in rules.records(born, rules.IntoxicationTag)
        or current_ref(born, value.controller) != value.subject
    ):
        raise WorkflowError("Preserve the affected owner's original Tag classification")
    _giver(game, c, born, value.subject)
    tag = TagState.model_validate_json(value.tag)
    original = next((x for x in born.sheets[value.subject.entity].tags if x.id == value.id), None)
    if (
        original is None
        or not same_tag(tag, original)
        or origin(game, c, born, value.controller, tag) != (value.source_event, value.action)
    ):
        raise WorkflowError("Recover the classified Tag's exact original giver and source")
    return tag


def record(
    game: GameService, viewer: GuildViewer, key: str, tag_id: str, expected: int, account: str
) -> dict[str, Any]:
    if not account.strip() or len(account) > 1200:
        raise WorkflowError(
            "Describe how your actual existing Tag represents drugs or intoxication"
        )

    def operation(c: Connection) -> dict[str, Any]:
        game.unpaused(c)
        state = load_state(c, game.store.campaign_id)
        actor = current_ref(state, viewer.user_id)
        _giver(game, c, state, actor)
        if state.revision != expected or game.pending_actions(c):
            raise WorkflowError("Finish the actual Play and reopen your current Tag")
        tag = next((x for x in state.sheets[actor.entity].tags if x.id == tag_id), None)
        if tag is None or any(x.id == tag_id for x in rules.records(state, rules.IntoxicationTag)):
            raise WorkflowError("Classify only your own existing unclassified Tag")
        source, action = origin(game, c, state, viewer.user_id, tag)
        event = str(uuid4())
        rules.put(
            state,
            rules.IntoxicationTag(
                id=tag.id,
                subject=actor,
                controller=viewer.user_id,
                event=event,
                source_event=source,
                action=action,
                tag=tag.model_dump_json(),
                account=account.strip(),
            ),
        )
        game.event(
            c,
            viewer.user_id,
            key,
            "m3.malleable_intoxication_tag",
            state,
            event_id=event,
            tag=tag.id,
        )
        return dict(id=tag.id)

    return game.store._write(
        viewer,
        key,
        "m3.malleable_intoxication_tag",
        dict(tag=tag_id, expected=expected, account=account),
        operation,
        auto_audit=False,
        authorize=lambda c: _access(game, c, viewer),
    )


def self_tag(
    game: GameService,
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    person: int,
    tag: TagState,
) -> bool:
    meta = action["data"].get("tag_context") or {}
    from girlframe.engine.m3_actor_state import ActorRef

    actor = (
        ActorRef.model_validate(meta["actor"])
        if meta.get("actor")
        else current_ref(state, int(action["actor_id"]))
    )
    if actor.kind != "pilot" or actor != current_ref(state, person):
        return False
    sheet = state.sheets[actor.entity]
    if not has_rule(sheet, rules.RULE, "STIM-BLISSED"):
        return False
    value = next(
        (
            x
            for x in rules.records(state, rules.IntoxicationTag)
            if x.id == tag.id and x.subject == actor
        ),
        None,
    )
    if value is None:
        return False
    from girlframe.services.m3_access import Access

    registry = Access(game.store).registry
    assert registry is not None
    registry.require_available(rules.RULE)
    original = prove(game, c, state, value)
    if not same_tag(tag, original) or not any(x.id == tag.id for x in sheet.tags):
        raise WorkflowError("Preserve this exact classified original Tag")
    return True
