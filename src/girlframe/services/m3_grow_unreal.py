"""Pay the original Growth cost and apply the actual tier's separate mutations."""

import json
from typing import TYPE_CHECKING, Any, cast
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_grow_unreal as rules
from girlframe.engine.m2 import ChoiceAnswer, GameState
from girlframe.engine.m3_actor_state import ActorRef, ActorView, SceneCast
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_gorgon_play_state import Declaration
from girlframe.engine.m3_hallucinations import Roll
from girlframe.engine.m3_janus_storage import alter, effective_assets
from girlframe.engine.m3_sentinel_shell import holds
from girlframe.engine.m3_world import damage_gorgon, update
from girlframe.engine.m3_world_state import CorePlan, Gorgon
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_work import related
from girlframe.services.onboarding import WorkflowError

if TYPE_CHECKING:
    from girlframe.services.m2_game import GameService

HEAT = "gorgon_unreal_heat"
GROW = "gorgon_unreal_grow"
DAMAGE = "gorgon_unreal_damage"
VOID = "gorgon_unreal_void"
THRESHOLD = "gorgon_unreal_threshold"


def _views(
    game: "GameService", c: Connection, state: GameState, action: dict[str, Any]
) -> tuple[ActorView, ActorView, Gorgon]:
    meta = action["data"]["gorgon_play"]
    cast_view = SceneCast.model_validate_json(json.dumps(meta["cast"]))
    if state.world is None or not any(
        x.id == cast_view.id and x.open and x.roles == cast_view.roles for x in state.scene_casts
    ):
        raise WorkflowError("Recover the actual original Growth scene")
    bound = profiles(c, game.store.campaign_id)
    actor = resolve(
        state, ActorRef.model_validate(meta["actor"]), bound, require_current_profile=False
    )
    girl = resolve(
        state, ActorRef.model_validate(meta["target"]), bound, require_current_profile=False
    )
    body = next((x for x in state.world.gorgons if x.id == actor.ref.entity), None)
    if (
        body is None
        or not body.alive
        or "growth" not in body.types
        or actor.controller != meta["controller"]
        or girl.ref.kind != "pilot"
        or not girl.alive
        or not any(x.actor == girl.ref and x.controller == girl.controller for x in cast_view.roles)
    ):
        raise WorkflowError("Recover the actual living Growth and original Girl")
    return actor, girl, body


def start(game: "GameService", c: Connection, state: GameState, action: dict[str, Any]) -> None:
    actor, girl, _ = _views(game, c, state, action)
    declared = Declaration.model_validate_json(
        json.dumps(action["data"]["gorgon_play"]["declaration"])
    )
    if not rules.original_target(actor, girl) or declared.shed is None or state.world is None:
        raise WorkflowError("Use the original Growth, its actual Asset and reachable original Girl")
    event = action["data"]["response_event"]
    state.world = rules.sacrifice(state.world, actor.ref, declared.shed)
    rules.put(
        state,
        rules.Episode(
            action=action["id"],
            scene=action["scene_id"],
            source=actor.ref,
            girl=girl.ref,
            sacrificed=declared.shed,
            event=event,
        ),
    )
    game.request(c, action, girl.controller, HEAT)


def _void_assets(state: GameState, girl: ActorView) -> dict[str, str]:
    return {
        x.id: x.name
        for x in effective_assets(state, girl.ref)
        if not x.void and (x.family == "girl" or girl.piloting is True)
    }


def _guards(body: Gorgon) -> dict[str, str]:
    existing = set(body.core_plan.assets)
    if (
        len(existing) == 2
        and not any(x.id in existing and x.damaged for x in body.assets)
        and not any(x.id in existing for x in body.destroyed_assets)
    ):
        return {}
    return {x.id: x.name for x in body.assets if not x.damaged and x.id not in existing}


def _available(
    state: GameState, actor: ActorView, girl: ActorView, body: Gorgon
) -> dict[rules.Option, str]:
    unavailable = set()
    if actor.cell is None or girl.cell is None or actor.cell == girl.cell:
        unavailable.add("distance")
    if girl.inside_frame is not True or girl.occupied_frame_instance is None:
        unavailable.add("cockpit")
    if not _guards(body):
        unavailable.add("reinforce")
    if not _void_assets(state, girl):
        unavailable.add("thoughts")
    return {key: label for key, label in rules.OPTIONS.items() if key not in unavailable}


def _actual_intact(body: Gorgon) -> dict[str, str]:
    if body.protected_asset is not None and any(
        x.id == body.protected_asset and not x.damaged for x in body.assets
    ):
        return {}
    return {x.id: x.name for x in body.assets if not x.damaged}


def _finish_or_offer(
    game: "GameService",
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    case: rules.Episode,
    body: Gorgon,
    event: str,
) -> None:
    if case.roll is not None and case.roll.result == "high" and _actual_intact(body):
        game.request(c, action, int(case.girl.entity), DAMAGE)
    else:
        rules.put(state, case.model_copy(update=dict(completed=event)))
        action["data"]["result"]["growth_resolved"] = True


def apply(
    game: "GameService",
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    row: dict[str, Any],
    answer: ChoiceAnswer,
) -> None:
    if row["kind"] == THRESHOLD:
        raise WorkflowError("Finish the actual source Void consequence in the private controls")
    actor, girl, body = _views(game, c, state, action)
    episode = rules.get(state, action["id"])
    event = action["data"]["response_event"]
    if episode.completed is not None or episode.source != actor.ref or episode.girl != girl.ref:
        raise WorkflowError("Recover the original paid episode and affected Girl")
    owner = actor.controller if row["kind"] == GROW else girl.controller
    if row["actor_id"] != str(owner) or answer.denied or answer.member is not None:
        raise WorkflowError("Use the original role's exact choice")
    if row["kind"] == HEAT:
        heat = answer.number
        sheet = state.sheets[girl.ref.entity]
        if (
            heat is None
            or not 0 <= heat <= sheet.heat
            or answer.flag is not None
            or answer.options
            or answer.fields
            or answer.text
            or episode.roll is not None
            or heat
            and holds(state, girl.ref, "trapped")
        ):
            raise WorkflowError("Only the original target can pay her actual owned Heat")
        roll = Roll(faces=game.dice.roll(), heat=heat, event=event)
        if heat:
            sheet.heat -= heat
            sheet.revision += 1
        rules.put(state, episode.model_copy(update=dict(roll=roll)))
        game.request(c, action, actor.controller, GROW)
    elif row["kind"] == GROW:
        _grow(game, c, state, action, actor, girl, body, episode, answer, event)
    elif row["kind"] == VOID:
        _gain_void(game, c, state, action, girl, body, episode, answer, event)
    elif row["kind"] == DAMAGE:
        if episode.roll is None or episode.roll.result != "high":
            raise WorkflowError("Recover the actual original high result")
        if (
            len(answer.options) > 1
            or not set(answer.options) <= set(_actual_intact(body))
            or answer.fields
            or answer.text
            or answer.flag is not None
            or answer.number is not None
        ):
            raise WorkflowError("Choose one actual Growth Asset to damage or decline")
        damage = answer.options[0] if answer.options else None
        if damage:
            assert state.world is not None
            state.world = damage_gorgon(state.world, actor.ref.entity, damage, indirect=False)
        rules.put(state, episode.model_copy(update=dict(completed=event, damaged_asset=damage)))
        action["data"]["result"]["growth_resolved"] = True
    else:
        raise WorkflowError("Recover the original Grow Unreal decision")


def _grow(
    game: "GameService",
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    actor: ActorView,
    girl: ActorView,
    body: Gorgon,
    episode: rules.Episode,
    answer: ChoiceAnswer,
    event: str,
) -> None:
    roll = episode.roll
    if roll is None or episode.effect_event is not None:
        raise WorkflowError("Use this original paid and rolled Grow Unreal choice")
    count = {"low": 4, "mid": 1, "high": 2}[roll.result]
    choices = cast(tuple[rules.Option, ...], answer.options)
    if (
        len(choices) != count
        or not set(choices) <= set(_available(state, actor, girl, body))
        or not answer.text.strip()
        or answer.flag is not None
        or answer.number is not None
        or answer.fields.keys() != ({"guard"} if "reinforce" in choices else set())
    ):
        raise WorkflowError("Choose the exact rolled number of actual growth effects")
    changes: dict[str, Any] = {}
    if "distance" in choices or "cockpit" in choices:
        changes.update(cell=girl.cell, position_event=event)
    if "voidspace" in choices:
        changes.update(cell=None, position_event=event)
    if "reinforce" in choices:
        selected = answer.fields["guard"]
        if selected not in _guards(body):
            raise WorkflowError("Choose a real new intact asset to protect the original Core")
        intact = {x.id for x in body.assets if not x.damaged}
        existing = tuple(x for x in body.core_plan.assets if x in intact)
        changes.update(
            core_plan=CorePlan(assets=(*existing, selected), weakness=body.core_plan.weakness),
            exposed=False,
        )
    if changes:
        assert state.world is not None
        body = body.model_copy(update=changes)
        state.world = update(
            state.world, gorgons=tuple(body if x.id == body.id else x for x in state.world.gorgons)
        )
    updated = episode.model_copy(
        update=dict(
            options=choices,
            account=answer.text.strip(),
            effect_event=event,
            frame_instance=girl.occupied_frame_instance if "cockpit" in choices else None,
        )
    )
    rules.put(state, updated)
    if "thoughts" in choices:
        game.request(c, action, girl.controller, VOID)
    else:
        _finish_or_offer(game, c, state, action, updated, body, event)


def _gain_void(
    game: "GameService",
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    girl: ActorView,
    body: Gorgon,
    episode: rules.Episode,
    answer: ChoiceAnswer,
    event: str,
) -> None:
    from girlframe.engine.m3_void import FINAL

    if (
        "thoughts" not in episode.options
        or episode.void_event
        or len(answer.options) != 1
        or answer.options[0] not in _void_assets(state, girl)
        or not answer.text.strip()
        or answer.fields
        or answer.flag is not None
        or answer.number is not None
        or any(x.actor == girl.ref and x.stage not in FINAL for x in state.void_thresholds)
    ):
        raise WorkflowError("Choose an actual uncorrupted Asset for the conceptual Void gain")
    selected = answer.options[0]
    family = next(x.family for x in state.sheets[girl.ref.entity].assets if x.id == selected)
    changed, effects = alter(
        state,
        girl.ref,
        selected,
        answer.text.strip(),
        action["id"],
        event,
        piloting=girl.piloting is True,
    )
    for field in GameState.model_fields:
        setattr(state, field, getattr(changed, field))
    applied = any(x.id == selected and x.void for x in effective_assets(state, girl.ref))
    work = None
    if applied and any(
        x.kind == f"{family}_void_threshold" or family == "frame" and x.kind == "mockingbird_resist"
        for x in effects
    ):
        work = f"{action['id']}:growth:void:{family}"
        action["data"]["gorgon_play"]["followups"].append(work)
    updated = episode.model_copy(
        update=dict(
            void_asset=selected if applied else None,
            void_event=event,
            void_work=work,
        )
    )
    rules.put(state, updated)
    if not work:
        _finish_or_offer(game, c, state, action, updated, body, event)


def project(
    game: "GameService",
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    row: dict[str, Any],
) -> dict[str, Any]:
    kind = row["kind"].removeprefix("gorgon_")
    if row["kind"] == THRESHOLD:
        return dict(kind=kind, work=json.loads(row["body_json"])["work_id"])
    actor, girl, body = _views(game, c, state, action)
    episode = rules.get(state, action["id"])
    if row["kind"] == HEAT:
        return dict(kind=kind, heat=girl.heat)
    if row["kind"] == GROW:
        assert episode.roll is not None
        return dict(
            kind=kind,
            options=_available(state, actor, girl, body),
            guards=_guards(body),
            count={"low": 4, "mid": 1, "high": 2}[episode.roll.result],
            roll=episode.roll.model_dump(mode="json"),
        )
    assets = _void_assets(state, girl) if row["kind"] == VOID else _actual_intact(body)
    return dict(kind=kind, assets=assets)


def materialize(
    game: "GameService",
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    event: str,
) -> None:
    if not any(x.get("kind") == rules.KIND and x.get("id") == action["id"] for x in state.facts):
        return
    episode = rules.get(state, action["id"])
    if episode.void_event != event or not episode.void_work:
        return
    work = t.m3["m3_required_work"]
    if c.scalar(
        sa.select(work.c.id).where(
            work.c.campaign_id == game.store.campaign_id,
            work.c.id == episode.void_work,
        )
    ):
        return
    owner = int(episode.girl.entity)
    related(
        c,
        game.store,
        action,
        episode.void_work,
        owner,
        owner,
        "void_threshold",
        dict(
            owner=episode.girl.model_dump(mode="json"),
            character=episode.girl.incarnation,
            source_action=action["id"],
            source_pdf=19,
            reason=rules.KIND,
            details=dict(family=episode.void_work.rsplit(":", 1)[-1]),
        ),
        event,
    )
    game.request(c, action, owner, THRESHOLD, dict(work_id=episode.void_work))


def prove_void(
    game: "GameService",
    c: Connection,
    state: GameState,
    row: dict[str, Any],
    body: dict[str, Any],
    girl: ActorRef,
) -> None:
    from girlframe.services.m3_gorgon_play import GorgonPlayService

    action = game.action(c, body["source_action"])
    original = GorgonPlayService(game).source(c, action)
    episode = rules.get(state, action["id"])
    responses, choices = t.m2["m2_responses"], t.m2["m2_choices"]
    answer = c.scalar(
        sa.select(responses.c.answer_json)
        .join(
            choices,
            sa.and_(
                responses.c.campaign_id == choices.c.campaign_id,
                responses.c.choice_id == choices.c.id,
            ),
        )
        .where(
            responses.c.campaign_id == game.store.campaign_id,
            responses.c.event_id == row["event_id"],
            responses.c.actor_id == girl.entity,
            choices.c.kind == VOID,
            choices.c.action_id == action["id"],
        )
    )
    if (
        original["kind"] != rules.PLAY
        or episode.girl != girl
        or episode.void_event != row["event_id"]
        or episode.void_work != row["id"]
        or episode.scene != row["scene_id"]
        or episode.void_asset is None
        or "thoughts" not in episode.options
        or episode.effect_event is None
        or answer is None
        or json.loads(answer).get("options") != [episode.void_asset]
    ):
        raise WorkflowError("Recover the actual paid Growth Play and original conceptual Void gain")


def complete_void(
    game: "GameService",
    c: Connection,
    work: str,
    parent: str,
    event: str,
    viewer: Any,
    key: str,
) -> None:
    from girlframe.services.m2_state import load_state
    from girlframe.services.m3_gorgon_play import GorgonPlayService

    action = game.action(c, parent)
    held = [
        x
        for x in game.pending(c, parent)
        if x["kind"] == THRESHOLD and json.loads(x["body_json"]).get("work_id") == work
    ]
    if len(held) != 1:
        raise WorkflowError("Recover the exact original Growth Void consequence")
    row = held[0]
    choices = t.m2["m2_choices"]
    c.execute(
        choices.update()
        .where(
            choices.c.campaign_id == game.store.campaign_id,
            choices.c.id == row["id"],
        )
        .values(state="completed_by_work", revision=row["revision"] + 1)
    )
    state = load_state(c, game.store.campaign_id)
    episode = rules.get(state, parent)
    body = (
        next((x for x in state.world.gorgons if x.id == episode.source.entity), None)
        if state.world
        else None
    )
    original = state.sheets.get(episode.girl.entity)
    if (
        body is not None
        and body.alive
        and original is not None
        and original.character_id == episode.girl.incarnation
        and episode.roll is not None
        and episode.roll.result == "high"
        and _actual_intact(body)
    ):
        game.request(c, action, int(episode.girl.entity), DAMAGE)
    else:
        finished = str(uuid4())
        rules.put(state, episode.model_copy(update=dict(completed=finished)))
        index = c.scalar(
            sa.select(sa.func.max(t.events.c.event_index)).where(
                t.events.c.campaign_id == game.store.campaign_id,
                t.events.c.command_key == key,
            )
        )
        game.event(
            c,
            viewer.user_id if viewer else episode.girl.entity,
            key,
            "m3.growth_void_completed",
            state,
            event_id=finished,
            event_index=index + 1 if index is not None else 0,
            source_action=action["id"],
            source_event=event,
        )
        action["data"]["result"]["growth_resolved"] = True
        game.save_action(c, action)
    GorgonPlayService(game).synchronize(c, action, event, viewer, key)
