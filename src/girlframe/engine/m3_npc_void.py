"""The printed NPC Void Tag; callers retain actual source and choice authority."""

from girlframe.engine.m3_world_state import WorldTag

MANIFESTATIONS = ("brain", "bones", "flesh", "abstract")


def npc_void_tag(tag_id: str, manifestation: str, giver_entity: str) -> WorldTag:
    if manifestation not in MANIFESTATIONS:
        raise ValueError("The actual source Handler chooses a printed NPC manifestation")
    return WorldTag(
        id=tag_id,
        label="Void of the " + manifestation,
        giver_entity=giver_entity,
    )
