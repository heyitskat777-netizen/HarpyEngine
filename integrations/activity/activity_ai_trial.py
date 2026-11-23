"""Trusted host wiring for one supervised, authenticated Activity campaign."""

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from os import environ
from threading import Lock
from typing import Literal
from uuid import UUID

from p2_scene import P2Scene

from girlframe.ai.contracts import Contract
from girlframe.ai.model_adapters import (
    ModelActivityBatch,
    ModelActivityPilot,
    ModelDirectorPlanning,
)
from girlframe.ai.model_transport import (
    ModelBudgetExhausted,
    ModelLimits,
    ModelUnavailable,
    OpenAIResponses,
)
from girlframe.services.m2_game import GameService


class ConnectionCheck(Contract):
    status: Literal["ok"]


@dataclass(frozen=True)
class ActivityAITrial:
    campaign: str
    facilitator: int | None
    handler_model: str
    key: str = field(repr=False)
    attempts: int = 30
    pilot_model: str | None = None
    director_model: str | None = None
    output_tokens: int = 700
    _clients: dict[str, OpenAIResponses] = field(init=False, repr=False, compare=False)
    _checks: dict[str, str] = field(default_factory=dict, init=False, repr=False, compare=False)
    _check_keys: dict[str, tuple[str, str]] = field(
        default_factory=dict, init=False, repr=False, compare=False
    )
    _lock: Lock = field(default_factory=Lock, init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        limits = ModelLimits(attempts=self.attempts, output_tokens=self.output_tokens)
        clients = {
            model: OpenAIResponses(model=model, api_key=self.key, limits=limits)
            for model in {self.handler_model, self.pilot_model, self.director_model}
            if model
        }
        object.__setattr__(self, "_clients", clients)

    def _roles(self) -> dict[str, str | None]:
        return {
            "handler": self.handler_model,
            "pilot": self.pilot_model,
            "director": self.director_model,
        }

    @classmethod
    def from_environment(cls, env: Mapping[str, str] = environ) -> "ActivityAITrial | None":
        nominated = env.get("GIRLFRAME_ACTIVITY_AI_CAMPAIGN", "").strip()
        if not nominated:
            return None
        try:
            legacy_facilitator = env.get("GIRLFRAME_ACTIVITY_AI_FACILITATOR", "").strip()
            facilitator = int(legacy_facilitator) if legacy_facilitator else None
            campaign = str(UUID(nominated))
            attempts = int(env.get("GIRLFRAME_ACTIVITY_AI_ATTEMPTS", "30"))
            tokens = int(env.get("GIRLFRAME_ACTIVITY_AI_OUTPUT_TOKENS", "700"))
            ModelLimits(attempts=attempts, output_tokens=tokens)
        except ValueError:
            raise ValueError("Invalid Activity AI campaign, facilitator or model limits.") from None
        handler = env.get("GIRLFRAME_ACTIVITY_HANDLER_MODEL", "").strip()
        pilot = env.get("GIRLFRAME_ACTIVITY_PILOT_MODEL", "").strip() or None
        director = env.get("GIRLFRAME_ACTIVITY_DIRECTOR_MODEL", "").strip() or None
        key = env.get("OPENAI_API_KEY", "").strip()
        if not (handler and key) or (facilitator is not None and not 0 < facilitator < 2**64):
            raise ValueError(
                "Supply the Handler model, server API key and any legacy facilitator ID."
            )
        if any(
            not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", model)
            for model in (handler, pilot, director)
            if model
        ):
            raise ValueError("Supply valid API model IDs for the configured roles.")
        return cls(campaign, facilitator, handler, key, attempts, pilot, director, tokens)

    def status(self) -> dict[str, object]:
        with self._lock:
            return {
                "roles": {
                    role: {
                        "model": model,
                        "connection": self._checks.get(model, "unchecked"),
                        **self._clients[model].status(),
                    }
                    if model
                    else None
                    for role, model in self._roles().items()
                }
            }

    def check(self, role: str, key: str) -> str:
        model = self._roles().get(role)
        if model is None:
            raise ValueError("Choose a configured AI role.")
        client = self._clients[model]
        with self._lock:
            if prior := self._check_keys.get(key):
                if prior[0] != model:
                    raise ValueError("Use a new request for a different model.")
                return prior[1]
            if self._checks.get(model) == "checking":
                return "checking"
            if client.status()["attempts"] == self.attempts:
                return "attempt_limit"
            self._checks[model] = "checking"
            self._check_keys[key] = (model, "checking")

        outcome = "unavailable"
        try:
            client.generate(
                'Return the JSON object {"status":"ok"} for a synthetic connection check.',
                {},
                ConnectionCheck,
            )
        except ModelBudgetExhausted:
            outcome = "attempt_limit"
        except ModelUnavailable as error:
            outcome = error.status
        else:
            outcome = "ok"
        finally:
            with self._lock:
                self._checks[model] = outcome
                self._check_keys[key] = (model, outcome)
        return outcome

    def adapter(self, game: GameService, *, opening_channel: int) -> P2Scene:
        if game.store.campaign_id != self.campaign:
            raise ValueError("The Activity AI trial is configured for a different campaign.")
        director = self._clients[self.director_model] if self.director_model else None
        return P2Scene.reviewed_activity(
            game,
            facilitator_id=self.facilitator,
            opening_channel=opening_channel,
            handler_batch=ModelActivityBatch(self._clients[self.handler_model]),
            pilot_batch=ModelActivityPilot(self._clients[self.pilot_model])
            if self.pilot_model
            else None,
            planning_provider=ModelDirectorPlanning(director) if director else None,
            review_models=director,
        )
