"""Identified replacement components for a genuine missing original Casualty part."""

from uuid import NAMESPACE_URL, uuid5

from pydantic import Field

from girlframe.engine import m3_casualty as casualty
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef, Model

PRODUCT = "casualty.part-replacement"


class Request(Model):
    id: str
    actor: ActorRef
    vessel: str
    part: str
    cause: str
    condition: str
    previous_component: str | None = None
    handler: ActorRef
    handler_controller: int
    event: str
    account: str = Field(min_length=1, max_length=1200)


class Quote(Model):
    id: str
    request: str
    actor: ActorRef
    vessel: str
    part: str
    component: str
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(min_length=1, max_length=1200)
    procurement: str = Field(min_length=1, max_length=1200)
    price: int = Field(ge=0)
    cell: tuple[int, int]
    event: str


class Installation(Model):
    id: str
    quote: str
    request: str
    actor: ActorRef
    vessel: str
    part: str
    component: str
    change: str
    event: str
    payment: str | None = None
    account: str = Field(min_length=1, max_length=1200)


KINDS = {
    Request: "casualty_replacement_request",
    Quote: "casualty_component_quote",
    Installation: "casualty_component_installed",
}


def records[T: (Request, Quote, Installation)](state: GameState, model: type[T]) -> tuple[T, ...]:
    return tuple(
        model.model_validate_json(x["body"]) for x in state.facts if x.get("kind") == KINDS[model]
    )


def get[T: (Request, Quote, Installation)](state: GameState, model: type[T], identity: str) -> T:
    value = next((x for x in records(state, model) if x.id == identity), None)
    if value is None:
        raise ValueError("Recover the actual original replacement source")
    return value


def put(state: GameState, value: Request | Quote | Installation) -> None:
    model = type(value)
    kind = KINDS[model]
    if any(x.get("kind") == kind and x.get("id") == value.id for x in state.facts):
        raise ValueError("Preserve each actual immutable component source once")
    state.facts.append(dict(kind=kind, id=value.id, body=value.model_dump_json()))


def price(state: GameState, actor: ActorRef, quote_id: str) -> int:
    """Amount only; the service's canonical quote proof supplies authority."""
    value = get(state, Quote, quote_id)
    if value.actor != actor:
        raise ValueError("This actual component quote belongs to another original body")
    return value.price


def install_component(
    state: GameState, value: Installation, quote: Quote, request: Request
) -> casualty.PartChange:
    body = casualty.body(state, request.actor)
    part = next((x for x in body.parts if x.id == request.part), None) if body else None
    if (
        body is None
        or body.vessel != request.vessel
        or request.part == "brain"
        or part is None
        or part.condition not in ("destroyed", "removed")
        or part.condition != request.condition
        or part.component != request.previous_component
        or (value.actor, value.vessel, value.part, value.request, value.quote, value.component)
        != (request.actor, request.vessel, request.part, request.id, quote.id, quote.component)
        or (quote.actor, quote.vessel, quote.part, quote.request)
        != (request.actor, request.vessel, request.part, request.id)
        or any(
            x.component == quote.component or x.request == request.id
            for x in records(state, Installation)
        )
    ):
        raise ValueError(
            "Install this one supplied non-Brain component into its original missing site"
        )
    change_id = str(uuid5(NAMESPACE_URL, "casualty-component:" + value.id))
    if value.change != change_id:
        raise ValueError("Preserve the genuine installation transition identity")
    change = casualty.PartChange(
        id=change_id,
        actor=request.actor,
        vessel=request.vessel,
        part=request.part,
        before=part.condition,
        after="intact",
        event=value.event,
        reason="replacement",
        inflictor=request.actor,
        account=value.account,
    )
    casualty.put(
        state,
        body.model_copy(
            update={
                "parts": tuple(
                    x.model_copy(update={"condition": "intact", "component": quote.component})
                    if x.id == request.part
                    else x
                    for x in body.parts
                )
            }
        ),
    )
    casualty.put(state, change)
    put(state, value)
    return change
