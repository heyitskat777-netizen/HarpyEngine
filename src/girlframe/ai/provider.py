"""Shared transport metadata and safe provider failures."""

from typing import Literal

from pydantic import Field

from girlframe.engine.m2 import Model

MAX_OUTPUT_TOKENS = 800
Failure = Literal["provider_unavailable", "invalid_proposal"]


class ProviderUsage(Model):
    trace_id: str = Field(pattern=r"^[A-Za-z0-9_.:-]{1,128}$")
    model: str = Field(pattern=r"^[A-Za-z0-9_.:-]{1,128}$")
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0, le=MAX_OUTPUT_TOKENS)


class ProviderError(RuntimeError):
    def __init__(self, code: Failure) -> None:
        super().__init__(code)
        self.code = code
