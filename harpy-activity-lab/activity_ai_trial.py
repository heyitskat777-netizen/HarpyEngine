"""Trusted host wiring for one supervised, authenticated Activity campaign."""

import json
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from os import environ
from threading import Lock
from typing import Literal
from uuid import UUID

import sqlalchemy as sa
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
from girlframe.database import tables
from girlframe.services.m2_game import GameService
from girlframe.services.onboarding import WorkflowError

DEFAULT_HANDLER_MODEL = "gpt-6.1-sol"
MODEL_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}")
MODEL_SELECTION = "activity.ai_models_saved"


def parse_models(values):
    if not isinstance(values, dict) or values.keys() != {"handler", "pilot", "director"}:
        raise ValueError("Provide the Handler, AI Pilot, and Director model fields.")
    if any(value is not None and not isinstance(value, str) for value in values.values()):
        raise ValueError("Use model IDs as text.")
    models = {role: (value or "").strip() or None for role, value in values.items()}
    if not models["handler"] or any(
        model and (model.startswith("sk-") or not MODEL_ID.fullmatch(model))
        for model in models.values()
    ):
        raise ValueError(
            "Enter a valid Handler model ID and optional Pilot and Director model IDs."
        )
    return models


class ConnectionCheck(Contract):
    status: Literal["ok"]


class ReviewedResponses(OpenAIResponses):
    def __init__(self, *, allowed, **options):
        super().__init__(**options)
        self._allowed = allowed

    def generate(self, instructions, packet, result_type):
        if not self._allowed():
            raise ModelUnavailable("AI assistance is off for this campaign.")
        return super().generate(instructions, packet, result_type)


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
    _clients: dict[str, OpenAIResponses] = field(
        default_factory=dict, init=False, repr=False, compare=False
    )
    _models: dict[str, str | None] = field(
        default_factory=dict, init=False, repr=False, compare=False
    )
    _checks: dict[str, str] = field(default_factory=dict, init=False, repr=False, compare=False)
    _check_keys: dict[str, tuple[str, str]] = field(
        default_factory=dict, init=False, repr=False, compare=False
    )
    _lock: Lock = field(default_factory=Lock, init=False, repr=False, compare=False)
    _allowed: Callable[[], bool] = field(
        default=lambda: False, init=False, repr=False, compare=False
    )

    def __post_init__(self) -> None:
        self._select_models(self.defaults())

    def _select_models(self, models):
        limits = ModelLimits(attempts=self.attempts, output_tokens=self.output_tokens)
        with self._lock:
            for model in models.values():
                if model and model not in self._clients:
                    self._clients[model] = ReviewedResponses(
                        model=model,
                        api_key=self.key,
                        limits=limits,
                        allowed=lambda: self._allowed(),
                    )
            self._models.update(models)
            return {role: self._clients.get(model) for role, model in models.items()}

    def defaults(self) -> dict[str, str | None]:
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
        models = parse_models(
            {
                "handler": env.get("GIRLFRAME_ACTIVITY_HANDLER_MODEL", "").strip()
                or DEFAULT_HANDLER_MODEL,
                "pilot": env.get("GIRLFRAME_ACTIVITY_PILOT_MODEL"),
                "director": env.get("GIRLFRAME_ACTIVITY_DIRECTOR_MODEL"),
            }
        )
        key = env.get("OPENAI_API_KEY", "").strip()
        if not key or (facilitator is not None and not 0 < facilitator < 2**64):
            raise ValueError("Supply a server API key and valid legacy facilitator ID, if used.")
        return cls(
            campaign,
            facilitator,
            models["handler"],
            key,
            attempts,
            models["pilot"],
            models["director"] or models["handler"],
            tokens,
        )

    def model_selection(self, connection):
        events = tables.events
        saved = connection.scalar(
            sa.select(events.c.payload_json)
            .where(
                events.c.campaign_id == self.campaign,
                events.c.kind == MODEL_SELECTION,
            )
            .order_by(events.c.seq.desc())
            .limit(1)
        )
        return json.loads(saved) if saved else {"revision": 0, "models": self.defaults()}

    def save_models(self, adapter, viewer, key, data):
        models = parse_models(data["models"])
        revision = data["revision"]
        if type(revision) is not int or revision < 0:
            raise ValueError("Use the saved model settings revision.")
        game = adapter.session.game
        observer = adapter.session.observer

        def authorize(connection):
            game.authorize(connection, viewer, game=False)
            if viewer.user_id != observer.facilitator(connection):
                raise WorkflowError("Model selection belongs to the approved facilitator.")

        def apply(connection):
            current = self.model_selection(connection)
            if revision != current["revision"]:
                raise WorkflowError("Model settings changed. Refresh AI setup and try again.")
            return {"revision": revision + 1, "models": models}

        game.store._write(
            viewer,
            key,
            MODEL_SELECTION,
            {"revision": revision, "models": models},
            apply,
            authorize=authorize,
        )

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
                    for role, model in self._models.items()
                }
            }

    def check(self, role: str, key: str) -> str:
        with self._lock:
            model = self._models.get(role)
            if model is None:
                raise ValueError("Choose a configured AI role.")
            client = self._clients[model]
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

    def adapter(
        self, game: GameService, *, opening_channel: int, setup=None, battlefield=None
    ) -> P2Scene:
        if game.store.campaign_id != self.campaign:
            raise ValueError("The Activity AI trial is configured for a different campaign.")
        with game.store.engine.connect() as connection:
            clients = self._select_models(self.model_selection(connection)["models"])
        director = clients["director"]
        adapter = P2Scene.reviewed_activity(
            game,
            facilitator_id=self.facilitator,
            opening_channel=opening_channel,
            handler_batch=ModelActivityBatch(clients["handler"]),
            pilot_batch=ModelActivityPilot(clients["pilot"]) if clients["pilot"] else None,
            planning_provider=ModelDirectorPlanning(director) if director else None,
            review_models=director,
        )
        if setup is not None:
            from ai_native_plays import ActivityNativePlays

            adapter.session.context.native_play_projection = ActivityNativePlays(setup, battlefield)
        object.__setattr__(self, "_allowed", adapter.ai_enabled)
        return adapter
