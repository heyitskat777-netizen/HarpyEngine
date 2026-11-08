"""Actual Dose Up sources, human-owned choices and real cocktail Tag lifetime."""

import json
from typing import Any
from uuid import NAMESPACE_URL, uuid4, uuid5

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_dose_up as rules
from girlframe.engine.m2 import ChoiceAnswer, GameState, PlayInput, TagState
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef, Model, SceneCast
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_girl_runtime_state import has_rule
from girlframe.engine.m3_handler_consequences import active_handler
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_actors import ActorService, profiles
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_handler_advancements import _history
from girlframe.services.m3_missions import MissionService
from girlframe.services.onboarding import OnboardingStore, WorkflowError
from girlframe.services.read_only_bot import GuildViewer

KINDS = ("dose_up_components", "dose_up_target_low")


def _record[T: Model](state: GameState, model: type[T], identity: str) -> T:
    value = next((x for x in rules.records(state, model) if x.model_dump()["id"] == identity), None)
    if value is None:
        raise WorkflowError("Recover the genuine original Dose Up source")
    return value


def _access(game: GameService, c: Connection, viewer: GuildViewer) -> None:
    gate = Access(game.store)
    gate.authorize(c, viewer, "plays", director_response=True)
    assert gate.registry is not None
    gate.registry.require_available(rules.RULE)


def _cast(game: GameService, c: Connection, state: GameState, channel: int) -> SceneCast:
    cast = CastService(ActorService(MissionService(game.store)))._current(c, state, channel)[0]
    if cast.adjudicator is not None or cast.facilitator != state.handler:
        raise WorkflowError("Use this ordinary native source with its actual Handler facilitator")
    return cast


def _native(game: GameService, c: Connection, state: GameState, actor: ActorRef) -> Any:
    value = resolve(state, actor, profiles(c, game.store.campaign_id))
    if (
        actor.kind != "pilot"
        or value.rules != "girl_frame"
        or value.offstage_source is not None
        or value.custody not in (None, "free")
        or state.sheets[actor.entity].medical_state != "fit"
    ):
        raise WorkflowError("Use the actual available original native Girl's body")
    return value


def _operator(game: GameService, c: Connection, state: GameState, actor: ActorRef) -> Any:
    actual = _native(game, c, state, actor)
    if not has_rule(state.sheets[actor.entity], rules.RULE, "STIM-BLISSED"):
        raise WorkflowError("Only the actual source-owned Dose Up Girl performs this Play")
    return actual


def _audit(
    game: GameService, c: Connection, event: str, kinds: tuple[str, ...], actor: int
) -> None:
    value = c.execute(
        sa.select(t.events.c.kind, t.events.c.actor_id).where(
            t.events.c.campaign_id == game.store.campaign_id,
            t.events.c.id == event,
        )
    ).first()
    if value is None or value.kind not in kinds or value.actor_id != str(actor):
        raise WorkflowError("Recover the actual original human's canonical Dose Up event")


def _reach(game: GameService, c: Connection, state: GameState, value: rules.Contact) -> None:
    first = _operator(game, c, state, value.actor)
    other = _native(game, c, state, value.target)
    if (
        value.actor == value.target
        or value.caster != first.controller
        or value.target_controller != other.controller
        or first.inside_frame is not False
        or other.inside_frame is not False
        or first.cell is None
        or first.cell != other.cell
        or first.position_sha256 != value.actor_position
        or other.position_sha256 != value.target_position
        or first.vessel_id != value.actor_vessel
        or other.vessel_id != value.target_vessel
        or not any(
            x.actor == value.actor and x.controller == value.caster for x in value.cast.roles
        )
        or not any(
            x.actor == value.target and x.controller == value.target_controller
            for x in value.cast.roles
        )
    ):
        raise WorkflowError("Re-establish actual close vein reach in the original bodies and scene")


def contact(game: GameService, c: Connection, state: GameState, identity: str) -> rules.Contact:
    value = _record(state, rules.Contact, identity)
    born = _history(c, game, value.event)
    _audit(game, c, value.event, ("m3.dose_up_contact",), value.caster)
    if (
        value not in rules.records(born, rules.Contact)
        or value.reviewer != value.caster
        or value.cast not in born.scene_casts
    ):
        raise WorkflowError("Recover the original operator's actual vein-reach account")
    _reach(game, c, born, value)
    return value


def stage_order(
    game: GameService,
    c: Connection,
    state: GameState,
    issuer: int,
    target: int,
    order_id: str,
    channel: int,
    event: str,
) -> dict[str, Any]:
    actor = current_ref(state, target)
    _operator(game, c, state, actor)
    cast = _cast(game, c, state, channel)
    source = active_handler(state) if issuer == state.handler else current_ref(state, issuer)
    if source is None or not any(x.actor == actor and x.controller == target for x in cast.roles):
        raise WorkflowError(
            "Use the real original Stim-Blissed target and actual issued-order source"
        )
    if issuer != state.handler and not any(
        x.actor == source and x.controller == issuer for x in cast.roles
    ):
        raise WorkflowError("Use the actual native issuer's original scene role")
    value = rules.DoseOrder(
        id=order_id,
        actor=actor,
        issuer=source,
        controller=issuer,
        scene=cast.id,
        cast=cast,
        event=event,
    )
    if not any(x.id == cast.id for x in state.scene_casts):
        state.scene_casts.append(cast)
    rules.put(state, value)
    return value.model_dump(mode="json")


def _order_proof(
    game: GameService, c: Connection, state: GameState, actor: ActorRef, identity: str
) -> rules.DoseOrder:
    value = _record(state, rules.DoseOrder, identity)
    row = (
        c.execute(
            sa.select(t.m2["m2_orders"]).where(
                t.m2["m2_orders"].c.campaign_id == game.store.campaign_id,
                t.m2["m2_orders"].c.id == identity,
            )
        )
        .mappings()
        .first()
    )
    born = _history(c, game, value.event)
    _audit(game, c, value.event, ("m2.order_issued",), value.controller)
    if (
        row is None
        or row["state"] != "followed"
        or row["issuer_id"] != str(value.controller)
        or row["target_id"] != actor.entity
        or value.actor != actor
        or json.loads(row["body_json"]).get("dose_up") != value.model_dump(mode="json")
        or value not in rules.records(born, rules.DoseOrder)
        or value.cast not in born.scene_casts
        or int(row["channel_id"]) != value.cast.channel
    ):
        raise WorkflowError("Recover the real original followed typed Dose Order")
    return value


def order_source(
    game: GameService,
    c: Connection,
    state: GameState,
    actor: ActorRef,
    identity: str,
    *,
    action: str | None = None,
) -> rules.DoseOrder:
    value = _order_proof(game, c, state, actor, identity)
    row = (
        c.execute(
            sa.select(t.m2["m2_orders"]).where(
                t.m2["m2_orders"].c.campaign_id == game.store.campaign_id,
                t.m2["m2_orders"].c.id == identity,
            )
        )
        .mappings()
        .first()
    )
    born = _history(c, game, value.event)
    _audit(game, c, value.event, ("m2.order_issued",), value.controller)
    if (
        row is None
        or row["state"] != "followed"
        or row["issuer_id"] != str(value.controller)
        or row["target_id"] != actor.entity
        or value.actor != actor
        or json.loads(row["body_json"]).get("dose_up") != value.model_dump(mode="json")
        or value not in rules.records(born, rules.DoseOrder)
        or int(row["channel_id"]) != value.cast.channel
        or any(
            x.id == identity and x.action != action for x in rules.records(state, rules.OrderUse)
        )
    ):
        raise WorkflowError("Use the real followed, unconsumed typed self-Dose Order")
    return value


def prepare(
    game: GameService,
    c: Connection,
    viewer: GuildViewer,
    state: GameState,
    prepared: PlayInput,
    channel: int,
) -> dict[str, Any]:
    _access(game, c, viewer)
    actor = current_ref(state, viewer.user_id)
    actual = _operator(game, c, state, actor)
    cast = _cast(game, c, state, channel)
    if not any(x.id == cast.id for x in state.scene_casts):
        state.scene_casts.append(cast)
    handler = active_handler(state)
    if (
        handler is None
        or cast.facilitator != state.handler
        or prepared.parent
        or prepared.off_duty_id
        or prepared.target is not None
        or not any(x.actor == actor and x.controller == viewer.user_id for x in cast.roles)
    ):
        raise WorkflowError("Use the original available Dose Up actor and ordinary source scene")
    target = prepared.target_actor or actor
    reach = None
    if target != actor:
        reach = contact(game, c, state, prepared.source_work or "")
        if (reach.actor, reach.target, reach.cast.channel) != (actor, target, channel):
            raise WorkflowError("Use this exact source's original vein contact")
        _reach(game, c, state, reach)
        if cast != reach.cast:
            raise WorkflowError("Re-establish actual vein contact after the scene roles change")
        if prepared.order_id:
            raise WorkflowError("The printed Order component override is for self-dosing")
    elif prepared.source_work:
        raise WorkflowError("Self-dose uses the actual original body without a foreign contact")
    other = _native(game, c, state, target)
    source_order = (
        order_source(game, c, state, actor, prepared.order_id) if prepared.order_id else None
    )
    if source_order is not None and source_order.cast != cast:
        raise WorkflowError("Use the actual followed dosing Order in its original scene")
    assert cast.facilitator is not None
    return dict(
        actor=actor.model_dump(mode="json"),
        target=target.model_dump(mode="json"),
        caster=actual.controller,
        target_controller=other.controller,
        handler=handler.model_dump(mode="json"),
        handler_controller=state.handler,
        cast=cast.model_dump(mode="json"),
        table=sorted({x.controller for x in cast.roles} | {cast.facilitator}),
        contact=reach.id if reach else None,
        order=source_order.id if source_order else None,
        chooser=source_order.controller if source_order else viewer.user_id,
        phase="unrolled",
        selections=[],
    )


def pre_roll(
    game: GameService, c: Connection, viewer: GuildViewer, state: GameState, action: dict[str, Any]
) -> None:
    prepared = PlayInput.model_validate(action["data"]["prepared"])
    expected = prepare(game, c, viewer, state, prepared, int(action["channel_id"]))
    meta = action["data"]["dose_up"]
    if any(
        meta.get(key) != expected[key]
        for key in (
            "actor",
            "target",
            "caster",
            "target_controller",
            "handler",
            "handler_controller",
            "cast",
            "table",
            "contact",
            "order",
            "chooser",
        )
    ):
        raise WorkflowError("Recover the unchanged actual Dose Up source before spending or RNG")
    if meta["order"]:
        order_source(
            game,
            c,
            state,
            ActorRef.model_validate(meta["actor"]),
            meta["order"],
            action=action["id"],
        )
        if not any(x.id == meta["order"] for x in rules.records(state, rules.OrderUse)):
            rules.put(state, rules.OrderUse(id=meta["order"], action=action["id"]))


def _roll_source(game: GameService, c: Connection, action: dict[str, Any]) -> tuple[str, int]:
    receipt = (
        c.execute(
            sa.select(t.m2["m2_receipts"]).where(
                t.m2["m2_receipts"].c.campaign_id == game.store.campaign_id,
                t.m2["m2_receipts"].c.action_id == action["id"],
            )
        )
        .mappings()
        .first()
    )
    if receipt is None or json.loads(receipt["body_json"]) != action["data"].get("receipt"):
        raise WorkflowError("Recover the real original Dose Up roll receipt")
    event = c.scalar(
        sa.select(t.events.c.id).where(
            t.events.c.campaign_id == game.store.campaign_id,
            t.events.c.kind.in_(("m2.rolled", "m3.rolled")),
            t.events.c.actor_id == str(action["actor_id"]),
            sa.func.json_extract(t.events.c.payload_json, "$.action_id") == action["id"],
            sa.func.json_extract(t.events.c.payload_json, "$.receipt_id") == receipt["id"],
        )
    )
    if event is None:
        raise WorkflowError("Recover the actual canonical original Dose Up roll event")
    if action["data"].get("prince_mark"):
        from girlframe.services.m3_prince import prove_mark

        prove_mark(game, c, load_state(c, game.store.campaign_id), action)
    total = action["data"]["receipt"]["pre_total"] + sum(
        x["amount"] for x in action["data"]["modifiers"]
    )
    from girlframe.engine.m3_gender_designation import man_floor

    minimum = man_floor(action)
    if minimum is not None:
        total = max(total, minimum)
    if action["data"].get("casualty_override"):
        from girlframe.services.m3_casualty import prove_override

        adjustment = prove_override(game, c, load_state(c, game.store.campaign_id), action)
        if adjustment is not None:
            total = max(total, adjustment)
    if action["data"].get("prince_override"):
        from girlframe.services.m3_prince import prove_override as prove_prince_override

        adjustment = prove_prince_override(game, c, load_state(c, game.store.campaign_id), action)
        if adjustment is not None:
            total = max(total, adjustment)
    if action["data"].get("consume_disobey_limit"):
        from girlframe.services.m3_consume import prove_disobey_limit

        cap = prove_disobey_limit(game, c, load_state(c, game.store.campaign_id), action)
        if cap is not None:
            total = min(total, cap)
    if action["data"].get("ankou_roll_modifiers"):
        from girlframe.services.m3_ankou import prove_roll_modifiers

        actual_modifiers = prove_roll_modifiers(
            game, c, load_state(c, game.store.campaign_id), action
        )
        source_ids = {x["source"] for x in actual_modifiers}
        recorded_modifiers = [
            x
            for x in action["data"]["receipt"].get("pre_modifiers", ())
            if x["source"] in source_ids
        ]
        if actual_modifiers != action["data"]["ankou_roll_modifiers"] or [
            (x["source"], x["amount"]) for x in actual_modifiers
        ] != [(x["source"], x["amount"]) for x in recorded_modifiers]:
            raise WorkflowError("Recover the actual consumed Fight/Fawn sources and receipt")
    if action["data"].get("changeling_flirt"):
        from girlframe.services.m3_changeling import prove_flirt_modifier

        actual = prove_flirt_modifier(game, c, load_state(c, game.store.campaign_id), action)
        recorded = sum(
            x["amount"]
            for x in action["data"]["receipt"].get("pre_modifiers", ())
            if x["source"] == "changeling_fingers_flirt"
        )
        if actual != recorded:
            raise WorkflowError("Recover the actual consumed psychic Flirt grant")
    if action["data"].get("red_queen_modifier"):
        from girlframe.services.m3_red_queen import prove_personality_modifier

        if (
            prove_personality_modifier(game, c, load_state(c, game.store.campaign_id), action)
            != action["data"]["red_queen_modifier"]
        ):
            raise WorkflowError("Recover the actual consumed personality modifier")
    if action["data"].get("red_queen_doll"):
        from girlframe.services.m3_red_queen import prove_doll_limit

        limit = prove_doll_limit(game, c, load_state(c, game.store.campaign_id), action)
        if limit is None:
            raise WorkflowError("Recover the actual consumed Doll source")
        total = min(total, limit)
    if total != action["data"]["result"]["total"]:
        raise WorkflowError("Recover the actual source roll and applied Tag modifiers")
    return str(event), int(total)


def _quota(action: dict[str, Any]) -> tuple[str, int, int, int]:
    meta = action["data"]["dose_up"]
    total = action["data"]["result"]["total"]
    if total <= 7:
        return "handler", int(meta["handler_controller"]), 1, 2
    if len(meta["selections"]) == 0:
        return "issuer" if meta["order"] else "roller", int(meta["chooser"]), 2, 2
    return "handler", int(meta["handler_controller"]), 1, 1


def results(game: GameService, c: Connection, state: GameState, action: dict[str, Any]) -> None:
    meta = action["data"]["dose_up"]
    if meta["phase"] != "unrolled":
        raise WorkflowError("Resume the existing original Dose Up choices without rerolling")
    _, total = _roll_source(game, c, action)
    meta["phase"] = "choosing"
    if total <= 7 and meta["actor"] != meta["target"]:
        meta["phase"] = "target_low"
        game.request(c, action, int(meta["target_controller"]), "dose_up_target_low")
    else:
        game.request(c, action, _quota(action)[1], "dose_up_components")


def _finish(game: GameService, c: Connection, state: GameState, action: dict[str, Any]) -> None:
    if game.pending(c, action["id"]) or action["state"] == "complete":
        return
    from girlframe.services.m2_choices import ChoiceEngine

    action["data"]["dose_up"]["phase"] = "complete"
    ChoiceEngine(game).finish(c, state, action)
    game.save_action(c, action)


def _outcome(
    game: GameService,
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    *,
    punishment: str | None = None,
) -> rules.Dose:
    meta = action["data"]["dose_up"]
    rolled, total = _roll_source(game, c, action)
    value = rules.Dose(
        id=action["id"],
        actor=ActorRef.model_validate(meta["actor"]),
        target=ActorRef.model_validate(meta["target"]),
        caster=meta["caster"],
        target_controller=meta["target_controller"],
        handler=ActorRef.model_validate(meta["handler"]),
        handler_controller=meta["handler_controller"],
        cast=SceneCast.model_validate_json(json.dumps(meta["cast"])),
        contact=meta["contact"],
        order=meta["order"],
        heat=action["data"]["prepared"]["heat"],
        total=total,
        roll_event=rolled,
        selections=tuple(
            rules.Selection.model_validate_json(json.dumps(x)) for x in meta["selections"]
        ),
        event=action["data"]["response_event"],
        punishment=punishment,
        recipient_choice=meta.get("recipient_choice"),
        recipient_event=meta.get("recipient_event"),
    )
    rules.put(state, value)
    return value


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
    meta = action["data"]["dose_up"]
    if (
        answer.denied
        or answer.fields
        or answer.number is not None
        or answer.member is not None
        or answer.flag is not None
    ):
        raise WorkflowError("Use only the actual source-owned Dose Up selection")
    if row["kind"] == "dose_up_target_low":
        if (
            meta["phase"] != "target_low"
            or int(row["actor_id"]) != meta["target_controller"]
            or answer.options not in (("dose",), ("punish",))
        ):
            raise WorkflowError("Only the actual recipient chooses dose or printed Punishment")
        meta["recipient_choice"] = row["id"]
        meta["recipient_event"] = action["data"]["response_event"]
        if answer.options == ("dose",):
            meta["phase"] = "choosing"
            game.request(c, action, meta["handler_controller"], "dose_up_components")
        else:
            from girlframe.services.m3_role_punishments import open_case

            identity = str(uuid4())
            target = ActorRef.model_validate(meta["target"])
            changed, case = open_case(
                state,
                profiles(c, game.store.campaign_id),
                actor=target,
                target=ActorRef.model_validate(meta["actor"]),
                chooser=target,
                source_kind="dose_up",
                action=action["id"],
                source_event=action["data"]["response_event"],
                identity=identity,
            )
            for name in GameState.model_fields:
                setattr(state, name, getattr(changed, name))
            meta["punishment"] = case
            meta["phase"] = "punishment"
            _outcome(game, c, state, action, punishment=case)
        return True
    role, chooser, minimum, maximum = _quota(action)
    used = {x for part in meta["selections"] for x in part["components"]}
    chosen = answer.options
    if (
        meta["phase"] != "choosing"
        or int(row["actor_id"]) != chooser
        or len(set(chosen)) != len(chosen)
        or not minimum <= len(chosen) <= maximum
        or not set(chosen) <= set(rules.COMPONENTS) - used
    ):
        raise WorkflowError("Choose the actual printed number of distinct available components")
    selection = rules.Selection.model_validate(
        dict(
            role=role,
            chooser=chooser,
            components=chosen,
            choice=row["id"],
            event=action["data"]["response_event"],
        )
    )
    meta["selections"].append(selection.model_dump(mode="json"))
    if action["data"]["result"]["total"] >= 11 and len(meta["selections"]) == 1:
        game.request(c, action, meta["handler_controller"], "dose_up_components")
        return True
    value = _outcome(game, c, state, action)
    sheet = state.sheets[value.target.entity]
    for part in value.selections:
        for component in part.components:
            identity = "dose-up:" + value.id + ":" + component
            tag = TagState(
                id=identity,
                label=rules.LABELS[component],
                giver=value.caster,
                giver_actor=value.actor,
                giver_character=value.actor.incarnation,
                observers=tuple(meta["table"]),
            )
            sheet.tags.append(tag)
            rules.put(
                state,
                rules.DrugTag(
                    id=identity,
                    dose=value.id,
                    target=value.target,
                    component=component,
                    tag=tag.model_copy(deep=True),
                    event=value.event,
                ),
            )
    sheet.revision += 1
    _finish(game, c, state, action)
    return True


def choice_projection(
    game: GameService, c: Connection, state: GameState, action: dict[str, Any], row: dict[str, Any]
) -> dict[str, Any]:
    meta = action["data"]["dose_up"]
    if row["kind"] == "dose_up_target_low":
        return dict(
            options=(
                ("dose", "Be dosed with the actual cocktail"),
                ("punish", "Punish the actual operator instead"),
            )
        )
    role, chooser, minimum, maximum = _quota(action)
    if int(row["actor_id"]) != chooser:
        raise WorkflowError("Use the actual original component chooser")
    used = {x for part in meta["selections"] for x in part["components"]}
    return dict(
        role=role,
        minimum=minimum,
        maximum=maximum,
        options=tuple(
            (x, rules.LABELS[x] + " — " + rules.DESCRIPTIONS[x])
            for x in rules.COMPONENTS
            if x not in used
        ),
    )


def _response(
    game: GameService, c: Connection, action: str, choice: str, event: str, owner: int, kind: str
) -> ChoiceAnswer:
    request = (
        c.execute(
            sa.select(t.m2["m2_choices"]).where(
                t.m2["m2_choices"].c.campaign_id == game.store.campaign_id,
                t.m2["m2_choices"].c.id == choice,
            )
        )
        .mappings()
        .first()
    )
    answer = (
        c.execute(
            sa.select(t.m2["m2_responses"]).where(
                t.m2["m2_responses"].c.campaign_id == game.store.campaign_id,
                t.m2["m2_responses"].c.choice_id == choice,
            )
        )
        .mappings()
        .first()
    )
    _audit(game, c, event, ("m2.choice_resolved", "m3.choice_resolved"), owner)
    if (
        request is None
        or answer is None
        or request["action_id"] != action
        or request["kind"] != kind
        or request["actor_id"] != str(owner)
        or answer["actor_id"] != str(owner)
        or answer["event_id"] != event
    ):
        raise WorkflowError("Recover the real original human's owned Dose Up response")
    return ChoiceAnswer.model_validate_json(answer["answer_json"])


def _scene_ends(game: GameService, c: Connection, state: GameState, value: rules.Dose) -> None:
    ends = [x for x in rules.records(state, rules.SceneEnd) if x.dose == value.id]
    if len({x.scene for x in ends}) != len(ends) or len(ends) > value.duration:
        raise WorkflowError("Count each actual recipient-participated scene exactly once")
    for index, end in enumerate(ends):
        born = _history(c, game, end.event)
        event = (
            c.execute(
                sa.select(t.events).where(
                    t.events.c.campaign_id == game.store.campaign_id,
                    t.events.c.id == end.event,
                )
            )
            .mappings()
            .first()
        )
        if (
            event is None
            or event["kind"] != "m2.scene_closed"
            or json.loads(event["payload_json"]).get("channel") != end.cast.channel
            or end not in rules.records(born, rules.SceneEnd)
            or end.scene != end.cast.id
            or end.cast.open
            or end.cast not in born.scene_casts
            or not any(
                x.actor == value.target and x.controller == value.target_controller
                for x in end.cast.roles
            )
            or end.expired != (index + 1 >= value.duration)
        ):
            raise WorkflowError("Recover the genuine original recipient's scene-closure receipt")


def prove(game: GameService, c: Connection, state: GameState, identity: str) -> rules.Dose:
    value = _record(state, rules.Dose, identity)
    born = _history(c, game, value.event)
    action = game.action(c, identity)
    rolled, total = _roll_source(game, c, action)
    rolled_state = _history(c, game, rolled)
    actor = current_ref(rolled_state, int(action["actor_id"]))
    from girlframe.services.m3_learned_plays import prove_consumed

    learned = prove_consumed(game, c, rolled_state, action, rules.RULE, rolled)
    meta = action["data"].get("dose_up")
    if (
        meta is None
        or action["data"]["prepared"]["play"] != rules.PLAY
        or value not in rules.records(born, rules.Dose)
        or value.actor != actor
        or not (has_rule(rolled_state.sheets[actor.entity], rules.RULE, "STIM-BLISSED") or learned)
        or value.caster != int(actor.entity)
        or value.roll_event != rolled
        or value.total != total
        or value.heat != action["data"]["prepared"]["heat"]
        or value.cast != SceneCast.model_validate_json(json.dumps(meta["cast"]))
        or value.target != ActorRef.model_validate(meta["target"])
        or value.handler != active_handler(rolled_state)
        or value.handler_controller != rolled_state.handler
        or value.contact != meta["contact"]
        or value.order != meta["order"]
    ):
        raise WorkflowError("Recover the actual original Dose Up actor, receipt and source context")
    _scene_ends(game, c, state, value)
    chooser = value.caster
    if value.order is not None:
        order = _order_proof(game, c, state, actor, value.order)
        if value.target != actor or not any(
            x.id == order.id and x.action == identity for x in rules.records(born, rules.OrderUse)
        ):
            raise WorkflowError("Recover the once-used actual self-Dose Order")
        chooser = order.controller
    if value.contact is not None:
        reach = contact(game, c, state, value.contact)
        if (reach.actor, reach.target, reach.cast) != (value.actor, value.target, value.cast):
            raise WorkflowError("Recover the original real recipient's vein source")
    elif value.target != actor:
        raise WorkflowError("Recover this actual other body's source contact")
    if total <= 7 and value.target != actor:
        if value.recipient_choice is None or value.recipient_event is None:
            raise WorkflowError("Recover the actual low recipient's original choice")
        answer = _response(
            game,
            c,
            identity,
            value.recipient_choice,
            value.recipient_event,
            value.target_controller,
            "dose_up_target_low",
        )
        if answer.options != (("punish",) if value.punishment else ("dose",)):
            raise WorkflowError("Recover the actual low recipient's dose-versus-Punishment choice")
    elif (
        value.recipient_choice is not None or value.recipient_event is not None or value.punishment
    ):
        raise WorkflowError("Only the real other-recipient low result grants this alternative")
    if value.punishment:
        if value.selections or any(x.dose == identity for x in rules.records(born, rules.DrugTag)):
            raise WorkflowError(
                "The actual Punishment replaces the dose; it cannot also grant drugs"
            )
        return value
    expected = (
        [("handler", value.handler_controller, 1, 2)]
        if total <= 7
        else [("issuer" if value.order else "roller", chooser, 2, 2)]
        + ([("handler", value.handler_controller, 1, 1)] if total >= 11 else [])
    )
    if len(value.selections) != len(expected):
        raise WorkflowError("Recover every printed original cocktail chooser")
    seen: set[str] = set()
    for selection, (role, human, minimum, maximum) in zip(value.selections, expected, strict=True):
        answer = _response(
            game, c, identity, selection.choice, selection.event, human, "dose_up_components"
        )
        if (
            selection.role != role
            or selection.chooser != human
            or not minimum <= len(selection.components) <= maximum
            or len(set(selection.components)) != len(selection.components)
            or set(selection.components) & seen
            or answer.options != selection.components
        ):
            raise WorkflowError("Recover the exact printed distinct component choices")
        seen.update(selection.components)
    if value.event != value.selections[-1].event:
        raise WorkflowError("Recover the actual final cocktail application event")
    tags = [x for x in rules.records(born, rules.DrugTag) if x.dose == value.id]
    if {x.component for x in tags} != seen or len(tags) != len(seen):
        raise WorkflowError("Recover every actual source-owned temporary drug Tag")
    observers = tuple(sorted({x.controller for x in value.cast.roles} | {value.handler_controller}))
    born_sheet = born.sheets.get(value.target.entity)
    for drug in tags:
        expected_id = "dose-up:" + value.id + ":" + drug.component
        if (
            drug.id != expected_id
            or drug.target != value.target
            or drug.event != value.event
            or drug.tag.id != expected_id
            or drug.tag.label != rules.LABELS[drug.component]
            or drug.tag.giver != value.caster
            or drug.tag.giver_actor != value.actor
            or drug.tag.giver_character != value.actor.incarnation
            or drug.tag.observers != observers
            or born_sheet is None
            or drug.tag not in born_sheet.tags
        ):
            raise WorkflowError("Recover the source-owned actual Drug Tag and original witnesses")
    return value


def prove_tag(
    game: GameService, c: Connection, state: GameState, owner: int, tag: TagState
) -> None:
    if not tag.id.startswith("dose-up:"):
        return
    actor = current_ref(state, owner)
    drug = _record(state, rules.DrugTag, tag.id)
    value = prove(game, c, state, drug.dose)
    born = _history(c, game, drug.event)
    if (
        drug not in rules.records(born, rules.DrugTag)
        or drug.target != actor
        or drug.event != value.event
        or tag.id != "dose-up:" + value.id + ":" + drug.component
        or tag.label != rules.LABELS[drug.component]
        or tag.giver != value.caster
        or tag.giver_actor != value.actor
        or tag.giver_character != value.actor.incarnation
        or tag.observers != drug.tag.observers
        or rules.expired(state, value.id)
    ):
        raise WorkflowError("Recover the actual original active Drug Tag and physical operator")


def self_tag(
    game: GameService,
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    person: int,
    tag: TagState,
) -> bool:
    meta = action["data"].get("tag_context") or {}
    actor = (
        ActorRef.model_validate(meta["actor"])
        if meta.get("actor")
        else current_ref(state, int(action["actor_id"]))
    )
    if actor.kind != "pilot" or actor.entity != str(person):
        return False
    sheet = state.sheets.get(actor.entity)
    if sheet is None or not has_rule(sheet, rules.SELF_RULE, "STIM-BLISSED"):
        return False
    drug = next((x for x in rules.drug_tags(state, actor) if x.id == tag.id), None)
    if drug is None:
        return False
    registry = Access(game.store).registry
    assert registry is not None
    registry.require_available(rules.SELF_RULE)
    dose = prove(game, c, state, drug.dose)
    saved = _record(_history(c, game, drug.event), rules.DrugTag, drug.id)
    if (
        saved != drug
        or drug.target != actor
        or drug.event != dose.event
        or tag.label != rules.LABELS[drug.component]
        or tag.giver_actor != dose.actor
        or not any(x.id == tag.id for x in sheet.tags)
    ):
        raise WorkflowError("Recover the actual active original Drug Tag before self-marking")
    return True


def expire_scene(
    game: GameService, c: Connection, state: GameState, scene: dict[str, Any], event: str
) -> bool:
    cast = next((x for x in state.scene_casts if x.id == scene["id"]), None)
    legacy = cast is None
    if cast is None:
        cast = CastService(ActorService(MissionService(game.store)))._legacy(c, scene)
        cast = cast.model_copy(update={"open": False, "revision": cast.revision + 1})
    changed = False
    for value in rules.records(state, rules.Dose):
        if (
            value.punishment
            or rules.expired(state, value.id)
            or not any(x.actor == value.target for x in cast.roles)
        ):
            continue
        previous = [x for x in rules.records(state, rules.SceneEnd) if x.dose == value.id]
        if any(x.scene == scene["id"] for x in previous):
            continue
        prove(game, c, state, value.id)
        sheet = state.sheets.get(value.target.entity)
        if sheet is None or sheet.character_id != value.target.incarnation:
            raise WorkflowError("Recover the original drugged body rather than inherit its Tags")
        tags = {x.id for x in rules.records(state, rules.DrugTag) if x.dose == value.id}
        if any(x.id in tags and x.rejection_pending for x in sheet.tags):
            raise WorkflowError("Finish the actual pending drug-Tag rejection before scene closure")
        ends = len(previous) + 1 >= value.duration
        record = rules.SceneEnd(
            id=str(uuid5(NAMESPACE_URL, "dose-scene:" + value.id + ":" + scene["id"])),
            dose=value.id,
            scene=scene["id"],
            cast=cast,
            event=event,
            expired=ends,
        )
        rules.put(state, record)
        if ends:
            sheet.tags = [x for x in sheet.tags if x.id not in tags]
            sheet.revision += 1
        changed = True
    if changed and legacy:
        state.scene_casts.append(cast)
    return changed


def validate_role_case(c: Connection, game: GameService, state: GameState, case: Any) -> None:
    from girlframe.services.m3_intracadre_marriage import original_offender

    value = prove(game, c, state, case.action or "")
    original = original_offender(game, c, state, case.id, case.source_event, case.subject)
    if (
        case.source_kind != "dose_up"
        or value.punishment != case.id
        or value.target == value.actor
        or value.total > 7
        or original != value.actor
        or case.executor != value.target
        or case.chooser != value.target
        or case.chooser_controller != value.target_controller
        or case.executor_controller != value.target_controller
        or case.source_event != value.event
    ):
        raise WorkflowError("Recover the exact real low recipient's printed Punishment instead")


def complete_role_case(c: Connection, game: GameService, case: Any, event: str) -> None:
    state = load_state(c, game.store.campaign_id)
    validate_role_case(c, game, state, case)
    if case.completion_event != event or case.effect_event is None:
        raise WorkflowError(
            "Complete actual Punishment and every required child before Dose Up closes"
        )
    action = game.action(c, case.action)
    _finish(game, c, state, action)


class DoseUpService:
    def __init__(self, store: OnboardingStore, game: GameService | None = None):
        self.store = store
        self.game = game or GameService(store)

    def record_contact(
        self,
        viewer: GuildViewer,
        key: str,
        channel: int,
        target: ActorRef,
        expected: int,
        account: str,
    ) -> dict[str, Any]:
        if not account.strip() or len(account) > 1200:
            raise WorkflowError("Describe your actual physical reach to this person's vein")

        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            if state.revision != expected or self.game.pending_actions(c):
                raise WorkflowError("Finish pending Plays and reopen actual dosing controls")
            actor = current_ref(state, viewer.user_id)
            first, other = (
                _operator(self.game, c, state, actor),
                _native(self.game, c, state, target),
            )
            cast = _cast(self.game, c, state, channel)
            event, identity = str(uuid4()), str(uuid4())
            value = rules.Contact(
                id=identity,
                actor=actor,
                target=target,
                caster=viewer.user_id,
                target_controller=other.controller,
                reviewer=viewer.user_id,
                cast=cast,
                actor_position=first.position_sha256,
                target_position=other.position_sha256,
                actor_vessel=first.vessel_id,
                target_vessel=other.vessel_id,
                event=event,
                account=account,
            )
            _reach(self.game, c, state, value)
            if not any(x.id == cast.id for x in state.scene_casts):
                state.scene_casts.append(cast)
            rules.put(state, value)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.dose_up_contact",
                state,
                event_id=event,
                contact=identity,
            )
            return dict(id=identity)

        return self.store._write(
            viewer,
            key,
            "m3.dose_up_contact",
            dict(
                channel=channel,
                target=target.model_dump(mode="json"),
                expected=expected,
                account=account,
            ),
            operation,
            auto_audit=False,
            authorize=lambda c: _access(self.game, c, viewer),
        )

    def menu(self, viewer: GuildViewer, channel: int) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            _access(self.game, c, viewer)
            state = load_state(c, self.store.campaign_id)
            targets: list[dict[str, Any]] = []
            orders: list[dict[str, str]] = []
            contacts: list[dict[str, Any]] = []
            can_dose = False
            try:
                actor = current_ref(state, viewer.user_id)
                own = _operator(self.game, c, state, actor)
                cast = _cast(self.game, c, state, channel)
                can_dose = any(
                    x.actor == actor and x.controller == viewer.user_id for x in cast.roles
                )
                for role in cast.roles:
                    if role.actor == actor or role.actor.kind != "pilot":
                        continue
                    other = _native(self.game, c, state, role.actor)
                    if (
                        own.inside_frame is False
                        and other.inside_frame is False
                        and own.cell is not None
                        and own.cell == other.cell
                    ):
                        targets.append(
                            dict(ref=role.actor.model_dump(mode="json"), label=other.label)
                        )
                for value in rules.records(state, rules.Contact):
                    if value.actor != actor or value.cast.channel != channel:
                        continue
                    try:
                        contact(self.game, c, state, value.id)
                        _reach(self.game, c, state, value)
                        if cast != value.cast:
                            continue
                    except (ValueError, WorkflowError):
                        continue
                    contacts.append(
                        dict(
                            id=value.id,
                            target=value.target.model_dump(mode="json"),
                            label=_native(self.game, c, state, value.target).label,
                        )
                    )
                for order in rules.records(state, rules.DoseOrder):
                    if order.actor != actor:
                        continue
                    try:
                        order_source(self.game, c, state, actor, order.id)
                    except (ValueError, WorkflowError):
                        continue
                    orders.append(dict(id=order.id, label="Actual followed dosing Order"))
            except (ValueError, WorkflowError):
                pass
            return dict(
                revision=state.revision,
                can_dose=can_dose,
                targets=targets,
                contacts=contacts,
                orders=orders,
                history=self._tasks(c, viewer),
            )

    def view(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            state = load_state(c, self.store.campaign_id)
            value = prove(self.game, c, state, identity)
            if viewer.user_id not in (
                value.caster,
                value.target_controller,
                value.handler_controller,
            ):
                raise WorkflowError(
                    "Only the original dosing participants may read this private source"
                )
            return dict(
                id=value.id,
                revision=state.revision,
                actor=value.actor.model_dump(mode="json"),
                target=value.target.model_dump(mode="json"),
                total=value.total,
                heat=value.heat,
                order=value.order,
                punishment=value.punishment,
                components=[
                    rules.LABELS[x.component]
                    for x in rules.records(state, rules.DrugTag)
                    if x.dose == value.id
                ],
                duration=value.duration,
                scenes=[
                    x.scene for x in rules.records(state, rules.SceneEnd) if x.dose == value.id
                ],
                phase="punishment"
                if value.punishment
                else "expired"
                if rules.expired(state, value.id)
                else "active",
            )

    def _tasks(self, c: Connection, viewer: GuildViewer) -> list[dict[str, Any]]:
        state = load_state(c, self.store.campaign_id)
        return [
            dict(
                id=x.id,
                revision=state.revision,
                label="Your actual Dose Up source and cocktail Tags",
                phase="punishment"
                if x.punishment
                else "expired"
                if rules.expired(state, x.id)
                else "active",
                pending=False,
            )
            for x in rules.records(state, rules.Dose)
            if viewer.user_id in (x.caster, x.target_controller, x.handler_controller)
        ]
