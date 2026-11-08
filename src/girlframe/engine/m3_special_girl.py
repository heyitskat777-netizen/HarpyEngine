"""A real Handler-authored token and named Class entitlement, never proxy authorship."""

from typing import Literal

from girlframe.engine import m3_class_grafts as grafts
from girlframe.engine.m2 import AssetState, GameState
from girlframe.engine.m3_actor_state import ActorRef, Model
from girlframe.engine.m3_core import install
from girlframe.engine.m3_janus_storage import ids as stored_ids
from girlframe.engine.m3_requisition_state import FrameRuleReceipt

RULE = "frame.class.autocrat.handlers-special-girl"
KIND = "special_girl_token"


class Token(Model):
    id: str
    actor: ActorRef
    handler: ActorRef
    frame: str
    purchase: str
    source_event: str
    event: str
    phase: Literal["handler", "owner", "complete"] = "handler"
    asset: AssetState | None = None
    authored_event: str | None = None
    installed_event: str | None = None
    replaced: str | None = None


def put(state: GameState, value: Token) -> None:
    state.facts = [
        x for x in state.facts if not (x.get("kind") == KIND and x.get("id") == value.id)
    ]
    state.facts.append(dict(kind=KIND, id=value.id, body=value.model_dump_json()))


def token(state: GameState, identity: str) -> Token | None:
    values = [
        Token.model_validate_json(x["body"])
        for x in state.facts
        if x.get("kind") == KIND and x.get("id") == identity
    ]
    if len(values) > 1:
        raise ValueError("Recover one actual original Handler token source")
    return values[0] if values else None


def held(state: GameState, actor: ActorRef) -> FrameRuleReceipt | None:
    receipt = grafts.held(state, actor, RULE)
    value = token(state, receipt.id) if receipt else None
    return receipt if value and value.phase == "complete" else None


def give(state: GameState, value: Token, replace: str | None, event: str) -> None:
    if value.phase != "owner" or value.asset is None or value.authored_event is None:
        raise ValueError("Wait for the actual original Handler to name and describe this token")
    if grafts.held(state, value.actor, RULE) is None:
        raise ValueError("Restore the original current Frame source before receiving its token")
    state.sheets[value.actor.entity] = install(
        state.sheets[value.actor.entity],
        value.asset,
        replace=replace,
        effective_void=stored_ids(state, value.actor),
        state=state,
    ).sheet
    put(
        state,
        value.model_copy(
            update=dict(phase="complete", event=event, installed_event=event, replaced=replace)
        ),
    )
