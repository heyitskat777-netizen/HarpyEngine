"""An earned original Pair AM source uses one real native counterpart roll."""

import json
from typing import TYPE_CHECKING

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_bonded as bonded
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_girl_runtime_state import has_rule
from girlframe.engine.m3_learned_play_state import LearnedSexLink, put_learned_sex_link
from girlframe.services.m3_handler_advancements import _history
from girlframe.services.onboarding import WorkflowError

if TYPE_CHECKING:
    from girlframe.services.m2_game import GameService


RULE = "girl.am.sex-play"


def _native(state: GameState, target: ActorRef, book: str) -> bool:
    sheet = state.sheets.get(target.entity) if target.kind == "pilot" else None
    return bool(
        sheet
        and sheet.character_id == target.incarnation
        and sheet.girl == book
        and has_rule(sheet, f"girl.{book.lower()}.sex-play", book)
    )


def eligible(state: GameState, target: ActorRef) -> bool:
    return any(
        _native(state, target, book)
        for book in (
            "MOCKINGBIRD",
            "ALPHA",
            "OLDGEN",
            "PRINCESS",
            "NEWGIRL",
            "STIM-BLISSED",
            "VATGROWN",
            "CASUALTY",
        )
    )


def _source(
    game: "GameService", c: Connection, state: GameState, parent: bonded.Source, action_id: str
) -> dict[str, str]:
    from girlframe.services.m3_am_sex import _counterpart_proof
    from girlframe.services.m3_learned_plays import _keep_raw_roll, _keep_receipt

    if (
        parent.learned_source is None
        or parent.route != "delegated"
        or parent.delegated_rule != RULE
        or parent.target is None
        or parent.target in (parent.actor, parent.pair)
        or parent.action is not None
        or parent.effect_event is not None
        or parent.changeling_source is not None
    ):
        raise WorkflowError("Use only this original learned Pair AM counterpart source")
    action = _counterpart_proof(game, c, state, parent, action_id)
    extra_consent_events: tuple[str, ...] = ()
    if action["data"].get("play") == "alpha_sex":
        from girlframe.engine import m3_alpha_sex as alpha

        meta = action["data"].get("alpha_sex", {})
        child = alpha.get(state, meta["session"])
        if (
            child.action != action_id
            or (child.actor, child.target) != (parent.target, parent.actor)
            or child.caster != parent.controllers.get(parent.target.token)
            or child.counterpart != parent.controllers.get(parent.actor.token)
            or child.cast != parent.cast
            or child.consent_event is None
            or any(
                getattr(child, key) is not None
                for key in ("bonded_source", "changeling_source", "learned_source", "npc_contact")
            )
            or not _native(_history(c, game, child.proposed_event), parent.target, "ALPHA")
            or alpha.get(_history(c, game, child.consent_event), child.id).phase != "accepted"
        ):
            raise WorkflowError(
                "Bind the actual native Alpha's independent original counterpart source"
            )
        source_event, consent_event = child.proposed_event, child.consent_event
    elif action["data"].get("play") == "stim_sex":
        from girlframe.engine import m3_stim_sex as stim

        meta = action["data"].get("stim_sex", {})
        stim_child = stim.get(state, meta["session"])
        if (
            stim_child.action != action_id
            or (stim_child.actor, stim_child.target) != (parent.target, parent.actor)
            or stim_child.caster != parent.controllers.get(parent.target.token)
            or stim_child.counterpart != parent.controllers.get(parent.actor.token)
            or stim_child.cast != parent.cast
            or stim_child.consent_event is None
            or any(
                getattr(stim_child, key) is not None
                for key in ("bonded_source", "changeling_source", "learned_source", "npc_contact")
            )
            or not _native(
                _history(c, game, stim_child.proposed_event), parent.target, "STIM-BLISSED"
            )
            or stim.get(_history(c, game, stim_child.consent_event), stim_child.id).phase
            != "accepted"
        ):
            raise WorkflowError(
                "Bind the actual native Stim's independent original counterpart source"
            )
        source_event, consent_event = stim_child.proposed_event, stim_child.consent_event
    elif action["data"].get("play") == "casualty_sex":
        from girlframe.services.m3_casualty import _session, prove_parts

        meta = action["data"].get("casualty_sex", {})
        casualty_child = _session(state, meta["session"])
        if (
            casualty_child.action != action_id
            or (casualty_child.actor, casualty_child.target) != (parent.target, parent.actor)
            or casualty_child.caster != parent.controllers.get(parent.target.token)
            or casualty_child.counterpart != parent.controllers.get(parent.actor.token)
            or casualty_child.cast != parent.cast
            or casualty_child.consent_event is None
            or any(
                getattr(casualty_child, key) is not None
                for key in ("bonded_source", "changeling_source", "learned_source", "npc_contact")
            )
            or not _native(
                _history(c, game, casualty_child.proposed_event), parent.target, "CASUALTY"
            )
            or _session(_history(c, game, casualty_child.consent_event), casualty_child.id).phase
            != "accepted"
        ):
            raise WorkflowError(
                "Bind the actual native Casualty's independent original counterpart source"
            )
        # The native receipt proof owns original vessels; learning never creates anatomy.
        prove_parts(game, c, state, casualty_child.actor)
        source_event, consent_event = casualty_child.proposed_event, casualty_child.consent_event
    elif action["data"].get("play") == "oldgen_sex":
        from girlframe.engine import m3_oldgen_sex as oldgen

        meta = action["data"].get("oldgen_sex", {})
        oldgen_child = oldgen.get(state, meta["session"])
        if (
            oldgen_child.action != action_id
            or (oldgen_child.actor, oldgen_child.target) != (parent.target, parent.actor)
            or oldgen_child.caster != parent.controllers.get(parent.target.token)
            or oldgen_child.counterpart != parent.controllers.get(parent.actor.token)
            or oldgen_child.cast != parent.cast
            or oldgen_child.consent_event is None
            or any(
                getattr(oldgen_child, key) is not None
                for key in ("bonded_source", "changeling_source", "learned_source", "npc_contact")
            )
            or not _native(_history(c, game, oldgen_child.proposed_event), parent.target, "OLDGEN")
            or oldgen.get(_history(c, game, oldgen_child.consent_event), oldgen_child.id).phase
            != "accepted"
        ):
            raise WorkflowError(
                "Bind the actual native Oldgen's independent original counterpart source"
            )
        source_event, consent_event = oldgen_child.proposed_event, oldgen_child.consent_event
    elif action["data"].get("play") == "vatgrown_sex":
        from girlframe.engine import m3_vatgrown_plays as vatgrown

        meta = action["data"].get("vatgrown_sex", {})
        vatgrown_child = vatgrown.get(state, meta["session"])
        if (
            vatgrown_child.action != action_id
            or (vatgrown_child.actor, vatgrown_child.target) != (parent.target, parent.actor)
            or vatgrown_child.caster != parent.controllers.get(parent.target.token)
            or vatgrown_child.counterpart != parent.controllers.get(parent.actor.token)
            or vatgrown_child.cast != parent.cast
            or vatgrown_child.consent_event is None
            or any(
                getattr(vatgrown_child, key) is not None
                for key in ("bonded_source", "changeling_source", "learned_source")
            )
            or not _native(
                _history(c, game, vatgrown_child.proposed_event), parent.target, "VATGROWN"
            )
            or vatgrown.get(
                _history(c, game, vatgrown_child.consent_event), vatgrown_child.id
            ).phase
            != "accepted"
        ):
            raise WorkflowError(
                "Bind the actual native Vatgrown's independent original counterpart source"
            )
        source_event, consent_event = vatgrown_child.proposed_event, vatgrown_child.consent_event
    elif action["data"].get("play") == "newgirl_sex":
        from girlframe.engine import m3_newgirl_sex as newgirl

        meta = action["data"].get("newgirl_sex", {})
        newgirl_child = newgirl.get(state, meta["session"])
        responses = tuple(
            x for x in newgirl.records(state, newgirl.Consent) if x.session == newgirl_child.id
        )
        expected_controllers = {
            role.actor.token: role.controller
            for role in parent.cast.roles
            if role.actor in (parent.target, *newgirl_child.partners)
        }
        accepted = {response.person.token: response for response in responses}
        if (
            newgirl_child.action != action_id
            or newgirl_child.actor != parent.target
            or parent.actor not in newgirl_child.partners
            or len({person.token for person in newgirl_child.partners})
            != len(newgirl_child.partners)
            or newgirl_child.controllers != expected_controllers
            or len(expected_controllers) != len(newgirl_child.partners) + 1
            or newgirl_child.cast != parent.cast
            or any(
                getattr(newgirl_child, key) is not None
                for key in ("bonded_source", "changeling_source", "learned_source")
            )
            or not _native(
                _history(c, game, newgirl_child.proposed_event), parent.target, "NEWGIRL"
            )
            or len(responses) != len(newgirl_child.partners)
            or set(accepted) != {person.token for person in newgirl_child.partners}
            or any(
                not response.accepted
                or response.controller != expected_controllers.get(response.person.token)
                or response
                not in newgirl.records(_history(c, game, response.event), newgirl.Consent)
                for response in responses
            )
        ):
            raise WorkflowError(
                "Bind the actual native Newgirl's independently consenting original partners"
            )
        source_event = newgirl_child.proposed_event
        consent_event = accepted[parent.actor.token].event
        extra_consent_events = tuple(x.event for x in responses)
    elif action["data"].get("play") == "princess_sex":
        from girlframe.engine import m3_princess_sex as princess

        meta = action["data"].get("princess_sex", {})
        princess_child = princess.get(state, meta["session"])
        if (
            princess_child.action != action_id
            or (princess_child.actor, princess_child.target) != (parent.target, parent.actor)
            or princess_child.caster != parent.controllers.get(parent.target.token)
            or princess_child.counterpart != parent.controllers.get(parent.actor.token)
            or princess_child.cast != parent.cast
            or princess_child.consent_event is None
            or any(
                getattr(princess_child, key) is not None
                for key in ("bonded_source", "changeling_source", "learned_source", "npc_contact")
            )
            or not _native(
                _history(c, game, princess_child.proposed_event), parent.target, "PRINCESS"
            )
            or princess.get(
                _history(c, game, princess_child.consent_event), princess_child.id
            ).phase
            != "accepted"
        ):
            raise WorkflowError(
                "Bind the actual native Princess's independent original counterpart source"
            )
        source_event, consent_event = princess_child.proposed_event, princess_child.consent_event
    else:
        meta = action["data"].get("mockingbird", {})
        trigger = next((x for x in state.mockingbird.triggers if x.action == action_id), None)
        if (
            action["data"].get("play") != "mockingbird_sex"
            or trigger is None
            or trigger.play != "mockingbird_sex"
            or trigger.actor != parent.target
            or not trigger.parties
            or len({party.actor.token for party in trigger.parties}) != len(trigger.parties)
            or trigger.parties[0].actor != parent.actor
            or trigger.parties[0].controller != parent.controllers.get(parent.actor.token)
            or any(
                party.decision != "accepted"
                or party.event is None
                or not any(
                    role.actor == party.actor and role.controller == party.controller
                    for role in parent.cast.roles
                )
                or not any(
                    old.id == trigger.id
                    and old.actor == trigger.actor
                    and old.scene == trigger.scene
                    and old.channel == trigger.channel
                    and old.cast_sha256 == trigger.cast_sha256
                    and party in old.parties
                    for old in _history(c, game, party.event).mockingbird.triggers
                )
                for party in trigger.parties
            )
            or any(
                getattr(trigger, key) is not None
                for key in (
                    "bonded_source",
                    "changeling_source",
                    "learned_source",
                    "learned_sex_source",
                )
            )
            or meta.get("trigger") != trigger.id
            or not _native(_history(c, game, trigger.source_event), parent.target, "MOCKINGBIRD")
        ):
            raise WorkflowError(
                "Bind the native Mockingbird's independent primary-counterpart group source, "
                "not a proxy"
            )
        assert trigger.parties[0].event is not None
        source_event, consent_event = trigger.source_event, trigger.parties[0].event
        extra_consent_events = tuple(party.event for party in trigger.parties if party.event)
    # Both source birth and its separate owned consent must follow the accepted parent.
    consent = [
        x for x in bonded.records(state, bonded.Consent) if x.source == parent.id and x.accepted
    ]
    events = t.events
    positions = {
        row.id: row.seq
        for row in c.execute(
            sa.select(events.c.id, events.c.seq).where(
                events.c.campaign_id == game.store.campaign_id,
                events.c.id.in_(
                    [
                        source_event,
                        consent_event,
                        *extra_consent_events,
                        *(x.event for x in consent),
                    ]
                ),
            )
        ).all()
    }
    if (
        len(consent) != 1
        or consent[0].person != parent.target
        or consent[0].controller != parent.controllers.get(parent.target.token)
        or not positions.get(consent[0].event, 0)
        or positions.get(source_event, 0) <= positions[consent[0].event]
        or positions.get(consent_event, 0) <= positions[source_event]
        or any(positions.get(event, 0) <= positions[source_event] for event in extra_consent_events)
    ):
        raise WorkflowError("Use new independent source consent after the original parent consent")
    return dict(
        lesson=parent.learned_source,
        counterpart_roll_event=_keep_raw_roll(game, c, action),
        counterpart_receipt_sha256=_keep_receipt(game, c, action),
    )


def consume(
    game: "GameService",
    c: Connection,
    state: GameState,
    parent: bonded.Source,
    action_id: str,
    event: str,
) -> dict[str, str]:
    from girlframe.services.m3_bonded import _contact
    from girlframe.services.m3_learned_plays import _replace
    from girlframe.services.m3_learned_sex import _grant, get

    proof = _source(game, c, state, parent, action_id)
    assert parent.learned_source is not None
    lesson = get(state, parent.learned_source)
    grant = _grant(game, c, state, lesson)
    _contact(game, c, state, parent)
    if (
        parent.phase != "accepted"
        or lesson.session != parent.id
        or lesson.rule_id != bonded.SEX
        or lesson.accepted is not True
        or (lesson.actor, lesson.target) != (parent.actor, parent.target)
        or any(
            getattr(lesson, key) is not None
            for key in (
                "action",
                "bound_event",
                "roll_event",
                "receipt_sha256",
                "used_event",
                "released_event",
            )
        )
        or any(
            getattr(grant, key) is not None
            for key in ("claimed_action", "rolled_event", "claimed_source", "used_event")
        )
        or any(x.source == parent.id for x in bonded.records(state, bonded.Delegation))
        or not event
    ):
        raise WorkflowError(
            "Consume this original unused lesson only for its real counterpart receipt"
        )
    _replace(state, grant.model_copy(update=dict(claimed_source=parent.id, used_event=event)))
    put_learned_sex_link(state, lesson.model_copy(update=dict(used_event=event)))
    return proof


def prove_use(
    game: "GameService",
    c: Connection,
    state: GameState,
    parent: bonded.Source,
    lesson: LearnedSexLink,
) -> None:
    from girlframe.services.m3_learned_sex import _grant, get

    links = [x for x in bonded.records(state, bonded.Delegation) if x.source == parent.id]
    if len(links) != 1 or lesson.used_event is None:
        raise WorkflowError("Preserve the one actual counterpart receipt binding")
    link = links[0]
    born = _history(c, game, lesson.used_event)
    original = next((x for x in bonded.records(born, bonded.Delegation) if x.id == link.id), None)
    source = bonded.get(born, parent.id)
    proof = _source(game, c, born, source, link.session)
    audit = c.execute(
        sa.select(t.events.c.kind, t.events.c.actor_id, t.events.c.payload_json).where(
            t.events.c.campaign_id == game.store.campaign_id,
            t.events.c.id == lesson.used_event,
        )
    ).first()
    payload = json.loads(audit.payload_json) if audit else {}
    if (
        audit is None
        or audit.kind != "m3.bonded_am_source"
        or audit.actor_id != parent.actor.entity
        or payload.get("source") != parent.id
        or payload.get("action_id") != link.session
        or any(payload.get(key) != value for key, value in proof.items())
        or parent.learned_source != lesson.id
        or lesson.session != parent.id
        or lesson.rule_id != bonded.SEX
        or lesson.accepted is not True
        or (lesson.actor, lesson.target) != (parent.actor, parent.target)
        or any(
            getattr(lesson, key) is not None
            for key in ("action", "bound_event", "roll_event", "receipt_sha256", "released_event")
        )
        or original is None
        or original.action is not None
        or original.completed_event is not None
        or link.event != lesson.used_event
        or (link.actor, link.target, link.rule) != (parent.actor, parent.target, RULE)
        or any(
            getattr(link, key) != getattr(original, key)
            for key in ("id", "source", "session", "rule", "actor", "target", "event")
        )
        or source.phase != "bound"
        or source.completed_event is not None
        or parent.phase not in ("bound", "complete")
        or link.action != (link.session if parent.phase == "complete" else None)
        or link.completed_event != parent.completed_event
        or get(born, lesson.id).used_event != lesson.used_event
    ):
        raise WorkflowError(
            "Keep the original one-use binding, independent receipt and owned source"
        )
    for snapshot in (born, state):
        grant = _grant(game, c, snapshot, lesson)
        if (
            grant.claimed_source != parent.id
            or grant.used_event != lesson.used_event
            or grant.claimed_action is not None
            or grant.rolled_event is not None
        ):
            raise WorkflowError(
                "The counterpart owns its receipt; no extra learner Action or refund"
            )
