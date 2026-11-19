"""Owned Off-Duty confirmations are the source of actual Scientist Project work."""

from typing import TYPE_CHECKING

from sqlalchemy import Connection

from girlframe.engine import m3_scientist_lab as rules
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_off_duty import Period, Scene
from girlframe.services.m3_handler_book_orders import active_book
from girlframe.services.onboarding import WorkflowError

if TYPE_CHECKING:
    from girlframe.services.m2_game import GameService


def available(game: "GameService", c: Connection, state: GameState) -> ActorRef | None:
    role = active_book(game, c, state, book="Scientist", rule=rules.LAB)
    if (
        role is None
        or active_book(game, c, state, book="Scientist", rule=rules.PROJECT) != role
        or rules.steps(state, role[0])
    ):
        return None
    return role[0]


def scope(
    game: "GameService",
    c: Connection,
    state: GameState,
    period: Period,
    participants: tuple[int, ...],
) -> tuple[ActorRef, ActorRef]:
    actor = available(game, c, state)
    if (
        actor is None
        or actor.entity != str(period.handler)
        or len(participants) != 2
        or period.handler not in participants
    ):
        raise WorkflowError("Choose an available Project start with the Scientist and one Girl")
    target = current_ref(state, next(x for x in participants if x != period.handler))
    if target.kind != "pilot" or period.character_ids.get(target.entity) != target.incarnation:
        raise WorkflowError("Choose the actual original Girl from this Off-Duty period")
    return actor, target


def attest(
    game: "GameService",
    c: Connection,
    state: GameState,
    period: Period,
    scene: Scene,
    owner: int,
    answer: rules.LabAnswer | None,
    event: str,
) -> None:
    actor, target = scope(game, c, state, period, scene.participants)
    assert scene.lab is not None
    if str(owner) == target.entity:
        if answer is None:
            raise WorkflowError("The original Girl chooses the exact Assets affected")
        rules.apply_assets(state, target=target, event=event, proposal=scene.lab, answer=answer)
        scene.lab_answer = answer
    elif answer is not None:
        raise WorkflowError("Only the affected Girl chooses the actual Assets")
    if set(scene.participants) == set(scene.acknowledgements):
        if scene.lab_answer is None:
            raise WorkflowError("Recover the original Girl's accepted Asset selections")
        rules.complete(
            state,
            actor=actor,
            target=target,
            period=period.id,
            event=event,
            proposal=scene.lab,
            answer=scene.lab_answer,
        )
