"""Actual Harpy/Girl Flirt resources and source-bound owed Tag restrictions."""

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef


def copy_state(state: GameState, changed: GameState) -> None:
    for field in GameState.model_fields:
        setattr(state, field, getattr(changed, field))


def unmark(state: GameState, ref: ActorRef, selected: tuple[str, ...], maximum: int) -> None:
    if len(selected) != len(set(selected)) or len(selected) > maximum:
        raise ValueError("Choose only the printed number of actual marked Identities")
    if ref.kind == "pilot":
        raise ValueError("Use the actual Pilot's source-proved unmark service")
    from girlframe.engine.m3_harpy_defeat import harpy, update

    value = harpy(state, ref)
    if set(selected) - {x.id for x in value.identities if x.marked}:
        raise ValueError("Unmark only this actual Harpy's marked Identities")
    if selected:
        copy_state(
            state,
            update(
                state,
                ref,
                identities=tuple(
                    x.model_copy(update={"marked": False}) if x.id in selected else x
                    for x in value.identities
                ),
            ),
        )


def clear_tag_debt(state: GameState, actor: ActorRef, tag: str) -> None:
    """Call only after an actual embrace/reject, never infer consent from absence."""
    for item in state.obligations:
        if (
            item.kind == "harpy_cannot_refuse_until_tag_resolved"
            and item.state == "pending"
            and ActorRef.model_validate_json(item.details["actor"]) == actor
            and item.details["tag"] == tag
        ):
            item.state = "fulfilled"


def assert_can_refuse(state: GameState, actor: ActorRef, target: ActorRef) -> None:
    if any(
        item.kind == "harpy_cannot_refuse_until_tag_resolved"
        and item.state == "pending"
        and ActorRef.model_validate_json(item.details["actor"]) == actor
        and ActorRef.model_validate_json(item.details["target_actor"]) == target
        for item in state.obligations
    ):
        raise ValueError("COMPULSION: embrace or reject this actual owed Tag before refusing her")
