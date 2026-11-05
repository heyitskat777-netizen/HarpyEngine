"""Prove an explicit human GM setter without borrowing a future fictional persona."""

import json

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine.m2 import GameState, TagState
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_harpy_defeat_state import NativeHarpyRuntime
from girlframe.engine.m3_void_state import HarpyState, HarpyTag
from girlframe.services.onboarding import OnboardingStore, WorkflowError


def _tags(state: GameState, subject: ActorRef) -> list[TagState]:
    if subject.kind == "pilot":
        sheet = state.sheets.get(subject.entity)
        return sheet.tags if sheet and sheet.character_id == subject.incarnation else []
    if subject.kind == "handler":
        from girlframe.engine.m3_handler_consequences import same_handler_body

        if same_handler_body(state, subject):
            return state.handler_tags
    if subject.kind == "external_pilot":
        bodies: list[HarpyState | NativeHarpyRuntime] = [*state.harpy_states, *state.native_harpies]
        body = next((x for x in bodies if x.id == subject.entity), None)
        if body is not None:
            return [
                TagState.model_validate(
                    {k: v for k, v in tag.model_dump().items() if k != "giver_ref"}
                    | {"giver_actor": tag.giver_ref}
                )
                for tag in body.tags
            ]
    return []


def ooc_setter(
    c: Connection, store: OnboardingStore, subject: ActorRef, tag: TagState | HarpyTag
) -> int | None:
    """Return the original human principal only after actual creation/appointment proof.

    Ordinary fictional setters return None. A malformed or forged OOC claim fails
    closed; the caller must not fall back to the giver UID's current character.
    """
    if isinstance(tag, HarpyTag):
        tag = TagState.model_validate(
            {k: v for k, v in tag.model_dump().items() if k != "giver_ref"}
            | {"giver_actor": tag.giver_ref}
        )
    if tag.gm_setter_appointment is None and tag.gm_setter_event is None:
        return None
    try:
        if (
            tag.gm_setter_appointment is None
            or tag.gm_setter_event is None
            or tag.giver_actor is not None
            or tag.giver_character is not None
        ):
            raise ValueError()
        event = (
            c.execute(
                sa.select(t.events).where(
                    t.events.c.campaign_id == store.campaign_id,
                    t.events.c.id == tag.gm_setter_event,
                )
            )
            .mappings()
            .first()
        )
        if event is None or event["actor_id"] != str(tag.giver):
            raise ValueError()
        history = t.m2["m2_state_history"]
        body = c.scalar(
            sa.select(history.c.body_json).where(
                history.c.campaign_id == store.campaign_id,
                history.c.event_id == event["id"],
            )
        )
        if body is None:
            raise ValueError()
        original = GameState.model_validate_json(body)
        lookup_subject = subject
        if subject.kind == "external_pilot" and not _tags(original, subject):
            from girlframe.engine.m3_tag_permissions import conversion
            from girlframe.services.m2_state import load_state

            current = load_state(c, store.campaign_id)
            harpy, marker = conversion(current, subject)
            born_raw = c.scalar(
                sa.select(history.c.body_json).where(
                    history.c.campaign_id == store.campaign_id,
                    history.c.event_id == harpy.source_event,
                )
            )
            born = GameState.model_validate_json(born_raw) if born_raw else None
            if born is None:
                raise ValueError()
            born_harpy, born_marker = conversion(born, subject)
            born_tag = next((x for x in _tags(born, subject) if x.id == tag.id), None)
            fields = (
                "giver",
                "giver_actor",
                "giver_character",
                "gm_setter_appointment",
                "gm_setter_event",
                "gm_setter_grant",
            )
            if (
                tag.id not in marker["retained_tag_ids"]
                or tag.id not in born_marker["retained_tag_ids"]
                or born_harpy.origin != harpy.origin
                or born_tag is None
                or any(getattr(tag, k) != getattr(born_tag, k) for k in fields)
            ):
                raise ValueError()
            lookup_subject = harpy.origin
        source = next((x for x in _tags(original, lookup_subject) if x.id == tag.id), None)
        if (
            (tag.gm_setter_grant is None and original.handler != tag.giver)
            or json.loads(event["payload_json"]).get("game_revision") != original.revision
            or source is None
            or source.label != tag.label
            or source.giver != tag.giver
            or source.giver_actor is not None
            or source.giver_character is not None
            or source.gm_setter_appointment != tag.gm_setter_appointment
            or source.gm_setter_event != event["id"]
            or source.gm_setter_grant != tag.gm_setter_grant
        ):
            raise ValueError()
        if tag.gm_setter_grant is not None:
            from girlframe.services.m2_game import GameService
            from girlframe.services.m3_battle import proved_judge
            from girlframe.services.m3_handler_plays import _source

            game = GameService(store)
            _, grant = _source(c, game, tag.gm_setter_grant)
            if grant.source_action is None:
                raise ValueError()
            director, human, campaign_appointment = proved_judge(
                game, c, game.action(c, grant.source_action)
            )
            if (
                event["kind"] != "m3.handler_play_applied"
                or grant.effect is None
                or grant.effect.kind != "tag"
                or grant.effect.target != lookup_subject
                or grant.effect_event != event["id"]
                or grant.effect.tag != tag.label
                or tag.id != grant.id + ":tag"
                or grant.chooser_actor is not None
                or director is None
                or grant.adjudicator_ref != director
                or human != tag.giver
                or grant.chooser_controller != human
                or campaign_appointment != tag.gm_setter_appointment
            ):
                raise ValueError()
        setup = t.setup_revisions
        appointment = (
            c.execute(
                sa.select(setup.c.event_id, setup.c.body_json)
                .join(
                    t.events,
                    t.events.c.id == setup.c.event_id,
                )
                .where(
                    setup.c.campaign_id == store.campaign_id,
                    t.events.c.campaign_id == store.campaign_id,
                    t.events.c.kind == "campaign.handler_appointed",
                    t.events.c.seq <= event["seq"],
                )
                .order_by(setup.c.revision.desc())
                .limit(1)
            )
            .mappings()
            .first()
        )
        if (
            appointment is None
            or appointment["event_id"] != tag.gm_setter_appointment
            or json.loads(appointment["body_json"]).get("handler_id")
            != (original.handler if tag.gm_setter_grant else tag.giver)
        ):
            raise ValueError()
        previous = c.scalar(
            sa.select(history.c.body_json)
            .join(
                t.events,
                t.events.c.id == history.c.event_id,
            )
            .where(
                history.c.campaign_id == store.campaign_id,
                t.events.c.seq < event["seq"],
            )
            .order_by(t.events.c.seq.desc())
            .limit(1)
        )
        if previous and any(
            x.id == tag.id for x in _tags(GameState.model_validate_json(previous), lookup_subject)
        ):
            raise ValueError()
        return tag.giver
    except (ValueError, KeyError, TypeError):
        raise WorkflowError(
            "SOURCE_GM_TAG_SETTER_MISSING: recover this original human's creation and appointment."
        ) from None
