"""One original Successor advancement and actual Gold Star milestones."""

from pydantic import Field

from girlframe.engine.m2 import GameState, shift_status
from girlframe.engine.m3_actor_state import ActorRef, Model
from girlframe.engine.m3_handler_play_state import SUCCESSOR_ADVICE
from girlframe.engine.m3_intracadre_marriage import credit, rank

RULE = SUCCESSOR_ADVICE


class Acquisition(Model):
    id: str
    award: str
    handler: ActorRef
    appointment: str
    event: str
    account: str = Field(min_length=1, max_length=1200)


class Star(Model):
    id: str
    acquisition: str
    handler: ActorRef
    girl: ActorRef
    advice: str
    lesson: str
    event: str
    account: str = Field(min_length=1, max_length=1200)
    removed_event: str | None = None


class Milestone(Model):
    acquisition: str
    girl: ActorRef
    event: str
    stars: tuple[str, str, str]


def acquisitions(state: GameState) -> tuple[Acquisition, ...]:
    return tuple(
        Acquisition.model_validate_json(x["body"])
        for x in state.facts
        if x.get("kind") == "successor_acquisition"
    )


def stars(state: GameState) -> tuple[Star, ...]:
    return tuple(
        Star.model_validate_json(x["body"])
        for x in state.facts
        if x.get("kind") == "successor_star"
    )


def earned(state: GameState) -> tuple[Milestone, ...]:
    return tuple(
        Milestone.model_validate_json(x["body"])
        for x in state.facts
        if x.get("kind") == "successor_three_stars"
    )


def put_acquisition(state: GameState, value: Acquisition) -> None:
    state.facts.append(
        dict(kind="successor_acquisition", id=value.id, body=value.model_dump_json())
    )


def put_star(state: GameState, value: Star) -> None:
    state.facts = [
        x for x in state.facts if x.get("kind") != "successor_star" or x.get("id") != value.id
    ]
    state.facts.append(dict(kind="successor_star", id=value.id, body=value.model_dump_json()))


def award(state: GameState, star: Star) -> None:
    saved = stars(state)
    if any(x.id == star.id or x.lesson == star.lesson or x.advice == star.advice for x in saved):
        raise ValueError("The original advice and performed lesson may earn one Gold Star")
    active = tuple(
        x.id
        for x in saved
        if x.acquisition == star.acquisition and x.girl == star.girl and x.removed_event is None
    )
    if len(active) >= 4:
        raise ValueError("The five-star Junior Handler offer still needs its own actual workflow")
    put_star(state, star)
    if len(active) != 2 or any(
        x.acquisition == star.acquisition and x.girl == star.girl for x in earned(state)
    ):
        return
    target = int(star.girl.entity)
    credit(
        state,
        star.girl,
        1,
        event=star.event,
        source="successor-three-stars:" + star.acquisition + ":" + star.girl.token,
    )
    for _ in range(rank(state, target)):
        shift_status(state, target, 1)
    state.sheets[star.girl.entity].revision += 1
    milestone = Milestone(
        acquisition=star.acquisition,
        girl=star.girl,
        event=star.event,
        stars=(active[0], active[1], star.id),
    )
    state.facts.append(dict(kind="successor_three_stars", body=milestone.model_dump_json()))
