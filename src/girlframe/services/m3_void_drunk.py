"""A nearby original Acolyte can follow a Dive and apply her own printed effects."""

import json
from typing import TYPE_CHECKING, Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_ancillary as ancillary
from girlframe.engine import m3_ancillary_void as ancillary_void
from girlframe.engine import m3_dive as dive_rules
from girlframe.engine.m2 import ChoiceAnswer, GameState
from girlframe.engine.m3_actor_bonds import make_helpless
from girlframe.engine.m3_actor_state import ActorRef, ActorView, CastRole, SceneCast
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_dive_state import NpcVoid
from girlframe.engine.m3_leviathan_arrival import external_pose
from girlframe.engine.m3_leviathan_arrival_state import ExternalPose
from girlframe.engine.m3_passengers import passenger_view
from girlframe.services.m3_access import Access
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_battle import _cast, _visible
from girlframe.services.m3_consume_support import knowledge_allowed
from girlframe.services.onboarding import WorkflowError

if TYPE_CHECKING:
    from girlframe.services.m2_game import GameService

RULE = "ancillary.abyssal-acolyte.void-drunk"
KIND = "abyssal_void_drunk"


def _enabled(game: "GameService") -> bool:
    gate = Access(game.store)
    if gate.registry is None:
        return False
    try:
        for identity in (ancillary.RULE, ancillary.STARTERS["ABYSSAL ACOLYTE"].rule):
            gate.registry.require_available(identity)
        gate.require_specialist_rule(RULE)
    except (ValueError, WorkflowError):
        return False
    return True


def _people(
    game: "GameService",
    c: Connection,
    state: GameState,
    action: dict[str, Any],
) -> tuple[ActorView, dict[str, CastRole]]:
    meta = action["data"]["dive"]
    actor = ActorRef.model_validate(meta["actor"])
    bound = profiles(c, game.store.campaign_id)
    actual = resolve(state, actor, bound, require_current_profile=False)
    original = SceneCast.model_validate_json(json.dumps(meta["cast"]))
    current = _cast(game, c, state, int(action["channel_id"]))
    people: dict[str, CastRole] = {}
    if (
        actor.kind != "pilot"
        or actual.cell is None
        or actual.offstage_source
        or current.id != original.id
    ):
        return actual, people
    for member in current.roles:
        role = ancillary.find(state, member.actor)
        if (
            member not in original.roles
            or member.controller not in action["data"]["participants"]
            or role is None
            or role.draft.book != "ABYSSAL ACOLYTE"
            or role.controller != member.controller
            or role.controller == actual.controller
        ):
            continue
        try:
            other = resolve(state, member.actor, bound)
        except ValueError:
            continue
        if (
            other.alive
            and other.controller == member.controller
            and not other.offstage_source
            and other.custody in (None, "free", "converted")
            and other.cell == actual.cell
        ):
            people[member.actor.token] = member
    return actual, people


def _tags(state: GameState, target: ActorRef, controller: int, scene: str) -> dict[str, str]:
    return {
        x.id: x.label
        for x in state.sheets[target.entity].tags
        if not x.marked and x.scene_used != scene and controller in x.observers
    }


def _shadow_pose(state: GameState, actor: CastRole, target: ActorView) -> ExternalPose | None:
    pose = external_pose(state, actor.actor)
    if (
        pose is None
        or pose.owner != actor.controller
        or pose.girl_cell is None
        or pose.girl_cell != target.cell
        or passenger_view(state, actor.actor) is not None
    ):
        return None
    return pose


def _npc_pool(
    game: "GameService",
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    actor: CastRole,
    target: ActorView,
) -> dict[str, str]:
    if state.world is None:
        return {}
    original = SceneCast.model_validate_json(json.dumps(action["data"]["dive"]["cast"]))
    current = _cast(game, c, state, int(action["channel_id"]))
    exact = {
        r.actor.entity: r.controller
        for r in current.roles
        if r.actor.kind == "npc" and r in original.roles
    }
    known = {}
    for npc in state.world.npcs:
        if (
            exact.get(npc.id) != npc.controller
            or not npc.alive
            or npc.cell != target.cell
            or "director" in npc.jobs
        ):
            continue
        ref = ActorRef(kind="npc", entity=npc.id)
        if _visible(state, ref, actor.controller) and knowledge_allowed(state, ref):
            known[npc.id] = npc.name
    return known if len(known) <= 12 else {}


def open_choices(
    game: "GameService",
    c: Connection,
    state: GameState,
    action: dict[str, Any],
) -> bool:
    meta = action["data"]["dive"]
    if (
        "void_drunk" in meta
        or meta["steps"]
        or meta["completed_steps"]
        or not _enabled(game)
        or ActorRef.model_validate(meta["actor"]).kind != "pilot"
    ):
        return False
    _, people = _people(game, c, state, action)
    if not people:
        return False
    meta["void_drunk"] = []
    for token, role in people.items():
        game.request(c, action, role.controller, "dive_void_drunk", dict(acolyte=token))
    return True


def _owned(
    game: "GameService",
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    request: dict[str, Any],
) -> tuple[ActorView, CastRole]:
    if not _enabled(game):
        raise WorkflowError("Recover the original approved Void-Drunk choice.")
    target, people = _people(game, c, state, action)
    token = json.loads(request["body_json"])["acolyte"]
    ref = people.get(token)
    if ref is None or int(request["actor_id"]) != ref.controller:
        raise WorkflowError("Recover the actual nearby original Acolyte role.")
    return target, ref


def project(
    game: "GameService",
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    request: dict[str, Any],
) -> dict[str, Any]:
    target, actor = _owned(game, c, state, action, request)
    primary = action["data"]["result"]["tier"] != "low"
    return dict(
        target=target.label,
        tags=_tags(state, target.ref, actor.controller, action["scene_id"]),
        shadow=_shadow_pose(state, actor, target) is not None,
        primary=1 if primary else 0,
        primary_npcs=primary and bool(_npc_pool(game, c, state, action, actor, target)),
        primary_assets={x.id: x.name for x in ancillary_void.gains(state, actor.actor)}
        if primary
        else {},
    )


def select(
    game: "GameService",
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    request: dict[str, Any],
    answer: ChoiceAnswer,
) -> None:
    target, actor = _owned(game, c, state, action, request)
    latching = answer.options in (("latch",), ("shadow",), ("smother",))
    primary = latching and action["data"]["result"]["tier"] != "low"
    asset = answer.fields.get("primary_asset")
    npc_primary = answer.fields == {"primary_kind": "npcs"}
    if primary:
        if npc_primary:
            if answer.text or not _npc_pool(game, c, state, action, actor, target):
                raise WorkflowError("Recover the original nearby NPCs eligible for Void.")
        elif (
            set(answer.fields) != {"primary_asset"}
            or not answer.text.strip()
            or asset not in {x.id for x in ancillary_void.gains(state, actor.actor)}
        ):
            raise WorkflowError("Choose one actual eligible Asset and describe its Void rewrite.")
    elif answer.fields or answer.text:
        raise WorkflowError("This actual choice takes no primary effect.")
    if (
        answer.options not in (("pass",), ("latch",), ("shadow",), ("smother",))
        or answer.options == ("shadow",)
        and _shadow_pose(state, actor, target) is None
        or answer.number is not None
        or answer.member is not None
        or answer.flag is not None
        or (answer.denied and answer.options != ("latch",))
        or len(answer.denied) > 1
        or answer.denied
        and answer.denied[0]
        not in _tags(
            state,
            target.ref,
            actor.controller,
            action["scene_id"],
        )
    ):
        raise WorkflowError("Pass or choose an available Void-Drunk effect for the actual Dive.")
    current = action["data"]["dive"]["void_drunk"]
    current.append(
        dict(
            actor=actor.actor.token,
            controller=actor.controller,
            choice=request["id"],
            source=action["data"]["response_event"],
            latch=latching,
            tag=answer.denied[0] if answer.denied else None,
            shadow=answer.options == ("shadow",),
            smother=answer.options == ("smother",),
            primary_asset=asset,
            primary_rewrite=answer.text.strip() if asset else None,
            primary_npcs=npc_primary,
        )
    )
    if npc_primary:
        from girlframe.services.m3_dive import _handler_controller

        game.request(
            c,
            action,
            _handler_controller(action["data"]["dive"]),
            "dive_void_drunk_npcs",
            dict(acolyte=actor.actor.token, choice=request["id"]),
        )


def _npc_choice(
    game: "GameService",
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    request: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, str]]:
    from girlframe.services.m3_dive import _handler_controller

    meta = action["data"]["dive"]
    body = json.loads(request["body_json"])
    target, people = _people(game, c, state, action)
    actor = people.get(body["acolyte"])
    selection = next((x for x in meta.get("void_drunk", ()) if x["choice"] == body["choice"]), None)
    if (
        not _enabled(game)
        or int(request["actor_id"]) != _handler_controller(meta)
        or actor is None
        or selection is None
        or selection["actor"] != actor.actor.token
        or not selection.get("primary_npcs")
    ):
        raise WorkflowError("Recover the actual Handler and original Acolyte Void choice.")
    return selection, _npc_pool(game, c, state, action, actor, target)


def npc_project(
    game: "GameService",
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    request: dict[str, Any],
) -> dict[str, Any]:
    _, options = _npc_choice(game, c, state, action, request)
    return dict(npcs=options)


def npc_response(
    game: "GameService",
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    request: dict[str, Any],
    answer: ChoiceAnswer,
) -> None:
    selected, options = _npc_choice(game, c, state, action, request)
    response = action["data"]["response_event"]
    if (
        answer.options == ("reopen",)
        and not answer.fields
        and not any(
            (
                answer.text,
                answer.denied,
                answer.number is not None,
                answer.member is not None,
                answer.flag is not None,
            )
        )
    ):
        meta = action["data"]["dive"]
        meta["void_drunk"].remove(selected)
        game.request(
            c, action, selected["controller"], "dive_void_drunk", dict(acolyte=selected["actor"])
        )
        return
    if (
        not options
        or set(answer.fields) != set(options)
        or answer.options
        or answer.denied
        or answer.text
        or answer.number is not None
        or answer.member is not None
        or answer.flag is not None
    ):
        raise WorkflowError("Choose one actual manifestation for every eligible original NPC.")
    selected["manifestations"] = [
        NpcVoid.model_validate(dict(npc=npc, manifestation=value)).model_dump(mode="json")
        for npc, value in answer.fields.items()
    ]
    selected["npc_event"] = response


def intercept(
    game: "GameService",
    c: Connection,
    action: dict[str, Any],
    key: str,
) -> bool:
    from girlframe.engine import m3_void as void
    from girlframe.services.m2_state import load_state
    from girlframe.services.m3_void import complete, prepare_threshold

    meta = action["data"]["dive"]
    choices = tuple(x for x in meta.get("void_drunk", ()) if x.get("smother"))
    if not choices or not meta.get("thresholds_opened") or not _enabled(game):
        return False
    work = tuple(x for x in meta["followups"] if x["details"]["family"] == "girl")
    if len(work) != 1 or work[0].get("completed_event"):
        return False
    state = load_state(c, game.store.campaign_id)
    target, people = _people(game, c, state, action)
    follower = next((x for x in choices if x["actor"] in people), None)
    if follower is None:
        return False
    body, threshold = prepare_threshold(c, game, work[0]["id"], state)
    if (
        threshold.source_works != (work[0]["id"],)
        or threshold.stage not in ("allured", "questions")
        or threshold.forced_by
        or threshold.free_identity
        or threshold.answers
        or threshold.enclosed
    ):
        return False
    event = str(uuid4())
    body = void.smother_apometanoia(body, threshold.id, target.ref, action["id"], event)
    actual = people[follower["actor"]]
    body.facts.append(
        dict(
            kind="void_drunk_smothered",
            action=action["id"],
            threshold=threshold.id,
            follower=actual.actor.token,
            target=target.ref.token,
            choice=follower["choice"],
            source=follower["source"],
            event=event,
        )
    )
    prior = c.scalar(
        sa.select(sa.func.max(t.events.c.event_index)).where(
            t.events.c.campaign_id == game.store.campaign_id,
            t.events.c.command_key == key,
        )
    )
    game.event(
        c,
        actual.controller,
        key,
        "m3.void_drunk_smothered",
        body,
        event_id=event,
        event_index=1 if prior is None else prior + 1,
        action_id=action["id"],
        work_id=work[0]["id"],
    )
    complete(c, game, void.threshold(body, threshold.id), event, None, key)
    return True


def complete(
    game: "GameService",
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    event: str,
) -> bool:
    selected = action["data"]["dive"].get("void_drunk", [])
    if not any(x["latch"] for x in selected):
        return True
    target, people = _people(game, c, state, action)
    if not _enabled(game):
        raise WorkflowError("Recover this original Void-Drunk scope before applying its effect.")
    for result in selected:
        if not result["latch"] or result.get("settled"):
            continue
        if target.subsumed or target.vitals_active is False:
            result["settled"] = "no_resurfacing"
            continue
        actor = people.get(result["actor"])
        if actor is None:
            result["settled"] = "expired"
            continue
        tag_id = result["tag"]
        primary_asset = result.get("primary_asset")
        shadow = _shadow_pose(state, actor, target) if result.get("shadow") else None
        if (
            tag_id
            and tag_id not in _tags(state, target.ref, actor.controller, action["scene_id"])
            or result.get("shadow")
            and shadow is None
            or primary_asset is not None
            and not any(x.id == primary_asset for x in ancillary_void.gains(state, actor.actor))
        ):
            selected.remove(result)
            game.request(
                c, action, actor.controller, "dive_void_drunk", dict(acolyte=actor.actor.token)
            )
            return False
        if primary_asset is not None:
            ancillary_void.gain(
                state, actor.actor, primary_asset, result["primary_rewrite"], unmark=True
            )
        if result.get("primary_npcs"):
            manifestations = tuple(NpcVoid.model_validate(x) for x in result["manifestations"])
            pool = _npc_pool(game, c, state, action, actor, target)
            if not pool or set(pool) != {x.npc for x in manifestations}:
                from girlframe.services.m3_dive import _handler_controller

                game.request(
                    c,
                    action,
                    _handler_controller(action["data"]["dive"]),
                    "dive_void_drunk_npcs",
                    dict(acolyte=result["actor"], choice=result["choice"]),
                )
                return False
            from girlframe.services.m3_dive import _context, _handler_controller

            _, handler, _ = _context(action)
            dive_rules.mark_npc_void(
                state,
                manifestations,
                result["npc_event"],
                handler,
                _handler_controller(action["data"]["dive"]),
            )
        if tag_id:
            changed = make_helpless(state, target.ref, actor.actor, event)
            state.helpless_conditions = changed.helpless_conditions
            sheet = state.sheets[target.ref.entity]
            tag = next(x for x in sheet.tags if x.id == tag_id)
            tag.marked, tag.scene_used = True, action["scene_id"]
            sheet.revision += 1
        if shadow is not None:
            emerged = shadow.model_copy(
                update=dict(
                    mode="outside_frame",
                    girl_cell=target.cell,
                    position_event=event,
                    account="Emerged beside the original diver through Void-Drunk.",
                )
            )
            state.external_poses = [
                emerged if x.actor == actor.actor else x for x in state.external_poses
            ]
        state.facts.append(
            dict(
                kind=KIND,
                action=action["id"],
                actor=actor.actor.token,
                target=target.ref.token,
                choice=result["choice"],
                event=event,
                tag=tag_id or "",
                **(dict(primary_asset=primary_asset) if primary_asset else {}),
                **(dict(primary_npcs=result["npc_event"]) if result.get("primary_npcs") else {}),
                **(dict(emergence="shadow") if shadow is not None else {}),
            )
        )
        result["settled"] = event
    return True
