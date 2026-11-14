"""Source-bound factual discharge from the original Handler's actual Defeat rescue."""

from uuid import NAMESPACE_URL, uuid5

from pydantic import Field

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef, Model
from girlframe.engine.m3_physical_state import Placement


def task_id(action: str, actor: ActorRef) -> str:
    return str(uuid5(NAMESPACE_URL, "handler-rescue-release:" + action + ":" + actor.token))


class Proposal(Model):
    id: str
    action: str
    rescue_event: str
    actor: ActorRef
    handler: ActorRef
    vessel: str
    origin: Placement
    cell: tuple[int, int]
    account: str = Field(min_length=1, max_length=1200)
    event: str


class Release(Model):
    id: str
    proposal: str
    actor: ActorRef
    handler: ActorRef
    cell: tuple[int, int]
    account: str = Field(min_length=1, max_length=1200)
    event: str


def proposals(state: GameState, identity: str) -> tuple[Proposal, ...]:
    return tuple(
        Proposal.model_validate_json(x["body"])
        for x in state.facts
        if x.get("kind") == "handler_recovery_proposal" and x.get("id") == identity
    )


def released(state: GameState, identity: str) -> Release | None:
    values = [
        Release.model_validate_json(x["body"])
        for x in state.facts
        if x.get("kind") == "handler_recovery_release" and x.get("id") == identity
    ]
    if len(values) > 1:
        raise ValueError("One actual rescued body is discharged once from this source")
    return values[0] if values else None


def put(state: GameState, value: Proposal | Release) -> None:
    kind = (
        "handler_recovery_proposal" if isinstance(value, Proposal) else "handler_recovery_release"
    )
    if any(x.get("kind") == kind and x.get("event") == value.event for x in state.facts):
        raise ValueError("Preserve the immutable original rescue response event")
    state.facts.append(
        dict(kind=kind, id=value.id, event=value.event, body=value.model_dump_json())
    )


def discharge(state: GameState, value: Proposal, event: str, account: str) -> GameState:
    from girlframe.engine.m3_physical import _finish, _save

    if released(state, value.id) is not None:
        raise ValueError("This original rescued body has already been released")
    current = next((x for x in state.placements if x.actor == value.actor), None)
    if (
        current != value.origin
        or current is None
        or current.custody != value.handler
        or current.vessel_id != value.vessel
        or current.mode != "outside_frame"
        or current.occupied_frame_owner is not None
        or current.incapacitated
        or current.subsumed
        or not current.vitals_active
        or not account.strip()
    ):
        raise ValueError("Confirm the same original recovered body and actual rescue custody")
    result = state.model_copy(deep=True)
    _save(
        result,
        current.model_copy(
            update=dict(
                custody=None,
                girl_cell=value.cell,
                source_event=event,
                account=account,
            )
        ),
    )
    put(
        result,
        Release(
            id=value.id,
            proposal=value.event,
            actor=value.actor,
            handler=value.handler,
            cell=value.cell,
            account=account,
            event=event,
        ),
    )
    return _finish(result, value.actor, event, account, "actual_handler_rescue_discharge")
