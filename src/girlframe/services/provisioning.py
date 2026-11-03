"""Resumable Discord resource provisioning. Never holds a DB transaction over HTTP."""

import asyncio
from dataclasses import dataclass
from typing import Literal, Protocol

from girlframe.services.onboarding import OnboardingStore, WorkflowError
from girlframe.services.read_only_bot import GuildViewer


@dataclass(frozen=True)
class ResourceSpec:
    key: str
    name: str
    kind: Literal["category", "text", "message"]
    parent: str | None = None
    private: bool = False
    read_only: bool = False


TEMPLATE = (
    ResourceSpec("main", "HarpyEngine", "category"),
    ResourceSpec("welcome", "welcome", "text", "main", read_only=True),
    ResourceSpec("new_players", "new-players", "text", "main"),
    ResourceSpec("characters", "character-directory", "text", "main", read_only=True),
    ResourceSpec("missions", "mission-board", "text", "main", read_only=True),
    ResourceSpec("scenes", "scenes", "text", "main"),
    ResourceSpec("ledger", "rolls-and-ledger", "text", "main", read_only=True),
    ResourceSpec("staff", "HarpyEngine Staff", "category", private=True),
    ResourceSpec("review", "staff-review", "text", "staff", private=True),
    ResourceSpec("entry", "New player entry", "message", "new_players"),
)


class CreationRefused(WorkflowError):
    """Discord explicitly refused creation; known no-effect result can be retried."""


class ProvisioningGateway(Protocol):
    async def preflight(self) -> None: ...
    async def exists(self, identity: int, spec: ResourceSpec, parent: int | None) -> bool: ...
    async def create(self, spec: ResourceSpec, parent: int | None) -> int: ...


class Provisioner:
    def __init__(self, store: OnboardingStore):
        self.store = store
        self.lock = asyncio.Lock()

    async def apply(self, viewer: GuildViewer, plan: str, gateway: ProvisioningGateway) -> int:
        self.store.administrator(viewer)
        async with self.lock:
            await gateway.preflight()
            mapping: dict[str, int] = {}
            created = 0
            for spec in TEMPLATE:
                state, identity = await asyncio.to_thread(
                    self.store.claim_resource, viewer, plan, spec.key
                )
                parent = mapping[spec.parent] if spec.parent else None
                if state == "uncertain":
                    raise WorkflowError(
                        "An earlier Discord create has an unknown outcome. Stop for administrator "
                        "review; no duplicate will be created automatically."
                    )
                if state == "ready":
                    assert identity is not None
                    if not await gateway.exists(identity, spec, parent):
                        # Never silently replace a deleted resource or overwrite a moved one.
                        raise WorkflowError(
                            "A saved managed resource is missing. Administrator repair is needed; "
                            "unrelated channels were not changed."
                        )
                    mapping[spec.key] = identity
                    continue
                try:
                    identity = await gateway.create(spec, parent)
                except CreationRefused:
                    await asyncio.to_thread(
                        self.store.finish_resource, viewer, plan, spec.key, None
                    )
                    raise
                except Exception:
                    raise WorkflowError(
                        "Discord create outcome is unknown. Partial setup is saved; inspect it "
                        "before retrying. No automatic duplicate will be created."
                    ) from None
                await asyncio.to_thread(
                    self.store.finish_resource, viewer, plan, spec.key, identity
                )
                mapping[spec.key] = identity
                created += 1
            return created
