"""Public process lifecycle only; never expose campaign/private state in presence."""

from typing import Literal

import discord

from girlframe import __version__

Phase = Literal["starting", "running", "reconnecting", "restarting", "stopping"]


def activity(phase: Phase) -> discord.CustomActivity:
    labels = {
        "starting": "Starting",
        "running": "Running",
        "reconnecting": "Reconnecting",
        "restarting": "Restarting",
        "stopping": "Stopping",
    }
    return discord.CustomActivity(name=f"{labels[phase]} v{__version__}")


def status(phase: Phase) -> discord.Status:
    if phase == "running":
        return discord.Status.online
    return discord.Status.dnd if phase in ("restarting", "stopping") else discord.Status.idle
