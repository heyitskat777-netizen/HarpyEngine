"""Original Princess appearance choices and actual Handler risk controls."""

import asyncio
from typing import Any
from uuid import uuid4

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_world_state import Npc
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_show_dog import ShowDogService
from girlframe.services.m3_world import WorldService


async def open_message(
    interaction: discord.Interaction, service: ShowDogService, identity: str
) -> None:
    data = await asyncio.to_thread(
        service.view_message, viewer_from_interaction(interaction), identity
    )
    await reply(
        interaction,
        "Addressed Show Dog message from "
        + data["sender"]
        + " to "
        + data["recipient"]
        + ": "
        + data["text"],
    )


async def open_interest(
    interaction: discord.Interaction, service: ShowDogService, identity: str
) -> None:
    data = await asyncio.to_thread(
        service.view_interest, viewer_from_interaction(interaction), identity
    )
    await reply(
        interaction,
        "Your actual NPC's appearance interest in "
        + data["princess"]
        + ": "
        + data["desire"]
        + ". Actual appearance: "
        + data["appearance"],
    )


async def open_show_dog(
    interaction: discord.Interaction, service: ShowDogService, identity: str | None = None
) -> None:
    viewer = viewer_from_interaction(interaction)
    if identity is None:
        data = await asyncio.to_thread(service.menu, viewer)
        if not data["tasks"]:
            await reply(interaction, "No genuine original Show Dog work or history is available.")
            return

        async def choose_task(current: discord.Interaction, values: dict[str, Any]) -> str | None:
            await open_show_dog(current, service, values["work"][0])
            return None

        form = NativeForm(
            viewer.user_id,
            "Show Dog",
            "Your actual original Go-OffDuty appearance choices.",
            [
                Field(
                    "work",
                    "Your original source",
                    tuple((x["id"], x["label"]) for x in data["tasks"]),
                )
            ],
            choose_task,
        )
        await reply(interaction, form.text(), form)
        return
    data = await asyncio.to_thread(service.menu, viewer, identity)
    options: list[tuple[str, str]] = []
    if data["can_choose"]:
        if data["first"] is None:
            options.extend(
                (
                    ("trend", "Start a trend or controversy: actual NPC Tag"),
                    ("public", "Put someone in the public eye: actual Tag"),
                    ("message", "Send an actual addressed message"),
                    ("quiet", "Smile, obey and take no risks"),
                )
            )
        if not data["second"]:
            options.append(("second", "Choose actual witnessed NPC interest and gain a Bond"))
            if data["locations"]:
                options.append(("create", "Introduce an actual new NPC first"))
    if data["can_risk"]:
        options.append(("risk", "Adjudicate actual performed appearance risk"))
    if not options:
        await reply(
            interaction,
            "Your original Show Dog: "
            + ("complete" if data["complete"] else "waiting for actual remaining work")
            + ". First choice: "
            + str(data["first"])
            + ". Second choice: "
            + ("saved" if data["second"] else "pending")
            + ".",
        )
        return

    async def choose(current: discord.Interaction, values: dict[str, Any]) -> str | None:
        selected = values["action"][0]
        if selected == "create":

            async def create(response: discord.Interaction, answer: dict[str, Any]) -> str:
                location = next(x for x in data["locations"] if x["id"] == answer["location"][0])
                npc = Npc(
                    id=str(uuid4()),
                    name=answer["name"],
                    jobs=("civilian",),
                    detail=answer["detail"],
                    controller=response.user.id,
                    cell=(int(location["cell"][0]), int(location["cell"][1])),
                )
                await asyncio.to_thread(
                    WorldService(MissionService(service.store)).npc,
                    viewer_from_interaction(response),
                    str(response.id),
                    data["game_revision"],
                    npc,
                    show_dog=identity,
                )
                return (
                    "Actual NPC introduced under your control. "
                    "Reopen Show Dog to choose the witnessed interest."
                )

            form = NativeForm(
                current.user.id,
                "Actual new NPC",
                "Use the existing world introduction. This records no NPC dialogue or consent.",
                [
                    Field("name", "Actual NPC name"),
                    Field("detail", "Actual identifying detail", paragraph=True),
                    Field(
                        "location",
                        "Actual present base or city",
                        tuple((x["id"], x["name"]) for x in data["locations"]),
                    ),
                ],
                create,
            )
        elif selected == "risk":

            async def risk(response: discord.Interaction, answer: dict[str, Any]) -> str:
                result = await asyncio.to_thread(
                    service.risk,
                    viewer_from_interaction(response),
                    str(response.id),
                    identity,
                    data["revision"],
                    data["game_revision"],
                    answer["punish"][0] == "yes",
                    answer["account"],
                )
                return "Actual risk adjudication saved." + (
                    " Complete the genuine Punishment through its existing controls."
                    if result["punishment"]
                    else ""
                )

            form = NativeForm(
                current.user.id,
                "Actual original Handler risk",
                "Performed choice: " + str(data["first"]) + ". Source account: " + data["account"],
                [
                    Field(
                        "punish",
                        "Your actual risk decision",
                        (("no", "No Punishment arises"), ("yes", "Inflict an actual Punishment")),
                    ),
                    Field("account", "Actual original Handler adjudication", paragraph=True),
                ],
                risk,
            )
        elif selected == "second":

            async def second(response: discord.Interaction, answer: dict[str, Any]) -> str:
                npc = ActorRef.model_validate(
                    next(
                        x["ref"]
                        for x in data["npcs"]
                        if ActorRef.model_validate(x["ref"]).token == answer["npc"][0]
                    )
                )
                await asyncio.to_thread(
                    service.second,
                    viewer_from_interaction(response),
                    str(response.id),
                    identity,
                    data["revision"],
                    data["game_revision"],
                    npc,
                    answer["desire"][0],
                    answer["account"],
                )
                return "Actual witnessed NPC interest and gained Bond saved."

            if not data["npcs"]:
                await reply(
                    current, "Introduce a real NPC first, then reopen this original source."
                )
                return None
            form = NativeForm(
                current.user.id,
                "Your second Show Dog choice",
                "Choose the actual NPC who saw your appearance. You author the printed interest; "
                "this creates no NPC dialogue or consent.",
                [
                    Field(
                        "npc",
                        "Actual known existing NPC",
                        tuple(
                            (ActorRef.model_validate(x["ref"]).token, x["label"])
                            for x in data["npcs"]
                        ),
                    ),
                    Field(
                        "desire",
                        "Actual printed NPC motivation",
                        (
                            ("sex", "Wants intimacy with you"),
                            ("own", "Wants to own you"),
                            ("kill", "Wants to kill you"),
                            ("emulate", "Wants to be you"),
                        ),
                    ),
                    Field("account", "Actual seen-appearance facts", paragraph=True),
                ],
                second,
            )
        else:
            targets = data["npcs"] if selected == "trend" else data["people"]
            fields = [
                Field("account", "Actual performed choice; visible to risk Handler", paragraph=True)
            ]
            if selected != "quiet":
                if not targets:
                    await reply(
                        current, "Choose a real known person or introduce an actual NPC first."
                    )
                    return None
                fields.insert(
                    0,
                    Field(
                        "target",
                        "Actual source target",
                        tuple(
                            (ActorRef.model_validate(x["ref"]).token, x["label"]) for x in targets
                        ),
                    ),
                )
            if selected in ("trend", "public"):
                fields.append(Field("tag", "Actual Tag label"))
            elif selected == "message":
                fields.append(Field("message", "Private addressed message text", paragraph=True))

            async def first(response: discord.Interaction, answer: dict[str, Any]) -> str:
                target = (
                    ActorRef.model_validate(
                        next(
                            x["ref"]
                            for x in targets
                            if ActorRef.model_validate(x["ref"]).token == answer["target"][0]
                        )
                    )
                    if selected != "quiet"
                    else None
                )
                await asyncio.to_thread(
                    service.first,
                    viewer_from_interaction(response),
                    str(response.id),
                    identity,
                    data["revision"],
                    data["game_revision"],
                    selected,
                    target=target,
                    tag=answer.get("tag", ""),
                    message=answer.get("message", ""),
                    account=answer["account"],
                )
                return (
                    "Your actual first Show Dog choice is saved. "
                    "The independent second choice remains required."
                )

            form = NativeForm(
                current.user.id,
                "Your first Show Dog choice",
                "Risky choices receive original Handler factual adjudication "
                "and any real selected Punishment.",
                fields,
                first,
            )
        await reply(current, form.text(), form)
        return None

    form = NativeForm(
        viewer.user_id,
        "Show Dog",
        "Your exact original source has two independent choices. OOC pause remains available.",
        [Field("action", "Your actual source control", tuple(options))],
        choose,
    )
    await reply(interaction, form.text(), form)
