"""Original-person Marriage, shared Status and source-bound financial custody (PDF155)."""

import hashlib
from typing import Any, Literal
from uuid import NAMESPACE_URL, uuid5

from pydantic import Field

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef, Model, SceneCast

RULE = "handler-advancement.handler-advancement.intracadre-marriage"


class Acquisition(Model):
    id: str
    award: str
    handler: ActorRef
    appointment: str
    event: str
    account: str = Field(min_length=1, max_length=1200)
    first: ActorRef
    second: ActorRef
    financial: ActorRef
    punished: ActorRef
    status_from: ActorRef
    initial_permissions: tuple[int, int]


class PaymentQuote(Model):
    id: str
    marriage: str
    beneficiary: ActorRef
    wallet: ActorRef
    product: str
    detail: str
    frame: str | None
    price: int = Field(ge=0)
    event: str
    account: str = Field(min_length=1, max_length=1200)


class Approval(Model):
    id: str
    quote: str
    financial: ActorRef
    event: str
    account: str = Field(min_length=1, max_length=1200)


class Payment(Model):
    beneficiary: ActorRef
    wallet: ActorRef
    product: str
    detail: str
    price: int = Field(ge=0)
    quote: str | None = None
    approval: str | None = None


class PermissionFlow(Model):
    id: str
    marriage: str | None
    kind: Literal["grant", "purchase", "defeat_loss", "custody"]
    beneficiary: ActorRef
    wallet: ActorRef
    amount: int = Field(ge=0)
    before: int = Field(ge=0)
    after: int = Field(ge=0)
    event: str
    source: str
    product: str = ""
    detail: str = ""
    quote: str | None = None
    approval: str | None = None


class Allocation(Model):
    id: str
    marriage: str
    original: ActorRef
    subject: ActorRef
    source_event: str
    source_id: str
    work_id: str


class Caught(Model):
    id: str
    marriage: str
    action: str
    observer: ActorRef
    actor: ActorRef
    target: ActorRef
    observed_event: str
    cast: SceneCast
    event: str
    account: str = Field(min_length=1, max_length=1200)
    work: str


KINDS: dict[type[Model], str] = {
    Acquisition: "marriage_acquisition",
    PaymentQuote: "marriage_payment_quote",
    Approval: "marriage_payment_approval",
    PermissionFlow: "marriage_permission_flow",
    Allocation: "marriage_punishment_allocation",
    Caught: "marriage_caught_flirt",
}


def records[T: Model](state: GameState, model: type[T]) -> tuple[T, ...]:
    return tuple(
        model.model_validate_json(x["body"]) for x in state.facts if x.get("kind") == KINDS[model]
    )


def put(state: GameState, value: Model) -> None:
    identity = value.model_dump()["id"]
    kind = KINDS[type(value)]
    if any(x.get("kind") == kind and x.get("id") == identity for x in state.facts):
        raise ValueError("Preserve this immutable original Marriage source")
    state.facts.append(dict(kind=kind, id=identity, body=value.model_dump_json()))


def acquisitions(state: GameState) -> tuple[Acquisition, ...]:
    return records(state, Acquisition)


def _current(state: GameState, ref: ActorRef) -> None:
    sheet = state.sheets.get(ref.entity)
    if ref.kind != "pilot" or sheet is None or sheet.character_id != ref.incarnation:
        raise ValueError("MARRIAGE_PERSON_RECOVERY_REQUIRED: retain the original married Girls")


def marriage_for(state: GameState, actor: ActorRef) -> Acquisition | None:
    source = next((x for x in acquisitions(state) if actor in (x.first, x.second)), None)
    if source is not None:
        _current(state, source.first)
        _current(state, source.second)
    return source


def wallet(state: GameState, beneficiary: ActorRef) -> ActorRef:
    source = marriage_for(state, beneficiary)
    return source.financial if source is not None else beneficiary


def available(state: GameState, beneficiary: ActorRef) -> int:
    return state.sheets[wallet(state, beneficiary).entity].permissions


def status_groups(state: GameState) -> tuple[tuple[int, ...], ...]:
    groups: dict[int, tuple[int, ...]] = {}
    removed: set[int] = set()
    for source in acquisitions(state):
        _current(state, source.first)
        _current(state, source.second)
        pair = (int(source.first.entity), int(source.second.entity))
        anchor = int(source.status_from.entity)
        if not set(pair) <= set(state.order) or removed.intersection(pair):
            raise ValueError("MARRIAGE_STATUS_RECOVERY_REQUIRED: preserve the original roster")
        groups[anchor] = pair
        removed.update(pair)
    return tuple(
        groups[owner] if owner in groups else (owner,)
        for owner in state.order
        if owner in groups or owner not in removed
    )


def rank(state: GameState, owner: int) -> int:
    return next(i for i, group in enumerate(status_groups(state)) if owner in group)


def is_ace(state: GameState, owner: int) -> bool:
    return bool(state.order) and owner in status_groups(state)[0]


def is_dog(state: GameState, owner: int) -> bool:
    return bool(state.order) and owner in status_groups(state)[-1]


def frame(state: GameState, actor: ActorRef) -> str | None:
    sheet = state.sheets[actor.entity]
    return sheet.frame_runtime.id if sheet.frame_runtime else "initial:" + str(sheet.character_id)


def payment_for(
    state: GameState, actor: ActorRef, product: str, amount: int, detail: str = ""
) -> Payment:
    own_wallet = wallet(state, actor)
    if own_wallet == actor:
        return Payment(
            beneficiary=actor, wallet=actor, product=product, price=amount, detail=detail
        )
    consumed = {x.quote for x in records(state, PermissionFlow) if x.kind == "purchase"}
    source = marriage_for(state, actor)
    assert source is not None
    for quote in reversed(records(state, PaymentQuote)):
        approval = next((x for x in records(state, Approval) if x.quote == quote.id), None)
        if (
            quote.marriage == source.id
            and quote.beneficiary == actor
            and quote.wallet == own_wallet
            and quote.product == product
            and quote.detail == detail
            and quote.frame == frame(state, actor)
            and quote.price == amount
            and quote.id not in consumed
            and approval is not None
            and approval.financial == own_wallet
        ):
            return Payment(
                beneficiary=actor,
                wallet=own_wallet,
                product=product,
                detail=detail,
                price=amount,
                quote=quote.id,
                approval=approval.id,
            )
    raise ValueError("Request and obtain your partner's exact source-priced payment approval")


def _flow(
    state: GameState,
    actor: ActorRef,
    amount: int,
    event: str,
    source: str,
    kind: Literal["grant", "purchase", "defeat_loss"],
    payment: Payment | None = None,
) -> PermissionFlow:
    if amount < 0 or not event or not source:
        raise ValueError("Retain the real nonnegative Permission source and event")
    marriage = marriage_for(state, actor)
    payee = wallet(state, actor)
    sheet = state.sheets[payee.entity]
    before = sheet.permissions
    after = before + amount if kind == "grant" else before - amount
    if after < 0:
        raise ValueError("Insufficient actual shared Permissions; no charge was applied")
    identity = str(uuid5(NAMESPACE_URL, "marriage-flow:" + event + ":" + source))
    if any(x.id == identity for x in records(state, PermissionFlow)):
        raise ValueError("This actual Permission source has already been applied")
    value = PermissionFlow(
        id=identity,
        marriage=marriage.id if marriage else None,
        kind=kind,
        beneficiary=actor,
        wallet=payee,
        amount=amount,
        before=before,
        after=after,
        event=event,
        source=source,
        product=payment.product if payment else "",
        detail=payment.detail if payment else "",
        quote=payment.quote if payment else None,
        approval=payment.approval if payment else None,
    )
    if marriage is not None:
        put(state, value)
    sheet.permissions = after
    if payee != actor:
        sheet.revision += 1
    return value


def credit(
    state: GameState, beneficiary: ActorRef, amount: int, *, event: str, source: str
) -> PermissionFlow:
    return _flow(state, beneficiary, amount, event, source, "grant")


def debit(
    state: GameState,
    beneficiary: ActorRef,
    amount: int,
    *,
    event: str,
    source: str,
    payment: Payment,
) -> PermissionFlow:
    if payment != payment_for(state, beneficiary, payment.product, amount, payment.detail):
        raise ValueError("Use the exact current original payment authorization")
    return _flow(state, beneficiary, amount, event, source, "purchase", payment)


def defeat_loss(
    state: GameState, beneficiary: ActorRef, amount: int, *, event: str, source: str
) -> PermissionFlow:
    return _flow(state, beneficiary, amount, event, source, "defeat_loss")


def punishment_subject(state: GameState, original: ActorRef) -> ActorRef:
    source = marriage_for(state, original)
    return source.punished if source is not None else original


def allocate(
    state: GameState, original: ActorRef, *, source_event: str, source_id: str, work_id: str
) -> Allocation | None:
    source = marriage_for(state, original)
    if source is None:
        return None
    value = Allocation(
        id=str(uuid5(NAMESPACE_URL, "marriage-punishment:" + source_id)),
        marriage=source.id,
        original=original,
        subject=source.punished,
        source_event=source_event,
        source_id=source_id,
        work_id=work_id,
    )
    existing = next((x for x in records(state, Allocation) if x.id == value.id), None)
    if existing is not None:
        if existing != value:
            raise ValueError("Preserve the original source-owned Punishment allocation")
        return existing
    put(state, value)
    return value


def allocation_fields(state: GameState, source_id: str) -> dict[str, Any]:
    value = next((x for x in records(state, Allocation) if x.source_id == source_id), None)
    return (
        dict(marriage_allocation=value.id, marriage_offender=value.original.model_dump(mode="json"))
        if value is not None
        else {}
    )


def digest(value: Model) -> str:
    return hashlib.sha256(value.model_dump_json().encode()).hexdigest()
