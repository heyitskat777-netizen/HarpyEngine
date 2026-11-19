"""Real rebel custody and the original Captured! roll."""

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef, Model
from girlframe.engine.m3_hallucinations import Roll

RULE = "situational.situational.captured"
KIND = "captured_situational"


class Result(Model):
    roll: Roll
    no_heat: bool
    prompt: str | None = None
    chosen_event: str | None = None
    completed: str | None = None
    erased_identity: str | None = None


class Capture(Model):
    id: str
    scene: str
    channel: int
    girl: ActorRef
    captor: ActorRef
    controller: int
    base: str
    faction: str
    gm: int
    appointment: str
    account: str
    confirmed: str | None = None
    declined: str | None = None
    escaped: str | None = None
    rolls: tuple[Result, ...] = ()

    @property
    def current(self) -> Result | None:
        return self.rolls[-1] if self.rolls else None


def records(state: GameState) -> tuple[Capture, ...]:
    return tuple(
        Capture.model_validate_json(x["body"]) for x in state.facts if x.get("kind") == KIND
    )


def put(state: GameState, value: Capture) -> None:
    state.facts = [x for x in state.facts if (x.get("kind"), x.get("id")) != (KIND, value.id)]
    state.facts.append(dict(kind=KIND, id=value.id, body=value.model_dump_json()))


def active(state: GameState, actor: ActorRef) -> bool:
    body = next((x for x in state.placements if x.actor == actor), None)
    return bool(
        body
        and body.custody
        and any(
            case.girl == actor
            and case.captor == body.custody
            and case.confirmed
            and not case.escaped
            and not case.declined
            for case in records(state)
        )
    )


def recover_capture_helplessness(state: GameState, case: Capture, event: str) -> None:
    # The escape source releases only what this actual capture imposed.
    result = []
    for item in state.helpless_conditions:
        if (
            item.active
            and item.subject == case.girl
            and item.foe == case.captor
            and case.confirmed in item.source_events
        ):
            residual = tuple(x for x in item.source_events if x != case.confirmed)
            item = item.model_copy(
                update=(
                    dict(source_events=residual)
                    if residual
                    else dict(active=False, recovery_event=event)
                )
            )
        result.append(item)
    state.helpless_conditions = result
