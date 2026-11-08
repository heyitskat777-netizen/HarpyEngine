"""Original AM voluntary occupancy; actual factual hardware, no circuit source."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine.m2 import AssetState
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_am_body import BodySpec
from girlframe.services.m3_am_jailbroken import JailbrokenService
from girlframe.services.onboarding import WorkflowError

YES = (("yes", "Yes, these are actual physical facts"), ("no", "Not confirmed"))


async def open_prepare(interaction: discord.Interaction, service: JailbrokenService) -> None:
    data = await asyncio.to_thread(service.view, viewer_from_interaction(interaction))

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        vessel = values["vessel"].strip()
        assets = []
        for index, line in enumerate(values["assets"].splitlines()):
            if not line.strip():
                continue
            parts = tuple(x.strip() for x in line.split("|"))
            if (
                len(parts) != 4
                or parts[2] not in ("intact", "damaged")
                or parts[3] not in ("clear", "void")
            ):
                raise WorkflowError(
                    "Each Asset: name | actual source | intact/damaged | clear/void"
                )
            assets.append(
                AssetState(
                    id=vessel + ":physical:" + str(index),
                    family="girl",
                    name=parts[0],
                    description=parts[1],
                    damaged=parts[2] == "damaged",
                    void=parts[3] == "void",
                )
            )
        spec = BodySpec.model_validate(
            dict(
                vessel=vessel,
                label=values["label"],
                source=values["source"],
                processing_confirmed=values["processing"] == ("yes",),
                unoccupied_confirmed=values["empty"] == ("yes",),
                medical=values["medical"][0],
                assets=tuple(assets),
                mind_assets=tuple(
                    data["classified"]
                    if data["classified"] is not None
                    else values.get("mind_assets", ())
                ),
                carried_items=tuple(values.get("carried_items", ())),
            )
        )
        await asyncio.to_thread(
            service.prepare,
            viewer_from_interaction(current),
            str(current.id),
            ActorRef.model_validate(data["actor"]),
            data["revision"],
            spec,
        )
        return (
            "Actual available hardware saved. "
            "Choose occupancy through your own Jailbroken controls."
        )

    fields = [
        Field("vessel", "Actual unique physical hardware identity"),
        Field("label", "Actual body label"),
        Field("source", "Actual hardware, processing and preparation source", paragraph=True),
        Field("processing", "Requisite processing power actually available", YES),
        Field("empty", "Actual body empty and available", YES),
        Field(
            "medical",
            "Actual physical condition",
            (("fit", "Fit"), ("unconscious_injured", "Unconscious / injured")),
        ),
        Field(
            "assets", "Asset per line: name | source | intact/damaged | clear/void", paragraph=True
        ),
    ]
    if data["classified"] is None and data["mind_assets"]:
        fields.append(
            Field(
                "mind_assets",
                "Actual existing software-linked Assets",
                tuple((x["id"], x["name"]) for x in data["mind_assets"]),
                0,
                len(data["mind_assets"]),
                required=False,
            )
        )
    if data.get("carried_items"):
        fields.append(
            Field(
                "carried_items",
                "Actual physical possessions prepared to accompany this body",
                tuple((x["id"], x["label"]) for x in data["carried_items"]),
                minimum=0,
                maximum=len(data["carried_items"]),
                required=False,
            )
        )
    form = NativeForm(
        interaction.user.id,
        "Actual empty processing-capable hardware",
        "Record actual supplied local puppet hardware and physical Assets. "
        "Classify existing software-linked "
        "Assets once; they carry their actual current condition. "
        "Your inherent ability supplies no free hardware.",
        fields,
        submit,
    )
    await reply(interaction, form.text(), form)


async def open_jailbroken(
    interaction: discord.Interaction, service: JailbrokenService, identity: str | None = None
) -> None:
    data = await asyncio.to_thread(service.view, viewer_from_interaction(interaction), identity)
    body = data["current"]
    physical = ", ".join(
        x["name"] + (" [damaged]" if x["damaged"] else "") + (" [Void]" if x["void"] else "")
        for x in body["assets"]
    )
    instructions = (
        f"Current vessel {body['vessel']}: {physical or 'no physical Assets'}; {body['medical']}. "
        "You control your voice, expressions and near-instant calculations. "
        + ("Your actual Limiter requires a smile. " if data["capabilities"]["must_smile"] else "")
        + "Same mind, marks, software, Bonds, memories, balances and current Frame. "
        "Choose actual available empty processing hardware; "
        "occupying a parked body is another use. "
        "Remote, Frame and other-body adapters remain unavailable here."
    )
    saved = []
    for parked in data["bodies"]:
        if parked["vessel"] == body["vessel"]:
            continue
        assets = ", ".join(
            x["name"] + (" [damaged]" if x["damaged"] else "") + (" [Void]" if x["void"] else "")
            for x in parked["assets"]
        )
        saved.append(
            f"Saved empty hardware {parked['label']} ({parked['vessel']}): "
            f"{assets or 'no physical Assets'}; {parked['medical']}."
        )
    if saved:
        instructions += "\n" + "\n".join(saved)
    options = (
        (("prepare", "Record actual available hardware"),)
        + tuple(("occupy:" + x["vessel"], "Occupy: " + x["label"][:70]) for x in data["available"])
        + (("spinal", "Review actual spinal connection / unplug"),)
        + (("route", "Keep actual powered spinal interface during occupancy"),)
    )

    async def choose(current: discord.Interaction, values: dict[str, Any]) -> str | None:
        selected = values["operation"][0]
        if selected == "prepare":
            await open_prepare(current, service)
            return None
        if selected == "route":
            from girlframe.discord_adapter.m3_am_neural_route import open_neural_route
            from girlframe.services.m3_am_neural_route import RouteService

            await open_neural_route(current, RouteService(service.game))
            return None
        if selected == "spinal":
            from girlframe.discord_adapter.m3_am_body import open_spinal_controls
            from girlframe.services.m3_am_body import BodyService

            await open_spinal_controls(
                current, BodyService(service.game), ActorRef.model_validate(data["actor"])
            )
            return None
        result = await asyncio.to_thread(
            service.occupy,
            viewer_from_interaction(current),
            str(current.id),
            ActorRef.model_validate(data["actor"]),
            data["revision"],
            selected.removeprefix("occupy:"),
            carried_items=tuple(values.get("carried_items", ())),
            carry_account=values.get("carry_account") or None,
        )
        return (
            "Same AM now occupies actual vessel "
            + str(result["vessel"])
            + ". Previous hardware remains empty with its actual condition."
        )

    fields = [Field("operation", "Your voluntary use or actual preparation", options)]
    if data.get("carried_items"):
        fields += [
            Field(
                "carried_items",
                "Actual possessions physically conveyed to the selected body",
                tuple((x["id"], x["label"]) for x in data["carried_items"]),
                minimum=0,
                maximum=len(data["carried_items"]),
                required=False,
            ),
            Field(
                "carry_account",
                "How these actual possessions were physically conveyed",
                paragraph=True,
                required=False,
            ),
        ]
    form = NativeForm(
        interaction.user.id,
        "Jailbroken: your actual body occupancy",
        instructions,
        fields,
        choose,
    )
    await reply(interaction, form.text(), form)
