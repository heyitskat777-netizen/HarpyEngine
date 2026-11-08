"""The original Handler's backstory Tag and its actual Strain-granted alternative."""

from pydantic import Field

from girlframe.engine.m2 import GameState, TagState
from girlframe.engine.m3_actor_state import ActorRef, Model
from girlframe.engine.m3_handler_consequences import active_handler, same_handler_body

RULE = "strain.rebellion.high.5.2"


class Backstory(Model):
    id: str
    source_work: str
    source_event: str
    handler: ActorRef
    tag: str
    label: str = Field(min_length=1, max_length=120)
    account: str = Field(min_length=1, max_length=2400)


def sources(state: GameState) -> tuple[Backstory, ...]:
    return tuple(
        Backstory.model_validate_json(x["body"])
        for x in state.facts
        if x.get("kind") == "rebel_backstory"
    )


def create(
    state: GameState, work: str, event: str, label: str, account: str, observers: tuple[int, ...]
) -> GameState:
    handler = active_handler(state)
    if (
        handler is None
        or not label.strip()
        or any(x.source_work == work for x in sources(state))
        or len(set(observers)) != len(observers)
        or not set(observers) <= set(state.order)
    ):
        raise ValueError("The actual original Handler describes its backstory Tag")
    changed = GameState.model_validate_json(state.model_dump_json())
    value = Backstory(
        id=work + ":backstory",
        source_work=work,
        source_event=event,
        handler=handler,
        tag=work + ":backstory-tag",
        label=label.strip(),
        account=account,
    )
    changed.handler_tags.append(
        TagState(
            id=value.tag,
            label=value.label,
            giver=int(handler.entity),
            giver_actor=handler,
            observers=(int(handler.entity), *observers),
        )
    )
    changed.facts.append(dict(kind="rebel_backstory", id=value.id, body=value.model_dump_json()))
    return changed


def eligible(state: GameState, handler: ActorRef, tag: str) -> Backstory | None:
    return next(
        (
            x
            for x in sources(state)
            if x.tag == tag
            and x.handler == active_handler(state)
            and same_handler_body(state, handler)
            and any(t.id == tag and t.label == x.label for t in state.handler_tags)
        ),
        None,
    )


def finish_body_response(state: GameState, consequence: str) -> tuple[str, ...]:
    from girlframe.engine.m3_handler_tags import save, uses

    case = next(x for x in state.handler_consequences if x.id == consequence)
    if case.state == "pending" or not case.effect_event:
        raise ValueError("The actual Handler-owned consequence is still pending")
    finished = []
    for value in uses(state):
        if (
            value.kind == "helpless"
            and value.state == "pending"
            and value.source_event == case.source_event
            and value.handler == case.actor
            and value.girl == case.opponent
        ):
            save(
                state,
                value.model_copy(
                    update=dict(
                        revision=value.revision + 1,
                        state="resolved",
                        response_account=case.account,
                        response_event=case.effect_event,
                    )
                ),
            )
            finished.append(value.id)
    return tuple(finished)
