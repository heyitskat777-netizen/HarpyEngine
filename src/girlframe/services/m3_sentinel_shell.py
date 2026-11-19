"""Actual Sentinel reach, private owned roll, containment, and source-bound Void."""

import json
from typing import TYPE_CHECKING, Any, Literal, cast

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_sentinel_shell as rules
from girlframe.engine.m2 import ChoiceAnswer, GameState
from girlframe.engine.m3_actor_state import ActorRef, ActorView, SceneCast
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_janus_storage import alter, effective_assets
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_work import related
from girlframe.services.onboarding import WorkflowError

if TYPE_CHECKING:
    from girlframe.services.m2_game import GameService

TIE = "gorgon_shell_tie"
HEAT = "gorgon_shell_heat"
CHOOSE = "gorgon_shell_choose"
VOID = "gorgon_shell_void"
THRESHOLD = "gorgon_shell_threshold"


def _views(
    game: "GameService", c: Connection, state: GameState, action: dict[str, Any]
) -> tuple[ActorView, ActorView, tuple[ActorRef, ...]]:
    meta = action["data"]["gorgon_play"]
    cast_view = SceneCast.model_validate_json(json.dumps(meta["cast"]))
    if not any(
        current.id == cast_view.id and current.open and current.roles == cast_view.roles
        for current in state.scene_casts
    ):
        raise WorkflowError("Recover the original Sentinel scene and actual target")
    bound = profiles(c, game.store.campaign_id)
    source = resolve(
        state, ActorRef.model_validate(meta["actor"]), bound, require_current_profile=False
    )
    girl = resolve(
        state, ActorRef.model_validate(meta["target"]), bound, require_current_profile=False
    )
    near = rules.nearest(
        source,
        tuple(
            resolve(state, x.actor, bound, require_current_profile=False)
            for x in cast_view.roles
            if x.actor.kind == "pilot"
        ),
    )
    if not source.alive or girl.ref not in near or source.controller != meta["controller"]:
        raise WorkflowError("Use the original Sentinel and its actual closest Girl")
    return source, girl, near


def start(game: "GameService", c: Connection, state: GameState, action: dict[str, Any]) -> None:
    _, girl, near = _views(game, c, state, action)
    meta = action["data"]["gorgon_play"]
    if len(near) > 1:
        game.request(c, action, meta["procedural_gm"], TIE)
    else:
        game.request(c, action, girl.controller, HEAT)


def _void_assets(state: GameState, girl: ActorView) -> dict[str, str]:
    return {
        x.id: x.name
        for x in effective_assets(state, girl.ref)
        if not x.void and (x.family == "girl" or girl.inside_frame is True)
    }


def _choices(state: GameState, girl: ActorView) -> tuple[str, ...]:
    available = ["trapped"]
    if girl.inside_frame is True and girl.frame_instance == girl.occupied_frame_instance:
        available.append("cockpit")
    if _void_assets(state, girl):
        available.append("void")
    return tuple(available)


def _roll(action: dict[str, Any]) -> rules.Roll:
    return rules.Roll.model_validate_json(json.dumps(action["data"]["gorgon_play"]["shell_roll"]))


def apply(
    game: "GameService",
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    row: dict[str, Any],
    answer: ChoiceAnswer,
) -> None:
    kind = row["kind"]
    if kind == THRESHOLD:
        raise WorkflowError("Resolve the original Sentinel Void threshold in its private controls")
    source, girl, near = _views(game, c, state, action)
    meta, event = action["data"]["gorgon_play"], action["data"]["response_event"]
    if answer.denied or answer.member is not None:
        raise WorkflowError("Use the actual Sentinel source's owned choice")
    if kind == TIE:
        if (
            len(near) < 2
            or str(meta["procedural_gm"]) != row["actor_id"]
            or answer.flag is None
            or not answer.text.strip()
            or answer.options
            or answer.fields
            or answer.number is not None
        ):
            raise WorkflowError("The human GM must verify the nearest tied Girl in the scene")
        if answer.flag:
            meta["shell_tie"] = event
            game.request(c, action, girl.controller, HEAT)
        return

    if kind == HEAT:
        heat = answer.number
        sheet = state.sheets[girl.ref.entity]
        if (
            row["actor_id"] != str(girl.controller)
            or heat is None
            or not 0 <= heat <= sheet.heat
            or answer.options
            or answer.text
            or answer.fields
            or answer.flag is not None
            or "shell_roll" in meta
            or len(near) > 1
            and not meta.get("shell_tie")
        ):
            raise WorkflowError("Only the actual closest Girl spends her own Heat")
        if heat and rules.holds(state, girl.ref, "trapped"):
            raise WorkflowError("The actual trapped Girl cannot spend Heat until freed")
        saved = rules.Roll(faces=game.dice.roll(), heat=heat, event=event)
        if heat:
            sheet.heat -= heat
            sheet.revision += 1
        meta["shell_roll"] = saved.model_dump(mode="json")
        chooser = girl.controller if saved.result == "mid" else source.controller
        game.request(c, action, chooser, CHOOSE)
        return

    if kind == VOID:
        if row["actor_id"] != str(girl.controller):
            raise WorkflowError("Only the original affected Girl rewrites this Asset")
        _apply_void(state, action, girl, answer, event)
        return

    saved = _roll(action)
    picks = 2 if saved.result == "low" else 1
    chooser = girl.controller if saved.result == "mid" else source.controller
    if (
        kind != CHOOSE
        or str(chooser) != row["actor_id"]
        or len(answer.options) != picks
        or not set(answer.options) <= set(_choices(state, girl))
        or not answer.text.strip()
        or answer.fields
        or answer.flag is not None
        or answer.number is not None
    ):
        raise WorkflowError("Choose the printed number of actual available ensnarement effects")
    shell = None
    assert state.world is not None and source.cell is not None
    if saved.result != "mid":
        state.world, shell = rules.close(state.world, source.ref, action["id"])
    if "cockpit" in answer.options:
        # Preserve the existing occupied Frame, cockpit position, and vitals.
        state.placements = [
            x.model_copy(update=dict(mode="inside_frame", source_event=event))
            if x.actor == girl.ref and x.mode == "piloting"
            else x
            for x in state.placements
        ]
    record = rules.Ensnarement(
        action=action["id"],
        scene=action["scene_id"],
        source=source.ref,
        girl=girl.ref,
        origin=source.cell,
        roll=saved,
        event=event,
        shell_asset=shell,
        effects=cast(tuple[Literal["trapped", "cockpit", "void"], ...], answer.options),
        frame_instance=girl.frame_instance,
    )
    rules.put(state, record)
    action["data"]["result"].update(shell_closed=bool(shell), ensnared=True)
    if "void" in record.effects:
        game.request(c, action, girl.controller, VOID)


def _apply_void(
    state: GameState,
    action: dict[str, Any],
    girl: ActorView,
    answer: ChoiceAnswer,
    event: str,
) -> None:
    from girlframe.engine.m3_void import FINAL

    original = next((x for x in rules.records(state) if x.action == action["id"]), None)
    if (
        original is None
        or original.girl != girl.ref
        or original.void_event is not None
        or "void" not in original.effects
        or len(answer.options) != 1
        or answer.options[0] not in _void_assets(state, girl)
        or not answer.text.strip()
        or answer.fields
        or answer.flag is not None
        or answer.number is not None
        or any(x.actor == girl.ref and x.stage not in FINAL for x in state.void_thresholds)
    ):
        raise WorkflowError("Use your actual original Void gain after any pending threshold")
    selected = answer.options[0]
    family = next(x.family for x in state.sheets[girl.ref.entity].assets if x.id == selected)
    changed, pending = alter(
        state,
        girl.ref,
        selected,
        answer.text.strip(),
        action["id"],
        event,
        piloting=girl.inside_frame is True,
    )
    for field in GameState.model_fields:
        setattr(state, field, getattr(changed, field))
    applied = any(x.id == selected and x.void for x in effective_assets(state, girl.ref))
    followup = None
    if applied and any(
        x.kind == f"{family}_void_threshold" or family == "frame" and x.kind == "mockingbird_resist"
        for x in pending
    ):
        followup = f"{action['id']}:shell:void:{family}"
        action["data"]["gorgon_play"]["followups"].append(followup)
    rules.put(
        state,
        original.model_copy(
            update=dict(
                void_asset=selected if applied else None, void_event=event, void_work=followup
            )
        ),
    )


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
    _, girl, _ = _views(game, c, state, action)
    if row["kind"] == HEAT:
        return dict(kind=kind, heat=girl.heat)
    if row["kind"] == CHOOSE:
        saved = _roll(action)
        return dict(
            kind=kind,
            options=_choices(state, girl),
            tier=saved.result,
            roll=saved.model_dump(mode="json"),
            count=2 if saved.result == "low" else 1,
        )
    if row["kind"] == VOID:
        return dict(kind=kind, assets=_void_assets(state, girl))
    return dict(kind=kind)


def materialize(
    game: "GameService",
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    event: str,
) -> None:
    saved = next(
        (x for x in rules.records(state) if x.action == action["id"] and x.void_event == event),
        None,
    )
    if saved is None or not saved.void_work:
        return
    table = t.m3["m3_required_work"]
    if c.scalar(
        sa.select(table.c.id).where(
            table.c.campaign_id == game.store.campaign_id,
            table.c.id == saved.void_work,
        )
    ):
        return
    owner = int(saved.girl.entity)
    related(
        c,
        game.store,
        action,
        saved.void_work,
        owner,
        owner,
        "void_threshold",
        dict(
            owner=saved.girl.model_dump(mode="json"),
            character=saved.girl.incarnation,
            source_action=action["id"],
            source_pdf=19,
            reason=rules.KIND,
            details=dict(family=saved.void_work.rsplit(":", 1)[-1]),
        ),
        event,
    )
    game.request(c, action, owner, THRESHOLD, dict(work_id=saved.void_work))


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
    saved = next((x for x in rules.records(state) if x.action == action["id"]), None)
    responses, choices = t.m2["m2_responses"], t.m2["m2_choices"]
    answer = c.scalar(
        sa.select(responses.c.answer_json)
        .join(
            choices,
            sa.and_(
                choices.c.campaign_id == responses.c.campaign_id,
                choices.c.id == responses.c.choice_id,
            ),
        )
        .where(
            responses.c.campaign_id == game.store.campaign_id,
            responses.c.event_id == row["event_id"],
            responses.c.actor_id == girl.entity,
            choices.c.action_id == action["id"],
            choices.c.kind == VOID,
        )
    )
    if (
        original["kind"] != rules.PLAY
        or saved is None
        or saved.girl != girl
        or saved.void_work != row["id"]
        or saved.void_event != row["event_id"]
        or saved.scene != row["scene_id"]
        or answer is None
        or json.loads(answer).get("options") != [saved.void_asset]
    ):
        raise WorkflowError("Recover the actual original Sentinel Void gain")


def complete_void(
    game: "GameService",
    c: Connection,
    work: str,
    parent: str,
    event: str,
    viewer: Any,
    key: str,
) -> None:
    from girlframe.services.m3_gorgon_play import GorgonPlayService

    action = game.action(c, parent)
    held = [
        x
        for x in game.pending(c, parent)
        if x["kind"] == THRESHOLD and json.loads(x["body_json"]).get("work_id") == work
    ]
    if len(held) != 1:
        raise WorkflowError("Recover the exact pending Sentinel Void consequence")
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
    GorgonPlayService(game).synchronize(c, action, event, viewer, key)
