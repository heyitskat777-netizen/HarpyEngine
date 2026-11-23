"""Project approved mission terms to the actual bound scene and original cast."""

from typing import TYPE_CHECKING, Literal

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.ai.director import KnowledgeReference
from girlframe.database import tables as t
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_missions import Mission
from girlframe.services.canon_briefings import CanonBriefings
from girlframe.services.mission_timing_history import active
from girlframe.services.onboarding import WorkflowError

if TYPE_CHECKING:
    from girlframe.services.director_context import DirectorContextService


def mission_references(
    context: "DirectorContextService", c: Connection, scene: str, *, allow_closed: bool
) -> tuple[KnowledgeReference, ...]:
    from girlframe.services.director_knowledge import DirectorKnowledgeService

    campaign = context.store.campaign_id
    table = t.m3["m3_missions"]
    clock = active(c, campaign)
    binding = sa.func.json_extract(table.c.body_json, "$.intro_scene") == scene
    if clock is not None and clock.scene == scene:
        binding = sa.or_(binding, table.c.id == clock.mission)
    raw = c.scalars(
        sa.select(table.c.body_json)
        .where(
            table.c.campaign_id == campaign,
            table.c.phase.in_(("active", "ending", "awaiting_consequences", "complete")),
            sa.func.json_extract(table.c.body_json, "$.briefing_terms").is_not(None),
            binding,
        )
        .limit(2)
    ).all()
    if len(raw) != 1:
        return ()
    mission = Mission.model_validate_json(raw[0])
    if mission.briefing_terms is None or mission.briefing_handler is None:
        return ()
    try:
        if mission.briefing_facts:
            briefings = CanonBriefings(context.store)
            facts = briefings._known(c, mission.handler, mission.briefing_facts)
            briefings.require_model_sources(c, facts)
        row = context.observations._scene(c, scene, allow_closed=allow_closed)
        present = DirectorKnowledgeService(context)._actors(c, row)
    except WorkflowError:
        return ()
    cast = {
        ActorRef(kind="pilot", entity=owner, incarnation=character)
        for owner, character in mission.character_ids.items()
    }
    cast.add(mission.briefing_handler)
    audience = tuple(sorted(actor.token for actor in present if actor in cast))
    if not audience:
        return ()
    terms: tuple[tuple[Literal["objective", "scope", "completion"], str], ...] = (
        ("objective", mission.objective),
        ("scope", mission.briefing_terms.scope),
        ("completion", mission.briefing_terms.completion),
    )
    return tuple(
        KnowledgeReference(
            id=f"mission:{mission.id}:{scene}:{topic}",
            source_id=f"mission:{mission.id}:{scene}:{topic}",
            source_revision=1,
            order=-3 + order,
            known_by=audience,
            topic=topic,
            classification="established_world",
            text=text,
        )
        for order, (topic, text) in enumerate(terms)
    )
