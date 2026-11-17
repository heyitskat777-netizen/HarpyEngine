"""Private, provider-neutral world proposals; no arbitrary effects or state patches."""

from typing import Annotated, Literal, Protocol

from pydantic import Field, JsonValue

from girlframe.ai.contracts import Contract
from girlframe.ai.director import DirectorContext
from girlframe.ai.knowledge import KnowledgeSource
from girlframe.engine.m3_world_development import DevelopmentDraft
from girlframe.engine.m3_world_state import Faction, Npc


class DevelopmentAction(Contract):
    kind: Literal["development"] = "development"
    development: DevelopmentDraft


class NpcAction(Contract):
    kind: Literal["introduce_npc"] = "introduce_npc"
    npc: Npc


class FactionAction(Contract):
    kind: Literal["introduce_faction"] = "introduce_faction"
    faction: Faction


WorldAction = Annotated[DevelopmentAction | NpcAction | FactionAction, Field(discriminator="kind")]


class WorldbuildingPacket(Contract):
    request_id: str
    scene_id: str
    source: KnowledgeSource
    context: DirectorContext
    canonical_state: dict[str, JsonValue]
    world_revision: int
    owner_id: str
    frontier: int
    native_guard: str
    revision: str
    instructions: str = (
        "Propose one grounded current-scene development, ordinary NPC or faction. "
        "Cite source and native, plus actual reference:<id> evidence used. New reports "
        "are testimony, not established truth. Preserve existing canon and explicit "
        "supersession history. Goals/complications express intent or unresolved hooks, "
        "never automatic player reactions, harm, custody, resource changes or time advance. "
        "NPC goals require actual controller authority. All additions require private GM "
        "semantic review and native owner confirmation. No character learns them until "
        "a separate exact, recipient-scoped disclosure."
    )


class WorldbuildingProposal(Contract):
    request_id: str
    action: WorldAction
    cited_evidence: tuple[str, ...] = Field(
        min_length=2,
        max_length=32,
        json_schema_extra={
            "uniqueItems": True,
            "allOf": [
                {"contains": {"const": "source"}},
                {"contains": {"const": "native"}},
            ],
        },
    )
    private_reasoning: str = Field(min_length=1, max_length=4000)


class WorldbuildingProvider(Protocol):
    def propose(self, packet: WorldbuildingPacket) -> WorldbuildingProposal: ...
