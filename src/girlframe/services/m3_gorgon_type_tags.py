"""Apply a direct Gorgon type Tag with the original source cast and physical facts."""

import json
from typing import TYPE_CHECKING, Any

from sqlalchemy import Connection

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_bonds import depth, set_depth
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_gorgon_play_state import Declaration
from girlframe.engine.m3_gorgon_type_tags import LABELS, TYPES, present
from girlframe.engine.m3_world import update
from girlframe.engine.m3_world_state import WorldTag
from girlframe.services.m2_choices import ChoiceEngine
from girlframe.services.m3_actors import profiles
from girlframe.services.onboarding import WorkflowError

if TYPE_CHECKING:
    from girlframe.services.m2_game import GameService

NPC_PREFIX = "gorgon-type-tag:"


def apply(game: "GameService", c: Connection, state: GameState, action: dict[str, Any]) -> None:
    meta = action["data"]["gorgon_play"]
    intent = Declaration.model_validate_json(json.dumps(meta["declaration"]))
    if (
        intent.kind not in ("incubus_inflict", "mother_mutation", "doppleganger_bond")
        or intent.tag is None
        or intent.target is None
        or state.world is None
    ):
        raise WorkflowError("Recover the actual Gorgon Tag and original target")
    bound = profiles(c, game.store.campaign_id)
    actor = resolve(state, intent.actor, bound, require_current_profile=False)
    target = resolve(state, intent.target, bound, require_current_profile=False)
    source = next((x for x in state.world.gorgons if x.id == actor.ref.entity), None)
    if (
        source is None
        or TYPES[intent.kind] not in source.types
        or not present(intent.kind, actor, target)
        or intent.kind == "doppleganger_bond"
        and not source.revealed
    ):
        raise WorkflowError("Recover the living original Gorgon and body in actual local reach")
    label = (
        intent.tag.strip()
        if intent.kind == "doppleganger_bond"
        else dict(LABELS[intent.kind])[intent.tag]
    )
    if target.ref.kind == "pilot":
        observers = tuple(dict.fromkeys((target.controller, actor.controller)))
        tag = ChoiceEngine(game).add_tag(
            state, {"data": {"participants": observers}}, target.controller, actor.controller, label
        )
        tag.giver_actor = actor.ref
        identity = tag.id
    else:
        identity = NPC_PREFIX + action["id"]
        world_tag = WorldTag(id=identity, label=label, giver_entity=actor.ref.model_dump_json())
        state.world = update(
            state.world,
            npcs=tuple(
                npc.model_copy(update=dict(tags=(*npc.tags, world_tag)))
                if npc.id == target.ref.entity
                else npc
                for npc in state.world.npcs
            ),
        )
    action["data"]["result"].update(tag=identity, tag_label=label)
    if intent.kind == "doppleganger_bond":
        old = depth(state, actor.ref, target.ref)
        if old == 0:
            event = action["data"]["response_event"]
            changed = set_depth(state, actor.ref, target.ref, 1, event)
            state.actor_bonds, state.bonds, state.world = (
                changed.actor_bonds,
                changed.bonds,
                changed.world,
            )
        action["data"]["result"]["bond"] = max(1, old)
