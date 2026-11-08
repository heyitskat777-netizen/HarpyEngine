"""Private finite aftermath decisions, actual replacement and owner-attested transport."""

import asyncio
import json
from typing import Any
from uuid import uuid4

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.m3_world import START_CELLS, START_NAMES, TYPES, coordinates, squares
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_world_state import Asset, Board, CorePlan, Gorgon, Location
from girlframe.services.m3_quadrant_loss import LossService
from girlframe.services.onboarding import WorkflowError


async def open_loss(interaction: discord.Interaction, service: LossService, identity: str) -> None:
    data = await asyncio.to_thread(service.get, viewer_from_interaction(interaction), identity)
    value = data["episode"]
    phase = value["phase"]
    if phase == "complete":
        await reply(
            interaction,
            "This actual quadrant aftermath is complete. Its source history is retained.",
        )
        return
    if phase == "handler":
        if interaction.user.id != data["procedural_gm"]:
            await reply(
                interaction, "The actual replacement Handler is being created by its owner."
            )
            return
        from girlframe.discord_adapter.m3_handler_creation import open_handler
        from girlframe.services.m3_handler_creation import HandlerCreationService

        await open_handler(interaction, HandlerCreationService(service.store), source_work=identity)
        return
    fields = []
    title = "Actual quadrant aftermath"
    if phase == "employment":
        if interaction.user.id != value["judge"]:
            await reply(
                interaction,
                "The source adjudicator must record the actual Foundation employment decision.",
            )
            return
        fields = [
            Field(
                "decision",
                "Actual Foundation decision",
                (
                    ("retained", "Retain the Handler under review"),
                    ("fired", "Fire the Handler"),
                    ("imprisoned", "Imprison the Handler"),
                ),
            ),
            Field("account", "Record the actual institutional decision", paragraph=True),
        ]

        async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
            await asyncio.to_thread(
                service.employment,
                viewer_from_interaction(current),
                str(current.id),
                identity,
                data["revision"],
                data["game_revision"],
                values["decision"][0],
                values["account"],
            )
            return "Employment decision saved. Reopen the aftermath to continue."
    elif phase == "outcome":
        if interaction.user.id != value["judge"]:
            await reply(interaction, "The source adjudicator owns the actual Cadre outcome.")
            return
        fields = [
            Field(
                "decision",
                "Actual Cadre outcome",
                (
                    ("new_handler", "New Handler in the existing quadrant"),
                    ("reassigned", "New quadrant and new Handler"),
                    ("execution", "Sentence the original Cadre to execution"),
                ),
            ),
            Field(
                "agent",
                "Actual Foundation execution agent (only for execution)",
                tuple((x["token"], x["label"]) for x in data["agents"])
                or (("none", "No eligible actual agent"),),
                required=False,
            ),
            Field("account", "Actual institutional decision and circumstances", paragraph=True),
        ]

        async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
            token = next(iter(values.get("agent", ())), None)
            actor = next(
                (ActorRef.model_validate(x["ref"]) for x in data["agents"] if x["token"] == token),
                None,
            )
            await asyncio.to_thread(
                service.outcome,
                viewer_from_interaction(current),
                str(current.id),
                identity,
                data["revision"],
                data["game_revision"],
                values["decision"][0],
                values["account"],
                actor if values["decision"][0] == "execution" else None,
            )
            return (
                "Actual Cadre decision recorded; no new person, transport or death was fabricated."
            )
    elif phase == "execution":
        if interaction.user.id != data["executor_controller"]:
            await reply(
                interaction,
                "The named Foundation agent's controller must attest carrying out the sentence.",
            )
            return
        fields = [
            Field(
                "confirm",
                "Actual execution has been carried out",
                (("yes", "I attest the actual original Cadre's execution"),),
            ),
            Field("account", "What the actual Foundation agent did", paragraph=True),
        ]

        async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
            await asyncio.to_thread(
                service.execute,
                viewer_from_interaction(current),
                str(current.id),
                identity,
                data["revision"],
                data["game_revision"],
                values["account"],
            )
            return "The executed characters are archived. Their history is retained."
    elif phase == "transport" and data["new_board"] is None:
        if interaction.user.id != data["procedural_gm"]:
            await reply(
                interaction,
                "The real new quadrant must be set up before owners can record actual arrivals.",
            )
            return
        await open_new_quadrant(interaction, service, data)
        return
    elif phase == "transport":
        choices = tuple(
            (str(i), "Your original Girl" if x["kind"] == "pilot" else "Your new Handler")
            for i, x in enumerate(data["owner_refs"])
        )
        if not choices:
            await reply(
                interaction, "Other actual owners must record their original bodies' real arrivals."
            )
            return
        fields = [
            Field("actor", "Your actual arriving body", choices),
            Field("cell", "Actual body arrival square", squares(data["new_board"])),
            Field(
                "frame",
                "Did your own assigned Frame actually arrive?",
                (
                    ("no", "No: it remains outside this map"),
                    ("yes", "Yes: I attest its actual transport"),
                ),
            ),
            Field(
                "frame_cell",
                "Actual assigned Frame square (if it arrived)",
                squares(data["new_board"]),
                required=False,
            ),
            Field(
                "account", "Describe your actual body/Frame transport and arrival", paragraph=True
            ),
        ]

        async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
            has_frame = values["frame"][0] == "yes"
            frame = next(iter(values.get("frame_cell", ())), None)
            await asyncio.to_thread(
                service.arrive,
                viewer_from_interaction(current),
                str(current.id),
                identity,
                data["revision"],
                data["game_revision"],
                ActorRef.model_validate(data["owner_refs"][int(values["actor"][0])]),
                coordinates(values["cell"][0]),
                values["account"],
                frame_arrived=has_frame,
                frame_cell=coordinates(frame) if has_frame and frame else None,
            )
            return "Your arrival is saved. The map changes after every required owner attests."
    else:
        raise WorkflowError("Reopen the actual saved aftermath phase.")
    form = NativeForm(
        interaction.user.id,
        title,
        "Complete only the actual event owned by you; other participants act for themselves.",
        fields,
        submit,
    )
    await reply(interaction, form.text(), form)


async def open_new_quadrant(
    interaction: discord.Interaction, service: LossService, data: dict[str, Any]
) -> None:
    locations = tuple(str(uuid4()) for _ in range(8))
    secret_id = str(uuid4())
    asset_ids = (str(uuid4()), str(uuid4()))

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        names = tuple(x.strip() for x in values["names"].splitlines())
        asset_names = tuple(x.strip() for x in values["assets"].splitlines())
        if len(names) != 8 or len(asset_names) != 2 or not all((*names, *asset_names)):
            raise WorkflowError("Name eight actual locations and two secret Class 0 Assets.")
        places = tuple(
            Location(
                id=locations[i],
                name=name,
                cell=START_CELLS[i],
                kind="base" if i < 3 else "city" if i < 5 else "important",
            )
            for i, name in enumerate(names)
        )
        assets = tuple(
            Asset(id=asset_ids[i], family="gorgon", name=name, description=name)
            for i, name in enumerate(asset_names)
        )
        secret = Gorgon.model_validate_json(
            json.dumps(
                dict(
                    id=secret_id,
                    name=values["secret"],
                    gorgon_class="benevolent",
                    types=(values["type"][0],),
                    cell=places[0].cell,
                    assets=assets,
                    core_plan=CorePlan(assets=(asset_ids[0],), weakness=values["weakness"]),
                ),
                default=lambda x: x.model_dump(mode="json"),
            )
        )
        await asyncio.to_thread(
            service.new_quadrant,
            viewer_from_interaction(current),
            str(current.id),
            data["id"],
            data["revision"],
            data["game_revision"],
            values["name"],
            Board(minimum=(0, 0), maximum=(9, 9)),
            places,
            secret,
        )
        return "The new quadrant is prepared. Each owner must now record their arrival."

    form = NativeForm(
        interaction.user.id,
        "Prepare the real new quadrant",
        "The secret Class 0 remains private; no original body or Frame has moved yet.",
        [
            Field("name", "New quadrant name"),
            Field("names", "Three Bases, two Cities, three important locations", paragraph=True),
            Field("secret", "Secret Class 0 name"),
            Field("type", "Actual secret Type", TYPES),
            Field("assets", "Two actual Class 0 Assets, one per line", paragraph=True),
            Field("weakness", "Actual Core weakness", paragraph=True),
        ],
        submit,
        values=dict(names=START_NAMES),
    )
    await reply(interaction, form.text(), form)
