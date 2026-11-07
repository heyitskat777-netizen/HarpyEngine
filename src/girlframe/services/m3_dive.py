"""Shared actual-roll Dive Deep with owned effects and real table responses."""

import json
from typing import TYPE_CHECKING, Any
from uuid import NAMESPACE_URL, uuid5

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_dive as rules
from girlframe.engine.m2 import ChoiceAnswer, GameState, PlayInput
from girlframe.engine.m3_actor_state import ActorRef, SceneCast
from girlframe.engine.m3_actors import fingerprint, resolve
from girlframe.engine.m3_choices import DIVE, Context, plan
from girlframe.engine.m3_dive_state import Effect, NpcVoid
from girlframe.engine.m3_handler_consequences import active_handler
from girlframe.engine.m3_physical import cockpit_lock, occupied_frame
from girlframe.services.handler_setup import HandlerService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_actors import ActorService, profiles
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_medical import MedicalService
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_work import related
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer

if TYPE_CHECKING:
    from girlframe.services.m2_game import GameService


def source_cast_compatible(
    game: "GameService", c: Connection, state: GameState, action: dict[str, Any], current: SceneCast
) -> bool:
    """Exact original cast, or an immutable original ending's sole recorded cast transition."""
    from girlframe.services.m3_harpy_defeat import ended_director_judge
    from girlframe.services.m3_void_keep import _ended_handler_cast

    meta = action["data"]["dive"]
    original = SceneCast.model_validate_json(json.dumps(meta["cast"]))
    if fingerprint(original) != meta["cast_sha256"] or original.id != action["scene_id"]:
        return False
    if fingerprint(original) == fingerprint(current):
        return True
    judge = ActorRef.model_validate(meta["handler"]) if meta["handler"] else None
    gm_controller = meta.get("gm_controller") or original.facilitator
    return bool(
        judge is not None
        and judge.kind == "npc"
        and ended_director_judge(
            game,
            c,
            state,
            original,
            current,
            judge,
            _handler_controller(meta),
        )
        or type(gm_controller) is int
        and _ended_handler_cast(state, original, current, gm_controller)
    )


def authorize(
    game: "GameService", c: Connection, viewer: GuildViewer, action: dict[str, Any] | None = None
) -> None:
    Access(game.store).authorize(c, viewer, "plays", director_response=action is not None)
    if action is None:
        return
    if action["data"].get("actor_basic"):
        from girlframe.services.m3_actor_plays import ActorPlayService

        ActorPlayService(game).validate(c, load_state(c, game.store.campaign_id), action)
        return
    meta = action["data"]["dive"]
    approval = game.store.policy.m3_approval
    if approval is None or meta["registry"] != approval.registry_sha256:
        raise WorkflowError("M3_POLICY_CHANGED: recover the actual Dive release approval.")
    game.action_characters(c, action, load_state(c, game.store.campaign_id))
    handler, appointment = MedicalService(game.store)._handler(c)
    state = load_state(c, game.store.campaign_id)
    ref = active_handler(state)
    original_body = meta.get("marker_handler", meta["handler"])
    body_changed = (ref.model_dump(mode="json") if ref else None) != original_body
    if appointment != meta["appointment"] or meta.get("gm_controller", handler) != handler:
        raise WorkflowError("Recover this Dive's original current Handler appointment/persona.")
    cast, _ = CastService(ActorService(MissionService(game.store)))._current(
        c, state, int(action["channel_id"])
    )
    if not source_cast_compatible(game, c, state, action, cast):
        raise WorkflowError("SOURCE_TABLE_CHANGED: recover this Dive's actual original table.")
    if body_changed:
        from girlframe.services.m3_harpy_defeat import ended_actor_source

        if (
            original_body is None
            or ended_actor_source(game, c, state, ActorRef.model_validate(original_body)) is None
        ):
            raise WorkflowError("A replacement Handler body cannot inherit the original source")
    if "marker_handler" in meta:
        from girlframe.services.m3_battle import _scene_judge

        judge, controller, source = _scene_judge(game, c, state, cast)
        expected = (
            judge.model_dump(mode="json")
            if judge
            else (ref.model_dump(mode="json") if ref else None)
        )
        source_ended = fingerprint(cast) != meta["cast_sha256"]
        if not source_ended and (
            expected != meta["handler"]
            or controller != meta["handler_controller"]
            or source != meta["judge_source"]
        ):
            raise WorkflowError("Recover this actual Dive's original source-bound adjudicator")


def prepare(
    game: "GameService",
    c: Connection,
    viewer: GuildViewer,
    prepared: PlayInput,
    state: GameState,
    *,
    channel: int,
) -> dict[str, Any]:
    authorize(game, c, viewer)
    if (
        prepared.target is not None
        or prepared.off_duty_id is not None
        or prepared.order_id is not None
    ):
        raise WorkflowError(
            "Dive Deep uses your actual link and Heat, without a target or Off-Duty context."
        )
    if prepared.source_work:
        if prepared.source_work.startswith("bomb-trigger:"):
            from girlframe.services.m3_bomb_collar import prepare_survival

            prepare_survival(game, c, state, viewer, prepared, channel)
        else:
            from girlframe.services.m3_battle_dormant import prepare_dive_source

            prepare_dive_source(game, c, viewer, prepared, state, channel)
    actor = ActorRef(
        kind="pilot",
        entity=str(viewer.user_id),
        incarnation=game.character_binding(c, state, viewer.user_id),
    )
    view = resolve(state, actor, profiles(c, game.store.campaign_id), require_current_profile=False)
    if (
        view.rules != "girl_frame"
        or view.piloting is not None
        and view.piloting != prepared.piloting
    ):
        raise WorkflowError("Confirm the original Girl's actual Frame context.")
    cast, _ = CastService(ActorService(MissionService(game.store)))._current(c, state, channel)
    table = {x.controller for x in cast.roles}
    if cast.facilitator is not None:
        table.add(cast.facilitator)
    if viewer.user_id not in table:
        raise WorkflowError("Join the actual source cast before making Dive Deep.")
    for role in cast.roles:
        actual = resolve(
            state, role.actor, profiles(c, game.store.campaign_id), require_current_profile=False
        )
        if actual.controller != role.controller:
            raise WorkflowError("Recover the actual original cast controller.")
    for uid in table:
        if not HandlerService(game.store)._member(c, uid):
            raise WorkflowError("Recover the actual table human's campaign membership.")
    cast_npcs = tuple(x.actor.entity for x in cast.roles if x.actor.kind == "npc")
    if not available_options(state, actor, cast_npcs):
        raise WorkflowError("No printed Dive effect can apply to the actual resources or scene.")
    handler, appointment = MedicalService(game.store)._handler(c)
    assert game.store.policy.m3_approval is not None
    actual_handler = active_handler(state)
    from girlframe.services.m3_battle import _scene_judge

    judge, judge_controller, judge_source = _scene_judge(game, c, state, cast)
    return dict(
        actor=actor.model_dump(mode="json"),
        table=sorted(table),
        cast=cast.model_dump(mode="json"),
        cast_sha256=fingerprint(cast),
        handler=judge.model_dump(mode="json")
        if judge
        else actual_handler.model_dump(mode="json")
        if actual_handler
        else None,
        handler_controller=judge_controller,
        marker_handler=actual_handler.model_dump(mode="json") if actual_handler else None,
        gm_controller=handler,
        judge_source=judge_source,
        appointment=appointment,
        registry=game.store.policy.m3_approval.registry_sha256,
        steps=[],
        completed_steps=0,
        followups=[],
    )


def prepare_actor(
    game: "GameService",
    c: Connection,
    viewer: GuildViewer,
    state: GameState,
    cast: SceneCast,
    prepared: PlayInput,
    ref: ActorRef,
) -> dict[str, Any]:
    """Actual Harpy basic Dive uses its own resources and frozen real table."""
    from girlframe.services.m3_actor_plays import ActorPlayService

    Access(game.store).authorize(c, viewer, "plays", director_response=True)
    actual = resolve(state, ref, profiles(c, game.store.campaign_id), require_current_profile=False)
    if (
        ref.kind != "external_pilot"
        or actual.girl != "harpy"
        or actual.controller != viewer.user_id
        or prepared.play != "dive_deep"
        or prepared.target is not None
        or prepared.target_actor is not None
        or prepared.order_id
        or prepared.off_duty_id
        or prepared.witnessed
    ):
        raise WorkflowError("Use the actual original linked Harpy's own Dive resources and role.")
    if prepared.source_work:
        from girlframe.services.m3_battle_dormant import prepare_dive_source

        source = prepare_dive_source(game, c, viewer, prepared, state, cast.channel)
        if source["actor"] != ref.model_dump(mode="json"):
            raise WorkflowError("Use this obligation's actual original transformed Harpy role.")
    if not any(x.actor == ref and x.controller == viewer.user_id for x in cast.roles):
        raise WorkflowError("Join the actual Harpy role in this source scene before Dive.")
    judge = ActorPlayService(game)._judge(c, state, cast, ref)
    table = sorted(
        {x.controller for x in cast.roles} | ({cast.facilitator} if cast.facilitator else set())
    )
    if not available_options(
        state, ref, tuple(x.actor.entity for x in cast.roles if x.actor.kind == "npc")
    ):
        raise WorkflowError("No actual printed Dive effect is currently available for this Harpy.")
    assert game.store.policy.m3_approval is not None
    return dict(
        actor=ref.model_dump(mode="json"),
        table=table,
        cast=cast.model_dump(mode="json"),
        cast_sha256=fingerprint(cast),
        handler=judge.ref.model_dump(mode="json") if judge.ref else None,
        handler_controller=judge.controller,
        appointment=judge.appointment,
        registry=game.store.policy.m3_approval.registry_sha256,
        steps=[],
        completed_steps=0,
        followups=[],
    )


def _handler_controller(meta: dict[str, Any]) -> int:
    if meta.get("handler_controller") is not None:
        return int(meta["handler_controller"])
    return int(meta["handler"]["entity"])


def pre_roll(
    game: "GameService",
    c: Connection,
    viewer: GuildViewer,
    state: GameState,
    action: dict[str, Any],
) -> None:
    authorize(game, c, viewer, action)
    ref = ActorRef.model_validate_json(json.dumps(action["data"]["dive"]["actor"]))
    resolve(state, ref, profiles(c, game.store.campaign_id), require_current_profile=False)


def _groups(action: dict[str, Any]) -> tuple[Any, ...]:
    return tuple(plan("dive_deep", Context(total=action["data"]["result"]["total"])).groups)


def _next(game: "GameService", c: Connection, state: GameState, action: dict[str, Any]) -> None:
    from girlframe.services.m2_choices import ChoiceEngine

    meta = action["data"]["dive"]
    if game.pending(c, action["id"]):
        return
    completed = meta["completed_steps"]
    groups = _groups(action)
    if completed < len(groups):
        owner = (
            int(action["actor_id"])
            if groups[completed].owner == "actor"
            else _handler_controller(meta)
        )
        game.request(
            c, action, owner, "dive_select", dict(step=completed, role=groups[completed].owner)
        )
        return
    if action["data"]["result"]["tier"] == "high" and not meta.get("status_lowered"):
        actor = ActorRef.model_validate_json(json.dumps(meta["actor"]))
        if (
            actor.kind == "pilot"
            and actor.entity in state.sheets
            and state.sheets[actor.entity].character_id == actor.incarnation
        ):
            changed = rules.high_status(
                state, actor, action["id"], action["data"]["response_event"]
            )
            _copy(state, changed)
        else:
            state.facts.append(
                dict(
                    kind="dive_spike_original_no_longer_ranked",
                    action=action["id"],
                    actor=actor.model_dump_json(),
                )
            )
        meta["status_lowered"] = True
    if any(not item.get("continuation") for item in meta["followups"]):
        for item in (x for x in meta["followups"] if not x.get("continuation")):
            game.request(
                c,
                action,
                int(item["owner"]["entity"]),
                "dive_void_threshold",
                dict(step=item["step"], work_id=item["id"], owner=item["owner"]),
            )
            item["continuation"] = next(
                x["id"]
                for x in game.pending(c, action["id"])
                if x["kind"] == "dive_void_threshold"
                and json.loads(x["body_json"])["work_id"] == item["id"]
            )
        meta["thresholds_opened"] = True
        return
    action["data"]["result"]["dive_steps"] = [
        dict(option=x["option"], choice_owner=x["chooser"]) for x in meta["steps"]
    ]
    if action["data"].get("actor_basic"):
        from girlframe.services.m3_actor_plays import ActorPlayService

        ActorPlayService(game).finish(c, state, action)
    else:
        ChoiceEngine(game).finish(c, state, action)


def results(game: "GameService", c: Connection, action: dict[str, Any]) -> None:
    from girlframe.services.m2_state import load_state

    _next(game, c, load_state(c, game.store.campaign_id), action)


def _copy(target: GameState, source: GameState) -> None:
    for field in GameState.model_fields:
        setattr(target, field, getattr(source, field))


def _context(action: dict[str, Any]) -> tuple[ActorRef, ActorRef | None, tuple[str, ...]]:
    meta = action["data"]["dive"]
    cast = SceneCast.model_validate_json(json.dumps(meta["cast"]))
    return (
        ActorRef.model_validate_json(json.dumps(meta["actor"])),
        ActorRef.model_validate_json(json.dumps(meta["handler"])) if meta["handler"] else None,
        tuple(x.actor.entity for x in cast.roles if x.actor.kind == "npc"),
    )


def projection(
    game: "GameService",
    c: Connection,
    viewer: GuildViewer,
    state: GameState,
    action: dict[str, Any],
    request: dict[str, Any],
) -> dict[str, Any]:
    actor, handler, npcs = _context(action)
    body = json.loads(request["body_json"])
    step = body["step"]
    meta = action["data"]["dive"]
    data: dict[str, Any] = dict(
        step=step, level=action["data"]["result"]["tier"], table=meta["table"]
    )
    if request["kind"] == "dive_select":
        data["options"] = available_options(state, actor, npcs)
        from girlframe.services.m3_mockingbird_communion import BOARD, RELAY, candidates

        data["options"] = tuple(
            x
            for x in data["options"]
            if x not in (BOARD, RELAY) or candidates(game, c, state, action, x)
        )
        return data
    if request["kind"] == "dive_handler_void":
        data["work_id"] = body["work_id"]
        return data
    selected = meta["steps"][step]
    data["option"] = selected["option"]
    if request["kind"] == "dive_call":
        data["call_session"] = body["session"]
        return data
    actual_assets, actual_identities = rules.resources(state, actor)
    if request["kind"] == "dive_effect":
        option = selected["option"]
        if option in ("call_cockpit_guest", "call_gorgon_relay"):
            from girlframe.services.m3_mockingbird_communion import candidates

            data["targets"] = candidates(game, c, state, action, option)
        elif option == "call_reclassify_assets":
            data["assets"] = [
                dict(id=x.id, label=x.name, family=x.family, void=x.void) for x in actual_assets
            ]
        elif option == "void_and_unmark_all":
            from girlframe.engine.m3_janus_storage import active
            from girlframe.services.m3_janus_storage import available as storage_available

            stored = {x.asset for x in active(state, actor)}
            data["assets"] = [
                dict(id=x.id, label=x.name)
                for x in actual_assets
                if not x.void and x.id not in stored
            ]
            data["storage_available"] = storage_available(game, c, state, actor)
            from girlframe.services.m3_sup import offer

            data["sup"] = offer(game, c, state, actor)
        elif option in ("erase_identity_and_table_question", "table_replaces_identity"):
            data["identities"] = [
                dict(id=x.id, label=x.name) for x in actual_identities if not x.protected
            ]
        elif option == "nearby_npcs_gain_void":
            available = rules.nearby(state, actor, npcs)
            data["npcs"] = (
                [dict(id=x.id, label=x.name) for x in state.world.npcs if x.id in available]
                if state.world
                else []
            )
            # Directors own their later physiology choices, not details on this form.
            # Do not reveal their identities or counts to the effect's chooser.
            data["has_targets"] = bool(rules.nearby_all(state, actor, npcs))
    if request["kind"] == "dive_table_answer":
        data["question"] = selected["effect"]["question"]
        data["answers"] = selected.get("answers", {})
    if request["kind"] == "dive_table_agreement":
        data["proposal"] = selected["effect"]
        data["identity_label"] = next(
            (x.name for x in actual_identities if x.id == selected["effect"]["identity"]),
            "Original Identity unavailable",
        )
        data["proposal_revision"] = selected["proposal_revision"]
        data["answers"] = selected.get("agreements", {})
    if request["kind"] == "dive_void_threshold":
        data["work_id"] = body["work_id"]
    return data


def available_options(
    state: GameState, actor: ActorRef, cast_npcs: tuple[str, ...] = ()
) -> tuple[str, ...]:
    try:
        actual_assets, actual_identities = rules.resources(state, actor)
    except ValueError:
        return ()
    values = list(DIVE)
    from girlframe.engine.m3_sup import offers

    if not any(not x.void for x in actual_assets) and not offers(state, actor):
        values.remove("void_and_unmark_all")
    if not any(not x.protected for x in actual_identities):
        values.remove("erase_identity_and_table_question")
        values.remove("table_replaces_identity")
    if not rules.nearby_all(state, actor, cast_npcs):
        values.remove("nearby_npcs_gain_void")
    if actor.kind == "external_pilot":
        from girlframe.engine.m3_harpy_defeat import harpy
        from girlframe.engine.m3_harpy_physical import locked

        actual_harpy = harpy(state, actor)
        if not actual_harpy.linked or locked(state, actor) is not None:
            values.remove("locked_cockpit_extraction_requires_frame_consent")
    else:
        body = next((x for x in state.placements if x.actor == actor), None)
        sheet = state.sheets[actor.entity]
        expected = (
            sheet.frame_runtime.id if sheet.frame_runtime else "initial:" + str(actor.incarnation)
        )
        if (
            body is None
            or occupied_frame(body) != (actor, expected)
            or cockpit_lock(state, actor, expected) is not None
        ):
            values.remove("locked_cockpit_extraction_requires_frame_consent")
    from girlframe.services.m3_mockingbird_call import options as call_options

    values.extend(call_options(state, actor))
    return tuple(values)


def _request_effect(game: "GameService", c: Connection, action: dict[str, Any], step: int) -> None:
    meta = action["data"]["dive"]
    selected = meta["steps"][step]
    role = selected["option"] in ("nearby_npcs_gain_void", "table_replaces_identity")
    uid = _handler_controller(meta) if role else int(action["actor_id"])
    game.request(c, action, uid, "dive_effect", dict(step=step))


def _apply_effect(
    game: "GameService",
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    step: int,
    request: dict[str, Any],
) -> None:
    meta = action["data"]["dive"]
    selected = meta["steps"][step]
    actor, handler, npcs = _context(action)
    if selected["option"] == "call_reclassify_assets":
        from girlframe.services.m3_mockingbird_call import apply as apply_classification

        result = apply_classification(game, c, state, action, step, actor)
    else:
        effect = Effect.model_validate_json(json.dumps(selected["effect"]))
        if selected.get("store_void"):
            from girlframe.services.m3_janus_storage import gain as store_gain

            followups = store_gain(game, c, state, action, step, request["id"], actor, effect)
            result = rules.Outcome(state=state, followups=followups)
        else:
            result = rules.apply(
                state,
                actor,
                profiles(c, game.store.campaign_id),
                selected["option"],
                effect,
                action["id"],
                step,
                action["data"]["response_event"],
                piloting=action["data"]["prepared"]["piloting"],
                handler=handler,
                cast_npcs=npcs,
                handler_controller=_handler_controller(meta),
            )
    _copy(state, result.state)
    if selected["option"] == "nearby_npcs_gain_void":
        directors = rules.nearby_directors(state, actor, npcs)
        if directors:
            from girlframe.services.m3_dive_handler_void import stage

            stage(
                game,
                c,
                state,
                action,
                source_choice=request["id"],
                step=step,
                actor=actor,
                candidates=directors,
                event=action["data"]["response_event"],
            )
    selected["applied_event"] = action["data"]["response_event"]
    if result.followups:
        for index, item in enumerate(result.followups):
            family = {
                "girl_void_threshold": "girl",
                "frame_void_threshold": "frame",
                "mockingbird_resist": "frame",
            }[item.kind]
            identity = str(
                uuid5(
                    NAMESPACE_URL,
                    "girlframe:dive-threshold:" + action["id"] + ":" + str(step) + ":" + str(index),
                )
            )
            meta["followups"].append(
                dict(
                    id=identity,
                    owner=actor.model_dump(mode="json"),
                    character=actor.incarnation,
                    source_action=action["id"],
                    source_choice=request["id"],
                    step=step,
                    details=dict(family=family),
                    source_pdf=19,
                    reason="dive_deep",
                    source_event=action["data"]["response_event"],
                    immediate=True,
                )
            )
    if selected["option"] == "erase_identity_and_table_question":
        selected["answers"] = {}
        for uid in meta["table"]:
            game.request(c, action, uid, "dive_table_answer", dict(step=step))
        return
    _complete_step(game, c, state, action, step)


def _complete_step(
    game: "GameService", c: Connection, state: GameState, action: dict[str, Any], step: int
) -> None:
    meta = action["data"]["dive"]
    if step != meta["completed_steps"]:
        raise WorkflowError("Recover this Dive's exact current effect order.")
    meta["steps"][step]["complete"] = True
    meta["completed_steps"] += 1
    _next(game, c, state, action)


def _strict(answer: ChoiceAnswer, allowed: set[str]) -> None:
    defaults = ChoiceAnswer()
    if any(
        getattr(answer, k) != getattr(defaults, k)
        for k in ChoiceAnswer.model_fields
        if k not in allowed
    ):
        raise WorkflowError("Supply only your actual current Dive choice fields.")


def apply(
    game: "GameService",
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    request: dict[str, Any],
    answer: ChoiceAnswer,
) -> None:
    meta = action["data"]["dive"]
    body = json.loads(request["body_json"])
    if request["kind"] == "dive_handler_void":
        raise WorkflowError("Resolve the original Director's real Void consequence")
    step = body["step"]
    if request["kind"] == "dive_void_threshold":
        raise WorkflowError(
            "Resolve the actual source Void threshold; this is not an acknowledgment."
        )
    if step != meta["completed_steps"]:
        raise WorkflowError("STALE_DIVE: resume the actual current effect.")
    kind = request["kind"]
    if kind == "dive_select":
        _strict(answer, {"options", "text"})
        actor, _, npcs = _context(action)
        if (
            len(answer.options) != 1
            or answer.options[0] not in available_options(state, actor, npcs)
            or not answer.text.strip()
        ):
            raise WorkflowError(
                "Choose exactly one printed effect and describe the actual connection."
            )
        if answer.options[0] in ("call_cockpit_guest", "call_gorgon_relay"):
            from girlframe.services.m3_mockingbird_communion import candidates

            if not candidates(game, c, state, action, answer.options[0]):
                raise WorkflowError("This original source has no eligible actual guest/Gorgon")
        group = _groups(action)[step]
        expected = int(action["actor_id"]) if group.owner == "actor" else _handler_controller(meta)
        if int(request["actor_id"]) != expected:
            raise WorkflowError("The actual printed chooser owns this effect.")
        meta["steps"].append(
            dict(
                option=answer.options[0],
                chooser=expected,
                account=answer.text,
                source_choice=request["id"],
            )
        )
        _request_effect(game, c, action, step)
        return
    selected = meta["steps"][step]
    if kind == "dive_effect":
        option = selected["option"]
        detail_owner = (
            _handler_controller(meta)
            if option in ("nearby_npcs_gain_void", "table_replaces_identity")
            else int(action["actor_id"])
        )
        if int(request["actor_id"]) != detail_owner:
            raise WorkflowError("The actual source-specific detail chooser owns this response.")
        if option in ("call_cockpit_guest", "call_gorgon_relay"):
            from girlframe.services.m3_mockingbird_communion import start

            _strict(answer, {"fields", "text"})
            if set(answer.fields) != {"target"}:
                raise WorkflowError("Choose the actual source guest or nearby Gorgon")
            start(game, c, state, action, step, request, answer.fields["target"], answer.text)
            return
        elif option == "call_reclassify_assets":
            from girlframe.services.m3_mockingbird_call import effect as classification_effect

            actor, _, _ = _context(action)
            selected["effect"] = classification_effect(state, actor, answer)
            _apply_effect(game, c, state, action, step, request)
            return
        elif option == "void_and_unmark_all":
            _strict(answer, {"text", "fields"})
            from girlframe.services.m3_sup import parse

            actor, _, _ = _context(action)
            if actor.kind == "pilot":
                from girlframe.services.m3_clone_am import prove_additional

                prove_additional(game, c, state, int(actor.entity))
            growth = parse(game, c, state, actor, answer.fields)
            if growth is None and set(answer.fields) not in ({"asset"}, {"asset", "storage"}):
                raise WorkflowError("Choose the actual uncorrupted Asset to rewrite.")
            if "storage" in answer.fields:
                if answer.fields["storage"] != "yes":
                    raise WorkflowError("Choose only the actual offered Void Storage destination")
                selected["store_void"] = True
            effect = Effect(
                account=selected["account"],
                asset=answer.fields.get("asset"),
                description=answer.text,
                growth=growth,
            )
        elif option == "erase_identity_and_table_question":
            _strict(answer, {"text", "fields"})
            if set(answer.fields) != {"identity"}:
                raise WorkflowError("Choose your actual ordinary Identity.")
            effect = Effect(
                account=selected["account"],
                identity=answer.fields["identity"],
                question=answer.text,
            )
        elif option == "nearby_npcs_gain_void":
            _strict(answer, {"fields"})
            effect = Effect(
                account=selected["account"],
                npcs=tuple(
                    NpcVoid.model_validate_json(json.dumps(dict(npc=k, manifestation=v)))
                    for k, v in answer.fields.items()
                ),
            )
        elif option == "table_replaces_identity":
            _strict(answer, {"text", "fields"})
            if set(answer.fields) != {"identity"}:
                raise WorkflowError("Propose the actual ordinary Identity slot.")
            effect = Effect(
                account=selected["account"],
                identity=answer.fields["identity"],
                replacement=answer.text,
            )
        else:
            _strict(answer, {"flag"})
            if answer.flag is not True:
                raise WorkflowError("Confirm the actual source cockpit subsumption.")
            effect = Effect(account=selected["account"])
        selected["effect"] = effect.model_dump(mode="json")
        if option == "table_replaces_identity":
            actor, handler, npcs = _context(action)
            rules.apply(
                state,
                actor,
                profiles(c, game.store.campaign_id),
                option,
                effect,
                action["id"],
                step,
                action["data"]["response_event"],
                piloting=action["data"]["prepared"]["piloting"],
                handler=handler,
                cast_npcs=npcs,
                handler_controller=_handler_controller(meta),
            )
            selected["proposal_revision"] = selected.get("proposal_revision", 0) + 1
            selected["agreements"] = {}
            for uid in meta["table"]:
                game.request(
                    c,
                    action,
                    uid,
                    "dive_table_agreement",
                    dict(step=step, proposal_revision=selected["proposal_revision"]),
                )
            return
        _apply_effect(game, c, state, action, step, request)
        return
    if kind == "dive_table_answer":
        if int(request["actor_id"]) not in meta["table"]:
            raise WorkflowError("Only an original table human owns this answer.")
        _strict(answer, {"text"})
        if not answer.text.strip() or len(answer.text) > 1200:
            raise WorkflowError("Each actual table human answers the question.")
        selected.setdefault("answers", {})[request["actor_id"]] = answer.text
        if len(selected["answers"]) == len(meta["table"]):
            _complete_step(game, c, state, action, step)
        return
    if kind == "dive_table_agreement":
        if int(request["actor_id"]) not in meta["table"]:
            raise WorkflowError("Only an original table human owns this agreement.")
        _strict(answer, {"flag", "text"})
        if answer.flag is None or body["proposal_revision"] != selected["proposal_revision"]:
            raise WorkflowError("Accept or reject the exact current table Identity proposal.")
        selected["agreements"][request["actor_id"]] = dict(
            accepted=answer.flag, account=answer.text
        )
        if len(selected["agreements"]) == len(meta["table"]):
            if all(x["accepted"] for x in selected["agreements"].values()):
                _apply_effect(game, c, state, action, step, request)
            else:
                _request_effect(game, c, action, step)
        return
    if kind == "dive_void_threshold":
        raise WorkflowError(
            "Resolve the actual source Void threshold; this is not an acknowledgment."
        )
    if kind == "dive_call":
        raise WorkflowError("Open the source-owned Call response; this is not an acknowledgment")
    raise WorkflowError("Resume the source-specific owned Dive response.")


def synchronize(game: "GameService", c: Connection, action: dict[str, Any], event: str) -> None:
    if action["data"]["dive"].get("handler_void_followups"):
        from girlframe.services.m3_dive_handler_void import synchronize as sync_handler

        sync_handler(game, c, action, event)
    table = t.m3["m3_required_work"]
    for item in action["data"]["dive"]["followups"]:
        if "continuation" not in item:
            continue
        if c.scalar(
            sa.select(table.c.id)
            .where(table.c.campaign_id == game.store.campaign_id, table.c.id == item["id"])
            .limit(1)
        ):
            continue
        related(
            c,
            game.store,
            dict(campaign_id=game.store.campaign_id, scene_id=action["scene_id"]),
            item["id"],
            int(item["owner"]["entity"]),
            int(item["owner"]["entity"]),
            "void_threshold",
            item,
            item["source_event"],
        )


def complete_void_continuation(
    game: "GameService",
    c: Connection,
    work_id: str,
    event: str,
    viewer: GuildViewer | None,
    key: str,
) -> None:
    """Only actual completed threshold work releases its original held Dive continuation."""
    from girlframe.engine.m3_void import FINAL

    table = t.m3["m3_required_work"]
    row = (
        c.execute(
            sa.select(table)
            .where(table.c.campaign_id == game.store.campaign_id, table.c.id == work_id)
            .order_by(table.c.revision.desc())
            .limit(1)
        )
        .mappings()
        .first()
    )
    if row is None or row["state"] != "resolved":
        raise WorkflowError("Finish the actual original Void threshold before resuming Dive.")
    body = json.loads(row["body_json"])
    action = game.action(c, body["source_action"])
    meta = action["data"].get("dive")
    if meta is None:
        raise WorkflowError("This consequence belongs to another actual source Play.")
    actual = next((x for x in meta["followups"] if x["id"] == work_id), None)
    state = load_state(c, game.store.campaign_id)
    threshold = next(
        (
            x
            for x in state.void_thresholds
            if work_id in x.source_works
            and x.actor.model_dump(mode="json") == meta["actor"]
            and x.stage in FINAL
        ),
        None,
    )
    if (
        actual is None
        or threshold is None
        or body.get("character") != meta["actor"]["incarnation"]
        or body.get("continuation") != actual["continuation"]
    ):
        raise WorkflowError(
            "SOURCE_DIVE_VOID_MISSING: recover the actual original completed threshold."
        )
    choices = t.m2["m2_choices"]
    continuation = next(
        (x for x in game.pending(c, action["id"]) if x["id"] == actual["continuation"]), None
    )
    if continuation is None:
        return
    c.execute(
        choices.update()
        .where(
            choices.c.campaign_id == game.store.campaign_id,
            choices.c.id == continuation["id"],
            choices.c.state == "pending",
        )
        .values(state="completed_by_work", revision=choices.c.revision + 1)
    )
    actual["completed_event"] = event
    _next(game, c, state, action)
    game.save_action(c, action)
    prior_index = c.scalar(
        sa.select(sa.func.max(t.events.c.event_index)).where(
            t.events.c.campaign_id == game.store.campaign_id,
            t.events.c.command_key == key,
        )
    )
    from girlframe.services.m3_janus_storage import continuation_actor

    completed_event = game.event(
        c,
        continuation_actor(game, c, event, viewer),
        key,
        "m3.dive_void_completed",
        state,
        action_id=action["id"],
        work_id=work_id,
        event_index=1 if prior_index is None else prior_index + 1,
    )
    if action["state"] == "complete" and action["data"].get("dormant_dive_source"):
        from girlframe.services.m3_battle_dormant import complete_dive

        complete_dive(game, c, action, completed_event, viewer, key)
    if action["state"] == "complete" and action["data"].get("bomb_collar_source"):
        from girlframe.services.m3_bomb_collar import complete_action

        complete_action(game, c, action, completed_event, key)


def prove_void_source(
    game: "GameService", c: Connection, first: dict[str, Any], body: dict[str, Any], actor: ActorRef
) -> None:
    """Prove the exact original corruption, not a guessed row label or current class."""
    try:
        action = game.action(c, body["source_action"])
        meta = action["data"]["dive"]
        actual = next(x for x in meta["followups"] if x["id"] == first["id"])
        if (
            first["kind"] != "void_threshold"
            or first["revision"] != 1
            or first["owner_id"] != actor.entity
            or first["subject_id"] != actor.entity
            or first["scene_id"] != action["scene_id"]
            or first["campaign_context"]
            or actor.model_dump(mode="json") != meta["actor"]
            or body["owner"] != meta["actor"]
            or body["character"] != actor.incarnation
            or any(
                body.get(k) != actual.get(k)
                for k in (
                    "source_action",
                    "source_choice",
                    "continuation",
                    "step",
                    "details",
                    "source_event",
                )
            )
            or first["event_id"] != actual["source_event"]
        ):
            raise ValueError()
        source = (
            c.execute(
                sa.select(t.events).where(
                    t.events.c.campaign_id == game.store.campaign_id,
                    t.events.c.id == first["event_id"],
                )
            )
            .mappings()
            .first()
        )
        payload = json.loads(source["payload_json"]) if source else {}
        if (
            source is None
            or source["kind"] != "m3.choice_resolved"
            or source["actor_id"] != actor.entity
            or payload.get("action_id") != action["id"]
            or payload.get("choice_id") != body["source_choice"]
        ):
            raise ValueError()
        choices, responses = t.m2["m2_choices"], t.m2["m2_responses"]
        response = c.execute(
            sa.select(
                choices.c.kind, choices.c.action_id, choices.c.body_json, responses.c.answer_json
            )
            .join(
                responses,
                sa.and_(
                    choices.c.campaign_id == responses.c.campaign_id,
                    choices.c.id == responses.c.choice_id,
                ),
            )
            .where(
                choices.c.campaign_id == game.store.campaign_id,
                choices.c.id == body["source_choice"],
                responses.c.event_id == first["event_id"],
                responses.c.actor_id == actor.entity,
            )
        ).first()
        if (
            response is None
            or response.kind != "dive_effect"
            or response.action_id != action["id"]
            or json.loads(response.body_json)["step"] != body["step"]
        ):
            raise ValueError()
        history = c.scalar(
            sa.select(t.m2["m2_state_history"].c.body_json).where(
                t.m2["m2_state_history"].c.campaign_id == game.store.campaign_id,
                t.m2["m2_state_history"].c.event_id == first["event_id"],
            )
        )
        original = GameState.model_validate_json(history) if history else None
        fact = (
            next(
                (
                    x
                    for x in original.facts
                    if x.get("kind") == "dive_effect"
                    and x.get("action") == action["id"]
                    and x.get("step") == str(body["step"])
                    and x.get("source_event") == first["event_id"]
                ),
                None,
            )
            if original
            else None
        )
        if fact is not None and fact["option"] == "call_reclassify_assets":
            from girlframe.services.m3_mockingbird_call import prove_classification_void

            assert original is not None
            prove_classification_void(
                original,
                actor,
                action,
                body,
                ChoiceAnswer.model_validate_json(response.answer_json),
            )
            return
        if (
            fact is None
            or fact["option"] != "void_and_unmark_all"
            or fact["actor"] != actor.model_dump_json()
        ):
            raise ValueError()
        effect = Effect.model_validate_json(fact["effect"])
        answer = ChoiceAnswer.model_validate_json(response.answer_json)
        if effect.asset != answer.fields.get("asset") or effect.description != answer.text:
            raise ValueError()
        sheet = original.sheets[actor.entity] if original else None
        family = body["details"]["family"]
        from girlframe.engine.m3_janus_storage import effective_assets

        actual_assets = effective_assets(original, actor) if original and sheet else ()
        family_assets = [x for x in actual_assets if x.family == family]
        actual_id: str | None
        if effect.growth is not None:
            from girlframe.services.m3_sup import prove_growth

            assert original is not None
            grown = prove_growth(game, c, original, actor, first["event_id"])
            if grown is None or grown.choice != effect.growth:
                raise ValueError()
            expected = dict(
                sup_name=effect.growth.name,
                sup_family=effect.growth.family,
                sup_replace=effect.growth.replace or "",
            )
            if answer.fields != expected:
                raise ValueError()
            actual_id = grown.asset
        else:
            actual_id = effect.asset
        asset = next((x for x in actual_assets if x.id == actual_id), None)
        if (
            sheet is None
            or sheet.character_id != actor.incarnation
            or asset is None
            or not asset.void
            or asset.description != effect.description
            or family not in ("girl", "frame")
            or not family_assets
            or not all(x.void for x in family_assets)
        ):
            raise ValueError()
    except (ValueError, KeyError, StopIteration, TypeError):
        raise WorkflowError(
            "SOURCE_DIVE_VOID_MISSING: recover the actual original corruption event."
        ) from None
