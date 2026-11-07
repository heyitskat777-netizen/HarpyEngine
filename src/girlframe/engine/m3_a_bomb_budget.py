"""Finite direct Budget operations while actual A-Bomb Mission conditions are pending."""

from typing import Literal

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_strain import copy

Severity = Literal["low", "high"]


def pending(state: GameState) -> bool:
    return any(
        x.get("kind") == "a_bomb_budget_window" and x.get("open") == "yes" for x in state.facts
    )


def begin_condition(state: GameState, drop: str, event: str) -> None:
    if state.strain is None:
        raise ValueError("A real bomb requires existing Budget Strain")
    if not pending(state):
        state.facts.append(
            dict(kind="a_bomb_budget_anchor", event=event, value=state.strain.levels["budget"])
        )
    state.facts.append(dict(kind="a_bomb_budget_window", id=drop, event=event, open="yes"))


def record_write(state: GameState, *, source: str, event: str, value: Severity) -> None:
    """Called by the actual writer, including same-value writes; never infer from a diff."""
    if not pending(state):
        return
    if not source.strip() or not event.strip() or state.strain is None:
        raise ValueError("Prove the actual source of every pending Budget operation")
    operations = [x for x in state.facts if x.get("kind") == "a_bomb_budget_operation"]
    if any(x.get("source") == source and x.get("event") == event for x in operations):
        raise ValueError("A real Budget source writes once per canonical occurrence")
    state.facts.append(
        dict(
            kind="a_bomb_budget_operation",
            source=source,
            event=event,
            ordinal=str(len(operations)),
            value=value,
            waived="no",
        )
    )


def waive_operation(state: GameState, drop: str, *, event: str, waive: bool) -> None:
    window = next(
        (
            x
            for x in state.facts
            if x.get("kind") == "a_bomb_budget_window"
            and x.get("id") == drop
            and x.get("open") == "yes"
        ),
        None,
    )
    if window is None or state.strain is None:
        raise ValueError("Resolve the actual pending bomb condition once")
    operation = next(
        (
            x
            for x in state.facts
            if x.get("kind") == "a_bomb_budget_operation" and x.get("source") == drop
        ),
        None,
    )
    if operation is None:
        raise ValueError("Recover this bomb's actual direct Budget operation")
    operation["waived"] = "yes" if waive else "no"
    window.update(open="no", resolved_event=event)
    if waive:
        anchor = next(x for x in reversed(state.facts) if x.get("kind") == "a_bomb_budget_anchor")
        # The anchor identifies a single pending interval; earlier closed operations are excluded.
        index = state.facts.index(anchor)
        value = anchor["value"]
        for row in state.facts[index + 1 :]:
            if row.get("kind") == "a_bomb_budget_operation" and row.get("waived") != "yes":
                value = row["value"]
        state.strain = copy(state.strain, levels=state.strain.levels | {"budget": value})
