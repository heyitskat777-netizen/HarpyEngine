"""Source-proved Red Queen choices; Court voices are software roles, not new people."""

import json
from collections.abc import Callable
from typing import Any, Literal, cast
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_red_queen as rules
from girlframe.engine.m2 import ChoiceAnswer, GameState, PlayInput, shift_status
from girlframe.engine.m3_actor_bonds import change, current_ref, make_helpless
from girlframe.engine.m3_actor_state import ActorRef, Model, SceneCast
from girlframe.engine.m3_actors import fingerprint, resolve
from girlframe.engine.m3_handler_consequences import active_handler
from girlframe.engine.m3_intracadre_marriage import available, debit
from girlframe.engine.m3_requisition_state import FrameRuleReceipt
from girlframe.engine.m3_work_scope import WorkScope
from girlframe.engine.shared_setup import AM_ROLES
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_dose_up import _cast, _roll_source
from girlframe.services.m3_handler_advancements import _history
from girlframe.services.m3_intracadre_marriage import prepare_payment
from girlframe.services.m3_privileges import purchase_proof
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer

KINDS = (
    "red_queen_consult",
    "red_queen_questions",
    "red_queen_answers",
    "red_queen_reciprocal",
    "red_queen_reciprocal_answer",
    "red_queen_tag",
    "red_queen_memory_category",
    "red_queen_memory_handler",
    "red_queen_memory_links",
)


def _copy(state: GameState, other: GameState) -> None:
    for name in GameState.model_fields:
        setattr(state, name, getattr(other, name))


def _text(value: str) -> str:
    if not value.strip() or len(value) > 1200:
        raise WorkflowError("Provide the actual source account in 1–1200 characters")
    return value.strip()


def authorize(
    game: GameService, c: Connection, viewer: GuildViewer, action: dict[str, Any] | None = None
) -> None:
    gate = Access(game.store)
    gate.authorize(c, viewer, "plays", director_response=True)
    if action is not None:
        meta = action["data"]["red_queen"]
        approval = game.store.policy.m3_approval
        if (
            viewer.user_id not in meta["table"]
            or approval is None
            or meta["registry"] != approval.registry_sha256
        ):
            raise WorkflowError("Only this genuine original Court source table can answer")


def require_rule(
    game: GameService, c: Connection, state: GameState, actor: ActorRef, rule: str
) -> None:
    rules.frame(state, actor)
    registry = Access(game.store).registry
    if registry is None:
        raise WorkflowError("Recover the actual approved Red Queen source")
    registry.require_available(rule)
    if rule in rules.REQUISITIONS:
        receipts = rules.held(state, actor, rule)
        if not receipts:
            raise WorkflowError("Acquire the actual current Frame Requisition first")
        for receipt in receipts:
            purchase_proof(c, game.store, receipt)


def _initial(state: GameState, actor: ActorRef) -> dict[str, ActorRef]:
    sheet = state.sheets[actor.entity]
    raw = (
        sheet.frame_runtime.court
        if sheet.frame_runtime
        else next(
            (
                x.allocation
                for x in sheet.review.shared
                if x.kind == "court" and x.source_id == int(actor.entity)
            ),
            {},
        )
    )
    if set(raw) != set(AM_ROLES):
        raise WorkflowError("Recover the actual accepted five-role Court setup")
    result = {}
    for role, owner in raw.items():
        original = state.sheets.get(str(owner))
        if original is None or original.character_id is None:
            raise WorkflowError("Recover the original source Girl, never its account replacement")
        result[role] = ActorRef(kind="pilot", entity=str(owner), incarnation=original.character_id)
    return result


def initial_source(
    game: GameService, c: Connection, state: GameState, actor: ActorRef
) -> tuple[str, dict[str, ActorRef]]:
    frame = rules.frame(state, actor)
    history = t.m2["m2_state_history"]
    for row in c.execute(
        sa.select(history)
        .where(history.c.campaign_id == game.store.campaign_id)
        .order_by(history.c.revision)
    ).mappings():
        saved = GameState.model_validate_json(row["body_json"])
        sheet = saved.sheets.get(actor.entity)
        if sheet is None or sheet.character_id != actor.incarnation or sheet.frame != rules.FRAME:
            continue
        actual = (
            sheet.frame_runtime.id if sheet.frame_runtime else "initial:" + str(actor.incarnation)
        )
        if actual == frame:
            allocation = (
                sheet.frame_runtime.court
                if sheet.frame_runtime
                else next(
                    (
                        x.allocation
                        for x in sheet.review.shared
                        if x.kind == "court" and x.source_id == int(actor.entity)
                    ),
                    {},
                )
            )
            if any(str(owner) not in saved.sheets for owner in allocation.values()):
                continue
            return row["event_id"], _initial(saved, actor)
    raise WorkflowError("Recover the actual immutable creation or paid Frame delivery source")


def prove_court(game: GameService, c: Connection, state: GameState, identity: str) -> rules.Court:
    value = rules.get(state, rules.Court, identity)
    born = rules.get(_history(c, game, value.event), rules.Court, identity)
    source = _history(c, game, value.source_event)
    if (
        born != value
        or rules.frame(source, value.actor) != value.frame
        or _initial(source, value.actor) != value.initial
    ):
        raise WorkflowError("Preserve the original accepted Court, people and physical Frame")
    return value


def prove_am(game: GameService, c: Connection, state: GameState, identity: str) -> rules.CourtAM:
    value = rules.get(state, rules.CourtAM, identity)
    court = prove_court(game, c, state, value.court)
    if rules.get(_history(c, game, value.state_event), rules.CourtAM, identity) != value:
        raise WorkflowError("Preserve the exact latest canonical AM residency and mark state")
    original = rules.get(_history(c, game, value.event), rules.CourtAM, identity)
    if any(
        getattr(original, k) != getattr(value, k)
        for k in ("id", "court", "role", "person", "event")
    ):
        raise WorkflowError("Preserve the original Court voice or genuine personality-copy source")
    if value.person is not None:
        from girlframe.services.m3_red_queen_transfer import prove_bond_change

        birth = _history(c, game, value.event)
        trigger = next(
            (
                x
                for x in birth.facts
                if x.get("kind") == "red_queen_copy_source" and x.get("id") == value.id
            ),
            None,
        )
        if trigger is None:
            raise WorkflowError("Preserve the genuine Intense Bond source of this copy")
        operation = prove_bond_change(
            game, c, birth, court.actor, value.person, trigger["operation"], delta=1
        )
        if (
            operation.event != trigger["source_event"]
            or operation.before_depth >= 2
            or operation.after_depth != 2
            or value.id != rules.identity("copy", court.id, operation.id)
        ):
            raise WorkflowError("Only a genuine gain of Intense Bond creates this Court copy")
    if value.person is None and (
        value.role not in AM_ROLES or value.id != rules.identity("am", court.id, value.role)
    ):
        raise WorkflowError("Preserve the actual original five AM identities")
    for event in (value.assigned_event, value.marked_event):
        if event:
            saved = rules.get(_history(c, game, event), rules.CourtAM, identity)
            if event == value.assigned_event and saved.bearer != value.bearer:
                raise WorkflowError("Preserve the actual original AM assignment recipient")
            if event == value.marked_event and saved.marked_event != event:
                raise WorkflowError("Preserve the actual canonical AM mark")
    return value


def prove_source(
    game: GameService, c: Connection, state: GameState, identity: str
) -> rules.Session:
    value = rules.get(state, rules.Session, identity)
    action = game.action(c, identity)
    event, total = _roll_source(game, c, action)
    born = rules.get(_history(c, game, value.event), rules.Session, identity)
    if (
        any(
            getattr(born, k) != getattr(value, k)
            for k in (
                "id",
                "actor",
                "target",
                "target_controller",
                "court",
                "frame",
                "play",
                "cast",
                "handler",
                "handler_controller",
                "registry",
                "roll_event",
                "total",
                "event",
            )
        )
        or event != value.roll_event
        or total != value.total
        or action["data"].get("red_queen", {}).get("court") != value.court
    ):
        raise WorkflowError("Preserve the actual original Red Queen roll, source and participants")
    prove_court(game, c, state, value.court)
    return value


def prove_mark(game: GameService, c: Connection, state: GameState, identity: str) -> rules.Mark:
    value = rules.get(state, rules.Mark, identity)
    born = rules.get(_history(c, game, value.event), rules.Mark, identity)
    if any(
        getattr(value, k) != getattr(born, k)
        for k in (
            "id",
            "court",
            "am",
            "actor",
            "target",
            "kind",
            "event",
            "counterpart",
            "instruction",
            "amount",
            "roll",
        )
    ):
        raise WorkflowError("Preserve the actual original Queen-owned mark and effect")
    source = rules.get(_history(c, game, value.event), rules.CourtAM, value.am)
    queen = next(
        x
        for x in rules.ams(
            _history(c, game, value.event), rules.get(state, rules.Court, value.court)
        )
        if x.role == "The Queen"
    )
    if (
        source.bearer != value.target
        or queen.bearer != value.actor
        or source.marked_event != value.event
    ):
        raise WorkflowError("Only the source Queen marks the actual assigned AM")
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
    court = rules.court(state, actor)
    prove_court(game, c, state, court.id)
    scene = _cast(game, c, state, channel)
    handler = active_handler(state)
    target = prepared.target_actor
    if (
        prepared.target is not None
        or prepared.parent
        or not prepared.trigger_confirmed
        or not prepared.context.strip()
        or handler is None
        or state.handler is None
    ):
        raise WorkflowError("Use the actual source scene, performed trigger and original Handler")
    if not any(x.actor == actor and x.controller == viewer.user_id for x in scene.roles):
        raise WorkflowError("The original Red Queen must actually participate")
    if prepared.play == "red_queen_consult":
        if target is not None:
            raise WorkflowError("Consult your actual Court inside your own cockpit")
    elif (
        target is None
        or target == actor
        or (
            prepared.play != "red_queen_panopticon"
            and not any(x.actor == target for x in scene.roles)
        )
    ):
        raise WorkflowError("Choose the actual target body in this scene")
    if prepared.play == "red_queen_memory" and target and target.kind not in ("pilot", "npc"):
        raise WorkflowError("SOURCE_MEMORY_BODY_REQUIRED: use an actual supported original person")
    from girlframe.services.m3_red_queen_support import context

    sourcefacts = context(game, c, state, actor, scene, prepared.play, target, prepared.source_work)
    approval = game.store.policy.m3_approval
    assert approval is not None
    return dict(
        actor=actor.model_dump(mode="json"),
        target=target.model_dump(mode="json") if target else None,
        target_controller=resolve(state, target, profiles(c, game.store.campaign_id)).controller
        if target
        else None,
        court=court.id,
        frame=court.frame,
        cast=scene.model_dump(mode="json"),
        cast_sha256=fingerprint(scene),
        table=sorted(
            {x.controller for x in scene.roles}
            | {state.handler}
            | (
                {resolve(state, target, profiles(c, game.store.campaign_id)).controller}
                if target
                else set()
            )
        ),
        handler=handler.model_dump(mode="json"),
        handler_controller=state.handler,
        registry=approval.registry_sha256,
        sourcefacts=sourcefacts,
        phase="rolling",
        context=prepared.source_work,
    )


def bind(state: GameState, action: dict[str, Any], event: str) -> None:
    if _acting(action) != ActorRef.model_validate(action["data"]["red_queen"]["actor"]):
        raise WorkflowError("SOURCE_COURT_ACTOR_REQUIRED: preserve the actual original acting Girl")
    action["data"]["red_queen"]["bound_event"] = event


def pre_roll(
    game: GameService, c: Connection, viewer: GuildViewer, state: GameState, action: dict[str, Any]
) -> None:
    authorize(game, c, viewer, action)
    meta = action["data"]["red_queen"]
    actor = ActorRef.model_validate(meta["actor"])
    if _acting(action) != actor:
        raise WorkflowError("Preserve the actual original Court acting body before RNG")
    require_rule(game, c, state, actor, rules.PLAYS[action["data"]["play"]])
    scene = _cast(game, c, state, int(action["channel_id"]))
    if fingerprint(scene) != meta["cast_sha256"] or rules.frame(state, actor) != meta["frame"]:
        raise WorkflowError("STALE_COURT: reopen the real original source before rolling")
    from girlframe.services.m3_red_queen_support import context

    actual = context(
        game,
        c,
        state,
        actor,
        scene,
        action["data"]["play"],
        ActorRef.model_validate(meta["target"]) if meta["target"] else None,
        meta.get("context"),
    )
    if actual != meta["sourcefacts"]:
        raise WorkflowError("STALE_BODY: actual Court source facts changed before dice")


def _request(
    game: GameService, c: Connection, action: dict[str, Any], owner: int, kind: str
) -> None:
    game.request(c, action, owner, kind)


def results(game: GameService, c: Connection, state: GameState, action: dict[str, Any]) -> None:
    if any(x.id == action["id"] for x in rules.records(state, rules.Session)):
        return
    meta = action["data"]["red_queen"]
    rolled, total = _roll_source(game, c, action)
    value = rules.Session(
        id=action["id"],
        actor=ActorRef.model_validate(meta["actor"]),
        target=ActorRef.model_validate(meta["target"]) if meta["target"] else None,
        target_controller=meta["target_controller"],
        court=meta["court"],
        frame=meta["frame"],
        play=action["data"]["play"],
        cast=SceneCast.model_validate_json(json.dumps(meta["cast"])),
        handler=ActorRef.model_validate(meta["handler"]),
        handler_controller=meta["handler_controller"],
        registry=meta["registry"],
        roll_event=rolled,
        total=total,
        event=action["data"]["response_event"],
    )
    rules.put(state, value)
    meta["phase"] = "choices"
    kind = (
        "red_queen_consult"
        if value.play == "red_queen_consult"
        else "red_queen_questions"
        if value.play == "red_queen_panopticon"
        else "red_queen_memory_category"
    )
    _request(game, c, action, int(value.actor.entity), kind)


def _native_targets(
    game: GameService, c: Connection, state: GameState, source: rules.Session
) -> list[dict[str, Any]]:
    return [
        dict(
            id=x.actor.token,
            ref=x.actor.model_dump(mode="json"),
            label=resolve(state, x.actor, profiles(c, game.store.campaign_id)).label,
        )
        for x in source.cast.roles
        if x.actor != source.actor and x.actor.kind in ("pilot", "npc", "handler")
    ]


def projection(
    game: GameService, c: Connection, state: GameState, action: dict[str, Any], row: dict[str, Any]
) -> dict[str, Any]:
    value = prove_source(game, c, state, action["id"])
    court = rules.get(state, rules.Court, value.court)
    if row["kind"] in ("red_queen_answers", "red_queen_reciprocal", "red_queen_tag"):
        _question_target(game, c, state, value)
    common = dict(
        source=value.id, total=value.total, targets=_native_targets(game, c, state, value)
    )
    if row["kind"] == "red_queen_consult":
        return common | dict(
            ams=[
                dict(
                    id=x.id,
                    label=x.role,
                    bearer=x.bearer.model_dump(mode="json"),
                    marked=bool(x.marked_event),
                )
                for x in rules.ams(state, court)
            ],
            minimum=1 if value.total < 8 else 0,
            maximum=1 if value.total < 8 else len(rules.ams(state, court)),
            low=value.total < 8,
            high=value.total >= 11,
        )
    if row["kind"] in ("red_queen_questions", "red_queen_reciprocal"):
        return common | dict(
            questions=list(rules.QUESTIONS.items()),
            minimum=0 if value.total >= 8 and row["kind"] == "red_queen_questions" else 1,
            maximum=1
            if row["kind"] == "red_queen_reciprocal" or value.total < 8
            else 3
            if value.total < 11
            else len(rules.QUESTIONS),
        )
    if row["kind"] in ("red_queen_answers", "red_queen_reciprocal_answer"):
        return common | dict(
            questions=[(x, rules.QUESTIONS[x]) for x in value.questions]
            if row["kind"] == "red_queen_answers"
            else [(value.replies["reciprocal"], rules.QUESTIONS[value.replies["reciprocal"]])]
        )
    if row["kind"] == "red_queen_tag":
        return common | dict(optional=True, label="Your actual noticed observation Tag")
    if row["kind"] in ("red_queen_memory_category", "red_queen_memory_handler"):
        return common | dict(
            categories=[(x, x.title()) for x in ("person", "place", "day", "year")],
            ams=[(x.id, x.role) for x in rules.ams(state, court)],
        )
    assert value.target is not None
    sheet = state.sheets[value.target.entity]

    return common | dict(
        categories=json.loads(value.replies["categories"]),
        identities=[
            (x.id, x.name)
            for x in (sheet.identities if sheet else ())
            if not (x.protected or x.paired or x.am_limiter or x.obsession_sources)
        ],
        ams=[(x.id, x.role) for x in rules.ams(state, court)],
    )


def _ref_token(source: rules.Session, token: str) -> ActorRef:
    value = next((x.actor for x in source.cast.roles if x.actor.token == token), None)
    if value is None:
        raise WorkflowError("Choose the actual original source participant")
    return value


def _question_target(
    game: GameService, c: Connection, state: GameState, value: rules.Session
) -> int:
    assert value.target is not None
    assert value.target_controller is not None
    if value.play == "red_queen_panopticon" and value.target.kind == "npc":
        current = resolve(state, value.target, profiles(c, game.store.campaign_id))
        if current.controller != value.target_controller:
            raise WorkflowError(
                "STALE_PANOPTICON_OWNER: preserve the original observed person's current controller"
            )
    return value.target_controller


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
    value = prove_source(game, c, state, action["id"])
    kind, event, owner = row["kind"], action["data"]["response_event"], int(row["actor_id"])
    court = rules.get(state, rules.Court, value.court)
    if answer.number is not None or answer.member is not None or answer.denied:
        raise WorkflowError("Use this actual owned Court result fields")
    if kind == "red_queen_consult":
        if (
            owner != int(value.actor.entity)
            or value.selected_event
            or len(set(answer.options)) != len(answer.options)
        ):
            raise WorkflowError("Resolve the genuine Court recall once")
        candidates = {x.id: x for x in rules.ams(state, court)}
        if (
            not set(answer.options) <= set(candidates)
            or value.total < 8
            and len(answer.options) != 1
        ):
            raise WorkflowError("Recall exactly one on a low; any number otherwise")
        for key in answer.options:
            am = prove_am(game, c, state, key)
            if am.bearer != value.actor:
                rules.assign(state, am, value.actor, value.id, value.event, event)
            rules.unmark(state, rules.get(state, rules.CourtAM, key), event)
        if value.total < 8:
            target = _ref_token(value, answer.fields.get("queen", ""))
            if target == value.actor:
                raise WorkflowError("Assign the Queen to someone else")
            queen = next(x for x in rules.ams(state, court) if x.role == "The Queen")
            rules.assign(state, queen, target, value.id, value.event, event)
            advice = [x for x in rules.ams(state, court) if x.bearer == value.actor]
        else:
            decree = rules.Decree(
                id=rules.identity("decree", value.id),
                court=court.id,
                session=value.id,
                actor=value.actor,
                text=_text(answer.text),
                event=event,
            )
            rules.put(state, decree)
            value = value.model_copy(update=dict(decree=decree.id))
            advice = []
            if value.total >= 11:
                chosen = rules.get(state, rules.CourtAM, answer.fields.get("advice", ""))
                if chosen.court != court.id or chosen.bearer != value.actor:
                    raise WorkflowError("Choose an actual AM now assigned to you for advice")
                advice = [chosen]
        for am in advice:
            rules.put(
                state,
                rules.Advice(
                    cast=value.cast,
                    id=rules.identity("advice", value.id, am.id),
                    court=court.id,
                    session=value.id,
                    am=am.id,
                    actor=value.actor,
                    author=value.handler_controller,
                    event=event,
                ),
            )
        rules.put(
            state, value.model_copy(update=dict(recalled=answer.options, selected_event=event))
        )
    elif kind == "red_queen_questions":
        maximum = 1 if value.total < 8 else 3 if value.total < 11 else len(rules.QUESTIONS)
        if (
            owner != int(value.actor.entity)
            or not 0 <= len(answer.options) <= maximum
            or value.total < 8
            and len(answer.options) != 1
            or not set(answer.options) <= set(rules.QUESTIONS)
            or len(set(answer.options)) != len(answer.options)
        ):
            raise WorkflowError("Select only the real tier number of printed questions")
        value = value.model_copy(update=dict(questions=answer.options, selected_event=event))
        rules.put(state, value)
        if answer.options:
            _request(game, c, action, _question_target(game, c, state, value), "red_queen_answers")
        if value.total < 8:
            _request(
                game, c, action, _question_target(game, c, state, value), "red_queen_reciprocal"
            )
        elif value.total >= 11:
            _request(game, c, action, _question_target(game, c, state, value), "red_queen_tag")
        if answer.fields.get("tag"):
            if not rules.assigned(state, cast(ActorRef, value.target), court.id):
                raise WorkflowError("Assign an actual Court AM before this observation Tag")
            from girlframe.services.m3_red_queen_support import tag_effect

            tag_effect(
                game,
                c,
                state,
                value.actor,
                cast(ActorRef, value.target),
                _text(answer.fields["tag"]),
                value.id,
                event,
            )
    elif kind in ("red_queen_answers", "red_queen_reciprocal_answer"):
        expected = (
            _question_target(game, c, state, value)
            if kind == "red_queen_answers"
            else int(value.actor.entity)
        )
        keys = value.questions if kind == "red_queen_answers" else (value.replies["reciprocal"],)
        if owner != expected or set(answer.fields) != set(keys):
            raise WorkflowError("Only the actual asked person authors every requested answer")
        replies = dict(value.replies)
        replies.update(
            {
                ("answer:" if kind == "red_queen_answers" else "return:") + key: _text(
                    answer.fields[key]
                )
                for key in keys
            }
        )
        rules.put(state, value.model_copy(update=dict(replies=replies)))
    elif kind == "red_queen_reciprocal":
        if (
            owner != _question_target(game, c, state, value)
            or len(answer.options) != 1
            or answer.options[0] not in rules.QUESTIONS
        ):
            raise WorkflowError("Choose your actual printed reciprocal question")
        rules.put(
            state,
            value.model_copy(
                update=dict(replies=value.replies | {"reciprocal": answer.options[0]})
            ),
        )
        _request(game, c, action, int(value.actor.entity), "red_queen_reciprocal_answer")
    elif kind == "red_queen_tag":
        if owner != _question_target(game, c, state, value) or answer.flag is None:
            raise WorkflowError("Only the actual noticed person chooses their optional Tag")
        if answer.flag:
            from girlframe.services.m3_red_queen_support import tag_effect

            tag_effect(
                game,
                c,
                state,
                cast(ActorRef, value.target),
                value.actor,
                _text(answer.text),
                value.id,
                event,
            )
    elif kind in ("red_queen_memory_category", "red_queen_memory_handler"):
        expected = (
            int(value.actor.entity)
            if kind == "red_queen_memory_category"
            else value.handler_controller
        )
        if (
            owner != expected
            or len(answer.options) != 1
            or answer.options[0] not in ("person", "place", "day", "year")
        ):
            raise WorkflowError("The actual source chooser selects one printed memory category")
        categories = json.loads(value.replies.get("categories", "[]"))
        if kind == "red_queen_memory_handler" and answer.options[0] in {
            x["kind"] for x in categories
        }:
            raise WorkflowError("Choose another actual memory category")
        scope = _text(answer.text)
        if answer.options[0] == "year" and answer.fields.get("years", "") != "1+":
            raise WorkflowError("Confirm a real time range of at least one year")
        categories.append(dict(kind=answer.options[0], scope=scope))
        replies = dict(value.replies)
        if kind == "red_queen_memory_category":
            chosen = rules.get(state, rules.CourtAM, answer.fields.get("am", ""))
            if chosen.court != court.id:
                raise WorkflowError("Select your actual existing Court AM for the extraction")
            replies["am"] = chosen.id
        rules.put(
            state,
            value.model_copy(update=dict(replies=replies | {"categories": json.dumps(categories)})),
        )
        if kind == "red_queen_memory_category" and value.total >= 11:
            _request(game, c, action, value.handler_controller, "red_queen_memory_handler")
        else:
            _request(
                game, c, action, _question_target(game, c, state, value), "red_queen_memory_links"
            )
    else:
        if owner != _question_target(game, c, state, value):
            raise WorkflowError(
                "Only the actual affected human supplies factual memory/Identity links"
            )
        categories = json.loads(value.replies["categories"])
        extractions = []
        for index, category in enumerate(categories):
            memories = tuple(
                x.strip()
                for x in answer.fields.get(f"memories{index}", "").splitlines()
                if x.strip()
            )
            ids = tuple(x for x in answer.fields.get(f"identities{index}", "").split(",") if x)
            am = rules.get(state, rules.CourtAM, value.replies["am"])
            if am.court != court.id:
                raise WorkflowError("Install a real existing AM of this Court")
            extraction = rules.Extraction(
                id=rules.identity("extraction", value.id, str(index)),
                court=court.id,
                session=value.id,
                actor=value.actor,
                target=cast(ActorRef, value.target),
                category=category["kind"],
                scope=category["scope"],
                memories=memories,
                identities=ids,
                am=am.id,
                through_revision=state.revision,
                low=value.total < 8,
                event=event,
            )
            extractions.append(extraction)
        from girlframe.services.m3_red_queen_support import extract_memories

        work = extract_memories(game, c, state, tuple(extractions), event)
        rules.put(state, value.model_copy(update=dict(selected_event=event, work=tuple(work))))
    action["data"]["red_queen"]["phase"] = "effects"
    return True


def synchronize(game: GameService, c: Connection, action: dict[str, Any], event: str) -> None:
    from girlframe.services.m3_red_queen_support import synchronize as synchronize_effects

    synchronize_effects(game, c, event)
    state = load_state(c, game.store.campaign_id)
    value = next((x for x in rules.records(state, rules.Session) if x.id == action["id"]), None)
    if value is None or not value.selected_event or game.pending(c, action["id"]):
        return
    if any(x.session == value.id and not x.order for x in rules.records(state, rules.Advice)):
        return
    if value.work:
        from girlframe.services.m3_collateral import latest

        if any(latest(game, c, x)["state"] != "resolved" for x in value.work):
            return
    if not value.completed_event:
        final = str(uuid4())
        rules.put(state, value.model_copy(update=dict(completed_event=final)))
        game.event(
            c,
            int(action["actor_id"]),
            str(uuid4()),
            "m3.red_queen_completed",
            state,
            event_id=final,
            action_id=action["id"],
            source_event=event,
        )
    action["data"]["red_queen"]["phase"] = "complete"
    from girlframe.services.m2_choices import ChoiceEngine

    ChoiceEngine(game).finish(c, state, action)
    game.save_action(c, action)


def intercept_finish(
    game: GameService, c: Connection, state: GameState, action: dict[str, Any]
) -> bool:
    if not action["data"].get("red_queen"):
        return False
    value = next((x for x in rules.records(state, rules.Session) if x.id == action["id"]), None)
    return value is None or not value.completed_event


def _body(state: GameState, ref: ActorRef, bound: Any) -> tuple[Any, ...]:
    actual = resolve(state, ref, bound)
    if not actual.alive or actual.offstage_source:
        raise WorkflowError("Use the original actual living available body")
    return actual.position_sha256, actual.vessel_id, actual.frame_instance, actual.cell


def prove_context(
    game: GameService, c: Connection, state: GameState, identity: str
) -> rules.Context:
    value = rules.get(state, rules.Context, identity)
    born = rules.get(_history(c, game, value.event), rules.Context, identity)
    audit = c.execute(
        sa.select(t.events.c.actor_id, t.events.c.kind).where(
            t.events.c.campaign_id == game.store.campaign_id, t.events.c.id == value.event
        )
    ).first()
    if (
        born != value
        or audit is None
        or audit.actor_id != str(value.author)
        or audit.kind != "m3.red_queen_context"
    ):
        raise WorkflowError("Preserve the real original human-authored Court source facts")
    bound = profiles(c, game.store.campaign_id)
    if _body(state, value.actor, bound) != (
        value.actor_position,
        value.actor_vessel,
        value.actor_frame,
        value.actor_cell,
    ) or _body(state, value.target, bound) != (
        value.target_position,
        value.target_vessel,
        value.target_frame,
        value.target_cell,
    ):
        raise WorkflowError("STALE_CONTEXT: original body, vessel or position changed")
    if fingerprint(_cast(game, c, state, value.cast.channel)) != fingerprint(value.cast):
        raise WorkflowError("STALE_CAST: record the actual current observation/access source")
    saved = _history(c, game, value.event)
    target = resolve(saved, value.target, bound, require_current_profile=False)
    actor = resolve(saved, value.actor, bound, require_current_profile=False)
    handler = active_handler(saved)
    if value.kind == "brain" and value.author not in (target.controller, saved.handler):
        raise WorkflowError("Only actual affected human or source Handler establishes brain access")
    if value.kind == "distant" and value.author != actor.controller:
        raise WorkflowError("Only the actual observer records performed observation")
    if value.kind == "watching" and (
        value.author != saved.handler
        or value.source_role != handler
        or not any(x.actor == handler and x.controller == value.author for x in value.cast.roles)
    ):
        raise WorkflowError("Watching needs actual fictional Handler presence, never GM alias")
    return value


def _born(
    game: GameService,
    c: Connection,
    state: GameState,
    model: type[Model],
    identity: str,
    event: str,
    exclude: set[str] | None = None,
) -> Model:
    current = rules.get(state, model, identity)
    original = rules.get(_history(c, game, event), model, identity)
    if current.model_dump(exclude=exclude or set()) != original.model_dump(
        exclude=exclude or set()
    ):
        raise WorkflowError("Preserve the exact immutable Court source record")
    return current


def prove_extraction(
    game: GameService, c: Connection, state: GameState, identity: str
) -> rules.Extraction:
    value = rules.get(state, rules.Extraction, identity)
    _born(
        game,
        c,
        state,
        rules.Extraction,
        identity,
        value.event,
        {"restored_event", "restored_source", "selected_am"},
    )
    source = prove_source(game, c, state, value.session)
    if (
        source.play != "red_queen_memory"
        or source.target != value.target
        or source.actor != value.actor
        or source.court != value.court
    ):
        raise WorkflowError("Preserve the real original brain-access roll and affected person")
    response = t.m2["m2_responses"]
    choice = t.m2["m2_choices"]
    answered = c.execute(
        sa.select(response.c.actor_id)
        .select_from(
            response.join(
                choice,
                sa.and_(
                    choice.c.campaign_id == response.c.campaign_id,
                    choice.c.id == response.c.choice_id,
                ),
            )
        )
        .where(
            response.c.campaign_id == game.store.campaign_id,
            response.c.event_id == value.event,
            choice.c.action_id == source.id,
            choice.c.kind == "red_queen_memory_links",
        )
    ).scalar()
    if answered != str(
        resolve(
            _history(c, game, value.event),
            value.target,
            profiles(c, game.store.campaign_id),
            require_current_profile=False,
        ).controller
    ):
        raise WorkflowError("Recover the actual affected human factual memory/Identity response")
    return value


def validate_role_case(c: Connection, game: GameService, state: GameState, case: Any) -> None:
    from girlframe.services.m3_intracadre_marriage import original_offender

    value = next((x for x in rules.records(state, rules.Breach) if x.id == case.source_work), None)
    offender = original_offender(game, c, state, case.id, case.source_event, case.subject)
    if value is not None:
        _born(game, c, state, rules.Breach, value.id, value.event, {"work", "completed_event"})
        decree = rules.get(state, rules.Decree, value.decree)
        _born(game, c, state, rules.Decree, decree.id, decree.event)
        prove_source(game, c, state, decree.session)
        source = _history(c, game, value.event)
        am = rules.get(source, rules.CourtAM, value.am)
        if (
            decree.court != value.court
            or value.actor != decree.actor
            or am.court != value.court
            or am.bearer != value.target
            or case.executor != value.actor
            or offender != value.target
            or case.source_event != value.event
        ):
            raise WorkflowError("Use only the original actual Decree breach and remote Punishment")
        return
    accusation = rules.get(state, rules.Accusation, case.source_work)
    _born(
        game,
        c,
        state,
        rules.Accusation,
        accusation.id,
        accusation.event,
        {"endorsement_event", "work", "completed_event"},
    )
    if (
        accusation.target_kind != "girl"
        or accusation.consequence_kind != "punishment"
        or accusation.target_actor != offender
        or accusation.actor != case.executor
        or accusation.endorsement_event != case.source_event
    ):
        raise WorkflowError("Preserve the original Director-endorsed actual Girl discipline")
    if case.instruction is not None and case.instruction.kind != accusation.consequence_detail.get(
        "kind"
    ):
        raise WorkflowError("Perform the actual Director-endorsed requested discipline kind")
    saved = rules.get(
        _history(c, game, cast(str, accusation.endorsement_event)), rules.Accusation, accusation.id
    )
    if (
        saved.endorsement_event != case.source_event
        or saved.director != accusation.director
        or saved.director_controller != accusation.director_controller
    ):
        raise WorkflowError("Preserve the actual original Director endorsement before discipline")


def role_scope(c: Connection, game: GameService, case: Any) -> WorkScope:
    state = load_state(c, game.store.campaign_id)
    validate_role_case(c, game, state, case)
    value = next((x for x in rules.records(state, rules.Breach) if x.id == case.source_work), None)
    if value is not None:
        source = prove_source(game, c, state, rules.get(state, rules.Decree, value.decree).session)
        return WorkScope(scene_id=source.cast.id)
    return WorkScope(campaign_context=True)


def complete_role_case(c: Connection, game: GameService, case: Any, event: str) -> None:
    state = load_state(c, game.store.campaign_id)
    validate_role_case(c, game, state, case)
    value: rules.Breach | rules.Accusation = next(
        (x for x in rules.records(state, rules.Breach) if x.id == case.source_work), None
    ) or rules.get(state, rules.Accusation, case.source_work)
    if value.completed_event:
        return
    if not case.effect_event or case.completion_event != event:
        raise WorkflowError("Complete the real Punishment and all mandatory followups")
    final = str(uuid4())
    rules.put(state, value.model_copy(update=dict(completed_event=final)))
    game.event(
        c,
        case.executor_controller,
        "red-queen-punished:" + case.id,
        "m3.red_queen_punished",
        state,
        event_id=final,
        source=value.id,
        source_event=event,
    )


def order_authority(
    game: GameService, c: Connection, state: GameState, issuer: int, target: int, instruction: str
) -> dict[str, Any] | None:
    for advice in rules.records(state, rules.Advice):
        if (
            advice.session is not None
            and advice.author == issuer
            and advice.actor.kind == "pilot"
            and advice.actor.entity == str(target)
            and advice.instruction == instruction
            and advice.answered_event
            and not advice.order
        ):
            _born(
                game,
                c,
                state,
                rules.Advice,
                advice.id,
                advice.event,
                {"instruction", "order", "answered_event"},
            )
            answered = rules.get(_history(c, game, advice.answered_event), rules.Advice, advice.id)
            if (
                answered.instruction != advice.instruction
                or answered.author != issuer
                or not answered.answered_event
            ):
                raise WorkflowError(
                    "Preserve the actual original human-authored advice instruction"
                )
            return dict(
                kind="advice",
                id=advice.id,
                target=advice.actor.model_dump(mode="json"),
                court=advice.court,
            )
    for mark in rules.records(state, rules.Mark):
        if (
            mark.kind == "order"
            and mark.actor.entity == str(issuer)
            and mark.target.kind == "pilot"
            and mark.target.entity == str(target)
            and mark.instruction == instruction
            and not mark.order
        ):
            prove_mark(game, c, state, mark.id)
            return dict(
                kind="regiment",
                id=mark.id,
                target=mark.target.model_dump(mode="json"),
                court=mark.court,
            )
    return None


def bind_order(
    game: GameService,
    c: Connection,
    state: GameState,
    source: dict[str, Any],
    order_id: str,
    event: str,
) -> None:
    if source["kind"] == "advice":
        value = rules.get(state, rules.Advice, source["id"])
        if source != order_authority(
            game, c, state, value.author, int(value.actor.entity), value.instruction
        ):
            raise WorkflowError("Bind only the actual original pending advice authority")
        if value.order:
            raise WorkflowError("Preserve the real already-issued advice Order")
        rules.put(state, value.model_copy(update=dict(order=order_id)))
    else:
        mark = prove_mark(game, c, state, source["id"])
        if source != order_authority(
            game, c, state, int(mark.actor.entity), int(mark.target.entity), mark.instruction
        ):
            raise WorkflowError("Bind only the exact pending actual Queen instruction")
        if mark.order:
            raise WorkflowError("Issue the actual Regiment Order only once")
        rules.put(state, mark.model_copy(update=dict(order=order_id, completed_event=event)))


def valid_order(
    game: GameService, c: Connection, state: GameState, body: dict[str, Any], target: ActorRef
) -> bool:
    source = body.get("red_queen")
    if not source:
        return False
    if source["kind"] == "advice":
        value = rules.get(state, rules.Advice, source["id"])
        _born(
            game,
            c,
            state,
            rules.Advice,
            value.id,
            value.event,
            {"instruction", "order", "answered_event"},
        )
        return (
            value.session is not None
            and value.actor == target
            and value.order == body["id"]
            and value.instruction == body["text"]
        )
    value_mark = prove_mark(game, c, state, source["id"])
    return (
        value_mark.kind == "order"
        and value_mark.target == target
        and value_mark.order == body["id"]
        and value_mark.instruction == body["text"]
    )


def _acting(action: dict[str, Any]) -> ActorRef:
    raw = action["data"].get("tag_context", {}).get("actor") or action["data"].get(
        "actor_basic", {}
    ).get("ref")
    if raw:
        return ActorRef.model_validate(raw)
    owner = str(action["actor_id"])
    incarnation = action["data"].get("character_ids", {}).get(owner)
    if incarnation is None:
        raise WorkflowError(
            "Recover the original bound source actor, never a current account alias"
        )
    return ActorRef(kind="pilot", entity=owner, incarnation=incarnation)


def _opponent(action: dict[str, Any]) -> ActorRef | None:
    prepared = action["data"].get("prepared", {})
    raw = prepared.get("target_actor")
    if raw:
        return ActorRef.model_validate(raw)
    owner = prepared.get("target")
    incarnation = action["data"].get("character_ids", {}).get(str(owner))
    return (
        ActorRef(kind="pilot", entity=str(owner), incarnation=incarnation)
        if owner is not None and incarnation
        else None
    )


def doll_source(
    game: GameService, c: Connection, state: GameState, actor: ActorRef
) -> dict[str, Any] | None:
    value = next(
        (
            x
            for x in rules.records(state, rules.Mark)
            if x.target == actor
            and x.kind == "doll"
            and not x.applied_event
            and rules.get(state, rules.CourtAM, x.am).marked_event == x.event
        ),
        None,
    )
    if value is None:
        return None
    current = prove_am(game, c, state, value.am)
    if current.marked_event != value.event or current.bearer != actor:
        return None
    prove_mark(game, c, state, value.id)
    return dict(id=value.id, total=7)


def consume_doll(
    game: GameService, c: Connection, state: GameState, identity: str, action: str, event: str
) -> None:
    value = prove_mark(game, c, state, identity)
    if value.applied_event:
        raise WorkflowError("This actual Doll result has already applied")
    actual = game.action(c, action)
    if actual["data"]["play"] != "disobey_orders" or _acting(actual) != value.target:
        raise WorkflowError("Apply the Doll only to its real bearer actual Disobey Play")
    rules.put(
        state,
        value.model_copy(
            update=dict(used_action=action, applied_event=event, completed_event=event)
        ),
    )


def roll_modifier(
    game: GameService, c: Connection, state: GameState, action: dict[str, Any], event: str
) -> int:
    actor = _acting(action)
    target = _opponent(action)
    total = 0
    for value in rules.records(state, rules.Mark):
        if value.kind == "modifier" and value.roll == action["id"] and not value.applied_event:
            prove_mark(game, c, state, value.id)
            am = prove_am(game, c, state, value.am)
            if am.marked_event != value.event:
                raise WorkflowError("This actual copy mark was reset before the roll")
            if actor != value.target or target != am.person or target != value.counterpart:
                raise WorkflowError(
                    "Use the personality copy only against its actual original person"
                )
            total += value.amount
            rules.put(
                state,
                value.model_copy(
                    update=dict(
                        used_action=action["id"], applied_event=event, completed_event=event
                    )
                ),
            )
    return total


def regiment_amount(
    game: GameService,
    c: Connection,
    state: GameState,
    giver: ActorRef,
    target: ActorRef,
    amount: int,
) -> int:
    for value in rules.records(state, rules.Court):
        if value.actor == giver and rules.assigned(state, target, value.id):
            if not rules.held(state, giver, rules.REGIMENT):
                continue
            require_rule(game, c, state, giver, rules.REGIMENT)
            prove_court(game, c, state, value.id)
            return 2 if amount > 0 else -2
    return amount


def reset_at_start(
    game: GameService, c: Connection, state: GameState, actor: ActorRef, period: str, event: str
) -> bool:
    try:
        value = rules.court(state, actor)
    except ValueError:
        return False
    prove_court(game, c, state, value.id)
    return rules.reset(state, actor, period, event)


class RedQueenService:
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
                raise WorkflowError("STALE_COURT: reopen the current actual source")
            event = str(uuid4())
            result = operation(c, state, event)
            self.game.event(c, viewer.user_id, key, kind, state, event_id=event, **result)
            from girlframe.services.m3_red_queen_support import synchronize as sync

            sync(self.game, c, event)
            return dict(**result, revision=load_state(c, self.store.campaign_id).revision)

        try:
            return self.store._write(
                viewer,
                key,
                kind,
                dict(revision=revision, **request),
                run,
                auto_audit=False,
                authorize=lambda c: authorize(self.game, c, viewer),
            )
        except ValueError as error:
            raise WorkflowError(str(error)) from None

    def initialize(self, viewer: GuildViewer, key: str, revision: int) -> dict[str, Any]:
        def operation(c: Connection, state: GameState, event: str) -> dict[str, Any]:
            actor = current_ref(state, viewer.user_id)
            require_rule(self.game, c, state, actor, rules.COURT)
            if any(
                x.actor == actor and x.frame == rules.frame(state, actor)
                for x in rules.records(state, rules.Court)
            ):
                raise WorkflowError("This actual original Court is already imported")
            source, allocation = initial_source(self.game, c, state, actor)
            value = rules.Court(
                id=rules.identity("court", actor.token, rules.frame(state, actor)),
                actor=actor,
                frame=rules.frame(state, actor),
                source_event=source,
                event=event,
                initial=allocation,
            )
            rules.bootstrap(state, value)
            return dict(id=value.id)

        return self._write(viewer, key, "m3.red_queen_initialized", revision, {}, operation)

    def record_context(
        self,
        viewer: GuildViewer,
        key: str,
        channel: int,
        revision: int,
        kind: Literal["distant", "brain", "watching"],
        actor: ActorRef,
        target: ActorRef,
        account: str,
    ) -> dict[str, Any]:
        def operation(c: Connection, state: GameState, event: str) -> dict[str, Any]:
            source = rules.court(state, actor)
            prove_court(self.game, c, state, source.id)
            scene = _cast(self.game, c, state, channel)
            bound = profiles(c, self.store.campaign_id)
            observer, subject = (resolve(state, x, bound) for x in (actor, target))
            if actor == target or not any(x.actor == actor for x in scene.roles):
                raise WorkflowError("Use the actual source observer and original target")
            if (
                kind == "brain"
                and target.kind == "npc"
                and state.world
                and any(
                    x.id == target.entity and x.source_kind == "wyvern_wraith"
                    for x in state.world.npcs
                )
            ):
                raise WorkflowError(
                    "A software-only Wyvern Wraith has no restrained physical brain"
                )
            handler = active_handler(state)
            if kind == "distant":
                if viewer.user_id != observer.controller:
                    raise WorkflowError(
                        "Only the original actual observer records performed observation"
                    )
                role: ActorRef | None = actor
            elif kind == "brain":
                if viewer.user_id not in (subject.controller, state.handler) or not any(
                    x.actor == target for x in scene.roles
                ):
                    raise WorkflowError(
                        "Actual affected human or source Handler confirms restrained brain access"
                    )
                role = target if viewer.user_id == subject.controller else handler
            else:
                if (
                    viewer.user_id != state.handler
                    or handler is None
                    or not any(x.actor == handler for x in scene.roles)
                ):
                    raise WorkflowError("Only actually present original Handler records watching")
                role = handler
            if role is None:
                raise WorkflowError("Recover the original real source role")
            ap, av, af, ac = _body(state, actor, bound)
            tp, tv, tf, tc = _body(state, target, bound)
            value = rules.Context(
                id=str(uuid4()),
                actor=actor,
                target=target,
                cast=scene,
                kind=kind,
                actor_position=ap,
                target_position=tp,
                actor_vessel=av,
                target_vessel=tv,
                actor_frame=af,
                target_frame=tf,
                actor_cell=ac,
                target_cell=tc,
                author=viewer.user_id,
                source_role=role,
                account=_text(account),
                event=event,
            )
            rules.put(state, value)
            return dict(id=value.id)

        return self._write(
            viewer,
            key,
            "m3.red_queen_context",
            revision,
            dict(
                channel=channel,
                kind=kind,
                actor=actor.model_dump(mode="json"),
                target=target.model_dump(mode="json"),
                account=account,
            ),
            operation,
        )

    def buy(
        self, viewer: GuildViewer, key: str, revision: int, rule: str, account: str
    ) -> dict[str, Any]:
        def operation(c: Connection, state: GameState, event: str) -> dict[str, Any]:
            from girlframe.services.m3_requisitions import RequisitionService

            actor = current_ref(state, viewer.user_id)
            original = rules.frame(state, actor)
            gate = Access(self.store)
            gate.authorize(c, viewer, "economy")
            assert gate.registry is not None
            gate.registry.require_available(rule)
            if (
                rule not in rules.REQUISITIONS
                or rule != rules.ACCUSATION
                and rules.held(state, actor, rule)
            ):
                raise WorkflowError(
                    "Choose an actual new printed source; only Accusation is repeatable"
                )
            RequisitionService(self.game)._safe(c, state, viewer.user_id)
            if available(state, actor) < 2:
                raise WorkflowError("This native Frame Requisition costs two Permissions")
            key_id = str(uuid4())
            payment = prepare_payment(self.game, c, state, viewer, actor, rule, 2, rules.FRAME)
            debit(state, actor, 2, event=event, source=key_id, payment=payment)
            receipt = FrameRuleReceipt(
                id=key_id,
                kind="ability_unlock",
                actor=actor,
                frame_instance=original,
                frame=rules.FRAME,
                donor_frame=rules.FRAME,
                rule_id=rule,
                grant="red-queen:" + key_id,
                price=2,
                account=_text(account),
                source_event=event,
            )
            state.requisitions.append(receipt)
            state.sheets[actor.entity].revision += 1
            return dict(id=key_id, requisition_id=key_id, rule_id=rule, cost=2)

        return self._write(
            viewer,
            key,
            "m3.ability_unlock_purchased",
            revision,
            dict(rule=rule, account=account),
            operation,
        )

    def mark(
        self,
        viewer: GuildViewer,
        key: str,
        channel: int,
        revision: int,
        am: str,
        kind: Literal[
            "status", "flirt", "bond", "assault", "doll", "helpless", "order", "modifier"
        ],
        *,
        counterpart: ActorRef | None = None,
        instruction: str = "",
        amount: int = 0,
        roll: str | None = None,
    ) -> dict[str, Any]:
        def operation(c: Connection, state: GameState, event: str) -> dict[str, Any]:
            value = prove_am(self.game, c, state, am)
            court = prove_court(self.game, c, state, value.court)
            queen = next(x for x in rules.ams(state, court) if x.role == "The Queen")
            if (
                resolve(state, queen.bearer, profiles(c, self.store.campaign_id)).controller
                != viewer.user_id
            ):
                raise WorkflowError("Only the actual current Queen bearer marks Court AMs")
            require_rule(self.game, c, state, court.actor, rules.COURT)
            expected = {
                "The Queen": ("status",),
                "The Consort": ("flirt", "bond"),
                "The Knight": ("assault",),
                "The Doll": ("doll",),
                "The Traitor": ("helpless",),
            }
            if kind not in expected.get(value.role, ("modifier",)) and kind != "order":
                raise WorkflowError("Choose this actual printed AM role effect")
            if kind == "order":
                require_rule(self.game, c, state, court.actor, rules.REGIMENT)
                _text(instruction)
            if kind in ("flirt", "bond", "assault", "helpless") and (
                counterpart is None or counterpart == value.bearer
            ):
                raise WorkflowError("Select the actual other person for the performed role effect")
            if kind == "modifier" and (
                value.person is None
                or amount not in (-1, 1)
                or roll is None
                or counterpart != value.person
            ):
                raise WorkflowError(
                    "Use the actual personality copy +/-1 against its original person"
                )
            if kind == "modifier":
                require_rule(self.game, c, state, court.actor, rules.PERSONALITY)
                action = self.game.action(c, cast(str, roll))
                if (
                    action["state"] not in ("awaiting_lock", "ready_to_roll")
                    or value.bearer.kind != "pilot"
                    or action["actor_id"] != value.bearer.entity
                    or action["data"].get("character_ids", {}).get(value.bearer.entity)
                    != value.bearer.incarnation
                ):
                    raise WorkflowError("Bind the copy to your real current unrolled Play")
            scene = _cast(self.game, c, state, channel)
            if not any(x.actor == value.bearer for x in scene.roles):
                raise WorkflowError(
                    "Use the actual bearer source scene; remote Queen presence is not required"
                )
            mark = rules.Mark(
                cast=scene,
                id=str(uuid4()),
                court=court.id,
                am=value.id,
                actor=queen.bearer,
                target=value.bearer,
                kind=kind,
                event=event,
                counterpart=counterpart,
                instruction=instruction,
                amount=amount,
                roll=roll,
            )
            rules.mark(state, value, mark)
            if value.bearer.kind == "pilot" and kind == "status":
                shift_status(state, int(value.bearer.entity), 1)
                mark = mark.model_copy(update=dict(applied_event=event, completed_event=event))
            elif value.bearer.kind == "pilot" and kind == "bond":
                assert counterpart is not None
                _copy(state, change(state, value.bearer, counterpart, 1, event))
                mark = mark.model_copy(update=dict(applied_event=event, completed_event=event))
            elif value.bearer.kind == "pilot" and kind == "helpless":
                assert counterpart is not None
                _copy(state, make_helpless(state, value.bearer, counterpart, event))
                mark = mark.model_copy(update=dict(applied_event=event, completed_event=event))
            elif kind not in ("doll", "modifier", "order") or value.bearer.kind != "pilot":
                from girlframe.services.m3_red_queen_support import mark_effect

                work = mark_effect(self.game, c, state, mark, event)
                mark = mark.model_copy(
                    update=dict(
                        work=tuple(work),
                        applied_event=event,
                        completed_event=event if not work else None,
                    )
                )
            rules.put(state, mark)
            return dict(id=mark.id, am=value.id)

        return self._write(
            viewer,
            key,
            "m3.red_queen_marked",
            revision,
            dict(
                channel=channel,
                am=am,
                kind=kind,
                counterpart=counterpart.model_dump(mode="json") if counterpart else None,
                instruction=instruction,
                amount=amount,
                roll=roll,
            ),
            operation,
        )

    def transfer(
        self,
        viewer: GuildViewer,
        key: str,
        revision: int,
        am: str,
        target: ActorRef,
        source: str,
        kind: Literal["sex", "bond", "punishment"],
    ) -> dict[str, Any]:
        def operation(c: Connection, state: GameState, event: str) -> dict[str, Any]:
            value = prove_am(self.game, c, state, am)
            court = prove_court(self.game, c, state, value.court)
            if (
                court.actor != value.bearer
                or resolve(state, court.actor, profiles(c, self.store.campaign_id)).controller
                != viewer.user_id
            ):
                raise WorkflowError(
                    "Only the original Red Queen transfers an AM currently assigned to herself"
                )
            require_rule(self.game, c, state, court.actor, rules.TRANSFER)
            from girlframe.services.m3_red_queen_support import transfer_source

            original = transfer_source(self.game, c, state, court.actor, target, source, kind)
            source_key = original
            if kind == "bond":
                from girlframe.services.m3_red_queen_transfer import prove_bond_change

                source_key = prove_bond_change(
                    self.game, c, state, court.actor, target, source, delta=-1
                ).id
            if any(
                previous.previous == court.actor
                and previous.target == target
                and previous.source == source_key
                for previous in rules.records(state, rules.Assignment)
            ):
                raise WorkflowError("This actual performed source already transferred its one AM")
            result = rules.assign(state, value, target, source_key, original, event)
            return dict(id=result.id)

        return self._write(
            viewer,
            key,
            "m3.red_queen_transferred",
            revision,
            dict(am=am, target=target.model_dump(mode="json"), source=source, kind=kind),
            operation,
        )

    def copy_personality(
        self, viewer: GuildViewer, key: str, revision: int, target: ActorRef, source_event: str
    ) -> dict[str, Any]:
        def operation(c: Connection, state: GameState, event: str) -> dict[str, Any]:
            from girlframe.services.m3_red_queen_transfer import prove_bond_change

            actor = current_ref(state, viewer.user_id)
            require_rule(self.game, c, state, actor, rules.PERSONALITY)
            court = rules.court(state, actor)
            operation = prove_bond_change(self.game, c, state, actor, target, source_event, delta=1)
            after = _history(c, self.game, operation.event)
            if (
                operation.before_depth >= 2
                or operation.after_depth != 2
                or rules.frame(after, actor) != court.frame
            ):
                raise WorkflowError("A real transition to an Intense Bond is required")
            identity = rules.identity("copy", court.id, operation.id)
            if any(x.id == identity for x in rules.records(state, rules.CourtAM)):
                raise WorkflowError("This exact actual gain of Intense already created its copy")
            original = resolve(
                after, target, profiles(c, self.store.campaign_id), require_current_profile=False
            )
            value = rules.CourtAM(
                id=identity,
                court=court.id,
                role="Copy of " + original.label,
                bearer=actor,
                person=target,
                event=event,
                state_event=event,
                assigned_event=event,
            )
            rules.put(state, value)
            # Keep the exact genuine triggering transition independently of present Bond depth.
            state.facts.append(
                dict(
                    kind="red_queen_copy_source",
                    id=value.id,
                    source_event=operation.event,
                    operation=operation.id,
                    event=event,
                )
            )
            return dict(id=value.id)

        return self._write(
            viewer,
            key,
            "m3.red_queen_personality",
            revision,
            dict(target=target.model_dump(mode="json"), source_event=source_event),
            operation,
        )

    def request_advice(
        self, viewer: GuildViewer, key: str, channel: int, revision: int, am: str
    ) -> dict[str, Any]:
        def operation(c: Connection, state: GameState, event: str) -> dict[str, Any]:
            value = prove_am(self.game, c, state, am)
            court = rules.get(state, rules.Court, value.court)
            if int(court.actor.entity) != viewer.user_id or value.person is None:
                raise WorkflowError("Ask advice from your actual acquired personality copy")
            require_rule(self.game, c, state, court.actor, rules.PERSONALITY)
            author = resolve(state, value.person, profiles(c, self.store.campaign_id)).controller
            source = rules.Advice(
                cast=_cast(self.game, c, state, channel),
                id=str(uuid4()),
                court=court.id,
                session=None,
                am=value.id,
                actor=court.actor,
                author=author,
                event=event,
            )
            rules.put(state, source)
            return dict(id=source.id)

        return self._write(
            viewer,
            key,
            "m3.red_queen_advice_requested",
            revision,
            dict(channel=channel, am=am),
            operation,
        )

    def answer_advice(
        self, viewer: GuildViewer, key: str, revision: int, identity: str, instruction: str
    ) -> dict[str, Any]:
        def operation(c: Connection, state: GameState, event: str) -> dict[str, Any]:
            value = rules.get(state, rules.Advice, identity)
            _born(
                self.game,
                c,
                state,
                rules.Advice,
                value.id,
                value.event,
                {"instruction", "order", "answered_event"},
            )
            if value.author != viewer.user_id or value.answered_event:
                raise WorkflowError("Only the actual requested human authors this advice once")
            if value.session:
                source = prove_source(self.game, c, state, value.session)
                if source.handler_controller != viewer.user_id:
                    raise WorkflowError(
                        "The actual original Handler gives the printed Court advice"
                    )
            rules.put(
                state,
                value.model_copy(update=dict(instruction=_text(instruction), answered_event=event)),
            )
            return dict(id=value.id)

        return self._write(
            viewer,
            key,
            "m3.red_queen_advice_answered",
            revision,
            dict(id=identity, instruction=instruction),
            operation,
        )

    def report_breach(
        self,
        viewer: GuildViewer,
        key: str,
        revision: int,
        decree: str,
        target: ActorRef,
        account: str,
    ) -> dict[str, Any]:
        def operation(c: Connection, state: GameState, event: str) -> dict[str, Any]:
            value = rules.get(state, rules.Decree, decree)
            _born(self.game, c, state, rules.Decree, value.id, value.event)
            prove_source(self.game, c, state, value.session)
            if value.actor.entity != str(viewer.user_id):
                raise WorkflowError(
                    "Only the actual original Red Queen interprets her Decree breach"
                )
            am = next((x for x in rules.assigned(state, target, value.court)), None)
            if am is None:
                raise WorkflowError("The actual reported person must bear an AM of this Court")
            actual = resolve(state, target, profiles(c, self.store.campaign_id))
            if target == value.actor or not actual.alive:
                raise WorkflowError(
                    "Punish a real other living assigned person for an actual breach"
                )
            breach = rules.Breach(
                id=str(uuid4()),
                decree=value.id,
                court=value.court,
                actor=value.actor,
                target=target,
                am=am.id,
                account=_text(account),
                event=event,
            )
            rules.put(state, breach)
            from girlframe.services.m3_red_queen_support import punishment

            work = punishment(self.game, c, state, breach, event)
            if not work:
                raise WorkflowError("An actual source-owned remote Punishment must be opened")
            rules.put(state, breach.model_copy(update=dict(work=tuple(work))))
            return dict(id=breach.id)

        return self._write(
            viewer,
            key,
            "m3.red_queen_decree_breach",
            revision,
            dict(decree=decree, target=target.model_dump(mode="json"), account=account),
            operation,
        )

    def restore_memory(
        self,
        viewer: GuildViewer,
        key: str,
        revision: int,
        identity: str,
        source_event: str,
        source_id: str,
        am: str | None,
        account: str,
    ) -> dict[str, Any]:
        def operation(c: Connection, state: GameState, event: str) -> dict[str, Any]:
            value = prove_extraction(self.game, c, state, identity)
            if (
                not value.low
                or value.restored_event
                or resolve(state, value.target, profiles(c, self.store.campaign_id)).controller
                != viewer.user_id
            ):
                raise WorkflowError(
                    "Only the actual low-result affected person chooses this restoration"
                )
            from girlframe.services.m3_red_queen_support import association_source

            association_source(self.game, c, state, value, source_event, source_id, _text(account))
            if am is not None:
                selected = prove_am(self.game, c, state, am)
                if selected.court != value.court:
                    raise WorkflowError("Choose an actual existing AM from this original Court")
                if selected.bearer != value.target:
                    rules.assign(state, selected, value.target, source_id, source_event, event)
            rules.put(
                state,
                value.model_copy(
                    update=dict(restored_event=event, restored_source=source_id, selected_am=am)
                ),
            )
            return dict(id=value.id)

        return self._write(
            viewer,
            key,
            "m3.red_queen_memory_restored",
            revision,
            dict(
                id=identity, source_event=source_event, source_id=source_id, am=am, account=account
            ),
            operation,
        )

    def accuse(
        self,
        viewer: GuildViewer,
        key: str,
        revision: int,
        purchase: str,
        target_kind: Literal["girl", "city", "base", "npc"],
        target: str,
        allegation: str,
        consequence: str,
        *,
        consequence_kind: Literal["punishment", "npc_tag", "administrative_closure"],
        consequence_detail: dict[str, str],
        director: ActorRef | None = None,
    ) -> dict[str, Any]:
        def operation(c: Connection, state: GameState, event: str) -> dict[str, Any]:
            actor = current_ref(state, viewer.user_id)
            require_rule(self.game, c, state, actor, rules.ACCUSATION)
            receipt = next(
                (x for x in rules.held(state, actor, rules.ACCUSATION) if x.id == purchase), None
            )
            if receipt is None:
                raise WorkflowError("Erase exactly one actual unspent acquired Accusation")
            source = rules.Accusation(
                id=str(uuid4()),
                court=rules.court(state, actor).id,
                actor=actor,
                purchase=purchase,
                target_kind=target_kind,
                target=target,
                allegation=_text(allegation),
                consequence=_text(consequence),
                consequence_kind=consequence_kind,
                consequence_detail=consequence_detail,
                director=director,
                event=event,
            )
            from girlframe.services.m3_red_queen_support import validate_accusation

            authority = validate_accusation(self.game, c, state, source)
            if source.target_kind in ("girl", "npc") and not authority.get("target_actor"):
                raise WorkflowError(
                    "Freeze the actual original accused person before erasing the Requisition"
                )
            source = source.model_copy(
                update=dict(
                    director=ActorRef.model_validate(authority["director"]),
                    director_controller=int(authority["director_controller"]),
                    target_actor=ActorRef.model_validate(authority["target_actor"])
                    if authority.get("target_actor")
                    else None,
                )
            )
            rules.put(state, source)
            return dict(id=source.id, purchase=purchase)

        return self._write(
            viewer,
            key,
            "m3.red_queen_accused",
            revision,
            dict(
                purchase=purchase,
                target_kind=target_kind,
                target=target,
                allegation=allegation,
                consequence=consequence,
                consequence_kind=consequence_kind,
                consequence_detail=consequence_detail,
                director=director.model_dump(mode="json") if director else None,
            ),
            operation,
        )

    def endorse(
        self, viewer: GuildViewer, key: str, revision: int, identity: str
    ) -> dict[str, Any]:
        def operation(c: Connection, state: GameState, event: str) -> dict[str, Any]:
            source = rules.get(state, rules.Accusation, identity)
            _born(
                self.game,
                c,
                state,
                rules.Accusation,
                identity,
                source.event,
                {"endorsement_event", "work", "completed_event"},
            )
            if source.endorsement_event:
                raise WorkflowError("Reopen the actual existing Director-endorsed consequence")
            from girlframe.services.m3_red_queen_support import endorse_accusation

            work = endorse_accusation(self.game, c, state, source, viewer, event)
            rules.put(
                state,
                source.model_copy(
                    update=dict(
                        endorsement_event=event,
                        work=tuple(work),
                        completed_event=event if not work else None,
                    )
                ),
            )
            return dict(id=source.id)

        return self._write(
            viewer, key, "m3.red_queen_endorsed", revision, dict(id=identity), operation
        )

    def _tasks(self, c: Connection, viewer: GuildViewer) -> list[dict[str, Any]]:
        state = load_state(c, self.store.campaign_id)
        rows = []
        for value in rules.records(state, rules.Advice):
            if viewer.user_id in (value.author, int(value.actor.entity)):
                pending = value.answered_event is None and value.session is not None
                rows.append(
                    dict(
                        id=value.id,
                        revision=state.revision,
                        label="Give actual Court advice"
                        if viewer.user_id == value.author
                        else "Read actual Court advice",
                        phase="pending" if pending else "complete",
                        pending=pending and viewer.user_id == value.author,
                    )
                )
        for breach in rules.records(state, rules.Breach):
            people = {
                resolve(
                    state, x, profiles(c, self.store.campaign_id), require_current_profile=False
                ).controller
                for x in (breach.actor, breach.target)
            }
            if viewer.user_id in people:
                rows.append(
                    dict(
                        id=breach.id,
                        revision=state.revision,
                        label="Actual Decree discipline",
                        phase="complete" if breach.completed_event else "pending",
                        pending=not bool(breach.completed_event),
                    )
                )
        for loss in rules.records(state, rules.Extraction):
            people = {
                resolve(
                    state, x, profiles(c, self.store.campaign_id), require_current_profile=False
                ).controller
                for x in (loss.actor, loss.target)
            }
            if viewer.user_id in people:
                rows.append(
                    dict(
                        id=loss.id,
                        revision=state.revision,
                        label="Saved fictional memory extraction",
                        phase="complete",
                        pending=False,
                    )
                )
        for marked in rules.records(state, rules.Mark):
            controllers = {
                resolve(
                    state, x, profiles(c, self.store.campaign_id), require_current_profile=False
                ).controller
                for x in (marked.actor, marked.target)
            }
            if viewer.user_id in controllers:
                pending = (
                    marked.kind in ("flirt", "assault", "order") and not marked.completed_event
                )
                target_controller = resolve(
                    state,
                    marked.target,
                    profiles(c, self.store.campaign_id),
                    require_current_profile=False,
                ).controller
                owner = (
                    target_controller
                    if marked.kind in ("flirt", "assault")
                    else resolve(
                        state,
                        marked.actor,
                        profiles(c, self.store.campaign_id),
                        require_current_profile=False,
                    ).controller
                )
                rows.append(
                    dict(
                        id=marked.id,
                        revision=state.revision,
                        label="Actual Court " + marked.kind,
                        phase="pending" if pending else "complete",
                        pending=pending and owner == viewer.user_id,
                    )
                )
        for session in rules.records(state, rules.Session):
            audience = {int(session.actor.entity), session.handler_controller}
            if session.target_controller is not None:
                audience.add(session.target_controller)
            if viewer.user_id in audience:
                rows.append(
                    dict(
                        id=session.id,
                        revision=state.revision,
                        label="Saved " + session.play.removeprefix("red_queen_").replace("_", " "),
                        phase="complete" if session.completed_event else "waiting",
                        pending=False,
                    )
                )
        for accusation in rules.records(state, rules.Accusation):
            if viewer.user_id in (int(accusation.actor.entity), accusation.director_controller):
                pending = not accusation.endorsement_event
                rows.append(
                    dict(
                        id=accusation.id,
                        revision=state.revision,
                        label="Actual Director endorsement"
                        if viewer.user_id == accusation.director_controller
                        else "Saved Biting Accusation",
                        phase="pending" if pending else "complete",
                        pending=pending and viewer.user_id == accusation.director_controller,
                    )
                )
        return rows

    def menu(self, viewer: GuildViewer, channel: int | None = None) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            authorize(self.game, c, viewer)
            state = load_state(c, self.store.campaign_id)
            bound = profiles(c, self.store.campaign_id)
            actor = (
                current_ref(state, viewer.user_id)
                if str(viewer.user_id) in state.sheets
                else active_handler(state)
            )
            own = None
            if (
                actor
                and actor.kind == "pilot"
                and state.sheets[actor.entity].frame == rules.FRAME
                and not state.sheets[actor.entity].frame_scrapped
            ):
                own = next(
                    (
                        x
                        for x in rules.records(state, rules.Court)
                        if x.actor == actor and x.frame == rules.frame(state, actor)
                    ),
                    None,
                )
            courts = []
            for value in rules.records(state, rules.Court):
                members = rules.ams(state, value)
                queen = next(x for x in members if x.role == "The Queen")
                queen_controller = resolve(
                    state, queen.bearer, bound, require_current_profile=False
                ).controller
                own_source = value.actor.entity == str(viewer.user_id)
                visible = (
                    own_source
                    or queen_controller == viewer.user_id
                    or viewer.user_id == state.handler
                    or any(
                        resolve(state, x.bearer, bound, require_current_profile=False).controller
                        == viewer.user_id
                        for x in members
                    )
                )
                if visible:
                    courts.append(
                        dict(
                            id=value.id,
                            actor=value.actor.model_dump(mode="json"),
                            label=resolve(
                                state, value.actor, bound, require_current_profile=False
                            ).label,
                            can_mark=queen_controller == viewer.user_id,
                            ams=[
                                x.model_dump(mode="json") | dict(label=x.role)
                                for x in members
                                if own_source
                                or queen_controller == viewer.user_id
                                or resolve(
                                    state, x.bearer, bound, require_current_profile=False
                                ).controller
                                == viewer.user_id
                            ],
                        )
                    )
            scene = _cast(self.game, c, state, channel) if channel is not None else None
            targets = []
            if scene:
                refs = {x.actor for x in scene.roles}
                refs.update(current_ref(state, x.owner) for x in state.sheets.values())
                if actor and state.world:
                    from girlframe.services.m3_actors import ActorService
                    from girlframe.services.m3_missions import MissionService

                    known = ActorService(MissionService(self.store)).known(viewer, actor)
                    refs.update(ActorRef.model_validate(x["ref"]) for x in known["actors"])
                for ref in refs:
                    actual = resolve(state, ref, bound, require_current_profile=False)
                    if actual.alive:
                        targets.append(
                            dict(id=ref.token, ref=ref.model_dump(mode="json"), label=actual.label)
                        )
            from girlframe.services.m3_red_queen_support import accusation_targets, director_options

            directors = director_options(self.game, c, state, viewer)
            judgements = []
            if own and rules.held(state, own.actor, rules.JUDGEMENT):
                from girlframe.services.m3_red_queen_support import judgement_source

                for watching in rules.records(state, rules.Context):
                    if (
                        watching.kind != "watching"
                        or watching.actor != own.actor
                        or watching.target.kind != "pilot"
                    ):
                        continue
                    subject = state.sheets.get(watching.target.entity)
                    if subject is None or subject.character_id != watching.target.incarnation:
                        continue
                    for tag in subject.tags:
                        if any(
                            x.tag == tag.id and x.court == own.id
                            for x in rules.records(state, rules.Judgement)
                        ):
                            continue
                        try:
                            judgement_source(self.game, c, state, watching, tag.id)
                        except WorkflowError:
                            continue
                        judgements.append(
                            dict(
                                id=rules.identity("judgement-option", watching.id, tag.id),
                                context=watching.id,
                                tag=tag.id,
                                label=resolve(state, watching.target, bound).label
                                + ": "
                                + tag.label,
                            )
                        )
            own_sheet = state.sheets.get(str(viewer.user_id))
            return dict(
                judgements=judgements,
                directors=directors,
                accusation_targets=accusation_targets(self.game, c, state, viewer),
                accusation_purchases=[
                    dict(id=x.id, label="Biting Accusation " + str(index + 1))
                    for index, x in enumerate(rules.held(state, own.actor, rules.ACCUSATION))
                ]
                if own
                else [],
                heat=own_sheet.heat if own_sheet else 0,
                sheet_revision=own_sheet.revision if own_sheet else None,
                identities=[(x.id, x.name) for x in own_sheet.identities if not x.marked]
                if own_sheet
                else [],
                pending_rolls=[
                    dict(
                        id=row["id"],
                        label=json.loads(row["body_json"])["play"].replace("_", " ").title(),
                    )
                    for row in c.execute(
                        sa.select(t.m2["m2_actions"]).where(
                            t.m2["m2_actions"].c.campaign_id == self.store.campaign_id,
                            t.m2["m2_actions"].c.actor_id == str(viewer.user_id),
                            t.m2["m2_actions"].c.state.in_(("awaiting_lock", "ready_to_roll")),
                        )
                    ).mappings()
                ],
                contexts=[
                    dict(
                        id=x.id,
                        label=x.kind
                        + ": "
                        + resolve(state, x.target, bound, require_current_profile=False).label,
                        kind=x.kind,
                        target=x.target.model_dump(mode="json"),
                    )
                    for x in rules.records(state, rules.Context)
                    if x.author == viewer.user_id or x.actor.entity == str(viewer.user_id)
                ],
                decrees=[
                    dict(id=x.id, label=x.text, target=x.actor.model_dump(mode="json"))
                    for x in rules.records(state, rules.Decree)
                    if x.actor.entity == str(viewer.user_id)
                ],
                revision=state.revision,
                actor=actor.model_dump(mode="json") if actor else None,
                can_initialize=bool(
                    actor
                    and actor.kind == "pilot"
                    and state.sheets[actor.entity].frame == rules.FRAME
                    and not own
                ),
                courts=courts,
                targets=targets,
                tasks=self._tasks(c, viewer),
                plays=[
                    (x, y)
                    for x, y in rules.PLAYS.items()
                    if own and (y not in rules.REQUISITIONS or rules.held(state, own.actor, y))
                ],
                requisitions=[
                    dict(
                        id=x,
                        label=x.removeprefix(rules.BASE).replace("-", " ").title(),
                        held=len(rules.held(state, own.actor, x)),
                    )
                    for x in rules.REQUISITIONS
                ]
                if own
                else [],
            )

    def view(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            authorize(self.game, c, viewer)
            state = load_state(c, self.store.campaign_id)
            bound = profiles(c, self.store.campaign_id)
            value = next(
                (
                    x
                    for model in rules.KINDS
                    for x in rules.records(state, model)
                    if str(x.model_dump()["id"]) == identity
                ),
                None,
            )
            if value is None:
                raise WorkflowError("Open the actual saved private Court source")
            people = set()
            if isinstance(value, rules.Advice):
                people = {
                    value.author,
                    resolve(state, value.actor, bound, require_current_profile=False).controller,
                }
            elif isinstance(value, rules.Mark):
                people = {
                    resolve(state, x, bound, require_current_profile=False).controller
                    for x in (value.actor, value.target)
                }
            elif isinstance(value, rules.Session):
                people = {int(value.actor.entity), value.handler_controller} | (
                    {value.target_controller} if value.target_controller is not None else set()
                )
            elif isinstance(value, (rules.Extraction, rules.Breach)):
                people = {
                    resolve(state, x, bound, require_current_profile=False).controller
                    for x in (value.actor, value.target)
                }
            elif isinstance(value, rules.Assignment):
                people = {
                    resolve(state, x, bound, require_current_profile=False).controller
                    for x in (value.previous, value.target)
                }
                people.add(
                    resolve(
                        state,
                        rules.get(state, rules.Court, value.court).actor,
                        bound,
                        require_current_profile=False,
                    ).controller
                )
            elif isinstance(value, rules.Context):
                people = {
                    value.author,
                    resolve(state, value.actor, bound, require_current_profile=False).controller,
                    resolve(state, value.target, bound, require_current_profile=False).controller,
                }
            elif isinstance(value, rules.Accusation):
                from girlframe.services.m3_red_queen_support import accusation_viewers

                people = set(accusation_viewers(self.game, c, state, value))
            else:
                court = rules.get(
                    state,
                    rules.Court,
                    value.id
                    if isinstance(value, rules.Court)
                    else str(value.model_dump()["court"]),
                )
                people = {
                    resolve(state, court.actor, bound, require_current_profile=False).controller
                }
                if isinstance(value, rules.CourtAM):
                    people.add(
                        resolve(
                            state, value.bearer, bound, require_current_profile=False
                        ).controller
                    )
            if viewer.user_id not in people:
                raise WorkflowError("This source is private to its actual original people")
            labels = {}
            for label in ("actor", "target", "bearer", "person"):
                ref = getattr(value, label, None)
                if isinstance(ref, ActorRef):
                    labels[label] = resolve(state, ref, bound, require_current_profile=False).label
            return dict(
                labels=labels,
                id=identity,
                revision=state.revision,
                kind=rules.KINDS[type(value)],
                source=value.model_dump(mode="json"),
                can_child=isinstance(value, rules.Mark)
                and value.kind in ("flirt", "assault")
                and not value.completed_event
                and resolve(state, value.target, bound, require_current_profile=False).controller
                == viewer.user_id,
                can_answer=isinstance(value, rules.Advice)
                and value.author == viewer.user_id
                and not value.answered_event,
                can_endorse=isinstance(value, rules.Accusation)
                and not value.endorsement_event
                and value.director_controller == viewer.user_id,
                can_restore=isinstance(value, rules.Extraction)
                and value.low
                and not value.restored_event
                and resolve(state, value.target, bound, require_current_profile=False).controller
                == viewer.user_id,
            )

    def judge(
        self, viewer: GuildViewer, key: str, revision: int, context: str, tag: str
    ) -> dict[str, Any]:
        def operation(c: Connection, state: GameState, event: str) -> dict[str, Any]:
            watched = prove_context(self.game, c, state, context)
            actor = current_ref(state, viewer.user_id)
            if (
                watched.kind != "watching"
                or watched.actor != actor
                or watched.target.kind != "pilot"
            ):
                raise WorkflowError(
                    "Lower the actual native Tag recipient while the real Handler watches"
                )
            require_rule(self.game, c, state, actor, rules.JUDGEMENT)
            from girlframe.services.m3_red_queen_support import judgement_source

            source = judgement_source(self.game, c, state, watched, tag)
            court = rules.court(state, actor)
            identity = rules.identity("judgement", court.id, tag)
            if any(x.id == identity for x in rules.records(state, rules.Judgement)):
                raise WorkflowError("Apply the actual Tag-linked Status reduction once")
            shift_status(state, int(watched.target.entity), -1)
            rules.put(
                state,
                rules.Judgement(
                    id=identity,
                    court=court.id,
                    actor=actor,
                    target=watched.target,
                    tag=tag,
                    tag_event=source,
                    context=context,
                    event=event,
                ),
            )
            return dict(id=identity)

        return self._write(
            viewer,
            key,
            "m3.red_queen_judgement",
            revision,
            dict(context=context, tag=tag),
            operation,
        )

    def restoration_options(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            data = self.view(viewer, identity)
            state = load_state(c, self.store.campaign_id)
            value = prove_extraction(self.game, c, state, identity)
            if not data["can_restore"]:
                raise WorkflowError(
                    "Only this actual affected person selects a real new association"
                )
            history = t.m2["m2_state_history"]
            seen: set[str] = set()
            options: list[dict[str, Any]] = []
            extraction_revision = _history(c, self.game, value.event).revision
            for row in c.execute(
                sa.select(history)
                .where(history.c.campaign_id == self.store.campaign_id)
                .order_by(history.c.revision)
            ).mappings():
                saved = GameState.model_validate_json(row["body_json"])
                if value.target.kind == "pilot":
                    sheet = saved.sheets.get(value.target.entity)
                    entries = (
                        sheet.identities
                        if sheet and sheet.character_id == value.target.incarnation
                        else []
                    )
                    labels = {x.id: x.name for x in entries}
                else:
                    npc = (
                        next((x for x in saved.world.npcs if x.id == value.target.entity), None)
                        if saved.world
                        else None
                    )
                    labels = {x.id: x.label for x in npc.tags} if npc else {}
                if saved.revision > extraction_revision:
                    options.extend(
                        dict(
                            id=rules.identity("association", row["event_id"], key),
                            source=key,
                            event=row["event_id"],
                            label=label,
                        )
                        for key, label in labels.items()
                        if key not in seen and key not in value.identities
                    )
                seen.update(labels)
            court = rules.get(state, rules.Court, value.court)
            return dict(
                revision=state.revision,
                options=options,
                ams=[(x.id, x.role) for x in rules.ams(state, court)],
            )


def validate_pending_mark(
    game: GameService, c: Connection, state: GameState, value: rules.Mark, event: str
) -> None:
    before = load_state(c, game.store.campaign_id)
    original = prove_am(game, c, before, value.am)
    court = prove_court(game, c, before, value.court)
    queen = next(x for x in rules.ams(before, court) if x.role == "The Queen")
    staged = rules.get(state, rules.CourtAM, value.am)
    if (
        original.marked_event
        or value.event != event
        or value.actor != queen.bearer
        or value.target != original.bearer
        or value.court != original.court
        or staged.marked_event != event
        or staged.state_event != event
        or rules.get(state, rules.Mark, value.id) != value
    ):
        raise WorkflowError("Stage only this actual original unmarked Queen-owned Court effect")
    if fingerprint(_cast(game, c, state, value.cast.channel)) != fingerprint(value.cast):
        raise WorkflowError("Use the actual current bearer scene for the Court source effect")


def transfer_options(
    game: GameService,
    c: Connection,
    state: GameState,
    actor: ActorRef,
    target: ActorRef,
    kind: Literal["sex", "bond", "punishment"],
) -> list[dict[str, str]]:
    from girlframe.services.m3_red_queen_support import transfer_source

    candidates = []
    if kind == "sex":
        from girlframe.engine import m3_bonded as bonded

        actions = t.m2["m2_actions"]
        candidates = list(
            c.scalars(
                sa.select(actions.c.id).where(
                    actions.c.campaign_id == game.store.campaign_id, actions.c.state == "complete"
                )
            )
        )
        candidates.extend(
            x.id
            for x in bonded.records(state, bonded.Source)
            if x.kind == "sex" and x.phase == "complete"
        )
        from girlframe.engine import m3_am_sex as am_sex

        candidates.extend(
            x.id for x in am_sex.sources(state) if x.mode == "both_am" and x.phase == "complete"
        )
    elif kind == "punishment":
        candidates = [x.id for x in state.role_punishments if x.completion_event]
    else:
        from girlframe.engine.m3_bond_operations import records

        candidates = [
            x.id for x in records(state) if x.delta == -1 and {x.first, x.second} == {actor, target}
        ]
    result: list[dict[str, str]] = []
    for source in candidates:
        try:
            event = transfer_source(game, c, state, actor, target, source, kind)
        except WorkflowError:
            continue
        result.append(
            dict(
                id=source,
                event=event,
                label="Completed " + kind + " source " + str(len(result) + 1),
            )
        )
    return result


def personality_options(
    game: GameService, c: Connection, state: GameState, actor: ActorRef, target: ActorRef
) -> list[dict[str, str]]:
    from girlframe.engine.m3_bond_operations import records
    from girlframe.services.m3_red_queen_transfer import prove_bond_change

    result: list[dict[str, str]] = []
    for value in records(state):
        if (
            value.delta != 1
            or value.before_depth >= 2
            or value.after_depth != 2
            or {value.first, value.second} != {actor, target}
        ):
            continue
        prove_bond_change(game, c, state, actor, target, value.id, delta=1)
        identity = rules.identity("copy", rules.court(state, actor).id, value.id)
        if any(x.id == identity for x in rules.records(state, rules.CourtAM)):
            continue
        result.append(dict(id=value.id, label="Actual newly Intense Bond " + str(len(result) + 1)))
    return result


def _prove_roll_use(
    game: GameService, c: Connection, state: GameState, value: rules.Mark, action: dict[str, Any]
) -> None:
    prove_mark(game, c, state, value.id)
    if (
        not value.applied_event
        or value.used_action != action["id"]
        or value.target != _acting(action)
    ):
        raise WorkflowError("Preserve the original actual consumed Court mark and bound roll")
    saved = rules.get(_history(c, game, value.applied_event), rules.Mark, value.id)
    if (
        saved.applied_event != value.applied_event
        or saved.used_action != action["id"]
        or saved.target != value.target
    ):
        raise WorkflowError("Recover the real canonical Court modifier application")
    receipt = action["data"].get("receipt")
    if not receipt:
        raise WorkflowError("A Court roll effect requires its actual immutable raw receipt")
    row = c.execute(
        sa.select(t.events.c.kind, t.events.c.payload_json).where(
            t.events.c.campaign_id == game.store.campaign_id, t.events.c.id == value.applied_event
        )
    ).first()
    payload = json.loads(row.payload_json) if row else {}
    if (
        row is None
        or row.kind not in ("m2.rolled", "m3.rolled")
        or payload.get("action_id") != action["id"]
        or payload.get("receipt_id") != receipt["id"]
    ):
        raise WorkflowError(
            "Bind Court adjustments only to the actual canonical original roll event"
        )


def prove_doll_limit(
    game: GameService, c: Connection, state: GameState, action: dict[str, Any]
) -> int | None:
    values = [
        x
        for x in rules.records(state, rules.Mark)
        if x.kind == "doll" and x.used_action == action["id"]
    ]
    if not values:
        return None
    if len(values) != 1 or action["data"]["play"] != "disobey_orders":
        raise WorkflowError("Preserve one actual next-Disobey Doll application")
    _prove_roll_use(game, c, state, values[0], action)
    return 7


def prove_personality_modifier(
    game: GameService, c: Connection, state: GameState, action: dict[str, Any]
) -> int | None:
    values = [
        x
        for x in rules.records(state, rules.Mark)
        if x.kind == "modifier" and x.used_action == action["id"]
    ]
    if not values:
        return None
    total = 0
    for value in values:
        _prove_roll_use(game, c, state, value, action)
        am = rules.get(state, rules.CourtAM, value.am)
        if (
            value.roll != action["id"]
            or value.amount not in (-1, 1)
            or am.person != _opponent(action)
            or value.counterpart != am.person
        ):
            raise WorkflowError(
                "Preserve the actual original personality copy, opponent and signed amount"
            )
        total += value.amount
    return total
