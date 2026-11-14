"""WYVERN's actual questions, choices and source-owned physical consequences."""

import json
from collections.abc import Callable
from typing import Any, Literal, cast
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_wyvern as rules
from girlframe.engine.m2 import ChoiceAnswer, GameState, PlayInput
from girlframe.engine.m3_actor_bonds import change, current_ref, depth
from girlframe.engine.m3_actor_state import ActorRef, SceneCast
from girlframe.engine.m3_actors import fingerprint, owned_refs, resolve
from girlframe.engine.m3_handler_consequences import active_handler
from girlframe.engine.m3_intracadre_marriage import available, debit
from girlframe.engine.m3_mockingbird import give_tag
from girlframe.engine.m3_requisition_state import FrameRuleReceipt
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_dose_up import _roll_source
from girlframe.services.m3_enforcement_initiative import _cast
from girlframe.services.m3_handler_advancements import _history
from girlframe.services.m3_intracadre_marriage import prepare_payment
from girlframe.services.m3_requisitions import RequisitionService
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer

HEAT_IDS = tuple(rules.PLAYS)
KINDS = (
    "wyvern_questions",
    "wyvern_unmark",
    "wyvern_danger",
    "wyvern_answers_done",
    "wyvern_rouse_cost",
    "wyvern_wraith",
    "wyvern_wraith_rules",
    "wyvern_shield_bond",
    "wyvern_child",
)


def _copy(target: GameState, source: GameState) -> None:
    for field in GameState.model_fields:
        setattr(target, field, getattr(source, field))


def authorize(
    game: GameService, c: Connection, viewer: GuildViewer, action: dict[str, Any] | None = None
) -> None:
    access = Access(game.store)
    access.authorize(c, viewer, "plays", director_response=action is not None)
    if action is not None:
        meta = action["data"]["wyvern"]
        approval = game.store.policy.m3_approval
        if (
            viewer.user_id not in meta["table"]
            or approval is None
            or approval.registry_sha256 != meta["registry"]
        ):
            raise WorkflowError("Use the original actual WYVERN source-table response")


def prove_acquisition(
    game: GameService, c: Connection, state: GameState, receipt: FrameRuleReceipt
) -> None:
    source = (
        c.execute(
            sa.select(t.events).where(
                t.events.c.campaign_id == game.store.campaign_id,
                t.events.c.id == receipt.source_event,
            )
        )
        .mappings()
        .first()
    )
    saved = _history(c, game, receipt.source_event)
    if (
        source is None
        or source["kind"] != "m3.ability_unlock_purchased"
        or source["actor_id"] != receipt.actor.entity
        or receipt not in saved.requisitions
        or receipt.donor_frame != rules.FRAME
        or receipt.rule_id not in rules.REQUISITIONS
        or receipt.price != 2
        or receipt.grant != "wyvern:" + receipt.id
        or json.loads(source["payload_json"]).get("requisition_id") != receipt.id
    ):
        raise WorkflowError("Recover this actual paid original Frame's WYVERN acquisition")


def require_rule(
    game: GameService, c: Connection, state: GameState, actor: ActorRef, rule: str
) -> None:
    rules.frame(state, actor)
    registry = Access(game.store).registry
    if registry is None:
        raise WorkflowError("Recover the actual reviewed WYVERN rules")
    registry.require_available(rule)
    if rule in rules.REQUISITIONS:
        receipt = rules.held(state, actor, rule)
        if receipt is None:
            raise WorkflowError("Acquire this actual original Frame's Requisition first")
        prove_acquisition(game, c, state, receipt)


def _context(
    game: GameService,
    c: Connection,
    state: GameState,
    actor: ActorRef,
    scene: SceneCast,
    play: str,
    target: ActorRef | None = None,
) -> dict[str, Any]:
    from girlframe.services.m3_wyvern_support import context

    return context(game, c, state, actor, scene, play, target)


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
        or not any(x.actor == actor and x.controller == viewer.user_id for x in scene.roles)
        or prepared.target is not None
        or prepared.order_id
        or prepared.off_duty_id
        or not prepared.context.strip()
    ):
        raise WorkflowError("Use the actual original WYVERN, Handler and declared source scene")
    if prepared.play != "wyvern_protector" and prepared.target_actor is not None:
        raise WorkflowError("Only Protector selects an actual protected person")
    if prepared.play == "wyvern_protector" and (
        prepared.target_actor is None or prepared.target_actor == actor
    ):
        raise WorkflowError("Use yourself as an actual shield for another actual person")
    party = None
    if prepared.play == "wyvern_explore":
        party = next(
            (x for x in rules.records(state, rules.Party) if x.id == prepared.source_work), None
        )
        if (
            party is None
            or party.actor != actor
            or party.frame != rules.frame(state, actor)
            or party.cancelled_event
            or party.bound_action
            or set(party.present) != {actor, *party.companions}
            or fingerprint(party.cast) != fingerprint(scene)
        ):
            raise WorkflowError(
                "Declare your actual exploration party and collect each real role's attendance"
            )
    elif prepared.source_work:
        raise WorkflowError("Use this actual WYVERN source rather than an unrelated work token")
    if prepared.play == "wyvern_rouse" and rules.roused(state, actor):
        raise WorkflowError("Use the actual already-Roused Frame before trying to rouse it again")
    facts = _context(game, c, state, actor, scene, prepared.play, prepared.target_actor)
    if party is not None:
        from girlframe.services.m3_wyvern_support import exploration_party

        facts["companions"] = exploration_party(game, c, state, actor, scene, party.companions)
    if (
        prepared.play == "wyvern_rouse"
        and len(_identity_options(game, c, state, actor, "erase")) < 2
    ):
        raise WorkflowError(
            "WYVERN_ERASURE_SOURCE_REQUIRED: the possible high result "
            "needs two legal actual erasures"
        )
    if prepared.play == "wyvern_wraith" and all(
        any(
            x.frame == rules.frame(state, actor) and x.slot == slot and x.active
            for x in rules.records(state, rules.Wraith)
        )
        for slot in rules.SLOTS
    ):
        raise WorkflowError("Every original Frame mind is already unleashed")
    if scene not in state.scene_casts:
        state.scene_casts.append(scene)
    assert game.store.policy.m3_approval is not None
    return dict(
        actor=actor.model_dump(mode="json"),
        target=prepared.target_actor.model_dump(mode="json") if prepared.target_actor else None,
        handler=handler.model_dump(mode="json"),
        handler_controller=state.handler,
        frame=rules.frame(state, actor),
        table=sorted(
            {x.controller for x in scene.roles}
            | {state.handler}
            | ({scene.facilitator} if scene.facilitator is not None else set())
        ),
        cast=scene.model_dump(mode="json"),
        cast_sha256=fingerprint(scene),
        registry=game.store.policy.m3_approval.registry_sha256,
        sourcefacts=facts,
        party=party.id if party else None,
        phase="unrolled",
    )


def bind(state: GameState, action: dict[str, Any], event: str) -> None:
    meta = action["data"]["wyvern"]
    meta["begin_event"] = event
    if meta["party"]:
        party = next(x for x in rules.records(state, rules.Party) if x.id == meta["party"])
        rules.put(state, party.model_copy(update={"bound_action": action["id"]}))


def pre_roll(
    game: GameService, c: Connection, viewer: GuildViewer, state: GameState, action: dict[str, Any]
) -> None:
    meta = action["data"]["wyvern"]
    party = next((x for x in rules.records(state, rules.Party) if x.id == meta.get("party")), None)
    if party:
        # Same genuine reservation is part of this action, never a second party.
        rules.put(state, party.model_copy(update={"bound_action": None}))
    expected = prepare(
        game,
        c,
        viewer,
        state,
        PlayInput.model_validate(action["data"]["prepared"]),
        int(action["channel_id"]),
    )
    if party:
        rules.put(state, party)
    if any(meta.get(k) != v for k, v in expected.items() if k != "phase"):
        raise WorkflowError(
            "Reopen the unchanged actual Frame, bodies, party and rules before rolling"
        )


def prove_source(
    game: GameService, c: Connection, state: GameState, identity: str
) -> rules.Session:
    source = next((x for x in rules.records(state, rules.Session) if x.id == identity), None)
    if source is None:
        raise WorkflowError("Recover the actual original WYVERN source")
    actual = game.action(c, identity)
    event, total = _roll_source(game, c, actual)
    meta = actual["data"].get("wyvern", {})
    if (
        event != source.roll_event
        or total != source.total
        or source.actor.model_dump(mode="json") != meta.get("actor")
        or source.actor.entity != str(actual["actor_id"])
        or (source.target.model_dump(mode="json") if source.target else None) != meta.get("target")
        or source.frame != meta.get("frame")
        or source.play != actual["data"]["play"]
        or source.handler.model_dump(mode="json") != meta.get("handler")
        or source.handler_controller != meta.get("handler_controller")
        or source.cast.model_dump(mode="json") != meta.get("cast")
        or fingerprint(source.cast) != meta.get("cast_sha256")
        or source.party != meta.get("party")
    ):
        raise WorkflowError(
            "Preserve the actual original WYVERN caster, Frame and immutable receipt"
        )
    return source


def _request(
    game: GameService, c: Connection, action: dict[str, Any], owner: int, kind: str
) -> None:
    if not any(
        x["kind"] == kind and x["actor_id"] == str(owner) for x in game.pending(c, action["id"])
    ):
        game.request(c, action, owner, kind)


def results(game: GameService, c: Connection, state: GameState, action: dict[str, Any]) -> None:
    from girlframe.services.m3_wyvern_support import excursion

    meta = action["data"]["wyvern"]
    if meta["phase"] != "unrolled":
        raise WorkflowError("Resume this real original WYVERN roll without repeating it")
    rolled, total = _roll_source(game, c, action)
    source = rules.Session(
        id=action["id"],
        actor=ActorRef.model_validate(meta["actor"]),
        target=ActorRef.model_validate(meta["target"]) if meta["target"] else None,
        frame=meta["frame"],
        play=action["data"]["play"],
        handler=ActorRef.model_validate(meta["handler"]),
        handler_controller=meta["handler_controller"],
        cast=SceneCast.model_validate_json(json.dumps(meta["cast"])),
        total=total,
        roll_event=rolled,
        event=action["data"].get("response_event") or rolled,
        party=meta["party"],
    )
    rules.put(state, source)
    meta["phase"] = "choosing"
    if source.play == "wyvern_explore":
        party = next(x for x in rules.records(state, rules.Party) if x.id == source.party)
        changed, work = excursion(
            game,
            c,
            state,
            source,
            source.event,
            operation="enter",
            actors=(source.actor, *party.companions),
        )
        _copy(state, changed)
        rules.put(state, rules.session(state, source.id).model_copy(update={"work": work}))
        _request(
            game,
            c,
            action,
            source.handler_controller if total < 8 else int(source.actor.entity),
            "wyvern_questions",
        )
    elif source.play == "wyvern_rouse":
        if 8 <= total <= 10:
            rules.put(
                state,
                rules.Roused(
                    id=rules.identity("roused", source.id),
                    actor=source.actor,
                    frame=source.frame,
                    session=source.id,
                    event=source.event,
                ),
            )
            meta["phase"] = "effects"
        else:
            _request(game, c, action, int(source.actor.entity), "wyvern_rouse_cost")
    elif source.play == "wyvern_wraith":
        _request(
            game,
            c,
            action,
            source.handler_controller if total < 8 else int(source.actor.entity),
            "wyvern_wraith",
        )
    elif total >= 8:
        from girlframe.services.m3_wyvern_support import shield

        assert source.target is not None
        protected = rules.Shield(
            id=rules.identity("shield", source.id),
            session=source.id,
            actor=source.actor,
            frame=source.frame,
            target=source.target,
            target_vessel=meta["sourcefacts"].get("target_vessel"),
            high=total >= 11,
            event=source.event,
        )
        rules.put(state, protected)
        # Shield proof reloads the action: persist this validated in-flight total
        # in the same transaction before checking the newly staged effect.
        game.save_action(c, action)
        changed, work = shield(game, c, state, protected, source.event)
        _copy(state, changed)
        rules.put(
            state,
            rules.session(state, source.id).model_copy(
                update={"shield": protected.id, "work": work}
            ),
        )
        if total < 11:
            _request(
                game,
                c,
                action,
                resolve(state, source.target, profiles(c, game.store.campaign_id)).controller,
                "wyvern_shield_bond",
            )
        else:
            meta["phase"] = "effects"
    else:
        from girlframe.services.m3_wyvern_support import handler_play

        assert source.target is not None
        if depth(state, source.actor, source.target):
            _copy(state, change(state, source.actor, source.target, -1, source.event))
        changed, work = handler_play(game, c, state, source, source.event)
        _copy(state, changed)
        rules.put(state, rules.session(state, source.id).model_copy(update={"work": work}))
        meta["phase"] = "effects"


def _identity_options(
    game: GameService, c: Connection, state: GameState, actor: ActorRef, mode: str
) -> list[tuple[str, str]]:
    from girlframe.services.m3_wyvern_support import identity_options

    return identity_options(game, c, state, actor, mode=mode)


def projection(
    game: GameService, c: Connection, state: GameState, action: dict[str, Any], row: dict[str, Any]
) -> dict[str, Any]:
    source = prove_source(game, c, state, action["id"])
    kind = row["kind"]
    if kind == "wyvern_questions":
        return dict(
            questions=list(rules.questions(state, source.actor).items()),
            count=2 if source.total >= 11 else 1,
            danger=source.total < 8,
        )
    if kind in ("wyvern_unmark", "wyvern_rouse_cost"):
        mode = "unmark" if kind == "wyvern_unmark" else "erase"
        options = _identity_options(game, c, state, source.actor, mode)
        count = 2 if source.total >= 11 else 1
        from girlframe.services.m3_wyvern_support import identity_requirements

        return dict(
            identities=options,
            count=min(count, len(options)) if mode == "unmark" else count,
            heat=kind == "wyvern_rouse_cost" and source.total >= 11,
            requirements=identity_requirements(game, c, state, source.actor)
            if mode == "erase"
            else {},
        )
    if kind == "wyvern_danger":
        return dict(
            options=[
                ("delay", "It takes time to return safely"),
                ("escape", "A genuine Play is required to escape"),
            ]
        )
    if kind == "wyvern_answers_done":
        return dict(
            questions=[
                dict(
                    id=q.id,
                    text=q.text,
                    answers=[
                        dict(author=x.author, text=x.text)
                        for x in rules.records(state, rules.Answer)
                        if x.question == q.id
                    ],
                )
                for q in rules.records(state, rules.Question)
                if q.session == source.id
            ]
        )
    if kind == "wyvern_wraith":
        active = {
            x.slot
            for x in rules.records(state, rules.Wraith)
            if x.frame == source.frame and x.active
        }
        return dict(options=[(x, x) for x in rules.SLOTS if x not in active])
    if kind == "wyvern_wraith_rules":
        return dict(
            tag=source.total < 8 or source.total >= 11,
            profile=[("frame_bound_npc", "Actual Frame-bound NPC mind")],
        )
    if kind == "wyvern_child":
        return dict(danger=source.danger)
    return dict(options=[("deepen", "Deepen your actual Bond"), ("pass", "Do not deepen it")])


detail = projection


def _advance_exploration(
    game: GameService, c: Connection, state: GameState, action: dict[str, Any]
) -> None:
    source = prove_source(game, c, state, action["id"])
    if source.unmarked_event is None:
        _request(game, c, action, int(source.actor.entity), "wyvern_unmark")
    elif source.total >= 11 and source.danger is None:
        _request(game, c, action, source.handler_controller, "wyvern_danger")
    elif source.answers_closed_event is None:
        _request(game, c, action, int(source.actor.entity), "wyvern_answers_done")
    elif source.danger:
        danger = next(x for x in rules.records(state, rules.Danger) if x.id == source.danger)
        action["data"]["wyvern"]["phase"] = "returning"
        if danger.kind == "escape" and not danger.child_completed_event:
            _request(game, c, action, int(source.actor.entity), "wyvern_child")
    else:
        _return(game, c, state, action)


def _return(
    game: GameService,
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    source: rules.Session | None = None,
    event: str | None = None,
    *,
    elapsed_fact: str | None = None,
    child_action: str | None = None,
) -> None:
    from girlframe.services.m3_wyvern_support import excursion

    source = source or prove_source(game, c, state, action["id"])
    danger = next((x for x in rules.records(state, rules.Danger) if x.id == source.danger), None)
    if danger and (
        (danger.kind == "delay" and not danger.elapsed_event)
        or (danger.kind == "escape" and not danger.child_completed_event)
    ):
        raise WorkflowError("Resolve the actual source time or escape performance before returning")
    party = next(x for x in rules.records(state, rules.Party) if x.id == source.party)
    event = event or action["data"].get("response_event") or source.event
    changed, work = excursion(
        game,
        c,
        state,
        source,
        event,
        operation="return",
        actors=(source.actor, *party.companions),
        elapsed_fact=elapsed_fact or (danger.elapsed_event if danger else None),
        child_action=child_action or (danger.child if danger else None),
    )
    _copy(state, changed)
    if danger:
        rules.put(state, danger.model_copy(update={"returned_event": event}))
    rules.put(
        state, source.model_copy(update={"work": tuple(dict.fromkeys((*source.work, *work)))})
    )
    action["data"]["wyvern"]["phase"] = "effects"


def apply(
    game: GameService,
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    row: dict[str, Any],
    answer: ChoiceAnswer,
) -> None:
    from girlframe.services import m3_wyvern_support as support

    source = prove_source(game, c, state, action["id"])
    event, kind = action["data"]["response_event"], row["kind"]
    if source.completed_event or answer.flag is not None or answer.member is not None:
        raise WorkflowError("Use the original owned pending WYVERN printed choice")
    if kind == "wyvern_questions":
        chooser = source.handler_controller if source.total < 8 else int(source.actor.entity)
        count = 2 if source.total >= 11 else 1
        available_questions = rules.questions(state, source.actor)
        if (
            int(row["actor_id"]) != chooser
            or source.questions
            or len(answer.options) != count
            or not set(answer.options) <= set(available_questions)
            or answer.denied
            or answer.number is not None
            or set(answer.fields) != ({"danger"} if source.total < 8 else set())
        ):
            raise WorkflowError("The printed original chooser selects the actual Frame questions")
        ids = []
        for index, key in enumerate(answer.options):
            identity = rules.identity("asked", source.id, str(index))
            rules.put(
                state,
                rules.Question(
                    id=identity,
                    session=source.id,
                    actor=source.actor,
                    frame=source.frame,
                    text=available_questions[key],
                    table=tuple(action["data"]["wyvern"]["table"]),
                    event=event,
                ),
            )
            ids.append(identity)
        danger_id = None
        if source.total < 8:
            if answer.fields["danger"] not in ("delay", "escape"):
                raise WorkflowError("The actual Handler chooses one printed return danger")
            danger_id = rules.identity("danger", source.id)
            rules.put(
                state,
                rules.Danger(
                    id=danger_id,
                    session=source.id,
                    actor=source.actor,
                    frame=source.frame,
                    kind=cast(Literal["delay", "escape"], answer.fields["danger"]),
                    event=event,
                ),
            )
        rules.put(state, source.model_copy(update={"questions": tuple(ids), "danger": danger_id}))
        _advance_exploration(game, c, state, action)
    elif kind in ("wyvern_unmark", "wyvern_rouse_cost"):
        mode = "unmark" if kind == "wyvern_unmark" else "erase"
        options = _identity_options(game, c, state, source.actor, mode)
        count = 2 if source.total >= 11 else 1
        expected = min(count, len(options)) if mode == "unmark" else count
        if (
            int(row["actor_id"]) != int(source.actor.entity)
            or len(answer.denied) != expected
            or not set(answer.denied) <= {x[0] for x in options}
            or answer.options
            or set(answer.fields) - ({"mentor_tags"} if mode == "erase" else set())
            or (
                kind == "wyvern_rouse_cost"
                and source.total >= 11
                and (answer.number is None or not 1 <= answer.number <= 10)
            )
            or (
                not (kind == "wyvern_rouse_cost" and source.total >= 11)
                and answer.number is not None
            )
        ):
            raise WorkflowError("Choose the actual legal source identities and printed Heat amount")
        mentor_tags = (
            json.loads(answer.fields["mentor_tags"]) if answer.fields.get("mentor_tags") else None
        )
        if mentor_tags is not None and (
            not isinstance(mentor_tags, dict)
            or not all(isinstance(k, str) and isinstance(v, str) for k, v in mentor_tags.items())
        ):
            raise WorkflowError("Choose the actual Identity-to-original-Mentor-Tag mapping")
        changed, work = support.identity_change(
            game,
            c,
            state,
            source.actor,
            answer.denied,
            event,
            source.id,
            mode=mode,
            mentor_tags=mentor_tags,
        )
        _copy(state, changed)
        source = source.model_copy(update={"work": tuple(dict.fromkeys((*source.work, *work)))})
        if mode == "unmark":
            rules.put(state, source.model_copy(update={"unmarked_event": event}))
            _advance_exploration(game, c, state, action)
        elif source.total >= 11:
            state.sheets[source.actor.entity].heat += cast(int, answer.number)
            state.sheets[source.actor.entity].revision += 1
            rules.put(state, source)
            rules.put(
                state,
                rules.Roused(
                    id=rules.identity("roused", source.id),
                    actor=source.actor,
                    frame=source.frame,
                    session=source.id,
                    event=event,
                ),
            )
            action["data"]["wyvern"]["phase"] = "effects"
        else:
            rules.put(state, source)
            rules.put(
                state,
                rules.Last(
                    id=event, actor=source.actor, frame=source.frame, session=source.id, event=event
                ),
            )
            action["data"]["wyvern"]["phase"] = "effects"
    elif kind == "wyvern_danger":
        if (
            int(row["actor_id"]) != source.handler_controller
            or source.danger
            or source.total < 11
            or len(answer.options) != 1
            or answer.options[0] not in ("delay", "escape")
            or answer.fields
            or answer.denied
            or answer.number is not None
        ):
            raise WorkflowError("The original Handler chooses the actual high exploration danger")
        identity = rules.identity("danger", source.id)
        rules.put(
            state,
            rules.Danger(
                id=identity,
                session=source.id,
                actor=source.actor,
                frame=source.frame,
                kind=cast(Literal["delay", "escape"], answer.options[0]),
                event=event,
            ),
        )
        rules.put(state, source.model_copy(update={"danger": identity}))
        _advance_exploration(game, c, state, action)
    elif kind == "wyvern_answers_done":
        if (
            int(row["actor_id"]) != int(source.actor.entity)
            or answer.options != ("done",)
            or answer.fields
            or answer.denied
            or answer.number is not None
            or not all(
                any(x.question == q for x in rules.records(state, rules.Answer))
                for q in source.questions
            )
        ):
            raise WorkflowError(
                "Collect at least one actual table-authored Frame answer to every question"
            )
        for question in rules.records(state, rules.Question):
            if question.session == source.id:
                rules.put(state, question.model_copy(update={"closed_event": event}))
        rules.put(state, source.model_copy(update={"answers_closed_event": event}))
        _advance_exploration(game, c, state, action)
    elif kind == "wyvern_shield_bond":
        if (
            source.target is None
            or answer.options not in (("deepen",), ("pass",))
            or answer.fields
            or answer.denied
            or answer.number is not None
        ):
            raise WorkflowError("The actual recipient owns their optional real Bond")
        if answer.options == ("deepen",):
            _copy(state, change(state, source.target, source.actor, 1, event))
        action["data"]["wyvern"]["phase"] = "effects"
    elif kind in ("wyvern_wraith", "wyvern_wraith_rules"):
        _wraith_choice(game, c, state, action, source, row, answer, event)
    else:
        raise WorkflowError(
            "Perform the actual required escape Play; acknowledgement cannot replace it"
        )


def _wraith_choice(
    game: GameService,
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    source: rules.Session,
    row: dict[str, Any],
    answer: ChoiceAnswer,
    event: str,
) -> None:
    from girlframe.services.m3_wyvern_support import spawn_wraith

    if row["kind"] == "wyvern_wraith":
        chooser = source.handler_controller if source.total < 8 else int(source.actor.entity)
        if (
            int(row["actor_id"]) != chooser
            or source.wraith
            or len(answer.options) != 1
            or answer.options[0] not in rules.SLOTS
            or set(answer.fields) - {"name"}
            or answer.denied
            or answer.number is not None
        ):
            raise WorkflowError("The printed original chooser selects one actual Frame mind")
        slot = answer.options[0]
        old = next(
            (
                x
                for x in rules.records(state, rules.Wraith)
                if x.frame == source.frame and x.slot == slot
            ),
            None,
        )
        if old and old.active:
            raise WorkflowError("That actual original mind is already unleashed")
        name = (
            "Sarah"
            if slot == "battery"
            else old.name
            if old
            else answer.fields.get("name", "").strip()
        )
        if (
            not name
            or len(name) > 120
            or (old and answer.fields.get("name", old.name) != old.name)
            or (slot == "battery" and answer.fields.get("name", "Sarah") != "Sarah")
        ):
            raise WorkflowError(
                "Name the original previously unnamed mind; Sarah retains her printed name"
            )
        mind = rules.Wraith(
            id=rules.identity("wraith", source.frame, slot),
            actor=source.actor,
            frame=source.frame,
            slot=cast(Literal["gunner", "navigator", "captain", "battery"], slot),
            name=name,
            persona=old.persona if old else None,
            handler=source.handler,
            handler_controller=source.handler_controller,
            session=source.id,
            table=tuple(action["data"]["wyvern"]["table"]),
            event=event,
            controller=old.controller if old else int(source.actor.entity),
            stubborn=source.total >= 11,
        )
        rules.put(state, mind)
        rules.put(state, source.model_copy(update={"wraith": mind.id}))
        _request(game, c, action, source.handler_controller, "wyvern_wraith_rules")
    else:
        mind = next(x for x in rules.records(state, rules.Wraith) if x.id == source.wraith)
        if (
            int(row["actor_id"]) != source.handler_controller
            or answer.options != ("frame_bound_npc",)
            or answer.denied
            or answer.number is not None
            or set(answer.fields) != ({"tag"} if source.total < 8 or source.total >= 11 else set())
            or not answer.text.strip()
        ):
            raise WorkflowError(
                "The actual original Handler states the supported NPC mind rules "
                "and owns the printed Tag"
            )
        mind = mind.model_copy(
            update={
                "profile": "frame_bound_npc",
                "rules_answer": answer.text.strip(),
                "rules_event": event,
                "active": True,
            }
        )
        rules.put(state, mind)
        changed, persona = spawn_wraith(game, c, state, mind, event)
        _copy(state, changed)
        mind = mind.model_copy(update={"persona": persona})
        rules.put(state, mind)
        if "tag" in answer.fields:
            label = answer.fields["tag"].strip()
            if not label or len(label) > 120:
                raise WorkflowError("The actual Handler authors the real printed mind Tag")
            _copy(
                state,
                give_tag(
                    state,
                    profiles(c, game.store.campaign_id),
                    persona,
                    source.handler,
                    label,
                    event,
                    event,
                    tuple(action["data"]["wyvern"]["table"]),
                ),
            )
            mind = mind.model_copy(update={"tag": event})
        rules.put(state, mind)
        action["data"]["wyvern"]["phase"] = "effects"


def _pending_work(game: GameService, c: Connection, ids: tuple[str, ...]) -> bool:
    work = t.m3["m3_required_work"]
    for identity in ids:
        row = c.execute(
            sa.select(work.c.state)
            .where(work.c.campaign_id == game.store.campaign_id, work.c.id == identity)
            .order_by(work.c.revision.desc())
            .limit(1)
        ).first()
        if row is None or row.state == "pending":
            return True
    return False


def intercept_finish(
    game: GameService, c: Connection, state: GameState, action: dict[str, Any]
) -> bool:
    source = next((x for x in rules.records(state, rules.Session) if x.id == action["id"]), None)
    if source is None:
        return False
    if _pending_work(game, c, source.work):
        return True
    if source.play == "wyvern_explore":
        danger = next(
            (x for x in rules.records(state, rules.Danger) if x.id == source.danger), None
        )
        return not source.answers_closed_event or (danger is not None and not danger.returned_event)
    return False


def synchronize(game: GameService, c: Connection, action: dict[str, Any], event: str) -> None:
    from girlframe.services.m2_choices import ChoiceEngine
    from girlframe.services.m3_wyvern_support import synchronize as sync_effects

    sync_effects(game, c, event)
    if action["state"] in ("complete", "aborted") or game.pending(c, action["id"]):
        return
    state = load_state(c, game.store.campaign_id)
    if intercept_finish(game, c, state, action):
        return
    source = prove_source(game, c, state, action["id"])
    if source.completed_event is None:
        completed = str(uuid4())
        human = c.scalar(
            sa.select(t.events.c.actor_id).where(
                t.events.c.campaign_id == game.store.campaign_id, t.events.c.id == event
            )
        )
        if human is None:
            raise WorkflowError("Preserve the genuine human event completing this source")
        rules.put(state, source.model_copy(update={"completed_event": completed}))
        game.event(
            c,
            int(human),
            str(uuid4()),
            "m3.wyvern_completed",
            state,
            event_id=completed,
            action_id=source.id,
            source_event=event,
        )
    action["data"]["wyvern"]["phase"] = "complete"
    ChoiceEngine(game).finish(c, state, action)
    game.save_action(c, action)


def prove_use(game: GameService, c: Connection, state: GameState, identity: str) -> rules.RousedUse:
    use = next((x for x in rules.records(state, rules.RousedUse) if x.id == identity), None)
    if use is None:
        raise WorkflowError("Recover the actual original consumed-Roused source")
    validate_pending_use(game, c, state, use, use.event)
    saved = _history(c, game, use.event)
    original = next((x for x in rules.records(saved, rules.RousedUse) if x.id == identity), None)
    if original is None or any(
        getattr(original, key) != getattr(use, key)
        for key in (
            "actor",
            "frame",
            "roused",
            "target",
            "kind",
            "cast",
            "event",
            "asset",
            "target_frame",
            "incoming",
        )
    ):
        raise WorkflowError("Preserve this actual original Roused use and canonical human event")
    return use


def validate_pending_use(
    game: GameService, c: Connection, state: GameState, use: rules.RousedUse, event: str
) -> None:
    roused = next((x for x in rules.records(state, rules.Roused) if x.id == use.roused), None)
    if (
        roused is None
        or roused.use != use.id
        or roused.frame != use.frame
        or prove_source(game, c, state, roused.session).play != "wyvern_rouse"
    ):
        raise WorkflowError("This genuine physical Frame must have actually become Roused first")
    source = prove_source(game, c, state, roused.session)
    original = next(
        (
            x
            for x in rules.records(_history(c, game, roused.event), rules.Roused)
            if x.id == roused.id
        ),
        None,
    )
    if (
        source.total < 8
        or source.actor != roused.actor
        or source.frame != roused.frame
        or roused.id != rules.identity("roused", source.id)
        or original is None
        or original.use is not None
        or original.model_copy(update={"use": use.id}) != roused
    ):
        raise WorkflowError("Prove this actual successful original Roused birth before spending it")
    if use.event != event or use not in rules.records(state, rules.RousedUse):
        raise WorkflowError("Stage this exact current-event consumed-Roused effect first")


def prove_cargo(game: GameService, c: Connection, state: GameState, identity: str) -> rules.Cargo:
    value = next((x for x in rules.records(state, rules.Cargo) if x.id == identity), None)
    if value is None or not value.accepted_event:
        raise WorkflowError("Recover the actual original Frame cargo authorization")
    saved = _history(c, game, value.accepted_event)
    if value.id not in {x.id for x in rules.records(saved, rules.Cargo)}:
        raise WorkflowError("The actual cargo owner must authorize this original physical Frame")
    return value


def prove_shield(game: GameService, c: Connection, state: GameState, identity: str) -> rules.Shield:
    value = next((x for x in rules.records(state, rules.Shield) if x.id == identity), None)
    if value is None:
        raise WorkflowError("Recover the actual original protected person and Shield source")
    source = prove_source(game, c, state, value.session)
    if (
        source.play != "wyvern_protector"
        or source.total < 8
        or source.target != value.target
        or source.frame != value.frame
        or source.actor != value.actor
        or value.id != rules.identity("shield", source.id)
        or value.event != source.event
        or value.high != (source.total >= 11)
        or value.target_vessel
        != game.action(c, source.id)["data"]["wyvern"]["sourcefacts"].get("target_vessel")
    ):
        raise WorkflowError("Shielded requires the actual original successful Protector")
    original = next(
        (
            x
            for x in rules.records(_history(c, game, value.event), rules.Shield)
            if x.id == value.id
        ),
        None,
    )
    if (
        original is None
        or original.ended_event
        or original.model_copy(update={"ended_event": value.ended_event}) != value
    ):
        raise WorkflowError("Preserve this original Shield's actual immutable canonical birth")
    return value


def prove_wraith(game: GameService, c: Connection, state: GameState, identity: str) -> rules.Wraith:
    value = next((x for x in rules.records(state, rules.Wraith) if x.id == identity), None)
    if (
        value is None
        or value.profile != "frame_bound_npc"
        or not value.rules_answer
        or not value.rules_event
    ):
        raise WorkflowError("Recover the actual Handler-defined original Frame mind")
    source = prove_source(game, c, state, value.session)
    if source.play != "wyvern_wraith" or source.frame != value.frame or source.wraith != value.id:
        raise WorkflowError("This actual original mind needs its genuine unleashing source")
    return value


def _text(value: str, limit: int = 2000) -> str:
    if not value.strip() or len(value) > limit:
        raise WorkflowError("Provide the actual source account within its saved text limit")
    return value


def _controlled(
    game: GameService, c: Connection, state: GameState, viewer: GuildViewer, actor: ActorRef
) -> None:
    if resolve(state, actor, profiles(c, game.store.campaign_id)).controller != viewer.user_id:
        raise WorkflowError("Only the actual original role's human controls that response")


def prepare_child(
    game: GameService,
    c: Connection,
    viewer: GuildViewer,
    state: GameState,
    prepared: PlayInput,
    channel: int,
) -> dict[str, Any] | None:
    danger = next(
        (x for x in rules.records(state, rules.Danger) if x.id == prepared.source_work), None
    )
    if danger is None:
        return None
    source = prove_source(game, c, state, danger.session)
    parent = game.action(c, source.id)
    scene = _cast(game, c, state, channel)
    if (
        danger.kind != "escape"
        or danger.child
        or danger.returned_event
        or not source.answers_closed_event
        or prepared.parent != source.id
        or int(parent["channel_id"]) != channel
        or fingerprint(scene) != fingerprint(source.cast)
        or not prepared.trigger_confirmed
        or not prepared.context.strip()
    ):
        raise WorkflowError("Perform the actual still-owed escape in the original Frame scene")
    _controlled(game, c, state, viewer, source.actor)
    guest = next(
        (
            x
            for x in rules.records(state, rules.InteriorGuest)
            if x.id == rules.identity("interior", source.id, source.actor.token)
            and x.session == source.id
            and x.actor == source.actor
            and x.frame == source.frame
            and not x.ended_event
        ),
        None,
    )
    actual = resolve(state, source.actor, profiles(c, game.store.campaign_id))
    if (
        guest is None
        or not actual.inside_frame
        or actual.occupied_frame_instance != source.frame
        or actual.vessel_id != json.loads(guest.original_pose).get("vessel_id")
        or actual.offstage_source
    ):
        raise WorkflowError("Escape with the actual original body still inside this source Frame")
    row = next(
        (
            x
            for x in game.pending(c, source.id)
            if x["kind"] == "wyvern_child" and x["actor_id"] == source.actor.entity
        ),
        None,
    )
    if row is None:
        raise WorkflowError("Recover the exact original pending escape performance")
    return dict(
        id=danger.id,
        parent=source.id,
        choice=row["id"],
        actor=source.actor.model_dump(mode="json"),
        handler=source.handler.model_dump(mode="json"),
        handler_controller=source.handler_controller,
        frame=source.frame,
        vessel=actual.vessel_id,
        position=actual.position_sha256,
        cell=list(actual.cell) if actual.cell is not None else None,
        cast=scene.model_dump(mode="json"),
        cast_sha256=fingerprint(scene),
        table=sorted(
            {x.controller for x in scene.roles}
            | ({scene.facilitator} if scene.facilitator is not None else set())
        ),
    )


def bind_child(
    game: GameService, c: Connection, state: GameState, action: dict[str, Any], event: str
) -> None:
    value = next(
        x
        for x in rules.records(state, rules.Danger)
        if x.id == action["data"]["wyvern_child"]["id"]
    )
    if value.child or value.returned_event:
        raise WorkflowError("Resume this actual already-bound escape")
    rules.put(state, value.model_copy(update={"child": action["id"]}))


def pre_roll_child(
    game: GameService,
    c: Connection,
    viewer: GuildViewer,
    state: GameState,
    action: dict[str, Any],
) -> None:
    metadata = action["data"]["wyvern_child"]
    danger = next(x for x in rules.records(state, rules.Danger) if x.id == metadata["id"])
    if danger.child != action["id"] or danger.child_completed_event or danger.returned_event:
        raise WorkflowError("Preserve the exact original pending escape reservation")
    rules.put(state, danger.model_copy(update={"child": None}))
    try:
        expected = prepare_child(
            game,
            c,
            viewer,
            state,
            PlayInput.model_validate(action["data"]["prepared"]),
            int(action["channel_id"]),
        )
    finally:
        rules.put(state, danger)
    if expected != metadata:
        raise WorkflowError("Reopen the actual unchanged escape body, Frame, cast and source")


def release_unrolled(
    game: GameService, c: Connection, state: GameState, action: dict[str, Any], event: str
) -> None:
    if action["data"].get("receipt") or c.scalar(
        sa.select(t.m2["m2_receipts"].c.action_id).where(
            t.m2["m2_receipts"].c.campaign_id == game.store.campaign_id,
            t.m2["m2_receipts"].c.action_id == action["id"],
        )
    ):
        raise WorkflowError("Release only an actual unrolled cancelled source reservation")
    meta = action["data"].get("wyvern_child")
    if meta:
        value = next(x for x in rules.records(state, rules.Danger) if x.id == meta["id"])
        if value.child != action["id"] or value.child_completed_event:
            raise WorkflowError("Preserve the actual original escape reservation")
        rules.put(state, value.model_copy(update={"child": None}))
    meta = action["data"].get("wyvern")
    if meta and meta.get("party"):
        party = next(x for x in rules.records(state, rules.Party) if x.id == meta["party"])
        if party.bound_action != action["id"]:
            raise WorkflowError("Preserve the actual original exploration reservation")
        rules.put(state, party.model_copy(update={"bound_action": None}))


def complete_child(
    game: GameService, c: Connection, state: GameState, action: dict[str, Any], event: str
) -> None:
    meta = action["data"].get("wyvern_child")
    if not meta:
        return
    danger = next(x for x in rules.records(state, rules.Danger) if x.id == meta["id"])
    if danger.child_completed_event:
        return
    if (
        danger.child != action["id"]
        or action["state"] != "complete"
        or not action["data"].get("receipt")
        or not action["data"].get("result")
    ):
        raise WorkflowError("Complete the genuine escape Play, its costs and actual effects first")
    human = c.scalar(
        sa.select(t.events.c.actor_id).where(
            t.events.c.campaign_id == game.store.campaign_id, t.events.c.id == event
        )
    )
    if human is None:
        raise WorkflowError("Preserve the actual committed human escape event")
    source = prove_source(game, c, state, danger.session)
    completed = str(uuid4())
    rules.put(state, danger.model_copy(update={"child_completed_event": completed}))
    choices = t.m2["m2_choices"]
    row = (
        c.execute(
            sa.select(choices).where(
                choices.c.campaign_id == game.store.campaign_id, choices.c.id == meta["choice"]
            )
        )
        .mappings()
        .one()
    )
    if (
        row["kind"] != "wyvern_child"
        or row["actor_id"] != source.actor.entity
        or row["state"] != "pending"
    ):
        raise WorkflowError("Close only the original exact escape work row")
    c.execute(
        choices.update()
        .where(choices.c.campaign_id == game.store.campaign_id, choices.c.id == row["id"])
        .values(state="completed_by_work", revision=row["revision"] + 1)
    )
    parent = game.action(c, source.id)
    _return(game, c, state, parent, source, completed, child_action=action["id"])
    game.event(
        c,
        int(human),
        str(uuid4()),
        "m3.wyvern_escaped",
        state,
        event_id=completed,
        action_id=source.id,
        child_action=action["id"],
        source_event=event,
    )
    game.save_action(c, parent)
    synchronize(game, c, parent, completed)


def big_enough(state: GameState, actor: ActorRef) -> bool:
    try:
        original = rules.frame(state, actor)
        own = resolve(state, actor, rules.bindings(state), require_current_profile=False)
        return bool(own.piloting and own.occupied_frame_instance == original)
    except (ValueError, KeyError):
        return False


def stage_unlink(
    game: GameService,
    c: Connection,
    before: GameState,
    after: GameState,
    actor: ActorRef,
    event: str,
) -> None:
    bound = profiles(c, game.store.campaign_id)
    try:
        old = resolve(before, actor, bound, require_alive=False, require_current_profile=False)
        new = resolve(after, actor, bound, require_alive=False, require_current_profile=False)
    except ValueError:
        return
    for source in rules.records(after, rules.Last):
        if (
            source.actor == actor
            and not source.unlinked_event
            and old.occupied_frame_instance == source.frame
            and old.piloting
            and (not new.piloting or new.occupied_frame_instance != source.frame)
        ):
            rules.put(after, source.model_copy(update={"unlinked_event": event}))


class WyvernService:
    def __init__(self, game: GameService):
        self.game, self.store = game, game.store

    def _write(
        self,
        viewer: GuildViewer,
        key: str,
        kind: str,
        request: dict[str, Any],
        revision: int,
        operation: Callable[[Connection, GameState, str], dict[str, Any]],
    ) -> dict[str, Any]:
        def run(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            if state.revision != revision:
                raise WorkflowError("Reopen the current saved source before changing it")
            event = str(uuid4())
            result = operation(c, state, event)
            self.game.event(c, viewer.user_id, key, kind, state, event_id=event, **result)
            if kind == "m3.wyvern_roused_used":
                from girlframe.services.m3_battle import synchronize_damage

                synchronize_damage(self.game, c, event)
            from girlframe.services.m3_wyvern_support import synchronize as sync_effects

            sync_effects(self.game, c, event)
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

    def menu(self, viewer: GuildViewer, channel: int) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            authorize(self.game, c, viewer)
            state = load_state(c, self.store.campaign_id)
            actor = current_ref(state, viewer.user_id)
            require_rule(self.game, c, state, actor, rules.BEAST)
            scene = _cast(self.game, c, state, channel)
            _context(self.game, c, state, actor, scene, "wyvern_explore")
            bound = profiles(c, self.store.campaign_id)
            return dict(
                revision=state.revision,
                sheet_revision=state.sheets[actor.entity].revision,
                actor=actor.model_dump(mode="json"),
                frame=rules.frame(state, actor),
                heat=state.sheets[actor.entity].heat,
                identities=[
                    (x.id, x.name) for x in state.sheets[actor.entity].identities if not x.marked
                ],
                targets=[
                    dict(
                        ref=x.actor.model_dump(mode="json"),
                        token=x.actor.token,
                        label=resolve(state, x.actor, bound).label,
                    )
                    for x in scene.roles
                    if x.actor != actor
                ],
                plays=[
                    (play, rule)
                    for play, rule in rules.PLAYS.items()
                    if rule not in rules.REQUISITIONS or rules.held(state, actor, rule)
                ],
                girl_replacements=[
                    (x.id, x.name)
                    for x in resolve(state, actor, bound).assets
                    if x.family == "girl" and x.can_replace_at_limit is not False
                ],
                requisitions=[
                    dict(id=x, held=rules.held(state, actor, x) is not None)
                    for x in rules.REQUISITIONS
                ],
                roused=(condition.id if (condition := rules.roused(state, actor)) else None),
                tasks=_tasks(self.game, c, state, viewer),
            )

    def party(
        self,
        viewer: GuildViewer,
        key: str,
        channel: int,
        revision: int,
        companions: tuple[ActorRef, ...],
    ) -> dict[str, Any]:
        def operation(c: Connection, state: GameState, event: str) -> dict[str, Any]:
            RequisitionService(self.game)._safe(c, state, viewer.user_id)
            actor = current_ref(state, viewer.user_id)
            require_rule(self.game, c, state, actor, rules.BEAST)
            scene = _cast(self.game, c, state, channel)
            if len(set(companions)) != len(companions) or actor in companions:
                raise WorkflowError("Declare distinct actual companion roles")
            for ref in (actor, *companions):
                _context(
                    self.game,
                    c,
                    state,
                    actor,
                    scene,
                    "wyvern_explore",
                    ref if ref != actor else None,
                )
            from girlframe.services.m3_wyvern_support import exploration_party

            exploration_party(self.game, c, state, actor, scene, companions)
            present = tuple(
                ref
                for ref in (actor, *companions)
                if resolve(state, ref, profiles(c, self.store.campaign_id)).controller
                == viewer.user_id
            )
            identity = str(uuid4())
            rules.put(
                state,
                rules.Party(
                    id=identity,
                    actor=actor,
                    frame=rules.frame(state, actor),
                    cast=scene,
                    companions=companions,
                    event=event,
                    present=present,
                    attendance_events={x.token: event for x in present},
                ),
            )
            return dict(id=identity)

        return self._write(
            viewer,
            key,
            "m3.wyvern_party_declared",
            dict(channel=channel, companions=[x.model_dump(mode="json") for x in companions]),
            revision,
            operation,
        )

    def attend(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        actors: tuple[ActorRef, ...],
    ) -> dict[str, Any]:
        def operation(c: Connection, state: GameState, event: str) -> dict[str, Any]:
            party = next(x for x in rules.records(state, rules.Party) if x.id == identity)
            if (
                party.bound_action
                or party.cancelled_event
                or not actors
                or len(set(actors)) != len(actors)
                or any(x not in party.companions for x in actors)
            ):
                raise WorkflowError("Attend only your genuine pending companion roles")
            for actor in actors:
                _controlled(self.game, c, state, viewer, actor)
                _context(self.game, c, state, party.actor, party.cast, "wyvern_explore", actor)
            rules.put(
                state,
                party.model_copy(
                    update={
                        "present": tuple(dict.fromkeys((*party.present, *actors))),
                        "attendance_events": dict(
                            party.attendance_events, **{x.token: event for x in actors}
                        ),
                    }
                ),
            )
            return dict(id=identity)

        return self._write(
            viewer,
            key,
            "m3.wyvern_party_attended",
            dict(id=identity, actors=[x.model_dump(mode="json") for x in actors]),
            revision,
            operation,
        )

    def answer(
        self, viewer: GuildViewer, key: str, identity: str, revision: int, text: str
    ) -> dict[str, Any]:
        actual = _text(text, 8000)

        def operation(c: Connection, state: GameState, event: str) -> dict[str, Any]:
            question = next(x for x in rules.records(state, rules.Question) if x.id == identity)
            source = prove_source(self.game, c, state, question.session)
            if (
                viewer.user_id not in question.table
                or question.closed_event
                or source.answers_closed_event
            ):
                raise WorkflowError(
                    "Only the original actual table contributes to this still-open Frame question"
                )
            answer = str(uuid4())
            rules.put(
                state,
                rules.Answer(
                    id=answer, question=identity, author=viewer.user_id, text=actual, event=event
                ),
            )
            return dict(id=answer, question=identity)

        return self._write(
            viewer,
            key,
            "m3.wyvern_frame_answered",
            dict(question=identity, text=actual),
            revision,
            operation,
        )

    def elapsed(
        self, viewer: GuildViewer, key: str, identity: str, revision: int, account: str
    ) -> dict[str, Any]:
        actual = _text(account)

        def operation(c: Connection, state: GameState, event: str) -> dict[str, Any]:
            danger = next(x for x in rules.records(state, rules.Danger) if x.id == identity)
            source = prove_source(self.game, c, state, danger.session)
            if (
                danger.kind != "delay"
                or danger.returned_event
                or danger.elapsed_event
                or not source.answers_closed_event
                or viewer.user_id != source.handler_controller
                or state.handler != source.handler_controller
                or active_handler(state) != source.handler
            ):
                raise WorkflowError(
                    "The actual original Handler records elapsed source time before safe return"
                )
            rules.put(state, danger.model_copy(update={"elapsed_event": event}))
            action = self.game.action(c, source.id)
            _return(self.game, c, state, action, source, event, elapsed_fact=actual)
            self.game.save_action(c, action)
            return dict(id=identity, account=actual, action_id=source.id)

        result = self._write(
            viewer,
            key,
            "m3.wyvern_time_elapsed",
            dict(id=identity, account=actual),
            revision,
            operation,
        )
        self.resume(viewer, identity)
        return result

    def resume(self, viewer: GuildViewer, identity: str) -> None:
        # The preceding durable operation owns the factual event. No new player answer.
        with self.store.transaction() as c:
            authorize(self.game, c, viewer)
            state = load_state(c, self.store.campaign_id)
            danger = next((x for x in rules.records(state, rules.Danger) if x.id == identity), None)
            if danger and danger.returned_event:
                source = prove_source(self.game, c, state, danger.session)
                synchronize(self.game, c, self.game.action(c, source.id), danger.returned_event)

    def roused_options(self, viewer: GuildViewer, channel: int) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            authorize(self.game, c, viewer)
            state = load_state(c, self.store.campaign_id)
            actor = current_ref(state, viewer.user_id)
            require_rule(self.game, c, state, actor, rules.BURDEN)
            scene = _cast(self.game, c, state, channel)
            _context(self.game, c, state, actor, scene, "wyvern_rouse")
            if rules.roused(state, actor) is None:
                raise WorkflowError("This actual Frame is not Roused")
            options = []
            for role in scene.roles:
                if role.actor == actor:
                    continue
                try:
                    _context(self.game, c, state, actor, scene, "wyvern_rouse", role.actor)
                except (ValueError, WorkflowError):
                    continue
                target = resolve(state, role.actor, profiles(c, self.store.campaign_id))
                options.append(
                    dict(
                        id=rules.identity("pin-option", role.actor.token),
                        label="Pin " + target.label,
                        target=role.actor.model_dump(mode="json"),
                        kind="pin",
                    )
                )
                for asset in target.assets:
                    if not asset.damaged:
                        options.append(
                            dict(
                                id=rules.identity("strike-option", role.actor.token, asset.id),
                                label="Strike " + target.label + ": " + asset.name,
                                target=role.actor.model_dump(mode="json"),
                                kind="strike",
                                asset=asset.id,
                            )
                        )
            actions = t.m2["m2_actions"]
            for row in c.execute(
                sa.select(actions).where(
                    actions.c.campaign_id == self.store.campaign_id,
                    actions.c.state.notin_(("complete", "aborted")),
                )
            ).mappings():
                action = self.game.action(c, row["id"])
                prepared = PlayInput.model_validate(action["data"]["prepared"])
                if int(action["channel_id"]) != channel or not (
                    prepared.target_actor == actor or prepared.target == int(actor.entity)
                ):
                    continue
                actual_actor = action["data"].get("tag_context", {}).get("actor")
                incarnation = action["data"].get("character_ids", {}).get(str(action["actor_id"]))
                other = (
                    ActorRef.model_validate(actual_actor)
                    if actual_actor
                    else ActorRef(
                        kind="pilot", entity=str(action["actor_id"]), incarnation=incarnation
                    )
                    if incarnation
                    else None
                )
                if (
                    other is None
                    or other == actor
                    or not any(x.actor == other for x in scene.roles)
                ):
                    continue
                options.append(
                    dict(
                        id=rules.identity("deflect-option", action["id"]),
                        label="Too big for " + action["data"]["play"],
                        target=other.model_dump(mode="json"),
                        kind="too_big",
                        incoming=action["id"],
                    )
                )
            from girlframe.services.m3_wyvern_combat import parked_strike_options

            options.extend(parked_strike_options(self.game, c, state, actor, scene))
            return dict(revision=state.revision, options=options)

    def use_roused(
        self,
        viewer: GuildViewer,
        key: str,
        channel: int,
        revision: int,
        target: ActorRef,
        kind: Literal["strike", "too_big", "pin"],
        *,
        asset: str | None = None,
        target_frame: str | None = None,
        incoming: str | None = None,
    ) -> dict[str, Any]:
        def operation(c: Connection, state: GameState, event: str) -> dict[str, Any]:
            from girlframe.services.m3_wyvern_support import roused_effect

            actor = current_ref(state, viewer.user_id)
            require_rule(self.game, c, state, actor, rules.BURDEN)
            scene = _cast(self.game, c, state, channel)
            _context(
                self.game,
                c,
                state,
                actor,
                scene,
                "wyvern_rouse",
                target if target_frame is None else None,
            )
            condition = rules.roused(state, actor)
            if (
                condition is None
                or kind not in ("strike", "too_big", "pin")
                or (kind == "strike") != bool(asset)
                or (kind == "too_big") != bool(incoming)
                or target_frame is not None
                and kind != "strike"
            ):
                raise WorkflowError("Choose one actual available use of the original Roused Frame")
            if target_frame is not None:
                from girlframe.services.m3_wyvern_combat import parked_strike_options

                if not any(
                    row["target"] == target.model_dump(mode="json")
                    and row["target_frame"] == target_frame
                    and row["asset"] == asset
                    for row in parked_strike_options(self.game, c, state, actor, scene)
                ):
                    raise WorkflowError("Choose the actual disclosed vacant original Frame Asset")
            identity = str(uuid4())
            value = rules.RousedUse(
                id=identity,
                actor=actor,
                frame=condition.frame,
                roused=condition.id,
                target=target,
                kind=kind,
                cast=scene,
                event=event,
                asset=asset,
                target_frame=target_frame,
                incoming=incoming,
            )
            rules.spend_roused(state, value)
            validate_pending_use(self.game, c, state, value, event)
            changed, work = roused_effect(self.game, c, state, value, event)
            _copy(state, changed)
            rules.put(
                state,
                value.model_copy(update={"work": work, "completed_event": None if work else event}),
            )
            return dict(id=identity)

        return self._write(
            viewer,
            key,
            "m3.wyvern_roused_used",
            dict(
                channel=channel,
                target=target.model_dump(mode="json"),
                kind=kind,
                asset=asset,
                incoming=incoming,
                **(dict(target_frame=target_frame) if target_frame is not None else {}),
            ),
            revision,
            operation,
        )

    def purchase(
        self,
        viewer: GuildViewer,
        key: str,
        revision: int,
        rule: str,
        account: str,
        *,
        questions: tuple[str, str] | None = None,
        room: str | None = None,
        kind: Literal["contraband", "past", "void"] | None = None,
        name: str | None = None,
        description: str | None = None,
        replace: str | None = None,
    ) -> dict[str, Any]:
        actual = _text(account, 1200)

        def operation(c: Connection, state: GameState, event: str) -> dict[str, Any]:
            from girlframe.services.m3_wyvern_support import renovate

            Access(self.store).authorize(c, viewer, "economy")
            RequisitionService(self.game)._safe(c, state, viewer.user_id)
            actor = current_ref(state, viewer.user_id)
            original = rules.frame(state, actor)
            registry = Access(self.store).registry
            if registry is None or rule not in rules.REQUISITIONS:
                raise WorkflowError("Choose a genuine printed Wyvern Requisition")
            registry.require_available(rule)
            if rule != rules.RENOVATE and rules.held(state, actor, rule):
                raise WorkflowError("Restore the actual owned source rather than paying twice")
            if available(state, actor) < 2:
                raise WorkflowError("This actual Frame acquisition costs two Permissions")
            identity = str(uuid4())
            payment = prepare_payment(self.game, c, state, viewer, actor, rule, 2, rules.FRAME)
            debit(state, actor, 2, event=event, source=identity, payment=payment)
            state.sheets[actor.entity].revision += 1
            receipt = FrameRuleReceipt(
                id=identity,
                kind="ability_unlock",
                actor=actor,
                frame_instance=original,
                frame=rules.FRAME,
                donor_frame=rules.FRAME,
                rule_id=rule,
                grant="wyvern:" + identity,
                price=2,
                account=actual,
                source_event=event,
            )
            state.requisitions.append(receipt)
            result: dict[str, Any] = dict(
                id=identity, requisition_id=identity, rule_id=rule, cost=2
            )
            if rule == rules.DEEP:
                if questions is None or len(questions) != 2 or len(set(questions)) != 2:
                    raise WorkflowError("Author exactly two distinct new Frame questions")
                texts = tuple(_text(x, 1000) for x in questions)
                if len(set(texts)) != 2 or any(
                    x in rules.questions(state, actor).values() for x in texts
                ):
                    raise WorkflowError(
                        "Add actual new questions rather than duplicate existing questions"
                    )
                rules.put(
                    state,
                    rules.DeepQuestions(
                        id=identity,
                        actor=actor,
                        frame=original,
                        receipt=identity,
                        questions=cast(tuple[str, str], texts),
                        event=event,
                    ),
                )
            elif questions is not None:
                raise WorkflowError("Only Deep Exploration adds actual Frame questions")
            if rule == rules.RENOVATE:
                handler = active_handler(state)
                if (
                    handler is None
                    or state.handler is None
                    or kind not in ("contraband", "past", "void")
                ):
                    raise WorkflowError(
                        "Preserve the actual original Handler and printed object choice"
                    )
                value = rules.Renovation(
                    id=identity,
                    actor=actor,
                    frame=original,
                    receipt=identity,
                    handler=handler,
                    handler_controller=state.handler,
                    room=_text(room or "", 500),
                    kind=kind,
                    name=_text(name or "", 120),
                    description=_text(description or "", 1200),
                    replace=replace,
                    event=event,
                )
                rules.put(state, value)
                if kind != "past":
                    changed, work = renovate(self.game, c, state, value, event)
                    _copy(state, changed)
                    current = next(
                        x for x in rules.records(state, rules.Renovation) if x.id == value.id
                    )
                    rules.put(
                        state,
                        current.model_copy(
                            update={"work": work, "completed_event": None if work else event}
                        ),
                    )
            elif any(x is not None for x in (room, kind, name, description, replace)):
                raise WorkflowError("Only Renovation chooses a real room and found Girl Asset")
            return result

        return self._write(
            viewer,
            key,
            "m3.ability_unlock_purchased",
            dict(
                rule=rule,
                account=actual,
                questions=questions,
                room=room,
                kind=kind,
                name=name,
                description=description,
                replace=replace,
            ),
            revision,
            operation,
        )

    def past_answer(
        self, viewer: GuildViewer, key: str, identity: str, revision: int, answer: str
    ) -> dict[str, Any]:
        actual = _text(answer, 2000)

        def operation(c: Connection, state: GameState, event: str) -> dict[str, Any]:
            from girlframe.services.m3_wyvern_support import renovate

            value = next(x for x in rules.records(state, rules.Renovation) if x.id == identity)
            receipt = next(
                x
                for x in state.requisitions
                if isinstance(x, FrameRuleReceipt) and x.id == value.receipt
            )
            prove_acquisition(self.game, c, state, receipt)
            if (
                value.kind != "past"
                or value.answered_event
                or viewer.user_id != value.handler_controller
                or active_handler(state) != value.handler
                or state.handler != value.handler_controller
            ):
                raise WorkflowError(
                    "Only the original Handler answers about the real object from their past"
                )
            RequisitionService(self.game)._safe(c, state, int(value.actor.entity))
            value = value.model_copy(update={"answer": actual, "answered_event": event})
            rules.put(state, value)
            changed, work = renovate(self.game, c, state, value, event)
            _copy(state, changed)
            current = next(x for x in rules.records(state, rules.Renovation) if x.id == identity)
            rules.put(
                state,
                current.model_copy(
                    update={"work": work, "completed_event": None if work else event}
                ),
            )
            return dict(id=identity)

        return self._write(
            viewer,
            key,
            "m3.wyvern_past_answered",
            dict(id=identity, answer=actual),
            revision,
            operation,
        )

    def propose_cargo(
        self, viewer: GuildViewer, key: str, channel: int, revision: int, owner: ActorRef
    ) -> dict[str, Any]:
        def operation(c: Connection, state: GameState, event: str) -> dict[str, Any]:
            actor = current_ref(state, viewer.user_id)
            require_rule(self.game, c, state, actor, rules.CHASSIS)
            scene = _cast(self.game, c, state, channel)
            _context(self.game, c, state, actor, scene, "wyvern_rouse")
            target = resolve(state, owner, profiles(c, self.store.campaign_id))
            if (
                owner == actor
                or not any(role.actor == owner for role in scene.roles)
                or target.frame_instance is None
                or target.frame_scrapped
                or target.frame_cell
                != tuple(_context(self.game, c, state, actor, scene, "wyvern_rouse")["cell"])
            ):
                raise WorkflowError(
                    "Carry another genuine co-present Vital Frame, "
                    "with its real owner's authorization"
                )
            if rules.cargo(state, owner, target.frame_instance):
                raise WorkflowError("This actual physical Frame is already carried")
            identity = str(uuid4())
            rules.put(
                state,
                rules.Cargo(
                    id=identity,
                    actor=actor,
                    frame=rules.frame(state, actor),
                    owner=owner,
                    guest_frame=target.frame_instance,
                    event=event,
                ),
            )
            return dict(id=identity)

        return self._write(
            viewer,
            key,
            "m3.wyvern_cargo_proposed",
            dict(channel=channel, owner=owner.model_dump(mode="json")),
            revision,
            operation,
        )

    def accept_cargo(
        self, viewer: GuildViewer, key: str, identity: str, revision: int
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            from girlframe.services.m3_wyvern_support import carry

            self.game.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            value = next(x for x in rules.records(state, rules.Cargo) if x.id == identity)
            _controlled(self.game, c, state, viewer, value.owner)
            if state.revision != revision or value.accepted_event or value.ended_event:
                raise WorkflowError("Reopen the actual still-pending physical Frame carriage")
            event = str(uuid4())
            value = value.model_copy(update={"accepted_event": event})
            rules.put(state, value)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.wyvern_cargo_accepted",
                state,
                event_id=event,
                cargo=identity,
            )
            boarded = str(uuid4())
            changed, work = carry(self.game, c, state, value, boarded)
            _copy(state, changed)
            if work:
                raise WorkflowError(
                    "CARGO_FOLLOWUP_ADAPTER_REQUIRED: preserve real cargo completion work"
                )
            rules.put(state, value.model_copy(update={"boarded_event": boarded}))
            self.game.event(
                c,
                viewer.user_id,
                str(uuid4()),
                "m3.wyvern_cargo_boarded",
                state,
                event_id=boarded,
                cargo=identity,
                source_event=event,
            )
            return dict(id=identity, revision=state.revision)

        return self.store._write(
            viewer,
            key,
            "m3.wyvern_cargo_accepted",
            dict(id=identity, revision=revision),
            operation,
            auto_audit=False,
            authorize=lambda c: authorize(self.game, c, viewer),
        )

    def unload(self, viewer: GuildViewer, key: str, identity: str, revision: int) -> dict[str, Any]:
        def operation(c: Connection, state: GameState, event: str) -> dict[str, Any]:
            from girlframe.services.m3_wyvern_support import carry

            value = prove_cargo(self.game, c, state, identity)
            own = resolve(
                state,
                value.actor,
                profiles(c, self.store.campaign_id),
                require_current_profile=False,
            )
            guest = resolve(
                state,
                value.owner,
                profiles(c, self.store.campaign_id),
                require_current_profile=False,
            )
            if (
                viewer.user_id not in (own.controller, guest.controller)
                or value.ended_event
                or not value.boarded_event
            ):
                raise WorkflowError(
                    "Only an actual original carrier or cargo owner unloads this held Frame"
                )
            changed, work = carry(self.game, c, state, value, event, unload=True)
            _copy(state, changed)
            if work:
                raise WorkflowError(
                    "CARGO_FOLLOWUP_ADAPTER_REQUIRED: preserve real cargo completion work"
                )
            rules.put(state, value.model_copy(update={"ended_event": event}))
            return dict(id=identity)

        return self._write(
            viewer, key, "m3.wyvern_cargo_unloaded", dict(id=identity), revision, operation
        )

    def voice(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        text: str,
        *,
        take_control: bool = False,
    ) -> dict[str, Any]:
        actual = _text(text, 8000)

        def operation(c: Connection, state: GameState, event: str) -> dict[str, Any]:
            from girlframe.services.m3_wyvern_support import voice_control

            value = prove_wraith(self.game, c, state, identity)
            if viewer.user_id not in value.table or not value.active or value.ended_event:
                raise WorkflowError(
                    "An actual original table human plays this active original Frame mind"
                )
            if take_control:
                changed, persona = voice_control(self.game, c, state, value, viewer.user_id, event)
                _copy(state, changed)
                value = value.model_copy(update={"controller": viewer.user_id, "persona": persona})
                rules.put(state, value)
            authored = str(uuid4())
            rules.put(
                state,
                rules.Voice(
                    id=authored, wraith=identity, author=viewer.user_id, text=actual, event=event
                ),
            )
            return dict(id=identity, voice=authored)

        return self._write(
            viewer,
            key,
            "m3.wyvern_mind_played",
            dict(id=identity, text=actual, take_control=take_control),
            revision,
            operation,
        )

    def dismiss(
        self, viewer: GuildViewer, key: str, identity: str, revision: int
    ) -> dict[str, Any]:
        def operation(c: Connection, state: GameState, event: str) -> dict[str, Any]:
            from girlframe.services.m3_wyvern_support import end_wraith

            value = prove_wraith(self.game, c, state, identity)
            _controlled(self.game, c, state, viewer, value.actor)
            if value.stubborn or not value.active or value.ended_event:
                raise WorkflowError("This actual mind cannot be dismissed, or is already done")
            changed, work = end_wraith(self.game, c, state, value, event)
            _copy(state, changed)
            if work:
                raise WorkflowError(
                    "WRAITH_ENDING_WORK_REQUIRED: complete actual source ending work"
                )
            rules.put(state, value.model_copy(update={"active": False, "ended_event": event}))
            return dict(id=identity)

        return self._write(
            viewer, key, "m3.wyvern_mind_dismissed", dict(id=identity), revision, operation
        )

    def approach(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        actor: ActorRef,
        account: str,
    ) -> dict[str, Any]:
        actual = _text(account)

        def operation(c: Connection, state: GameState, event: str) -> dict[str, Any]:
            value = prove_shield(self.game, c, state, identity)
            _controlled(self.game, c, state, viewer, actor)
            target = resolve(state, value.target, profiles(c, self.store.campaign_id))
            approaching = resolve(state, actor, profiles(c, self.store.campaign_id))
            if (
                not value.high
                or value.ended_event
                or actor in (value.actor, value.target)
                or target.cell is None
                or approaching.cell != target.cell
            ):
                raise WorkflowError(
                    "Declare an actual co-present approach to this still-protected person"
                )
            approach_id = str(uuid4())
            rules.put(
                state,
                rules.Approach(
                    id=approach_id,
                    shield=value.id,
                    actor=actor,
                    controller=viewer.user_id,
                    event=event,
                ),
            )
            state.facts.append(
                dict(kind="wyvern_approach_account", id=approach_id, event=event, body=actual)
            )
            return dict(id=approach_id)

        return self._write(
            viewer,
            key,
            "m3.wyvern_approached",
            dict(shield=identity, actor=actor.model_dump(mode="json"), account=actual),
            revision,
            operation,
        )

    def give_up(
        self, viewer: GuildViewer, key: str, identity: str, revision: int, *, tag: str | None = None
    ) -> dict[str, Any]:
        def operation(c: Connection, state: GameState, event: str) -> dict[str, Any]:
            value = next(x for x in rules.records(state, rules.Approach) if x.id == identity)
            shield = prove_shield(self.game, c, state, value.shield)
            _controlled(self.game, c, state, viewer, value.actor)
            if viewer.user_id != value.controller or value.gave_up_event or shield.ended_event:
                raise WorkflowError("Only the actual original approacher chooses to give up")
            if tag is not None:
                source = prove_source(self.game, c, state, shield.session)
                _copy(
                    state,
                    give_tag(
                        state,
                        profiles(c, self.store.campaign_id),
                        shield.actor,
                        value.actor,
                        _text(tag, 120),
                        event,
                        event,
                        tuple({x.controller for x in source.cast.roles}),
                    ),
                )
            rules.put(
                state,
                value.model_copy(update={"gave_up_event": event, "tag": event if tag else None}),
            )
            return dict(id=identity)

        return self._write(
            viewer,
            key,
            "m3.wyvern_approach_abandoned",
            dict(id=identity, tag=tag),
            revision,
            operation,
        )

    def view(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            authorize(self.game, c, viewer)
            state = load_state(c, self.store.campaign_id)
            source = next((x for x in rules.all_records(state) if x.id == identity), None)
            if source is None:
                raise WorkflowError("Recover the actual saved Wyvern source")
            audience = _audience(self.game, c, state, source)
            if viewer.user_id not in audience:
                approachers = _approachers(self.game, c, state, viewer, source)
                if not approachers:
                    raise WorkflowError("This saved source belongs to its actual private audience")
                # A present newcomer can approach, not read the original private scene.
                return dict(
                    id=identity,
                    kind=rules.KINDS[type(source)],
                    revision=state.revision,
                    source=dict(high=True, ended_event=None),
                    approachers=approachers,
                )
            result: dict[str, Any] = dict(
                id=identity,
                kind=rules.KINDS[type(source)],
                revision=state.revision,
                source=source.model_dump(mode="json"),
            )
            bound = profiles(c, self.store.campaign_id)
            result["labels"] = {
                name: resolve(
                    state, ref, bound, require_alive=False, require_current_profile=False
                ).label
                for name in ("actor", "target", "owner", "carrier")
                if isinstance(ref := getattr(source, name, None), ActorRef)
            }
            session = (
                source
                if isinstance(source, rules.Session)
                else next(
                    (
                        x
                        for x in rules.records(state, rules.Session)
                        if getattr(source, "session", None) == x.id
                    ),
                    None,
                )
            )
            if session:
                prove_source(self.game, c, state, session.id)
                result["questions"] = [
                    dict(
                        id=q.id,
                        text=q.text,
                        closed=bool(q.closed_event),
                        answers=[
                            dict(author=a.author, text=a.text, event=a.event)
                            for a in rules.records(state, rules.Answer)
                            if a.question == q.id
                        ],
                    )
                    for q in rules.records(state, rules.Question)
                    if q.session == session.id
                ]
            if isinstance(source, rules.Wraith):
                result["voices"] = [
                    x.model_dump(mode="json")
                    for x in rules.records(state, rules.Voice)
                    if x.wraith == identity
                ]
            if isinstance(source, rules.Shield) and source.high and not source.ended_event:
                result["approachers"] = _approachers(self.game, c, state, viewer, source)
            if isinstance(source, rules.Party):
                result["owed_roles"] = [
                    x.model_dump(mode="json") for x in source.companions if x not in source.present
                ]
            return result


def _approachers(
    game: GameService, c: Connection, state: GameState, viewer: GuildViewer, source: rules.Source
) -> list[dict[str, Any]]:
    if not isinstance(source, rules.Shield) or not source.high or source.ended_event:
        return []
    prove_shield(game, c, state, source.id)
    bound = profiles(c, game.store.campaign_id)
    target = resolve(state, source.target, bound)
    if target.cell is None:
        return []
    result = []
    for ref in owned_refs(state, viewer.user_id, bound):
        if ref in (source.actor, source.target):
            continue
        try:
            actor = resolve(state, ref, bound)
        except ValueError:
            continue
        if actor.controller == viewer.user_id and actor.cell == target.cell:
            result.append(dict(ref=ref.model_dump(mode="json"), token=ref.token, label=actor.label))
    return result


def _audience(game: GameService, c: Connection, state: GameState, source: rules.Source) -> set[int]:
    if isinstance(source, (rules.Session, rules.RousedUse)):
        return {x.controller for x in source.cast.roles} | (
            {source.cast.facilitator} if source.cast.facilitator else set()
        )
    if isinstance(source, rules.Party):
        return {x.controller for x in source.cast.roles} | (
            {source.cast.facilitator} if source.cast.facilitator else set()
        )
    if isinstance(source, (rules.Question, rules.Wraith)):
        return set(source.table)
    if isinstance(source, rules.Shield) and source.high:
        original = prove_source(game, c, state, source.session)
        return {x.controller for x in original.cast.roles} | {original.handler_controller}
    if isinstance(source, rules.Danger):
        original = prove_source(game, c, state, source.session)
        return {x.controller for x in original.cast.roles} | {original.handler_controller}
    if isinstance(source, rules.Answer):
        question = next(x for x in rules.records(state, rules.Question) if x.id == source.question)
        return set(question.table)
    if isinstance(source, rules.Voice):
        mind = next(x for x in rules.records(state, rules.Wraith) if x.id == source.wraith)
        return set(mind.table)
    if isinstance(source, rules.Approach):
        return {source.controller}
    bound = profiles(c, game.store.campaign_id)
    people = {
        resolve(
            state, source.actor, bound, require_alive=False, require_current_profile=False
        ).controller
    }
    if isinstance(source, (rules.Cargo, rules.Shield)):
        people.add(
            resolve(
                state,
                source.owner if isinstance(source, rules.Cargo) else source.target,
                bound,
                require_alive=False,
                require_current_profile=False,
            ).controller
        )
    if isinstance(source, rules.Renovation):
        people.add(source.handler_controller)
    return people


def _tasks(
    game: GameService, c: Connection, state: GameState, viewer: GuildViewer
) -> list[dict[str, Any]]:
    tasks = []
    models = (
        rules.Session,
        rules.Party,
        rules.Question,
        rules.Danger,
        rules.Renovation,
        rules.Wraith,
        rules.Cargo,
        rules.Shield,
        rules.Approach,
    )
    for source in rules.all_records(state, models):
        if viewer.user_id not in _audience(game, c, state, source) and not _approachers(
            game, c, state, viewer, source
        ):
            continue
        pending = False
        actionable = False
        if isinstance(source, rules.Session):
            pending = not source.completed_event
        elif isinstance(source, rules.Party):
            pending = not source.bound_action and not source.cancelled_event
            actionable = pending and any(
                x not in source.present
                and resolve(state, x, profiles(c, game.store.campaign_id)).controller
                == viewer.user_id
                for x in source.companions
            )
        elif isinstance(source, rules.Question):
            pending = not source.closed_event
            actionable = pending
        elif isinstance(source, rules.Danger):
            pending = not source.returned_event
            original = prove_source(game, c, state, source.session)
            actionable = (
                pending
                and source.kind == "delay"
                and bool(original.answers_closed_event)
                and viewer.user_id == original.handler_controller
            )
        elif isinstance(source, rules.Renovation):
            pending = not source.completed_event
            actionable = (
                pending
                and source.kind == "past"
                and not source.answered_event
                and viewer.user_id == source.handler_controller
            )
        elif isinstance(source, rules.Wraith):
            pending = source.active and not source.ended_event
            actionable = pending
        elif isinstance(source, rules.Shield):
            pending = not source.ended_event
            actionable = pending and source.high
        elif isinstance(source, rules.Cargo):
            pending = not source.ended_event
            actionable = pending and (
                bool(source.boarded_event)
                or resolve(state, source.owner, profiles(c, game.store.campaign_id)).controller
                == viewer.user_id
            )
        elif isinstance(source, rules.Approach):
            pending = not source.gave_up_event
            actionable = pending
        tasks.append(
            dict(
                id=source.id,
                revision=state.revision,
                label=rules.KINDS[type(source)].replace("_", " "),
                phase="pending" if pending else "resolved",
                pending=actionable,
            )
        )
    return tasks
