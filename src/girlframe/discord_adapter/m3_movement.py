"""Choose the actual controlled body and destination; no inferred movement or escape."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.services.m3_movement import MovementService
from girlframe.services.onboarding import WorkflowError


async def open_movement(interaction: discord.Interaction, service: MovementService) -> None:
    data = await asyncio.to_thread(
        service.menu, viewer_from_interaction(interaction), int(interaction.channel_id or 0)
    )
    if not data["actors"]:
        raise WorkflowError("Establish your actual role and physical position first")
    choices = {x["id"]: ActorRef.model_validate(x["ref"]) for x in data["actors"]}
    fields = [
        Field(
            "actor", "Actual controlled body", tuple((x["id"], x["label"]) for x in data["actors"])
        ),
        Field(
            "mode",
            "What actually moved?",
            (("body", "Body on foot"), ("frame", "Frame I actually pilot")),
        ),
        Field(
            "x",
            "Actual destination X",
            tuple((str(x), str(x)) for x in range(data["minimum"][0], data["maximum"][0] + 1)),
        ),
        Field(
            "y",
            "Actual destination Y",
            tuple((str(y), str(y)) for y in range(data["minimum"][1], data["maximum"][1] + 1)),
        ),
        Field("account", "Your actual movement or exact journey proposal", paragraph=True),
    ]
    if any(x["vatgrown"] for x in data["actors"]):
        fields.append(
            Field(
                "intent",
                "Travel or record an attempt first?",
                (
                    ("move", "Record actual movement"),
                    ("unchaperoned", "Record an unchaperoned Vatgrown attempt"),
                    *(
                        (("chaperoned", "Propose actual chaperoned joint travel"),)
                        if data["companions"]
                        else ()
                    ),
                ),
                minimum=0,
                required=False,
            )
        )
        if data["companions"]:
            fields.extend(
                [
                    Field(
                        "companion",
                        "Actual invited companion role (joint proposal)",
                        tuple((x["id"], x["label"]) for x in data["companions"]),
                        minimum=0,
                        required=False,
                    ),
                    Field(
                        "mutual",
                        "If also an Experiment: explicitly accompany them too?",
                        (
                            ("yes", "I authorize actual mutual accompaniment throughout this trip"),
                            ("no", "No mutual accompaniment authorization"),
                        ),
                        minimum=0,
                        required=False,
                    ),
                ]
            )

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        if values.get("intent") == ("chaperoned",):
            from girlframe.services.m3_vatgrown_travel import VatgrownTravelService

            if len(values.get("companion", ())) != 1:
                raise WorkflowError("Choose the actual invited companion for this joint proposal")
            companion = next(x for x in data["companions"] if x["id"] == values["companion"][0])
            result = await asyncio.to_thread(
                VatgrownTravelService(service.game).propose_chaperoned,
                viewer_from_interaction(current),
                str(current.id),
                data["channel"],
                data["revision"],
                choices[values["actor"][0]],
                ActorRef.model_validate(companion["ref"]),
                (int(values["x"][0]), int(values["y"][0])),
                frame=values["mode"] == ("frame",),
                account=values["account"],
                mutual=values.get("mutual") == ("yes",),
            )
            return (
                "Joint proposal saved; neither body moved. Both move when the actual "
                "companion accepts with their own movement account. You may cancel before "
                "acceptance from your private requests inbox. Reference `"
                + str(result["id"])
                + "`."
            )
        if values.get("intent") == ("unchaperoned",):
            from girlframe.services.m3_vatgrown_travel import VatgrownTravelService

            result = await asyncio.to_thread(
                VatgrownTravelService(service.game).attempt,
                viewer_from_interaction(current),
                str(current.id),
                data["channel"],
                data["revision"],
                choices[values["actor"][0]],
                (int(values["x"][0]), int(values["y"][0])),
                frame=values["mode"] == ("frame",),
                account=values["account"],
            )
            return (
                "Unchaperoned attempt saved; your position has not changed. "
                "Open your private requests inbox to continue. Reference `"
                + str(result["id"])
                + "`."
            )
        await asyncio.to_thread(
            service.move,
            viewer_from_interaction(current),
            str(current.id),
            data["revision"],
            data["channel"],
            choices[values["actor"][0]],
            (int(values["x"][0]), int(values["y"][0])),
            frame=values["mode"] == ("frame",),
            account=values["account"],
        )
        return "Actual movement saved. Your original body, Frame and source history are preserved."

    form = NativeForm(
        interaction.user.id,
        "Record actual movement",
        "Record movement permitted in the fiction. This does not resolve a barrier, "
        "source pin, custody or required escape. Joint travel is a proposal: both bodies "
        "move together when the named companion accepts; the owner may cancel before then.",
        fields,
        submit,
    )
    await reply(interaction, form.text(), form)
