"""Original role-bound Conditioning roll, choices and applied effects."""

from typing import Annotated, Literal
from uuid import NAMESPACE_URL, uuid5

from pydantic import Field

from girlframe.engine.m2 import AssetState, GameState, IdentityState, PilotSheet, TagState
from girlframe.engine.m3_actor_bonds import change, depth, set_depth
from girlframe.engine.m3_actor_state import ActorRef, Model
from girlframe.engine.m3_core import install
from girlframe.engine.m3_identity_slots import bind, replacement_slot
from girlframe.engine.m3_leviathan_obsession import require_identity_change
from girlframe.engine.rolls import Face

RULE = "situational.situational.conditioning"
KIND = "situational_conditioning"
Label = Annotated[str, Field(min_length=1, max_length=120)]
Account = Annotated[str, Field(min_length=1, max_length=1200)]


class IdentityChoice(Model):
    name: Label
    replace: str | None = None


class TagChoice(Model):
    tag: str
    replace: str | None = None


class Effect(Model):
    account: Account


class Replace(Effect):
    kind: Literal["replace"] = "replace"
    identity: str
    label: Label


class Teach(Effect):
    kind: Literal["teach"] = "teach"
    labels: tuple[Label, ...] = Field(min_length=1, max_length=2)


class Embrace(Effect):
    kind: Literal["embrace"] = "embrace"
    choices: tuple[TagChoice, ...] = Field(min_length=1, max_length=2)


class Erase(Effect):
    kind: Literal["erase"] = "erase"
    identities: tuple[str, str]


class Bond(Effect):
    kind: Literal["bond"] = "bond"
    weaken: tuple[ActorRef, ...] = Field(default=(), max_length=25)


class Excise(Effect):
    kind: Literal["excise"] = "excise"
    asset: str
    replacement: Label | None = None


class Tag(Effect):
    kind: Literal["tag"] = "tag"
    label: Label


class Word(Effect):
    kind: Literal["word"] = "word"
    phrase: Label


Choice = Annotated[
    Replace | Teach | Embrace | Erase | Bond | Excise | Tag | Word, Field(discriminator="kind")
]


class Roll(Model):
    faces: tuple[Face, Face]
    trainer_bonus: Literal[1, 2, 3]
    identity_bonus: Literal[0, 1]

    @property
    def total(self) -> int:
        return sum(self.faces) + self.trainer_bonus + self.identity_bonus

    @property
    def count(self) -> int:
        return 1 if self.total <= 7 else 2 if self.total <= 10 else 3


class Utterance(Model):
    choice: int
    scene: str
    event: str
    released: str | None = None


class Conditioning(Model):
    id: str
    scene: str
    channel: int
    source_cast: tuple[str, str]
    trainee: ActorRef
    trainer: ActorRef
    trainee_controller: int
    trainer_controller: int
    offer: str
    event: str
    phase: Literal["offered", "consented", "choices", "confirm", "complete", "withdrawn"]
    shared_bonds: tuple[ActorRef, ...] = ()
    roll: Roll | None = None
    choices: tuple[Choice, ...] = ()
    account: str | None = None
    low_identity: IdentityChoice | None = None
    utterances: tuple[Utterance, ...] = ()


def records(state: GameState) -> tuple[Conditioning, ...]:
    return tuple(
        Conditioning.model_validate_json(x["body"]) for x in state.facts if x.get("kind") == KIND
    )


def find(state: GameState, identity: str) -> Conditioning | None:
    return next((x for x in records(state) if x.id == identity), None)


def put(state: GameState, value: Conditioning) -> None:
    state.facts = [x for x in state.facts if (x.get("kind"), x.get("id")) != (KIND, value.id)]
    state.facts.append(dict(kind=KIND, id=value.id, body=value.model_dump_json()))


def active_words(
    state: GameState, subject: ActorRef, trainer: ActorRef | None = None
) -> tuple[Conditioning, ...]:
    if subject.kind != "pilot":
        return ()
    return tuple(
        x
        for x in records(state)
        if x.trainee == subject
        and x.phase == "complete"
        and (trainer is None or x.trainer == trainer)
        and any(word.released is None for word in x.utterances)
    )


def unsaid(value: Conditioning) -> tuple[tuple[int, Word], ...]:
    if value.phase != "complete":
        return ()
    said = {x.choice for x in value.utterances}
    return tuple(
        (index, choice)
        for index, choice in enumerate(value.choices)
        if isinstance(choice, Word) and index not in said
    )


def release(state: GameState, subject: ActorRef, trainer: ActorRef, event: str) -> None:
    for source in active_words(state, subject, trainer):
        utterances = tuple(
            utterance.model_copy(update={"released": event})
            if utterance.released is None
            else utterance
            for utterance in source.utterances
        )
        put(state, source.model_copy(update={"utterances": utterances}))


def ordinary_count(sheet: PilotSheet) -> int:
    return sum(not x.protected or x.paired or x.am_limiter is not None for x in sheet.identities)


def text(value: str, limit: int) -> str:
    value = value.strip()
    if not 1 <= len(value) <= limit:
        raise ValueError("Supply the actual human-authored text.")
    return value


def removable(sheet: PilotSheet, identity: IdentityState) -> bool:
    return (
        not identity.protected
        and not identity.paired
        and not identity.am_limiter
        and identity.id not in sheet.sedation_locked
        and not identity.obsession_sources
    )


def excisable(sheet: PilotSheet, asset: AssetState) -> bool:
    return (
        asset.family == "girl"
        and asset.battery_asset is None
        and asset.intrinsic is None
        and not asset.classification_event
        and not asset.void
        and not asset.concealed
    )


def _remove_identity(state: GameState, subject: ActorRef, identity: str) -> IdentityState:
    sheet = state.sheets[subject.entity]
    chosen = next((x for x in sheet.identities if x.id == identity and removable(sheet, x)), None)
    if chosen is None:
        raise ValueError("Choose an actual removable Identity of the original trainee.")
    require_identity_change(state, subject, (chosen.id,))
    sheet.identities.remove(chosen)
    return chosen


def _identity(
    state: GameState,
    subject: ActorRef,
    identity: str,
    choice: IdentityChoice,
    allow_duplicates: bool,
) -> None:
    sheet = state.sheets[subject.entity]
    removed = (
        _remove_identity(state, subject, choice.replace) if choice.replace is not None else None
    )
    if ordinary_count(sheet) >= 4:
        raise ValueError("There is no free ordinary Identity slot.")
    label = text(choice.name, 120)
    if not allow_duplicates and any(
        x.name.casefold() == label.casefold() for x in sheet.identities
    ):
        raise ValueError("Choose an Identity distinct from the remaining labels.")
    slot = removed.slot if removed is not None else replacement_slot(sheet, None)
    sheet.identities.append(IdentityState(id=identity, name=label, slot=slot))


def preview(
    original: GameState,
    value: Conditioning,
    event: str,
    *,
    allow_duplicates: bool,
    low_identity: IdentityChoice | None = None,
) -> GameState:
    """Preview and final confirmation apply the same choices against original resources."""
    state = GameState.model_validate_json(original.model_dump_json())
    subject = value.trainee
    sheet = bind(state.sheets[subject.entity])
    state.sheets[subject.entity] = sheet
    for index, choice in enumerate(value.choices):
        text(choice.account, 1200)
        root = f"{value.id}:{index}"
        fresh = str(uuid5(NAMESPACE_URL, root))
        if isinstance(choice, Replace):
            _identity(
                state,
                subject,
                fresh,
                IdentityChoice(name=choice.label, replace=choice.identity),
                allow_duplicates,
            )
        elif isinstance(choice, Teach):
            for n, label in enumerate(choice.labels):
                _identity(
                    state, subject, f"{fresh}:{n}", IdentityChoice(name=label), allow_duplicates
                )
        elif isinstance(choice, Embrace):
            for n, selection in enumerate(choice.choices):
                source = next(
                    (x for x in sheet.tags if x.id == selection.tag and not x.rejection_pending),
                    None,
                )
                if source is None:
                    raise ValueError("Embrace an actual Tag with no rejection pending.")
                _identity(
                    state,
                    subject,
                    f"{fresh}:{n}",
                    IdentityChoice(name=source.label, replace=selection.replace),
                    allow_duplicates,
                )
                sheet.tags.remove(source)
        elif isinstance(choice, Erase):
            for selected in choice.identities:
                _remove_identity(state, subject, selected)
        elif isinstance(choice, Bond):
            if len(set(choice.weaken)) != len(choice.weaken) or not set(choice.weaken) <= set(
                value.shared_bonds
            ):
                raise ValueError("Weaken only Bonds shared by the original trainee.")
            state = set_depth(state, subject, value.trainer, 2, event)
            for other in choice.weaken:
                state = change(state, subject, other, -1, event)
            sheet = state.sheets[subject.entity]
        elif isinstance(choice, Excise):
            selected_asset = next(
                (x for x in sheet.assets if x.id == choice.asset and excisable(sheet, x)), None
            )
            if selected_asset is None:
                raise ValueError("Choose an actual nonconcealed ordinary Girl Asset.")
            sheet.assets.remove(selected_asset)
            if choice.replacement is not None:
                sheet = install(
                    sheet,
                    AssetState(id=fresh, family="girl", name=text(choice.replacement, 120)),
                    state=state,
                ).sheet
                state.sheets[subject.entity] = sheet
        elif isinstance(choice, Tag):
            sheet.tags.append(
                TagState(
                    id=fresh,
                    label=text(choice.label, 120),
                    giver=value.trainer_controller,
                    giver_actor=value.trainer,
                    giver_character=value.trainer.incarnation,
                    observers=(value.trainee_controller, value.trainer_controller),
                )
            )
        elif isinstance(choice, Word):
            text(choice.phrase, 120)
    if low_identity is not None:
        if value.roll is None or value.roll.count != 1:
            raise ValueError("Only the actual low result lets the trainee write a new Identity.")
        if low_identity.replace is not None and ordinary_count(sheet) < 4:
            raise ValueError("Write the low-result Identity into the available slot.")
        _identity(
            state,
            subject,
            str(uuid5(NAMESPACE_URL, value.id + ":low")),
            low_identity,
            allow_duplicates,
        )
    sheet.revision += 1
    return state


def shareable_bonds(state: GameState, value: Conditioning) -> tuple[ActorRef, ...]:
    """Only ordinary known characters. Hidden world roles need individual disclosure."""
    from girlframe.engine.m3_actor_bonds import current_ref

    refs = [current_ref(state, uid) for uid in state.order if uid != value.trainee_controller]
    if state.handler is not None and state.handler not in state.order:
        refs.append(current_ref(state, state.handler))
    if state.world:
        refs.extend(
            ActorRef(kind="npc", entity=x.id) for x in state.world.npcs if x.revealed and x.alive
        )
    return tuple(x for x in refs if x != value.trainer and depth(state, value.trainee, x) > 0)
