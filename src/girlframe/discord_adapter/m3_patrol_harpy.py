"""Private actual patrol source, factual World introduction and once-only extra die."""

import asyncio
import json
from typing import Any
from uuid import uuid4

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field
from girlframe.discord_adapter.m3_memory_pages import MemoryForm, MemoryHistory
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_world_state import AdversaryPilot, Asset
from girlframe.services.m3_patrol_harpy import PatrolHarpyService
from girlframe.services.m3_world import WorldService


async def open_patrol_harpy(
    interaction: discord.Interaction, service: PatrolHarpyService, work: str
) -> None:
    data = await asyncio.to_thread(service.get, viewer_from_interaction(interaction), work)

    async def access(current: discord.Interaction) -> None:
        await asyncio.to_thread(service.get, viewer_from_interaction(current), work)

    sighting, encounter = data["sighting"], data["encounter"]
    lines = ["Actual Low Void patrol sighting: " + data["state"]]
    if encounter:
        lines.append("Actual patrol: " + encounter["account"])
    if sighting:
        lines.extend(
            (
                "Observed Harpy: " + encounter["harpy_body"]["name"],
                "Actual additional d6: " + str(sighting["face"]) + " — " + sighting["mood"],
                "This observation grants no attack, escape, healing or invented dialogue.",
            )
        )
    options = []
    if data["can_stage"] and data["observers"] and data["harpies"] and data["channels"]:
        options.append(("stage", "Record actual patrol and Harpy contact"))
    if data["can_stage"] and data.get("can_introduce") and data["cells"]:
        options.append(("introduce", "Introduce this source's actual World Harpy"))
    for actual in data.get("setups", ()):
        options.append(
            (
                "setup:" + ActorRef.model_validate(actual["ref"]).token,
                "Establish actual body: " + actual["label"],
            )
        )
    if data["can_roll"]:
        options.append(("roll", "Roll the actual additional d6 once"))
    if not options:
        history = MemoryHistory(interaction.user.id, "\n\n".join(lines), access)
        await reply(interaction, history.text(), history)
        return

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str | None:
        operation = values["operation"][0]
        if operation == "roll":
            result = await asyncio.to_thread(
                service.roll,
                viewer_from_interaction(current),
                str(current.id),
                work,
                data["revision"],
                data["game_revision"],
            )
            return (
                "Actual source sighting saved: "
                + str(result["mood"])
                + ". Reopen the private source."
            )
        if operation.startswith("setup:"):
            from girlframe.discord_adapter.m3_harpy_defeat import open_setup
            from girlframe.services.m3_harpy_defeat import HarpyDefeatService

            actual = next(
                ActorRef.model_validate(x["ref"])
                for x in data["setups"]
                if ActorRef.model_validate(x["ref"]).token == operation[6:]
            )
            await open_setup(current, HarpyDefeatService(service.store, game=service.game), actual)
        elif operation == "introduce":
            await _introduce(current, service, work)
        else:
            await _stage(current, service, work)
        return None

    form = MemoryForm(
        interaction.user.id,
        "Actual patrol Harpy",
        "\n\n".join(lines) + "\nThe original Handler records actual source facts; "
        "only the actual observer gains this sighting, without a global reveal.",
        [Field("operation", "Actual source control", tuple(options))],
        submit,
        authorize=access,
    )
    await reply(interaction, form.text(), form)


async def _stage(interaction: discord.Interaction, service: PatrolHarpyService, work: str) -> None:
    data = await asyncio.to_thread(service.get, viewer_from_interaction(interaction), work)

    async def access(current: discord.Interaction) -> None:
        await asyncio.to_thread(service.get, viewer_from_interaction(current), work)

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        observer = next(
            ActorRef.model_validate(x["ref"])
            for x in data["observers"]
            if ActorRef.model_validate(x["ref"]).token == values["observer"][0]
        )
        harpy = next(
            ActorRef.model_validate(x["ref"])
            for x in data["harpies"]
            if ActorRef.model_validate(x["ref"]).token == values["harpy"][0]
        )
        await asyncio.to_thread(
            service.stage,
            viewer_from_interaction(current),
            str(current.id),
            work,
            data["revision"],
            data["game_revision"],
            observer,
            harpy,
            int(values["channel"][0]),
            values["account"],
        )
        return "Actual patrol contact saved. Reopen for the separate genuine additional d6."

    form = MemoryForm(
        interaction.user.id,
        "Actual patrol contact",
        "Record the actual original Girl's patrol and genuine visual contact in her joined "
        "scene. Bodies must remain in their actual known positions; this does not move them.",
        [
            Field(
                "observer",
                "Actual original patrol Girl",
                tuple(
                    (ActorRef.model_validate(x["ref"]).token, x["label"]) for x in data["observers"]
                ),
            ),
            Field(
                "harpy",
                "Actual existing World Harpy",
                tuple(
                    (ActorRef.model_validate(x["ref"]).token, x["label"]) for x in data["harpies"]
                ),
            ),
            Field(
                "channel",
                "Actual source scene",
                tuple((x["id"], x["label"]) for x in data["channels"]),
            ),
            Field("account", "Actual patrol and visual contact", paragraph=True),
        ],
        submit,
        authorize=access,
    )
    await reply(interaction, form.text(), form)


async def _introduce(
    interaction: discord.Interaction, service: PatrolHarpyService, work: str
) -> None:
    data = await asyncio.to_thread(service.get, viewer_from_interaction(interaction), work)
    identity, girl_id, frame_id = (str(uuid4()) for _ in range(3))

    async def access(current: discord.Interaction) -> None:
        await asyncio.to_thread(service.get, viewer_from_interaction(current), work)

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        viewer = viewer_from_interaction(current)
        cell = json.loads(values["cell"][0])
        pilot = AdversaryPilot(
            id=identity,
            name=values["name"],
            kind="harpy",
            girl="HARPY",
            frame=values["frame"],
            controller=viewer.user_id,
            cell=(int(cell[0]), int(cell[1])),
            assets=(
                Asset(
                    id=girl_id,
                    name=values["girl_asset"],
                    description=values["girl_detail"],
                    family="girl",
                    void=values["girl_void"] == ("yes",),
                ),
                Asset(
                    id=frame_id,
                    name=values["frame_asset"],
                    description=values["frame_detail"],
                    family="frame",
                    void=values["frame_void"] == ("yes",),
                ),
            ),
        )
        await asyncio.to_thread(
            WorldService(service.strain.missions).introduce_patrol_harpy,
            viewer,
            str(current.id),
            work,
            data["revision"],
            data["game_revision"],
            pilot,
            values["account"],
        )
        return "The actual source Harpy is saved without public reveal. Reopen to bind the patrol."

    form = MemoryForm(
        interaction.user.id,
        "Actual source Harpy introduction",
        "As the original Handler, establish a genuinely present World Harpy and actual known "
        "hardware. These factual descriptions grant no PC sheet or borrowed rule/resources. "
        "Existing Harpy runtime/body setup remains required for later actual mechanical actions.",
        [
            Field("name", "Actual Harpy name"),
            Field("frame", "Actual current Frame description"),
            Field(
                "cell",
                "Actual known introduction cell",
                tuple((json.dumps(x), str(x)) for x in data["cells"]),
            ),
            Field("girl_asset", "Actual Girl-body component"),
            Field("girl_detail", "Actual body component detail", paragraph=True),
            Field("girl_void", "That actual component has Void", (("yes", "Yes"), ("no", "No"))),
            Field("frame_asset", "Actual Frame component"),
            Field("frame_detail", "Actual Frame component detail", paragraph=True),
            Field("frame_void", "That actual component has Void", (("yes", "Yes"), ("no", "No"))),
            Field("account", "Actual source introduction facts", paragraph=True),
        ],
        submit,
        authorize=access,
    )
    await reply(interaction, form.text(), form)
