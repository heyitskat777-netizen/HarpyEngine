"""The original Vatgrown's first actual comparison, distinct from DNA/actor inference."""

import hashlib
from typing import Literal
from uuid import NAMESPACE_URL, uuid5

from pydantic import Field, model_validator

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef, Model, SceneCast

RULE = "girl.vatgrown.dna-comparison"
BOOK = "VATGROWN"


def identity(*parts: str) -> str:
    return str(uuid5(NAMESPACE_URL, "girlframe:vatgrown-dna:" + ":".join(parts)))


class BasisProof(Model):
    actor: ActorRef
    source: str
    epoch: str
    text: str = Field(min_length=1, max_length=300)
    digest: str

    @model_validator(mode="after")
    def original_source(self) -> "BasisProof":
        if (
            self.actor.kind != "pilot"
            or not self.text.strip()
            or not self.source
            or not self.epoch
            or self.digest != hashlib.sha256(self.text.encode()).hexdigest()
        ):
            raise ValueError("Preserve the original native Vatgrown's exact private DNA source")
        return self


class Disclosure(Model):
    id: str
    basis: BasisProof
    recipient: ActorRef
    controller: int
    recipient_controller: int
    cast: SceneCast
    account: str = Field(min_length=1, max_length=1200)
    event: str


class Comparison(Model):
    id: str
    basis: BasisProof
    comparer: ActorRef
    controller: int
    owner_controller: int
    cast: SceneCast
    account: str = Field(min_length=1, max_length=1200)
    event: str
    outcome: Literal["pending", "given", "declined"] = "pending"
    completed_event: str | None = Field(default=None, exclude_if=lambda value: value is None)
    tag: str | None = Field(default=None, exclude_if=lambda value: value is None)
    label: str | None = Field(default=None, exclude_if=lambda value: value is None)
    resolution_account: str | None = Field(default=None, exclude_if=lambda value: value is None)

    @model_validator(mode="after")
    def actual_optional_choice(self) -> "Comparison":
        if self.outcome == "pending":
            if any((self.completed_event, self.tag, self.label, self.resolution_account)):
                raise ValueError("An unresolved optional Tag has no invented completed outcome")
        elif not self.completed_event or not self.resolution_account:
            raise ValueError("Preserve the actual comparer-authored completion")
        elif (self.outcome == "given") != bool(self.tag and self.label):
            raise ValueError("Only an actual given Tag has a Tag identity and label")
        elif self.outcome == "declined" and (self.tag is not None or self.label is not None):
            raise ValueError("A genuine decline creates no Tag")
        return self


KINDS: dict[type[Model], str] = {
    Disclosure: "vatgrown_dna_disclosure",
    Comparison: "vatgrown_dna_comparison",
}


def records[T: Model](state: GameState, model: type[T]) -> tuple[T, ...]:
    return tuple(
        model.model_validate_json(value["body"])
        for value in state.facts
        if value.get("kind") == KINDS[model]
    )


def get[T: Model](state: GameState, model: type[T], key: str) -> T:
    values = [value for value in records(state, model) if value.model_dump()["id"] == key]
    if len(values) != 1:
        raise ValueError("Recover this exact original DNA source")
    return values[0]


def put(state: GameState, value: Disclosure | Comparison) -> None:
    kind = KINDS[type(value)]
    state.facts = [
        fact
        for fact in state.facts
        if not (fact.get("kind") == kind and fact.get("id") == value.id)
    ]
    state.facts.append(dict(kind=kind, id=value.id, body=value.model_dump_json()))


def compare(
    state: GameState,
    campaign: str,
    basis: BasisProof,
    comparer: ActorRef,
    controller: int,
    owner_controller: int,
    cast: SceneCast,
    account: str,
    event: str,
) -> Comparison:
    if any(value.basis.actor == basis.actor for value in records(state, Comparison)):
        raise ValueError("This original person's first campaign comparison is already recorded")
    value = Comparison(
        id=identity(campaign, basis.actor.token),
        basis=basis,
        comparer=comparer,
        controller=controller,
        owner_controller=owner_controller,
        cast=cast,
        account=account,
        event=event,
    )
    put(state, value)
    return value


def complete(
    state: GameState,
    value: Comparison,
    event: str,
    account: str,
    *,
    tag: str | None = None,
    label: str | None = None,
) -> Comparison:
    if get(state, Comparison, value.id) != value or value.outcome != "pending":
        raise ValueError("The original comparer already settled this once-only source")
    result = Comparison.model_validate(
        value.model_dump()
        | dict(
            outcome="given" if tag is not None else "declined",
            tag=tag,
            label=label,
            completed_event=event,
            resolution_account=account,
        )
    )
    put(state, result)
    return result
