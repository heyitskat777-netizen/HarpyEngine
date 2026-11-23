"""Private exact Mother source and the Girl's own resulting choices."""

import json
from typing import TYPE_CHECKING, Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_mother_hazard as rules
from girlframe.engine.m2 import ChoiceAnswer, GameState, spend_heat
from girlframe.engine.m3_actor_state import ActorRef, ActorView, SceneCast
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_gorgon_play_state import Declaration
from girlframe.engine.m3_hallucinations import Roll
from girlframe.engine.m3_janus_storage import alter, effective_assets
from girlframe.engine.m3_physical import cockpit_enter, cockpit_exit
from girlframe.engine.m3_sentinel_shell import holds
from girlframe.engine.m3_void_state import VoidThreshold
from girlframe.services.m2_choices import ChoiceEngine
from girlframe.services.m2_state import load_state
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_work import related
from girlframe.services.onboarding import WorkflowError

if TYPE_CHECKING:
    from girlframe.services.m2_game import GameService
    from girlframe.services.read_only_bot import GuildViewer

HEAT = "gorgon_hazard_heat"
EJECT = "gorgon_hazard_eject"
PURSUE = "gorgon_hazard_pursue"
REVIEW = "gorgon_hazard_review"
MID = "gorgon_hazard_mid"
VOID = "gorgon_hazard_void"
THRESHOLD = "gorgon_hazard_threshold"
PICK_PLAY = "gorgon_hazard_pick_play"
SUPPORTED_PLAY = "keep_your_head"


def _originals(
    game: "GameService",
    c: Connection,
    state: GameState,
    action: dict[str, Any],
) -> tuple[ActorView, ActorView]:
    original = action["data"]["gorgon_play"]
    scene = SceneCast.model_validate_json(json.dumps(original["cast"]))
    if not any(x.id == scene.id and x.open and x.roles == scene.roles for x in state.scene_casts):
        raise WorkflowError("Recover Mother's actual original scene")
    bound = profiles(c, game.store.campaign_id)
    mother = resolve(
        state, ActorRef.model_validate(original["actor"]), bound, require_current_profile=False
    )
    girl = resolve(
        state, ActorRef.model_validate(original["target"]), bound, require_current_profile=False
    )
    if (
        not mother.alive
        or not girl.alive
        or mother.controller != original["controller"]
        or not any(x.actor == girl.ref and x.controller == girl.controller for x in scene.roles)
    ):
        raise WorkflowError("Recover Mother's actual original affected Girl")
    return mother, girl


def start(game: "GameService", c: Connection, state: GameState, action: dict[str, Any]) -> None:
    mother, girl = _originals(game, c, state, action)
    original = action["data"]["gorgon_play"]
    declaration = Declaration.model_validate_json(json.dumps(original["declaration"]))
    tag = next((x for x in rules.available(state, mother, girl) if x.id == declaration.tag), None)
    if tag is None:
        raise WorkflowError("Choose an actual unmarked Tag known to this original Mother")
    ChoiceEngine(game).prove_tag_setter(c, state, girl.controller, tag)
    tag.marked = True
    state.sheets[girl.ref.entity].revision += 1
    rules.put(
        state,
        rules.Exposure(
            action=action["id"],
            scene=action["scene_id"],
            source=mother.ref,
            girl=girl.ref,
            tag=tag.id,
            mark_event=action["data"]["response_event"],
        ),
    )
    game.request(c, action, girl.controller, HEAT)


def _actual_cockpit(state: GameState, girl: ActorView) -> bool:
    return (
        girl.inside_frame is True
        and girl.frame_instance is not None
        and girl.occupied_frame_instance == girl.frame_instance
        and girl.custody in (None, "free")
        and girl.vitals_active is not False
        and state.sheets[girl.ref.entity].medical_state == "fit"
        and not holds(state, girl.ref, "trapped")
    )


def apply(
    game: "GameService",
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    row: dict[str, Any],
    answer: ChoiceAnswer,
) -> None:
    mother, girl = _originals(game, c, state, action)
    case = rules.get(state, action["id"])
    kind, event = row["kind"], action["data"]["response_event"]
    if (
        case is None
        or case.source != mother.ref
        or case.girl != girl.ref
        or case.completed
        or not any(
            x.id == case.tag and x.marked and x.giver_actor == mother.ref
            for x in state.sheets[girl.ref.entity].tags
        )
    ):
        raise WorkflowError("Recover the actual marked Tag and source of this exposure")
    if kind == REVIEW:
        _review_rebirth(state, action, case, girl, row, answer, event)
        return
    if kind == THRESHOLD:
        raise WorkflowError("The saved original hazard needs its actual outstanding consequence")
    owner = mother.controller if kind == PICK_PLAY else girl.controller
    if (
        row["actor_id"] != str(owner)
        or answer.denied
        or answer.flag is not None
        or answer.member is not None
        or answer.fields
    ):
        raise WorkflowError("Use the actual source role's owned response")
    if kind == HEAT:
        _roll(game, c, state, action, case, girl, answer, event)
    elif kind == MID:
        if (
            case.roll is None
            or case.roll.result != "mid"
            or case.choice is not None
            or answer.options not in (("void",), ("play",))
            or answer.text
            or answer.number is not None
        ):
            raise WorkflowError("Choose one actual mid-tier Memetic Hazard consequence")
        selected = answer.options[0]
        rules.put(state, case.model_copy(update=dict(choice=selected)))
        game.request(
            c,
            action,
            girl.controller if selected == "void" else mother.controller,
            VOID if selected == "void" else PICK_PLAY,
        )
    elif kind == VOID:
        _apply_void(game, c, state, action, case, girl, answer, event)
    elif kind == PICK_PLAY:
        _request_play(game, c, state, action, case, girl, answer)
    elif kind == PURSUE:
        _return_to_frame(game, c, state, action, case, girl, answer, event)
    elif kind == EJECT:
        if (
            case.roll is None
            or case.roll.result != "low"
            or case.frame != girl.frame_instance
            or not _actual_cockpit(state, girl)
            or not answer.text.strip()
            or answer.options not in ((), ("eject",), ("remain",))
            or answer.number is not None
        ):
            raise WorkflowError("Use the original Girl's actual still-occupied Frame decision")
        if answer.options == ("remain",):
            rules.put(state, case.model_copy(update=dict(remain_event=event)))
            game.request(c, action, action["data"]["gorgon_play"]["procedural_gm"], REVIEW)
            return
        changed = cockpit_exit(
            state,
            profiles(c, game.store.campaign_id),
            girl.ref,
            event,
            answer.text.strip(),
        )
        for field in GameState.model_fields:
            setattr(state, field, getattr(changed, field))
        rules.put(state, case.model_copy(update=dict(ejected=event, completed=event)))
        action["data"]["result"]["mother_hazard_ejected"] = True
    else:
        raise WorkflowError("Recover the actual outstanding Memetic Hazard decision")


def _review_rebirth(
    state: GameState,
    action: dict[str, Any],
    case: rules.Exposure,
    girl: ActorView,
    row: dict[str, Any],
    answer: ChoiceAnswer,
    event: str,
) -> None:
    from girlframe.engine.m3_void import FINAL

    source = action["data"]["gorgon_play"]
    if (
        row["actor_id"] != str(source["procedural_gm"])
        or case.roll is None
        or case.roll.result != "low"
        or case.choice == "pursue"
        or case.ejected
        or case.rebirth_event
        or case.frame is None
        or case.frame != girl.frame_instance
        or girl.occupied_frame_instance != case.frame
        or girl.inside_frame is not True
        or girl.vitals_active is False
        or (case.remain_event is None and _actual_cockpit(state, girl))
        or any(x.actor == girl.ref and x.stage not in FINAL for x in state.void_thresholds)
        or answer.flag is not True
        or not answer.text.strip()
        or answer.options
        or answer.number is not None
        or answer.denied
        or answer.fields
        or answer.member is not None
    ):
        raise WorkflowError("Verify the original low result and actual in-Frame failure to eject")
    work = f"{action['id']}:hazard:rebirth"
    state.void_thresholds.append(
        VoidThreshold(
            id="void:" + work,
            actor=girl.ref,
            frame_instance=case.frame,
            family="frame",
            source_event=event,
            source_action=action["id"],
            source_works=(work,),
            sheet_json=state.sheets[girl.ref.entity].model_dump_json(),
            stage="rebirth",
            enclosed=True,
            forced_by=rules.KIND,
        )
    )
    rules.put(state, case.model_copy(update=dict(rebirth_event=event, void_work=work)))
    source["followups"].append(work)


def _roll(
    game: "GameService",
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    case: rules.Exposure,
    girl: ActorView,
    answer: ChoiceAnswer,
    event: str,
) -> None:
    heat = answer.number
    if (
        case.roll is not None
        or heat is None
        or answer.text
        or answer.options
        or heat
        and holds(state, girl.ref, "trapped")
    ):
        raise WorkflowError("Spend this original Girl's actual Heat for Memetic Hazard")
    sheet = state.sheets[girl.ref.entity]
    spend_heat(sheet, heat)
    if heat:
        sheet.revision += 1
    roll = Roll(faces=game.dice.roll(), heat=heat, event=event)
    if roll.result == "low":
        low_void = girl.inside_frame is False
        choice = "pursue" if low_void else None
        step, owner = (
            (EJECT, girl.controller)
            if _actual_cockpit(state, girl)
            else (VOID, girl.controller)
            if low_void
            else (REVIEW, action["data"]["gorgon_play"]["procedural_gm"])
        )
    else:
        choice = "both" if roll.result == "high" else None
        step, owner = (VOID if choice else MID), girl.controller
    rules.put(
        state,
        case.model_copy(
            update=dict(
                roll=roll,
                frame=girl.occupied_frame_instance or girl.frame_instance,
                choice=choice,
            )
        ),
    )
    game.request(c, action, owner, step)


def _void_assets(state: GameState, girl: ActorView) -> dict[str, str]:
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
    case: rules.Exposure,
    girl: ActorView,
    answer: ChoiceAnswer,
    event: str,
) -> None:
    from girlframe.engine.m3_void import FINAL

    if (
        case.choice not in ("void", "both", "pursue")
        or case.void_event
        or len(answer.options) != 1
        or answer.options[0] not in _void_assets(state, girl)
        or answer.number is not None
        or not answer.text.strip()
        or any(x.actor == girl.ref and x.stage not in FINAL for x in state.void_thresholds)
    ):
        raise WorkflowError("Choose an actual eligible Asset for the original Girl's ordinary Void")
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
        work = f"{action['id']}:hazard:void:{family}"
        action["data"]["gorgon_play"]["followups"].append(work)
    updated = case.model_copy(
        update=dict(
            void_asset=selected if applied else None,
            void_event=event,
            void_work=work,
        )
    )
    rules.put(state, updated)
    if work is None:
        _after_void(game, c, state, action, updated, event)


def _parked_here(state: GameState, case: rules.Exposure, girl: ActorView) -> bool:
    return (
        girl.inside_frame is False
        and girl.offstage_source is None
        and case.frame is not None
        and girl.frame_instance == case.frame
        and girl.frame_cell == girl.cell
        and girl.cell is not None
        and girl.custody in (None, "free")
        and girl.vitals_active is not False
        and not holds(state, girl.ref, "trapped")
        and state.sheets[girl.ref.entity].medical_state == "fit"
    )


def _return_to_frame(
    game: "GameService",
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    case: rules.Exposure,
    girl: ActorView,
    answer: ChoiceAnswer,
    event: str,
) -> None:
    if (
        case.choice != "pursue"
        or not case.void_event
        or not _parked_here(state, case, girl)
        or answer.number is not None
        or answer.options
        or not answer.text.strip()
    ):
        raise WorkflowError("Use the original Girl's actual attempt to return to her parked Frame")
    changed = cockpit_enter(
        state,
        profiles(c, game.store.campaign_id),
        girl.ref,
        event,
        answer.text.strip(),
        pilot=False,
    )
    for field in GameState.model_fields:
        setattr(state, field, getattr(changed, field))
    rules.put(state, case.model_copy(update=dict(pursuit_event=event, completed=event)))
    action["data"]["result"]["mother_hazard_returned"] = True


def _after_void(
    game: "GameService",
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    case: rules.Exposure,
    event: str,
) -> None:
    original = state.sheets.get(case.girl.entity)
    source = action["data"]["gorgon_play"]
    if (
        case.choice == "both"
        and original is not None
        and original.character_id == case.girl.incarnation
    ):
        game.request(c, action, source["controller"], PICK_PLAY)
    elif (
        case.choice == "pursue"
        and original is not None
        and original.character_id == case.girl.incarnation
    ):
        girl = resolve(
            state, case.girl, profiles(c, game.store.campaign_id), require_current_profile=False
        )
        if _parked_here(state, case, girl):
            game.request(c, action, girl.controller, PURSUE)
        else:
            game.request(c, action, source["procedural_gm"], REVIEW)
    elif case.choice != "void":
        game.request(c, action, source["procedural_gm"], REVIEW)
    else:
        rules.put(state, case.model_copy(update=dict(completed=event)))
        action["data"]["result"]["mother_hazard_resolved"] = True


def _request_play(
    game: "GameService",
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    case: rules.Exposure,
    girl: ActorView,
    answer: ChoiceAnswer,
) -> None:
    from girlframe.services.m3_gorgon_runtime import _request

    if (
        case.choice not in ("play", "both")
        or case.requested_play
        or case.choice == "both"
        and not case.void_event
        or answer.options != (SUPPORTED_PLAY,)
        or answer.text
        or answer.number is not None
    ):
        raise WorkflowError("Choose the supported immediate Play for this original Girl")
    rules.put(state, case.model_copy(update=dict(requested_play=SUPPORTED_PLAY)))
    _request(game, c, action, girl.controller, "response_play", allowed=[SUPPORTED_PLAY])


def project(
    game: "GameService",
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    row: dict[str, Any],
) -> dict[str, Any]:
    case = rules.get(state, action["id"])
    if case is None:
        raise WorkflowError("Recover the actual original Memetic Hazard")
    kind = row["kind"]
    result: dict[str, Any] = dict(kind=kind.removeprefix("gorgon_"))
    if kind == THRESHOLD:
        return result | dict(work=case.void_work)
    if kind == PICK_PLAY:
        return result | dict(options=(SUPPORTED_PLAY,))
    original = state.sheets.get(case.girl.entity)
    if kind == REVIEW and (original is None or original.character_id != case.girl.incarnation):
        return result | dict(can_review_rebirth=False)
    _, girl = _originals(game, c, state, action)
    if kind == REVIEW:
        return result | dict(
            roll=case.roll.model_dump(mode="json") if case.roll else None,
            can_review_rebirth=bool(
                case.roll
                and case.roll.result == "low"
                and case.frame is not None
                and case.frame == girl.frame_instance == girl.occupied_frame_instance
                and case.choice != "pursue"
                and (case.remain_event or not _actual_cockpit(state, girl))
            ),
        )
    if kind == VOID:
        return result | dict(assets=_void_assets(state, girl))
    if kind == HEAT:
        result["heat"] = (
            0 if holds(state, girl.ref, "trapped") else state.sheets[girl.ref.entity].heat
        )
    elif case.roll:
        result["roll"] = case.roll.model_dump(mode="json")
    return result


def materialize(
    game: "GameService",
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    event: str,
) -> None:
    case = rules.get(state, action["id"])
    if not case or event not in (case.void_event, case.rebirth_event) or not case.void_work:
        return
    table = t.m3["m3_required_work"]
    if c.scalar(
        sa.select(table.c.id).where(
            table.c.campaign_id == game.store.campaign_id,
            table.c.id == case.void_work,
        )
    ):
        return
    owner = int(case.girl.entity)
    rebirth = case.rebirth_event == event
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
            reason="mother_memetic_hazard_rebirth" if rebirth else rules.KIND,
            details=dict(family="frame" if rebirth else case.void_work.rsplit(":", 1)[-1]),
        ),
        event,
    )
    game.request(c, action, owner, THRESHOLD, dict(work_id=case.void_work))


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
        or case.choice not in ("void", "both", "pursue")
        or case.void_event != row["event_id"]
        or case.void_work != row["id"]
        or case.scene != row["scene_id"]
        or case.void_asset is None
        or answer is None
        or json.loads(answer).get("options") != [case.void_asset]
    ):
        raise WorkflowError("Recover the original Mother hazard and the owned Void response")


def _record(
    game: "GameService",
    c: Connection,
    state: GameState,
    case: rules.Exposure,
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
    if case is None or case.void_work != work or case.completed or len(held) != 1:
        raise WorkflowError("Recover the actual original hazard Void threshold")
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
    action = game.action(c, parent)
    recorded = str(uuid4())
    if case.rebirth_event:
        if not any(
            x.source_works == (work,) and x.stage == "converted" and x.resulting_actor is not None
            for x in state.void_thresholds
        ):
            raise WorkflowError(
                "Finish the actual original Mother rebirth before closing the source"
            )
        rules.put(state, case.model_copy(update=dict(completed=recorded)))
        action["data"]["result"]["mother_hazard_rebirth"] = True
    else:
        _after_void(game, c, state, action, case, recorded)
    _record(game, c, state, case, recorded, event, viewer, key, "m3.mother_hazard_void_resolved")
    game.save_action(c, action)
    GorgonPlayService(game).synchronize(c, action, event, viewer, key)


def complete_response(
    game: "GameService",
    c: Connection,
    state: GameState,
    parent: dict[str, Any],
    child: dict[str, Any],
    event: str,
    viewer: "GuildViewer | None",
    key: str,
) -> None:
    case = rules.get(state, parent["id"])
    source = child["data"]["gorgon_counter_source"]
    if (
        case is None
        or case.completed
        or case.requested_play != SUPPORTED_PLAY
        or child["data"]["play"] != case.requested_play
        or child["state"] != "complete"
        or child["parent_id"] != parent["id"]
        or source["actor"] != case.girl.model_dump(mode="json")
    ):
        raise WorkflowError("Recover the actual completed owned Play of the original hazard")
    recorded = str(uuid4())
    rules.put(state, case.model_copy(update=dict(completed=recorded, child=child["id"])))
    _record(
        game, c, state, case, recorded, event, viewer, key, "m3.mother_hazard_response_resolved"
    )
    parent["data"]["result"]["mother_hazard_resolved"] = True
    game.save_action(c, parent)


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
            responses.c.actor_id == str(original["procedural_gm"]),
            choices.c.kind == REVIEW,
            choices.c.action_id == action["id"],
        )
    )
    if (
        original["kind"] != rules.PLAY
        or case is None
        or case.girl != girl
        or case.ejected
        or case.roll is None
        or case.roll.result != "low"
        or case.rebirth_event != row["event_id"]
        or case.void_work != row["id"]
        or case.scene != row["scene_id"]
        or threshold is None
        or threshold.actor != girl
        or threshold.forced_by != rules.KIND
        or threshold.stage != "rebirth"
        or threshold.frame_instance != case.frame
        or threshold.source_action != action["id"]
        or answer is None
        or json.loads(answer).get("flag") is not True
    ):
        raise WorkflowError(
            "Recover the original low Mother roll and actual in-Frame rebirth source"
        )
