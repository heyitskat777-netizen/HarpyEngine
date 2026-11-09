"""Finite genuine learned Sex providers, with separate invitation and actual Action ownership."""

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
    "girl.alpha.sex-play": ("alpha_sex", "ALPHA", "m3.alpha_sex"),
    "girl.oldgen.sex-play": ("oldgen_sex", "OLDGEN", "m3.oldgen_sex"),
    "girl.newgirl.sex-play": ("newgirl_sex", "NEWGIRL", "m3.newgirl_sex"),
    "girl.mockingbird.sex-play": ("mockingbird_sex", "MOCKINGBIRD", "m3.mockingbird_trigger"),
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
    if value.rule_id == "girl.alpha.sex-play":
        from girlframe.engine.m3_alpha_sex import get as alpha_get

        return alpha_get(state, value.session)
    if value.rule_id == "girl.mockingbird.sex-play":
        from girlframe.services.m3_mockingbird_plays import _trigger

        return _trigger(state, value.session)
    if value.rule_id == "girl.oldgen.sex-play":
        from girlframe.engine.m3_oldgen_sex import get as oldgen_get

        return oldgen_get(state, value.session)
    if value.rule_id == "girl.newgirl.sex-play":
        from girlframe.engine.m3_newgirl_sex import get as newgirl_get

        return newgirl_get(state, value.session)
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


def reserve_trigger_invitation(
    game: "GameService", c: Connection, state: GameState, trigger: Any, lesson: str
) -> str:
    rule = "girl.mockingbird.sex-play"
    if (
        trigger.play != "mockingbird_sex"
        or len(trigger.parties) != 1
        or not admit_offer(game, c, state, trigger.actor, rule, lesson)
    ):
        raise WorkflowError("Select your actual free lesson and one real intimacy counterpart")
    value = LearnedSexLink(
        id="learned-sex:" + trigger.id,
        lesson=lesson,
        rule_id="girl.mockingbird.sex-play",
        session=trigger.id,
        actor=trigger.actor,
        target=trigger.parties[0].actor,
        cast_sha256=trigger.cast_sha256,
        proposed_event=trigger.source_event,
    )
    put_learned_sex_link(state, value)
    return value.id


def reserve_partner_invitation(
    game: "GameService", c: Connection, state: GameState, session: Any, lesson: str
) -> str:
    """Reserve an actual Newgirl Session, never synthesize its target/consent fields."""
    if len(session.partners) != 1 or not admit_offer(
        game, c, state, session.actor, "girl.newgirl.sex-play", lesson
    ):
        raise WorkflowError("Select your actual free lesson and one real original partner")
    value = LearnedSexLink(
        id="learned-sex:" + session.id,
        lesson=lesson,
        rule_id="girl.newgirl.sex-play",
        session=session.id,
        actor=session.actor,
        target=session.partners[0],
        cast_sha256=fingerprint(session.cast),
        proposed_event=session.proposed_event,
    )
    put_learned_sex_link(state, value)
    return value.id


def _newgirl_consents(state: GameState) -> Any:
    from girlframe.engine.m3_newgirl_sex import Consent, records

    return records(state, Consent)


def _partner_consent(state: GameState, value: LearnedSexLink) -> Any:
    answers = [
        x
        for x in _newgirl_consents(state)
        if x.session == value.session and x.person == value.target
    ]
    if len(answers) != 1:
        raise WorkflowError("Recover the real original partner's separate consent record")
    return answers[0]


def prove(game: "GameService", c: Connection, state: GameState, identity: str) -> LearnedSexLink:
    value = get(state, identity)
    if value.rule_id not in SOURCES:
        raise WorkflowError("Use one of the genuine learned Sex providers")
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
    mockingbird = value.rule_id == "girl.mockingbird.sex-play"
    newgirl = value.rule_id == "girl.newgirl.sex-play"
    if mockingbird:
        original_invitation = (
            first.state == "proposed"
            and first.action is None
            and first.play == "mockingbird_sex"
            and len(first.parties) == 1
            and first.parties[0].actor == value.target
            and first.parties[0].decision == "pending"
            and first.parties[0].event is None
            and first.actor == value.actor
            and first.source_event == value.proposed_event
            and first.cast_sha256 == value.cast_sha256
            and first.learned_sex_source == value.id
            and first.learned_source is None
            and any(
                x.id == first.scene and x.open and fingerprint(x) == value.cast_sha256
                for x in proposed.scene_casts
            )
        )
    elif newgirl:
        original_invitation = (
            first.phase == "invited"
            and first.action is None
            and len(first.partners) == 1
            and first.partners[0] == value.target
            and first.actor == value.actor
            and first.proposed_event == value.proposed_event
            and first.learned_source == value.id
            and fingerprint(first.cast) == value.cast_sha256
            and not any(x.session == value.session for x in _newgirl_consents(proposed))
        )
    else:
        original_invitation = (
            first.phase == "invited"
            and first.consent_event is None
            and first.learned_source == value.id
            and first.actor == value.actor
            and first.target == value.target
            and first.proposed_event == value.proposed_event
            and fingerprint(first.cast) == value.cast_sha256
        )
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
        or not original_invitation
        or (value.consent_event is None) != (value.accepted is None)
        or (value.action is None) != (value.bound_event is None)
        or (value.roll_event is None) != (value.receipt_sha256 is None)
        or (value.released_event is None) != (value.released_kind is None)
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

    payload = {"trigger" if mockingbird else "session": value.session}
    audit(
        value.proposed_event,
        (prefix if mockingbird else prefix + "_proposed" if newgirl else prefix + "_invited",),
        value.actor.entity,
        **payload,
    )
    if mockingbird:
        current = _session(state, value)
        if any(
            getattr(first, key) != getattr(current, key)
            for key in (
                "id",
                "play",
                "actor",
                "scene",
                "channel",
                "cast_sha256",
                "source_event",
                "account",
                "learned_source",
                "learned_sex_source",
                "bonded_source",
                "changeling_source",
            )
        ) or [(x.actor, x.controller) for x in first.parties] != [
            (x.actor, x.controller) for x in current.parties
        ]:
            raise WorkflowError(
                "Preserve the original learned trigger and actual party controllers"
            )
    if value.consent_event is not None:
        consent = audit(
            value.consent_event,
            (
                "m3.mockingbird_trigger_attested"
                if mockingbird
                else prefix + "_confirmed"
                if newgirl
                else prefix + "_consent",
            ),
            str(first.parties[0].controller) if mockingbird else value.target.entity,
            **(
                dict(
                    trigger=value.session,
                    party=value.target.model_dump(mode="json"),
                    accept=value.accepted,
                )
                if mockingbird
                else payload
            ),
        )
        saved = get(consent, identity)
        actual = _session(consent, value)
        if mockingbird:
            actual_answer = (
                actual.parties[0].event == value.consent_event
                and actual.parties[0].decision == ("accepted" if value.accepted else "declined")
                and actual.state == ("ready" if value.accepted else "declined")
            )
        elif newgirl:
            answer = _partner_consent(consent, value)
            actual_answer = (
                answer.event == value.consent_event
                and answer.accepted == value.accepted
                and answer.controller == int(value.target.entity)
                and actual.phase == ("accepted" if value.accepted else "declined")
            )
        else:
            actual_answer = actual.consent_event == value.consent_event and actual.phase == (
                "accepted" if value.accepted else "declined"
            )
        if (
            saved.consent_event != value.consent_event
            or saved.accepted != value.accepted
            or not actual_answer
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
            or (
                session.state != "ready"
                if mockingbird
                else session.phase != "active"
                if value.rule_id == "girl.alpha.sex-play"
                else (
                    session.bound_event != value.bound_event or newgirl and session.phase != "bound"
                )
            )
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
        elif value.released_kind == "withdrawn":
            if not mockingbird or value.action is not None or value.roll_event is not None:
                raise WorkflowError("Withdraw only the actual unbound learned trigger")
            withdrawn = audit(
                value.released_event,
                ("m3.mockingbird_trigger_withdrawn",),
                value.actor.entity,
                trigger=value.session,
            )
            if (
                get(withdrawn, identity).released_event != value.released_event
                or _session(withdrawn, value).state != "withdrawn"
            ):
                raise WorkflowError("Recover the actual original owner's source withdrawal")
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


def record_partner_consent(
    game: "GameService", c: Connection, state: GameState, session: Any, event: str
) -> None:
    if session.learned_source is None:
        return
    value = prove(game, c, state, session.learned_source)
    answer = _partner_consent(state, value)
    if (
        value.consent_event is not None
        or value.released_event is not None
        or answer.event != event
        or answer.controller != session.controllers[value.target.token]
    ):
        raise WorkflowError("Preserve the original partner's actual own consent event")
    put_learned_sex_link(
        state,
        value.model_copy(
            update=dict(
                consent_event=event,
                accepted=answer.accepted,
                **(
                    dict(released_event=event, released_kind="declined")
                    if not answer.accepted
                    else {}
                ),
            )
        ),
    )


def record_trigger_consent(
    game: "GameService", c: Connection, state: GameState, trigger: Any, accepted: bool, event: str
) -> None:
    if trigger.learned_sex_source is None:
        return
    value = prove(game, c, state, trigger.learned_sex_source)
    if (
        value.consent_event is not None
        or value.released_event is not None
        or len(trigger.parties) != 1
        or trigger.parties[0].actor != value.target
        or trigger.parties[0].event != event
        or trigger.parties[0].decision != ("accepted" if accepted else "declined")
    ):
        raise WorkflowError("Preserve the actual original party's voluntary source response")
    put_learned_sex_link(
        state,
        value.model_copy(
            update=dict(
                consent_event=event,
                accepted=accepted,
                **(dict(released_event=event, released_kind="declined") if not accepted else {}),
            )
        ),
    )


def withdraw_invitation(
    game: "GameService", c: Connection, state: GameState, trigger: Any, event: str
) -> None:
    if trigger.learned_sex_source is None:
        return
    value = prove(game, c, state, trigger.learned_sex_source)
    if value.action is not None or value.roll_event is not None or value.released_event:
        raise WorkflowError("Withdraw only your actual unbound source reservation")
    put_learned_sex_link(
        state,
        value.model_copy(
            update=dict(
                released_event=event,
                released_kind="withdrawn",
            )
        ),
    )


def source_id(action: dict[str, Any]) -> str | None:
    """Finite metadata dispatch only: this makes no eligibility/authority claim."""
    data = action["data"]
    values = [
        meta["learned_source"]
        for key in ("princess_sex", "stim_sex", "alpha_sex", "oldgen_sex", "newgirl_sex")
        if (meta := data.get(key)) and meta.get("learned_source")
    ]
    if data.get("mockingbird", {}).get("learned_sex_source"):
        values.append(data["mockingbird"]["learned_sex_source"])
    if len(values) > 1:
        raise WorkflowError("One genuine Action has one learned intimacy source")
    return values[0] if values else None


def _action_link(state: GameState, action: dict[str, Any]) -> LearnedSexLink | None:
    identity = source_id(action)
    return get(state, identity) if identity is not None else None


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
        or (
            session.state != "ready"
            if value.rule_id == "girl.mockingbird.sex-play"
            else session.phase != "active"
            if value.rule_id == "girl.alpha.sex-play"
            else (
                session.bound_event != event
                or (value.rule_id == "girl.newgirl.sex-play" and session.phase != "bound")
            )
        )
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
