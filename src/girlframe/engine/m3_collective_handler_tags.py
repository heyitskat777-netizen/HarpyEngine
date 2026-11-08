"""Source-owned collective Tag proposals; each actual human supplies her own agreement."""

from typing import Literal
from uuid import NAMESPACE_URL, uuid5

from pydantic import Field, model_validator

from girlframe.engine.m2 import GameState, TagState
from girlframe.engine.m3_actor_state import ActorRef, Model
from girlframe.engine.m3_budget_tags import original_girl_alive
from girlframe.engine.m3_handler_consequences import same_handler_body


class Entitlement(Model):
    id: str = Field(min_length=1)
    handler: ActorRef
    selection_event: str = Field(min_length=1)
    source_event: str = Field(min_length=1)


class Proposal(Model):
    id: str = Field(min_length=1)
    revision: int = Field(ge=1)
    entitlement: str = Field(min_length=1)
    period: str = Field(min_length=1)
    handler: ActorRef
    girls: tuple[ActorRef, ...] = Field(min_length=1)
    roll_event: str = Field(min_length=1)
    proposer: ActorRef
    label: str = Field(min_length=1, max_length=120)
    account: str = Field(min_length=1, max_length=1200)
    votes: tuple[ActorRef, ...] = ()
    ended: tuple[ActorRef, ...] = ()
    stage: Literal["proposed", "given", "declined", "withdrawn", "original_ended"]
    event: str = Field(min_length=1)
    tag: str | None = None

    @model_validator(mode="after")
    def actual_consensus(self) -> "Proposal":
        if (
            self.handler.kind != "handler"
            or any(x.kind != "pilot" for x in self.girls)
            or len(set(self.girls)) != len(self.girls)
            or self.proposer not in self.girls
            or len(set(self.votes)) != len(self.votes)
            or not set(self.votes) <= set(self.girls)
            or len(set(self.ended)) != len(self.ended)
            or not set(self.ended) <= set(self.girls)
            or not self.label.strip()
            or not self.account.strip()
        ):
            raise ValueError("Retain the exact original girls and their distinct actual agreements")
        if self.stage == "given" and (
            not self.tag
            or not (set(self.girls) - set(self.ended))
            or not (set(self.girls) - set(self.ended)) <= set(self.votes)
        ):
            raise ValueError("A collective Tag requires every remaining original Girl's agreement")
        return self


def entitlements(state: GameState) -> tuple[Entitlement, ...]:
    entries = tuple(
        Entitlement.model_validate_json(x["body"])
        for x in state.facts
        if x.get("kind") == "budget_collective_tag_entitlement"
    )
    if len({x.id for x in entries}) != len(entries):
        raise ValueError("An actual Endgame grants one original collective Tag entitlement")
    return entries


def proposals(state: GameState) -> tuple[Proposal, ...]:
    latest: dict[str, Proposal] = {}
    for fact in state.facts:
        if fact.get("kind") != "budget_collective_tag_proposal":
            continue
        value = Proposal.model_validate_json(fact["body"])
        old = latest.get(value.id)
        if value.revision != (old.revision + 1 if old else 1):
            raise ValueError("Recover the actual append-only collective proposal history")
        latest[value.id] = value
    return tuple(latest.values())


def save(state: GameState, proposal: Proposal) -> None:
    state.facts.append(dict(kind="budget_collective_tag_proposal", body=proposal.model_dump_json()))


def apply(state: GameState, proposal: Proposal, event: str) -> Proposal:
    """Commit only actual unanimity; this is an ordinary removable Handler Tag."""
    living = set(proposal.girls) - set(proposal.ended)
    if not living or not living <= set(proposal.votes):
        return proposal
    if not same_handler_body(state, proposal.handler) or any(
        not original_girl_alive(state, x) for x in living
    ):
        raise ValueError(
            "Review the actual original participants' endings before this collective gift"
        )
    tag = str(uuid5(NAMESPACE_URL, "collective-handler-tag:" + proposal.id))
    if any(x.id == tag for x in state.handler_tags):
        raise ValueError("This actual period's collective Tag has already been given")
    state.handler_tags.append(
        TagState(
            id=tag,
            label=proposal.label,
            giver=int(proposal.proposer.entity),
            giver_actor=proposal.proposer,
            observers=tuple(sorted({int(x.entity) for x in living})),
        )
    )
    return proposal.model_copy(update=dict(stage="given", tag=tag, event=event))
