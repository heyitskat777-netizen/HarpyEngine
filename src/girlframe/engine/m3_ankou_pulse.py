"""Lossless original Amygdala Tag movement into the existing NPC representation."""

from girlframe.engine import m3_ankou as rules
from girlframe.engine.m2 import GameState, TagState
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_world_state import WorldTag


def world_tag(original: TagState) -> WorldTag:
    """Project mechanics only; the movement record retains all original provenance."""
    if original.gm_setter_appointment:
        giver = "gm:" + original.gm_setter_appointment
    elif original.giver_actor:
        giver = original.giver_actor.model_dump_json()
    elif original.giver_character:
        giver = ActorRef(
            kind="pilot", entity=str(original.giver), incarnation=original.giver_character
        ).model_dump_json()
    else:
        raise ValueError("Recover the original Tag setter before moving it to an NPC")
    return WorldTag(
        id=original.id,
        label=original.label,
        giver_entity=giver,
        marked=original.marked,
        trigger_scene=original.scene_used,
        rejection_pending=original.rejection_pending,
    )


def npc_move(
    before: GameState,
    after: GameState,
    recipient: ActorRef,
    tag: str,
    event: str,
) -> bool:
    """Recognize only an exact new movement, never infer a new Tag from holder diff."""
    moves = [
        x
        for x in rules.records(after, rules.TagUse)
        if x.kind == "pulse" and x.target == recipient and x.tag == tag and x.event == event
    ]
    if not moves or recipient.kind != "npc":
        return False
    if len(moves) != 1 or before.world is None or after.world is None:
        raise ValueError("Recover one actual original Amygdala NPC movement")
    move = moves[0]
    source = before.sheets.get(move.actor.entity) if move.actor.kind == "pilot" else None
    changed_source = after.sheets.get(move.actor.entity)
    old_npc = next((x for x in before.world.npcs if x.id == recipient.entity), None)
    npc = next((x for x in after.world.npcs if x.id == recipient.entity), None)
    if (
        source is None
        or source.character_id != move.actor.incarnation
        or changed_source is None
        or changed_source.character_id != move.actor.incarnation
        or old_npc is None
        or not old_npc.alive
        or old_npc.source_kind is not None
        or npc is None
        or not npc.alive
        or move.original_tag is None
        or move.original_tag.id != tag
        or move.original_tag not in source.tags
        or any(x.id == tag for x in changed_source.tags)
        or any(x.id == tag for x in old_npc.tags)
        or any(x.id == move.id for x in rules.records(before, rules.TagUse))
        or next((x for x in npc.tags if x.id == tag), None) != world_tag(move.original_tag)
    ):
        raise ValueError("Preserve the exact original Tag, setter, privacy and NPC movement")
    return True
