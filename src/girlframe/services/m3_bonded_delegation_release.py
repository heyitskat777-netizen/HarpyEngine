"""Original delegated Mockingbird refusal/withdrawal closes only the unused parent."""

import json
from typing import TYPE_CHECKING

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_bonded as rules
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_mockingbird_state import Trigger
from girlframe.services.onboarding import WorkflowError

if TYPE_CHECKING:
    from girlframe.services.m2_game import GameService


def _unused(game: "GameService", c: Connection, state: GameState, source: rules.Source) -> Trigger:
    from girlframe.services.m3_handler_advancements import _history
    from girlframe.services.m3_mockingbird_plays import _trigger

    links = [x for x in rules.records(state, rules.Delegation) if x.source == source.id]
    if len(links) != 1:
        raise WorkflowError("Recover the exact original delegated child")
    link = links[0]
    born = next(
        (
            x
            for x in rules.records(_history(c, game, link.event), rules.Delegation)
            if x.id == link.id
        ),
        None,
    )
    child = _trigger(state, link.session)
    original = _trigger(_history(c, game, child.source_event), child.id)
    birth = c.execute(
        sa.select(t.events.c.kind, t.events.c.actor_id, t.events.c.payload_json).where(
            t.events.c.campaign_id == game.store.campaign_id,
            t.events.c.id == child.source_event,
        )
    ).first()
    birth_payload = json.loads(birth.payload_json) if birth else {}
    if (
        birth is None
        or birth.kind != "m3.mockingbird_trigger"
        or birth.actor_id != source.actor.entity
        or birth_payload.get("trigger") != child.id
        or original.state != "proposed"
        or original.action is not None
        or any(x.decision != "pending" or x.event is not None for x in original.parties)
        or source.route != "delegated"
        or source.delegated_rule != "girl.mockingbird.sex-play"
        or source.changeling_source is not None
        or source.action is not None
        or source.effect_event is not None
        or source.completed_event is not None
        or born != link
        or link.action is not None
        or link.completed_event is not None
        or (link.actor, link.target, link.rule)
        != (source.actor, source.target, source.delegated_rule)
        or child.bonded_source != source.id
        or child.actor != source.actor
        or child.play != "mockingbird_sex"
        or child.action is not None
        or child.learned_sex_source is not None
        or child.learned_source is not None
        or child.changeling_source is not None
        or child.source_event != link.event
        or not child.parties
        or len({x.actor for x in child.parties}) != len(child.parties)
        or any(
            x.actor == child.actor
            or not any(
                r.actor == x.actor and r.controller == x.controller for r in source.cast.roles
            )
            for x in child.parties
        )
        or child.parties[0].actor != source.target
        or child.parties[0].controller != source.controllers.get(child.parties[0].actor.token)
        or any(
            getattr(child, name) != getattr(original, name)
            for name in (
                "id",
                "play",
                "actor",
                "scene",
                "channel",
                "cast_sha256",
                "source_event",
                "account",
                "bonded_source",
                "learned_sex_source",
                "learned_source",
                "changeling_source",
            )
        )
        or [(x.actor, x.controller) for x in original.parties]
        != [(x.actor, x.controller) for x in child.parties]
    ):
        raise WorkflowError("Preserve the original unused delegated source and exact participants")
    actions = t.m2["m2_actions"]
    if c.scalar(
        sa.select(actions.c.id).where(
            actions.c.campaign_id == game.store.campaign_id,
            sa.or_(
                sa.func.json_extract(actions.c.body_json, "$.mockingbird.trigger") == child.id,
                sa.func.json_extract(actions.c.body_json, "$.prepared.source_work") == child.id,
            ),
        )
    ):
        raise WorkflowError("Recover the actual child Action; never erase its dice or costs")
    return child


def release_mockingbird(
    game: "GameService", c: Connection, state: GameState, identity: str, controller: int, event: str
) -> None:
    from girlframe.services.m3_bonded import prove
    from girlframe.services.m3_mockingbird_plays import _trigger

    child = _trigger(state, identity)
    if child.bonded_source is None:
        return
    source = prove(game, c, state, child.bonded_source)
    child = _unused(game, c, state, source)
    if source.phase != "bound" or child.state not in ("declined", "withdrawn"):
        raise WorkflowError("Release only an unused original declined or withdrawn child")
    if child.state == "declined":
        if not any(
            party.controller == controller and party.decision == "declined" and party.event == event
            for party in child.parties
        ):
            raise WorkflowError("Only the actual counterpart's refusal releases this delegation")
    elif controller != int(source.actor.entity):
        raise WorkflowError("Only the original owner withdraws an unused delegated invitation")
    rules.put(
        state,
        rules.DelegationRelease(
            id=source.id + ":release",
            source=source.id,
            session=child.id,
            actor=source.actor,
            controller=controller,
            outcome=child.state,
            event=event,
        ),
    )
    if source.learned_source is not None:
        from girlframe.engine.m3_learned_play_state import put_learned_sex_link
        from girlframe.services.m3_learned_sex import get

        lesson = get(state, source.learned_source)
        if lesson.action or lesson.roll_event or lesson.used_event or lesson.released_event:
            raise WorkflowError("Release only this unused original parent lesson")
        put_learned_sex_link(
            state,
            lesson.model_copy(
                update={
                    "released_event": event,
                    "released_kind": "delegation_" + child.state,
                }
            ),
        )
    rules.put(state, source.model_copy(update={"phase": child.state}))


def prove_release(
    game: "GameService", c: Connection, state: GameState, source: rules.Source
) -> None:
    if source.delegated_rule == "girl.am.sex-play":
        from girlframe.services.m3_learned_bonded_am import prove_release as am_release

        am_release(game, c, state, source)
        return
    if source.delegated_rule == "girl.casualty.sex-play":
        from girlframe.services.m3_learned_bonded_casualty import prove_release as casualty_release

        casualty_release(game, c, state, source)
        return
    if source.delegated_rule == "girl.vatgrown.sex-play":
        from girlframe.services.m3_learned_bonded_vatgrown import prove_release as vatgrown_release

        vatgrown_release(game, c, state, source)
        return
    if source.delegated_rule == "girl.alpha.sex-play":
        from girlframe.services.m3_learned_bonded_alpha import prove_release as alpha_release

        alpha_release(game, c, state, source)
        return
    if source.delegated_rule == "girl.stim-blissed.sex-play":
        from girlframe.services.m3_learned_bonded_stim import prove_release as stim_release

        stim_release(game, c, state, source)
        return
    if source.delegated_rule == "girl.oldgen.sex-play":
        from girlframe.services.m3_learned_bonded_oldgen import prove_release as oldgen_release

        oldgen_release(game, c, state, source)
        return
    if source.delegated_rule == "girl.newgirl.sex-play":
        from girlframe.services.m3_learned_bonded_newgirl import prove_release as newgirl_release

        newgirl_release(game, c, state, source)
        return
    if source.delegated_rule == "girl.princess.sex-play":
        from girlframe.services.m3_learned_bonded_princess import prove_release as princess_release

        princess_release(game, c, state, source)
        return
    from girlframe.services.m3_handler_advancements import _history

    records = [x for x in rules.records(state, rules.DelegationRelease) if x.source == source.id]
    if not records:
        if (
            source.route == "delegated"
            and source.phase in ("declined", "withdrawn")
            and any(x.source == source.id for x in rules.records(state, rules.Delegation))
        ):
            raise WorkflowError("Recover the actual child refusal or withdrawal evidence")
        return
    if len(records) != 1:
        raise WorkflowError("Preserve the one original delegated release")
    value = records[0]
    child = _unused(game, c, state, source)
    saved = _history(c, game, value.event)
    audit = c.execute(
        sa.select(t.events.c.kind, t.events.c.actor_id, t.events.c.payload_json).where(
            t.events.c.campaign_id == game.store.campaign_id, t.events.c.id == value.event
        )
    ).first()
    payload = json.loads(audit.payload_json) if audit else {}
    expected = (
        "m3.mockingbird_trigger_attested"
        if value.outcome == "declined"
        else "m3.mockingbird_trigger_withdrawn"
    )
    if (
        audit is None
        or audit.kind != expected
        or audit.actor_id != str(value.controller)
        or payload.get("trigger") != child.id
        or value not in rules.records(saved, rules.DelegationRelease)
        or rules.get(saved, source.id).phase != value.outcome
        or (value.actor, value.session, value.outcome) != (source.actor, child.id, source.phase)
        or child.state != value.outcome
        or (value.outcome == "withdrawn" and value.controller != int(source.actor.entity))
        or (
            value.outcome == "declined"
            and (
                payload.get("accept") is not False
                or not any(
                    payload.get("party") == party.actor.model_dump(mode="json")
                    and party.controller == value.controller
                    and party.decision == "declined"
                    and party.event == value.event
                    for party in child.parties
                )
            )
        )
    ):
        raise WorkflowError("Prove the original human's exact no-effect delegated release")
