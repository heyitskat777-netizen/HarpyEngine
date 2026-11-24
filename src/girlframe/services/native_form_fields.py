"""Fields shared by the native Discord and Activity forms."""

from collections.abc import Iterable
from dataclasses import asdict, dataclass
from typing import Any

from girlframe.services.onboarding import WorkflowError


@dataclass(frozen=True)
class Field:
    key: str
    label: str
    options: tuple[tuple[str, str], ...] = ()
    minimum: int = 1
    maximum: int = 1
    paragraph: bool = False
    required: bool = True


def form_fields(fields: Iterable[Field]) -> list[dict[str, Any]]:
    return [
        asdict(field) | {"options": [list(option) for option in field.options]} for field in fields
    ]


def selected_fields(fields: list[Field], submitted: dict[str, Any]) -> dict[str, Any]:
    """Recover the original native form values from an owner's Activity submission."""
    picked: dict[str, Any] = {}
    if submitted.keys() - {field.key for field in fields}:
        raise WorkflowError("INITIATIVE_PLAY_CHOICES: use the current original Play form.")
    for field in fields:
        value = submitted.get(field.key)
        if value is None and not field.required:
            continue
        if field.options:
            values = [value] if isinstance(value, str) else value
            allowed = dict(field.options)
            if (
                not isinstance(values, list)
                or not field.minimum <= len(values) <= field.maximum
                or any(not isinstance(token, str) or token not in allowed for token in values)
                or len(values) != len(set(values))
            ):
                raise WorkflowError("INITIATIVE_PLAY_CHOICES: confirm listed original options.")
            picked[field.key] = tuple(values)
        else:
            if not isinstance(value, str) or not value.strip() or len(value) > 1200:
                raise WorkflowError("INITIATIVE_PLAY_CHOICES: fill out the bounded source account.")
            picked[field.key] = value.strip()
    return picked
