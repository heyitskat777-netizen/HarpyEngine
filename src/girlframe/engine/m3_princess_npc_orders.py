"""The three original standards and a human GM's period-specific finding."""

import hashlib
import json
from typing import TYPE_CHECKING, Literal

from girlframe.engine.m3_actor_state import ActorRef, Model
from girlframe.engine.m3_girl_runtime_state import has_rule
from girlframe.engine.m3_standards import RULE, ready

if TYPE_CHECKING:
    from girlframe.engine.m2 import GameState, PilotSheet

Standard = Literal["own", "peer", "handler"]
ALL_STANDARDS = frozenset(("own", "peer", "handler"))


class Upkeep(Model):
    girl: ActorRef
    period: str
    period_revision: int
    standards: str
    gm: int
    appointment: str
    upheld: tuple[Standard, ...]
    account: str
    event: str

    @property
    def approved(self) -> bool:
        return set(self.upheld) == ALL_STANDARDS


def standards_hash(sheet: "PilotSheet") -> str | None:
    if not has_rule(sheet, RULE, "PRINCESS") or not ready(sheet):
        return None
    if sheet.girl_runtime and sheet.girl_runtime.standards:
        source = [x.model_dump_json() for x in sheet.girl_runtime.standards]
    else:
        details = sheet.review.creation.girl_details
        if details is None or details.own_standard is None:
            return None
        source = [details.own_standard.model_dump_json()] + [
            x.model_dump_json()
            for x in sheet.review.coordination
            if x.role in ("princess_peer", "princess_handler") and x.standard
        ]
    return hashlib.sha256(json.dumps(source).encode()).hexdigest()


def latest(state: "GameState", girl: ActorRef, period: str | None = None) -> Upkeep | None:
    for fact in reversed(state.facts):
        if (
            fact.get("kind") == "princess_off_duty_upkeep"
            and fact.get("girl") == girl.token
            and (period is None or fact.get("period") == period)
        ):
            return Upkeep.model_validate_json(fact["body"])
    return None


def save(state: "GameState", value: Upkeep) -> None:
    state.facts.append(
        dict(
            kind="princess_off_duty_upkeep",
            girl=value.girl.token,
            period=value.period,
            body=value.model_dump_json(),
        )
    )
