"""Secret original Asset cards and actual one-use, human-authored failures."""

from typing import Literal
from uuid import NAMESPACE_URL, uuid5

from pydantic import Field

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef, Model
from girlframe.engine.m3_handler_consequences import active_handler


class Pin(Model):
    owner: ActorRef
    asset: str

    @property
    def token(self) -> str:
        return str(uuid5(NAMESPACE_URL, self.owner.token + ":" + self.asset))


class Trap(Model):
    id: str
    source_work: str
    source_event: str
    handler: ActorRef
    pin: Pin
    account: str = Field(min_length=1, max_length=2400)
    phase: Literal["armed", "revealed", "spent"] = "armed"
    action: str | None = None
    choice: str | None = None
    reveal_event: str | None = None
    calamity: str | None = None
    resolved_event: str | None = None


def traps(state: GameState) -> tuple[Trap, ...]:
    return tuple(
        Trap.model_validate_json(x["body"])
        for x in state.facts
        if x.get("kind") == "budget_asset_trap"
    )


def put(state: GameState, value: Trap) -> None:
    state.facts = [
        x
        for x in state.facts
        if not (x.get("kind") == "budget_asset_trap" and x.get("id") == value.id)
    ]
    state.facts.append(dict(kind="budget_asset_trap", id=value.id, body=value.model_dump_json()))


def create(
    state: GameState, work: str, event: str, pins: tuple[Pin, ...], account: str
) -> GameState:
    handler = active_handler(state)
    if (
        handler is None
        or len(pins) != 2
        or len({x.token for x in pins}) != 2
        or any(x.source_work == work for x in traps(state))
    ):
        raise ValueError("Choose exactly two distinct actual Cadre Assets for one new source")
    for pin in pins:
        if (
            pin.owner.kind != "pilot"
            or int(pin.owner.entity) not in state.order
            or current_ref(state, int(pin.owner.entity)) != pin.owner
            or not any(
                x.id == pin.asset and not x.concealed for x in state.sheets[pin.owner.entity].assets
            )
        ):
            raise ValueError("Choose an actual current original Girl's nonconcealed Asset")
    changed = GameState.model_validate_json(state.model_dump_json())
    for i, pin in enumerate(pins):
        put(
            changed,
            Trap(
                id=work + ":asset:" + str(i),
                source_work=work,
                source_event=event,
                handler=handler,
                pin=pin,
                account=account,
            ),
        )
    return changed


def matching(state: GameState, actor: ActorRef, assets: set[str]) -> tuple[Trap, ...]:
    return tuple(
        x
        for x in traps(state)
        if x.phase == "armed" and x.pin.owner == actor and x.pin.asset in assets
    )
