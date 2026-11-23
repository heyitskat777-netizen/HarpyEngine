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
    contents = registry.model_dump(mode="json")
    contents["enabled_modules"] = sorted(registry.enabled_modules)
    checksum = hashlib.sha256(json.dumps(contents, sort_keys=True).encode()).hexdigest()
    # Exactly two descriptions changed to use the printed name. Preserve the
    # existing approval and recorded source proofs for that exact registry.
    if checksum == "a8d61d0c8a3169e4bf047ccd4681171bc7997262b04ff0b90df9bbb646922350":
        return "73c4e0c1f3a350fa715fc17d082e40f82f1de05cd520804dae260f542a2f9941"
    return checksum


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
        # Saved private records remain readable when a release file is unavailable.
        self._registry = registry

    @property
    def registry(self) -> Registry | None:
        if self._registry is None and self.store.policy.m3_approval is not None:
            self._registry = load_registry()
        return self._registry

    @registry.setter
    def registry(self, value: Registry | None) -> None:
        self._registry = value

    def activity_specialist_enabled(self, identity: str) -> bool:
        approval = self.store.policy.m3_approval
        if (
            approval is None
            or approval.scope != "rules_subset"
            or identity not in approval.activity_specialist_rules
            or "plays" not in approval.subsystems
            or self.store.policy.owner_m3_rulings is None
            or self.registry is None
            or approval.registry_sha256 != digest(self.registry)
        ):
            return False
        entry = self.registry.entry(identity)
        return (
            entry.module in self.registry.enabled_modules
            and entry.implementation != "unimplemented"
        )

    def require_specialist_rule(self, identity: str) -> None:
        if self.registry is None:
            raise WorkflowError("M3 source registry is unavailable or invalid.")
        if not self.activity_specialist_enabled(identity):
            self.registry.require_available(identity)

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
        registry = self.registry
        if (
            approval is None
            or registry is None
            or approval.registry_sha256 != digest(registry)
            or subsystem not in approval.subsystems
        ):
            raise WorkflowError(
                "M3_REVIEW_PENDING: this subsystem needs a scoped release approval."
            )
        if approval.scope == "core_complete" and registry.coverage != "RULES_COMPLETE":
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
