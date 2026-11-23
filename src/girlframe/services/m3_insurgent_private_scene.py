"""The Insurgent's actual choices after the original Girl reports no suspicion."""

from typing import Any

from girlframe.engine.m2 import GameState, TagState, shift_status
from girlframe.engine.m3_handler_private_scene import PrivateScene
from girlframe.services.m2_choices import ChoiceEngine
from girlframe.services.m2_game import GameService
from girlframe.services.onboarding import WorkflowError

EFFECTS = ("confess", "lower_status", "erase_tag")


def tags(state: GameState, value: PrivateScene) -> dict[str, tuple[int, TagState]]:
    handler, girl = int(value.handler.entity), int(value.girl.entity)
    return {
        f"{owner}:{tag.id}": (owner, tag)
        for owner, source in (
            (handler, state.handler_tags),
            (girl, state.sheets[value.girl.entity].tags),
        )
        for tag in source
        if not tag.rejection_pending and (owner == handler or handler in tag.observers)
    }


def apply(
    game: GameService,
    state: GameState,
    value: PrivateScene,
    effects: tuple[str, ...],
    confession: str,
    selected_tag: str,
) -> dict[str, Any]:
    if (
        not set(effects) <= set(EFFECTS)
        or len(effects) != len(set(effects))
        or ("confess" in effects) != bool(confession.strip())
        or ("erase_tag" in effects) != bool(selected_tag)
        or len(confession.strip()) > 1200
    ):
        raise WorkflowError("Choose the printed reactions and their actual source details")
    selected = tags(state, value).get(selected_tag) if selected_tag else None
    if selected_tag and selected is None:
        raise WorkflowError("Choose a current Tag known to the original Insurgent")
    girl = int(value.girl.entity)
    if "lower_status" in effects:
        shift_status(state, girl, -1)
        state.sheets[value.girl.entity].revision += 1
    removed = None
    if selected:
        owner, tag = selected
        removed = tag.id
        if owner == girl:
            sheet = state.sheets[value.girl.entity]
            sheet.tags = [x for x in sheet.tags if x.id != tag.id]
            sheet.revision += 1
        else:
            state.handler_tags = [x for x in state.handler_tags if x.id != tag.id]
        ChoiceEngine(game).tag_resolved(state, owner, tag.id)
    return dict(
        phase="complete",
        outcome="insurgent_resolved",
        effects=effects,
        account=confession.strip(),
        tag=removed,
    )
