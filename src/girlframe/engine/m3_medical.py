"""Actual waking and source-backed Girl Play exchange after Defeat."""

from pydantic import Field, model_validator

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef, Model, ProfileBinding
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_girl_runtime_state import GirlRuntime, PlaySwap, has_rule
from girlframe.engine.m3_physical import medical_recovery
from girlframe.engine.m3_standards import RULE as STANDARD_RULE
from girlframe.engine.m3_standards import ready as standards_ready
from girlframe.engine.rules_registry import Registry

BOOKS = {
    "princess": "PRINCESS",
    "mockingbird": "MOCKINGBIRD",
    "stim-blissed": "STIM-BLISSED",
    "newgirl": "NEWGIRL",
    "casualty": "CASUALTY",
    "oldgen": "OLDGEN",
    "vatgrown": "VATGROWN",
    "alpha": "ALPHA",
    "am": "AM",
    "bonded": "BONDED",
}
# Each consumer is integrated by the root agent through has_rule, rather than class identity.
SUPPORTED_BORROWED = frozenset(
    {
        "girl.princess.objectively-beautiful",
        "girl.alpha.itching-for-a-fight",
        "girl.alpha.nothing-more-than-a-hound",
        "girl.oldgen.elder-bitch",
        STANDARD_RULE,
    }
)
PROTECTED_REMOVAL = frozenset({"girl.bonded.bonded-pair"})


class Care(Model):
    account: str = Field(min_length=1, max_length=1200)
    restore_vitals: bool = False

    @model_validator(mode="after")
    def actual_help(self) -> "Care":
        if not self.account.strip():
            raise ValueError("Describe the actual medical help and waking")
        return self


class Exchange(Model):
    removed: str = Field(min_length=1, max_length=180)
    acquired: str = Field(min_length=1, max_length=180)


def rule_book(identity: str) -> str | None:
    parts = identity.split(".")
    return BOOKS.get(parts[1]) if len(parts) >= 3 and parts[0] == "girl" else None


def choices(
    state: GameState, actor: ActorRef, registry: Registry
) -> dict[str, list[dict[str, str]]]:
    if actor.kind != "pilot" or actor.entity not in state.sheets:
        raise ValueError("A medical Play exchange belongs to an actual Girl")
    sheet = state.sheets[actor.entity]
    used = {x.girl for x in state.sheets.values()}
    removable: list[dict[str, str]] = []
    borrowed: list[dict[str, str]] = []
    unsupported: list[dict[str, str]] = []
    for entry in registry.entries:
        book = rule_book(entry.id)
        if book is None or entry.scope != "girl" or entry.kind not in ("play", "mechanic"):
            continue
        record = dict(id=entry.id, name=entry.title, playbook=book)
        if has_rule(sheet, entry.id, book):
            if entry.id not in PROTECTED_REMOVAL:
                removable.append(record)
        elif book not in used:
            (borrowed if entry.id in SUPPORTED_BORROWED else unsupported).append(record)
    return dict(removed=removable, acquired=borrowed, runtime_pending=unsupported)


def wake(
    original: GameState,
    actor: ActorRef,
    bindings: tuple[ProfileBinding, ...],
    care: Care,
    event: str,
) -> GameState:
    view = resolve(original, actor, bindings, require_current_profile=False)
    if (
        view.rules != "girl_frame"
        or original.sheets[actor.entity].medical_state != "unconscious_injured"
    ):
        raise ValueError("The original Girl must still have this Defeat injury")
    state = medical_recovery(
        original, bindings, actor, event, care.account, restore_vitals=care.restore_vitals
    )
    body = next(x for x in state.placements if x.actor == actor)
    if not body.vitals_active:
        raise ValueError(
            "Actual waking requires active vital signs or explicit medical restoration"
        )
    sheet = state.sheets[actor.entity]
    sheet.medical_state = "fit"
    sheet.revision += 1
    return state


def exchange(
    original: GameState,
    actor: ActorRef,
    bindings: tuple[ProfileBinding, ...],
    selected: Exchange,
    registry: Registry,
    event: str,
) -> GameState:
    resolve(original, actor, bindings, require_current_profile=False)
    if actor.kind != "pilot" or original.sheets[actor.entity].medical_state != "fit":
        raise ValueError("Wake the original Girl before the required Play exchange")
    state = GameState.model_validate_json(original.model_dump_json())
    available = choices(state, actor, registry)
    if selected.removed in PROTECTED_REMOVAL:
        raise ValueError("UNSUPPORTED_RULE: protected Paired setup needs its full removal workflow")
    if selected.removed not in {x["id"] for x in available["removed"]}:
        raise ValueError("Choose one currently available original Girl Play to give up")
    if selected.acquired in {x["id"] for x in available["runtime_pending"]}:
        raise ValueError("UNSUPPORTED_RULE: this borrowed Girl Play's runtime is still unfinished")
    target = next((x for x in available["acquired"] if x["id"] == selected.acquired), None)
    if target is None:
        raise ValueError("Choose an available rule from a currently unused base Girl playbook")
    sheet = state.sheets[actor.entity]
    if selected.acquired == STANDARD_RULE and not standards_ready(sheet):
        raise ValueError(
            "STANDARDS_REQUIRED: all three actual choosers must provide standards first"
        )
    runtime = sheet.girl_runtime or GirlRuntime()
    if not event or any(x.source_event == event for x in runtime.swaps):
        raise ValueError("This medical exchange source is missing or already applied")
    sheet.girl_runtime = runtime.model_copy(
        update={
            "swaps": runtime.swaps
            + (
                PlaySwap(
                    removed_rule=selected.removed,
                    acquired_rule=selected.acquired,
                    source_playbook=target["playbook"],
                    source_event=event,
                ),
            )
        }
    )
    sheet.revision += 1
    return state
