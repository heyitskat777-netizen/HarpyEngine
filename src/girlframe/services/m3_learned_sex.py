"""Two genuine learned Sex providers, with separate invitation and actual Action ownership."""

import json
from typing import TYPE_CHECKING, Any

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_actors import fingerprint
from girlframe.engine.m3_girl_runtime_state import GirlRuntime, has_rule
from girlframe.engine.m3_learned_play_state import (
    LearnedPlayUse,
    LearnedSexLink,
    learned_sex_links,
    put_learned_sex_link,
)
from girlframe.services.m3_access import load_registry
from girlframe.services.m3_handler_advancements import _history
from girlframe.services.m3_learned_plays import _keep_raw_roll, _keep_receipt, _prove, _replace
from girlframe.services.onboarding import WorkflowError

if TYPE_CHECKING:
    from girlframe.services.m2_game import GameService

SOURCES = {
    "girl.princess.sex-play": ("princess_sex", "PRINCESS", "m3.princess_sex"),
    "girl.stim-blissed.sex-play": ("stim_sex", "STIM-BLISSED", "m3.stim_sex"),
}


def get(state: GameState, identity: str) -> LearnedSexLink:
    values = [x for x in learned_sex_links(state) if x.id == identity]
    if len(values) != 1:
        raise WorkflowError("Recover the original learned voluntary source link")
    return values[0]


def _session(state: GameState, value: LearnedSexLink) -> Any:
    if value.rule_id == "girl.princess.sex-play":
        from girlframe.engine.m3_princess_sex import get as princess_get

        return princess_get(state, value.session)
    from girlframe.engine.m3_stim_sex import get as stim_get

    return stim_get(state, value.session)


def _grant(
    game: "GameService", c: Connection, state: GameState, link: LearnedSexLink
) -> LearnedPlayUse:
    sheet = state.sheets.get(link.actor.entity)
    runtime = sheet.girl_runtime if sheet and sheet.character_id == link.actor.incarnation else None
    value = (
        next((x for x in runtime.learned_plays if x.id == link.lesson), None) if runtime else None
    )
    if value is None or value.actor != link.actor or value.rule_id != link.rule_id:
        raise WorkflowError("Preserve the original learner and genuine one-use source")
    _prove(game, c, state, value)
    return value


def lessons(
    game: "GameService", c: Connection, state: GameState, actor: ActorRef, rule: str
) -> tuple[dict[str, str], ...]:
    if rule not in SOURCES or actor.kind != "pilot":
        return ()
    sheet = state.sheets.get(actor.entity)
    if sheet is None or sheet.character_id != actor.incarnation:
        return ()
    try:
        load_registry().require_available(rule)
    except ValueError:
        return ()
    play, book, _ = SOURCES[rule]
    runtime = sheet.girl_runtime or GirlRuntime()
    if has_rule(
        sheet.model_copy(update={"girl_runtime": runtime.model_copy(update={"learned_plays": ()})}),
        rule,
        book,
    ):
        return ()
    held = {x.lesson for x in learned_sex_links(state) if x.released_event is None}
    result = []
    for value in runtime.learned_plays:
        if (
            value.rule_id == rule
            and value.actor == actor
            and value.rolled_event is None
            and value.claimed_action is None
            and value.id not in held
        ):
            _prove(game, c, state, value)
            result.append(
                dict(
                    id=value.id,
                    label=book.replace("-", " ").title() + " Sex — one source",
                    rule_id=rule,
                    play=play,
                )
            )
    return tuple(result)


def available_rules(
    game: "GameService", c: Connection, state: GameState, actor: ActorRef
) -> tuple[dict[str, str], ...]:
    return tuple(row for rule in SOURCES for row in lessons(game, c, state, actor, rule))


def admit_offer(
    game: "GameService",
    c: Connection,
    state: GameState,
    actor: ActorRef,
    rule: str,
    lesson: str | None,
) -> bool:
    return bool(
        lesson is not None and any(x["id"] == lesson for x in lessons(game, c, state, actor, rule))
    )


def reserve_invitation(
    game: "GameService", c: Connection, state: GameState, session: Any, rule: str, lesson: str
) -> str:
    if not admit_offer(game, c, state, session.actor, rule, lesson):
        raise WorkflowError("Select your actual free lesson before this real invitation")
    value = LearnedSexLink.model_validate(
        dict(
            id="learned-sex:" + session.id,
            lesson=lesson,
            rule_id=rule,
            session=session.id,
            actor=session.actor,
            target=session.target,
            cast_sha256=fingerprint(session.cast),
            proposed_event=session.proposed_event,
        )
    )
    put_learned_sex_link(state, value)
    return value.id


def prove(game: "GameService", c: Connection, state: GameState, identity: str) -> LearnedSexLink:
    value = get(state, identity)
    if value.rule_id not in SOURCES:
        raise WorkflowError("Use one of the two genuine learned Sex providers")
    _, _, prefix = SOURCES[value.rule_id]
    proposed = _history(c, game, value.proposed_event)
    born = get(proposed, identity)
    first = _session(proposed, value)
    stable = (
        "id",
        "lesson",
        "rule_id",
        "session",
        "actor",
        "target",
        "cast_sha256",
        "proposed_event",
    )
    grant = _grant(game, c, proposed, value)
    if (
        any(getattr(value, k) != getattr(born, k) for k in stable)
        or any(
            getattr(born, key) is not None
            for key in (
                "consent_event",
                "accepted",
                "action",
                "bound_event",
                "roll_event",
                "receipt_sha256",
                "released_event",
                "released_kind",
            )
        )
        or first.phase != "invited"
        or first.consent_event is not None
        or (value.consent_event is None) != (value.accepted is None)
        or (value.action is None) != (value.bound_event is None)
        or (value.roll_event is None) != (value.receipt_sha256 is None)
        or (value.released_event is None) != (value.released_kind is None)
        or first.learned_source != value.id
        or first.actor != value.actor
        or first.target != value.target
        or first.proposed_event != value.proposed_event
        or fingerprint(first.cast) != value.cast_sha256
        or first.bonded_source is not None
        or first.changeling_source is not None
        or grant.claimed_action is not None
        or grant.rolled_event is not None
    ):
        raise WorkflowError(
            "Keep the actual original invitation, counterpart, cast and free lesson"
        )

    def audit(event: str, kind: tuple[str, ...], owner: str, **payload: Any) -> GameState:
        row = (
            c.execute(
                sa.select(t.events).where(
                    t.events.c.campaign_id == game.store.campaign_id, t.events.c.id == event
                )
            )
            .mappings()
            .first()
        )
        data = json.loads(row["payload_json"]) if row else {}
        if (
            row is None
            or row["kind"] not in kind
            or row["actor_id"] != owner
            or any(data.get(k) != v for k, v in payload.items())
        ):
            raise WorkflowError("Prove the actual original human's canonical learned source event")
        return _history(c, game, event)

    audit(value.proposed_event, (prefix + "_invited",), value.actor.entity, session=value.session)
    if value.consent_event is not None:
        consent = audit(
            value.consent_event, (prefix + "_consent",), value.target.entity, session=value.session
        )
        saved = get(consent, identity)
        actual = _session(consent, value)
        if (
            saved.consent_event != value.consent_event
            or saved.accepted != value.accepted
            or actual.consent_event != value.consent_event
            or actual.phase != ("accepted" if value.accepted else "declined")
        ):
            raise WorkflowError("Keep the actual counterpart's own confirmation or refusal")
    if value.action is not None:
        if value.bound_event is None or value.accepted is not True:
            raise WorkflowError("Bind only the actual accepted original source")
        bound = audit(
            value.bound_event,
            ("m2.play_confirmed", "m3.play_confirmed"),
            value.actor.entity,
            action_id=value.action,
        )
        original = get(bound, identity)
        session = _session(bound, value)
        claimed = _grant(game, c, bound, value)
        if (
            original.action != value.action
            or original.bound_event != value.bound_event
            or session.action != value.action
            or session.bound_event != value.bound_event
            or claimed.claimed_action != value.action
            or claimed.rolled_event is not None
        ):
            raise WorkflowError("Keep the genuine Action binding and original resource reservation")
    if value.roll_event is not None:
        if value.action is None:
            raise WorkflowError("A real learned receipt needs its actual Action")
        action = game.action(c, value.action)
        rolled = _history(c, game, value.roll_event)
        spent = _grant(game, c, rolled, value)
        saved = get(rolled, identity)
        if (
            saved.roll_event != value.roll_event
            or saved.receipt_sha256 != value.receipt_sha256
            or value.roll_event != _keep_raw_roll(game, c, action)
            or value.receipt_sha256 != _keep_receipt(game, c, action)
            or spent.claimed_action != value.action
            or spent.rolled_event != value.roll_event
        ):
            raise WorkflowError("Preserve the actual once-only learned receipt and source costs")
    if value.released_event is not None:
        if value.released_kind == "declined":
            if (
                value.accepted is not False
                or value.released_event != value.consent_event
                or value.action is not None
            ):
                raise WorkflowError("A source refusal is the actual counterpart's answer")
        elif value.released_kind == "owner_cancelled":
            if value.action is None or value.roll_event is not None:
                raise WorkflowError("Cancel only the genuine unrolled original source")
            ended = audit(
                value.released_event,
                ("m3.shared_play_recovered",),
                value.actor.entity,
                action_id=value.action,
                cancelled_unrolled=True,
            )
            released = _grant(game, c, ended, value)
            if (
                get(ended, identity).released_event != value.released_event
                or released.claimed_action is not None
                or released.rolled_event is not None
            ):
                raise WorkflowError("Preserve the actual owner's cancellation and unspent lesson")
        else:
            raise WorkflowError("A released source needs its actual release event")
    return value


def admit_source(
    game: "GameService",
    c: Connection,
    state: GameState,
    actor: ActorRef,
    target: ActorRef,
    rule: str,
    identity: str | None,
    *,
    pending_event: str | None = None,
) -> bool:
    if identity is None:
        return False
    value = get(state, identity)
    if (
        value.actor != actor
        or value.target != target
        or value.rule_id != rule
        or value.released_event is not None
    ):
        raise WorkflowError("Use the original living source, not another person's entitlement")
    if pending_event is not None:
        grant = _grant(game, c, state, value)
        if (
            value.proposed_event != pending_event
            or grant.claimed_action is not None
            or grant.rolled_event is not None
        ):
            raise WorkflowError("Stage only this actual original invitation's unused source")
    else:
        prove(game, c, state, identity)
    return True


def record_consent(
    game: "GameService", c: Connection, state: GameState, session: Any, accepted: bool, event: str
) -> None:
    if session.learned_source is None:
        return
    value = prove(game, c, state, session.learned_source)
    if (
        value.consent_event is not None
        or value.released_event is not None
        or session.counterpart != int(value.target.entity)
    ):
        raise WorkflowError("Only the real original counterpart answers this invitation once")
    put_learned_sex_link(
        state,
        value.model_copy(
            update=dict(
                consent_event=event,
                accepted=accepted,
                **({"released_event": event, "released_kind": "declined"} if not accepted else {}),
            )
        ),
    )


def _action_link(state: GameState, action: dict[str, Any]) -> LearnedSexLink | None:
    values = [
        get(state, meta["learned_source"])
        for key in ("princess_sex", "stim_sex")
        if (meta := action["data"].get(key)) and meta.get("learned_source")
    ]
    if len(values) > 1:
        raise WorkflowError("One genuine Action has one learned intimacy source")
    return values[0] if values else None


def bind_action(
    game: "GameService", c: Connection, state: GameState, action: dict[str, Any], event: str
) -> bool:
    value = _action_link(state, action)
    if value is None:
        return False
    prove(game, c, state, value.id)
    session = _session(state, value)
    grant = _grant(game, c, state, value)
    if (
        value.accepted is not True
        or value.action is not None
        or value.released_event is not None
        or session.action != action["id"]
        or session.bound_event != event
        or str(action["actor_id"]) != value.actor.entity
        or grant.claimed_action is not None
        or grant.rolled_event is not None
        or action["data"].get("play") != SOURCES[value.rule_id][0]
        or action["data"]["prepared"].get("source_work") != value.session
    ):
        raise WorkflowError("Bind the accepted original lesson only to its actual new Action")
    _replace(state, grant.model_copy(update=dict(claimed_action=action["id"])))
    put_learned_sex_link(
        state, value.model_copy(update=dict(action=action["id"], bound_event=event))
    )
    return True


def pre_roll(game: "GameService", c: Connection, state: GameState, action: dict[str, Any]) -> None:
    value = _action_link(state, action)
    if value is None:
        return
    prove(game, c, state, value.id)
    grant = _grant(game, c, state, value)
    if (
        value.action != action["id"]
        or value.released_event is not None
        or value.roll_event is not None
        or grant.claimed_action != action["id"]
        or grant.rolled_event is not None
        or action["data"].get("receipt")
        or value.actor != current_ref(state, int(action["actor_id"]))
    ):
        raise WorkflowError("Use only your actual original accepted unrolled Sex source")


def consume(
    game: "GameService", c: Connection, state: GameState, action: dict[str, Any], event: str
) -> None:
    value = _action_link(state, action)
    if value is None:
        return
    prove(game, c, state, value.id)
    grant = _grant(game, c, state, value)
    if (
        value.action != action["id"]
        or value.released_event is not None
        or value.roll_event is not None
        or grant.rolled_event is not None
    ):
        raise WorkflowError("Consume only this actual accepted source's first genuine receipt")
    receipt = _keep_receipt(game, c, action)
    _replace(state, grant.model_copy(update=dict(rolled_event=event)))
    put_learned_sex_link(
        state, value.model_copy(update=dict(roll_event=event, receipt_sha256=receipt))
    )


def release_unrolled(
    game: "GameService", c: Connection, state: GameState, action: dict[str, Any], event: str
) -> bool:
    value = _action_link(state, action)
    if value is None:
        return False
    pre_roll(game, c, state, action)
    grant = _grant(game, c, state, value)
    _replace(state, grant.model_copy(update=dict(claimed_action=None)))
    put_learned_sex_link(
        state, value.model_copy(update=dict(released_event=event, released_kind="owner_cancelled"))
    )
    return True


def cancelled(game: "GameService", c: Connection, state: GameState, identity: str | None) -> bool:
    return bool(
        identity is not None and prove(game, c, state, identity).released_kind == "owner_cancelled"
    )
