"""Whole native Unassuming Doll roll, real attention consequences and scoped benefits."""

import json
from typing import Any, Literal
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_vatgrown as rules
from girlframe.engine.m2 import ChoiceAnswer, GameState, PlayInput, TagState
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef, SceneCast
from girlframe.engine.m3_actors import fingerprint, resolve
from girlframe.engine.m3_girl_runtime_state import has_rule
from girlframe.engine.m3_handler_consequences import active_handler
from girlframe.services.m2_choices import ChoiceEngine
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_dose_up import _cast, _native, _response, _roll_source
from girlframe.services.m3_handler_advancements import _history
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer

KINDS = ("vat_doll_benefits", "vat_doll_attention", "vat_doll_information")


def _access(game: GameService, c: Connection, viewer: GuildViewer) -> None:
    gate = Access(game.store)
    gate.authorize(c, viewer, "plays", director_response=True)
    assert gate.registry is not None
    gate.registry.require_available(rules.RULE)


def _context(
    game: GameService,
    c: Connection,
    state: GameState,
    actor: ActorRef,
    target: ActorRef,
    channel: int,
) -> dict[str, Any]:
    own = _native(game, c, state, actor)
    if target.kind not in ("pilot", "handler") or target == actor:
        raise WorkflowError(
            "SOURCE_DOLL_OBSERVER_REQUIRED: use an actual other native Girl or Handler"
        )
    other = resolve(state, target, profiles(c, game.store.campaign_id))
    cast = _cast(game, c, state, channel)
    handler = active_handler(state)
    if (
        not has_rule(state.sheets[actor.entity], rules.RULE, "VATGROWN")
        or own.inside_frame is not False
        or own.cell is None
        or other.cell != own.cell
        or other.offstage_source
        or other.custody not in (None, "free")
        or target.kind == "handler"
        and target != handler
        or target.kind == "pilot"
        and other.rules != "girl_frame"
        or not all(
            any(x.actor == ref and x.controller == human for x in cast.roles)
            for ref, human in ((actor, own.controller), (target, other.controller))
        )
        or own.vessel_id is None
        or handler is None
        or cast.facilitator is None
    ):
        raise WorkflowError(
            "Establish the real native background scene, original body and actual observer"
        )
    if not any(x.id == cast.id for x in state.scene_casts):
        state.scene_casts.append(cast)
    return dict(
        actor=actor.model_dump(mode="json"),
        caster=own.controller,
        target=target.model_dump(mode="json"),
        counterpart=other.controller,
        vessel=own.vessel_id,
        actor_position=own.position_sha256,
        target_position=other.position_sha256,
        cast=cast.model_dump(mode="json"),
        cast_sha256=fingerprint(cast),
        table=sorted({x.controller for x in cast.roles} | {cast.facilitator}),
        handler=handler.model_dump(mode="json"),
        handler_controller=cast.facilitator,
    )


def prepare(
    game: GameService,
    c: Connection,
    viewer: GuildViewer,
    state: GameState,
    prepared: PlayInput,
    channel: int,
) -> dict[str, Any]:
    _access(game, c, viewer)
    target = prepared.target_actor
    if target is None and prepared.target is not None and str(prepared.target) in state.sheets:
        target = current_ref(state, prepared.target)
    if (
        target is None
        or (prepared.target_actor is not None and prepared.target is not None)
        or prepared.parent
        or prepared.source_work
        or prepared.off_duty_id
    ):
        raise WorkflowError(
            "Name the actual person present while your original Vatgrown fades into the background"
        )
    result = _context(game, c, state, current_ref(state, viewer.user_id), target, channel)
    result.update(phase="unrolled")
    return result


def authorize(
    game: GameService, c: Connection, viewer: GuildViewer, action: dict[str, Any]
) -> None:
    _access(game, c, viewer)
    if viewer.user_id not in action["data"]["vatgrown"]["table"]:
        raise WorkflowError("Only the actual original source-table human owns this Doll response")


def pre_roll(
    game: GameService, c: Connection, viewer: GuildViewer, state: GameState, action: dict[str, Any]
) -> None:
    authorize(game, c, viewer, action)
    expected = prepare(
        game,
        c,
        viewer,
        state,
        PlayInput.model_validate_json(json.dumps(action["data"]["prepared"])),
        int(action["channel_id"]),
    )
    saved = action["data"]["vatgrown"]
    if saved.get("phase") != "unrolled" or any(
        saved[key] != expected[key] for key in expected if key != "phase"
    ):
        raise WorkflowError(
            "Recover the unchanged original Doll body, cast and observer before Heat or RNG"
        )


def results(game: GameService, c: Connection, state: GameState, action: dict[str, Any]) -> None:
    meta = action["data"]["vatgrown"]
    if meta["phase"] != "unrolled":
        raise WorkflowError("Resume actual saved Doll choices without another roll")
    event, total = _roll_source(game, c, action)
    value = rules.Source(
        id=action["id"],
        actor=ActorRef.model_validate(meta["actor"]),
        caster=meta["caster"],
        target=ActorRef.model_validate(meta["target"]),
        counterpart=meta["counterpart"],
        vessel=meta["vessel"],
        cast=SceneCast.model_validate_json(json.dumps(meta["cast"])),
        roll_event=event,
        total=total,
        event=action["data"]["response_event"],
    )
    rules.put(state, value)
    meta["phase"] = "attention" if total <= 7 else "benefits"
    game.request(
        c,
        action,
        value.counterpart if total <= 7 else value.caster,
        "vat_doll_attention" if total <= 7 else "vat_doll_benefits",
    )


def _finish(game: GameService, c: Connection, state: GameState, action: dict[str, Any]) -> None:
    if game.pending(c, action["id"]):
        return
    value = rules.source(state, action["id"])
    rules.put(
        state,
        value.model_copy(
            update=dict(complete=True, completed_event=action["data"]["response_event"])
        ),
    )
    action["data"]["vatgrown"]["phase"] = "complete"
    ChoiceEngine(game).finish(c, state, action)
    game.save_action(c, action)


def _effect(state: GameState, value: rules.Source, kind: str, choice: str, event: str) -> None:
    rules.put(
        state,
        rules.Effect.model_validate(
            dict(
                id="vat-doll-effect:" + value.id + ":" + kind,
                action=value.id,
                actor=value.actor,
                caster=value.caster,
                vessel=value.vessel,
                scene=value.cast.id,
                kind=kind,
                choice=choice,
                event=event,
            )
        ),
    )


def apply_choice(
    game: GameService,
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    row: dict[str, Any],
    answer: ChoiceAnswer,
) -> bool:
    if row["kind"] not in KINDS:
        return False
    value = rules.source(state, action["id"])
    phase = action["data"]["vatgrown"]["phase"]
    event = action["data"]["response_event"]
    if (
        answer.denied
        or answer.fields
        or answer.number is not None
        or answer.flag is not None
        or answer.member is not None
    ):
        raise WorkflowError("Use only the actual owned Doll choice")
    if row["kind"] == "vat_doll_attention":
        if (
            phase != "attention"
            or int(row["actor_id"]) != value.counterpart
            or answer.options not in (("tag",), ("punish",))
        ):
            raise WorkflowError("Only the actual noticed observer chooses Tag or real Punishment")
        if answer.options == ("tag",):
            if not answer.text.strip() or len(answer.text.strip()) > 120:
                raise WorkflowError("Author the actual Tag given by the original observer")
            tag = TagState(
                id="vatgrown-doll-tag:" + value.id,
                label=answer.text.strip(),
                giver=value.counterpart,
                giver_actor=value.target,
                giver_character=value.target.incarnation,
                observers=tuple(action["data"]["vatgrown"]["table"]),
            )
            state.sheets[value.actor.entity].tags.append(tag)
            state.sheets[value.actor.entity].revision += 1
            value = value.model_copy(
                update=dict(attention_choice=row["id"], attention_event=event, tag=tag)
            )
            action["data"]["vatgrown"]["phase"] = "benefits"
            game.request(c, action, value.caster, "vat_doll_benefits")
        else:
            if answer.text:
                raise WorkflowError(
                    "Give the real Punishment instruction through its actual source controls"
                )
            from girlframe.services.m3_role_punishments import open_case

            changed, case = open_case(
                state,
                profiles(c, game.store.campaign_id),
                actor=value.target,
                target=value.actor,
                chooser=value.target,
                source_kind="vatgrown_doll",
                action=value.id,
                source_event=event,
                identity=str(uuid4()),
            )
            for key in GameState.model_fields:
                setattr(state, key, getattr(changed, key))
            value = value.model_copy(
                update=dict(attention_choice=row["id"], attention_event=event, punishment=case)
            )
            action["data"]["vatgrown"]["phase"] = "punishment"
        rules.put(state, value)
    elif row["kind"] == "vat_doll_benefits":
        count = 2 if 8 <= value.total <= 10 else 1
        if (
            phase != "benefits"
            or int(row["actor_id"]) != value.caster
            or len(answer.options) != count
            or len(set(answer.options)) != count
            or not set(answer.options) <= set(rules.BENEFITS)
            or (answer.text and "information" not in answer.options)
        ):
            raise WorkflowError(
                "Choose the exact printed Doll benefits; only a real question supplies text"
            )
        value = value.model_copy(
            update=dict(benefit_choice=row["id"], benefit_event=event, benefits=answer.options)
        )
        rules.put(state, value)
        for kind in answer.options:
            _effect(state, value, kind, row["id"], event)
        if value.total >= 11:
            _effect(state, value, "object", row["id"], event)
        if "information" in answer.options:
            info = rules.Information(
                id=value.id + ":information",
                action=value.id,
                giver=value.target,
                controller=value.counterpart,
                recipient=value.actor,
                recipient_controller=value.caster,
                cast=value.cast,
                question=answer.text.strip(),
                requested_event=event,
            )
            rules.put(state, info)
            if info.question:
                rules.stage_act(state, value.actor, value.cast.id, value.id, event, "question")
            action["data"]["vatgrown"]["phase"] = "information"
            game.request(c, action, value.counterpart, "vat_doll_information")
        else:
            _finish(game, c, state, action)
    else:
        if (
            phase != "information"
            or int(row["actor_id"]) != value.counterpart
            or answer.options
            or not answer.text.strip()
        ):
            raise WorkflowError(
                "The actual original counterpart authors a real answer or offered secret"
            )
        info = next(x for x in rules.records(state, rules.Information) if x.action == value.id)
        rules.put(
            state, info.model_copy(update=dict(answer=answer.text, choice=row["id"], event=event))
        )
        _finish(game, c, state, action)
    return True


def _before(game: GameService, c: Connection, event: str) -> GameState:
    sequence = c.scalar(
        sa.select(t.events.c.seq).where(
            t.events.c.campaign_id == game.store.campaign_id, t.events.c.id == event
        )
    )
    history = t.m2["m2_state_history"]
    body = (
        c.scalar(
            sa.select(history.c.body_json)
            .join(t.events, history.c.event_id == t.events.c.id)
            .where(history.c.campaign_id == game.store.campaign_id, t.events.c.seq < sequence)
            .order_by(t.events.c.seq.desc())
            .limit(1)
        )
        if sequence is not None
        else None
    )
    if body is None:
        raise WorkflowError("Recover the genuine original pre-source scene state")
    return GameState.model_validate_json(body)


def _event(game: GameService, c: Connection, event: str, kinds: tuple[str, ...]) -> dict[str, Any]:
    row = (
        c.execute(
            sa.select(t.events).where(
                t.events.c.campaign_id == game.store.campaign_id, t.events.c.id == event
            )
        )
        .mappings()
        .first()
    )
    if row is None or row["kind"] not in kinds:
        raise WorkflowError("Recover the actual canonical Doll event")
    return dict(row)


def prove(game: GameService, c: Connection, state: GameState, identity: str) -> rules.Source:
    value = rules.source(state, identity)
    born = _history(c, game, value.event)
    first = rules.source(born, identity)
    stable = (
        "id",
        "actor",
        "caster",
        "target",
        "counterpart",
        "vessel",
        "cast",
        "roll_event",
        "total",
        "event",
    )
    if any(getattr(value, key) != getattr(first, key) for key in stable):
        raise WorkflowError("Recover the original immutable Doll source people and receipt")
    action = game.action(c, identity)
    rolled, total = _roll_source(game, c, action)
    confirmed = c.scalar(
        sa.select(t.events.c.id).where(
            t.events.c.campaign_id == game.store.campaign_id,
            t.events.c.kind.in_(("m2.play_confirmed", "m3.play_confirmed")),
            sa.func.json_extract(t.events.c.payload_json, "$.action_id") == identity,
        )
    )
    if confirmed is None:
        raise WorkflowError("Recover the actual original confirmed Doll Play")
    context = _history(c, game, confirmed)
    meta = action["data"].get("vatgrown", {})
    original = current_ref(context, int(action["actor_id"]))
    own = resolve(
        context, original, profiles(c, game.store.campaign_id), require_current_profile=False
    )
    observer = resolve(
        context, value.target, profiles(c, game.store.campaign_id), require_current_profile=False
    )
    if (
        value.actor != original
        or value.caster != own.controller
        or value.counterpart != observer.controller
        or value.vessel != own.vessel_id
        or meta.get("actor_position") != own.position_sha256
        or meta.get("target_position") != observer.position_sha256
        or own.inside_frame is not False
        or own.cell is None
        or own.cell != observer.cell
        or value.cast not in context.scene_casts
        or action["data"]["play"] != rules.PLAY
        or rolled != value.roll_event
        or total != value.total
        or meta.get("actor") != value.actor.model_dump(mode="json")
        or meta.get("target") != value.target.model_dump(mode="json")
        or meta.get("caster") != value.caster
        or meta.get("counterpart") != value.counterpart
        or meta.get("vessel") != value.vessel
        or meta.get("cast") != value.cast.model_dump(mode="json")
        or meta.get("cast_sha256") != fingerprint(value.cast)
        or meta.get("table")
        != sorted(
            {x.controller for x in value.cast.roles}
            | ({value.cast.facilitator} if value.cast.facilitator is not None else set())
        )
        or not has_rule(context.sheets[original.entity], rules.RULE, "VATGROWN")
    ):
        raise WorkflowError(
            "Recover the exact original native body, observer, scene and genuine Doll roll"
        )
    ready = _event(game, c, value.event, ("m2.choice_resolved", "m3.choice_resolved"))
    payload = json.loads(ready["payload_json"])
    row = (
        c.execute(
            sa.select(t.m2["m2_choices"]).where(
                t.m2["m2_choices"].c.campaign_id == game.store.campaign_id,
                t.m2["m2_choices"].c.id == payload.get("choice_id"),
            )
        )
        .mappings()
        .first()
    )
    if (
        row is None
        or row["action_id"] != identity
        or row["kind"] not in ("tag_window", "tag_resolution", "tag_marker_agreement")
    ):
        raise WorkflowError("Recover the actual original completed Tag window before Doll outcomes")
    _response(game, c, identity, row["id"], value.event, int(row["actor_id"]), row["kind"])
    if value.attention_choice or value.attention_event:
        if value.total > 7 or not value.attention_choice or not value.attention_event:
            raise WorkflowError("Only the actual low result grants this attention consequence")
        answer = _response(
            game,
            c,
            identity,
            value.attention_choice,
            value.attention_event,
            value.counterpart,
            "vat_doll_attention",
        )
        attention = rules.source(_history(c, game, value.attention_event), identity)
        if (
            attention.attention_choice != value.attention_choice
            or attention.punishment != value.punishment
            or attention.tag != value.tag
        ):
            raise WorkflowError("Recover the genuine actual observer's consequence choice")
        if answer.options == ("tag",):
            if (
                value.punishment
                or value.tag is None
                or value.tag.label != answer.text.strip()
                or value.tag.giver_actor != value.target
                or value.tag.giver != value.counterpart
            ):
                raise WorkflowError("Recover the actual Tag given by this original observer")
        elif answer.options != ("punish",) or value.tag is not None or value.punishment is None:
            raise WorkflowError(
                "Recover the actual source-owned Punishment instead of a fake acknowledgment"
            )
    if value.benefit_choice or value.benefit_event:
        if not value.benefit_choice or not value.benefit_event:
            raise WorkflowError("Recover the exact original benefit choice event")
        answer = _response(
            game,
            c,
            identity,
            value.benefit_choice,
            value.benefit_event,
            value.caster,
            "vat_doll_benefits",
        )
        selected = rules.source(_history(c, game, value.benefit_event), identity)
        count = 2 if 8 <= value.total <= 10 else 1
        if (
            selected.benefits != value.benefits
            or answer.options != value.benefits
            or len(value.benefits) != count
            or not set(value.benefits) <= set(rules.BENEFITS)
        ):
            raise WorkflowError("Recover the actual printed original Vatgrown benefits")
        if value.total <= 7 and value.attention_event is None:
            raise WorkflowError(
                "Complete the actual attention consequence before choosing a benefit"
            )
        if value.punishment:
            case = next(
                (
                    x
                    for x in _history(c, game, value.benefit_event).role_punishments
                    if x.id == value.punishment
                ),
                None,
            )
            if case is None or not case.effect_event or not case.completion_event:
                raise WorkflowError("Complete actual Punishment and required child work first")
    if value.complete:
        if value.completed_event is None or not value.benefit_event:
            raise WorkflowError("Complete the real original benefit and information work first")
        completed = rules.source(_history(c, game, value.completed_event), identity)
        if (
            not completed.complete
            or completed.completed_event != value.completed_event
            or action["state"] != "complete"
        ):
            raise WorkflowError("Recover the actual canonical complete Doll source")
    return value


def prove_effect(game: GameService, c: Connection, state: GameState, identity: str) -> rules.Effect:
    effect = next((x for x in rules.records(state, rules.Effect) if x.id == identity), None)
    if effect is None:
        raise WorkflowError("Recover the real original Doll benefit")
    value = prove(game, c, state, effect.action)
    if (
        effect not in rules.records(_history(c, game, effect.event), rules.Effect)
        or effect.actor != value.actor
        or effect.vessel != value.vessel
        or effect.caster != value.caster
        or effect.scene != value.cast.id
        or effect.choice != value.benefit_choice
        or effect.event != value.benefit_event
        or effect.kind not in value.benefits
        and not (effect.kind == "object" and value.total >= 11)
    ):
        raise WorkflowError("Recover the exact actual source-owned benefit")
    return effect


def prove_tag(
    game: GameService, c: Connection, state: GameState, owner: int, tag: TagState
) -> None:
    if not tag.id.startswith("vatgrown-doll-tag:"):
        return
    value = prove(game, c, state, tag.id.removeprefix("vatgrown-doll-tag:"))
    if (
        value.actor != current_ref(state, owner)
        or value.tag is None
        or any(
            getattr(tag, key) != getattr(value.tag, key)
            for key in ("id", "label", "giver", "giver_actor", "giver_character", "observers")
        )
    ):
        raise WorkflowError("Recover the actual original noticed Vatgrown Tag")


def _prove_act(game: GameService, c: Connection, state: GameState, act: rules.Act) -> None:
    born = _history(c, game, act.event)
    if act not in rules.records(born, rules.Act):
        raise WorkflowError("Recover the genuine actual fictional act and exact consumed effects")
    for identity in act.effects:
        effect = prove_effect(game, c, born, identity)
        if (
            effect.actor != act.actor
            or effect.scene != act.scene
            or effect.kind not in ("quiet", "object")
        ):
            raise WorkflowError(
                "An act consumes only its original actually active background effects"
            )
    if act.kind == "play":
        event = _event(game, c, act.event, ("m2.rolled", "m3.rolled"))
        actual = game.action(c, act.source_action)
        if (
            json.loads(event["payload_json"]).get("action_id") != act.source_action
            or str(actual["actor_id"]) != act.actor.entity
            or actual["scene_id"] != act.scene
        ):
            raise WorkflowError(
                "Only the original actual performed Play consumes background presentation"
            )
    elif act.kind == "question":
        info = next(
            (x for x in rules.records(born, rules.Information) if x.action == act.source_action),
            None,
        )
        if (
            info is None
            or not info.question
            or info.recipient != act.actor
            or info.requested_event != act.event
        ):
            raise WorkflowError("Only the actual authored question counts as speaking")
    elif act.kind == "departure":
        if not any(
            x.event == act.event and x.actor == act.actor and x.before.id == act.scene
            for x in rules.records(born, rules.Departure)
        ):
            raise WorkflowError("Recover the actual source-authored exit")
    elif not any(
        x.event == act.event and x.actor == act.actor and x.after.id == act.scene
        for x in rules.records(born, rules.Return)
    ):
        raise WorkflowError("Recover the actual factual re-entry")


def require_attention(
    game: GameService,
    c: Connection,
    state: GameState,
    actor: ActorRef,
    scene: str,
    purpose: Literal["intercept", "discovery", "expectation"],
) -> None:
    for effect in rules.records(state, rules.Effect):
        if effect.actor != actor or effect.scene != scene:
            continue
        prove_effect(game, c, state, effect.id)
        for act in rules.records(state, rules.Act):
            if effect.id in act.effects:
                _prove_act(game, c, state, act)
        if rules.active(state, effect) and (
            (effect.kind == "quiet" and purpose in ("intercept", "discovery"))
            or (effect.kind == "object" and purpose == "expectation")
        ):
            raise WorkflowError(
                "The actual Doll source prevents this attention until she acts or leaves its scene"
            )


def _current_body(
    game: GameService,
    c: Connection,
    state: GameState,
    actor: ActorRef,
    vessel: str,
    viewer: GuildViewer,
) -> None:
    if actor != current_ref(state, viewer.user_id):
        raise WorkflowError(
            "Use only your actual original native person, not another profile or replacement"
        )
    actual = _native(game, c, state, actor)
    if actual.vessel_id != vessel or actual.inside_frame is not False or actual.cell is None:
        raise WorkflowError(
            "Recover the original outside-Frame body and actual known physical placement"
        )


def departure_source(
    game: GameService,
    c: Connection,
    state: GameState,
    viewer: GuildViewer,
    effect: str,
    channel: int,
) -> rules.Effect:
    _access(game, c, viewer)
    value = prove_effect(game, c, state, effect)
    _current_body(game, c, state, value.actor, value.vessel, viewer)
    cast = _cast(game, c, state, channel)
    if (
        value.kind != "leave"
        or cast.id != value.scene
        or not rules.active(state, value)
        or any(x.effect == value.id for x in rules.records(state, rules.Departure))
    ):
        raise WorkflowError("Use your actual unspent unopposed exit in its original real scene")
    return value


def prove_departure(
    game: GameService, c: Connection, state: GameState, identity: str
) -> rules.Departure:
    value = next((x for x in rules.records(state, rules.Departure) if x.id == identity), None)
    if value is None:
        raise WorkflowError("Recover the actual original factual Doll exit")
    effect = prove_effect(game, c, state, value.effect)
    born = _history(c, game, value.event)
    before = _before(game, c, value.event)
    event = _event(game, c, value.event, ("m3.vatgrown_departed",))
    if (
        value not in rules.records(born, rules.Departure)
        or event["actor_id"] != effect.actor.entity
        or value.before not in before.scene_casts
        or value.after not in born.scene_casts
        or value.actor != effect.actor
        or value.vessel != effect.vessel
        or before.sheets[value.actor.entity] != born.sheets[value.actor.entity]
        or before.placements != born.placements
    ):
        raise WorkflowError(
            "Recover the genuine cast departure without invented body, map or resource changes"
        )
    scratch = GameState.model_validate_json(before.model_dump_json())
    produced = rules.record_departure(
        scratch, effect, value.before, value.after, value.event, value.account
    )
    if produced != value:
        raise WorkflowError("Recover the actual exact effects consumed at this original departure")
    return value


def return_source(
    game: GameService,
    c: Connection,
    state: GameState,
    viewer: GuildViewer,
    departure: str,
    channel: int,
) -> rules.Departure:
    _access(game, c, viewer)
    value = prove_departure(game, c, state, departure)
    _current_body(game, c, state, value.actor, value.vessel, viewer)
    cast = _cast(game, c, state, channel)
    if any(x.departure == value.id for x in rules.records(state, rules.Return)) or any(
        x.actor == value.actor for x in cast.roles
    ):
        raise WorkflowError(
            "Restore your original unreturned absence before joining this actual scene"
        )
    own = _native(game, c, state, value.actor)
    actual_others = [
        resolve(state, x.actor, profiles(c, game.store.campaign_id), require_current_profile=False)
        for x in cast.roles
        if x.actor != value.actor and x.actor.kind in ("pilot", "handler")
    ]
    if not actual_others or not any(
        x.cell is not None and x.cell == own.cell for x in actual_others
    ):
        raise WorkflowError(
            "Actually establish your legal current co-presence; re-entry never teleports anyone"
        )
    return value


def validate_role_case(c: Connection, game: GameService, state: GameState, case: Any) -> None:
    from girlframe.services.m3_intracadre_marriage import original_offender

    value = prove(game, c, state, case.action or "")
    if (
        case.source_kind != "vatgrown_doll"
        or value.total > 7
        or value.punishment != case.id
        or value.target != case.executor
        or value.target != case.chooser
        or case.chooser_controller != value.counterpart
        or case.executor_controller != value.counterpart
        or case.source_event != value.attention_event
        or original_offender(game, c, state, case.id, case.source_event, case.subject)
        != value.actor
    ):
        raise WorkflowError("Recover the original actual noticed Vatgrown consequence and observer")


def complete_role_case(c: Connection, game: GameService, case: Any, event: str) -> None:
    state = load_state(c, game.store.campaign_id)
    validate_role_case(c, game, state, case)
    if case.completion_event != event or not case.effect_event:
        raise WorkflowError(
            "Complete actual Punishment and mandatory children before the Doll benefit"
        )
    action = game.action(c, case.action)
    if action["data"]["vatgrown"]["phase"] != "punishment":
        return
    value = rules.source(state, case.action)
    action["data"]["vatgrown"]["phase"] = "benefits"
    game.request(c, action, value.caster, "vat_doll_benefits")
    game.save_action(c, action)


def projection(
    game: GameService, c: Connection, state: GameState, action: dict[str, Any], row: dict[str, Any]
) -> dict[str, Any]:
    value = rules.source(state, action["id"])
    if row["kind"] == "vat_doll_attention":
        return dict(
            options=(
                ("tag", "Give her an actual Tag"),
                ("punish", "Inflict a real supported Punishment"),
            ),
            minimum=1,
            maximum=1,
            text=True,
            label="Only if Tag: your actual authored label",
        )
    if row["kind"] == "vat_doll_information":
        info = next(x for x in rules.records(state, rules.Information) if x.action == value.id)
        return dict(
            options=(),
            minimum=0,
            maximum=0,
            text=True,
            label="Your actual answer" if info.question else "Your actual offered secret",
            question=info.question,
        )
    count = 2 if 8 <= value.total <= 10 else 1
    return dict(
        options=(
            ("quiet", "Avoid notice while quiet or still until you act"),
            ("leave", "Leave this scene without confrontation or interception"),
            ("information", "Get an answer or offered secret"),
        ),
        minimum=count,
        maximum=count,
        text=True,
        label="If information: your actual question, or leave blank for a secret",
    )


def prove_return(game: GameService, c: Connection, state: GameState, identity: str) -> rules.Return:
    value = next((x for x in rules.records(state, rules.Return) if x.id == identity), None)
    if value is None:
        raise WorkflowError("Recover the genuine factual Doll re-entry")
    departure = prove_departure(game, c, state, value.departure)
    born = _history(c, game, value.event)
    before = _before(game, c, value.event)
    event = _event(game, c, value.event, ("m3.vatgrown_returned",))
    if (
        value not in rules.records(born, rules.Return)
        or event["actor_id"] != value.actor.entity
        or value.actor != departure.actor
        or value.vessel != departure.vessel
        or value.before not in before.scene_casts
        or value.after not in born.scene_casts
        or before.sheets[value.actor.entity] != born.sheets[value.actor.entity]
        or before.placements != born.placements
    ):
        raise WorkflowError(
            "Recover the actual original re-entry without fabricated movement or body changes"
        )
    scratch = GameState.model_validate_json(before.model_dump_json())
    scratch.scene_casts = [
        value.after if x.id == value.before.id else x for x in scratch.scene_casts
    ]
    if (
        rules.record_return(
            scratch, departure, value.before, value.after, value.event, value.account
        )
        != value
    ):
        raise WorkflowError("Recover the actual source-attributed cast re-entry")
    return value


class DollService:
    def __init__(self, game: GameService):
        self.game, self.store = game, game.store

    def menu(self, viewer: GuildViewer, channel: int) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            _access(self.game, c, viewer)
            state = load_state(c, self.store.campaign_id)
            targets = []
            if str(viewer.user_id) in state.sheets:
                actor = current_ref(state, viewer.user_id)
                try:
                    cast = _cast(self.game, c, state, channel)
                except (WorkflowError, ValueError):
                    cast = None
                for role in cast.roles if cast else ():
                    if role.actor == actor or role.actor.kind not in ("pilot", "handler"):
                        continue
                    try:
                        _context(self.game, c, state, actor, role.actor, channel)
                    except (WorkflowError, ValueError):
                        continue
                    targets.append(
                        dict(
                            ref=role.actor.model_dump(mode="json"),
                            label=resolve(
                                state, role.actor, profiles(c, self.store.campaign_id)
                            ).label,
                        )
                    )
            return dict(revision=state.revision, targets=targets, history=self._tasks(c, viewer))

    def _tasks(self, c: Connection, viewer: GuildViewer) -> list[dict[str, Any]]:
        state = load_state(c, self.store.campaign_id)
        return [
            dict(
                id=x.id,
                revision=state.revision,
                label="Your actual Unassuming Doll source",
                phase="complete" if x.complete else "pending",
                pending=False,
            )
            for x in rules.records(state, rules.Source)
            if viewer.user_id in (x.caster, x.counterpart)
        ]

    def view(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            state = load_state(c, self.store.campaign_id)
            value = prove(self.game, c, state, identity)
            if viewer.user_id not in (value.caster, value.counterpart):
                raise WorkflowError(
                    "Only the actual original source participants read this private information"
                )
            information = next(
                (x for x in rules.records(state, rules.Information) if x.action == identity), None
            )
            if information is not None:
                requested = next(
                    (
                        x
                        for x in rules.records(
                            _history(c, self.game, information.requested_event), rules.Information
                        )
                        if x.id == information.id
                    ),
                    None,
                )
                if (
                    requested is None
                    or requested.question != information.question
                    or requested.giver != value.target
                    or requested.recipient != value.actor
                ):
                    raise WorkflowError(
                        "Recover the actual authored question or offered-secret source"
                    )
                if information.event:
                    if information.choice is None:
                        raise WorkflowError("Recover the actual original answer choice")
                    answer = _response(
                        self.game,
                        c,
                        identity,
                        information.choice,
                        information.event,
                        value.counterpart,
                        "vat_doll_information",
                    )
                    delivered = next(
                        (
                            x
                            for x in rules.records(
                                _history(c, self.game, information.event), rules.Information
                            )
                            if x.id == information.id
                        ),
                        None,
                    )
                    if (
                        delivered != information
                        or answer.text != information.answer
                        or not information.answer.strip()
                    ):
                        raise WorkflowError(
                            "Recover the original actual substantive answer or offered secret"
                        )
            effects = [
                prove_effect(self.game, c, state, x.id)
                for x in rules.records(state, rules.Effect)
                if x.action == identity
            ]
            departed = [
                prove_departure(self.game, c, state, x.id)
                for x in rules.records(state, rules.Departure)
                if x.effect in {e.id for e in effects}
            ]
            returned = [
                prove_return(self.game, c, state, x.id)
                for x in rules.records(state, rules.Return)
                if x.departure in {d.id for d in departed}
            ]
            own = viewer.user_id == value.caster
            leave = (
                next((x.id for x in effects if x.kind == "leave" and rules.active(state, x)), None)
                if own
                else None
            )
            pending_departure = (
                next(
                    (x.id for x in departed if not any(y.departure == x.id for y in returned)), None
                )
                if own
                else None
            )
            return dict(
                id=identity,
                revision=state.revision,
                phase=self.game.action(c, identity)["data"]["vatgrown"]["phase"],
                caster=value.caster,
                counterpart=value.counterpart,
                total=value.total,
                benefits=value.benefits,
                tag=value.tag.label if value.tag else None,
                punishment=value.punishment,
                information=information.model_dump(mode="json", exclude={"cast"})
                if information
                else None,
                quiet=rules.notice_blocked(state, value.actor, value.cast.id),
                object=rules.object_treatment(state, value.actor, value.cast.id),
                leave=leave,
                departure=pending_departure,
                returned=bool(returned),
                departure_account=departed[-1].account if own and departed else None,
                return_account=returned[-1].account if own and returned else None,
                channel=value.cast.channel,
            )
