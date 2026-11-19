"""Original known Tag, paid target roll, and the Incubus's printed consequences."""

import json
from typing import TYPE_CHECKING, Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_incubus_conditioning as rules
from girlframe.engine.m2 import ChoiceAnswer, GameState, TagState
from girlframe.engine.m3_actor_state import ActorRef, ActorView, SceneCast
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_beneath import rejection_blocked
from girlframe.engine.m3_gorgon_play_state import Declaration
from girlframe.engine.m3_hallucinations import Roll
from girlframe.engine.m3_janus_storage import alter, effective_assets
from girlframe.engine.m3_sentinel_shell import holds
from girlframe.engine.m3_void_state import VoidThreshold
from girlframe.services.m2_choices import ChoiceEngine
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_work import related
from girlframe.services.onboarding import WorkflowError

if TYPE_CHECKING:
    from girlframe.services.m2_game import GameService

HEAT = "gorgon_conditioning_heat"
ERASE = "gorgon_conditioning_erase"
REVIEW = "gorgon_conditioning_review"
VOID = "gorgon_conditioning_void"
THRESHOLD = "gorgon_conditioning_threshold"
REBIRTH = "incubus_conditioning_rebirth"


def _views(
    game: "GameService", c: Connection, state: GameState, action: dict[str, Any]
) -> tuple[ActorView, ActorView]:
    meta = action["data"]["gorgon_play"]
    scene = SceneCast.model_validate_json(json.dumps(meta["cast"]))
    if not any(x.id == scene.id and x.open and x.roles == scene.roles for x in state.scene_casts):
        raise WorkflowError("Recover the original Incubus and Girl in their actual scene")
    bound = profiles(c, game.store.campaign_id)
    source = resolve(
        state, ActorRef.model_validate(meta["actor"]), bound, require_current_profile=False
    )
    girl = resolve(
        state, ActorRef.model_validate(meta["target"]), bound, require_current_profile=False
    )
    if (
        source.controller != meta["controller"]
        or not source.alive
        or source.cell is None
        or not girl.alive
        or source.offstage_source
        or girl.offstage_source
        or source.cell != girl.cell
        or not any(x.actor == girl.ref and x.controller == girl.controller for x in scene.roles)
    ):
        raise WorkflowError("Recover the original Incubus source and actual Girl's current reach")
    return source, girl


def start(game: "GameService", c: Connection, state: GameState, action: dict[str, Any]) -> None:
    source, girl = _views(game, c, state, action)
    meta = action["data"]["gorgon_play"]
    declared = Declaration.model_validate_json(json.dumps(meta["declaration"]))
    tag = next((x for x in rules.available(state, source, girl) if x.id == declared.tag), None)
    if tag is None:
        raise WorkflowError("Choose an original unmarked Tag known to this Incubus")
    ChoiceEngine(game).prove_tag_setter(c, state, girl.controller, tag)
    tag.marked = True
    state.sheets[girl.ref.entity].revision += 1
    event = action["data"]["response_event"]
    rules.put(
        state,
        rules.Exposure(
            action=action["id"],
            scene=action["scene_id"],
            source=source.ref,
            girl=girl.ref,
            tag=tag.id,
            mark_event=event,
        ),
    )
    game.request(c, action, girl.controller, HEAT)


def _source(
    game: "GameService", c: Connection, state: GameState, action: dict[str, Any]
) -> tuple[rules.Exposure, ActorView, TagState]:
    source, girl = _views(game, c, state, action)
    current = rules.get(state, action["id"])
    sheet = state.sheets[girl.ref.entity]
    tag = next((x for x in sheet.tags if x.id == current.tag and x.marked), None)
    if (
        current.source != source.ref
        or current.girl != girl.ref
        or current.scene != action["scene_id"]
        or current.completed is not None
        or tag is None
    ):
        raise WorkflowError("Recover the actual marked Tag and original exposure")
    return current, girl, tag


def apply(
    game: "GameService",
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    row: dict[str, Any],
    answer: ChoiceAnswer,
) -> None:
    if row["kind"] == THRESHOLD:
        raise WorkflowError("Resolve the original Incubus Void threshold in its private controls")
    if row["kind"] == REVIEW:
        if json.loads(row["body_json"]).get("ended_original"):
            raise WorkflowError("The original transformed body needs its actual response port")
        _review_low(game, c, state, action, row, answer)
        return
    current, girl, tag = _source(game, c, state, action)
    event = action["data"]["response_event"]
    if row["kind"] == REVIEW:
        raise WorkflowError(
            "Resolve the saved result's actual source consequence before closing it"
        )
    if row["kind"] == VOID:
        if row["actor_id"] != str(girl.controller):
            raise WorkflowError("The affected original Girl owns the Void gain")
        _apply_void(game, c, state, action, current, girl, answer, event)
        return
    if (
        row["actor_id"] != str(girl.controller)
        or answer.options
        or answer.denied
        or answer.fields
        or answer.member is not None
        or answer.text
    ):
        raise WorkflowError("Only the original Girl makes this owned choice")
    sheet = state.sheets[girl.ref.entity]
    if row["kind"] == HEAT:
        amount = answer.number
        if (
            amount is None
            or not 0 <= amount <= sheet.heat
            or answer.flag is not None
            or current.roll is not None
            or amount
            and holds(state, girl.ref, "trapped")
        ):
            raise WorkflowError("Spend only current Heat this original Girl is allowed to pay")
        roll = Roll(faces=game.dice.roll(), heat=amount, event=event)
        if amount:
            sheet.heat -= amount
            sheet.revision += 1
        rules.put(state, current.model_copy(update=dict(roll=roll)))
        if roll.result == "mid":
            game.request(c, action, girl.controller, ERASE)
        elif roll.result == "high":
            game.request(c, action, girl.controller, VOID)
        else:
            game.request(c, action, action["data"]["gorgon_play"]["procedural_gm"], REVIEW)
        return
    if (
        row["kind"] != ERASE
        or current.roll is None
        or current.roll.result != "mid"
        or answer.number is not None
        or answer.flag is None
    ):
        raise WorkflowError("Resolve the exact original mid result")
    if answer.flag:
        if rejection_blocked(state, girl.controller, tag.id):
            raise WorkflowError(
                "This marked Tag has a separate source protection requiring adjudication"
            )
        sheet.tags = [x for x in sheet.tags if x.id != tag.id]
        sheet.revision += 1
    rules.put(state, current.model_copy(update=dict(completed=event, tag_erased=answer.flag)))
    action["data"]["result"]["conditioning_resolved"] = True


def project(
    game: "GameService",
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    row: dict[str, Any],
) -> dict[str, Any]:
    if row["kind"] == THRESHOLD:
        return dict(kind="conditioning_threshold", work=json.loads(row["body_json"])["work_id"])
    if row["kind"] == REVIEW and json.loads(row["body_json"]).get("ended_original"):
        return dict(kind="conditioning_review")
    current, girl, tag = _source(game, c, state, action)
    kind = row["kind"].removeprefix("gorgon_")
    if row["kind"] == HEAT:
        return dict(kind=kind, heat=girl.heat, tag=tag.label)
    if row["kind"] == VOID:
        return dict(kind=kind, tag=tag.label, assets=_available_void(state, girl))
    if row["kind"] == REVIEW:
        return dict(
            kind=kind,
            tag=tag.label,
            can_transform=girl.inside_frame is True
            and girl.occupied_frame_instance == girl.frame_instance,
        )
    assert current.roll is not None
    return dict(
        kind=kind,
        tag=tag.label,
        roll=current.roll.model_dump(mode="json"),
        tier=current.roll.result,
    )


def _review_low(
    game: "GameService",
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    row: dict[str, Any],
    answer: ChoiceAnswer,
) -> None:
    from girlframe.engine.m3_void import FINAL

    case, girl, _ = _source(game, c, state, action)
    meta = action["data"]["gorgon_play"]
    if (
        case.roll is None
        or case.roll.result != "low"
        or case.rebirth_event is not None
        or str(meta["procedural_gm"]) != row["actor_id"]
        or answer.flag is not True
        or not answer.text.strip()
        or answer.options
        or answer.fields
        or answer.denied
        or answer.member is not None
        or answer.number is not None
    ):
        raise WorkflowError("The actual human GM must verify the immediate original outcome")
    if (
        girl.inside_frame is not True
        or girl.frame_instance is None
        or girl.occupied_frame_instance != girl.frame_instance
        or girl.custody not in (None, "free")
        or girl.vitals_active is False
        or state.sheets[girl.ref.entity].medical_state != "fit"
        or any(x.actor == girl.ref and x.stage not in FINAL for x in state.void_thresholds)
    ):
        raise WorkflowError("Recover the actual uninterrupted original in-Frame body for rebirth")
    event = action["data"]["response_event"]
    work = f"{action['id']}:incubus:rebirth"
    state.void_thresholds.append(
        VoidThreshold(
            id="void:" + work,
            actor=girl.ref,
            frame_instance=girl.frame_instance,
            family="frame",
            source_event=event,
            source_action=action["id"],
            source_works=(work,),
            sheet_json=state.sheets[girl.ref.entity].model_dump_json(),
            stage="rebirth",
            enclosed=True,
            forced_by="incubus_conditioning",
        )
    )
    rules.put(state, case.model_copy(update=dict(rebirth_event=event, void_work=work)))
    meta["followups"].append(work)


def _available_void(state: GameState, girl: ActorView) -> dict[str, str]:
    return {
        x.id: x.name
        for x in effective_assets(state, girl.ref)
        if not x.void and (x.family == "girl" or girl.piloting is True)
    }


def _apply_void(
    game: "GameService",
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    exposure: rules.Exposure,
    girl: ActorView,
    choice: ChoiceAnswer,
    event: str,
) -> None:
    from girlframe.engine.m3_void import FINAL

    if (
        exposure.roll is None
        or exposure.roll.result != "high"
        or exposure.void_event
        or len(choice.options) != 1
        or choice.options[0] not in _available_void(state, girl)
        or not choice.text.strip()
        or choice.denied
        or choice.fields
        or choice.flag is not None
        or choice.member is not None
        or choice.number is not None
        or any(x.actor == girl.ref and x.stage not in FINAL for x in state.void_thresholds)
    ):
        raise WorkflowError("Choose an actual uncorrupted Asset after resolving other thresholds")
    selected = choice.options[0]
    family = next(x.family for x in state.sheets[girl.ref.entity].assets if x.id == selected)
    changed, effects = alter(
        state,
        girl.ref,
        selected,
        choice.text.strip(),
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
        work = f"{action['id']}:incubus:void:{family}"
        action["data"]["gorgon_play"]["followups"].append(work)
    updated = exposure.model_copy(
        update=dict(void_event=event, void_asset=selected if applied else None, void_work=work)
    )
    rules.put(state, updated)
    if work is None:
        stage_response(game, c, state, action, updated)


def stage_response(
    game: "GameService",
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    exposure: rules.Exposure,
) -> None:
    from girlframe.services.m3_gorgon_runtime import _request

    if exposure.void_event is None or exposure.completed is not None:
        raise WorkflowError("Resolve the original owned Void gain before the immediate Play")
    original = state.sheets.get(exposure.girl.entity)
    if original is None or original.character_id != exposure.girl.incarnation:
        game.request(
            c,
            action,
            action["data"]["gorgon_play"]["procedural_gm"],
            REVIEW,
            dict(ended_original=True),
        )
        return
    _request(
        game,
        c,
        action,
        int(exposure.girl.entity),
        "response_play",
        actor=exposure.girl.model_dump(mode="json"),
        conditioning_tag=exposure.tag,
    )


def materialize(
    game: "GameService",
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    event: str,
) -> None:
    if not any(x.get("kind") == rules.KIND and x.get("id") == action["id"] for x in state.facts):
        return
    case = rules.get(state, action["id"])
    if event not in (case.void_event, case.rebirth_event) or not case.void_work:
        return
    table = t.m3["m3_required_work"]
    if c.scalar(
        sa.select(table.c.id).where(
            table.c.campaign_id == game.store.campaign_id, table.c.id == case.void_work
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
            reason=REBIRTH if case.rebirth_event == event else rules.KIND,
            details=dict(
                family="frame" if case.rebirth_event == event else case.void_work.rsplit(":", 1)[-1]
            ),
        ),
        event,
    )
    game.request(c, action, owner, THRESHOLD, dict(work_id=case.void_work))


def prove_void(
    game: "GameService",
    c: Connection,
    historical: GameState,
    row: dict[str, Any],
    body: dict[str, Any],
    girl: ActorRef,
) -> None:
    from girlframe.services.m3_gorgon_play import GorgonPlayService

    action = game.action(c, body["source_action"])
    original = GorgonPlayService(game).source(c, action)
    case = rules.get(historical, action["id"])
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
        or case.girl != girl
        or case.void_work != row["id"]
        or case.void_event != row["event_id"]
        or case.scene != row["scene_id"]
        or case.roll is None
        or case.roll.result != "high"
        or answer is None
        or json.loads(answer).get("options") != [case.void_asset]
    ):
        raise WorkflowError("Recover the actual paid Incubus roll and original Void gain")


def prove_rebirth(
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
    threshold = next((x for x in state.void_thresholds if x.source_works == (row["id"],)), None)
    responses, choices = t.m2["m2_responses"], t.m2["m2_choices"]
    review = c.scalar(
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
            responses.c.actor_id == str(original["procedural_gm"]),
            choices.c.action_id == action["id"],
            choices.c.kind == REVIEW,
        )
    )
    if (
        original["kind"] != rules.PLAY
        or case.girl != girl
        or case.rebirth_event != row["event_id"]
        or case.void_work != row["id"]
        or case.roll is None
        or case.roll.result != "low"
        or case.scene != row["scene_id"]
        or threshold is None
        or threshold.stage != "rebirth"
        or threshold.actor != girl
        or threshold.forced_by != "incubus_conditioning"
        or threshold.source_action != action["id"]
        or body["details"]["family"] != "frame"
        or review is None
        or json.loads(review).get("flag") is not True
    ):
        raise WorkflowError("Recover the actual original low roll and Incubus rebirth source")


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
        raise WorkflowError("Recover the exact original pending Incubus Void source")
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
    case = rules.get(state, parent)
    if case.rebirth_event is None:
        stage_response(game, c, state, action, case)
    else:
        converted = next(
            (
                x
                for x in state.void_thresholds
                if x.source_works == (work,) and x.stage == "converted"
            ),
            None,
        )
        if converted is None or converted.resulting_actor is None:
            raise WorkflowError("Finish actual original Incubus rebirth before closing the source")
        action["data"]["result"]["conditioning_resolved"] = True
        action["data"]["result"]["reborn_actor"] = converted.resulting_actor.model_dump(mode="json")
        game.save_action(c, action)
    GorgonPlayService(game).synchronize(c, action, event, viewer, key)


def complete_response(
    game: "GameService",
    c: Connection,
    state: GameState,
    parent: dict[str, Any],
    child: dict[str, Any],
    event: str,
    viewer: Any,
    key: str,
) -> None:
    case = rules.get(state, parent["id"])
    source = child["data"]["gorgon_counter_source"]
    if (
        child["state"] != "complete"
        or child["parent_id"] != parent["id"]
        or source.get("conditioning_tag") != case.tag
        or source["actor"] != case.girl.model_dump(mode="json")
        or case.completed is not None
        or case.void_event is None
    ):
        raise WorkflowError("Recover the actual completed original Play on the marked Tag")
    recorded = str(uuid4())
    rules.put(state, case.model_copy(update=dict(completed=recorded, child=child["id"])))
    index = c.scalar(
        sa.select(sa.func.max(t.events.c.event_index)).where(
            t.events.c.campaign_id == game.store.campaign_id,
            t.events.c.command_key == key,
        )
    )
    game.event(
        c,
        viewer.user_id if viewer else child["actor_id"],
        key,
        "m3.incubus_response_completed",
        state,
        event_id=recorded,
        event_index=index + 1 if index is not None else 0,
        source_action=parent["id"],
        child=child["id"],
        source_event=event,
    )
    parent["data"]["result"]["conditioning_resolved"] = True
    game.save_action(c, parent)
