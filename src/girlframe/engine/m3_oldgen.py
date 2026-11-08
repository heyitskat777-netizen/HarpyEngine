"""Actual original maxims, one-use advice and source-bound Oldgen consequences."""

from typing import Literal

from girlframe.engine.creation_details import MAXIMS
from girlframe.engine.m2 import GameState, IdentityState
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef, Model, SceneCast
from girlframe.engine.m3_girl_runtime_state import has_rule

RULE = "girl.oldgen.just-the-way-it-is"
ADVICE = "girl.oldgen.old-dog-new-pups"
PLAY = "old_dog_new_pups"


class Maxim(Model):
    id: str
    owner: ActorRef
    subject: ActorRef | None = None
    text: str
    event: str
    advice: str | None = None
    slot: int | None = None
    high: bool = False


class Advice(Model):
    id: str
    actor: ActorRef
    target: ActorRef
    caster: int
    counterpart: int
    handler: int
    cast: SceneCast
    total: int
    heat: int
    roll_event: str
    event: str
    maxim: str
    choice: str


class PoorOutcome(Model):
    id: str
    maxim: str
    handler: int
    cast: SceneCast
    event: str
    account: str


class Use(Model):
    id: str
    maxim: str
    owner: ActorRef
    subject: ActorRef
    kind: Literal["reinforce", "reject"]
    event: str
    account: str
    tag: str | None = None
    replaced: str | None = None
    replacement: str | None = None
    poor: str | None = None


KINDS: dict[type[Model], str] = {
    Maxim: "oldgen_maxim",
    Advice: "oldgen_advice",
    PoorOutcome: "oldgen_poor",
    Use: "oldgen_use",
}


def records[T: Model](state: GameState, model: type[T]) -> tuple[T, ...]:
    return tuple(
        model.model_validate_json(x["body"]) for x in state.facts if x.get("kind") == KINDS[model]
    )


def put(state: GameState, value: Model) -> None:
    kind, identity = KINDS[type(value)], value.model_dump()["id"]
    if any(x.get("kind") == kind and x.get("id") == identity for x in state.facts):
        raise ValueError("Preserve the immutable original Oldgen source")
    state.facts.append(dict(kind=kind, id=identity, body=value.model_dump_json()))


def base_maxims(state: GameState, owner: int) -> tuple[Maxim, ...]:
    sheet = state.sheets.get(str(owner))
    if sheet is None or sheet.girl != "OLDGEN" or not has_rule(sheet, RULE, "OLDGEN"):
        return ()
    setup = sheet.girl_runtime.setup if sheet.girl_runtime else None
    details = sheet.review.creation.girl_details
    selected = (
        setup.maxims if setup and setup.book == "OLDGEN" else details.maxims if details else ()
    )
    if len(selected) != 2:
        raise ValueError("Recover this actual Oldgen's two chosen printed maxims")
    actor = current_ref(state, owner)
    return tuple(
        Maxim(
            id="oldgen-base:" + actor.token + ":" + str(x),
            owner=actor,
            text=MAXIMS[x],
            event=setup.source_event if setup else sheet.source_fingerprint,
            slot=x,
        )
        for x in selected
    )


def get(state: GameState, identity: str) -> Maxim:
    value = next((x for x in records(state, Maxim) if x.id == identity), None)
    if value is None:
        value = next(
            (
                x
                for sheet in state.sheets.values()
                for x in base_maxims(state, sheet.owner)
                if x.id == identity
            ),
            None,
        )
    if value is None:
        raise ValueError("Recover the actual original owned maxim")
    return value


def available(state: GameState, value: Maxim) -> bool:
    sheet = state.sheets.get(value.owner.entity)
    if sheet is None or sheet.character_id != value.owner.incarnation:
        return False
    return (
        value.slot not in sheet.maxims_marked
        if value.slot is not None
        else not any(x.maxim == value.id for x in records(state, Use))
    )


def marked_maxims(state: GameState, owner: int) -> tuple[tuple[str, str], ...]:
    return tuple(
        ("oldgen:" + str(x.slot), x.text)
        for x in base_maxims(state, owner)
        if not available(state, x)
    )


def unmark_maxim(state: GameState, owner: int, token: str) -> bool:
    if not token.startswith("oldgen:"):
        return False
    if token not in {x[0] for x in marked_maxims(state, owner)}:
        raise ValueError("Choose an actual marked base maxim under this Identity-unmark grant")
    slot = int(token.split(":", 1)[1])
    sheet = state.sheets[str(owner)]
    sheet.maxims_marked = tuple(x for x in sheet.maxims_marked if x != slot)
    sheet.revision += 1
    return True


def replacements(state: GameState, subject: ActorRef) -> tuple[IdentityState, ...]:
    sheet = state.sheets.get(subject.entity)
    if subject.kind != "pilot" or sheet is None or sheet.character_id != subject.incarnation:
        return ()
    return tuple(
        x
        for x in sheet.identities
        if not x.protected and not x.paired and not x.obsession_sources and x.am_limiter is None
    )


def mark(
    state: GameState, value: Maxim, use: Use, *, name: str = "", duplicates: bool = False
) -> None:
    if (
        get(state, value.id) != value
        or not available(state, value)
        or use.maxim != value.id
        or use.owner != value.owner
        or use.subject == value.owner
        or (value.subject is not None and use.subject != value.subject)
    ):
        raise ValueError("Use the original available maxim against its actual other Girl")
    if use.replaced is not None:
        poor = next(
            (x for x in records(state, PoorOutcome) if x.id == use.poor and x.maxim == value.id),
            None,
        )
        old = next((x for x in replacements(state, use.subject) if x.id == use.replaced), None)
        sheet = state.sheets[use.subject.entity]
        if (
            not value.high
            or use.kind != "reject"
            or poor is None
            or old is None
            or not name.strip()
            or len(name) > 120
            or not use.replacement
            or (
                not duplicates
                and any(x.name.casefold() == name.casefold() for x in sheet.identities)
            )
        ):
            raise ValueError(
                "Prove actual high advice, rejection and poor outcome, "
                "then choose a legal Identity rewrite"
            )
        # A rewrite retains the original resource's mark, slot and Sedation lock.
        sheet.identities = [
            x.model_copy(update={"name": name.strip()}) if x.id == old.id else x
            for x in sheet.identities
        ]
        sheet.revision += 1
    elif use.kind == "reinforce":
        state.sheets[use.subject.entity].heat += 2
        state.sheets[use.subject.entity].revision += 1
    elif use.tag is None:
        raise ValueError("A rejected maxim grants its actual authored Tag")
    if value.slot is not None:
        own = state.sheets[value.owner.entity]
        own.maxims_marked = tuple(sorted((*own.maxims_marked, value.slot)))
        own.revision += 1
    put(state, use)
