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
    LearnedSexParty,
    learned_sex_links,
    put_learned_sex_link,
    sex_party_refs,
)
from girlframe.services.m3_access import load_registry
from girlframe.services.m3_handler_advancements import _history
from girlframe.services.m3_learned_plays import _keep_raw_roll, _keep_receipt, _prove, _replace
from girlframe.services.onboarding import WorkflowError

if TYPE_CHECKING:
    from girlframe.services.m2_game import GameService

SOURCES = {
    "girl.casualty.sex-play": ("casualty_sex", "CASUALTY", "m3.casualty_sex"),
    "girl.bonded.sex-play": ("bonded_sex", "BONDED", "m3.bonded"),
    "girl.princess.sex-play": ("princess_sex", "PRINCESS", "m3.princess_sex"),
    "girl.stim-blissed.sex-play": ("stim_sex", "STIM-BLISSED", "m3.stim_sex"),
    "girl.alpha.sex-play": ("alpha_sex", "ALPHA", "m3.alpha_sex"),
    "girl.oldgen.sex-play": ("oldgen_sex", "OLDGEN", "m3.oldgen_sex"),
    "girl.newgirl.sex-play": ("newgirl_sex", "NEWGIRL", "m3.newgirl_sex"),
    "girl.vatgrown.sex-play": ("vatgrown_sex", "VATGROWN", "m3.vatgrown_sex"),
    "girl.mockingbird.sex-play": ("mockingbird_sex", "MOCKINGBIRD", "m3.mockingbird_trigger"),
}


def get(state: GameState, identity: str) -> LearnedSexLink:
    values = [x for x in learned_sex_links(state) if x.id == identity]
    if len(values) != 1:
        raise WorkflowError("Recover the original learned voluntary source link")
    return values[0]


def _session(state: GameState, value: LearnedSexLink) -> Any:
    if value.rule_id == "girl.casualty.sex-play":
        from girlframe.services.m3_casualty import _session as casualty_session

        return casualty_session(state, value.session)
    if value.rule_id == "girl.bonded.sex-play":
        from girlframe.engine.m3_bonded import get as bonded_get

        return bonded_get(state, value.session)
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
    if value.rule_id == "girl.vatgrown.sex-play":
        from girlframe.engine.m3_vatgrown_plays import get as vatgrown_get

        return vatgrown_get(state, value.session)
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
            and value.claimed_source is None
            and value.used_event is None
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
        or not trigger.parties
        or len({x.actor for x in trigger.parties}) != len(trigger.parties)
        or not admit_offer(game, c, state, trigger.actor, rule, lesson)
    ):
        raise WorkflowError(
            "Select your actual free lesson and distinct real intimacy counterparts"
        )
    value = LearnedSexLink(
        id="learned-sex:" + trigger.id,
        lesson=lesson,
        rule_id="girl.mockingbird.sex-play",
        session=trigger.id,
        actor=trigger.actor,
        target=trigger.parties[0].actor,
        cast_sha256=trigger.cast_sha256,
        proposed_event=trigger.source_event,
        parties=(
            tuple(LearnedSexParty(actor=x.actor, controller=x.controller) for x in trigger.parties)
            if len(trigger.parties) > 1
            else None
        ),
    )
    put_learned_sex_link(state, value)
    return value.id


def reserve_partner_invitation(
    game: "GameService", c: Connection, state: GameState, session: Any, lesson: str
) -> str:
    """Reserve an actual Newgirl Session, never synthesize its target/consent fields."""
    if (
        not session.partners
        or len(set(session.partners)) != len(session.partners)
        or not admit_offer(game, c, state, session.actor, "girl.newgirl.sex-play", lesson)
    ):
        raise WorkflowError("Select your actual free lesson and distinct real original partners")
    value = LearnedSexLink(
        id="learned-sex:" + session.id,
        lesson=lesson,
        rule_id="girl.newgirl.sex-play",
        session=session.id,
        actor=session.actor,
        target=session.partners[0],
        cast_sha256=fingerprint(session.cast),
        proposed_event=session.proposed_event,
        parties=(
            tuple(
                LearnedSexParty(actor=x, controller=session.controllers[x.token])
                for x in session.partners
            )
            if len(session.partners) > 1
            else None
        ),
    )
    put_learned_sex_link(state, value)
    return value.id


def _newgirl_consents(state: GameState) -> Any:
    from girlframe.engine.m3_newgirl_sex import Consent, records

    return records(state, Consent)


def _partner_consent(state: GameState, value: LearnedSexLink, event: str | None = None) -> Any:
    answers = [
        x
        for x in _newgirl_consents(state)
        if x.session == value.session and x.event == (event or value.consent_event)
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
    bonded = value.rule_id == "girl.bonded.sex-play"
    casualty = value.rule_id == "girl.casualty.sex-play"
    alpha = value.rule_id == "girl.alpha.sex-play"
    oldgen = value.rule_id == "girl.oldgen.sex-play"
    princess = value.rule_id == "girl.princess.sex-play"
    if mockingbird:
        original_invitation = (
            first.state == "proposed"
            and first.action is None
            and first.play == "mockingbird_sex"
            and bool(first.parties)
            and len({x.actor for x in first.parties}) == len(first.parties)
            and tuple(x.actor for x in first.parties) == sex_party_refs(value)
            and first.parties[0].actor == value.target
            and all(x.decision == "pending" and x.event is None for x in first.parties)
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
            and bool(first.partners)
            and len(set(first.partners)) == len(first.partners)
            and first.partners == sex_party_refs(value)
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
                "used_event",
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
        or grant.claimed_source is not None
        or grant.used_event is not None
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

    # Vatgrown's existing transaction wrapper stamps its source ID as `source`.
    # Other Session providers stamp `session`; Mockingbird stamps `trigger`.
    payload = {
        "trigger"
        if mockingbird
        else "source"
        if value.rule_id in ("girl.vatgrown.sex-play", "girl.bonded.sex-play")
        else "session": value.session
    }
    audit(
        value.proposed_event,
        (
            prefix
            if mockingbird
            else prefix + "_proposed"
            if newgirl or bonded or casualty
            else prefix + "_invited",
        ),
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
    if casualty:
        current_casualty = _session(state, value)
        if any(
            getattr(first, key) != getattr(current_casualty, key)
            for key in (
                "id",
                "actor",
                "target",
                "caster",
                "counterpart",
                "cast",
                "actor_vessel",
                "target_vessel",
                "registry",
                "proposed_event",
                "proposal",
                "bonded_source",
                "changeling_source",
                "learned_source",
            )
        ):
            raise WorkflowError(
                "Preserve original Casualty source, real bodies and independent controllers"
            )
        from girlframe.services.m3_casualty import prove_parts

        body = prove_parts(game, c, proposed, value.actor)
        if body.vessel != first.actor_vessel:
            raise WorkflowError("Learned Sex supplies no missing or replacement anatomy")
    if bonded:
        current_bonded = _session(state, value)
        if (
            first.kind != "sex"
            or first.route not in ("pair", "seven", "delegated")
            or first.target is None
            or first.target == first.actor
            or (first.target == first.pair) != (first.route == "pair")
            or (
                first.delegated_rule
                not in (
                    "girl.mockingbird.sex-play",
                    "girl.princess.sex-play",
                    "girl.newgirl.sex-play",
                    "girl.oldgen.sex-play",
                    "girl.stim-blissed.sex-play",
                    "girl.alpha.sex-play",
                    "girl.vatgrown.sex-play",
                    "girl.casualty.sex-play",
                    "girl.am.sex-play",
                )
                if first.route == "delegated"
                else first.delegated_rule is not None
            )
            or any(
                getattr(first, key) != getattr(current_bonded, key)
                for key in (
                    "id",
                    "kind",
                    "actor",
                    "pair",
                    "target",
                    "observer",
                    "controllers",
                    "vessels",
                    "cast",
                    "registry",
                    "pair_source",
                    "event",
                    "account",
                    "route",
                    "delegated_rule",
                    "changeling_source",
                    "learned_source",
                )
            )
        ):
            raise WorkflowError("Preserve the real own-Pair source and its original lineage")
        from girlframe.services.m3_bonded import pair_lineage

        if pair_lineage(game, c, proposed, value.actor, historical=True) != (
            first.pair,
            first.pair_source,
        ):
            raise WorkflowError("Recover the independently genuine original Pair")
    if newgirl:
        current_session = _session(state, value)
        if any(
            getattr(first, key) != getattr(current_session, key)
            for key in (
                "id",
                "actor",
                "partners",
                "controllers",
                "vessels",
                "cast",
                "registry",
                "proposed_event",
                "proposal",
                "learned_source",
                "bonded_source",
                "changeling_source",
            )
        ):
            raise WorkflowError("Preserve every original group partner, controller and body")
    if value.parties is not None:
        _prove_group(game, c, state, value, born, first, proposed)
    elif value.consent_event is not None:
        consent_owner = value.target.entity
        if newgirl:
            final_partner = _partner_consent(_history(c, game, value.consent_event), value)
            if final_partner.person not in first.partners:
                raise WorkflowError("The deciding consent belongs to an original group partner")
            consent_owner = str(first.controllers[final_partner.person.token])
        deciding_party = None
        consent_party = value.target.model_dump(mode="json")
        if mockingbird:
            replies = _session(_history(c, game, value.consent_event), value).parties
            deciding = [x for x in replies if x.event == value.consent_event]
            if len(deciding) != 1 or not any(
                x.actor == deciding[0].actor and x.controller == deciding[0].controller
                for x in first.parties
            ):
                raise WorkflowError("Recover the actual original participant's deciding answer")
            deciding_party = deciding[0]
            consent_owner = str(deciding_party.controller)
            consent_party = deciding_party.actor.model_dump(mode="json")
        consent = audit(
            value.consent_event,
            (
                "m3.mockingbird_trigger_attested"
                if mockingbird
                else prefix + "_confirmed"
                if newgirl or bonded or casualty
                else prefix + "_consent",
            ),
            consent_owner if mockingbird or newgirl else str(first.counterpart),
            **(
                dict(
                    trigger=value.session,
                    party=consent_party,
                    accept=value.accepted,
                )
                if mockingbird
                else payload
            ),
        )
        saved = get(consent, identity)
        actual = _session(consent, value)
        if mockingbird:
            if [(x.actor, x.controller) for x in actual.parties] != [
                (x.actor, x.controller) for x in first.parties
            ]:
                raise WorkflowError("Preserve the full original intimacy group")
            for item in actual.parties:
                if item.decision == "pending":
                    if item.event is not None:
                        raise WorkflowError("A pending participant has not answered")
                    continue
                if item.event is None or item.decision not in ("accepted", "declined"):
                    raise WorkflowError("Recover each participant's actual source response")
                answered = audit(
                    item.event,
                    ("m3.mockingbird_trigger_attested",),
                    str(item.controller),
                    trigger=value.session,
                    party=item.actor.model_dump(mode="json"),
                    accept=item.decision == "accepted",
                )
                if item not in _session(answered, value).parties:
                    raise WorkflowError("Preserve every independently authored source response")
            actual_answer = (
                deciding_party is not None
                and deciding_party.decision == ("accepted" if value.accepted else "declined")
                and (
                    all(x.decision == "accepted" for x in actual.parties)
                    if value.accepted
                    else any(x.decision == "declined" for x in actual.parties)
                )
                and actual.state == ("ready" if value.accepted else "declined")
            )
        elif newgirl:
            answer = _partner_consent(consent, value)
            answers = [x for x in _newgirl_consents(consent) if x.session == value.session]
            for item in answers:
                if (
                    item.person not in first.partners
                    or item.controller != first.controllers[item.person.token]
                ):
                    raise WorkflowError("Preserve every original participant's own consent")
                answered = audit(
                    item.event, (prefix + "_confirmed",), str(item.controller), **payload
                )
                if item not in _newgirl_consents(answered):
                    raise WorkflowError("Recover each original independent group consent")
            actual_answer = (
                answer.event == value.consent_event
                and answer.accepted == value.accepted
                and answer.person in first.partners
                and answer.controller == first.controllers[answer.person.token]
                and len({x.person for x in answers}) == len(answers)
                and (
                    all(x.accepted for x in answers)
                    and {x.person for x in answers} == set(first.partners)
                    if value.accepted
                    else any(not x.accepted for x in answers)
                )
                and actual.partners == first.partners
                and actual.controllers == first.controllers
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
    delegated = bonded and first.route == "delegated"
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
        session = _binding_session(game, c, bound, value)
        claimed = _grant(game, c, bound, value)
        if (
            original.action != value.action
            or original.bound_event != value.bound_event
            or session.action != value.action
            or (
                session.state != "ready"
                if mockingbird
                or (delegated and first.delegated_rule == "girl.mockingbird.sex-play")
                else session.phase != "active"
                if value.rule_id == "girl.alpha.sex-play"
                or (delegated and first.delegated_rule == "girl.alpha.sex-play")
                else (
                    session.bound_event != value.bound_event
                    or (newgirl or delegated and first.delegated_rule == "girl.newgirl.sex-play")
                    and session.phase != "bound"
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
    current_grant = _grant(game, c, state, value)
    if value.used_event is not None and delegated and first.delegated_rule == "girl.am.sex-play":
        from girlframe.services.m3_learned_bonded_am import prove_use

        prove_use(game, c, state, _session(state, value), value)
    elif value.used_event is not None:
        if (
            not bonded
            or first.route != "seven"
            or value.accepted is not True
            or value.action is not None
            or value.bound_event is not None
            or value.roll_event is not None
            or value.receipt_sha256 is not None
            or value.released_event is not None
        ):
            raise WorkflowError("An actual unrolled Bonded source has no Action or receipt")
        used = audit(
            value.used_event, ("m3.bonded_activated",), value.actor.entity, source=value.session
        )
        source = _session(used, value)
        from girlframe.engine import m3_bonded as bonded_rules

        activations = [
            x
            for x in bonded_rules.records(used, bonded_rules.Activation)
            if x.source == value.session
        ]
        if (
            get(used, identity).used_event != value.used_event
            or source.effect_event != value.used_event
            or source.action is not None
            or source.route != "seven"
            or source.phase != "results"
            or len(activations) != 1
            or activations[0].actor != value.actor
            or activations[0].event != value.used_event
            or not activations[0].account.strip()
            or _grant(game, c, used, value).used_event != value.used_event
            or _grant(game, c, used, value).claimed_source != value.session
            or current_grant.used_event != value.used_event
            or current_grant.claimed_source != value.session
            or current_grant.claimed_action is not None
            or current_grant.rolled_event is not None
        ):
            raise WorkflowError("Preserve the actual performed source and once-only diceless use")
    elif value.released_event is None and (
        current_grant.used_event is not None or current_grant.claimed_source is not None
    ):
        raise WorkflowError("A diceless lesson use needs its original performed-source evidence")
    if value.released_event is not None:
        if value.released_kind == "declined":
            if (
                value.accepted is not False
                or value.released_event != value.consent_event
                or value.action is not None
            ):
                raise WorkflowError("A source refusal is the actual counterpart's answer")
        elif value.released_kind == "withdrawn":
            if (
                not (mockingbird or bonded or casualty or alpha or oldgen or newgirl or princess)
                or value.action is not None
                or value.roll_event is not None
            ):
                raise WorkflowError("Withdraw only the actual unbound learned trigger")
            withdrawn = audit(
                value.released_event,
                (
                    "m3.bonded_learned_withdrawn"
                    if bonded
                    else "m3.casualty_learned_withdrawn"
                    if casualty
                    else "m3.alpha_sex_withdrawn"
                    if alpha
                    else "m3.oldgen_sex_withdrawn"
                    if oldgen
                    else "m3.newgirl_sex_withdrawn"
                    if newgirl
                    else "m3.princess_sex_withdrawn"
                    if princess
                    else "m3.mockingbird_trigger_withdrawn",
                ),
                value.actor.entity,
                **(
                    {"source": value.session}
                    if bonded
                    else {"session": value.session}
                    if casualty or alpha or oldgen or newgirl or princess
                    else {"trigger": value.session}
                ),
            )
            if (
                get(withdrawn, identity).released_event != value.released_event
                or (
                    getattr(_session(withdrawn, value), "phase", None)
                    if bonded or casualty or alpha or oldgen or newgirl or princess
                    else _session(withdrawn, value).state
                )
                != "withdrawn"
            ):
                raise WorkflowError("Recover the actual original owner's source withdrawal")
        elif value.released_kind in ("delegation_declined", "delegation_withdrawn"):
            from girlframe.engine import m3_bonded as bonded_rules
            from girlframe.services.m3_bonded_delegation_release import prove_release

            if not delegated or value.action is not None or value.roll_event is not None:
                raise WorkflowError("Release only the actual unused delegated child")
            parent = _session(state, value)
            prove_release(game, c, state, parent)
            releases = [
                x
                for x in bonded_rules.records(state, bonded_rules.DelegationRelease)
                if x.source == parent.id
            ]
            ended = _history(c, game, value.released_event)
            if (
                len(releases) != 1
                or releases[0].event != value.released_event
                or value.released_kind != "delegation_" + releases[0].outcome
                or get(ended, identity).released_event != value.released_event
            ):
                raise WorkflowError("Preserve this original child's own release event")
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


def admit_group_source(
    game: "GameService",
    c: Connection,
    state: GameState,
    actor: ActorRef,
    targets: tuple[ActorRef, ...],
    rule: str,
    identity: str | None,
    *,
    pending_event: str | None = None,
) -> bool:
    if identity is None:
        return False
    value = get(state, identity)
    if targets != sex_party_refs(value):
        raise WorkflowError("Use the complete original ordered group, not a controller alias")
    return admit_source(
        game, c, state, actor, value.target, rule, identity, pending_event=pending_event
    )


def _record_group(
    state: GameState,
    value: LearnedSexLink,
    actor: ActorRef,
    controller: int,
    accepted: bool,
    event: str,
) -> None:
    parties = value.parties
    own = next((x for x in parties or () if x.actor == actor), None)
    if (
        parties is None
        or own is None
        or own.controller != controller
        or own.accepted is not None
        or own.consent_event is not None
        or value.released_event is not None
        or value.action is not None
        or value.accepted is not None
    ):
        raise WorkflowError("Only this actual original group role answers its pending source once")
    changed = tuple(
        x.model_copy(update=dict(accepted=accepted, consent_event=event)) if x.actor == actor else x
        for x in parties
    )
    aggregate = (
        False if not accepted else True if all(x.accepted is True for x in changed) else None
    )
    put_learned_sex_link(
        state,
        value.model_copy(
            update=dict(
                parties=changed,
                accepted=aggregate,
                consent_event=event if aggregate is not None else None,
                **(dict(released_event=event, released_kind="declined") if not accepted else {}),
            )
        ),
    )


def _prove_group(
    game: "GameService",
    c: Connection,
    state: GameState,
    value: LearnedSexLink,
    born: LearnedSexLink,
    first: Any,
    proposed: GameState,
) -> None:
    parties = value.parties or ()
    initial = born.parties or ()
    mockingbird = value.rule_id == "girl.mockingbird.sex-play"
    if value.rule_id not in ("girl.mockingbird.sex-play", "girl.newgirl.sex-play"):
        raise WorkflowError("Use an actual released group source provider")
    expected = (
        tuple((x.actor, x.controller) for x in first.parties)
        if mockingbird
        else tuple((x, first.controllers[x.token]) for x in first.partners)
    )
    cast = (
        next((x for x in proposed.scene_casts if x.id == first.scene), None)
        if mockingbird
        else first.cast
    )
    if (
        len(parties) < 2
        or len({x.actor for x in parties}) != len(parties)
        or [(x.actor, x.controller) for x in initial] != [(x.actor, x.controller) for x in parties]
        or tuple((x.actor, x.controller) for x in parties) != expected
        or value.actor in sex_party_refs(value)
        or value.target != parties[0].actor
        or cast is None
        or fingerprint(cast) != value.cast_sha256
        or any(x.accepted is not None or x.consent_event is not None for x in initial)
        or any(
            not any(r.actor == x.actor and r.controller == x.controller for r in cast.roles)
            for x in parties
        )
    ):
        raise WorkflowError("Prove exact original group roles, controllers, cast and primary")
    answered = []
    for party in parties:
        if (party.accepted is None) != (party.consent_event is None):
            raise WorkflowError("A group answer requires its own real event")
        if party.consent_event is None:
            continue
        row = (
            c.execute(
                sa.select(t.events).where(
                    t.events.c.campaign_id == game.store.campaign_id,
                    t.events.c.id == party.consent_event,
                )
            )
            .mappings()
            .first()
        )
        payload = json.loads(row["payload_json"]) if row else {}
        snapshot = _history(c, game, party.consent_event)
        saved = get(snapshot, value.id)
        stored = next((x for x in saved.parties or () if x.actor == party.actor), None)
        actual = _session(snapshot, value)
        if mockingbird:
            item = next((x for x in actual.parties if x.actor == party.actor), None)
            native_answer = (
                item is not None
                and item.controller == party.controller
                and item.event == party.consent_event
                and item.decision == ("accepted" if party.accepted else "declined")
            )
            exact_payload = (
                payload.get("trigger") == value.session
                and payload.get("party") == party.actor.model_dump(mode="json")
                and payload.get("accept") == party.accepted
            )
        else:
            items = [
                x
                for x in _newgirl_consents(snapshot)
                if x.session == value.session and x.person == party.actor
            ]
            native_answer = (
                len(items) == 1
                and items[0].controller == party.controller
                and items[0].event == party.consent_event
                and items[0].accepted == party.accepted
            )
            exact_payload = payload.get("session") == value.session
        if (
            row is None
            or row["actor_id"] != str(party.controller)
            or row["kind"]
            != ("m3.mockingbird_trigger_attested" if mockingbird else "m3.newgirl_sex_confirmed")
            or not native_answer
            or not exact_payload
            or stored != party
        ):
            raise WorkflowError("Prove each original person's independently authored group answer")
        answered.append((row["seq"], party))
    aggregate = (
        False
        if any(x.accepted is False for x in parties)
        else (True if all(x.accepted is True for x in parties) else None)
    )
    event = max(answered, key=lambda x: x[0])[1].consent_event if aggregate is not None else None
    if value.accepted != aggregate or value.consent_event != event:
        raise WorkflowError("A group becomes ready only after every actual original yes")
    if event is not None:
        saved = get(_history(c, game, event), value.id)
        actual = _session(_history(c, game, event), value)
        if (
            saved.parties != value.parties
            or saved.accepted != aggregate
            or saved.consent_event != event
            or (actual.state if mockingbird else actual.phase)
            != ("ready" if mockingbird and aggregate else "accepted" if aggregate else "declined")
        ):
            raise WorkflowError(
                "Keep the actual last group confirmation/refusal as aggregate proof"
            )


def record_consent(
    game: "GameService", c: Connection, state: GameState, session: Any, accepted: bool, event: str
) -> None:
    if session.learned_source is None:
        return
    value = prove(game, c, state, session.learned_source)
    original = _session(_history(c, game, value.proposed_event), value)
    if (
        value.consent_event is not None
        or value.released_event is not None
        or session.counterpart != original.counterpart
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
    if value.parties is not None:
        changed = [
            x for x in _newgirl_consents(state) if x.session == value.session and x.event == event
        ]
        if len(changed) != 1:
            raise WorkflowError("Preserve this exact original partner consent event")
        item = changed[0]
        _record_group(state, value, item.person, item.controller, item.accepted, event)
        return
    answer = _partner_consent(state, value, event)
    if (
        value.consent_event is not None
        or value.released_event is not None
        or answer.event != event
        or answer.person not in session.partners
        or answer.controller != session.controllers[answer.person.token]
    ):
        raise WorkflowError("Preserve the original partner's actual own consent event")
    answers = [x for x in _newgirl_consents(state) if x.session == value.session]
    if len({x.person for x in answers}) != len(answers) or any(
        x.person not in session.partners or x.controller != session.controllers[x.person.token]
        for x in answers
    ):
        raise WorkflowError("Keep exactly one independent answer per original partner")
    if answer.accepted and {x.person for x in answers if x.accepted} != set(session.partners):
        # Partial consent neither binds the source nor spends/releases its lesson.
        return
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
    if value.parties is not None:
        changed = [x for x in trigger.parties if x.event == event]
        if len(changed) != 1 or changed[0].decision != ("accepted" if accepted else "declined"):
            raise WorkflowError("Preserve this exact actual party response event")
        item = changed[0]
        _record_group(state, value, item.actor, item.controller, accepted, event)
        return
    deciding = [x for x in trigger.parties if x.event == event]
    if (
        value.consent_event is not None
        or value.released_event is not None
        or not trigger.parties
        or trigger.parties[0].actor != value.target
        or len(deciding) != 1
        or deciding[0].decision != ("accepted" if accepted else "declined")
    ):
        raise WorkflowError("Preserve the actual original party's voluntary source response")
    if accepted and not all(x.decision == "accepted" for x in trigger.parties):
        return  # One person's consent cannot bind the group or spend its lesson.
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
    link = (
        trigger.learned_sex_source
        if hasattr(trigger, "learned_sex_source")
        else trigger.learned_source
    )
    if link is None:
        return
    value = prove(game, c, state, link)
    if (
        value.action is not None
        or value.roll_event is not None
        or value.used_event is not None
        or value.released_event
    ):
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


def consume_bonded_unrolled(
    game: "GameService", c: Connection, state: GameState, source: Any, event: str
) -> None:
    if source.learned_source is None:
        return
    value = prove(game, c, state, source.learned_source)
    grant = _grant(game, c, state, value)
    if (
        value.rule_id != "girl.bonded.sex-play"
        or source.route != "seven"
        or source.target is None
        or source.target == source.pair
        or source.action is not None
        or value.action is not None
        or source.id != value.session
        or source.actor != value.actor
        or source.target != value.target
        or value.accepted is not True
        or value.released_event is not None
        or value.used_event is not None
        or source.phase != "results"
        or source.effect_event != event
        or grant.claimed_action is not None
        or grant.rolled_event is not None
        or grant.claimed_source is not None
        or grant.used_event is not None
    ):
        raise WorkflowError("Consume only this actual accepted non-Pair performance once")
    _replace(state, grant.model_copy(update=dict(claimed_source=source.id, used_event=event)))
    put_learned_sex_link(state, value.model_copy(update=dict(used_event=event)))


def source_id(action: dict[str, Any]) -> str | None:
    """Finite metadata dispatch only: this makes no eligibility/authority claim."""
    data = action["data"]
    values = [
        meta["learned_source"]
        for key in (
            "princess_sex",
            "stim_sex",
            "alpha_sex",
            "oldgen_sex",
            "newgirl_sex",
            "vatgrown_sex",
            "bonded",
            "casualty_sex",
        )
        if (meta := data.get(key)) and meta.get("learned_source")
    ]
    if data.get("mockingbird", {}).get("learned_sex_source"):
        values.append(data["mockingbird"]["learned_sex_source"])
    for key in (
        "mockingbird",
        "princess_sex",
        "newgirl_sex",
        "oldgen_sex",
        "stim_sex",
        "alpha_sex",
        "vatgrown_sex",
        "casualty_sex",
    ):
        if data.get(key, {}).get("bonded_lesson"):
            values.append(data[key]["bonded_lesson"])
    if len(values) > 1:
        raise WorkflowError("One genuine Action has one learned intimacy source")
    return values[0] if values else None


def _binding_session(
    game: "GameService", c: Connection, state: GameState, value: LearnedSexLink
) -> Any:
    parent = _session(state, value)
    if value.rule_id == "girl.bonded.sex-play" and parent.route == "delegated":
        from girlframe.services.m3_learned_bonded_delegation import binding_child

        return binding_child(game, c, state, parent, value)
    return parent


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
    session = _binding_session(game, c, state, value)
    delegated = (
        value.rule_id == "girl.bonded.sex-play" and _session(state, value).route == "delegated"
    )
    grant = _grant(game, c, state, value)
    if (
        value.accepted is not True
        or value.action is not None
        or value.released_event is not None
        or session.action != action["id"]
        or (
            session.state != "ready"
            if value.rule_id == "girl.mockingbird.sex-play"
            or (delegated and _session(state, value).delegated_rule == "girl.mockingbird.sex-play")
            else session.phase != "active"
            if value.rule_id == "girl.alpha.sex-play"
            or (delegated and _session(state, value).delegated_rule == "girl.alpha.sex-play")
            else (
                session.bound_event != event
                or (
                    value.rule_id == "girl.newgirl.sex-play"
                    or delegated
                    and _session(state, value).delegated_rule == "girl.newgirl.sex-play"
                )
                and session.phase != "bound"
            )
        )
        or str(action["actor_id"]) != value.actor.entity
        or grant.claimed_action is not None
        or grant.rolled_event is not None
        or action["data"].get("play")
        != (
            SOURCES[_session(state, value).delegated_rule][0]
            if delegated
            else SOURCES[value.rule_id][0]
        )
        or action["data"]["prepared"].get("source_work") != session.id
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
