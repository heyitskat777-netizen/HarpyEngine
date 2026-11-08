"""Genuine Pair sources, owned human responses and actual Bonded effects."""

import json
from typing import Any, Literal
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_bonded as rules
from girlframe.engine.m2 import (
    ChoiceAnswer,
    GameState,
    IdentityState,
    PlayInput,
    shift_status,
    tier,
)
from girlframe.engine.m3_actor_bonds import change, current_ref, set_depth
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_actors import fingerprint, resolve
from girlframe.engine.m3_girl_runtime_state import has_rule
from girlframe.engine.m3_handler_consequences import active_handler
from girlframe.engine.m3_mockingbird import give_tag
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_dose_up import _audit, _cast, _native, _response, _roll_source
from girlframe.services.m3_handler_advancements import _history
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer

KINDS = ("bonded_side", "bonded_mid", "bonded_promise", "bonded_reply", "bonded_high", "bonded_low")


def _paired_basis(
    game: GameService, c: Connection, state: GameState, owner: ActorRef, marker: ActorRef
) -> tuple[IdentityState, str] | None:
    from girlframe.engine.m3_girl_runtime_state import relation_current

    sheet = state.sheets[owner.entity]
    paired = [x for x in sheet.identities if x.paired]
    if not has_rule(sheet, rules.PAIR, "BONDED"):
        if paired:
            raise WorkflowError("Recover the actual Bonded source for this protected Paired slot")
        return None
    if not relation_current(sheet, "pair", state):
        raise WorkflowError("Recover the actual current original Pair, not a replacement account")
    actual, relation = original_pair(game, c, state, owner)
    if len(paired) != 1:
        raise WorkflowError("Recover the actual unique protected Paired Identity")
    return (paired[0], relation) if actual == marker else None


def _paired_legal(
    state: GameState, owner: ActorRef, paired: IdentityState, label: str, duplicates: bool
) -> bool:
    return rules.paired_conversion_legal(
        state, owner, paired.id, label, duplicate_labels=duplicates
    )


def _man_options(
    game: GameService, c: Connection, state: GameState, value: rules.Source
) -> list[dict[str, str]]:
    from girlframe.services.m3_gender_designation import _current

    if value.kind != "sex" or value.route != "seven" or value.target is None:
        return []
    law = _current(game, c, state, value.actor)
    if law is None or law.gender != "man":
        return []
    other = state.sheets[value.target.entity]
    paired = _paired_basis(game, c, state, value.target, value.actor)
    from girlframe.services.m2_choices import ChoiceEngine

    result = []
    for tag in other.tags:
        if (
            tag.rejection_pending
            or tag.scene_used == value.cast.id
            or int(value.actor.entity) not in tag.observers
            or (tag.marked or paired is not None)
            and not _ordinary_repeat(tag.id)
        ):
            continue
        engine = ChoiceEngine(game)
        engine.prove_tag_setter(c, state, int(value.target.entity), tag)
        if tag.marked and not (
            _man_reject_allowed(state, value.target, tag)
            or _man_identities(state, value.target)
            and (
                engine.duplicate_labels()
                or not any(x.name.casefold() == tag.label.casefold() for x in other.identities)
            )
        ):
            continue
        result.append(dict(id=tag.id, label=tag.label))
    return result


def _ordinary_repeat(identity: str) -> bool:
    return not identity.startswith(
        (
            "bomb-collar:",
            "cute-uniform:",
            "stim-sex-drug:",
            "stim-sex-effect:",
            "dose-up:",
            "control-ritual:",
        )
    )


def _prove_man_mark(
    game: GameService, c: Connection, state: GameState, value: rules.Source
) -> rules.NoRollManMark | None:
    marks = [x for x in rules.records(state, rules.NoRollManMark) if x.source == value.id]
    if not marks:
        return None
    if len(marks) != 1 or value.effect_event is None or value.action is not None:
        raise WorkflowError("Preserve the one actual source-only Man mark")
    mark = marks[0]
    birth = _history(c, game, mark.event)
    history = t.m2["m2_state_history"]
    previous = c.scalar(
        sa.select(history.c.body_json).where(
            history.c.campaign_id == game.store.campaign_id,
            history.c.revision == birth.revision - 1,
        )
    )
    if previous is None:
        raise WorkflowError("Recover the actual pre-mark partner Tag source")
    before = GameState.model_validate_json(previous)
    from girlframe.services.m3_gender_designation import _current, designation

    law = designation(game, c, birth, mark.designation)
    tagged = birth.sheets.get(mark.partner.entity)
    tag = next((x for x in tagged.tags if x.id == mark.tag), None) if tagged else None
    previous_tag = next(
        (x for x in before.sheets[mark.partner.entity].tags if x.id == mark.tag), None
    )
    if (
        mark not in rules.records(birth, rules.NoRollManMark)
        or mark.id != value.id + ":man"
        or mark.actor != value.actor
        or mark.partner != value.target
        or mark.event != value.effect_event
        or mark.scene != value.cast.id
        or law.actor != value.actor
        or law.gender != "man"
        or _current(game, c, before, value.actor) != law
        or dict(id=mark.tag, label=mark.label) not in _man_options(game, c, before, value)
        or tag is None
        or not tag.marked
        or tag.scene_used != mark.scene
        or tag.label != mark.label
        or previous_tag is None
        or previous_tag.marked != mark.already_marked
    ):
        raise WorkflowError("Preserve the real original Man, partner, law and marked Tag")
    return mark


def _unrolled_choice(state: GameState, value: rules.Source) -> str:
    if value.kind == "intimacy":
        return "bonded_intimacy"
    if value.tier != "high":
        return "bonded_low"
    promised = any(
        x.source == value.id and x.kind == "bonded_promise"
        for x in rules.records(state, rules.Selection)
    )
    return "bonded_high" if promised else "bonded_promise"


def _before(game: GameService, c: Connection, birth: GameState) -> GameState:
    table = t.m2["m2_state_history"]
    body = c.scalar(
        sa.select(table.c.body_json).where(
            table.c.campaign_id == game.store.campaign_id,
            table.c.revision == birth.revision - 1,
        )
    )
    if body is None:
        raise WorkflowError("Recover the actual preceding source state")
    return GameState.model_validate_json(body)


def _man_identities(state: GameState, partner: ActorRef) -> list[IdentityState]:
    from girlframe.engine.m3_leviathan_obsession import require_identity_change, require_unlocked

    result = []
    for item in state.sheets[partner.entity].identities:
        if item.protected or item.paired or item.am_limiter:
            continue
        try:
            require_unlocked((item,), (item.id,))
            require_identity_change(state, partner, (item.id,))
        except ValueError:
            continue
        result.append(item)
    return result


def _man_reject_allowed(state: GameState, partner: ActorRef, tag: Any) -> bool:
    from girlframe.engine.m3_beneath import rejection_blocked
    from girlframe.engine.m3_girl_runtime_state import mentor_tag
    from girlframe.services.m3_vatgrown_plays import rejection_allowed

    return bool(
        rejection_allowed(state, partner, tag)
        and not rejection_blocked(state, int(partner.entity), tag.id)
        and not mentor_tag(state.sheets[partner.entity], tag, state)
    )


def _paired_resolution(
    game: GameService, c: Connection, state: GameState, value: rules.Source
) -> dict[str, Any] | None:
    mark = _prove_man_mark(game, c, state, value)
    if mark is None:
        return None
    birth = _history(c, game, mark.event)
    basis = _paired_basis(game, c, _before(game, c, birth), mark.partner, mark.actor)
    works = [x for x in rules.records(state, rules.ManPairedWork) if x.source == value.id]
    if basis is None:
        if works:
            raise WorkflowError("Only the actual marking Pair has this source conversion choice")
        return None
    paired, relation = basis
    expected = rules.ManPairedWork(
        id=mark.id + ":paired",
        source=value.id,
        mark=mark.id,
        owner=mark.partner,
        marker=mark.actor,
        controller=value.controllers[mark.actor.token],
        relation=relation,
        paired=paired.id,
        slot=paired.slot,
        tag=mark.tag,
        event=mark.event,
    )
    if works != [expected] or expected not in rules.records(birth, rules.ManPairedWork):
        raise WorkflowError("Preserve the genuine marking Pair and actual protected source slot")
    decisions = [x for x in rules.records(state, rules.ManPairedDecision) if x.work == expected.id]
    if len(decisions) > 1:
        raise WorkflowError("The actual marking Pair chooses once")
    decision = decisions[0] if decisions else None
    if decision is not None:
        saved = _history(c, game, decision.event)
        previous = _before(game, c, saved)
        current = _paired_basis(game, c, previous, expected.owner, expected.marker)
        old_tag = next(
            (x for x in previous.sheets[expected.owner.entity].tags if x.id == expected.tag), None
        )
        new_tag = next(
            (x for x in saved.sheets[expected.owner.entity].tags if x.id == expected.tag), None
        )
        new_paired = next(
            (x for x in saved.sheets[expected.owner.entity].identities if x.id == expected.paired),
            None,
        )
        _audit(game, c, decision.event, ("m3.bonded_man_paired_chosen",), expected.controller)
        if (
            decision not in rules.records(saved, rules.ManPairedDecision)
            or decision.id != expected.id + ":decision"
            or decision.marker != expected.marker
            or decision.controller != expected.controller
            or current is None
            or current[1] != expected.relation
            or current[0].id != expected.paired
            or current[0].slot != expected.slot
            or old_tag is None
            or not old_tag.marked
            or old_tag.scene_used != mark.scene
            or old_tag.rejection_pending
            or new_paired is None
        ):
            raise WorkflowError("Recover the actual marking Pair's canonical owned decision")
        if decision.convert:
            from girlframe.services.m2_choices import ChoiceEngine

            actual = current[0].model_copy(
                update=dict(
                    name=mark.label,
                    marked=current[0].id in previous.sheets[expected.owner.entity].sedation_locked,
                )
            )
            if (
                new_tag is not None
                or new_paired != actual
                or not _paired_legal(
                    previous,
                    expected.owner,
                    current[0],
                    mark.label,
                    ChoiceEngine(game).duplicate_labels(),
                )
            ):
                raise WorkflowError("Preserve the real Paired conversion, protection and sedation")
        elif new_paired != current[0] or new_tag != old_tag:
            raise WorkflowError("Declining leaves the actual marked Tag and Paired slot intact")
    return dict(
        work=expected,
        decision=decision,
        pending=decision is None,
        converted=decision is not None and decision.convert,
    )


def _man_resolution(
    game: GameService, c: Connection, state: GameState, value: rules.Source
) -> dict[str, Any] | None:
    mark = _prove_man_mark(game, c, state, value)
    if mark is None or not mark.already_marked:
        return None
    paired = _paired_resolution(game, c, state, value)
    if paired is not None and (paired["pending"] or paired["converted"]):
        return None
    works = [x for x in rules.records(state, rules.ManTagResolution) if x.source == value.id]
    birth = _history(c, game, mark.event)
    if len(works) != 1:
        raise WorkflowError("Recover the actual repeated-Tag source work")
    work = works[0]
    if (
        work not in rules.records(birth, rules.ManTagResolution)
        or work.id != mark.id + ":resolution"
        or work.mark != mark.id
        or work.partner != mark.partner
        or work.controller != value.controllers[mark.partner.token]
        or work.tag != mark.tag
        or work.event != mark.event
    ):
        raise WorkflowError("Preserve the original partner's actual Tag-resolution ownership")
    decisions = [x for x in rules.records(state, rules.ManTagDecision) if x.work == work.id]
    performances = [x for x in rules.records(state, rules.ManTagRejection) if x.work == work.id]
    if len(decisions) > 1 or len(performances) > 1:
        raise WorkflowError("Resolve this exact repeated Tag only once")
    decision = decisions[0] if decisions else None
    performance = performances[0] if performances else None
    if decision:
        saved = _history(c, game, decision.event)
        previous = _before(game, c, saved)
        old = next((x for x in previous.sheets[work.partner.entity].tags if x.id == work.tag), None)
        new = next((x for x in saved.sheets[work.partner.entity].tags if x.id == work.tag), None)
        _audit(game, c, decision.event, ("m3.bonded_man_tag_resolved",), work.controller)
        if (
            decision not in rules.records(saved, rules.ManTagDecision)
            or decision.id != work.id + ":decision"
            or decision.partner != work.partner
            or decision.controller != work.controller
            or old is None
            or not old.marked
            or old.scene_used != mark.scene
        ):
            raise WorkflowError("Recover the original partner's canonical repeated-Tag decision")
        if decision.decision == "embrace":
            replaced = next(
                (x for x in _man_identities(previous, work.partner) if x.id == decision.identity),
                None,
            )
            added = next(
                (
                    x
                    for x in saved.sheets[work.partner.entity].identities
                    if x.id == decision.replacement
                ),
                None,
            )
            if (
                replaced is None
                or added is None
                or new is not None
                or added.name != mark.label
                or added.slot != replaced.slot
                or added.marked
                != (replaced.id in previous.sheets[work.partner.entity].sedation_locked)
                or any(x.id == replaced.id for x in saved.sheets[work.partner.entity].identities)
            ):
                raise WorkflowError(
                    "Preserve the actual legal Identity replacement and Tag consumption"
                )
        elif (
            decision.identity is not None
            or decision.replacement is not None
            or new is None
            or not new.rejection_pending
            or not _man_reject_allowed(previous, work.partner, old)
        ):
            raise WorkflowError("Preserve the real owed rejection and its source restrictions")
    if performance:
        saved = _history(c, game, performance.event)
        previous = _before(game, c, saved)
        old = next((x for x in previous.sheets[work.partner.entity].tags if x.id == work.tag), None)
        _audit(game, c, performance.event, ("m3.bonded_man_tag_rejected",), work.controller)
        recorded = c.scalar(
            sa.select(t.events.c.payload_json).where(
                t.events.c.campaign_id == game.store.campaign_id, t.events.c.id == performance.event
            )
        )
        finding_id = json.loads(recorded or "{}").get("bonded_rejection_finding")
        consumed_event = None
        if finding_id:
            from girlframe.services.m3_bonded_rejection import (
                prove_finding,
                prove_rejection_consumption,
                prove_request,
            )

            finding = prove_finding(game, c, state, finding_id)
            request = prove_request(game, c, state, finding.request)
            if (
                finding.owner != work.partner
                or finding.event != performance.event
                or not finding.achieved
                or request.source != value.id
                or request.resolution != work.id
                or decision is None
                or request.decision != decision.id
            ):
                raise WorkflowError(
                    "Preserve the actual completed rejection Play and owned finding"
                )
            if old is None:
                consumed_event = prove_rejection_consumption(
                    game,
                    c,
                    state,
                    finding_id,
                    source=value.id,
                    resolution=work.id,
                    owner=work.partner,
                    tag=work.tag,
                )
        if (
            decision is None
            or decision.decision != "reject"
            or performance not in rules.records(saved, rules.ManTagRejection)
            or decision not in rules.records(previous, rules.ManTagDecision)
            or performance.id != work.id + ":performed"
            or performance.partner != work.partner
            or performance.controller != work.controller
            or not performance.account.strip()
            or consumed_event is None
            and (
                old is None
                or not old.rejection_pending
                or not _man_reject_allowed(previous, work.partner, old)
            )
            or any(x.id == work.tag for x in saved.sheets[work.partner.entity].tags)
        ):
            raise WorkflowError("Preserve the actual partner-authored performed rejection")
    return dict(
        work=work,
        decision=decision,
        performance=performance,
        pending=decision is None or decision.decision == "reject" and performance is None,
    )


def _copy(state: GameState, other: GameState) -> None:
    for name in GameState.model_fields:
        setattr(state, name, getattr(other, name))


def _access(game: GameService, c: Connection, viewer: GuildViewer, rule: str) -> None:
    gate = Access(game.store)
    gate.authorize(c, viewer, "plays", director_response=True)
    assert gate.registry is not None
    gate.registry.require_available(rule)


def original_pair(
    game: GameService,
    c: Connection,
    state: GameState,
    actor: ActorRef,
    required_rule: str = rules.PAIR,
) -> tuple[ActorRef, str]:
    sheet = state.sheets.get(actor.entity)
    if (
        actor.kind != "pilot"
        or sheet is None
        or sheet.character_id != actor.incarnation
        or not has_rule(sheet, required_rule, "BONDED")
        or sheet.pair is None
    ):
        raise WorkflowError("Use the original current Bonded Girl and actual assigned Pair")
    setup = sheet.girl_runtime.setup if sheet.girl_runtime else None
    if setup is not None and setup.pair is not None:
        original = _history(c, game, setup.source_event).sheets.get(actor.entity)
        if original is None or not original.girl_runtime or original.girl_runtime.setup != setup:
            raise WorkflowError("Recover the immutable actual Pair transition source")
        actual, source = setup.pair, setup.source_event
    else:
        outgoing = next((x for x in sheet.review.bonds if x.outgoing), None)
        if outgoing is None or outgoing.counterpart != sheet.pair:
            raise WorkflowError("Recover the actual reviewed outgoing Pair Bond")
        bond = (
            c.execute(
                sa.select(t.bond_revisions).where(
                    t.bond_revisions.c.campaign_id == game.store.campaign_id,
                    t.bond_revisions.c.id == outgoing.id,
                    t.bond_revisions.c.revision == outgoing.revision,
                )
            )
            .mappings()
            .first()
        )
        if (
            bond is None
            or bond["state"] != "accepted"
            or bond["source_id"] != actor.entity
            or bond["target_id"] != str(sheet.pair)
        ):
            raise WorkflowError("Recover the genuine accepted original Pair Bond")
        histories = c.execute(
            sa.select(t.m2["m2_state_history"].c.body_json)
            .join(
                t.events,
                sa.and_(
                    t.events.c.id == t.m2["m2_state_history"].c.event_id,
                    t.events.c.campaign_id == t.m2["m2_state_history"].c.campaign_id,
                ),
            )
            .where(
                t.events.c.campaign_id == game.store.campaign_id,
                t.events.c.kind == "m2.character_activated",
                t.events.c.actor_id == str(sheet.pair),
            )
            .order_by(t.events.c.seq)
        ).scalars()
        other = next(
            (
                s
                for raw in histories
                if (s := GameState.model_validate_json(raw).sheets.get(str(sheet.pair))) is not None
                and s.source_profile_revision == bond["target_revision"]
            ),
            None,
        )
        if other is None or not other.character_id:
            raise WorkflowError("Activate the actual original Pair; never alias a replacement")
        actual = ActorRef(kind="pilot", entity=str(sheet.pair), incarnation=other.character_id)
        source = bond["event_id"]
    if actual == actor or actual.entity != str(sheet.pair):
        raise WorkflowError("Preserve the distinct actual assigned Pair")
    _native(game, c, state, actor)
    _native(game, c, state, actual)
    return actual, source


def _people(value: rules.Source) -> tuple[ActorRef, ...]:
    values = (
        (value.actor, value.target)
        if value.kind == "sex"
        else (value.actor, value.pair, value.observer)
    )
    return tuple(dict.fromkeys(x for x in values if x is not None))


def _contact(game: GameService, c: Connection, state: GameState, value: rules.Source) -> None:
    from girlframe.services.m3_changeling_sex import admit_contact

    remote = False
    if value.changeling_source is not None:
        if value.kind != "sex" or value.target is None:
            raise WorkflowError("Psychic contact belongs only to this genuine Sex source")
        remote = admit_contact(
            game, c, state, value.actor, value.target, rules.SEX, value.changeling_source
        )
    cast = _cast(game, c, state, value.cast.channel)
    if fingerprint(cast) != fingerprint(value.cast):
        raise WorkflowError("Recover the unchanged genuine source cast")
    views = {x: _native(game, c, state, x) for x in _people(value)}
    if any(
        v.cell is None
        or v.vessel_id is None
        or value.controllers.get(ref.token) != v.controller
        or value.vessels.get(ref.token) != v.vessel_id
        or not any(r.actor == ref and r.controller == v.controller for r in cast.roles)
        for ref, v in views.items()
    ):
        raise WorkflowError("SOURCE_BODY_REQUIRED: use actual native original bodies and cast")
    if value.kind == "side":
        if not value.apart or any(
            v.custody not in (None, "free") or v.offstage_source for v in views.values()
        ):
            raise WorkflowError("Confirm that these actual original people really are apart")
    elif not remote and (
        any(v.inside_frame is not False for v in views.values())
        or len({x.cell for x in views.values()}) != 1
    ):
        raise WorkflowError("Use the actual voluntary original people together here")


def _consents(game: GameService, c: Connection, state: GameState, value: rules.Source) -> None:
    if value.kind != "sex":
        return
    responses = tuple(x for x in rules.records(state, rules.Consent) if x.source == value.id)
    for item in responses:
        if (
            item.person != value.target
            or item.controller != value.controllers[item.person.token]
            or item not in rules.records(_history(c, game, item.event), rules.Consent)
        ):
            raise WorkflowError("Preserve the actual counterpart's voluntary source response")
        _audit(game, c, item.event, ("m3.bonded_confirmed",), item.controller)
    if value.phase not in ("invited", "declined") and (
        len(responses) != 1 or not responses[0].accepted
    ):
        raise WorkflowError("The actual counterpart must confirm their own voluntary intimacy")


def prove(game: GameService, c: Connection, state: GameState, identity: str) -> rules.Source:
    value = rules.get(state, identity)
    if value.changeling_source is not None:
        from girlframe.services.m3_changeling_sex import prove_source_link

        if value.target is None:
            raise WorkflowError("Preserve the genuine original psychic counterpart")
        prove_source_link(
            game, c, state, value.changeling_source, value.id, value.actor, value.target, rules.SEX
        )

    birth = _history(c, game, value.event)
    born = rules.get(birth, identity)
    stable = (
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
        "apart",
        "event",
        "account",
        "route",
        "delegated_rule",
        "changeling_source",
    )
    if any(getattr(value, k) != getattr(born, k) for k in stable):
        raise WorkflowError("Preserve the genuine original Bonded source and people")
    rule = dict(side=rules.SIDE, intimacy=rules.INTIMACY, sex=rules.SEX)[value.kind]
    actual, source = original_pair(game, c, birth, value.actor, rule)
    if actual != value.pair or source != value.pair_source:
        raise WorkflowError("Preserve the source-time original Pair, not their current account")
    _audit(game, c, value.event, ("m3.bonded_proposed",), int(value.actor.entity))
    _consents(game, c, state, value)
    actions = c.scalars(
        sa.select(t.m2["m2_actions"].c.id).where(
            t.m2["m2_actions"].c.campaign_id == game.store.campaign_id,
            sa.func.json_extract(t.m2["m2_actions"].c.body_json, "$.bonded.source") == identity,
        )
    ).all()
    if (
        len(actions) > 1
        or actions
        and value.action != actions[0]
        or value.action is not None
        and value.phase in ("invited", "accepted", "declined")
    ):
        raise WorkflowError("Never clear or rebind an actual confirmed Bonded source")
    if value.action:
        action = game.action(c, value.action)
        meta = action["data"].get("bonded", {})
        bound = rules.get(_history(c, game, value.bound_event or ""), identity)
        if (
            bound.action != value.action
            or str(action["actor_id"]) != value.actor.entity
            or action["scene_id"] != value.cast.id
            or int(action["channel_id"]) != value.cast.channel
            or action["data"]["play"]
            != (rules.SIDE_PLAY if value.kind == "side" else rules.SEX_PLAY)
            or bound.bound_event != value.bound_event
            or meta.get("source") != identity
            or meta.get("actor") != value.actor.model_dump(mode="json")
            or meta.get("pair") != value.pair.model_dump(mode="json")
            or meta.get("cast") != value.cast.model_dump(mode="json")
            or meta.get("target")
            != (value.target.model_dump(mode="json") if value.target else None)
            or meta.get("cast_sha256") != fingerprint(value.cast)
            or action["data"].get("character_ids", {}).get(value.actor.entity)
            != value.actor.incarnation
            or action["data"].get("prepared", {}).get("source_work") != identity
        ):
            raise WorkflowError("Recover the actual confirmed source Play binding")
        if not value.effect_event and any(
            x.source == identity for x in rules.records(state, rules.Selection)
        ):
            raise WorkflowError("Preserve the actual source result before its responses")
        if value.effect_event:
            _, total = _roll_source(game, c, action)
            effect = rules.get(_history(c, game, value.effect_event), identity)
            if value.tier != tier(total) or effect.effect_event != value.effect_event:
                raise WorkflowError("Preserve the real final receipt and source result")
    elif value.effect_event:
        effect = rules.get(_history(c, game, value.effect_event), identity)
        _audit(game, c, value.effect_event, ("m3.bonded_activated",), int(value.actor.entity))
        activation = next(
            (x for x in rules.records(state, rules.Activation) if x.source == identity), None
        )
        if (
            activation is None
            or activation.actor != value.actor
            or activation.event != value.effect_event
            or not activation.account.strip()
            or activation
            not in rules.records(_history(c, game, activation.event), rules.Activation)
        ):
            raise WorkflowError("Preserve the actual performed diceless source and its author")
        man = _prove_man_mark(game, c, state, value)
        if (
            effect.effect_event != value.effect_event
            or effect.tier != value.tier
            or (value.route == "seven" and value.tier != ("high" if man else "low"))
            or value.route != "seven"
            and value.kind != "intimacy"
        ):
            raise WorkflowError("Unrolled source results never fabricate a Sex receipt")
        _paired_resolution(game, c, state, value)
        _man_resolution(game, c, state, value)
    for item in rules.records(state, rules.Selection):
        if item.source != identity:
            continue
        saved = next(
            (
                x
                for x in rules.records(_history(c, game, item.event), rules.Selection)
                if x.id == item.id
            ),
            None,
        )
        if (
            saved != item
            or item.person not in _people(value)
            or item.controller != value.controllers[item.person.token]
        ):
            raise WorkflowError("Preserve every original person's immutable owned choice")
        if item.action:
            answer = _response(
                game, c, item.action, item.id, item.event, item.controller, item.kind
            )
            actual_row = (
                c.execute(
                    sa.select(t.m2["m2_choices"]).where(
                        t.m2["m2_choices"].c.campaign_id == game.store.campaign_id,
                        t.m2["m2_choices"].c.id == item.id,
                    )
                )
                .mappings()
                .one()
            )
            if json.loads(actual_row["body_json"]).get("request") != item.request:
                raise WorkflowError("Preserve the real Pair request and its owned reply")
            if (
                answer.options != item.options
                or answer.denied != item.identities
                or answer.text != item.text
            ):
                raise WorkflowError("Preserve the exact canonical response and source cost")
        else:
            _audit(game, c, item.event, ("m3.bonded_selected",), item.controller)
    for detail in rules.records(state, rules.Detail):
        if detail.source != identity:
            continue
        born_detail = next(
            (
                x
                for x in rules.records(_history(c, game, detail.event), rules.Detail)
                if x.id == detail.id
            ),
            None,
        )
        reply = next(
            (
                x
                for x in rules.records(state, rules.Selection)
                if x.source == identity
                and x.kind == "bonded_reply"
                and x.request == detail.kind
                and x.event == detail.event
                and x.options == ("give",)
            ),
            None,
        )
        if (
            born_detail != detail
            or detail.actor != value.pair
            or detail.target != value.actor
            or detail.controller != value.controllers.get(value.pair.token)
            or reply is None
            or detail.account != _text(reply.text).get("content", _text(reply.text)["account"])
        ):
            raise WorkflowError(
                "Preserve the real Pair-authored secret, Order or appearance source"
            )
    for binding in rules.records(state, rules.OrderBinding):
        if binding.source != identity:
            continue
        born_binding = next(
            (
                x
                for x in rules.records(_history(c, game, binding.event), rules.OrderBinding)
                if x.id == binding.id
            ),
            None,
        )
        binding_detail = next(
            (x for x in rules.records(state, rules.Detail) if x.id == binding.detail), None
        )
        order = (
            c.execute(
                sa.select(t.m2["m2_orders"]).where(
                    t.m2["m2_orders"].c.campaign_id == game.store.campaign_id,
                    t.m2["m2_orders"].c.id == binding.order,
                )
            )
            .mappings()
            .first()
        )
        if (
            born_binding != binding
            or binding_detail is None
            or order is None
            or order["issuer_id"] != binding.actor.entity
            or order["target_id"] != binding.target.entity
            or (binding.actor, binding.target) != (binding_detail.actor, binding_detail.target)
            or json.loads(order["body_json"]).get("text") != binding_detail.account
        ):
            raise WorkflowError(
                "Preserve the actual requested Order row and original issuer/recipient"
            )
    if (
        value.phase == "complete"
        and value.kind == "sex"
        and value.tier == "mid"
        and not _ready_to_close(state, value)
    ):
        raise WorkflowError("Complete each actual Pair reply and genuine Order before closing")
    if value.phase == "complete":
        if not value.completed_event:
            raise WorkflowError("Preserve the actual completed source event")
        completed = rules.get(_history(c, game, value.completed_event), identity)
        if completed.completed_event != value.completed_event or completed.phase != "complete":
            raise WorkflowError("Preserve real completion, never a mutable acknowledgment")
    for help_record in rules.records(state, rules.PairHelp):
        if help_record.source != identity:
            continue
        if (
            help_record.actor != value.actor
            or help_record.pair != value.pair
            or help_record.controller != int(value.pair.entity)
            or help_record
            not in rules.records(_history(c, game, help_record.event), rules.PairHelp)
        ):
            raise WorkflowError("Preserve the original Pair's actual help source")
        _audit(game, c, help_record.event, ("m3.bonded_helped",), help_record.controller)
    return value


def prepare(
    game: GameService,
    c: Connection,
    viewer: GuildViewer,
    state: GameState,
    prepared: PlayInput,
    channel: int,
) -> dict[str, Any]:
    rule = rules.SIDE if prepared.play == rules.SIDE_PLAY else rules.SEX
    _access(game, c, viewer, rule)
    value = prove(game, c, state, prepared.source_work or "")
    expected = rules.SIDE_PLAY if value.kind == "side" else rules.SEX_PLAY
    if (
        prepared.play != expected
        or value.kind == "intimacy"
        or value.route != "pair"
        or value.phase != "accepted"
        or value.actor != current_ref(state, viewer.user_id)
        or channel != value.cast.channel
        or prepared.target is not None
        or prepared.target_actor is not None
        or prepared.parent
        or prepared.order_id
        or prepared.off_duty_id
    ):
        raise WorkflowError("Use the genuine accepted original Bonded source")
    _contact(game, c, state, value)
    handler = active_handler(state)
    if handler is None or value.cast.facilitator is None:
        raise WorkflowError("Recover the actual original Handler and source table")
    return dict(
        source=value.id,
        actor=value.actor.model_dump(mode="json"),
        pair=value.pair.model_dump(mode="json"),
        target=value.target.model_dump(mode="json") if value.target else None,
        cast=value.cast.model_dump(mode="json"),
        cast_sha256=fingerprint(value.cast),
        table=sorted({x.controller for x in value.cast.roles} | {value.cast.facilitator}),
        handler=handler.model_dump(mode="json"),
        handler_controller=resolve(
            state, handler, profiles(c, game.store.campaign_id), require_current_profile=False
        ).controller,
    )


def bind(state: GameState, action: dict[str, Any], event: str | None = None) -> None:
    value = rules.get(state, action["data"]["bonded"]["source"])
    if not event or value.action or value.phase != "accepted":
        raise WorkflowError("Bind the genuine source once to the actual confirmed Play")
    rules.put(
        state, value.model_copy(update=dict(action=action["id"], bound_event=event, phase="bound"))
    )


def authorize(
    game: GameService, c: Connection, viewer: GuildViewer, action: dict[str, Any]
) -> None:
    value = rules.get(load_state(c, game.store.campaign_id), action["data"]["bonded"]["source"])
    _access(game, c, viewer, rules.SIDE if value.kind == "side" else rules.SEX)
    if viewer.user_id not in action["data"]["bonded"]["table"]:
        raise WorkflowError("Only the original source table owns this response")


def pre_roll(
    game: GameService, c: Connection, viewer: GuildViewer, state: GameState, action: dict[str, Any]
) -> None:
    value = prove(game, c, state, action["data"]["bonded"]["source"])
    if value.phase != "bound" or value.actor != current_ref(state, viewer.user_id):
        raise WorkflowError("Resume the saved source without another roll")
    _contact(game, c, state, value)


def sex_parties(state: GameState, action: dict[str, Any]) -> tuple[ActorRef, ...]:
    value = rules.get(state, action["data"]["bonded"]["source"])
    return (value.actor, value.target) if value.target is not None and value.kind == "sex" else ()


def _pending(game: GameService, c: Connection, action: dict[str, Any], value: rules.Source) -> None:
    if value.kind == "side":
        game.request(c, action, int(value.actor.entity), "bonded_side", {})
    else:
        kind = (
            "bonded_mid"
            if value.tier == "mid"
            else "bonded_promise"
            if value.tier == "high"
            else "bonded_low"
        )
        person = value.actor if value.tier in ("mid", "high") else value.target
        assert person is not None
        game.request(c, action, value.controllers[person.token], kind, {})


def results(game: GameService, c: Connection, state: GameState, action: dict[str, Any]) -> None:
    value = rules.get(state, action["data"]["bonded"]["source"])
    if value.effect_event:
        raise WorkflowError("Resume the original Bonded result without duplicating it")
    if value.kind == "sex":
        from girlframe.services.m3_gender_designation import offer_animal_tags

        if offer_animal_tags(game, c, state, action):
            action["data"]["gender_sex_deferred"] = True
            return
    _, total = _roll_source(game, c, action)
    event = action["data"]["response_event"]
    value = value.model_copy(update=dict(effect_event=event, tier=tier(total), phase="results"))
    rules.put(state, value)
    if value.kind == "side" and value.tier == "low":
        shift_status(state, int(value.actor.entity), 1)
    if value.kind == "sex" and value.tier == "mid":
        _copy(state, set_depth(state, value.actor, value.pair, 2, event))
    _pending(game, c, action, value)


def _text(text: str) -> dict[str, str]:
    try:
        value = json.loads(text)
    except ValueError:
        value = {"account": text}
    if (
        not isinstance(value, dict)
        or any(not isinstance(k, str) or not isinstance(v, str) for k, v in value.items())
        or not value.get("account", "").strip()
        or len(text) > 7000
    ):
        raise WorkflowError("Author your own actual account and source fields")
    return value


def _give(
    game: GameService,
    c: Connection,
    state: GameState,
    value: rules.Source,
    giver: ActorRef,
    target: ActorRef,
    label: str,
    event: str,
    suffix: str,
) -> None:
    _copy(
        state,
        give_tag(
            state,
            profiles(c, game.store.campaign_id),
            target,
            giver,
            label,
            value.id + ":" + suffix + ":" + event,
            event,
            tuple(sorted(set(value.controllers.values()))),
        ),
    )


def _complete(state: GameState, value: rules.Source, event: str) -> rules.Source:
    updated = value.model_copy(update=dict(phase="complete", completed_event=event))
    rules.put(state, updated)
    return updated


def _detail(state: GameState, value: rules.Source, kind: str, account: str, event: str) -> None:
    assert value.target is not None
    rules.put(
        state,
        rules.Detail.model_validate(
            dict(
                id=value.id + ":" + kind,
                source=value.id,
                kind=kind,
                actor=value.pair,
                target=value.actor,
                controller=value.controllers[value.pair.token],
                account=account,
                event=event,
            )
        ),
    )


def _choice_person(value: rules.Source, kind: str) -> ActorRef:
    if kind in ("bonded_side", "bonded_mid", "bonded_promise", "bonded_intimacy"):
        return value.actor
    assert value.target is not None
    return value.target


def _select(
    game: GameService,
    c: Connection,
    state: GameState,
    value: rules.Source,
    kind: str,
    answer: ChoiceAnswer,
    event: str,
    identity: str,
    action: dict[str, Any] | None,
    request: str | None = None,
) -> None:
    if (
        answer.fields
        or answer.flag is not None
        or answer.member is not None
        or answer.number is not None
    ):
        raise WorkflowError("Use only this actual owned Bonded response shape")
    if answer.denied and kind not in ("bonded_mid", "bonded_high", "bonded_low"):
        raise WorkflowError("This result has no private Identity or Tag selector")
    fields = _text(answer.text)
    options = answer.options
    person = _choice_person(value, kind)
    if value.phase != "results" or len(set(options)) != len(options):
        raise WorkflowError("Choose the actual saved source result once")
    valid = projection_options(state, value, kind)
    if any(x not in valid for x in options):
        raise WorkflowError("Select only actual available printed outcomes")
    selection = rules.Selection(
        id=identity,
        source=value.id,
        action=action["id"] if action else None,
        person=person,
        controller=value.controllers[person.token],
        kind=kind,
        options=options,
        identities=answer.denied,
        request=request,
        text=answer.text,
        event=event,
    )
    if kind == "bonded_side":
        if (
            len([x for x in options if x in ("stay", "arrive")]) != 1
            or value.tier == "high"
            and "arrive" not in options
            or "weapon" in options
            and (value.tier != "high" or "arrive" not in options)
        ):
            raise WorkflowError("Choose the actual printed stay or arrival result")
        if "weapon" in options and (
            not fields.get("weapon_name", "").strip()
            or not fields.get("weapon_description", "").strip()
        ):
            raise WorkflowError("Describe the actual weapon you needed and found")
        rules.put(state, selection)
        if "arrive" in options:
            from girlframe.services.m3_bonded_support import arrive

            arrive(game, c, state, value, event, fields["account"], weapon="weapon" in options)
        elif not fields.get("question", "").strip():
            raise WorkflowError("Ask your Pair when she is coming for you")
        _complete(state, value, event)
    elif kind == "bonded_mid":
        if len(answer.denied) != len(options) or len(set(answer.denied)) != len(answer.denied):
            raise WorkflowError("Unmark one distinct actual marked Identity for each chosen option")
        sheet = state.sheets[value.actor.entity]
        marked = {
            x.id: x for x in sheet.identities if x.marked and x.id not in sheet.sedation_locked
        }
        if any(x not in marked for x in answer.denied):
            raise WorkflowError("Choose actual marked Identities available to unmark")
        for entry in answer.denied:
            marked[entry].marked = False
        rules.put(state, selection)
        if action is None:
            raise WorkflowError("Use the actual rolled Pair Sex request source")
        for option in options:
            game.request(
                c, action, value.controllers[value.pair.token], "bonded_reply", {"request": option}
            )
        if not options:
            _complete(state, value, event)
    elif kind == "bonded_reply":
        if (
            request not in ("tag", "secret", "order", "appearance")
            or len(options) != 1
            or answer.denied
        ):
            raise WorkflowError("Reply only to this actual requested shaping action")
        asked = next(
            (
                x
                for x in rules.records(state, rules.Selection)
                if x.source == value.id and x.kind == "bonded_mid"
            ),
            None,
        )
        if (
            asked is None
            or request not in asked.options
            or any(
                x.source == value.id and x.kind == kind and x.request == request
                for x in rules.records(state, rules.Selection)
            )
        ):
            raise WorkflowError("Preserve the original question and one actual Pair response")
        if options == ("give",):
            content = fields.get("content", fields["account"])
            if not content.strip():
                raise WorkflowError("The actual Pair authors their own performed reply")
            if request == "tag":
                _give(
                    game, c, state, value, value.pair, value.actor, content, event, "requested-tag"
                )
            else:
                _detail(state, value, request, content, event)
        rules.put(state, selection)
        if _ready_to_close(state, value):
            _complete(state, value, event)
    elif kind == "bonded_promise":
        if (
            options != ("promise",)
            or answer.denied
            or (action is None and _prove_man_mark(game, c, state, value) is None)
        ):
            raise WorkflowError("Author your actual promise to protect her")
        rules.put(state, selection)
        if action is not None:
            game.request(c, action, value.controllers[value.pair.token], "bonded_high", {})
    elif kind == "bonded_high":
        assert value.target is not None
        tags = {x.id: x for x in state.sheets[value.target.entity].tags}
        if (
            options
            or len(set(answer.denied)) != len(answer.denied)
            or any(x not in tags for x in answer.denied)
        ):
            raise WorkflowError(
                "The actual Pair chooses any of her own actual Tags, including none"
            )
        for index, tag in enumerate(answer.denied):
            _give(
                game,
                c,
                state,
                value,
                value.target,
                value.actor,
                tags[tag].label,
                event,
                "high-tag:" + str(index),
            )
        rules.put(state, selection)
        from girlframe.services.m3_bonded_support import place_above

        place_above(state, value.actor, value.target)
        _complete(state, value, event)
    elif kind == "bonded_low":
        if len(options) != 1:
            raise WorkflowError("The actual intimate counterpart owns continuing or stopping")
        assert value.target is not None
        if options == ("continue",):
            other = state.sheets[value.target.entity]
            selected = [
                x
                for x in other.identities
                if x.id in answer.denied and x.marked and x.id not in other.sedation_locked
            ]
            if len(answer.denied) != 1 or len(selected) != 1:
                raise WorkflowError("Unmark one of your actual available marked Identities")
            selected[0].marked = False
            shift_status(state, int(value.actor.entity), 1)
        elif answer.denied:
            raise WorkflowError("Stopping weakens the real Bond; it does not unmark an Identity")
        else:
            _copy(state, change(state, value.actor, value.target, -1, event))
        rules.put(state, selection)
        _complete(state, value, event)
    elif kind == "bonded_intimacy":
        if len(options) != 1 or value.observer is None:
            raise WorkflowError("Choose the actual witnessed-affection outcome")
        if options == ("pair_tag",):
            _give(
                game,
                c,
                state,
                value,
                value.actor,
                value.pair,
                fields.get("tag", fields["account"]),
                event,
                "affection-pair-tag",
            )
        elif options == ("observer_tag",):
            from girlframe.engine.m2 import higher

            if not (
                higher(state, int(value.actor.entity), int(value.observer.entity))
                or higher(state, int(value.pair.entity), int(value.observer.entity))
            ):
                raise WorkflowError("Only an actual lower-Status onlooker can receive this Tag")
            _give(
                game,
                c,
                state,
                value,
                value.actor,
                value.observer,
                fields.get("tag", fields["account"]),
                event,
                "affection-observer-tag",
            )
        elif options == ("child",):
            play = fields.get("play", "")
            if play not in ("flirt", "brutalize", "snoop") or not fields.get("context", "").strip():
                raise WorkflowError(
                    "Describe one actual legal triggered Play against this onlooker"
                )
            rules.put(
                state,
                rules.Child(
                    id=value.id + ":child",
                    source=value.id,
                    actor=value.actor,
                    target=value.observer,
                    parent=None,
                    play=play,
                    account=fields["context"],
                    event=event,
                ),
            )
            rules.put(state, value.model_copy(update=dict(phase="child")))
        rules.put(state, selection)
        if options != ("child",):
            _complete(state, value, event)
    else:
        raise WorkflowError("Use the actual source-owned Bonded choice")


def _ready_to_close(state: GameState, value: rules.Source) -> bool:
    asked = next(
        (
            x
            for x in rules.records(state, rules.Selection)
            if x.source == value.id and x.kind == "bonded_mid"
        ),
        None,
    )
    answered = {
        x.request
        for x in rules.records(state, rules.Selection)
        if x.source == value.id and x.kind == "bonded_reply"
    }
    return bool(
        asked is not None and set(asked.options) <= answered and not _unbound_orders(state, value)
    )


def _unbound_orders(state: GameState, value: rules.Source) -> tuple[rules.Detail, ...]:
    return tuple(
        x
        for x in rules.records(state, rules.Detail)
        if x.source == value.id
        and x.kind == "order"
        and not any(y.detail == x.id for y in rules.records(state, rules.OrderBinding))
    )


def apply_choice(
    game: GameService,
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    row: Any,
    answer: ChoiceAnswer,
) -> bool:
    if row["kind"] not in KINDS:
        return False
    value = prove(game, c, state, action["data"]["bonded"]["source"])
    person = _choice_person(value, row["kind"])
    if str(row["actor_id"]) != str(value.controllers[person.token]):
        raise WorkflowError("Only the original actual chooser owns this response")
    _select(
        game,
        c,
        state,
        value,
        row["kind"],
        answer,
        action["data"]["response_event"],
        row["id"],
        action,
        json.loads(row["body_json"]).get("request"),
    )
    action["data"].setdefault("result", {}).update(
        source=value.id, phase=rules.get(state, value.id).phase
    )
    return True


def projection_options(state: GameState, value: rules.Source, kind: str) -> dict[str, str]:
    if kind == "bonded_side":
        return (
            dict(arrive="Be there now, close enough to touch", weapon="I needed and found a weapon")
            if value.tier == "high"
            else dict(
                stay="Stay, fidget and ask when she comes",
                arrive="Be there now, close enough to touch",
            )
        )
    if kind == "bonded_promise":
        return dict(promise="Take hold of her and promise to protect her")
    if kind == "bonded_mid":
        return dict(
            tag="Ask her to give me a Tag",
            secret="Ask her to tell me a secret",
            order="Ask her to give me an Order",
            appearance="Ask her to change my appearance",
        )
    if kind == "bonded_reply":
        return dict(give="Author my actual reply/performed shaping", decline="Decline the request")
    if kind == "bonded_low":
        return {
            "continue": "Keep going, lower her Status and unmark my Identity",
            "stop": "Stop and weaken our actual Bond",
        }
    if kind == "bonded_intimacy":
        return dict(
            draw_back="Draw back at the last moment",
            pair_tag="Give my Pair a Tag",
            child="Make an actual Play against the onlooker",
            observer_tag="Give an actual lower-Status onlooker a Tag",
        )
    return {}


def projection(
    game: GameService, c: Connection, viewer: GuildViewer, action: dict[str, Any], row: Any
) -> dict[str, Any]:
    value = prove(
        game, c, load_state(c, game.store.campaign_id), action["data"]["bonded"]["source"]
    )
    state = load_state(c, game.store.campaign_id)
    if viewer.user_id != int(row["actor_id"]):
        raise WorkflowError("Only the original chooser sees this private resource selector")
    person = _choice_person(value, row["kind"])
    sheet = state.sheets[person.entity]
    return dict(
        source=value.id,
        kind=row["kind"],
        tier=value.tier,
        options=list(projection_options(state, value, row["kind"]).items()),
        request=json.loads(row["body_json"]).get("request"),
        identities=[
            dict(id=x.id, label=x.name)
            for x in sheet.identities
            if x.marked and x.id not in sheet.sedation_locked
        ],
        tags=[dict(id=x.id, label=x.label) for x in sheet.tags]
        if row["kind"] == "bonded_high"
        else [],
        maximum=4
        if row["kind"] == "bonded_mid"
        else 2
        if row["kind"] == "bonded_side" and value.tier == "high"
        else 1,
    )


def _child(game: GameService, c: Connection, state: GameState, identity: str) -> rules.Child:
    value = next((x for x in rules.records(state, rules.Child) if x.id == identity), None)
    if value is None:
        raise WorkflowError("Recover the actual witnessed-affection child source")
    source = prove(game, c, state, value.source)
    born = next(
        (x for x in rules.records(_history(c, game, value.event), rules.Child) if x.id == identity),
        None,
    )
    if (
        born is None
        or any(
            getattr(born, k) != getattr(value, k)
            for k in ("id", "source", "actor", "target", "parent", "play", "account", "event")
        )
        or source.kind != "intimacy"
        or value.actor != source.actor
        or value.target != source.observer
    ):
        raise WorkflowError("Preserve the actual child actor, onlooker and observed affection")
    if value.child:
        action = game.action(c, value.child)
        meta = action["data"].get("bonded_child", {})
        bound = next(
            (
                x
                for x in rules.records(_history(c, game, value.bound_event or ""), rules.Child)
                if x.id == identity
            ),
            None,
        )
        if (
            bound is None
            or bound.child != value.child
            or action["data"]["play"] != value.play
            or meta.get("child") != identity
            or action["data"].get("character_ids", {}).get(value.actor.entity)
            != value.actor.incarnation
        ):
            raise WorkflowError("Recover the real source-bound child Play")
    return value


def child_source(
    game: GameService,
    c: Connection,
    viewer: GuildViewer,
    state: GameState,
    prepared: PlayInput,
    channel: int,
) -> dict[str, Any] | None:
    if not any(x.id == prepared.source_work for x in rules.records(state, rules.Child)):
        return None
    _access(game, c, viewer, rules.INTIMACY)
    value = _child(game, c, state, prepared.source_work or "")
    source = prove(game, c, state, value.source)
    if (
        source.phase != "child"
        or value.child
        or value.completed_event
        or value.actor != current_ref(state, viewer.user_id)
        or prepared.play != value.play
        or channel != source.cast.channel
        or prepared.parent
        or prepared.order_id
        or prepared.off_duty_id
        or not prepared.trigger_confirmed
        or prepared.context != value.account
        or prepared.target_actor not in (None, value.target)
        or prepared.target not in (None, int(value.target.entity))
    ):
        raise WorkflowError("Use the actual original triggered Play against this onlooker")
    _contact(game, c, state, source)
    return dict(
        child=value.id,
        source=source.id,
        actor=value.actor.model_dump(mode="json"),
        target=value.target.model_dump(mode="json"),
        cast=source.cast.model_dump(mode="json"),
        table=sorted(
            set(source.controllers.values())
            | ({source.cast.facilitator} if source.cast.facilitator else set())
        ),
    )


def bind_child(
    game: GameService, c: Connection, state: GameState, action: dict[str, Any], event: str
) -> None:
    meta = action["data"]["bonded_child"]
    value = _child(game, c, state, meta["child"])
    if (
        value.child
        or action["actor_id"] != value.actor.entity
        or action["data"]["play"] != value.play
    ):
        raise WorkflowError("Bind the genuine actual child once")
    rules.put(state, value.model_copy(update=dict(child=action["id"], bound_event=event)))


def complete_child(
    game: GameService, c: Connection, state: GameState, action: dict[str, Any], event: str
) -> None:
    value = _child(game, c, state, action["data"]["bonded_child"]["child"])
    if value.child != action["id"] or action["state"] != "complete":
        raise WorkflowError("Resolve the real child effects before closing witnessed affection")
    if value.completed_event:
        return
    _, total = _roll_source(game, c, action)
    source = rules.get(state, value.source)
    if total >= 8:
        rules.put(
            state,
            rules.Silence(
                id=value.id + ":silence",
                source=source.id,
                child=value.id,
                actor=source.actor,
                pair=source.pair,
                observer=value.target,
                observation=source.id,
                event=event,
            ),
        )
    rules.put(state, value.model_copy(update=dict(completed_event=event, total=total)))
    _complete(state, source, event)


def synchronize(game: GameService, c: Connection, action: dict[str, Any], event: str) -> None:
    if action["data"].get("bonded_child") and action["state"] == "complete":
        state = load_state(c, game.store.campaign_id)
        value = _child(game, c, state, action["data"]["bonded_child"]["child"])
        if value.completed_event:
            return
        receipt_event = str(uuid4())
        complete_child(game, c, state, action, receipt_event)
        game.event(
            c,
            int(action["actor_id"]),
            "bonded-child:" + value.id,
            "m3.bonded_child_completed",
            state,
            event_id=receipt_event,
            action_id=action["id"],
            source=value.source,
            completion_event=event,
        )

        source = rules.get(state, value.source)
        if source.changeling_source is not None:
            from girlframe.services.m3_changeling_sex import synchronize_session

            synchronize_session(game, c, state, source.id, receipt_event)


def order_authority(
    game: GameService, c: Connection, state: GameState, issuer: int, target: int, instruction: str
) -> dict[str, Any] | None:
    actor, recipient = current_ref(state, issuer), current_ref(state, target)
    for detail in rules.records(state, rules.Detail):
        if (
            detail.kind != "order"
            or detail.actor != actor
            or detail.target != recipient
            or detail.account != instruction
            or any(x.detail == detail.id for x in rules.records(state, rules.OrderBinding))
        ):
            continue
        source = prove(game, c, state, detail.source)
        if source.phase != "results":
            raise WorkflowError("Use the original still-pending real Pair Sex Order")
        return dict(
            detail=detail.id,
            source=detail.source,
            actor=actor.model_dump(mode="json"),
            target=recipient.model_dump(mode="json"),
            instruction=instruction,
            source_event=detail.event,
        )
    return None


def bind_order(
    game: GameService,
    c: Connection,
    state: GameState,
    authority: dict[str, Any],
    order_id: str,
    event: str,
) -> None:
    detail = next(
        (x for x in rules.records(state, rules.Detail) if x.id == authority.get("detail")), None
    )
    if detail is None or authority != order_authority(
        game, c, state, int(detail.actor.entity), int(detail.target.entity), detail.account
    ):
        raise WorkflowError("Preserve the exact pending instruction and actual Pair source")
    rules.put(
        state,
        rules.OrderBinding(
            id=detail.id + ":issued",
            detail=detail.id,
            source=detail.source,
            actor=detail.actor,
            target=detail.target,
            order=order_id,
            event=event,
        ),
    )
    source = rules.get(state, detail.source)
    if _ready_to_close(state, source):
        _complete(state, source, event)


def valid_order(game: GameService, c: Connection, state: GameState, body: dict[str, Any]) -> bool:
    authority = body.get("bonded")
    if not isinstance(authority, dict):
        return False
    detail = next(
        (x for x in rules.records(state, rules.Detail) if x.id == authority.get("detail")), None
    )
    if detail is None:
        return False
    prove(game, c, state, detail.source)
    binding = next(
        (
            x
            for x in rules.records(state, rules.OrderBinding)
            if x.detail == detail.id and x.order == body.get("id")
        ),
        None,
    )
    if binding is None:
        return False
    born = next(
        (
            x
            for x in rules.records(_history(c, game, binding.event), rules.OrderBinding)
            if x.id == binding.id
        ),
        None,
    )
    return bool(
        born == binding
        and authority
        == dict(
            detail=detail.id,
            source=detail.source,
            actor=detail.actor.model_dump(mode="json"),
            target=detail.target.model_dump(mode="json"),
            instruction=detail.account,
            source_event=detail.event,
        )
        and body.get("text") == detail.account
    )


def sex_route(
    game: GameService, c: Connection, state: GameState, prepared: PlayInput, channel: int
) -> dict[str, Any] | None:
    value = next(
        (
            x
            for x in rules.records(state, rules.Source)
            if x.id == prepared.source_work and x.route == "delegated"
        ),
        None,
    )
    if value is None:
        return None
    value = prove(game, c, state, value.id)
    if (
        value.actor != current_ref(state, int(value.actor.entity))
        or value.phase != "accepted"
        or channel != value.cast.channel
        or not value.delegated_rule
    ):
        raise WorkflowError("Use the actual original Pair's source-authenticated Sex rule")
    _contact(game, c, state, value)
    return dict(
        source=value.id,
        actor=value.actor.model_dump(mode="json"),
        target=value.target.model_dump(mode="json") if value.target else None,
        pair=value.pair.model_dump(mode="json"),
        rule=value.delegated_rule,
        cast=value.cast.model_dump(mode="json"),
        source_event=value.event,
    )


def prove_route(game: GameService, c: Connection, state: GameState, route: dict[str, Any]) -> None:
    value = prove(game, c, state, str(route.get("source", "")))
    if route != dict(
        source=value.id,
        actor=value.actor.model_dump(mode="json"),
        target=value.target.model_dump(mode="json") if value.target else None,
        pair=value.pair.model_dump(mode="json"),
        rule=value.delegated_rule,
        cast=value.cast.model_dump(mode="json"),
        source_event=value.event,
    ):
        raise WorkflowError("Preserve the actual borrowed rule and original participants")
    if value.route != "delegated" or not value.delegated_rule:
        raise WorkflowError("Only the actual original Pair's current Sex rule may be delegated")
    if not has_rule(
        state.sheets[value.pair.entity], value.delegated_rule, rule_book(value.delegated_rule)
    ):
        raise WorkflowError("Recover the actual current source rule, not an old book name")


class BondedService:
    def __init__(self, game: GameService):
        self.game, self.store = game, game.store

    def _write(
        self,
        viewer: GuildViewer,
        key: str,
        kind: str,
        body: dict[str, Any],
        operation: Any,
        rule: str = rules.PAIR,
    ) -> dict[str, Any]:
        def access(c: Connection) -> None:
            _access(self.game, c, viewer, rule)
            self.game.unpaused(c)

        try:
            return self.store._write(
                viewer, key, kind, body, operation, auto_audit=False, authorize=access
            )
        except ValueError as error:
            raise WorkflowError(str(error)) from None

    def propose(
        self,
        viewer: GuildViewer,
        key: str,
        channel: int,
        revision: int,
        kind: str,
        account: str,
        *,
        target: ActorRef | None = None,
        observer: ActorRef | None = None,
        route: str = "pair",
        apart: bool = False,
        delegated_rule: str | None = None,
        changeling_source: str | None = None,
    ) -> dict[str, Any]:
        rule = dict(side=rules.SIDE, intimacy=rules.INTIMACY, sex=rules.SEX).get(kind)
        if rule is None:
            raise WorkflowError("Choose a genuine printed Bonded source")

        def operation(c: Connection) -> dict[str, Any]:
            state = load_state(c, self.store.campaign_id)
            actor = current_ref(state, viewer.user_id)
            actual_pair, lineage = original_pair(self.game, c, state, actor, rule)
            if (
                state.revision != revision
                or self.game.pending_actions(c)
                or not account.strip()
                or len(account) > 1200
            ):
                raise WorkflowError(
                    "Use the actual current idle source and your own factual account"
                )
            cast = _cast(self.game, c, state, channel)
            if not any(x.id == cast.id for x in state.scene_casts):
                state.scene_casts.append(cast)
            if kind == "sex":
                target_ref = target or actual_pair
                if target_ref == actor or (target_ref == actual_pair) != (route == "pair"):
                    raise WorkflowError("Use actual Pair Sex or an explicit non-Pair route")
            else:
                target_ref = None
                if target is not None or route != "pair":
                    raise WorkflowError("This source is not a substituted Sex route")
            if (
                kind == "intimacy"
                and (observer is None or observer in (actor, actual_pair))
                or kind != "intimacy"
                and observer is not None
            ):
                raise WorkflowError("Use a distinct actual witnessed-affection onlooker")
            refs = (actor, target_ref) if kind == "sex" else (actor, actual_pair, observer)
            people = [_native(self.game, c, state, x) for x in refs if x is not None]
            event, identity = str(uuid4()), str(uuid4())
            assert self.store.policy.m3_approval is not None
            delegated = None
            if route == "delegated":
                candidates = current_pair_sex_rules(state, actual_pair)
                if delegated_rule is not None:
                    if delegated_rule not in candidates:
                        raise WorkflowError(
                            "Choose only the actual original Pair's current owned Sex rule"
                        )
                    delegated = delegated_rule
                elif len(candidates) == 1:
                    delegated = candidates[0]
                else:
                    raise WorkflowError("Select the actual current Pair Sex source explicitly")
                if delegated == rules.SEX:
                    raise WorkflowError(
                        "SOURCE_SEX_ROUTING_CYCLE: use the explicit unrolled7 alternative"
                    )
                gate = Access(self.store)
                assert gate.registry is not None
                gate.registry.require_available(delegated)
            value = rules.Source.model_validate(
                dict(
                    id=identity,
                    changeling_source=changeling_source,
                    kind=kind,
                    actor=actor,
                    pair=actual_pair,
                    target=target_ref,
                    observer=observer,
                    controllers={x.ref.token: x.controller for x in people},
                    vessels={x.ref.token: x.vessel_id for x in people},
                    cast=cast,
                    registry=self.store.policy.m3_approval.registry_sha256,
                    pair_source=lineage,
                    apart=apart,
                    event=event,
                    account=account.strip(),
                    phase="invited" if kind == "sex" else "accepted",
                    route=route,
                    delegated_rule=delegated,
                )
            )
            _contact(self.game, c, state, value)
            rules.put(state, value)
            if changeling_source is not None:
                from girlframe.services.m3_changeling_sex import bind_source

                bind_source(self.game, c, state, changeling_source, value.id, rules.SEX, event)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.bonded_proposed",
                state,
                event_id=event,
                source=identity,
                source_kind=kind,
            )
            return dict(id=identity, revision=state.revision, phase=value.phase)

        return self._write(
            viewer,
            key,
            "m3.bonded_proposed",
            dict(
                channel=channel,
                revision=revision,
                kind=kind,
                account=account,
                target=target.model_dump(mode="json") if target else None,
                observer=observer.model_dump(mode="json") if observer else None,
                route=route,
                apart=apart,
                delegated_rule=delegated_rule,
                **(
                    {"changeling_source": changeling_source}
                    if changeling_source is not None
                    else {}
                ),
            ),
            operation,
            rule,
        )

    def confirm(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        accept: bool,
        account: str,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            state = load_state(c, self.store.campaign_id)
            value = prove(self.game, c, state, identity)
            person = current_ref(state, viewer.user_id)
            if (
                state.revision != revision
                or value.phase != "invited"
                or person != value.target
                or value.controllers.get(person.token) != viewer.user_id
                or not account.strip()
                or len(account) > 1200
            ):
                raise WorkflowError(
                    "Only the actual original intimate counterpart confirms their own choice"
                )
            _contact(self.game, c, state, value)
            event = str(uuid4())
            rules.put(
                state,
                rules.Consent(
                    id=identity + ":consent",
                    source=identity,
                    person=person,
                    controller=viewer.user_id,
                    accepted=accept,
                    event=event,
                    account=account.strip(),
                ),
            )
            rules.put(
                state, value.model_copy(update=dict(phase="accepted" if accept else "declined"))
            )
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.bonded_confirmed",
                state,
                event_id=event,
                source=identity,
                accepted=accept,
            )
            if value.changeling_source is not None:
                from girlframe.services.m3_changeling_sex import synchronize_session

                synchronize_session(self.game, c, state, value.id, event)
            return dict(
                id=identity, revision=state.revision, phase="accepted" if accept else "declined"
            )

        return self._write(
            viewer,
            key,
            "m3.bonded_confirmed",
            dict(id=identity, revision=revision, accept=accept, account=account),
            operation,
            rules.SEX,
        )

    def activate(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        account: str,
        *,
        man_tag: str | None = None,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            state = load_state(c, self.store.campaign_id)
            value = prove(self.game, c, state, identity)
            _access(self.game, c, viewer, rules.INTIMACY if value.kind == "intimacy" else rules.SEX)
            if (
                state.revision != revision
                or value.actor != current_ref(state, viewer.user_id)
                or value.phase != "accepted"
                or self.game.pending_actions(c)
                or (value.kind != "intimacy" and value.route != "seven")
                or not account.strip()
                or len(account) > 1200
            ):
                raise WorkflowError(
                    "Record the actual performed affection or confirmed unrolled7 source"
                )
            _contact(self.game, c, state, value)
            if man_tag is not None and man_tag not in {
                x["id"] for x in _man_options(self.game, c, state, value)
            }:
                raise WorkflowError(
                    "Choose an actual observed unused partner Tag; special "
                    "conversion/removal sources require their own adapters"
                )
            event = str(uuid4())
            if man_tag is not None:
                from girlframe.services.m3_gender_designation import _current

                law = _current(self.game, c, state, value.actor)
                assert law is not None and value.target is not None
                other = state.sheets[value.target.entity]
                tag = next(x for x in other.tags if x.id == man_tag)
                paired = _paired_basis(self.game, c, state, value.target, value.actor)
                rules.put(
                    state,
                    rules.NoRollManMark(
                        id=identity + ":man",
                        source=identity,
                        actor=value.actor,
                        partner=value.target,
                        designation=law.id,
                        tag=tag.id,
                        label=tag.label,
                        event=event,
                        scene=value.cast.id,
                        already_marked=tag.marked,
                    ),
                )
                if paired is not None:
                    rules.put(
                        state,
                        rules.ManPairedWork(
                            id=identity + ":man:paired",
                            source=identity,
                            mark=identity + ":man",
                            owner=value.target,
                            marker=value.actor,
                            controller=value.controllers[value.actor.token],
                            relation=paired[1],
                            paired=paired[0].id,
                            slot=paired[0].slot,
                            tag=tag.id,
                            event=event,
                        ),
                    )
                if tag.marked:
                    rules.put(
                        state,
                        rules.ManTagResolution(
                            id=identity + ":man:resolution",
                            source=identity,
                            mark=identity + ":man",
                            partner=value.target,
                            controller=value.controllers[value.target.token],
                            tag=tag.id,
                            event=event,
                        ),
                    )
                tag.marked, tag.scene_used = True, value.cast.id
                other.revision += 1
            rules.put(
                state,
                rules.Activation(
                    id=identity + ":activation",
                    source=identity,
                    actor=value.actor,
                    event=event,
                    account=account.strip(),
                ),
            )
            rules.put(
                state,
                value.model_copy(
                    update=dict(
                        phase="results",
                        effect_event=event,
                        tier="high"
                        if man_tag is not None
                        else "low"
                        if value.route == "seven"
                        else None,
                    )
                ),
            )
            if value.route == "seven":
                from girlframe.services.p1_unrolled_sex import offer

                offer(self.game, c, state, rules.get(state, identity), event)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.bonded_activated",
                state,
                event_id=event,
                source=identity,
            )
            return dict(id=identity, revision=state.revision, no_roll=True)

        return self._write(
            viewer,
            key,
            "m3.bonded_activated",
            dict(
                id=identity,
                revision=revision,
                account=account,
                **({"man_tag": man_tag} if man_tag else {}),
            ),
            operation,
            rules.PAIR,
        )

    def choose(
        self, viewer: GuildViewer, key: str, identity: str, revision: int, answer: ChoiceAnswer
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            state = load_state(c, self.store.campaign_id)
            value = prove(self.game, c, state, identity)
            _access(self.game, c, viewer, rules.INTIMACY if value.kind == "intimacy" else rules.SEX)
            kind = _unrolled_choice(state, value)
            person = _choice_person(value, kind)
            if (
                state.revision != revision
                or person != current_ref(state, viewer.user_id)
                or value.action is not None
                or value.kind != "intimacy"
                and value.route != "seven"
            ):
                raise WorkflowError("Only the actual unrolled source chooser owns this decision")
            from girlframe.services.p1_source_pause import require_ready

            require_ready(self.game, c, state, identity)
            if value.route == "seven":
                from girlframe.services.p1_unrolled_sex import require_complete

                require_complete(self.game, c, state, identity)
                paired = _paired_resolution(self.game, c, state, value)
                if paired is not None and paired["pending"]:
                    raise WorkflowError(
                        "The actual marking Pair must choose the Paired conversion first"
                    )
                work = _man_resolution(self.game, c, state, value)
                if work is not None and work["pending"]:
                    raise WorkflowError(
                        "Resolve the actual partner's repeated Tag and owed action first"
                    )
            event = str(uuid4())
            _select(self.game, c, state, value, kind, answer, event, str(uuid4()), None)
            self.game.event(
                c, viewer.user_id, key, "m3.bonded_selected", state, event_id=event, source=identity
            )
            if value.changeling_source is not None:
                from girlframe.services.m3_changeling_sex import synchronize_session

                synchronize_session(self.game, c, state, value.id, event)
            return dict(
                id=identity, revision=state.revision, phase=rules.get(state, identity).phase
            )

        return self._write(
            viewer,
            key,
            "m3.bonded_selected",
            dict(id=identity, revision=revision, answer=answer.model_dump(mode="json")),
            operation,
        )

    def choose_man_paired(
        self, viewer: GuildViewer, key: str, identity: str, revision: int, convert: bool
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            state = load_state(c, self.store.campaign_id)
            value = prove(self.game, c, state, identity)
            status = _paired_resolution(self.game, c, state, value)
            if status is None:
                raise WorkflowError("Recover the actual marking Pair's source-owned choice")
            work = status["work"]
            if (
                state.revision != revision
                or value.phase != "results"
                or not status["pending"]
                or type(convert) is not bool
                or work.marker != current_ref(state, viewer.user_id)
                or work.controller != viewer.user_id
            ):
                raise WorkflowError("Only the actual original marking Pair chooses yes or no once")
            from girlframe.services.m2_choices import ChoiceEngine
            from girlframe.services.p1_source_pause import require_ready

            require_ready(self.game, c, state, identity)
            _contact(self.game, c, state, value)
            basis = _paired_basis(self.game, c, state, work.owner, work.marker)
            sheet = state.sheets[work.owner.entity]
            tag = next((x for x in sheet.tags if x.id == work.tag), None)
            if (
                basis is None
                or basis[1] != work.relation
                or basis[0].id != work.paired
                or basis[0].slot != work.slot
                or tag is None
                or not tag.marked
                or tag.scene_used != value.cast.id
                or tag.rejection_pending
            ):
                raise WorkflowError(
                    "Preserve the actual Pair relation, protected slot and marked Tag"
                )
            engine = ChoiceEngine(self.game)
            engine.prove_tag_setter(c, state, int(work.owner.entity), tag)
            if convert:
                paired = basis[0]
                if not _paired_legal(
                    state, work.owner, paired, tag.label, engine.duplicate_labels()
                ):
                    raise WorkflowError(
                        "Preserve actual duplicate-label, Limited and obsession restrictions"
                    )
                consumed_tag = rules.convert_paired_tag(
                    state,
                    work.owner,
                    paired.id,
                    tag.id,
                    duplicate_labels=engine.duplicate_labels(),
                )
                engine.tag_resolved(state, int(work.owner.entity), consumed_tag)
            event = str(uuid4())
            rules.put(
                state,
                rules.ManPairedDecision(
                    id=work.id + ":decision",
                    work=work.id,
                    marker=work.marker,
                    controller=viewer.user_id,
                    convert=convert,
                    event=event,
                ),
            )
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.bonded_man_paired_chosen",
                state,
                event_id=event,
                source=identity,
            )
            return dict(id=identity, revision=state.revision, converted=convert)

        return self._write(
            viewer,
            key,
            "m3.bonded_man_paired_chosen",
            dict(id=identity, revision=revision, convert=convert),
            operation,
        )

    def resolve_man_tag(
        self, viewer: GuildViewer, key: str, identity: str, revision: int, answer: ChoiceAnswer
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            state = load_state(c, self.store.campaign_id)
            value = prove(self.game, c, state, identity)
            status = _man_resolution(self.game, c, state, value)
            if status is None:
                raise WorkflowError("Recover the actual source-owned repeated Tag")
            work = status["work"]
            if (
                state.revision != revision
                or value.phase != "results"
                or status["decision"] is not None
                or work.partner != current_ref(state, viewer.user_id)
                or work.controller != viewer.user_id
                or answer.text
                or answer.fields
                or answer.number is not None
                or answer.member is not None
                or answer.flag is not None
            ):
                raise WorkflowError(
                    "Only the original affected partner chooses embrace or reject once"
                )
            from girlframe.services.m2_choices import ChoiceEngine
            from girlframe.services.p1_source_pause import require_ready

            require_ready(self.game, c, state, identity)
            _contact(self.game, c, state, value)
            sheet = state.sheets[work.partner.entity]
            tag = next((x for x in sheet.tags if x.id == work.tag), None)
            if (
                tag is None
                or not tag.marked
                or tag.scene_used != value.cast.id
                or tag.rejection_pending
            ):
                raise WorkflowError("Preserve the actual source-marked partner Tag")
            engine = ChoiceEngine(self.game)
            engine.prove_tag_setter(c, state, int(work.partner.entity), tag)
            event, replaced, replacement = str(uuid4()), None, None
            decision: Literal["embrace", "reject"]
            if answer.options == ("embrace",) and len(answer.denied) == 1:
                replaced = next(
                    (x for x in _man_identities(state, work.partner) if x.id == answer.denied[0]),
                    None,
                )
                if replaced is None or (
                    not engine.duplicate_labels()
                    and any(x.name.casefold() == tag.label.casefold() for x in sheet.identities)
                ):
                    raise WorkflowError(
                        "Choose one actual legal unprotected Identity and preserve label policy"
                    )
                replacement = IdentityState(
                    id=str(uuid4()),
                    name=tag.label,
                    slot=replaced.slot,
                    marked=replaced.id in sheet.sedation_locked,
                )
                sheet.identities = [x for x in sheet.identities if x.id != replaced.id] + [
                    replacement
                ]
                if replacement.marked:
                    sheet.sedation_locked = tuple(
                        x for x in sheet.sedation_locked if x != replaced.id
                    ) + (replacement.id,)
                sheet.tags = [x for x in sheet.tags if x.id != tag.id]
                engine.tag_resolved(state, int(work.partner.entity), tag.id)
                decision = "embrace"
            elif answer.options == ("reject",) and not answer.denied:
                if not _man_reject_allowed(state, work.partner, tag):
                    raise WorkflowError(
                        "Preserve actual setter consent, Mentor and Vatgrown restrictions"
                    )
                tag.rejection_pending = True
                decision = "reject"
            else:
                raise WorkflowError(
                    "Choose embrace with one real Identity, or reject and take actual action"
                )
            sheet.revision += 1
            rules.put(
                state,
                rules.ManTagDecision(
                    id=work.id + ":decision",
                    work=work.id,
                    partner=work.partner,
                    controller=viewer.user_id,
                    decision=decision,
                    identity=replaced.id if replaced else None,
                    replacement=replacement.id if replacement else None,
                    event=event,
                ),
            )
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.bonded_man_tag_resolved",
                state,
                event_id=event,
                source=identity,
            )
            return dict(id=identity, revision=state.revision, decision=decision)

        return self._write(
            viewer,
            key,
            "m3.bonded_man_tag_resolved",
            dict(id=identity, revision=revision, answer=answer.model_dump(mode="json")),
            operation,
        )

    def perform_man_rejection(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        account: str,
        *,
        requires_play: bool = False,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            state = load_state(c, self.store.campaign_id)
            value = prove(self.game, c, state, identity)
            status = _man_resolution(self.game, c, state, value)
            if status is None:
                raise WorkflowError("Recover the real pending source-owned rejection")
            work = status["work"]
            if (
                state.revision != revision
                or value.phase != "results"
                or work.partner != current_ref(state, viewer.user_id)
                or work.controller != viewer.user_id
                or status["decision"] is None
                or status["decision"].decision != "reject"
                or status["performance"] is not None
                or not account.strip()
                or len(account.strip()) > 1200
            ):
                raise WorkflowError(
                    "Only the actual affected partner records its real performed rejection"
                )
            from girlframe.services.m3_bonded_rejection import require_no_child

            require_no_child(self.game, c, state, value.id)
            if requires_play:
                raise WorkflowError(
                    "REJECTION_PLAY_ADAPTER_REQUIRED: perform the actual mandatory Play; "
                    "this source account cannot certify it"
                )
            from girlframe.services.m2_choices import ChoiceEngine
            from girlframe.services.p1_source_pause import require_ready

            require_ready(self.game, c, state, identity)
            _contact(self.game, c, state, value)
            sheet = state.sheets[work.partner.entity]
            tag = next((x for x in sheet.tags if x.id == work.tag), None)
            if (
                tag is None
                or not tag.rejection_pending
                or not _man_reject_allowed(state, work.partner, tag)
            ):
                raise WorkflowError("Preserve the actual pending Tag and rejection restrictions")
            engine = ChoiceEngine(self.game)
            engine.prove_tag_setter(c, state, int(work.partner.entity), tag)
            sheet.tags = [x for x in sheet.tags if x.id != tag.id]
            sheet.revision += 1
            engine.tag_resolved(state, int(work.partner.entity), tag.id)
            event = str(uuid4())
            rules.put(
                state,
                rules.ManTagRejection(
                    id=work.id + ":performed",
                    work=work.id,
                    partner=work.partner,
                    controller=viewer.user_id,
                    account=account.strip(),
                    event=event,
                ),
            )
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.bonded_man_tag_rejected",
                state,
                event_id=event,
                source=identity,
            )
            return dict(id=identity, revision=state.revision, performed=True)

        return self._write(
            viewer,
            key,
            "m3.bonded_man_tag_rejected",
            dict(id=identity, revision=revision, account=account, requires_play=requires_play),
            operation,
        )

    def help(
        self, viewer: GuildViewer, key: str, identity: str, revision: int, account: str
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            state = load_state(c, self.store.campaign_id)
            value = prove(self.game, c, state, identity)
            if (
                state.revision != revision
                or value.kind != "side"
                or value.tier != "low"
                or current_ref(state, viewer.user_id) != value.pair
                or not account.strip()
                or len(account) > 1200
                or any(x.source == identity for x in rules.records(state, rules.PairHelp))
            ):
                raise WorkflowError(
                    "Only the actual original Pair records their genuine performed help"
                )
            people = [_native(self.game, c, state, x) for x in (value.actor, value.pair)]
            if (
                any(x.cell is None or x.vessel_id is None for x in people)
                or people[0].cell != people[1].cell
            ):
                raise WorkflowError(
                    "Record actual co-present physical help, never remote fictional aid"
                )
            event = str(uuid4())
            rules.put(
                state,
                rules.PairHelp(
                    id=identity + ":help",
                    source=identity,
                    actor=value.actor,
                    pair=value.pair,
                    controller=viewer.user_id,
                    event=event,
                    account=account.strip(),
                ),
            )
            self.game.event(
                c, viewer.user_id, key, "m3.bonded_helped", state, event_id=event, source=identity
            )
            return dict(id=identity, revision=state.revision, helped=True)

        return self._write(
            viewer,
            key,
            "m3.bonded_helped",
            dict(id=identity, revision=revision, account=account),
            operation,
            rules.SIDE,
        )

    def _tasks(self, c: Connection, viewer: GuildViewer) -> list[dict[str, Any]]:
        state = load_state(c, self.store.campaign_id)
        result = []
        for source in rules.records(state, rules.Source):
            if viewer.user_id not in source.controllers.values():
                continue
            value = prove(self.game, c, state, source.id)
            chooser: int | None = None
            if value.phase == "invited" and value.target is not None:
                chooser = value.controllers[value.target.token]
            elif value.phase == "accepted" or value.phase == "child":
                chooser = value.controllers[value.actor.token]
            elif value.phase == "results":
                orders = _unbound_orders(state, value)
                if orders:
                    chooser = orders[0].controller
                elif value.action:
                    pending = self.game.pending(c, value.action)
                    chooser = next(
                        (
                            int(x["actor_id"])
                            for x in pending
                            if int(x["actor_id"]) == viewer.user_id
                        ),
                        None,
                    )
                elif value.kind == "intimacy":
                    chooser = value.controllers[value.actor.token]
                elif value.target is not None:
                    paired = _paired_resolution(self.game, c, state, value)
                    work = _man_resolution(self.game, c, state, value)
                    chooser = (
                        paired["work"].controller
                        if paired and paired["pending"]
                        else work["work"].controller
                        if work and work["pending"]
                        else value.controllers[
                            _choice_person(value, _unrolled_choice(state, value)).token
                        ]
                    )
            result.append(
                dict(
                    id=value.id,
                    revision=state.revision,
                    label={
                        "side": "Always By Her Side",
                        "intimacy": "Witnessed affection",
                        "sex": "Bonded intimacy",
                    }[value.kind]
                    + " · "
                    + value.phase,
                    phase="pending" if value.phase not in ("complete", "declined") else "complete",
                    pending=chooser == viewer.user_id,
                    source_phase=value.phase,
                )
            )
        return result

    def menu(self, viewer: GuildViewer, channel: int | None = None) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            state = load_state(c, self.store.campaign_id)
            history = self._tasks(c, viewer)
            actor = (
                current_ref(state, viewer.user_id) if str(viewer.user_id) in state.sheets else None
            )
            data: dict[str, Any] = dict(
                revision=state.revision,
                history=history,
                pair=None,
                people=[],
                actor=None,
                available=[],
            )
            if actor is None:
                return data
            sheet = state.sheets[actor.entity]
            if not any(has_rule(sheet, rule, "BONDED") for rule in rules.RULES):
                return data
            _access(self.game, c, viewer, rules.PAIR)
            actual, _ = original_pair(self.game, c, state, actor)
            data.update(
                actor=actor.model_dump(mode="json"),
                pair=actual.model_dump(mode="json"),
                pair_label=state.sheets[actual.entity].callsign,
                delegated_rules=[
                    dict(id=x, label=rule_book(x) + " Sex Play")
                    for x in current_pair_sex_rules(state, actual)
                ],
                available=[
                    x
                    for x in ("side", "intimacy", "sex")
                    if has_rule(
                        sheet,
                        dict(side=rules.SIDE, intimacy=rules.INTIMACY, sex=rules.SEX)[x],
                        "BONDED",
                    )
                ],
            )
            if channel is not None:
                cast = _cast(self.game, c, state, channel)
                for role in cast.roles:
                    if role.actor.kind != "pilot" or role.actor == actor:
                        continue
                    try:
                        person = _native(self.game, c, state, role.actor)
                    except (ValueError, WorkflowError):
                        continue
                    data["people"].append(
                        dict(ref=role.actor.model_dump(mode="json"), label=person.label)
                    )
            return data

    def view(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            state = load_state(c, self.store.campaign_id)
            value = prove(self.game, c, state, identity)
            if viewer.user_id not in value.controllers.values():
                raise WorkflowError(
                    "Only the original actual participants read this private source"
                )
            person = next(x for x in _people(value) if value.controllers[x.token] == viewer.user_id)
            selected = [x for x in rules.records(state, rules.Selection) if x.source == identity]
            details = [
                x
                for x in rules.records(state, rules.Detail)
                if x.source == identity and person in (x.actor, x.target)
            ]
            child = next(
                (x for x in rules.records(state, rules.Child) if x.source == identity), None
            )
            orders = [x for x in _unbound_orders(state, value) if x.controller == viewer.user_id]
            choice_kind = _unrolled_choice(state, value)
            own = state.sheets[person.entity]
            from girlframe.services.p1_source_pause import projection as pause_projection

            pause = (
                pause_projection(self.game, c, identity)
                if value.action is None and value.effect_event
                else None
            )
            from girlframe.services.p1_unrolled_sex import tasks as gender_tasks

            gender = (
                gender_tasks(self.game, c, state, value, viewer) if value.route == "seven" else []
            )
            resolution = _man_resolution(self.game, c, state, value)
            paired_resolution = _paired_resolution(self.game, c, state, value)
            pending_paired = paired_resolution is not None and paired_resolution["pending"]
            pending_resolution = resolution is not None and resolution["pending"]
            resolution_owner = resolution is not None and resolution["work"].partner == person
            resolution_tag = next(
                (x for x in own.tags if resolution and x.id == resolution["work"].tag), None
            )
            from girlframe.services.m2_choices import ChoiceEngine

            embrace_options = (
                _man_identities(state, person)
                if resolution_owner
                and resolution_tag is not None
                and (
                    ChoiceEngine(self.game).duplicate_labels()
                    or not any(
                        x.name.casefold() == resolution_tag.label.casefold() for x in own.identities
                    )
                )
                else []
            )
            return dict(
                man_paired=(
                    dict(
                        id=paired_resolution["work"].id,
                        state="pending"
                        if pending_paired
                        else "converted"
                        if paired_resolution["converted"]
                        else "declined",
                        can_choose=pending_paired and paired_resolution["work"].marker == person,
                        owner=paired_resolution["work"].owner.model_dump(mode="json"),
                        marker=paired_resolution["work"].marker.model_dump(mode="json"),
                        decision=paired_resolution["decision"].model_dump(mode="json")
                        if paired_resolution["decision"]
                        else None,
                        label=next(
                            x.label
                            for x in rules.records(state, rules.NoRollManMark)
                            if x.source == identity
                        ),
                    )
                    if paired_resolution
                    else None
                ),
                man_resolution=(
                    dict(
                        id=resolution["work"].id,
                        tag=resolution["work"].tag,
                        label=next(
                            x.label
                            for x in rules.records(state, rules.NoRollManMark)
                            if x.source == identity
                        ),
                        state="choice"
                        if resolution["decision"] is None
                        else "reject_action"
                        if resolution["pending"]
                        else "complete",
                        decision=resolution["decision"].model_dump(
                            mode="json",
                            exclude=set() if resolution_owner else {"identity", "replacement"},
                        )
                        if resolution["decision"]
                        else None,
                        performance=resolution["performance"].model_dump(mode="json")
                        if resolution["performance"]
                        else None,
                        can_resolve=resolution_owner and resolution["decision"] is None,
                        can_perform=resolution_owner
                        and resolution["pending"]
                        and resolution["decision"] is not None,
                        reject_allowed=bool(
                            resolution_owner
                            and resolution_tag
                            and _man_reject_allowed(state, person, resolution_tag)
                        ),
                        identities=[dict(id=x.id, label=x.name) for x in embrace_options],
                    )
                    if resolution
                    else None
                ),
                unrolled_gender=gender,
                pause=pause,
                id=identity,
                revision=state.revision,
                kind=value.kind,
                phase=value.phase,
                route=value.route,
                tier=value.tier,
                choice_kind=choice_kind,
                man_tags=_man_options(self.game, c, state, value)
                if value.phase == "accepted" and person == value.actor
                else [],
                man_mark=(
                    mark.model_dump(mode="json")
                    if (mark := _prove_man_mark(self.game, c, state, value))
                    else None
                ),
                delegated_rule=value.delegated_rule,
                account=value.account,
                actor=value.actor.model_dump(mode="json"),
                pair=value.pair.model_dump(mode="json"),
                target=value.target.model_dump(mode="json") if value.target else None,
                channel=value.cast.channel,
                action=value.action,
                can_confirm=value.phase == "invited" and person == value.target,
                can_roll=value.phase == "accepted"
                and person == value.actor
                and value.route == "pair"
                and value.kind != "intimacy",
                can_activate=value.phase == "accepted"
                and person == value.actor
                and (value.route == "seven" or value.kind == "intimacy"),
                can_choose=value.phase == "results"
                and value.action is None
                and not pending_resolution
                and not pending_paired
                and person == _choice_person(value, choice_kind),
                can_help=value.kind == "side"
                and value.tier == "low"
                and person == value.pair
                and not any(x.source == identity for x in rules.records(state, rules.PairHelp)),
                options=list(projection_options(state, value, choice_kind).items()),
                tags=[dict(id=x.id, label=x.label) for x in own.tags]
                if choice_kind == "bonded_high" and person == value.target
                else [],
                identities=[
                    dict(id=x.id, label=x.name)
                    for x in own.identities
                    if x.marked and x.id not in own.sedation_locked
                ],
                selections=[
                    dict(
                        kind=x.kind,
                        request=x.request,
                        options=x.options,
                        text=(
                            x.text
                            if x.person == person
                            or (value.kind == "sex" and person in (value.actor, value.target))
                            else json.dumps(
                                {
                                    k: v
                                    for k, v in _text(x.text).items()
                                    if k in ("account", "question")
                                }
                            )
                            if value.kind == "side" and person == value.pair
                            else ""
                        ),
                        identities=x.identities if x.person == person else (),
                    )
                    for x in selected
                ],
                details=[x.model_dump(mode="json") for x in details],
                orders=[x.model_dump(mode="json") for x in orders],
                delegation=next(
                    (
                        x.model_dump(mode="json")
                        for x in rules.records(state, rules.Delegation)
                        if x.source == identity
                    ),
                    None,
                ),
                child=child.model_dump(mode="json") if child and person == value.actor else None,
                silent=bool(
                    value.observer and not rules.can_disclose(state, value.observer, value.id)
                ),
            )


def unrolled_parties(state: GameState, source_id: str) -> tuple[ActorRef, ...]:
    value = rules.get(state, source_id)
    if (
        value.kind != "sex"
        or value.route != "seven"
        or value.target is None
        or not value.effect_event
    ):
        return ()
    return value.actor, value.target


def admit_delegation(
    game: GameService,
    c: Connection,
    state: GameState,
    actor: ActorRef,
    target: ActorRef,
    rule: str,
    bonded_source: str | None,
) -> bool:
    """Only a particular proved borrowed rule; never a global rule entitlement."""
    if bonded_source is None:
        return False
    value = prove(game, c, state, bonded_source)
    if (
        value.route != "delegated"
        or value.actor != actor
        or value.target != target
        or value.delegated_rule != rule
        or value.phase not in ("accepted", "bound", "complete")
    ):
        raise WorkflowError("Use the exact original Pair's delegated Sex source and participants")
    origin = _history(c, game, value.event)
    actual_pair, _ = original_pair(game, c, origin, actor, rules.SEX)
    if actual_pair != value.pair or not has_rule(
        origin.sheets[actual_pair.entity], rule, rule_book(rule)
    ):
        raise WorkflowError("Preserve the actual source-time Pair's owned Sex rule")
    if value.phase != "complete":
        current_pair, _ = original_pair(game, c, state, actor, rules.SEX)
        if current_pair != actual_pair or not has_rule(
            state.sheets[current_pair.entity], rule, rule_book(rule)
        ):
            raise WorkflowError("The actual original Pair must still hold this source Sex rule")
    if not any(x.source == value.id and x.accepted for x in rules.records(state, rules.Consent)):
        raise WorkflowError("Preserve the actual other participant's voluntary confirmation")
    return True


def bind_delegation(
    game: GameService,
    c: Connection,
    state: GameState,
    bonded_source: str,
    session: str,
    rule: str,
    event: str,
) -> None:
    value = prove(game, c, state, bonded_source)
    if (
        value.phase != "accepted"
        or value.target is None
        or any(x.source == value.id for x in rules.records(state, rules.Delegation))
    ):
        raise WorkflowError("Bind only one genuine counterpart source to the original delegation")
    admit_delegation(game, c, state, value.actor, value.target, rule, bonded_source)
    rules.put(
        state,
        rules.Delegation(
            id=value.id + ":delegation",
            source=value.id,
            session=session,
            rule=rule,
            actor=value.actor,
            target=value.target,
            event=event,
        ),
    )
    rules.put(state, value.model_copy(update=dict(phase="bound")))


def prove_delegation(
    game: GameService,
    c: Connection,
    state: GameState,
    bonded_source: str | None,
    session: str,
    actor: ActorRef,
    target: ActorRef,
    rule: str,
) -> None:
    if bonded_source is None:
        return
    admit_delegation(game, c, state, actor, target, rule, bonded_source)
    link = next(
        (x for x in rules.records(state, rules.Delegation) if x.source == bonded_source), None
    )
    if link is None or (link.session, link.actor, link.target, link.rule) != (
        session,
        actor,
        target,
        rule,
    ):
        raise WorkflowError("Preserve the exact original delegated consumer and participants")
    birth = next(
        (
            x
            for x in rules.records(_history(c, game, link.event), rules.Delegation)
            if x.id == link.id
        ),
        None,
    )
    if birth is None or any(
        getattr(birth, k) != getattr(link, k)
        for k in ("id", "source", "session", "rule", "actor", "target", "event")
    ):
        raise WorkflowError("Recover the immutable genuine delegated source birth")


def complete_unrolled_am(
    game: GameService,
    c: Connection,
    state: GameState,
    bonded_source: str,
    session: str,
    event: str,
) -> None:
    """Stage only the proved actual no-roll consumer; its caller persists this event."""
    from girlframe.services.m3_bonded_am import validate_completion

    value = prove(game, c, state, bonded_source)
    if (
        value.target is None
        or value.route != "delegated"
        or value.delegated_rule != "girl.am.sex-play"
    ):
        raise WorkflowError("Use the genuine original Pair's delegated AM source")
    prove_delegation(
        game, c, state, bonded_source, session, value.actor, value.target, value.delegated_rule
    )
    link = next(x for x in rules.records(state, rules.Delegation) if x.source == bonded_source)
    if link.action is not None:
        raise WorkflowError(
            "Preserve the actual rolled consumer; never replace it with a no-roll source"
        )
    if link.completed_event:
        if link.completed_event != event or value.completed_event != event:
            raise WorkflowError("Preserve the original completed source event")
        return
    if value.phase != "bound":
        raise WorkflowError("Complete only the original bound AM delegation")
    validate_completion(game, c, state, session, event)
    rules.put(state, link.model_copy(update=dict(completed_event=event)))
    _complete(state, value, event)


def withdraw_unrolled_am(
    game: GameService,
    c: Connection,
    state: GameState,
    bonded_source: str,
    session: str,
    event: str,
) -> None:
    """Retain consent and link history while withdrawing the unperformed attempt."""
    from girlframe.services.m3_bonded_am import prove as prove_am

    value = prove(game, c, state, bonded_source)
    encounter = prove_am(game, c, state, session)
    if (
        not event
        or value.target is None
        or value.phase != "bound"
        or value.route != "delegated"
        or value.delegated_rule != "girl.am.sex-play"
        or encounter.bonded_source != value.id
        or encounter.phase != "active"
        or encounter.effect_event
        or encounter.completed_event
    ):
        raise WorkflowError("Withdraw only the original no-effect AM encounter")
    prove_delegation(
        game, c, state, bonded_source, session, value.actor, value.target, value.delegated_rule
    )
    link = next(x for x in rules.records(state, rules.Delegation) if x.source == bonded_source)
    if link.action is not None or link.completed_event:
        raise WorkflowError("Retain the real performed or rolled source")
    rules.put(state, value.model_copy(update=dict(phase="declined")))


def synchronize_delegation(
    game: GameService, c: Connection, action: dict[str, Any], event: str
) -> None:
    """Root calls after the real delegated consumer and its own completion checks."""
    state = load_state(c, game.store.campaign_id)
    link = next(
        (
            x
            for x in rules.records(state, rules.Delegation)
            if x.session in (action["id"], action["data"].get("prepared", {}).get("source_work"))
        ),
        None,
    )
    if link is None or link.completed_event or action["state"] != "complete":
        return
    source = prove(game, c, state, link.source)
    prove_delegation(game, c, state, link.source, link.session, link.actor, link.target, link.rule)
    _roll_source(game, c, action)
    final = str(uuid4())
    rules.put(state, link.model_copy(update=dict(action=action["id"], completed_event=final)))
    _complete(state, source, final)
    game.event(
        c,
        int(link.actor.entity),
        "bonded-delegation:" + link.id,
        "m3.bonded_delegation_completed",
        state,
        event_id=final,
        action_id=action["id"],
        source=source.id,
        completion_event=event,
    )


def pre_roll_child(
    game: GameService, c: Connection, viewer: GuildViewer, state: GameState, action: dict[str, Any]
) -> None:
    _access(game, c, viewer, rules.INTIMACY)
    value = _child(game, c, state, action["data"]["bonded_child"]["child"])
    source = prove(game, c, state, value.source)
    if (
        value.child != action["id"]
        or value.completed_event
        or source.phase != "child"
        or value.actor != current_ref(state, viewer.user_id)
        or action["actor_id"] != value.actor.entity
        or action["data"].get("prepared", {}).get("source_work") != value.id
    ):
        raise WorkflowError("Roll only the original bound onlooker child once")
    _contact(game, c, state, source)


def intercept_finish(
    game: GameService, c: Connection, state: GameState, action: dict[str, Any]
) -> bool:
    meta = action["data"].get("bonded")
    if not isinstance(meta, dict):
        return False
    value = rules.get(state, meta["source"])
    if value.phase != "complete":
        action["state"] = "awaiting_choices"
        return True
    return False


def delegation_for_play(
    game: GameService, c: Connection, state: GameState, actor: ActorRef, prepared: PlayInput
) -> dict[str, Any] | None:
    link = next(
        (x for x in rules.records(state, rules.Delegation) if x.session == prepared.source_work),
        None,
    )
    if link is None:
        return None
    plays = {
        "girl.alpha.sex-play": "alpha_sex",
        "girl.princess.sex-play": "princess_sex",
        "girl.mockingbird.sex-play": "mockingbird_sex",
        "girl.stim-blissed.sex-play": "stim_sex",
        "girl.oldgen.sex-play": "oldgen_sex",
        "girl.casualty.sex-play": "casualty_sex",
        "girl.vatgrown.sex-play": "vatgrown_sex",
        "girl.newgirl.sex-play": "newgirl_sex",
    }
    if actor != link.actor or plays.get(link.rule) != prepared.play or link.completed_event:
        raise WorkflowError("Admit only the actual original actor's fixed delegated Sex Play")
    prove_delegation(game, c, state, link.source, link.session, link.actor, link.target, link.rule)
    return dict(
        source=link.source,
        session=link.session,
        rule=link.rule,
        actor=link.actor.model_dump(mode="json"),
        target=link.target.model_dump(mode="json"),
    )


def rule_book(rule: str) -> str:
    books = {
        "girl.alpha.sex-play": "ALPHA",
        "girl.princess.sex-play": "PRINCESS",
        "girl.mockingbird.sex-play": "MOCKINGBIRD",
        "girl.stim-blissed.sex-play": "STIM-BLISSED",
        "girl.oldgen.sex-play": "OLDGEN",
        "girl.casualty.sex-play": "CASUALTY",
        "girl.vatgrown.sex-play": "VATGROWN",
        "girl.newgirl.sex-play": "NEWGIRL",
        "girl.am.sex-play": "AM",
        rules.SEX: "BONDED",
    }
    if rule not in books:
        raise WorkflowError("Recover the actual supported original Pair Sex rule")
    return books[rule]


def current_pair_sex_rules(state: GameState, actual_pair: ActorRef) -> tuple[str, ...]:
    sheet = state.sheets[actual_pair.entity]
    native = "girl." + sheet.girl.lower() + ".sex-play"
    runtime = sheet.girl_runtime
    candidates = {native}
    if runtime:
        candidates.update(
            x.acquired_rule for x in runtime.swaps if x.acquired_rule.endswith(".sex-play")
        )
        candidates.update(x for x in runtime.retained_rules if x.endswith(".sex-play"))
    return tuple(sorted(x for x in candidates if has_rule(sheet, x, rule_book(x))))


def require_disclosure(
    game: GameService, c: Connection, state: GameState, speaker: ActorRef, observation: str
) -> None:
    for silence in rules.records(state, rules.Silence):
        if silence.observer != speaker or silence.observation != observation:
            continue
        source = prove(game, c, state, silence.source)
        child = _child(game, c, state, silence.child)
        saved = next(
            (
                x
                for x in rules.records(_history(c, game, silence.event), rules.Silence)
                if x.id == silence.id
            ),
            None,
        )
        if (
            saved != silence
            or not child.completed_event
            or child.completed_event != silence.event
            or child.total is None
            or child.total < 8
            or child.target != speaker
            or source.id != observation
        ):
            raise WorkflowError("Recover the actual successful observed-affection child source")
        raise WorkflowError(
            "The successful source Play prevents this actual observer telling what they saw; "
            "OOC safety is unchanged"
        )
