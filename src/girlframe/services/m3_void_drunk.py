"""A nearby original Acolyte can follow a Dive and apply her own printed effects."""

import json
from typing import TYPE_CHECKING, Any

from sqlalchemy import Connection

from girlframe.engine import m3_ancillary as ancillary
from girlframe.engine import m3_ancillary_void as ancillary_void
from girlframe.engine.m2 import ChoiceAnswer, GameState
from girlframe.engine.m3_actor_bonds import make_helpless
from girlframe.engine.m3_actor_state import ActorRef, ActorView, CastRole, SceneCast
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_leviathan_arrival import external_pose
from girlframe.engine.m3_leviathan_arrival_state import ExternalPose
from girlframe.engine.m3_passengers import passenger_view
from girlframe.services.m3_access import Access
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_battle import _cast
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
    latching = answer.options in (("latch",), ("shadow",))
    primary = latching and action["data"]["result"]["tier"] != "low"
    asset = answer.fields.get("primary_asset")
    if primary:
        if (
            set(answer.fields) != {"primary_asset"}
            or not answer.text.strip()
            or asset not in {x.id for x in ancillary_void.gains(state, actor.actor)}
        ):
            raise WorkflowError("Choose one actual eligible Asset and describe its Void rewrite.")
    elif answer.fields or answer.text:
        raise WorkflowError("This actual choice takes no primary effect.")
    if (
        answer.options not in (("pass",), ("latch",), ("shadow",))
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
            primary_asset=asset,
            primary_rewrite=answer.text.strip() if asset else None,
        )
    )


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
                **(dict(emergence="shadow") if shadow is not None else {}),
            )
        )
        result["settled"] = event
    return True
