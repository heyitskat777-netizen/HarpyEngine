"""M3 release gating and trusted local source-registry loading."""

import hashlib
import json
import os
from pathlib import Path

from sqlalchemy import Connection

from girlframe.engine.rules_registry import Registry
from girlframe.services.m2_game import GameService
from girlframe.services.onboarding import OnboardingStore, WorkflowError
from girlframe.services.read_only_bot import GuildViewer


def digest(registry: Registry) -> str:
    return hashlib.sha256(
        json.dumps(registry.model_dump(mode="json"), sort_keys=True).encode()
    ).hexdigest()


def load_registry() -> Registry:
    path = Path(os.environ.get("GIRLFRAME_RULES_REGISTRY", str(Path.cwd() / "rules/registry.json")))
    try:
        with path.open("rb") as source:
            data = source.read(4 * 1024 * 1024 + 1)
        if len(data) > 4 * 1024 * 1024:
            raise ValueError()
        return Registry.model_validate_json(data)
    except (OSError, ValueError):
        raise WorkflowError("M3 source registry is unavailable or invalid.") from None


class Access:
    def __init__(self, store: OnboardingStore, registry: Registry | None = None):
        self.store = store
        # A disabled M3 service does not need to load an external file at startup.
        self.registry = (
            registry
            if registry is not None
            else load_registry()
            if store.policy.m3_approval
            else None
        )

    def authorize(
        self, c: Connection, viewer: GuildViewer, subsystem: str, *, director_response: bool = False
    ) -> None:
        game = GameService(self.store)
        game.authorize(c, viewer, game=False)
        if not director_response and game.director_mode_pending(c, viewer.user_id):
            raise WorkflowError(
                "UNSUPPORTED_RULE: resolve the Director's Handler/Girl rules context first."
            )
        approval = self.store.policy.m3_approval
        if (
            approval is None
            or self.registry is None
            or approval.registry_sha256 != digest(self.registry)
            or subsystem not in approval.subsystems
        ):
            raise WorkflowError(
                "M3_REVIEW_PENDING: this subsystem needs a scoped release approval."
            )
        if approval.scope == "core_complete" and self.registry.coverage != "RULES_COMPLETE":
            raise WorkflowError(
                "RULES_SUBSET: incomplete coverage cannot claim a complete M3 release."
            )
        if self.store.policy.owner_m3_rulings is None:
            raise WorkflowError(
                "UNRESOLVED_RULING: record the approved M3 campaign rulings in trusted policy."
            )
        if director_response:
            game.gate()
        else:
            game.authorize(c, viewer)
