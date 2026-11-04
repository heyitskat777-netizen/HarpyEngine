"""User-scoped request projections; no new game mechanics."""

from dataclasses import dataclass

SCOPES = ("pending", "you", "waiting", "history")
CATEGORIES = (
    "all",
    "bonds",
    "mentors",
    "court",
    "pair",
    "playbook",
    "plays",
    "missions",
    "off_duty",
)


@dataclass(frozen=True)
class InboxItem:
    key: str
    source: str
    identity: str
    revision: int
    category: str
    title: str
    counterpart: str
    state: str
    incoming: bool
    stale: bool
    effect: str
    details: str
    primary: str | None = None
    secondary: str | None = None
    task: str | None = None
    target: int | None = None
    sort_time: str = ""


@dataclass(frozen=True)
class InboxPage:
    item: InboxItem | None
    index: int
    total: int
    counts: dict[str, int]
    window: tuple[InboxItem, ...] = ()
