"""Original people author Changeling sources; real brains and reducers carry effects."""

import json
from collections.abc import Callable
from typing import Any, Literal
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_changeling as rules
from girlframe.engine.m2 import ChoiceAnswer, GameState, PlayInput
from girlframe.engine.m3_actor_bonds import change, current_ref
from girlframe.engine.m3_actor_state import ActorRef, SceneCast
from girlframe.engine.m3_actors import fingerprint, resolve
from girlframe.engine.m3_handler_consequences import active_handler
from girlframe.engine.m3_intracadre_marriage import available, debit
from girlframe.engine.m3_mockingbird import actor_tags, give_tag
from girlframe.engine.m3_requisition_state import FrameRuleReceipt
from girlframe.services import m3_changeling_support as support
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_dose_up import _cast, _roll_source
from girlframe.services.m3_handler_advancements import _history
from girlframe.services.m3_intracadre_marriage import prepare_payment
from girlframe.services.m3_requisitions import RequisitionService
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer

HEAT_IDS = tuple(rules.PLAYS)
KINDS = (
    "changeling_low_erase",
    "changeling_recent",
    "changeling_clay_owner",
    "changeling_clay_handler",
    "changeling_taste",
)


def _copy(state: GameState, other: GameState) -> None:
    for field in GameState.model_fields:
        setattr(state, field, getattr(other, field))


def _text(value: str, maximum: int = 1200) -> str:
    if not value.strip() or len(value) > maximum:
        raise WorkflowError("Provide the actual source text within its saved limit")
    return value


def authorize(
    game: GameService, c: Connection, viewer: GuildViewer, action: dict[str, Any] | None = None
) -> None:
    Access(game.store).authorize(c, viewer, "plays", director_response=action is not None)
    if action is not None and viewer.user_id not in action["data"]["changeling"]["table"]:
        raise WorkflowError("Use the actual original Changeling source table")


def require_rule(
    game: GameService, c: Connection, state: GameState, actor: ActorRef, rule: str
) -> None:
    rules.frame(state, actor)
    registry = Access(game.store).registry
    if registry is None:
        raise WorkflowError("Recover the actual reviewed Changeling rules")
    registry.require_available(rule)
    if rule in rules.REQUISITIONS:
        receipt = rules.held(state, actor, rule)
        if receipt is None:
            raise WorkflowError("Acquire this actual Frame's real printed Requisition first")
        prove_acquisition(game, c, state, receipt)


def prove_acquisition(
    game: GameService, c: Connection, state: GameState, value: FrameRuleReceipt
) -> None:
    source = (
        c.execute(
            sa.select(t.events).where(
                t.events.c.campaign_id == game.store.campaign_id,
                t.events.c.id == value.source_event,
            )
        )
        .mappings()
        .first()
    )
    saved = _history(c, game, value.source_event)
    if (
        source is None
        or source["kind"] != "m3.ability_unlock_purchased"
        or source["actor_id"] != value.actor.entity
        or value not in saved.requisitions
        or value.donor_frame != rules.FRAME
        or value.rule_id not in rules.REQUISITIONS
        or value.price != 2
        or value.grant != "changeling:" + value.id
        or json.loads(source["payload_json"]).get("requisition_id") != value.id
    ):
        raise WorkflowError("Recover the original genuine paid Changeling source")


def _brain(
    game: GameService, c: Connection, state: GameState, actor: ActorRef, purpose: str = "mental"
) -> rules.BrainRef:
    value = support.brain(game, c, state, actor, purpose=purpose)
    if (
        not isinstance(value, rules.BrainRef)
        or value.actor != actor
        or not value.id
        or not value.vessel
        or not value.source
    ):
        raise WorkflowError("Prove the actual original person's brain and body source")
    return value


def _owned(
    game: GameService,
    c: Connection,
    state: GameState,
    viewer: GuildViewer,
    actor: ActorRef,
    controller: int | None = None,
) -> None:
    actual = resolve(
        state, actor, profiles(c, game.store.campaign_id), require_current_profile=False
    )
    if (
        actual.controller != viewer.user_id
        or controller is not None
        and controller != viewer.user_id
    ):
        raise WorkflowError("Only this actual original role's human authors its choice")


def _audit(game: GameService, c: Connection, event: str, kind: str, controller: int) -> GameState:
    row = (
        c.execute(
            sa.select(t.events).where(
                t.events.c.campaign_id == game.store.campaign_id, t.events.c.id == event
            )
        )
        .mappings()
        .first()
    )
    if row is None or row["kind"] != kind or row["actor_id"] != str(controller):
        raise WorkflowError("Recover the actual original human-authored source event")
    return _history(c, game, event)


def prove_speech(game: GameService, c: Connection, state: GameState, identity: str) -> rules.Speech:
    value = rules.record(state, rules.Speech, identity)
    saved = _audit(game, c, value.event, "m3.changeling_spoken", value.controller)
    born = rules.record(saved, rules.Speech, identity)
    if born.model_copy(update=dict(used_by=value.used_by)) != value:
        raise WorkflowError("Preserve the original actual words, roles, brains and scene")
    return value


def prove_source(
    game: GameService, c: Connection, state: GameState, identity: str
) -> rules.Session:
    value = rules.session(state, identity)
    action = game.action(c, identity)
    event, total = _roll_source(game, c, action)
    meta = action["data"].get("changeling", {})
    expected = dict(
        actor=value.actor.model_dump(mode="json"),
        brain=value.brain.model_dump(mode="json"),
        frame=value.frame,
        target=value.target.model_dump(mode="json") if value.target else None,
        target_brain=value.target_brain.model_dump(mode="json") if value.target_brain else None,
        handler=value.handler.model_dump(mode="json"),
        handler_controller=value.handler_controller,
        cast=value.cast.model_dump(mode="json"),
        cast_sha256=fingerprint(value.cast),
        speech=value.speech,
    )
    if (
        value.roll_event != event
        or value.total != total
        or value.actor.entity != str(action["actor_id"])
        or value.play != action["data"]["play"]
        or any(meta.get(key) != item for key, item in expected.items())
    ):
        raise WorkflowError(
            "Preserve the real original Changeling source, receipt, people and body"
        )
    born = rules.session(_history(c, game, value.event), value.id)
    immutable = {
        "id",
        "actor",
        "brain",
        "frame",
        "play",
        "target",
        "target_brain",
        "handler",
        "handler_controller",
        "cast",
        "total",
        "roll_event",
        "event",
        "speech",
        "identities",
    }
    if any(getattr(born, key) != getattr(value, key) for key in immutable):
        raise WorkflowError("Preserve the actual original result's held Identity batch and source")
    return value


def prove_node(game: GameService, c: Connection, state: GameState, identity: str) -> rules.String:
    value = rules.record(state, rules.String, identity)
    born = rules.record(_history(c, game, value.event), rules.String, identity)
    if (
        born.spent_event
        or born.spent_by
        or born.model_copy(update=dict(spent_by=value.spent_by, spent_event=value.spent_event))
        != value
    ):
        raise WorkflowError("Preserve the original actual brain-bound Psych String birth")
    saved = _history(c, game, value.event)
    if value.origin == "start":
        starting = rules.record(saved, rules.StartingBond, value.source)
        valid = (
            starting.actor == value.actor
            and starting.frame == value.frame
            and starting.subject == value.subject.actor
            and starting.node == value.id
            and starting.attached_event == value.event
        )
    elif value.origin == "deepen":
        from girlframe.engine.m3_bond_operations import records as bond_operations

        operation = rules.record(saved, rules.Deepening, value.source)
        valid = (
            operation.first == value.actor
            and operation.second == value.subject.actor
            and operation.event == value.event
            and any(
                item.id == operation.source
                and item.delta == 1
                and item.event == value.event
                and {item.first, item.second} == {operation.first, operation.second}
                for item in bond_operations(saved)
            )
        )
    elif value.origin == "web":
        access = rules.record(saved, rules.Access, value.source)
        valid = (
            access.actor == value.actor
            and access.frame == value.frame
            and rules.same_brain(access.subject, value.subject)
            and access.used_event == value.event
        )
    else:
        gift = rules.record(saved, rules.AssaultGift, value.source)
        valid = (
            gift.actor == value.actor
            and gift.frame == value.frame
            and rules.same_brain(gift.subject, value.subject)
            and gift.chosen is True
            and gift.completed_event == value.event
        )
    if not valid:
        raise WorkflowError(
            "Prove the actual starting/deepen/implant/Assault producer of this String"
        )
    return value


def prove_fingers(
    game: GameService, c: Connection, state: GameState, identity: str
) -> rules.Fingers:
    value = rules.get(state, identity)
    saved = _audit(
        game, c, value.event, "m3.changeling_fingers_used", value.controllers[value.actor.token]
    )
    born = rules.get(saved, identity)
    for field in (
        "actor",
        "brain",
        "frame",
        "target",
        "subject",
        "node",
        "kind",
        "cast",
        "handler",
        "handler_controller",
        "controllers",
        "event",
        "account",
        "incoming",
        "subject_scene",
    ):
        if getattr(value, field) != getattr(born, field):
            raise WorkflowError("Preserve the actual original consumed String and chosen source")
    node = prove_node(game, c, state, value.node)
    if (
        node.actor != value.actor
        or not rules.same_brain(node.subject, value.subject)
        or node.spent_by != value.id
        or node.spent_event != value.event
    ):
        raise WorkflowError("The actual original String must be consumed by exactly this source")
    return value


def prepare(
    game: GameService,
    c: Connection,
    viewer: GuildViewer,
    state: GameState,
    prepared: PlayInput,
    channel: int,
) -> dict[str, Any]:
    authorize(game, c, viewer)
    actor = current_ref(state, viewer.user_id)
    require_rule(game, c, state, actor, rules.PLAYS[prepared.play])
    scene = _cast(game, c, state, channel)
    handler = active_handler(state)
    if (
        handler is None
        or state.handler is None
        or not any(
            role.actor == actor and role.controller == viewer.user_id for role in scene.roles
        )
        or prepared.target is not None
        or prepared.target_actor is not None
        or prepared.order_id
        or prepared.off_duty_id
    ):
        raise WorkflowError(
            "Use the actual original Changeling and its genuine declared source scene"
        )
    speech = None
    target = None
    if prepared.play == "changeling_blank_slate":
        speech = prove_speech(game, c, state, prepared.source_work or "")
        if (
            speech.kind != "definition"
            or speech.addressed != actor
            or speech.used_by
            or fingerprint(speech.cast) != fingerprint(scene)
        ):
            raise WorkflowError("Use the actual other person's still-unused who-you-are statement")
        target = speech.actor
        low = support.identity_options(game, c, state, actor, chooser=actor, clause="blank_low")
        support.identity_options(game, c, state, actor, chooser=actor, clause="blank_all")
        if not low:
            raise WorkflowError(
                "SOURCE_IDENTITY_REMOVAL_REQUIRED: support the actual possible "
                "erasures before rolling"
            )
    elif prepared.source_work:
        raise WorkflowError("Use the actual voluntary body change, not another source token")
    facts = support.context(game, c, state, actor, scene, prepared.play, target)
    brain = _brain(game, c, state, actor)
    subject = _brain(game, c, state, target) if target else None
    if speech and (
        not rules.same_brain(speech.addressed_brain, brain)
        or subject is None
        or not rules.same_brain(speech.brain, subject)
    ):
        raise WorkflowError("Use the original actual people and brains that held this conversation")
    if scene not in state.scene_casts:
        state.scene_casts.append(scene)
    return dict(
        actor=actor.model_dump(mode="json"),
        brain=brain.model_dump(mode="json"),
        frame=rules.frame(state, actor),
        target=target.model_dump(mode="json") if target else None,
        target_brain=subject.model_dump(mode="json") if subject else None,
        handler=handler.model_dump(mode="json"),
        handler_controller=state.handler,
        cast=scene.model_dump(mode="json"),
        cast_sha256=fingerprint(scene),
        table=sorted(
            {role.controller for role in scene.roles}
            | {state.handler}
            | ({scene.facilitator} if scene.facilitator else set())
        ),
        speech=speech.id if speech else None,
        sourcefacts=facts,
        phase="unrolled",
    )


def bind(state: GameState, action: dict[str, Any], event: str) -> None:
    meta = action["data"]["changeling"]
    meta["begin_event"] = event
    if meta["speech"]:
        value = rules.record(state, rules.Speech, meta["speech"])
        rules.put(state, value.model_copy(update=dict(used_by=action["id"])))


def pre_roll(
    game: GameService, c: Connection, viewer: GuildViewer, state: GameState, action: dict[str, Any]
) -> None:
    meta = action["data"]["changeling"]
    value = rules.record(state, rules.Speech, meta["speech"]) if meta["speech"] else None
    if value:
        if value.used_by != action["id"]:
            raise WorkflowError("Preserve the actual original statement reservation")
        rules.put(state, value.model_copy(update=dict(used_by=None)))
    try:
        expected = prepare(
            game,
            c,
            viewer,
            state,
            PlayInput.model_validate(action["data"]["prepared"]),
            int(action["channel_id"]),
        )
    finally:
        if value:
            rules.put(state, value)
    if any(meta.get(key) != item for key, item in expected.items() if key != "phase"):
        raise WorkflowError(
            "Reopen the unchanged actual brain, speaker, Frame and scene before rolling"
        )


def _request(
    game: GameService, c: Connection, action: dict[str, Any], controller: int, kind: str
) -> None:
    if not any(
        row["kind"] == kind and row["actor_id"] == str(controller)
        for row in game.pending(c, action["id"])
    ):
        game.request(c, action, controller, kind)


def _owed(game: GameService, c: Connection, work: tuple[str, ...]) -> bool:
    table = t.m3["m3_required_work"]
    return any(
        c.scalar(
            sa.select(table.c.state)
            .where(table.c.campaign_id == game.store.campaign_id, table.c.id == identity)
            .order_by(table.c.revision.desc())
            .limit(1)
        )
        != "resolved"
        for identity in work
    )


def _live(
    game: GameService, c: Connection, state: GameState, expected: rules.BrainRef
) -> rules.BrainRef:
    actual = _brain(game, c, state, expected.actor)
    if not rules.same_brain(actual, expected):
        raise WorkflowError("Use the actual original brain; a shared controller is not continuity")
    return actual


def _choice_controller(
    game: GameService, c: Connection, state: GameState, expected: rules.BrainRef
) -> int:
    """Continue an unchanged NPC brain through its real controller claim.

    Historical BrainRefs and event authors stay immutable. This accepts neither
    another actor nor a new brain merely because a human account is shared.
    """
    if expected.actor.kind != "npc" or state.world is None:
        return expected.controller
    npc = next((x for x in state.world.npcs if x.id == expected.actor.entity), None)
    if npc is None or not npc.alive or npc.controller == expected.controller:
        return expected.controller
    actual = _live(game, c, state, expected)
    claims = c.execute(
        sa.select(t.events)
        .where(
            t.events.c.campaign_id == game.store.campaign_id,
            t.events.c.kind == "m3.npc_control_claimed",
        )
        .order_by(t.events.c.seq.desc())
    ).mappings()
    claim = next(
        (x for x in claims if json.loads(x["payload_json"]).get("entity_id") == npc.id),
        None,
    )
    if claim is None or claim["actor_id"] != str(actual.controller):
        raise WorkflowError("Recover this original NPC's actual controller-claim source")
    after = _history(c, game, claim["id"])
    history = t.m2["m2_state_history"]
    raw = c.scalar(
        sa.select(history.c.body_json)
        .join(t.events, history.c.event_id == t.events.c.id)
        .where(
            history.c.campaign_id == game.store.campaign_id,
            t.events.c.campaign_id == game.store.campaign_id,
            t.events.c.seq < claim["seq"],
        )
        .order_by(t.events.c.seq.desc())
        .limit(1)
    )
    before = GameState.model_validate_json(raw) if raw else None
    old = (
        next((x for x in before.world.npcs if x.id == npc.id), None)
        if before and before.world
        else None
    )
    new = next((x for x in after.world.npcs if x.id == npc.id), None) if after.world else None
    if (
        old is None
        or new is None
        or new.controller != actual.controller
        or new != old.model_copy(update={"controller": actual.controller})
        or not rules.same_brain(_brain(game, c, after, expected.actor), expected)
    ):
        raise WorkflowError("Preserve the actual same-brain NPC controller handover")
    return actual.controller


def _owned_brain_choice(
    game: GameService,
    c: Connection,
    state: GameState,
    viewer: GuildViewer,
    brain: rules.BrainRef,
    scene: SceneCast,
) -> None:
    controller = _choice_controller(game, c, state, brain)
    _owned(game, c, state, viewer, brain.actor, controller)
    _live(game, c, state, brain)
    if controller != brain.controller:
        current = next((x for x in state.scene_casts if x.id == scene.id and x.open), None)
        if current is None or not any(
            role.actor == brain.actor and role.controller == controller for role in current.roles
        ):
            raise WorkflowError("Join this actual NPC role in the original source scene first")


def _blank_finish(
    game: GameService,
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    source: rules.Session,
    event: str,
) -> None:
    if source.erased_event is None or _owed(game, c, source.work):
        return
    if source.total >= 11 and source.blank is None:
        changed, identity, work = support.grant_blank(game, c, state, source, event)
        _copy(state, changed)
        grant = rules.BlankSlate(
            id=rules.identity("blank", source.id),
            session=source.id,
            actor=source.actor,
            brain=source.brain,
            identity=identity,
            event=event,
            work=tuple(work),
        )
        rules.put(state, grant)
        source = source.model_copy(
            update=dict(blank=grant.id, work=tuple(dict.fromkeys((*source.work, *work))))
        )
        rules.put(state, source)
    if source.total < 8 and source.recent_event is None:
        _request(game, c, action, source.handler_controller, "changeling_recent")
    else:
        action["data"]["changeling"]["phase"] = "effects"


def results(game: GameService, c: Connection, state: GameState, action: dict[str, Any]) -> None:
    meta = action["data"]["changeling"]
    if meta["phase"] != "unrolled":
        raise WorkflowError("Resume the actual original Changeling result without rolling again")
    rolled, total = _roll_source(game, c, action)
    source = rules.Session(
        id=action["id"],
        actor=ActorRef.model_validate(meta["actor"]),
        brain=rules.BrainRef.model_validate(meta["brain"]),
        frame=meta["frame"],
        play=action["data"]["play"],
        target=ActorRef.model_validate(meta["target"]) if meta["target"] else None,
        target_brain=rules.BrainRef.model_validate(meta["target_brain"])
        if meta["target_brain"]
        else None,
        handler=ActorRef.model_validate(meta["handler"]),
        handler_controller=meta["handler_controller"],
        cast=SceneCast.model_validate_json(json.dumps(meta["cast"])),
        total=total,
        roll_event=rolled,
        event=action["data"].get("response_event") or rolled,
        speech=meta["speech"],
        identities=tuple(item.id for item in state.sheets[meta["actor"]["entity"]].identities)
        if action["data"]["play"] == "changeling_blank_slate"
        else (),
    )
    rules.put(state, source)
    meta["phase"] = "choices"
    if source.play == "changeling_blank_slate":
        if 8 <= total <= 10:
            assert source.target is not None
            _copy(state, change(state, source.actor, source.target, 1, source.event))
            meta["phase"] = "effects"
        elif total < 8:
            _request(game, c, action, int(source.actor.entity), "changeling_low_erase")
        else:
            changed, work = support.erase_identities(
                game,
                c,
                state,
                source.actor,
                source.identities,
                source.event,
                source.id,
                clause="blank_all",
            )
            _copy(state, changed)
            source = source.model_copy(update=dict(erased_event=source.event, work=tuple(work)))
            rules.put(state, source)
            _blank_finish(game, c, state, action, source, source.event)
    else:
        _request(
            game,
            c,
            action,
            source.handler_controller if total < 8 else int(source.actor.entity),
            "changeling_clay_handler" if total < 8 else "changeling_clay_owner",
        )


def projection(
    game: GameService, c: Connection, state: GameState, action: dict[str, Any], row: dict[str, Any]
) -> dict[str, Any]:
    source = prove_source(game, c, state, action["id"])
    kind = row["kind"]
    if kind == "changeling_low_erase":
        return dict(
            identities=support.identity_options(
                game, c, state, source.actor, chooser=source.actor, clause="blank_low"
            ),
        )
    if kind == "changeling_recent":
        return dict(
            recent=True, actor=source.actor.model_dump(mode="json"), through_event=source.event
        )
    if kind == "changeling_taste":
        return dict(taste=True)
    handler = kind == "changeling_clay_handler"
    count = (None if source.total < 8 else 1) if handler else 2 if source.total < 11 else 3
    return dict(
        facets=list(rules.FACET_LABELS.items()),
        count=count,
        minimum=0 if count is None else count,
        maximum=5 if count is None else count,
        copies=support.appearance_choices(game, c, state, source.actor)
        if not handler and source.total < 11
        else [],
    )


detail = projection


def apply(
    game: GameService,
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    row: dict[str, Any],
    answer: ChoiceAnswer,
) -> None:
    source = prove_source(game, c, state, action["id"])
    event, kind = action["data"]["response_event"], row["kind"]
    if (
        source.completed_event
        or answer.flag is not None
        and kind != "changeling_taste"
        or answer.member is not None
    ):
        raise WorkflowError("Use only the actual original pending Changeling consequence")
    if kind == "changeling_low_erase":
        ids = answer.denied
        options = dict(
            support.identity_options(
                game, c, state, source.actor, chooser=source.actor, clause="blank_low"
            )
        )
        if (
            int(row["actor_id"]) != int(source.actor.entity)
            or source.erased_event
            or answer.options
            or answer.number is not None
            or len(ids) != 1
            or not set(ids) <= set(options)
            or answer.fields
        ):
            raise WorkflowError("Choose the actual one erased Identity")
        changed, work = support.erase_identities(
            game, c, state, source.actor, tuple(ids), event, source.id, clause="blank_low"
        )
        _copy(state, changed)
        source = source.model_copy(
            update=dict(erased_event=event, work=tuple(dict.fromkeys((*source.work, *work))))
        )
        rules.put(state, source)
        _blank_finish(game, c, state, action, source, event)
    elif kind == "changeling_recent":
        if (
            source.total >= 8
            or source.recent_event
            or int(row["actor_id"]) != source.handler_controller
            or set(answer.fields) != {"start_event"}
            or answer.options
            or answer.denied
            or answer.number is not None
        ):
            raise WorkflowError(
                "The original Handler defines the actual recent fictional-time window"
            )
        changed, work = support.recent_loss(
            game, c, state, source, answer.fields["start_event"], _text(answer.text), event
        )
        _copy(state, changed)
        rules.put(
            state,
            source.model_copy(
                update=dict(recent_event=event, work=tuple(dict.fromkeys((*source.work, *work))))
            ),
        )
        action["data"]["changeling"]["phase"] = "effects"
    elif kind in ("changeling_clay_owner", "changeling_clay_handler"):
        owner = kind == "changeling_clay_owner"
        chooser = source.actor if owner else source.handler
        if (
            int(row["actor_id"])
            != (int(source.actor.entity) if owner else source.handler_controller)
            or answer.denied
            or answer.number is not None
        ):
            raise WorkflowError("The actual printed owner authors this body change")
        copy_from = answer.fields.get("copy")
        values: dict[str, str] = {}
        copied = None
        copied_source = None
        if copy_from:
            if (
                not owner
                or not 8 <= source.total <= 10
                or answer.options
                or set(answer.fields) != {"copy"}
            ):
                raise WorkflowError(
                    "Only the actual mid result can choose a genuine appearance copy"
                )
            option = next(
                (
                    item
                    for item in support.appearance_choices(game, c, state, source.actor)
                    if item["id"] == copy_from
                ),
                None,
            )
            if option is None:
                raise WorkflowError("Select the actual known person's current appearance snapshot")
            copied = ActorRef.model_validate(option["actor"])
            copied_source = option["source"]
            values = dict(option["values"])
        else:
            count = (2 if source.total < 11 else 3) if owner else 1 if source.total >= 11 else None
            if (
                not set(answer.options) <= set(rules.FACETS)
                or len(set(answer.options)) != len(answer.options)
                or (count is not None and len(answer.options) != count)
                or set(answer.fields) != set(answer.options)
            ):
                raise WorkflowError(
                    "Choose the printed number of actual physical facets and detail each"
                )
            values = {key: _text(value, 1000) for key, value in answer.fields.items()}
        if owner and source.owner_change_event or not owner and source.handler_change_event:
            raise WorkflowError(
                "Preserve the original authored change rather than applying it twice"
            )
        change_fact = rules.FacetChange(
            id=event,
            session=source.id,
            actor=source.actor,
            brain=source.brain,
            frame=source.frame,
            author=chooser,
            controller=int(row["actor_id"]),
            values=values,
            event=event,
            copied_from=copied,
            copied_source=copied_source,
        )
        rules.put(state, change_fact)
        changed, work = support.change_body(game, c, state, change_fact, event)
        _copy(state, changed)
        source = source.model_copy(
            update=dict(
                owner_change_event=event if owner else source.owner_change_event,
                handler_change_event=event if not owner else source.handler_change_event,
                work=tuple(dict.fromkeys((*source.work, *work))),
            )
        )
        rules.put(state, source)
        if owner and source.total >= 11:
            _request(game, c, action, source.handler_controller, "changeling_clay_handler")
        else:
            _request(game, c, action, source.handler_controller, "changeling_taste")
    elif kind == "changeling_taste":
        if (
            int(row["actor_id"]) != source.handler_controller
            or source.taste_event
            or answer.flag is None
            or answer.options
            or answer.fields
            or answer.denied
            or answer.number is not None
        ):
            raise WorkflowError("The original Handler answers their actual tastes and owns any Tag")
        work = ()
        if answer.flag:
            changed, work = support.status(game, c, state, source.actor, 1, event, source.id)
            _copy(state, changed)
        else:
            _copy(
                state,
                give_tag(
                    state,
                    profiles(c, game.store.campaign_id),
                    source.actor,
                    source.handler,
                    _text(answer.text, 120),
                    event,
                    event,
                    tuple(action["data"]["changeling"]["table"]),
                ),
            )
        rules.put(
            state,
            source.model_copy(
                update=dict(taste_event=event, work=tuple(dict.fromkeys((*source.work, *work))))
            ),
        )
        action["data"]["changeling"]["phase"] = "effects"
    else:
        raise WorkflowError("Use the actual pending source consequence")


def intercept_finish(
    game: GameService, c: Connection, state: GameState, action: dict[str, Any]
) -> bool:
    source = next(
        (value for value in rules.records(state, rules.Session) if value.id == action["id"]), None
    )
    if source is None:
        return False
    if _owed(game, c, source.work):
        return True
    if source.play == "changeling_blank_slate":
        return (
            source.total >= 11
            and source.blank is None
            or source.total < 8
            and source.recent_event is None
        )
    return source.taste_event is None


def synchronize(game: GameService, c: Connection, action: dict[str, Any], event: str) -> None:
    from girlframe.services.m2_choices import ChoiceEngine

    support.synchronize(game, c, event)
    if action["state"] in ("complete", "aborted") or game.pending(c, action["id"]):
        return
    state = load_state(c, game.store.campaign_id)
    source = prove_source(game, c, state, action["id"])
    final = str(uuid4())
    human = c.scalar(
        sa.select(t.events.c.actor_id).where(
            t.events.c.campaign_id == game.store.campaign_id, t.events.c.id == event
        )
    )
    if human is None:
        raise WorkflowError("Preserve the canonical source human completing this result")
    before = state.model_dump_json()
    if source.play == "changeling_blank_slate" and source.total >= 11 and source.blank is None:
        _blank_finish(game, c, state, action, source, final)
    pending = bool(game.pending(c, action["id"])) or intercept_finish(game, c, state, action)
    source = rules.session(state, source.id)
    if not pending and source.completed_event is None:
        rules.put(state, source.model_copy(update=dict(completed_event=final)))
    if state.model_dump_json() != before:
        game.event(
            c,
            int(human),
            str(uuid4()),
            "m3.changeling_progressed" if pending else "m3.changeling_completed",
            state,
            event_id=final,
            action_id=source.id,
            source_event=event,
        )
        support.synchronize(game, c, final)
    if pending:
        game.save_action(c, action)
        return
    action["data"]["changeling"]["phase"] = "complete"
    ChoiceEngine(game).finish(c, state, action)
    game.save_action(c, action)


def _available(game: GameService, rule: str) -> bool:
    from girlframe.services.m3_access import digest

    access = Access(game.store)
    approval = game.store.policy.m3_approval
    if (
        approval is None
        or access.registry is None
        or "plays" not in approval.subsystems
        or approval.registry_sha256 != digest(access.registry)
        or game.store.policy.owner_m3_rulings is None
    ):
        return False
    try:
        access.registry.require_available(rule)
    except (ValueError, WorkflowError):
        return False
    return True


def _grant(
    state: GameState,
    actor: ActorRef,
    frame: str,
    subject: rules.BrainRef,
    origin: Literal["start", "deepen", "web", "assault"],
    source: str,
    event: str,
    count: int = 1,
) -> tuple[str, ...]:
    ids = []
    for index in range(count):
        identity = rules.identity("string", source, actor.token, subject.id, str(index))
        old = next(
            (value for value in rules.records(state, rules.String) if value.id == identity), None
        )
        if old is None:
            rules.put(
                state,
                rules.String(
                    id=identity,
                    actor=actor,
                    frame=frame,
                    subject=subject,
                    origin=origin,
                    source=source,
                    event=event,
                ),
            )
        elif (
            old.actor != actor
            or old.frame != frame
            or not rules.same_brain(old.subject, subject)
            or old.origin != origin
            or old.source != source
        ):
            raise WorkflowError("Preserve the original actual Psych String birth")
        ids.append(identity)
    return tuple(ids)


def stage_start(
    game: GameService,
    c: Connection,
    state: GameState,
    actor: ActorRef,
    event: str,
    subjects: tuple[ActorRef, ...],
    *,
    source: str | None = None,
) -> None:
    if not _available(game, rules.STRINGS):
        return
    try:
        original = rules.frame(state, actor)
    except ValueError:
        return
    for subject in subjects:
        if subject == actor:
            raise WorkflowError("Starting Strings require actual other original people")
        identity = rules.identity("starting", actor.token, original, subject.token)
        if any(
            value.actor == actor and value.frame == original and value.subject == subject
            for value in rules.records(state, rules.StartingBond)
        ):
            continue
        rules.put(
            state,
            rules.StartingBond(
                id=identity,
                actor=actor,
                frame=original,
                subject=subject,
                source=source or event,
                event=event,
            ),
        )


def stage_brain(
    game: GameService,
    c: Connection,
    before: GameState,
    after: GameState,
    subject: ActorRef,
    event: str,
) -> None:
    if not _available(game, rules.STRINGS):
        return
    waiting = [
        value
        for value in rules.records(after, rules.StartingBond)
        if value.subject == subject and value.node is None
    ]
    if not waiting:
        return
    brain = _brain(game, c, after, subject, "starting")
    for value in waiting:
        from girlframe.services.m3_body_facts import _original_brain

        try:
            _original_brain(game, c, after, _history(c, game, value.source), subject)
        except WorkflowError as error:
            if str(error).startswith("SOURCE_ORIGINAL_BRAIN_REQUIRED:"):
                continue
            raise
        support.validate_start_brain(game, c, before, after, value, brain, event)
        ids = _grant(after, value.actor, value.frame, brain, "start", value.id, event)
        rules.put(after, value.model_copy(update=dict(node=ids[0], attached_event=event)))


def stage_deepen(
    game: GameService,
    c: Connection,
    before: GameState,
    after: GameState,
    first: ActorRef,
    second: ActorRef,
    event: str,
    source: str,
) -> None:
    if not _available(game, rules.STRINGS):
        return
    from girlframe.engine.m3_actor_bonds import depth

    for actor, subject in ((first, second), (second, first)):
        try:
            original = rules.frame(before, actor)
        except ValueError:
            continue
        identity = rules.identity("deepen", source, actor.token, subject.token)
        if any(value.id == identity for value in rules.records(after, rules.Deepening)):
            continue
        brain = _brain(game, c, after, subject, "node")
        rules.put(
            after,
            rules.Deepening(
                id=identity,
                first=actor,
                second=subject,
                before=depth(before, actor, subject),
                after=depth(after, actor, subject),
                source=source,
                event=event,
            ),
        )
        _grant(after, actor, original, brain, "deepen", identity, event)


def stage_damage(
    game: GameService,
    c: Connection,
    before: GameState,
    after: GameState,
    actor: ActorRef,
    asset: str,
    event: str,
    source: str,
) -> None:
    if not _available(game, rules.RECONDITION):
        return
    for value in support.reconditioning_candidates(
        game, c, before, after, actor, asset, event, source
    ):
        if not isinstance(value, rules.Reconditioning):
            raise WorkflowError("Prove the actual damaged Asset and shared original cockpit")
        if not any(old.id == value.id for old in rules.records(after, rules.Reconditioning)):
            rules.put(after, value)


def stage_assault(
    game: GameService, c: Connection, state: GameState, action: dict[str, Any], event: str
) -> None:
    if not _available(game, rules.WEB) or action["data"].get("play") != "all_out_assault":
        return
    actor = ActorRef.model_validate(action["data"]["battle"]["actor"])
    try:
        original = rules.frame(state, actor)
    except ValueError:
        return
    if rules.held(state, actor, rules.WEB) is None:
        return
    require_rule(game, c, state, actor, rules.WEB)
    rolled, total = _roll_source(game, c, action)
    if total < 8:
        return
    target = ActorRef.model_validate(action["data"]["battle"]["target"])
    subject = _brain(game, c, state, target, "node")
    identity = rules.identity("assault-gift", action["id"])
    if not any(value.id == identity for value in rules.records(state, rules.AssaultGift)):
        rules.put(
            state,
            rules.AssaultGift(
                id=identity,
                actor=actor,
                frame=original,
                subject=subject,
                action=action["id"],
                roll_event=rolled,
                event=event,
            ),
        )


def require_answers(game: GameService, c: Connection, state: GameState, actor: ActorRef) -> None:
    for value in rules.unanswered(state, actor):
        prove_fingers(game, c, state, value.source)
        raise WorkflowError(
            "REQUIRED_FOLLOWUP: answer the actual source-owned mental question first"
        )


def validate_pending_fingers(
    game: GameService, c: Connection, state: GameState, use: rules.Fingers, event: str
) -> None:
    node = prove_node(game, c, state, use.node)
    if (
        use.event != event
        or node.actor != use.actor
        or node.frame != use.frame
        or use.frame != rules.frame(state, use.actor)
        or node.spent_by != use.id
        or node.spent_event != event
        or not rules.same_brain(node.subject, use.subject)
        or use.target != use.subject.actor
    ):
        raise WorkflowError("Stage the exact real consumed original String before its effect")
    _live(game, c, state, use.brain)
    _live(game, c, state, use.subject)
    require_rule(game, c, state, use.actor, rules.FINGERS)
    if use.kind == "sex":
        require_rule(game, c, state, use.actor, rules.MINDFUCK)
    if use.kind in ("fry", "damage"):
        require_rule(game, c, state, use.actor, rules.WHIP)
    if use.kind == "fry" and use.subject.kind != "human_npc":
        raise WorkflowError("Fry requires the actual proved human NPC brain")


def _finish_fingers(
    game: GameService, c: Connection, state: GameState, use: rules.Fingers, event: str
) -> None:
    if use.main_event is None or use.completed_event is not None:
        return
    if not rules.reciprocal(use.subject) and use.counter_closed_event is None:
        use = use.model_copy(
            update=dict(counter_closed_event=event, counter_unavailable_reason="not_eligible")
        )
    pending_questions = any(
        value.source == use.id and value.answer_event is None
        for value in rules.records(state, rules.Question)
    )
    from girlframe.services.m3_changeling_effects import effect_complete

    ready = (
        effect_complete(game, c, state, use)
        and use.counter_closed_event is not None
        and not pending_questions
        and not _owed(game, c, use.work)
    )
    if use.kind == "sex":
        ready = (
            ready and use.sex_event is not None and bool(support.sex_complete(game, c, state, use))
        )
    phase: rules.Phase = (
        "complete"
        if ready
        else "counter"
        if use.counter_closed_event is None
        else "answer"
        if pending_questions
        else "sex"
        if use.kind == "sex"
        else "effect"
    )
    rules.put(
        state, use.model_copy(update=dict(phase=phase, completed_event=event if ready else None))
    )


def _question(
    state: GameState,
    use: rules.Fingers,
    asker: ActorRef,
    answerer: rules.BrainRef,
    text: str,
    event: str,
    branch: str,
) -> str:
    identity = rules.identity("question", use.id, branch)
    rules.put(
        state,
        rules.Question(
            id=identity,
            source=use.id,
            asker=asker,
            answerer=answerer,
            asker_controller=use.controllers[asker.token],
            question=_text(text),
            event=event,
        ),
    )
    return identity


class ChangelingService:
    def __init__(self, game: GameService):
        self.game, self.store = game, game.store

    def _write(
        self,
        viewer: GuildViewer,
        key: str,
        kind: str,
        revision: int,
        request: dict[str, Any],
        operation: Callable[[Connection, GameState, str], dict[str, Any]],
    ) -> dict[str, Any]:
        def run(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            if state.revision != revision:
                raise WorkflowError("Reopen the actual current source before changing it")
            event = str(uuid4())
            result = operation(c, state, event)
            reserved = {"c", "actor", "key", "kind", "state", "event_id", "event_index"}
            payload: dict[str, Any] = {}
            for name, value in result.items():
                target = "source_" + name if name in reserved else name
                if target in payload:
                    raise WorkflowError("Preserve distinct actual source metadata fields")
                payload[target] = value
            self.game.event(c, viewer.user_id, key, kind, state, event_id=event, **payload)
            support.synchronize(self.game, c, event)
            return dict(**result, revision=load_state(c, self.store.campaign_id).revision)

        try:
            return self.store._write(
                viewer,
                key,
                kind,
                dict(revision=revision, **request),
                run,
                auto_audit=False,
                authorize=lambda c: Access(self.store).authorize(
                    c, viewer, "plays", director_response=True
                ),
            )
        except ValueError as error:
            raise WorkflowError(str(error)) from None

    def speak(
        self,
        viewer: GuildViewer,
        key: str,
        revision: int,
        channel: int,
        speaker: ActorRef,
        addressed: ActorRef,
        kind: Literal["definition", "conversation", "push"],
        text: str,
        *,
        session: str | None = None,
    ) -> dict[str, Any]:
        actual = _text(text)

        def operation(c: Connection, state: GameState, event: str) -> dict[str, Any]:
            scene = _cast(self.game, c, state, channel)
            _owned(self.game, c, state, viewer, speaker)
            if kind not in ("definition", "conversation", "push") or not all(
                any(role.actor == ref for role in scene.roles) for ref in (speaker, addressed)
            ):
                raise WorkflowError("Use the actual original speaking and addressed source roles")
            first, second = (
                _brain(self.game, c, state, speaker, "speech"),
                _brain(self.game, c, state, addressed, "speech"),
            )
            if speaker == addressed or first.vessel == second.vessel:
                raise WorkflowError("Use actual other people, not two aliases for one body")
            if kind == "definition":
                require_rule(self.game, c, state, addressed, rules.BLANK)
                if session is not None:
                    raise WorkflowError("Use the new actual defining statement")
            elif kind == "push":
                source = prove_source(self.game, c, state, session or "")
                if (
                    source.target != speaker
                    or source.actor != addressed
                    or not 8 <= source.total <= 10
                    or not source.completed_event
                    or not support.can_lower_status(self.game, c, state, speaker)
                ):
                    raise WorkflowError(
                        "Only the actual ranked original speaker can overstep this real mid result"
                    )
            elif session is not None:
                raise WorkflowError("Actual conversation does not invent a different source event")
            identity = str(uuid4())
            rules.put(
                state,
                rules.Speech(
                    id=identity,
                    actor=speaker,
                    addressed=addressed,
                    brain=first,
                    addressed_brain=second,
                    kind=kind,
                    controller=viewer.user_id,
                    cast=scene,
                    text=actual,
                    event=event,
                    session=session,
                ),
            )
            return dict(id=identity)

        return self._write(
            viewer,
            key,
            "m3.changeling_spoken",
            revision,
            dict(
                channel=channel,
                speaker=speaker.model_dump(mode="json"),
                addressed=addressed.model_dump(mode="json"),
                kind=kind,
                text=actual,
                session=session,
            ),
            operation,
        )

    def fingers(
        self,
        viewer: GuildViewer,
        key: str,
        revision: int,
        channel: int,
        node: str,
        kind: rules.FingerKind,
        account: str,
        *,
        question: str | None = None,
        incoming: str | None = None,
        subject_scene: str | None = None,
    ) -> dict[str, Any]:
        actual = _text(account)

        def operation(c: Connection, state: GameState, event: str) -> dict[str, Any]:
            actor = current_ref(state, viewer.user_id)
            require_rule(self.game, c, state, actor, rules.FINGERS)
            original = prove_node(self.game, c, state, node)
            if (
                original.actor != actor
                or original.spent_event
                or kind
                not in (
                    "pause",
                    "sight",
                    "interrupt",
                    "question",
                    "flirt_plus",
                    "flirt_minus",
                    "sex",
                    "fry",
                    "damage",
                )
                or (kind == "question") != bool(question)
                or (kind == "interrupt") != bool(incoming)
                or subject_scene is not None
                and kind != "sight"
            ):
                raise WorkflowError("Choose one genuine effect of your actual unspent Psych String")
            scene = _cast(self.game, c, state, channel)
            if not any(
                role.actor == actor and role.controller == viewer.user_id for role in scene.roles
            ):
                raise WorkflowError(
                    "The actual original Changeling must declare this source herself"
                )
            brain = _brain(self.game, c, state, actor)
            subject = _live(self.game, c, state, original.subject)
            handler = active_handler(state)
            if handler is None or state.handler is None:
                raise WorkflowError("Recover the actual original source Handler")
            if kind == "damage" and not any(
                not item.damaged
                for item in resolve(
                    state,
                    subject.actor,
                    profiles(c, self.store.campaign_id),
                    require_current_profile=False,
                ).assets
            ):
                raise WorkflowError("This actual subject has no real undamaged Asset to choose")
            if kind == "sex":
                from girlframe.services.m3_changeling_sex import preflight_initiation

                preflight_initiation(self.game, c, state, actor, subject.actor)
            identity = str(uuid4())
            use = rules.Fingers(
                id=identity,
                actor=actor,
                brain=brain,
                frame=rules.frame(state, actor),
                target=subject.actor,
                subject=subject,
                node=node,
                kind=kind,
                cast=scene,
                handler=handler,
                handler_controller=state.handler,
                controllers={actor.token: viewer.user_id, subject.actor.token: subject.controller},
                event=event,
                account=actual,
                incoming=incoming,
                subject_scene=subject_scene,
            )
            rules.consume(state, node, identity, event)
            rules.put(state, use)
            validate_pending_fingers(self.game, c, state, use, event)
            work: tuple[str, ...] = ()
            if kind == "question":
                q = _question(state, use, actor, subject, question or "", event, "primary")
                use = use.model_copy(update=dict(question=q, main_event=event))
            elif kind in ("flirt_plus", "flirt_minus"):
                rules.put(
                    state,
                    rules.FlirtGrant(
                        id=rules.identity("flirt", identity),
                        use=identity,
                        actor=actor,
                        sign=1 if kind == "flirt_plus" else -1,
                        event=event,
                    ),
                )
                use = use.model_copy(update=dict(main_event=event))
            elif kind in ("damage", "fry"):
                use = use.model_copy(update=dict(phase="damage" if kind == "damage" else "fry"))
            else:
                changed, work = support.fingers_effect(self.game, c, state, use, event)
                _copy(state, changed)
                current = rules.get(state, identity)
                use = current.model_copy(
                    update=dict(main_event=event, work=tuple(dict.fromkeys((*current.work, *work))))
                )
            rules.put(state, use)
            _finish_fingers(self.game, c, state, use, event)
            return dict(id=identity)

        return self._write(
            viewer,
            key,
            "m3.changeling_fingers_used",
            revision,
            dict(
                channel=channel,
                node=node,
                kind=kind,
                account=actual,
                question=question,
                incoming=incoming,
                subject_scene=subject_scene,
            ),
            operation,
        )

    def answer(
        self, viewer: GuildViewer, key: str, revision: int, identity: str, text: str
    ) -> dict[str, Any]:
        actual = _text(text, 8000)

        def operation(c: Connection, state: GameState, event: str) -> dict[str, Any]:
            value = rules.record(state, rules.Question, identity)
            use = prove_fingers(self.game, c, state, value.source)
            _owned_brain_choice(self.game, c, state, viewer, value.answerer, use.cast)
            if value.answer_event:
                raise WorkflowError(
                    "Preserve the actual original answer rather than overwriting it"
                )
            rules.put(state, value.model_copy(update=dict(answer=actual, answer_event=event)))
            _finish_fingers(self.game, c, state, use, event)
            return dict(id=identity)

        return self._write(
            viewer,
            key,
            "m3.changeling_answered",
            revision,
            dict(id=identity, text=actual),
            operation,
        )

    def counter(
        self,
        viewer: GuildViewer,
        key: str,
        revision: int,
        identity: str,
        kind: Literal["question", "erase", "tag", "pass"],
        *,
        text: str = "",
        identity_id: str | None = None,
    ) -> dict[str, Any]:
        def operation(c: Connection, state: GameState, event: str) -> dict[str, Any]:
            use = prove_fingers(self.game, c, state, identity)
            _owned_brain_choice(self.game, c, state, viewer, use.subject, use.cast)
            if (
                not rules.reciprocal(use.subject)
                or use.main_event is None
                or use.counter_closed_event
                or kind not in ("question", "erase", "tag", "pass")
                or (kind == "erase") != bool(identity_id)
            ):
                raise WorkflowError(
                    "Choose at most one printed response for your actual affected person"
                )
            work: tuple[str, ...] = ()
            update: dict[str, Any] = dict(
                counter=kind, counter_event=event, counter_closed_event=event
            )
            if kind == "question":
                update["counter_question"] = _question(
                    state, use, use.target, use.brain, text, event, "reciprocal"
                )
            elif kind == "tag":
                _copy(
                    state,
                    give_tag(
                        state,
                        profiles(c, self.store.campaign_id),
                        use.actor,
                        use.target,
                        _text(text, 120),
                        event,
                        event,
                        tuple(use.controllers.values()),
                    ),
                )
                update["counter_tag"] = event
            elif kind == "erase":
                assert identity_id is not None
                changed, work = support.erase_identities(
                    self.game,
                    c,
                    state,
                    use.actor,
                    (identity_id,),
                    event,
                    use.id,
                    clause="fingers_counter",
                )
                _copy(state, changed)
                update["counter_erase"] = identity_id
            elif text:
                raise WorkflowError("Passing does not fabricate an answer, erasure or Tag")
            use = use.model_copy(
                update=dict(**update, work=tuple(dict.fromkeys((*use.work, *work))))
            )
            rules.put(state, use)
            _finish_fingers(self.game, c, state, use, event)
            return dict(id=identity)

        return self._write(
            viewer,
            key,
            "m3.changeling_countered",
            revision,
            dict(id=identity, kind=kind, text=text, identity=identity_id),
            operation,
        )

    def damage(
        self, viewer: GuildViewer, key: str, revision: int, identity: str, asset: str
    ) -> dict[str, Any]:
        def operation(c: Connection, state: GameState, event: str) -> dict[str, Any]:
            use = prove_fingers(self.game, c, state, identity)
            _owned_brain_choice(self.game, c, state, viewer, use.subject, use.cast)
            if use.kind != "damage" or use.main_event:
                raise WorkflowError("The actual affected person chooses their own real Asset once")
            changed, work = support.force_damage(self.game, c, state, use, asset, event)
            _copy(state, changed)
            use = use.model_copy(update=dict(main_event=event, work=tuple(work)))
            rules.put(state, use)
            _finish_fingers(self.game, c, state, use, event)
            return dict(id=identity)

        return self._write(
            viewer,
            key,
            "m3.changeling_asset_damaged",
            revision,
            dict(id=identity, asset=asset),
            operation,
        )

    def fry(
        self,
        viewer: GuildViewer,
        key: str,
        revision: int,
        identity: str,
        outcome: Literal["helpless", "dead"],
    ) -> dict[str, Any]:
        def operation(c: Connection, state: GameState, event: str) -> dict[str, Any]:
            use = prove_fingers(self.game, c, state, identity)
            if (
                use.kind != "fry"
                or use.main_event
                or use.subject.kind != "human_npc"
                or viewer.user_id != use.handler_controller
                or state.handler != use.handler_controller
                or active_handler(state) != use.handler
                or outcome not in ("helpless", "dead")
            ):
                raise WorkflowError(
                    "The actual original Handler chooses the real human NPC brain outcome"
                )
            changed, work = support.fry(self.game, c, state, use, outcome, event)
            _copy(state, changed)
            use = use.model_copy(update=dict(main_event=event, work=tuple(work)))
            rules.put(state, use)
            _finish_fingers(self.game, c, state, use, event)
            return dict(id=identity)

        return self._write(
            viewer,
            key,
            "m3.changeling_brain_fried",
            revision,
            dict(id=identity, outcome=outcome),
            operation,
        )

    def access(
        self,
        viewer: GuildViewer,
        key: str,
        revision: int,
        channel: int,
        actor: ActorRef,
        target: ActorRef,
        condition: Literal["unconscious", "helpless", "unexpecting"],
        account: str,
    ) -> dict[str, Any]:
        actual = _text(account)

        def operation(c: Connection, state: GameState, event: str) -> dict[str, Any]:
            require_rule(self.game, c, state, actor, rules.WEB)
            handler = active_handler(state)
            if (
                handler is None
                or state.handler != viewer.user_id
                or condition not in ("unconscious", "helpless", "unexpecting")
            ):
                raise WorkflowError(
                    "The actual original Handler records genuine access and body facts"
                )
            scene = _cast(self.game, c, state, channel)
            subject = _brain(self.game, c, state, target, "implant")
            facts = support.validate_access(
                self.game, c, state, actor, target, scene, condition, actual, event
            )
            identity = str(uuid4())
            rules.put(
                state,
                rules.Access(
                    id=identity,
                    actor=actor,
                    frame=rules.frame(state, actor),
                    subject=subject,
                    handler=handler,
                    handler_controller=viewer.user_id,
                    cast=scene,
                    condition=condition,
                    facts=json.dumps(facts, sort_keys=True),
                    account=actual,
                    event=event,
                ),
            )
            return dict(id=identity)

        return self._write(
            viewer,
            key,
            "m3.changeling_access_proved",
            revision,
            dict(
                channel=channel,
                actor=actor.model_dump(mode="json"),
                target=target.model_dump(mode="json"),
                condition=condition,
                account=actual,
            ),
            operation,
        )

    def implant(
        self, viewer: GuildViewer, key: str, revision: int, identity: str, account: str
    ) -> dict[str, Any]:
        actual = _text(account)

        def operation(c: Connection, state: GameState, event: str) -> dict[str, Any]:
            value = rules.record(state, rules.Access, identity)
            original = rules.record(
                _audit(
                    self.game,
                    c,
                    value.event,
                    "m3.changeling_access_proved",
                    value.handler_controller,
                ),
                rules.Access,
                identity,
            )
            if (
                original.model_copy(update=dict(used_event=value.used_event)) != value
                or value.used_event
            ):
                raise WorkflowError("Use this actual original still-unused access procedure")
            _owned(self.game, c, state, viewer, value.actor)
            require_rule(self.game, c, state, value.actor, rules.WEB)
            subject = _live(self.game, c, state, value.subject)
            support.recheck_access(self.game, c, state, value)
            _grant(state, value.actor, value.frame, subject, "web", value.id, event, 3)
            rules.put(state, value.model_copy(update=dict(used_event=event)))
            state.facts.append(
                dict(kind="changeling_implant_account", id=identity, event=event, body=actual)
            )
            return dict(id=identity)

        return self._write(
            viewer,
            key,
            "m3.changeling_implanted",
            revision,
            dict(id=identity, account=actual),
            operation,
        )

    def assault_gift(
        self, viewer: GuildViewer, key: str, revision: int, identity: str, give: bool
    ) -> dict[str, Any]:
        def operation(c: Connection, state: GameState, event: str) -> dict[str, Any]:
            value = rules.record(state, rules.AssaultGift, identity)
            _owned(self.game, c, state, viewer, value.actor)
            original = rules.record(
                _history(c, self.game, value.event), rules.AssaultGift, identity
            )
            if (
                original.model_copy(
                    update=dict(chosen=value.chosen, completed_event=value.completed_event)
                )
                != value
                or value.completed_event
                or type(give) is not bool
            ):
                raise WorkflowError("Use the actual original one-time Assault offer")
            action = self.game.action(c, value.action)
            rolled, total = _roll_source(self.game, c, action)
            if (
                rolled != value.roll_event
                or total < 8
                or ActorRef.model_validate(action["data"]["battle"]["actor"]) != value.actor
            ):
                raise WorkflowError("Prove this genuine 8+ Assault's actual caster and target")
            if give:
                subject = _live(self.game, c, state, value.subject)
                _grant(state, value.actor, value.frame, subject, "assault", value.id, event)
            rules.put(state, value.model_copy(update=dict(chosen=give, completed_event=event)))
            return dict(id=identity)

        return self._write(
            viewer,
            key,
            "m3.changeling_assault_gift",
            revision,
            dict(id=identity, give=give),
            operation,
        )

    def recondition(
        self, viewer: GuildViewer, key: str, revision: int, identity: str, label: str | None
    ) -> dict[str, Any]:
        def operation(c: Connection, state: GameState, event: str) -> dict[str, Any]:
            value = rules.record(state, rules.Reconditioning, identity)
            original = rules.record(
                _history(c, self.game, value.event), rules.Reconditioning, identity
            )
            _owned(self.game, c, state, viewer, value.actor, value.controller)
            if (
                original.model_copy(
                    update=dict(label=value.label, completed_event=value.completed_event)
                )
                != value
                or value.completed_event
                or label is not None
                and label not in rules.TAGS
            ):
                raise WorkflowError(
                    "Choose only a real absent printed reconditioning Tag or decline"
                )
            if label is not None:
                _live(self.game, c, state, value.subject)
                if label in {item.label for item in actor_tags(state, value.subject.actor)}:
                    raise WorkflowError("The actual affected person already has this Tag")
                _copy(
                    state,
                    give_tag(
                        state,
                        profiles(c, self.store.campaign_id),
                        value.subject.actor,
                        value.actor,
                        label,
                        event,
                        event,
                        (value.controller, value.subject.controller),
                    ),
                )
            rules.put(state, value.model_copy(update=dict(label=label, completed_event=event)))
            return dict(id=identity)

        return self._write(
            viewer,
            key,
            "m3.changeling_reconditioned",
            revision,
            dict(id=identity, label=label),
            operation,
        )

    def push(
        self, viewer: GuildViewer, key: str, revision: int, identity: str, label: str
    ) -> dict[str, Any]:
        actual = _text(label, 120)

        def operation(c: Connection, state: GameState, event: str) -> dict[str, Any]:
            speech = prove_speech(self.game, c, state, identity)
            source = prove_source(self.game, c, state, speech.session or "")
            _owned(self.game, c, state, viewer, speech.actor, speech.controller)
            if (
                speech.kind != "push"
                or speech.used_by
                or source.target != speech.actor
                or source.actor != speech.addressed
                or not 8 <= source.total <= 10
                or not support.can_lower_status(self.game, c, state, speech.actor)
            ):
                raise WorkflowError(
                    "Pay the actual original speaker's real overstepping Status cost"
                )
            _live(self.game, c, state, speech.brain)
            _live(self.game, c, state, speech.addressed_brain)
            changed, work = support.status(self.game, c, state, speech.actor, -1, event, source.id)
            _copy(state, changed)
            _copy(
                state,
                give_tag(
                    state,
                    profiles(c, self.store.campaign_id),
                    source.actor,
                    speech.actor,
                    actual,
                    event,
                    event,
                    tuple(role.controller for role in source.cast.roles),
                ),
            )
            push_id = str(uuid4())
            rules.put(
                state,
                rules.Push(
                    id=push_id,
                    session=source.id,
                    actor=speech.actor,
                    target=source.actor,
                    speech=speech.id,
                    label=actual,
                    event=event,
                    work=tuple(work),
                ),
            )
            rules.put(state, speech.model_copy(update=dict(used_by=push_id)))
            return dict(id=push_id)

        return self._write(
            viewer,
            key,
            "m3.changeling_pushed",
            revision,
            dict(speech=identity, label=actual),
            operation,
        )

    def copy_blank(
        self,
        viewer: GuildViewer,
        key: str,
        revision: int,
        identity: str,
        other: ActorRef,
        possessed: str,
        speeches: tuple[str, str],
    ) -> dict[str, Any]:
        def operation(c: Connection, state: GameState, event: str) -> dict[str, Any]:
            value = rules.record(state, rules.BlankSlate, identity)
            prove_source(self.game, c, state, value.session)
            original = rules.record(_history(c, self.game, value.event), rules.BlankSlate, identity)
            if (
                original.model_dump(
                    exclude={
                        "conversation",
                        "copied_from",
                        "copied_identity",
                        "replacement",
                        "replaced_event",
                        "work",
                    }
                )
                != value.model_dump(
                    exclude={
                        "conversation",
                        "copied_from",
                        "copied_identity",
                        "replacement",
                        "replaced_event",
                        "work",
                    }
                )
                or value.replaced_event
            ):
                raise WorkflowError("Use the actual original still-held Blank Slate entitlement")
            _owned(self.game, c, state, viewer, value.actor)
            first, second = (prove_speech(self.game, c, state, key) for key in speeches)
            if (
                fingerprint(_cast(self.game, c, state, first.cast.channel))
                != fingerprint(first.cast)
                or not all(speech.kind == "conversation" for speech in (first, second))
                or {(speech.actor, speech.addressed) for speech in (first, second)}
                != {(value.actor, other), (other, value.actor)}
                or fingerprint(first.cast) != fingerprint(second.cast)
            ):
                raise WorkflowError(
                    "Talk with the actual other person; do not invent their conversation"
                )
            _live(self.game, c, state, first.brain)
            _live(self.game, c, state, first.addressed_brain)
            _live(self.game, c, state, second.brain)
            _live(self.game, c, state, second.addressed_brain)
            disclosure = rules.record(state, rules.IdentityDisclosure, possessed)
            if disclosure.speech not in speeches or fingerprint(disclosure.cast) != fingerprint(
                first.cast
            ):
                raise WorkflowError(
                    "Use the actual currently disclosed Identity in this original conversation"
                )
            if possessed not in {
                row["id"] for row in support.copy_choices(self.game, c, state, value.actor, other)
            }:
                raise WorkflowError(
                    "Select actual possessed known Identity content, not its protected mechanics"
                )
            changed, replacement, work = support.replace_blank(
                self.game, c, state, value, other, possessed, event
            )
            _copy(state, changed)
            rules.put(
                state,
                value.model_copy(
                    update=dict(
                        conversation=speeches,
                        copied_from=other,
                        copied_identity=possessed,
                        replacement=replacement,
                        replaced_event=event,
                        work=tuple(work),
                    )
                ),
            )
            return dict(id=identity)

        return self._write(
            viewer,
            key,
            "m3.changeling_blank_copied",
            revision,
            dict(
                id=identity,
                other=other.model_dump(mode="json"),
                possessed=possessed,
                speeches=speeches,
            ),
            operation,
        )

    def purchase(
        self, viewer: GuildViewer, key: str, revision: int, rule: str, account: str
    ) -> dict[str, Any]:
        actual = _text(account)

        def operation(c: Connection, state: GameState, event: str) -> dict[str, Any]:
            Access(self.store).authorize(c, viewer, "economy")
            RequisitionService(self.game)._safe(c, state, viewer.user_id)
            actor = current_ref(state, viewer.user_id)
            original = rules.frame(state, actor)
            registry = Access(self.store).registry
            if registry is None or rule not in rules.REQUISITIONS:
                raise WorkflowError("Choose a real printed Changeling Requisition")
            registry.require_available(rule)
            if rules.held(state, actor, rule) is not None or available(state, actor) < 2:
                raise WorkflowError("Use an unowned actual two-Permission acquisition")
            identity = str(uuid4())
            payment = prepare_payment(self.game, c, state, viewer, actor, rule, 2, rules.FRAME)
            debit(state, actor, 2, event=event, source=identity, payment=payment)
            state.sheets[actor.entity].revision += 1
            state.requisitions.append(
                FrameRuleReceipt(
                    id=identity,
                    kind="ability_unlock",
                    actor=actor,
                    frame_instance=original,
                    frame=rules.FRAME,
                    donor_frame=rules.FRAME,
                    rule_id=rule,
                    grant="changeling:" + identity,
                    price=2,
                    account=actual,
                    source_event=event,
                )
            )
            return dict(id=identity, requisition_id=identity, rule_id=rule, cost=2)

        return self._write(
            viewer,
            key,
            "m3.ability_unlock_purchased",
            revision,
            dict(rule=rule, account=actual),
            operation,
        )

    def body_fact(
        self,
        viewer: GuildViewer,
        key: str,
        revision: int,
        channel: int,
        actor: ActorRef,
        kind: Literal["girl", "gorgon", "harpy", "handler", "human_npc", "other"],
        account: str,
    ) -> dict[str, Any]:
        actual_account = _text(account)

        def operation(c: Connection, state: GameState, event: str) -> dict[str, Any]:
            from girlframe.services.m3_recovery import pending

            if self.game.pending_actions(c) or pending(self.game, c, include_unrolled=True):
                raise WorkflowError("Finish the actual held Play before establishing body facts")
            scene = _cast(self.game, c, state, channel)
            actual = resolve(
                state, actor, profiles(c, self.store.campaign_id), require_current_profile=False
            )
            handler = active_handler(state)
            author = next(
                (
                    role.actor
                    for role in scene.roles
                    if role.controller == viewer.user_id and role.actor == actor
                ),
                None,
            )
            if viewer.user_id == state.handler and handler is not None:
                author = handler
            if author is None or not any(role.actor == actor for role in scene.roles):
                raise WorkflowError(
                    "The actual owner or original Handler records witnessed body facts"
                )
            if kind not in ("girl", "gorgon", "harpy", "handler", "human_npc", "other"):
                raise WorkflowError("Use a real source body category")
            expected_kind = (
                "girl"
                if actor.kind == "pilot"
                else "gorgon"
                if actor.kind == "gorgon"
                else "handler"
                if actor.kind == "handler"
                else "harpy"
                if actor.kind == "external_pilot" and actual.girl == "harpy"
                else "girl"
                if actor.kind == "external_pilot" and actual.girl
                else None
            )
            if expected_kind is not None and kind != expected_kind:
                raise WorkflowError(
                    "Factual brain biology does not change the actual printed actor role"
                )
            reset = None
            if actor.kind == "npc":
                npc = (
                    next((item for item in state.world.npcs if item.id == actor.entity), None)
                    if state.world
                    else None
                )
                from girlframe.engine.m3_am_reset import body as reset_body
                from girlframe.engine.m3_am_reset import prove as prove_reset

                reset = reset_body(state, actor)
                if (
                    npc is None
                    or npc.source_kind == "wyvern_wraith"
                    or reset is not None
                    and kind != "other"
                    or viewer.user_id != state.handler
                    or kind not in ("human_npc", "other")
                ):
                    raise WorkflowError(
                        "The actual Handler establishes ordinary NPC biology; "
                        "no Wraith or AM human proxy"
                    )
                if reset is not None:
                    prove_reset(state, reset)
                    born_reset = reset_body(_history(c, self.game, reset.source_event), actor)
                    if born_reset != reset or actual.vessel_id != reset.body.vessel_id:
                        raise WorkflowError(
                            "Use canonical actual reset hardware and its original body"
                        )
            elif (
                kind == "human_npc"
                or (kind == "gorgon" and actor.kind != "gorgon")
                or (kind == "handler" and actor.kind != "handler")
                or (
                    kind == "girl"
                    and actual.rules not in ("girl_frame", "handler_girl", "external_pilot")
                )
            ):
                raise WorkflowError("Preserve the actual original body's role and rules")
            if any(
                item.actor == actor
                and (actual.vessel_id is None or item.vessel == actual.vessel_id)
                for item in rules.records(state, rules.BodyFact)
            ):
                raise WorkflowError(
                    "Do not reset an existing original brain or attach by controller alias"
                )
            vessel = actual.vessel_id
            if vessel is None:
                if actor.kind not in ("handler", "npc"):
                    raise WorkflowError(
                        "SOURCE_BODY_VESSEL_REQUIRED: establish the actual existing vessel"
                    )
                vessel = rules.identity("factual-body", actor.token)
            identity = rules.identity("body", actor.token, vessel)
            value = rules.BodyFact(
                id=identity,
                actor=actor,
                vessel=vessel,
                brain=rules.identity(
                    "brain", reset.original.token if reset else actor.token, vessel
                ),
                reset_source=reset.source_event if reset else None,
                reset_record=reset.id if reset else None,
                kind=kind,
                author=author,
                controller=viewer.user_id,
                cast=scene,
                account=actual_account,
                event=event,
            )
            rules.put(state, value)
            return dict(id=identity, actor=actor.model_dump(mode="json"))

        return self._write(
            viewer,
            key,
            "m3.changeling_body_proved",
            revision,
            dict(
                channel=channel,
                actor=actor.model_dump(mode="json"),
                kind=kind,
                account=actual_account,
            ),
            operation,
        )

    def disclose_identity(
        self,
        viewer: GuildViewer,
        key: str,
        revision: int,
        speech: str,
        identity: str,
    ) -> dict[str, Any]:
        def operation(c: Connection, state: GameState, event: str) -> dict[str, Any]:
            source = prove_speech(self.game, c, state, speech)
            _owned(self.game, c, state, viewer, source.actor, source.controller)
            _live(self.game, c, state, source.brain)
            if source.kind != "conversation":
                raise WorkflowError("Disclose an actual possessed Identity while truly talking")
            actual = resolve(
                state,
                source.actor,
                profiles(c, self.store.campaign_id),
                require_current_profile=False,
            )
            item = next((item for item in actual.identities if item.id == identity), None)
            if item is None:
                raise WorkflowError("Identify content actually possessed by your original person")
            value = rules.IdentityDisclosure(
                id=str(uuid4()),
                actor=source.actor,
                addressed=source.addressed,
                identity=item.id,
                label=item.name,
                controller=viewer.user_id,
                cast=source.cast,
                speech=source.id,
                event=event,
            )
            rules.put(state, value)
            return dict(id=value.id)

        return self._write(
            viewer,
            key,
            "m3.changeling_identity_disclosed",
            revision,
            dict(speech=speech, identity=identity),
            operation,
        )

    def appearance(
        self,
        viewer: GuildViewer,
        key: str,
        revision: int,
        channel: int,
        actor: ActorRef,
        values: dict[str, str],
    ) -> dict[str, Any]:
        if set(values) != set(rules.FACETS) or any(
            not text.strip() or len(text) > 1200 for text in values.values()
        ):
            raise WorkflowError("Describe the actual existing body's five appearance facets")

        def operation(c: Connection, state: GameState, event: str) -> dict[str, Any]:
            _owned(self.game, c, state, viewer, actor)
            scene = _cast(self.game, c, state, channel)
            if actor not in {role.actor for role in scene.roles}:
                raise WorkflowError("Use the actual original role in this real scene")
            subject = _brain(self.game, c, state, actor, "appearance")
            if any(
                item.actor == actor and item.vessel == subject.vessel
                for item in rules.records(state, rules.Appearance)
            ):
                raise WorkflowError(
                    "Describe existing appearance once; actual later changes "
                    "require their real source"
                )
            value = rules.Appearance(
                id=str(uuid4()),
                actor=actor,
                vessel=subject.vessel,
                values=values,
                author=actor,
                controller=viewer.user_id,
                cast=scene,
                event=event,
            )
            rules.put(state, value)
            return dict(id=value.id)

        return self._write(
            viewer,
            key,
            "m3.changeling_appearance_proved",
            revision,
            dict(channel=channel, actor=actor.model_dump(mode="json"), values=values),
            operation,
        )

    def disclose_appearance(
        self,
        viewer: GuildViewer,
        key: str,
        revision: int,
        channel: int,
        appearance: str,
        addressed: ActorRef,
    ) -> dict[str, Any]:
        def operation(c: Connection, state: GameState, event: str) -> dict[str, Any]:
            value = rules.record(state, rules.Appearance, appearance)
            _owned(self.game, c, state, viewer, value.actor, value.controller)
            subject = _brain(self.game, c, state, value.actor, "appearance")
            scene = _cast(self.game, c, state, channel)
            if subject.vessel != value.vessel or not {value.actor, addressed} <= {
                role.actor for role in scene.roles
            }:
                raise WorkflowError(
                    "Show the actual original appearance to a truly present other person"
                )
            disclosure = rules.AppearanceDisclosure(
                id=str(uuid4()),
                appearance=value.id,
                values=__import__(
                    "girlframe.services.m3_changeling_body", fromlist=["current_appearance"]
                ).current_appearance(state, value.actor, value.vessel),
                actor=value.actor,
                addressed=addressed,
                controller=viewer.user_id,
                cast=scene,
                event=event,
            )
            rules.put(state, disclosure)
            return dict(id=disclosure.id)

        return self._write(
            viewer,
            key,
            "m3.changeling_appearance_disclosed",
            revision,
            dict(
                channel=channel, appearance=appearance, addressed=addressed.model_dump(mode="json")
            ),
            operation,
        )

    def observe_eyes(
        self,
        viewer: GuildViewer,
        key: str,
        revision: int,
        identity: str,
        text: str,
    ) -> dict[str, Any]:
        actual_text = _text(text, 8000)

        def operation(c: Connection, state: GameState, event: str) -> dict[str, Any]:
            from girlframe.services.m3_changeling_effects import _born

            use = prove_fingers(self.game, c, state, identity)
            view = _born(self.game, c, state, rules.EyeView, identity, {"ended_event"})
            _owned_brain_choice(self.game, c, state, viewer, use.subject, use.cast)
            actual = resolve(
                state,
                use.target,
                profiles(c, self.store.campaign_id),
                require_current_profile=False,
            )
            scene = _cast(self.game, c, state, view.cast.channel)
            if (
                view.ended_event
                or scene.id != view.cast.id
                or not any(role.actor == use.target for role in scene.roles)
                or actual.cell is None
            ):
                raise WorkflowError(
                    "Describe only what these original eyes actually see in the source scene"
                )
            value = rules.EyeObservation(
                id=str(uuid4()),
                view=view.id,
                subject=use.subject,
                controller=viewer.user_id,
                scene=scene.id,
                cell=actual.cell,
                text=actual_text,
                event=event,
            )
            rules.put(state, value)
            _finish_fingers(self.game, c, state, use, event)
            return dict(id=value.id, use=use.id)

        return self._write(
            viewer,
            key,
            "m3.changeling_eye_observed",
            revision,
            dict(use=identity, text=actual_text),
            operation,
        )

    def consent(
        self,
        viewer: GuildViewer,
        key: str,
        revision: int,
        identity: str,
        accepted: bool,
    ) -> dict[str, Any]:
        def operation(c: Connection, state: GameState, event: str) -> dict[str, Any]:
            use = prove_fingers(self.game, c, state, identity)
            _owned_brain_choice(self.game, c, state, viewer, use.subject, use.cast)
            if (
                use.kind != "sex"
                or use.consent_event
                or use.sex_event
                or type(accepted) is not bool
            ):
                raise WorkflowError(
                    "Only the original counterpart confirms or declines this actual initiation"
                )
            if accepted:
                _live(self.game, c, state, use.brain)
            changed = (
                use.model_copy(update=dict(consent_event=event))
                if accepted
                else use.model_copy(update=dict(sex_event=event, sex_outcome="declined"))
            )
            rules.put(state, changed)
            _finish_fingers(self.game, c, state, changed, event)
            return dict(id=identity, accepted=accepted)

        return self._write(
            viewer,
            key,
            "m3.changeling_sex_consented",
            revision,
            dict(use=identity, accepted=accepted),
            operation,
        )

    def _tasks(self, c: Connection, viewer: GuildViewer) -> list[dict[str, Any]]:
        state = load_state(c, self.store.campaign_id)
        result: list[dict[str, Any]] = []
        for session in rules.records(state, rules.Session):
            if (
                viewer.user_id == int(session.actor.entity)
                or session.play == "changeling_body_of_clay"
                and viewer.user_id == session.handler_controller
            ):
                result.append(
                    dict(
                        id=session.id,
                        revision=state.revision,
                        label=session.play.removeprefix("changeling_").replace("_", " "),
                        pending=False,
                        phase="resolved" if session.completed_event else "pending",
                    )
                )
        for speech in rules.records(state, rules.Speech):
            if viewer.user_id in (speech.controller, speech.addressed_brain.controller):
                result.append(
                    dict(
                        id=speech.id,
                        revision=state.revision,
                        label="Actual " + speech.kind,
                        pending=speech.kind == "push"
                        and not speech.used_by
                        and viewer.user_id == speech.controller,
                        phase="resolved" if speech.used_by else "pending",
                    )
                )
        for question in rules.records(state, rules.Question):
            answerer = _choice_controller(self.game, c, state, question.answerer)
            if viewer.user_id not in (question.asker_controller, answerer):
                continue
            result.append(
                dict(
                    id=question.id,
                    revision=state.revision,
                    label="Psychic question",
                    pending=question.answer_event is None and viewer.user_id == answerer,
                    phase="pending" if question.answer_event is None else "resolved",
                )
            )
        for use in rules.records(state, rules.Fingers):
            subject_controller = _choice_controller(self.game, c, state, use.subject)
            if viewer.user_id not in (use.controllers[use.actor.token], subject_controller):
                if not (use.kind == "fry" and viewer.user_id == use.handler_controller):
                    continue
            actionable = (
                use.main_event is None
                and (
                    use.kind == "fry"
                    and viewer.user_id == use.handler_controller
                    or use.kind == "damage"
                    and viewer.user_id == subject_controller
                )
                or use.main_event is not None
                and not use.counter_closed_event
                and viewer.user_id == subject_controller
                and rules.reciprocal(use.subject)
            )
            result.append(
                dict(
                    id=use.id,
                    revision=state.revision,
                    label="Fingers: " + use.kind,
                    pending=bool(actionable),
                    phase="resolved" if use.completed_event else "pending",
                )
            )
        for reconditioning in rules.records(state, rules.Reconditioning):
            if viewer.user_id == reconditioning.controller:
                result.append(
                    dict(
                        id=reconditioning.id,
                        revision=state.revision,
                        label="Live Reconditioning",
                        pending=reconditioning.completed_event is None,
                        phase="resolved" if reconditioning.completed_event else "pending",
                    )
                )
        for gift in rules.records(state, rules.AssaultGift):
            if viewer.user_id == int(gift.actor.entity):
                result.append(
                    dict(
                        id=gift.id,
                        revision=state.revision,
                        label="Assault String",
                        pending=gift.completed_event is None,
                        phase="resolved" if gift.completed_event else "pending",
                    )
                )
        for blank in rules.records(state, rules.BlankSlate):
            if viewer.user_id == int(blank.actor.entity):
                result.append(
                    dict(
                        id=blank.id,
                        revision=state.revision,
                        label="Blank Slate copy",
                        pending=blank.replaced_event is None,
                        phase="resolved" if blank.replaced_event else "pending",
                    )
                )
        return result

    def menu(self, viewer: GuildViewer, channel: int | None = None) -> dict[str, Any]:
        def run(c: Connection) -> dict[str, Any]:
            Access(self.store).authorize(c, viewer, "plays", director_response=True)
            state = load_state(c, self.store.campaign_id)
            result: dict[str, Any] = dict(
                revision=state.revision,
                tasks=self._tasks(c, viewer),
                roles=[],
                targets=[],
                nodes=[],
                definitions=[],
                conversations=[],
                accesses=[],
                appearances=[],
                plays=[],
                requisitions=[],
            )
            try:
                scene = _cast(self.game, c, state, channel or 0)
            except (ValueError, WorkflowError):
                return result
            bound = profiles(c, self.store.campaign_id)
            for role in scene.roles:
                actual = resolve(state, role.actor, bound, require_current_profile=False)
                row = dict(
                    id=role.actor.token,
                    label=actual.label,
                    actor=role.actor.model_dump(mode="json"),
                )
                result["targets"].append(row)
                if role.controller != viewer.user_id:
                    continue
                result["roles"].append(row)
                for speech in rules.records(state, rules.Speech):
                    if (
                        speech.addressed == role.actor
                        and speech.kind == "definition"
                        and speech.used_by is None
                        and fingerprint(speech.cast) == fingerprint(scene)
                    ):
                        result["definitions"].append(
                            dict(
                                id=speech.id,
                                label=speech.text,
                                actor=role.actor.model_dump(mode="json"),
                            )
                        )
                    if speech.actor == role.actor and speech.kind == "conversation":
                        result["conversations"].append(
                            dict(
                                id=speech.id,
                                label=speech.text,
                                actor=role.actor.model_dump(mode="json"),
                                identities=[(x.id, x.name) for x in actual.identities],
                            )
                        )
                result["appearances"].extend(
                    dict(id=x.id, label=actual.label, actor=role.actor.model_dump(mode="json"))
                    for x in rules.records(state, rules.Appearance)
                    if x.actor == role.actor
                )
                try:
                    rules.frame(state, role.actor)
                except ValueError:
                    continue
                for node in rules.records(state, rules.String):
                    if node.actor == role.actor and node.spent_event is None:
                        prove_node(self.game, c, state, node.id)
                        result["nodes"].append(
                            dict(
                                id=node.id,
                                label=node.subject.actor.kind + ":" + node.subject.actor.entity,
                                actor=role.actor.model_dump(mode="json"),
                                target=node.subject.actor.model_dump(mode="json"),
                            )
                        )
                result["accesses"].extend(
                    dict(id=x.id, label=x.subject.actor.entity)
                    for x in rules.records(state, rules.Access)
                    if x.actor == role.actor and x.used_event is None
                )
                result["plays"].extend(
                    dict(id=play, label=play.removeprefix("changeling_").replace("_", " "))
                    for play in rules.PLAYS
                    if _available(self.game, rules.PLAYS[play])
                    and (
                        rules.PLAYS[play] not in rules.REQUISITIONS
                        or rules.held(state, role.actor, rules.PLAYS[play])
                    )
                )
                result["requisitions"].extend(
                    dict(id=rule, label=rule.removeprefix(rules.BASE).replace("-", " "))
                    for rule in rules.REQUISITIONS
                    if _available(self.game, rule) and not rules.held(state, role.actor, rule)
                )
            result["cast"] = scene.model_dump(mode="json")
            return result

        with self.store.engine.connect() as c:
            return run(c)

    def view(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        def run(c: Connection) -> dict[str, Any]:
            Access(self.store).authorize(c, viewer, "plays", director_response=True)
            state = load_state(c, self.store.campaign_id)
            value = next(
                (x for x in rules.all_records(state) if x.model_dump()["id"] == identity), None
            )
            if value is None:
                raise WorkflowError("Recover the actual saved Changeling source")
            result: dict[str, Any] = dict(
                id=identity,
                revision=state.revision,
                kind=rules.KINDS[type(value)],
                body=value.model_dump(mode="json"),
                actionable=False,
            )
            if isinstance(value, rules.Session):
                if viewer.user_id != int(value.actor.entity) and not (
                    value.play == "changeling_body_of_clay"
                    and viewer.user_id == value.handler_controller
                ):
                    raise WorkflowError(
                        "Only the original source owner and actual body-change Handler "
                        "read this history"
                    )
                prove_source(self.game, c, state, value.id)
                result["changes"] = [
                    x.model_dump(mode="json")
                    for x in rules.records(state, rules.FacetChange)
                    if x.session == value.id
                ]
            elif isinstance(value, rules.Question):
                answerer = _choice_controller(self.game, c, state, value.answerer)
                result["answerer_controller"] = answerer
                if viewer.user_id not in (value.asker_controller, answerer):
                    raise WorkflowError(
                        "Only the actual addressed humans read this private question"
                    )
                prove_fingers(self.game, c, state, value.source)
                result["actionable"] = value.answer_event is None and viewer.user_id == answerer
            elif isinstance(value, rules.Fingers):
                subject_controller = _choice_controller(self.game, c, state, value.subject)
                result["subject_controller"] = subject_controller
                if viewer.user_id not in (
                    value.controllers[value.actor.token],
                    subject_controller,
                ) and not (value.kind == "fry" and viewer.user_id == value.handler_controller):
                    raise WorkflowError("Only actual source humans read this private use")
                prove_fingers(self.game, c, state, value.id)
                result["effect"] = support.effect_detail(self.game, c, state, value)
                result["observe"] = (
                    value.kind == "sight"
                    and viewer.user_id == subject_controller
                    and not result["effect"]["body"]["ended_event"]
                )
                result["consent"] = (
                    value.kind == "sex"
                    and viewer.user_id == subject_controller
                    and value.consent_event is None
                    and value.sex_event is None
                )
                result["questions"] = [
                    x.model_dump(mode="json")
                    | {"current_answerer": _choice_controller(self.game, c, state, x.answerer)}
                    for x in rules.records(state, rules.Question)
                    if x.source == value.id
                    and viewer.user_id
                    in (x.asker_controller, _choice_controller(self.game, c, state, x.answerer))
                ]
                result["counter"] = (
                    value.main_event is not None
                    and value.counter_closed_event is None
                    and rules.reciprocal(value.subject)
                    and viewer.user_id == subject_controller
                )
                result["damage"] = (
                    value.kind == "damage"
                    and value.main_event is None
                    and viewer.user_id == subject_controller
                )
                result["fry"] = (
                    value.kind == "fry"
                    and value.main_event is None
                    and viewer.user_id == value.handler_controller
                )
                if result["counter"]:
                    result["identities"] = support.identity_options(
                        self.game,
                        c,
                        state,
                        value.actor,
                        chooser=value.target,
                        clause="fingers_counter",
                    )
                if result["damage"]:
                    actual = resolve(
                        state,
                        value.target,
                        profiles(c, self.store.campaign_id),
                        require_current_profile=False,
                    )
                    result["assets"] = [(x.id, x.name) for x in actual.assets if not x.damaged]
                result["actionable"] = any(
                    result.get(key) for key in ("counter", "damage", "fry", "observe", "consent")
                )
            elif isinstance(value, (rules.Reconditioning, rules.AssaultGift, rules.BlankSlate)):
                controller = (
                    value.controller
                    if isinstance(value, rules.Reconditioning)
                    else int(value.actor.entity)
                )
                if viewer.user_id != controller:
                    raise WorkflowError(
                        "Only the actual original owner reads this private entitlement"
                    )
                result["actionable"] = not (
                    value.replaced_event
                    if isinstance(value, rules.BlankSlate)
                    else value.completed_event
                )
                if isinstance(value, rules.Reconditioning):
                    result["tags"] = [
                        label
                        for label in rules.TAGS
                        if label.casefold()
                        not in {x.label.casefold() for x in actor_tags(state, value.subject.actor)}
                    ]
                elif isinstance(value, rules.BlankSlate) and result["actionable"]:
                    result["copies"] = [
                        dict(other=x.actor.model_dump(mode="json"), identity=x.id, label=x.label)
                        for x in rules.records(state, rules.IdentityDisclosure)
                        if x.addressed == value.actor
                    ]
                    result["conversations"] = [
                        x.model_dump(mode="json")
                        for x in rules.records(state, rules.Speech)
                        if x.kind == "conversation" and value.actor in (x.actor, x.addressed)
                    ]
                if isinstance(value, rules.BlankSlate) and value.copied_identity:
                    result["copied_label"] = rules.record(
                        state, rules.IdentityDisclosure, value.copied_identity
                    ).label
            elif isinstance(value, rules.Speech):
                if viewer.user_id not in (value.controller, value.addressed_brain.controller):
                    raise WorkflowError(
                        "Only the actual conversation humans read these saved words"
                    )
                prove_speech(self.game, c, state, value.id)
                result["push"] = (
                    value.kind == "push"
                    and value.used_by is None
                    and viewer.user_id == value.controller
                )
                result["actionable"] = result["push"]
            else:
                raise WorkflowError("Use the actual owned source history entry")
            return result

        with self.store.engine.connect() as c:
            return run(c)


def prove_flirt(
    game: GameService, c: Connection, state: GameState, identity: str
) -> rules.FlirtGrant:
    value = rules.record(state, rules.FlirtGrant, identity)
    use = prove_fingers(game, c, state, value.use)
    born = rules.record(_history(c, game, value.event), rules.FlirtGrant, identity)
    if (
        use.kind not in ("flirt_plus", "flirt_minus")
        or value.actor != use.actor
        or value.event != use.event
        or value.sign != (1 if use.kind == "flirt_plus" else -1)
        or born.model_copy(update=dict(action=value.action, rolled_event=value.rolled_event))
        != value
    ):
        raise WorkflowError("Recover the actual once-source Flirt grant and consumed String")
    return value


def reserve_flirt(
    game: GameService, c: Connection, state: GameState, action: dict[str, Any], event: str
) -> None:
    if action["data"]["play"] != "flirt":
        return
    actor = (
        ActorRef.model_validate(action["data"]["actor"])
        if action["data"].get("actor")
        else current_ref(state, int(action["actor_id"]))
    )
    options = [item for item in rules.pending_flirt(state, actor) if item.action is None]
    if not options:
        return
    value = prove_flirt(game, c, state, options[0].id)
    _live(game, c, state, rules.get(state, value.use).brain)
    rules.put(state, value.model_copy(update=dict(action=action["id"])))
    action["data"]["changeling_flirt"] = dict(
        id=value.id, use=value.use, sign=value.sign, event=value.event
    )


def _flirt(
    game: GameService, c: Connection, state: GameState, action: dict[str, Any]
) -> rules.FlirtGrant | None:
    meta = action["data"].get("changeling_flirt")
    if meta is None:
        return None
    value = prove_flirt(game, c, state, meta["id"])
    if (
        action["data"]["play"] != "flirt"
        or value.action != action["id"]
        or meta != dict(id=value.id, use=value.use, sign=value.sign, event=value.event)
        or value.actor.entity != str(action["actor_id"])
    ):
        raise WorkflowError("Keep the exact original Flirt source reservation")
    return value


def pre_roll_flirt(
    game: GameService, c: Connection, state: GameState, action: dict[str, Any]
) -> None:
    value = _flirt(game, c, state, action)
    if value is not None:
        if value.rolled_event:
            raise WorkflowError("Do not spend the actual once-use modifier twice")
        _live(game, c, state, rules.get(state, value.use).brain)


def flirt_modifier(
    game: GameService, c: Connection, state: GameState, action: dict[str, Any]
) -> int:
    value = _flirt(game, c, state, action)
    return value.sign if value else 0


def consume_flirt(
    game: GameService, c: Connection, state: GameState, action: dict[str, Any], event: str
) -> None:
    value = _flirt(game, c, state, action)
    if value is not None:
        if value.rolled_event and value.rolled_event != event:
            raise WorkflowError("The actual modifier was consumed by its original receipt")
        rules.put(state, value.model_copy(update=dict(rolled_event=event)))


def prove_flirt_modifier(
    game: GameService, c: Connection, state: GameState, action: dict[str, Any]
) -> int | None:
    value = _flirt(game, c, state, action)
    if value is None:
        return None
    if value.rolled_event is None:
        raise WorkflowError("Recover the actual committed source modifier receipt")
    saved = _history(c, game, value.rolled_event)
    consumed = rules.record(saved, rules.FlirtGrant, value.id)
    row = (
        c.execute(
            sa.select(t.events).where(
                t.events.c.campaign_id == game.store.campaign_id,
                t.events.c.id == value.rolled_event,
            )
        )
        .mappings()
        .first()
    )
    payload = json.loads(row["payload_json"]) if row else {}
    if consumed != value or row is None or payload.get("action_id") != action["id"]:
        raise WorkflowError("Preserve the actual source roll, cost and reserved modifier")
    return value.sign


def release_unrolled(
    game: GameService, c: Connection, state: GameState, action: dict[str, Any]
) -> None:
    if action["data"].get("receipt") is not None:
        raise WorkflowError("A known rolled source is not cancellable")
    value = _flirt(game, c, state, action)
    if value is not None:
        if value.rolled_event:
            raise WorkflowError("A spent modifier remains spent")
        rules.put(state, value.model_copy(update=dict(action=None)))
    meta = action["data"].get("changeling")
    if meta and meta.get("speech"):
        speech = prove_speech(game, c, state, meta["speech"])
        if speech.used_by != action["id"]:
            raise WorkflowError("Preserve the original speaker's reserved definition")
        rules.put(state, speech.model_copy(update=dict(used_by=None)))


def settle_fingers(
    game: GameService, c: Connection, state: GameState, identity: str, event: str
) -> None:
    """Called inside an actual effect/child completion; its event is published by that producer."""
    value = prove_fingers(game, c, state, identity)
    _finish_fingers(game, c, state, value, event)


def synchronize_brains(game: GameService, c: Connection, event: str) -> None:
    """Attach original starting characters only after their real brain facts are canonical."""
    if not _available(game, rules.STRINGS):
        return
    state = load_state(c, game.store.campaign_id)
    subjects = {
        item.subject
        for item in rules.records(state, rules.StartingBond)
        if item.node is None
        and any(fact.actor == item.subject for fact in rules.records(state, rules.BodyFact))
    }
    if not subjects:
        return
    fresh = str(uuid4())
    before = GameState.model_validate_json(state.model_dump_json())
    for subject in subjects:
        stage_brain(game, c, before, state, subject, fresh)
    if state == before:
        return
    human = c.scalar(
        sa.select(t.events.c.actor_id).where(
            t.events.c.campaign_id == game.store.campaign_id, t.events.c.id == event
        )
    )
    if human is None:
        raise WorkflowError("Preserve the actual source human establishing the original brain")
    game.event(
        c,
        int(human),
        str(uuid4()),
        "m3.changeling_starting_attached",
        state,
        event_id=fresh,
        source_event=event,
    )
