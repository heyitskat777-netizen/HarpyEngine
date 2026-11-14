"""Exact performed Sex, actual Bond weakening and completed inflicted discipline sources."""

import json
from typing import Literal

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_bond_operations as bonds
from girlframe.engine import m3_bonded as bonded
from girlframe.engine.m2 import GameState, higher
from girlframe.engine.m3_actor_state import ActorRef, Model
from girlframe.engine.m3_actors import resolve
from girlframe.services.m2_game import GameService
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_asset_loss import snapshots
from girlframe.services.m3_dose_up import _roll_source
from girlframe.services.m3_handler_advancements import _history
from girlframe.services.onboarding import WorkflowError


def prove_bond_change(
    game: GameService,
    c: Connection,
    state: GameState,
    actor: ActorRef,
    target: ActorRef,
    source: str,
    *,
    delta: Literal[-1, 1],
) -> bonds.Change:
    values = [
        x
        for x in bonds.records(state)
        if (x.id == source or x.event == source)
        and {x.first, x.second} == {actor, target}
        and x.delta == delta
    ]
    if len(values) != 1:
        raise WorkflowError("Choose the exact real Bond operation, not a restored depth difference")
    value = values[0]
    born = next(
        (x for x in bonds.records(_history(c, game, value.event)) if x.id == value.id), None
    )
    if born != value or value.after_depth != min(2, max(0, value.before_depth + delta)):
        raise WorkflowError("Preserve the original canonical Bond operation and people")
    if delta == -1 and value.before_depth == 0:
        raise WorkflowError("There was no actual Bond to weaken")
    return value


def _completed_session(game: GameService, c: Connection, value: Model, kind: str) -> str:
    history = t.m2["m2_state_history"]
    original = value.model_dump()
    if original.get("phase") != "complete":
        raise WorkflowError("Complete all genuine Sex source outcomes first")
    for row in c.execute(
        sa.select(history)
        .where(history.c.campaign_id == game.store.campaign_id)
        .order_by(history.c.revision)
    ).mappings():
        saved = GameState.model_validate_json(row["body_json"])
        fact = next(
            (
                x
                for x in saved.facts
                if x.get("kind") == kind and json.loads(x["body"]).get("id") == original["id"]
            ),
            None,
        )
        if fact is not None:
            canonical = type(value).model_validate_json(fact["body"])
            if canonical.model_dump() == original:
                return str(row["event_id"])
    raise WorkflowError("Recover the canonical actual completed intimacy source")


def _sex(
    game: GameService,
    c: Connection,
    state: GameState,
    actor: ActorRef,
    target: ActorRef,
    source: str,
) -> str:
    unrolled = next((x for x in bonded.records(state, bonded.Source) if x.id == source), None)
    if unrolled is not None:
        from girlframe.services.m3_bonded import prove

        bonded_value = prove(game, c, state, source)
        if (
            bonded_value.kind != "sex"
            or bonded_value.phase != "complete"
            or bonded_value.target is None
            or {bonded_value.actor, bonded_value.target} != {actor, target}
            or not bonded_value.completed_event
        ):
            raise WorkflowError(
                "Use only the true completed Sex between these original participants"
            )
        bonded_completed = bonded.get(
            _history(c, game, bonded_value.completed_event), bonded_value.id
        )
        if (
            bonded_completed.phase != "complete"
            or bonded_completed.completed_event != bonded_value.completed_event
        ):
            raise WorkflowError("Preserve the genuine diceless or rolled source completion")
        return bonded_value.completed_event
    from girlframe.engine import m3_am_sex as am_sex

    native_am = next((x for x in am_sex.sources(state) if x.id == source), None)
    if native_am is not None:
        from girlframe.services.m3_am_sex import prove_learned

        actual = prove_learned(game, c, state, source)
        if (
            actual.mode != "both_am"
            or actual.phase != "complete"
            or actual.completed_event is None
            or actual.action is not None
            or actual.counterpart_action is not None
            or {actual.actor, actual.target} != {actor, target}
        ):
            raise WorkflowError(
                "Use the actual completed native AM or learned AM pair and both real performances"
            )
        am_completed = am_sex.source(_history(c, game, actual.completed_event), source)
        if am_completed != actual:
            raise WorkflowError("Preserve the genuine original diceless AM source completion")
        return actual.completed_event
    action = game.action(c, source)
    if action["state"] != "complete" or game.pending(c, source):
        raise WorkflowError("Complete the genuine performed Sex and all its required outcomes")
    _roll_source(game, c, action)
    data = action["data"]
    play = data["play"]
    pairs: tuple[tuple[ActorRef, ActorRef], ...]
    value: Model
    if play == "alpha_sex" and data.get("alpha_sex"):
        from girlframe.services.m3_alpha_sex import prove as alpha

        value = alpha(game, c, state, data["alpha_sex"]["session"])
        fact_kind = "alpha_sex_session"
    elif play == "princess_sex" and data.get("princess_sex"):
        from girlframe.services.m3_princess_sex import prove as princess

        value = princess(game, c, state, data["princess_sex"]["session"])
        fact_kind = "princess_sex_session"
    elif play == "stim_sex" and data.get("stim_sex"):
        from girlframe.services.m3_stim_sex import prove as stim

        value = stim(game, c, state, data["stim_sex"]["session"])
        fact_kind = "stim_sex_session"
    elif play == "oldgen_sex" and data.get("oldgen_sex"):
        from girlframe.services.m3_oldgen_sex import prove as oldgen

        value = oldgen(game, c, state, data["oldgen_sex"]["session"])
        fact_kind = "oldgen_sex_session"
    elif play == "casualty_sex" and data.get("casualty_sex"):
        from girlframe.services.m3_casualty import prove_sex

        value = prove_sex(game, c, state, data["casualty_sex"]["session"])
        fact_kind = "casualty_sex_session"
    elif play == "vatgrown_sex" and data.get("vatgrown_sex"):
        from girlframe.services.m3_vatgrown_plays import prove as vatgrown

        value = vatgrown(game, c, state, data["vatgrown_sex"]["session"])
        fact_kind = "vatgrown_sex_session"
    elif play == "newgirl_sex" and data.get("newgirl_sex"):
        from girlframe.services.m3_newgirl_sex import prove as newgirl

        current = newgirl(game, c, state, data["newgirl_sex"]["session"])
        pairs = tuple((current.actor, partner) for partner in current.partners)
        if not any({first, second} == {actor, target} for first, second in pairs):
            raise WorkflowError("Co-partners do not automatically have sex with one another")
        return _completed_session(game, c, current, "newgirl_sex_session")
    elif play == "mockingbird_sex" and data.get("mockingbird"):
        trigger = next(
            (x for x in state.mockingbird.triggers if x.id == data["mockingbird"]["trigger"]), None
        )
        if (
            trigger is None
            or trigger.action != source
            or trigger.state != "complete"
            or not trigger.parties
        ):
            raise WorkflowError("Recover the real completed Mockingbird Sex source")
        from girlframe.services.m3_mockingbird_effects import source_trigger

        source_trigger(game, c, action, state)
        if not any({trigger.actor, party.actor} == {actor, target} for party in trigger.parties):
            raise WorkflowError("Co-partners do not automatically have sex with one another")
        # Every actual party must retain their own accepted immutable attestation.
        # The AM recipient can be any actual partner, not only the primary outcome target.
        for party in trigger.parties:
            if party.decision != "accepted" or not party.event:
                raise WorkflowError("Preserve every original participant's voluntary contact")
            accepted = _history(c, game, party.event)
            original_trigger = next(
                (x for x in accepted.mockingbird.triggers if x.id == trigger.id), None
            )
            original_party = (
                next((x for x in original_trigger.parties if x.actor == party.actor), None)
                if original_trigger
                else None
            )
            audit = c.scalar(
                sa.select(t.events.c.actor_id).where(
                    t.events.c.campaign_id == game.store.campaign_id, t.events.c.id == party.event
                )
            )
            if original_party != party or audit != str(party.controller):
                raise WorkflowError(
                    "Only the original actual counterpart confirmed this Sex source"
                )
        history = t.m2["m2_state_history"]
        for row in c.execute(
            sa.select(history)
            .where(history.c.campaign_id == game.store.campaign_id)
            .order_by(history.c.revision)
        ).mappings():
            completed = GameState.model_validate_json(row["body_json"])
            if any(x == trigger for x in completed.mockingbird.triggers):
                return str(row["event_id"])
        raise WorkflowError("Recover the actual canonical completed Mockingbird trigger")
    elif play == "bonded_sex" and data.get("bonded"):
        return _sex(game, c, state, actor, target, data["bonded"]["source"])
    else:
        raise WorkflowError(
            "SOURCE_SEX_ADAPTER_REQUIRED: maintenance or co-presence is not performed Sex"
        )
    fields = value.model_dump()
    if (
        fields.get("action") != source
        or not fields.get("consent_event")
        or {fields["actor"]["entity"], fields["target"]["entity"]} != {actor.entity, target.entity}
    ):
        raise WorkflowError("Use the genuine accepted actual original Sex source")
    actual_actor = ActorRef.model_validate(fields["actor"])
    actual_target = ActorRef.model_validate(fields["target"])
    if {actual_actor, actual_target} != {actor, target}:
        raise WorkflowError(
            "A replacement account cannot inherit another original person’s contact"
        )
    return _completed_session(game, c, value, fact_kind)


def _punishment(
    game: GameService,
    c: Connection,
    state: GameState,
    actor: ActorRef,
    target: ActorRef,
    source: str,
) -> str:
    from girlframe.services.m3_role_punishments import case_proof

    case = next((x for x in state.role_punishments if x.id == source or x.pc_work == source), None)
    if case is not None:
        value = case_proof(c, game, case.id)
        if (
            value.executor != actor
            or value.subject != target
            or not value.effect_event
            or not value.completion_event
        ):
            raise WorkflowError(
                "Actually inflict the Punishment on this person and finish its consequences"
            )
        before, _ = snapshots(game, c, value.effect_event)
        if (
            actor.kind != "pilot"
            or target.kind != "pilot"
            or not higher(before, int(actor.entity), int(target.entity))
        ):
            raise WorkflowError(
                "The actual inflictor must have higher Status when performing Punishment"
            )
        return value.completion_event
    from girlframe.services.m3_punishments import PunishmentService

    service = PunishmentService(game.store)
    row = service._row(c, source)
    body = json.loads(row["body_json"])
    if (
        row["kind"] != "punishment"
        or row["state"] != "resolved"
        or not body.get("applied_event")
        or body.get("role_case")
    ):
        raise WorkflowError("Use the exact actual completed inflicted Punishment source")
    event = body["applied_event"]
    audit = c.execute(
        sa.select(t.events.c.actor_id, t.events.c.kind, t.events.c.payload_json).where(
            t.events.c.campaign_id == game.store.campaign_id, t.events.c.id == event
        )
    ).first()
    before, _ = snapshots(game, c, event)
    if (
        actor.kind != "pilot"
        or target.kind != "pilot"
        or before.handler == int(actor.entity)
        or before.sheets.get(actor.entity) is None
        or before.sheets[actor.entity].character_id != actor.incarnation
        or str(row["subject_id"]) != target.entity
        or body.get("character") != target.incarnation
        or audit is None
        or audit.actor_id != actor.entity
        or audit.kind != "m3.punishment_applied"
        or json.loads(audit.payload_json).get("work_id") != source
        or not higher(before, int(actor.entity), int(target.entity))
    ):
        raise WorkflowError("Prove the real original native inflictor, recipient and higher Status")
    from girlframe.services.m3_collateral import latest

    work = t.m3["m3_required_work"]
    rows = [
        latest(game, c, identity)
        for identity in c.scalars(
            sa.select(work.c.id).where(work.c.campaign_id == game.store.campaign_id).distinct()
        )
    ]
    descendants = {source}
    changed = True
    while changed:
        changed = False
        for child in rows:
            detail = json.loads(child["body_json"])
            if (
                detail.get("source_work") in descendants
                or detail.get("punishment_work") in descendants
            ):
                if child["state"] != "resolved":
                    raise WorkflowError(
                        "Complete every real immediate Punishment consequence first"
                    )
                if child["id"] not in descendants:
                    descendants.add(child["id"])
                    changed = True
    return str(event)


def transfer_source(
    game: GameService,
    c: Connection,
    state: GameState,
    actor: ActorRef,
    target: ActorRef,
    source: str,
    kind: Literal["sex", "bond", "punishment"],
) -> str:
    bound = profiles(c, game.store.campaign_id)
    if actor == target or not all(resolve(state, x, bound).alive for x in (actor, target)):
        raise WorkflowError("Assign an AM only between these actual original living people")
    if kind == "bond":
        return prove_bond_change(game, c, state, actor, target, source, delta=-1).event
    if kind == "sex":
        return _sex(game, c, state, actor, target, source)
    if kind == "punishment":
        return _punishment(game, c, state, actor, target, source)
    raise WorkflowError("Use a real printed AM Transfer source")
