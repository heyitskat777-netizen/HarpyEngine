"""Sparse witnessed NPC resources for Nanobot care, never a controller's Girl sheet."""

from pydantic import Field, model_validator

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef, Model

KIND = "npc_treatment_resources"


class NpcIdentity(Model):
    id: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=120)
    marked: bool


class HeatAward(Model):
    action: str = Field(min_length=1)
    amount: int = Field(ge=0)
    event: str = Field(min_length=1)


class NpcResources(Model):
    id: str
    actor: ActorRef
    body_fact: str
    body_event: str
    brain: str
    vessel: str
    author: ActorRef
    controller: int = Field(gt=0)
    audience: tuple[int, ...]
    source_event: str
    account: str = Field(min_length=1, max_length=1200)
    heat: int = Field(ge=0)
    identities: tuple[NpcIdentity, ...] = Field(max_length=4)
    awards: tuple[HeatAward, ...] = ()
    event: str

    @model_validator(mode="after")
    def original_sparse_inventory(self) -> "NpcResources":
        if (
            self.actor.kind != "npc"
            or self.author.kind != "handler"
            or not self.account.strip()
            or any(not x.name.strip() for x in self.identities)
            or len({x.id for x in self.identities}) != len(self.identities)
            or len({x.action for x in self.awards}) != len(self.awards)
            or not all(
                (
                    self.id,
                    self.body_fact,
                    self.body_event,
                    self.brain,
                    self.vessel,
                    self.source_event,
                    self.event,
                )
            )
        ):
            raise ValueError("Preserve one witnessed original NPC resource inventory")
        return self


def original(state: GameState, target: ActorRef) -> NpcResources | None:
    values = [
        NpcResources.model_validate_json(value["body"])
        for value in state.facts
        if value.get("kind") == KIND
    ]
    found = [value for value in values if value.actor == target]
    if len(found) > 1:
        raise ValueError("Recover the single original NPC resource inventory")
    return found[0] if found else None


def current(state: GameState, target: ActorRef) -> NpcResources | None:
    """Pure projection requires its original live body; services prove event history."""
    from girlframe.engine.m3_changeling import BodyFact, records

    value = original(state, target)
    npc = (
        next((x for x in state.world.npcs if x.id == target.entity), None) if state.world else None
    )
    if value is None or npc is None or not npc.alive or npc.source_kind is not None:
        return None
    body = next((x for x in records(state, BodyFact) if x.id == value.body_fact), None)
    if (
        body is None
        or body.actor != target
        or body.event != value.body_event
        or body.brain != value.brain
        or body.vessel != value.vessel
        or body.reset_source
        or body.reset_record
        or body.kind not in ("human_npc", "other")
    ):
        return None
    return value


def put(state: GameState, value: NpcResources) -> None:
    old = original(state, value.actor)
    if old is not None and old.model_dump(
        exclude={"heat", "identities", "awards", "event"}
    ) != value.model_dump(exclude={"heat", "identities", "awards", "event"}):
        raise ValueError("Do not reauthor the witnessed original NPC inventory")
    if old is not None:
        if (
            tuple((x.id, x.name) for x in old.identities)
            != tuple((x.id, x.name) for x in value.identities)
            or value.awards[: len(old.awards)] != old.awards
        ):
            raise ValueError("Preserve actual NPC Identities and original Heat awards")
    state.facts = [
        fact
        for fact in state.facts
        if not (fact.get("kind") == KIND and fact.get("id") == value.id)
    ]
    state.facts.append(dict(kind=KIND, id=value.id, body=value.model_dump_json()))


def award(value: NpcResources, action: str, amount: int, event: str) -> NpcResources:
    given = next((x for x in value.awards if x.action == action), None)
    if given is not None:
        if given.amount != amount:
            raise ValueError("Preserve the original source Heat award")
        return value
    actual = HeatAward(action=action, amount=amount, event=event)
    return value.model_copy(
        update=dict(heat=value.heat + amount, awards=(*value.awards, actual), event=event)
    )


def unmark(value: NpcResources, identity: str | None, event: str) -> NpcResources:
    if identity is None:
        return value
    selected = next((x for x in value.identities if x.id == identity and x.marked), None)
    if selected is None:
        raise ValueError("Choose one actual marked NPC Identity")
    return value.model_copy(
        update=dict(
            identities=tuple(
                x.model_copy(update=dict(marked=False)) if x.id == identity else x
                for x in value.identities
            ),
            event=event,
        )
    )
