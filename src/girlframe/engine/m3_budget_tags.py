"""Actual Budget Endgame gifts; persistence affects Handler Tag use only."""

from typing import Literal
from uuid import NAMESPACE_URL, uuid5

from pydantic import Field, model_validator

from girlframe.engine.m2 import GameState, TagState
from girlframe.engine.m3_actor_state import ActorRef, Model
from girlframe.engine.m3_handler_consequences import same_handler_body


class Gift(Model):
    id: str = Field(min_length=1)
    revision: int = Field(ge=1)
    source_work: str = Field(min_length=1)
    source_event: str = Field(min_length=1)
    handler: ActorRef
    girl: ActorRef
    nominated_event: str = Field(min_length=1)
    stage: Literal["awaiting_girl", "given", "original_ended"]
    account: str = Field(min_length=1, max_length=1200)
    tag: str | None = None
    label: str | None = Field(default=None, min_length=1, max_length=120)
    given_event: str | None = None

    @model_validator(mode="after")
    def original_roles(self) -> "Gift":
        if self.handler.kind != "handler" or self.girl.kind != "pilot" or not self.account.strip():
            raise ValueError("Retain the actual original Cadre Girl and Handler roles")
        if (self.stage == "given") != all((self.tag, self.label, self.given_event)):
            raise ValueError("A given persistent Tag requires its actual Tag and source event")
        return self


def gifts(state: GameState) -> tuple[Gift, ...]:
    latest: dict[str, Gift] = {}
    for fact in state.facts:
        if fact.get("kind") != "budget_persistent_handler_tag":
            continue
        entry = Gift.model_validate_json(fact["body"])
        old = latest.get(entry.id)
        if entry.revision != (old.revision + 1 if old else 1):
            raise ValueError("Recover the original append-only Budget Tag history")
        latest[entry.id] = entry
    return tuple(latest.values())


def save(state: GameState, gift: Gift) -> None:
    state.facts.append(dict(kind="budget_persistent_handler_tag", body=gift.model_dump_json()))


def pending(state: GameState, identity: str) -> Gift:
    gift = next((x for x in gifts(state) if x.id == identity), None)
    if gift is None or gift.stage != "awaiting_girl":
        raise ValueError("Reopen the actual original pending Budget Tag gift")
    return gift


def original_girl_alive(state: GameState, girl: ActorRef) -> bool:
    sheet = state.sheets.get(girl.entity)
    if sheet is not None and sheet.character_id == girl.incarnation:
        return True
    archive = next((x for x in state.career_archives if x.actor == girl), None)
    if archive is None or archive.ending in ("death", "execution"):
        return False
    if archive.ending == "harpy":
        return any(
            x.origin == girl and x.original_archive == archive.id and x.alive
            for x in state.harpy_states
        )
    # Retirement/reserve/custody do not create a new person. Giving a descriptor
    # spends no successor resources and requires no invented position or travel.
    return True


def give(original: GameState, identity: str, label: str, account: str, event: str) -> GameState:
    state = GameState.model_validate_json(original.model_dump_json())
    gift = pending(state, identity)
    if not original_girl_alive(state, gift.girl) or not same_handler_body(state, gift.handler):
        raise ValueError("Only the actual original Girl can give this original Handler her Tag")
    if not label.strip() or not account.strip() or not event.strip():
        raise ValueError("The actual Girl must name and describe her Tag gift")
    tag = str(uuid5(NAMESPACE_URL, "budget-persistent-tag:" + gift.source_work))
    if any(x.id == tag for x in state.handler_tags):
        raise ValueError("This exact Endgame Tag has already been given")
    state.handler_tags.append(
        TagState(
            id=tag,
            label=label.strip(),
            giver=int(gift.girl.entity),
            giver_actor=gift.girl,
            observers=(int(gift.girl.entity),),
        )
    )
    save(
        state,
        gift.model_copy(
            update=dict(
                revision=gift.revision + 1,
                stage="given",
                tag=tag,
                label=label.strip(),
                account=account.strip(),
                given_event=event,
            )
        ),
    )
    return state


def persistent(state: GameState, handler: ActorRef, tag: str) -> bool:
    return (
        handler.kind == "handler"
        and same_handler_body(state, handler)
        and any(
            x.stage == "given" and x.tag == tag and same_handler_body(state, x.handler)
            for x in gifts(state)
        )
    )
