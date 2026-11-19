"""Private exact Mother source and the Girl's own resulting choices."""

import json
from typing import TYPE_CHECKING, Any

from sqlalchemy import Connection

from girlframe.engine import m3_mother_hazard as rules
from girlframe.engine.m2 import ChoiceAnswer, GameState, spend_heat
from girlframe.engine.m3_actor_state import ActorRef, ActorView, SceneCast
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_gorgon_play_state import Declaration
from girlframe.engine.m3_hallucinations import Roll
from girlframe.engine.m3_physical import cockpit_exit
from girlframe.engine.m3_sentinel_shell import holds
from girlframe.services.m2_choices import ChoiceEngine
from girlframe.services.m3_actors import profiles
from girlframe.services.onboarding import WorkflowError

if TYPE_CHECKING:
    from girlframe.services.m2_game import GameService

HEAT = "gorgon_hazard_heat"
EJECT = "gorgon_hazard_eject"
REVIEW = "gorgon_hazard_review"


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
        raise WorkflowError("The saved original hazard needs its actual outstanding consequence")
    if (
        row["actor_id"] != str(girl.controller)
        or answer.denied
        or answer.flag is not None
        or answer.member is not None
        or answer.fields
        or answer.options
    ):
        raise WorkflowError("Only the original affected Girl owns this response")
    if kind == HEAT:
        _roll(game, c, state, action, case, girl, answer, event)
    elif kind == EJECT:
        if (
            case.roll is None
            or case.roll.result != "low"
            or case.frame != girl.frame_instance
            or not _actual_cockpit(state, girl)
            or not answer.text.strip()
            or answer.number is not None
        ):
            raise WorkflowError("Eject the original Girl from her actual still-occupied Frame")
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
        or heat
        and holds(state, girl.ref, "trapped")
    ):
        raise WorkflowError("Spend this original Girl's actual Heat for Memetic Hazard")
    sheet = state.sheets[girl.ref.entity]
    spend_heat(sheet, heat)
    if heat:
        sheet.revision += 1
    roll = Roll(faces=game.dice.roll(), heat=heat, event=event)
    eject = roll.result == "low" and _actual_cockpit(state, girl)
    rules.put(
        state,
        case.model_copy(
            update=dict(
                roll=roll,
                frame=girl.occupied_frame_instance,
            )
        ),
    )
    if eject:
        game.request(c, action, girl.controller, EJECT)
    else:
        game.request(c, action, action["data"]["gorgon_play"]["procedural_gm"], REVIEW)


def project(
    game: "GameService",
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    row: dict[str, Any],
) -> dict[str, Any]:
    _, girl = _originals(game, c, state, action)
    case = rules.get(state, action["id"])
    if case is None:
        raise WorkflowError("Recover the actual original Memetic Hazard")
    kind = row["kind"]
    result: dict[str, Any] = dict(kind=kind.removeprefix("gorgon_"))
    if kind == HEAT:
        result["heat"] = (
            0 if holds(state, girl.ref, "trapped") else state.sheets[girl.ref.entity].heat
        )
    elif case.roll:
        result["roll"] = case.roll.model_dump(mode="json")
    return result
