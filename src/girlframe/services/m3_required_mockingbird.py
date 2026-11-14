"""Actual native conversation/Sex recipes for an original Emotional Relay nomination."""

import json
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_ankou as ankou
from girlframe.engine import m3_required_plays as rules
from girlframe.engine.m2 import GameState, PlayInput
from girlframe.engine.m3_actors import fingerprint
from girlframe.engine.m3_mockingbird_state import PERSON, SEX, Trigger
from girlframe.services.m2_game import GameService
from girlframe.services.m3_handler_advancements import _history
from girlframe.services.m3_mockingbird_plays import _trigger, prepare
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer

RULE = "girl.mockingbird.bad-at-being-a-person"
RULES = {PERSON: RULE, SEX: "girl.mockingbird.sex-play"}


def _audit(
    game: GameService, c: Connection, event: str, kind: str, owner: int, **payload: Any
) -> None:
    row = c.execute(
        sa.select(t.events.c.kind, t.events.c.actor_id, t.events.c.payload_json).where(
            t.events.c.campaign_id == game.store.campaign_id, t.events.c.id == event
        )
    ).first()
    if (
        row is None
        or row.kind != kind
        or row.actor_id != str(owner)
        or any(json.loads(row.payload_json).get(k) != v for k, v in payload.items())
    ):
        raise WorkflowError(
            "Recover the actual conversation declaration and independent attestations"
        )


def prove_trigger(
    game: GameService, c: Connection, state: GameState, link: rules.RequiredLink
) -> Trigger:
    current = _trigger(state, link.recipe)
    original = _trigger(_history(c, game, link.event), link.recipe)
    born = _trigger(_history(c, game, original.source_event), link.recipe)
    sheet = _history(c, game, link.event).sheets.get(link.actor.entity)
    if (
        original.play not in RULES
        or RULES.get(original.play) != link.rule
        or original.state != "ready"
        or original.action is not None
        or original.actor != link.actor
        or original.parties[0].actor != link.target
        or original.cast_sha256 != fingerprint(link.cast)
        or original.scene != link.cast.id
        or original.channel != link.cast.channel
        or sheet is None
        or sheet.character_id != link.actor.incarnation
        or sheet.girl != "MOCKINGBIRD"
        or any(
            (
                original.learned_source,
                original.learned_sex_source,
                original.bonded_source,
                original.changeling_source,
            )
        )
        or current.model_dump(exclude={"state", "action"})
        != original.model_dump(exclude={"state", "action"})
        or born.model_dump(exclude={"state", "action", "parties"})
        != original.model_dump(exclude={"state", "action", "parties"})
        or [(x.actor, x.controller) for x in born.parties]
        != [(x.actor, x.controller) for x in original.parties]
        or any(x.decision != "pending" or x.event is not None for x in born.parties)
        or born.state != ("ready" if original.play == PERSON else "proposed")
        or born.action is not None
        or current.state not in ("ready", "started", "complete")
        or (current.state == "ready" and current.action is not None)
        or (current.state != "ready" and current.action != link.action)
    ):
        raise WorkflowError(
            "Keep the exact original native declared conversation and required actor"
        )
    _audit(
        game,
        c,
        born.source_event,
        "m3.mockingbird_trigger",
        int(link.actor.entity),
        trigger=born.id,
    )
    if original.play == SEX:
        _prove_consent(game, c, born, original)
    elif original.parties != born.parties:
        raise WorkflowError(
            "Preserve the original conversation participants without invented consent"
        )
    return current


def _prove_consent(game: GameService, c: Connection, born: Trigger, original: Trigger) -> None:
    for party in original.parties:
        if party.decision != "accepted" or not party.event:
            raise WorkflowError("Each original participant must independently accept this source")
        _audit(
            game,
            c,
            party.event,
            "m3.mockingbird_trigger_attested",
            party.controller,
            trigger=original.id,
            party=party.actor.model_dump(mode="json"),
            accept=True,
        )
        attested = _trigger(_history(c, game, party.event), original.id)
        if (
            attested.model_dump(exclude={"state", "parties"})
            != born.model_dump(exclude={"state", "parties"})
            or [(x.actor, x.controller) for x in attested.parties]
            != [(x.actor, x.controller) for x in born.parties]
            or party not in attested.parties
        ):
            raise WorkflowError("Preserve the actual source and original independent consent event")


def link_trigger(
    game: GameService,
    c: Connection,
    state: GameState,
    viewer: GuildViewer,
    key: str,
    task: ankou.Task,
    recipe: str,
) -> dict[str, Any]:
    trigger = _trigger(state, recipe)
    if (
        trigger.play not in RULES
        or trigger.play not in task.options
        or state.sheets[task.actor.entity].girl != "MOCKINGBIRD"
    ):
        raise WorkflowError("Use the actual nominated native Mockingbird source")
    if any(
        (
            trigger.learned_source,
            trigger.learned_sex_source,
            trigger.bonded_source,
            trigger.changeling_source,
        )
    ):
        raise WorkflowError(
            "This source is the actual native Mockingbird source, not a borrowed Play"
        )
    if trigger.actor != task.actor or trigger.cast_sha256 != fingerprint(task.cast):
        raise WorkflowError("Keep the original required actor and scene")
    # Run the existing native producer's authority, trigger, counterpart and duplicate checks.
    prepare(
        game,
        c,
        viewer,
        PlayInput(
            play=trigger.play,
            source_work=recipe,
            context=trigger.account,
            trigger_confirmed=True,
            heat=0,
        ),
        state,
        channel=task.cast.channel,
    )
    from girlframe.services.p1_source_pause import require_ready

    require_ready(game, c, state, task.id)
    event = str(uuid4())
    link = rules.RequiredLink.model_validate(
        dict(
            id=rules.identity(task.id, recipe, event),
            source=task.id,
            recipe=recipe,
            rule=RULES[trigger.play],
            actor=task.actor,
            target=trigger.parties[0].actor,
            cast=task.cast,
            event=event,
        )
    )
    rules.put(state, link)
    game.event(
        c,
        viewer.user_id,
        key,
        "m3.required_play_linked",
        state,
        event_id=event,
        source=task.id,
        recipe=recipe,
        link=link.id,
    )
    prove_trigger(game, c, state, link)
    return dict(id=link.id, source=task.id, recipe=recipe, revision=state.revision)


def menu_triggers(
    game: GameService, c: Connection, state: GameState, task: ankou.Task
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    accepted: list[dict[str, Any]] = []
    pending: list[dict[str, Any]] = []
    if not set(RULES).intersection(task.options):
        return accepted, pending
    for value in state.mockingbird.triggers:
        if (
            value.play not in RULES
            or value.play not in task.options
            or value.actor != task.actor
            or value.cast_sha256 != fingerprint(task.cast)
            or value.action
            or any(
                (
                    value.learned_source,
                    value.learned_sex_source,
                    value.bonded_source,
                    value.changeling_source,
                )
            )
        ):
            continue
        if value.state == "ready":
            accepted.append(
                dict(
                    id=value.id,
                    rule=RULES[value.play],
                    play=value.play,
                    label="Actual " + value.play.replace("_", " ") + ": " + value.account[:70],
                    target=value.parties[0].actor.model_dump(mode="json"),
                )
            )
        elif value.state == "proposed":
            pending.append(dict(id=value.id, label="Await actual interlocutor attestation"))
    return accepted, pending


def withdraw_link(
    game: GameService, c: Connection, state: GameState, trigger: Trigger, event: str
) -> None:
    """Release an unprepared nomination link, never its still-owed performance."""
    from girlframe.services.m3_required_plays import prove

    links = [x for x in rules.records(state) if x.recipe == trigger.id and x.retired_event is None]
    if len(links) > 1:
        raise WorkflowError("Preserve the single original required source link")
    for link in links:
        prove(game, c, state, link.id)
        if (
            link.rule not in RULES.values()
            or link.action
            or link.bound_event
            or link.completed_event
            or link.releases
            or link.withdrawn_event
            or trigger.action
        ):
            raise WorkflowError("Recover/cancel the actual prepared nomination before withdrawing")
        rules.put(state, link.model_copy(update={"retired_event": event, "withdrawn_event": event}))


def prove_withdrawal(
    game: GameService, c: Connection, state: GameState, link: rules.RequiredLink
) -> None:
    """A retirement flag alone cannot remove the original required-source authority."""
    if (
        link.rule not in RULES.values()
        or not link.withdrawn_event
        or link.retired_event != link.withdrawn_event
        or link.action
        or link.bound_event
        or link.completed_event
        or link.releases
    ):
        raise WorkflowError("Retire only the genuinely withdrawn unprepared conversation link")
    _audit(
        game,
        c,
        link.withdrawn_event,
        "m3.mockingbird_trigger_withdrawn",
        int(link.actor.entity),
        trigger=link.recipe,
    )
    withdrawn = _history(c, game, link.withdrawn_event)
    if rules.get(withdrawn, link.id) != link:
        raise WorkflowError("Preserve the canonical original withdrawal event")
    original = prove_trigger(game, c, _history(c, game, link.event), link)
    expected = original.model_copy(update={"state": "withdrawn"})
    if _trigger(withdrawn, link.recipe) != expected or _trigger(state, link.recipe) != expected:
        raise WorkflowError("Preserve the exact unperformed withdrawn conversation source")
