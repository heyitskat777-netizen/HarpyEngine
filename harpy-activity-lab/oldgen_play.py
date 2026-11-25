"""Adapters for HarpyEngine's native Old Dog, New Pups roll and owned answers."""

from dataclasses import asdict

from girlframe.discord_adapter.m2_forms import Field
from girlframe.discord_adapter.m2_ui import text
from girlframe.engine.m3_oldgen import ADVICE, PLAY
from girlframe.services.m3_oldgen import OldgenService, _access
from girlframe.services.onboarding import WorkflowError

OLDGEN_ADVICE = PLAY

OLDGEN_CHOICES = ("oldgen_listen", "oldgen_low_maxim", "oldgen_write_maxim")


def advice_targets(game, viewer, channel):
    try:
        menu = OldgenService(game).menu(viewer, channel)
        if not menu["can_advise"]:
            return [], "HarpyEngine has no available advice Play for this pilot here."
        with game.store.engine.connect() as c:
            _access(game, c, viewer, ADVICE)
    except (ValueError, WorkflowError) as error:
        return [], str(error)
    return [
        {"id": row["ref"]["entity"], "label": row["label"]}
        for row in menu["subjects"]
        if row["ref"]["entity"] != str(viewer.user_id)
    ], None


def advice_choice(decision):
    detail = decision["detail"]
    fields = [
        text(
            "text",
            "Your account of listening"
            if decision["kind"] == "oldgen_listen"
            else "Your original target-only maxim",
        )
    ]
    if detail["unmark"]:
        fields.append(
            Field(
                "denied",
                "Optional Identity or maxim to unmark",
                tuple(tuple(row) for row in detail["unmark"]),
                minimum=0,
                required=False,
            )
        )
    return {"fields": [asdict(spec) for spec in fields]}
