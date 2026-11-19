"""Private infection choices through actual damage and ordinary Void."""

import json
from typing import TYPE_CHECKING, Any, cast
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_parasite_infection as rules
from girlframe.engine.m2 import ChoiceAnswer, GameState
from girlframe.engine.m3_actor_state import ActorRef, ActorView, SceneCast
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_hallucinations import Roll
from girlframe.engine.m3_janus_storage import alter, effective_assets
from girlframe.engine.m3_sentinel_shell import holds
from girlframe.services.m2_state import load_state
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_collateral import latest
from girlframe.services.m3_work import related
from girlframe.services.onboarding import WorkflowError

if TYPE_CHECKING:
    from girlframe.services.m2_game import GameService
    from girlframe.services.read_only_bot import GuildViewer

DAMAGE = "gorgon_infection_damage"
HEAT = "gorgon_infection_heat"
LOSS = "gorgon_infection_loss"
VOID = "gorgon_infection_void"
THRESHOLD = "gorgon_infection_threshold"
LOW_REVIEW = "gorgon_infection_low_review"
LOSSES = {
    "body": "A small part of your body",
    "memory": "A precious memory",
    "emotion": "An emotion",
}


def _originals(
    game: "GameService", c: Connection, state: GameState, action: dict[str, Any]
) -> tuple[ActorView, ActorView]:
    original = action["data"]["gorgon_play"]
    cast_view = SceneCast.model_validate_json(json.dumps(original["cast"]))
    if state.world is None or not any(
        x.id == cast_view.id and x.open and x.roles == cast_view.roles for x in state.scene_casts
    ):
        raise WorkflowError("Recover the actual original Parasite scene")
    bound = profiles(c, game.store.campaign_id)
    body = resolve(
        state, ActorRef.model_validate(original["actor"]), bound, require_current_profile=False
    )
    girl = resolve(
        state, ActorRef.model_validate(original["target"]), bound, require_current_profile=False
    )
    if (
        body.controller != original["controller"]
        or not any(x.actor == girl.ref and x.controller == girl.controller for x in cast_view.roles)
        or not any(x.id == body.ref.entity and "parasite" in x.types for x in state.world.gorgons)
    ):
        raise WorkflowError("Recover the actual original Parasite and Girl")
    return body, girl


def start(game: "GameService", c: Connection, state: GameState, action: dict[str, Any]) -> None:
    body, girl = _originals(game, c, state, action)
    if not rules.reachable(state, body, girl) or rules.get(state, action["id"]) is not None:
        raise WorkflowError("Use the original Parasite and the living Girl in the same square")
    rules.put(
        state,
        rules.Infection(
            action=action["id"],
            scene=action["scene_id"],
            source=body.ref,
            girl=girl.ref,
            event=action["data"]["response_event"],
        ),
    )
    game.request(c, action, girl.controller, DAMAGE)


def apply(
    game: "GameService",
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    row: dict[str, Any],
    answer: ChoiceAnswer,
) -> None:
    body, girl = _originals(game, c, state, action)
    case = rules.get(state, action["id"])
    kind, event = row["kind"], action["data"]["response_event"]
    if (
        case is None
        or case.source != body.ref
        or case.girl != girl.ref
        or case.resolved is not None
        or case.interrupted is not None
        or not body.alive
        or not girl.alive
    ):
        raise WorkflowError("Recover the active infection and its original bodies")
    if kind == LOW_REVIEW:
        raise WorkflowError("The original low result awaits private human review of sheet control")
    if (
        row["actor_id"] != str(girl.controller)
        or answer.denied
        or answer.member is not None
        or answer.flag is not None
        or answer.fields
    ):
        raise WorkflowError("Use the original Girl's exact owned infection response")
    if kind == DAMAGE:
        if not rules.assets(state, girl, damaged_connection=True) and answer == ChoiceAnswer():
            rules.put(state, case.model_copy(update=dict(interrupted=event)))
            action["data"]["result"]["parasite_infection_interrupted"] = True
            return
        _damage(game, c, state, action, case, body, girl, answer, event)
    elif kind == HEAT:
        _roll(game, c, state, action, case, girl, answer, event)
    elif kind == LOSS:
        if (
            case.roll is None
            or case.roll.result != "mid"
            or len(answer.options) != 1
            or answer.options[0] not in LOSSES
            or not answer.text.strip()
            or answer.number is not None
        ):
            raise WorkflowError("Give the original Girl's chosen actual small loss")
        rules.put(
            state,
            case.model_copy(
                update=dict(
                    loss=cast(rules.Loss, answer.options[0]),
                    loss_account=answer.text.strip(),
                    resolved=event,
                )
            ),
        )
        action["data"]["result"]["parasite_fought_off"] = True
    elif kind == VOID:
        _void(game, c, state, action, case, girl, answer, event)
    else:
        raise WorkflowError("Resume the actual outstanding infection consequence")


def _damage(
    game: "GameService",
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    case: rules.Infection,
    body: ActorView,
    girl: ActorView,
    answer: ChoiceAnswer,
    event: str,
) -> None:
    from girlframe.engine.m3_janus_pandora import require_can_harm
    from girlframe.services.m3_battle import damage_actor

    if (
        case.damage_event
        or not rules.reachable(state, body, girl)
        or len(answer.options) != 1
        or answer.options[0] not in rules.assets(state, girl, damaged_connection=True)
        or answer.text
        or answer.number is not None
    ):
        raise WorkflowError("Choose one actual intact Voided Asset belonging to the original Girl")
    selected = answer.options[0]
    require_can_harm(state, body.ref, girl.ref)
    changed, work = damage_actor(
        game,
        c,
        state,
        target=girl.ref,
        asset_id=selected,
        source_action=action["id"],
        source_work=None,
        event=event,
        actor=body.ref,
        chooser_controller=body.controller,
        occurrence=rules.KIND,
        physical_blow=False,
    )
    for field in GameState.model_fields:
        setattr(state, field, getattr(changed, field))
    rules.put(
        state,
        case.model_copy(
            update=dict(
                damaged_asset=selected,
                damage_event=event,
                damage_work=work,
            )
        ),
    )
    action["data"]["gorgon_play"]["followups"].extend(work)


def _roll(
    game: "GameService",
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    case: rules.Infection,
    girl: ActorView,
    answer: ChoiceAnswer,
    event: str,
) -> None:
    heat = answer.number
    sheet = state.sheets[girl.ref.entity]
    if (
        case.roll is not None
        or not case.damage_event
        or heat is None
        or not 0 <= heat <= sheet.heat
        or answer.options
        or answer.text
        or heat
        and holds(state, girl.ref, "trapped")
    ):
        raise WorkflowError("Only the original target can spend her actual Heat on this infection")
    roll = Roll(faces=game.dice.roll(), heat=heat, event=event)
    if heat:
        sheet.heat -= heat
        sheet.revision += 1
    rules.put(state, case.model_copy(update=dict(roll=roll)))
    if roll.result == "low":
        game.request(c, action, action["data"]["gorgon_play"]["procedural_gm"], LOW_REVIEW)
    else:
        game.request(c, action, girl.controller, LOSS if roll.result == "mid" else VOID)


def _void(
    game: "GameService",
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    case: rules.Infection,
    girl: ActorView,
    answer: ChoiceAnswer,
    event: str,
) -> None:
    from girlframe.engine.m3_void import FINAL

    if (
        case.roll is None
        or case.roll.result != "high"
        or case.void_event is not None
        or len(answer.options) != 1
        or answer.number is not None
        or not answer.text.strip()
        or answer.options[0] not in rules.assets(state, girl, damaged_connection=False)
        or any(x.actor == girl.ref and x.stage not in FINAL for x in state.void_thresholds)
    ):
        raise WorkflowError("Choose and describe the original Girl's actual incoming Void")
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
        work = f"{action['id']}:infection:void:{family}"
        action["data"]["gorgon_play"]["followups"].append(work)
    rules.put(
        state,
        case.model_copy(
            update=dict(
                void_asset=selected if applied else None,
                void_event=event,
                void_work=work,
                surgery_required=True,
                resolved=None if work else event,
            )
        ),
    )
    if not work:
        action["data"]["result"]["parasite_partial_infection"] = True


def project(
    game: "GameService",
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    row: dict[str, Any],
) -> dict[str, Any]:
    case = rules.get(state, action["id"])
    if case is None:
        raise WorkflowError("Recover the original infection")
    kind = row["kind"]
    result: dict[str, Any] = {"kind": kind.removeprefix("gorgon_")}
    if kind == THRESHOLD:
        return result | {"work": case.void_work}
    _, girl = _originals(game, c, state, action)
    if kind in (DAMAGE, VOID):
        result["assets"] = rules.assets(state, girl, damaged_connection=kind == DAMAGE)
    if kind == HEAT:
        result["heat"] = (
            0 if holds(state, girl.ref, "trapped") else state.sheets[girl.ref.entity].heat
        )
    if kind in (LOSS, LOW_REVIEW) and case.roll:
        result["roll"] = case.roll.model_dump(mode="json")
    return result


def materialize(
    game: "GameService",
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    event: str,
    viewer: "GuildViewer | None",
    key: str,
) -> None:
    case = rules.get(state, action["id"])
    if case is None:
        return
    if case.void_event == event and case.void_work:
        _materialize_threshold(game, c, action, case, event)
    meta = action["data"]["gorgon_play"]
    if (
        case.damage_event is None
        or case.roll is not None
        or case.interrupted
        or meta.get("infection_damage_advanced")
        or any(latest(game, c, identity)["state"] != "resolved" for identity in case.damage_work)
    ):
        return
    meta["infection_damage_advanced"] = True
    original = state.sheets.get(case.girl.entity)
    if (
        original is not None
        and original.character_id == case.girl.incarnation
        and state.world is not None
        and any(x.id == case.source.entity and x.alive for x in state.world.gorgons)
    ):
        source, girl = _originals(game, c, state, action)
        if (
            rules.reachable(state, source, girl)
            and any(
                x.id == case.damaged_asset and x.damaged and x.void
                for x in effective_assets(state, girl.ref)
            )
            and any(
                x.get("kind") == "battle_damage_stage"
                and x.get("event") == case.damage_event
                and x.get("applied") == girl.ref.model_dump_json()
                and x.get("asset") == case.damaged_asset
                for x in state.facts
            )
        ):
            game.request(c, action, girl.controller, HEAT)
            return
    recorded = str(uuid4())
    rules.put(state, case.model_copy(update=dict(interrupted=recorded)))
    _event(game, c, state, case, recorded, event, viewer, key, "m3.parasite_infection_interrupted")
    action["data"]["result"]["parasite_infection_interrupted"] = True


def _materialize_threshold(
    game: "GameService",
    c: Connection,
    action: dict[str, Any],
    case: rules.Infection,
    event: str,
) -> None:
    assert case.void_work is not None
    work = t.m3["m3_required_work"]
    if c.scalar(
        sa.select(work.c.id).where(
            work.c.campaign_id == game.store.campaign_id,
            work.c.id == case.void_work,
        )
    ):
        return
    owner = int(case.girl.entity)
    related(
        c,
        game.store,
        action,
        case.void_work,
        owner,
        owner,
        "void_threshold",
        dict(
            owner=case.girl.model_dump(mode="json"),
            character=case.girl.incarnation,
            source_action=action["id"],
            source_pdf=19,
            reason=rules.KIND,
            details=dict(family=case.void_work.rsplit(":", 1)[-1]),
        ),
        event,
    )
    game.request(c, action, owner, THRESHOLD, dict(work_id=case.void_work))


def _event(
    game: "GameService",
    c: Connection,
    state: GameState,
    case: rules.Infection,
    recorded: str,
    source: str,
    viewer: "GuildViewer | None",
    key: str,
    kind: str,
) -> None:
    index = c.scalar(
        sa.select(sa.func.max(t.events.c.event_index)).where(
            t.events.c.campaign_id == game.store.campaign_id,
            t.events.c.command_key == key,
        )
    )
    game.event(
        c,
        viewer.user_id if viewer else case.girl.entity,
        key,
        kind,
        state,
        event_id=recorded,
        event_index=index + 1 if index is not None else 0,
        source_event=source,
        source_action=case.action,
    )


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
    case = rules.get(state, action["id"])
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
        or case is None
        or case.girl != girl
        or case.roll is None
        or case.roll.result != "high"
        or case.void_event != row["event_id"]
        or case.void_work != row["id"]
        or case.scene != row["scene_id"]
        or not case.surgery_required
        or case.void_asset is None
        or answer is None
        or json.loads(answer).get("options") != [case.void_asset]
    ):
        raise WorkflowError(
            "Recover the original high infection result and its actual owned Void response"
        )


def complete_void(
    game: "GameService",
    c: Connection,
    work: str,
    parent: str,
    event: str,
    viewer: "GuildViewer | None",
    key: str,
) -> None:
    from girlframe.services.m3_gorgon_play import GorgonPlayService

    state = load_state(c, game.store.campaign_id)
    case = rules.get(state, parent)
    held = [
        x
        for x in game.pending(c, parent)
        if x["kind"] == THRESHOLD and json.loads(x["body_json"]).get("work_id") == work
    ]
    if case is None or case.void_work != work or case.resolved or len(held) != 1:
        raise WorkflowError("Recover the actual original infection Void threshold")
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
    recorded = str(uuid4())
    rules.put(state, case.model_copy(update=dict(resolved=recorded)))
    _event(
        game, c, state, case, recorded, event, viewer, key, "m3.parasite_infection_void_resolved"
    )
    action = game.action(c, parent)
    action["data"]["result"]["parasite_partial_infection"] = True
    game.save_action(c, action)
    GorgonPlayService(game).synchronize(c, action, event, viewer, key)
