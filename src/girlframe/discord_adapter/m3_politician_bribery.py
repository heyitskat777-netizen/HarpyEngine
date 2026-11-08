"""Actual political contacts, owned assignments and source-performed String cash-outs."""

import asyncio
from typing import Any, Literal, cast

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.ledger import clean
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.m3_punishments import Picker
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine import m3_politician_bribery as rules
from girlframe.engine.m3_strain_effects import Choice
from girlframe.engine.m3_world_state import Npc
from girlframe.services.m3_politician_bribery import BriberyService
from girlframe.services.onboarding import WorkflowError


async def open_bribery(
    interaction: discord.Interaction, service: BriberyService, identity: str | None = None
) -> None:
    viewer = viewer_from_interaction(interaction)
    data = await asyncio.to_thread(service.menu, viewer, identity)
    if data["acquisition"] is None:
        if not data["awards"] or not data["cities"]:
            raise WorkflowError(
                "Use an actual held Award and existing Cities before naming politicians"
            )

        async def buy(current: discord.Interaction, values: dict[str, Any]) -> str:
            cities = {}
            for city in data["cities"]:
                duplicates = sum(
                    x["name"].casefold() == city["name"].casefold() for x in data["cities"]
                )
                label = (
                    city["name"]
                    if duplicates == 1
                    else city["name"] + " at " + str(tuple(city["cell"]))
                )
                cities[label.casefold()] = city
            politicians = []
            for index, line in enumerate(values["politicians"].splitlines()):
                parts = [x.strip() for x in line.split("|")]
                parts[0] = parts[0].casefold()
                if len(parts) != 4 or parts[0] not in cities:
                    raise WorkflowError(
                        "Use City name | person name | actual NPC role | actual known x,y"
                    )
                location = None
                if parts[3] != "unknown":
                    coordinates = parts[3].split(",")
                    if len(coordinates) != 2:
                        raise WorkflowError("Record the actual known x,y coordinate")
                    location = (int(coordinates[0].strip()), int(coordinates[1].strip()))
                if location is None:
                    raise WorkflowError(
                        "SOURCE_NPC_POSITION_REQUIRED: this NPC body needs an actual known "
                        "position before purchase; do not invent coordinates."
                    )
                politicians.append(
                    rules.Politician(
                        city=cities[parts[0]]["id"],
                        npc=Npc(
                            id="politician:" + str(current.id) + ":" + str(index),
                            name=parts[1],
                            jobs=(parts[2].casefold().replace(" ", "_"),),
                            detail="Actual named political officeholder in "
                            + cities[parts[0]]["name"],
                            controller=viewer.user_id,
                            cell=location,
                            revealed=True,
                            employment="foundation",
                        ),
                    )
                )
            result = await asyncio.to_thread(
                service.buy,
                viewer_from_interaction(current),
                str(current.id),
                values["award"][0],
                data["revision"],
                tuple(politicians),
                values["account"],
            )
            return (
                "Actual politicians named; Cadre assigns the six spheres and NPC Bonds. "
                "Reference: " + str(result["id"])
            )

        form = NativeForm(
            viewer.user_id,
            "Politician Bribery Fund — actual contacts",
            "Name at least six politicians, at least one per City. "
            "Lines: City name | person name | NPC role | actual known x,y. Cities: "
            + ", ".join(x["name"] for x in data["cities"]),
            [
                Field(
                    "award",
                    "Actual held advancement",
                    tuple((x["id"], x["label"]) for x in data["awards"]),
                ),
                Field(
                    "politicians", "Actual officeholders / Cities / existing jobs", paragraph=True
                ),
                Field("account", "Actual political contacts and acquisition", paragraph=True),
            ],
            buy,
            values={"award": (identity,)} if identity else None,
        )
        await reply(interaction, form.text(), form)
        return
    contacts = {x["id"]: x for x in data["politicians"]}
    options = [
        ("assign", "Assign a sphere / write your own NPC Bond"),
        ("aid", "Record actual performed sphere aid"),
    ]
    if data["owner"]:
        options.extend(
            (
                ("budget", "Spend 3 Strings — Budget to Low"),
                ("tag", "Spend 1 String — real NPC Tag"),
                ("cause", "Bind actual action to its pending consequence"),
            )
        )
        options.extend(
            ("benefit:" + x["id"], "Record actual NPC benefit: " + contacts[x["npc"]]["name"])
            for x in data["aid"]
            if not x["earned"]
        )
        for cause in data["causes"]:
            if not cause["complete"]:
                options.append(
                    (
                        ("finish:" if cause["reserved"] else "reserve:") + cause["id"],
                        "Apply actual scapegoat consequence"
                        if cause["reserved"]
                        else "Spend 1 String — politician takes this consequence",
                    )
                )
    lines = ["**Political contacts / actual source**"]
    lines.extend(
        clean(x["name"])
        + " — "
        + clean(x["city"])
        + (("; available Strings " + str(x["balance"])) if data["owner"] else "")
        for x in contacts.values()
    )
    lines.extend(
        "Saved cash-out: " + x["kind"] + "; actual source " + x["event"]
        for x in data.get("cashouts", [])
    )

    async def choose(current: discord.Interaction, mode: str) -> None:
        if mode == "assign":
            fields = [
                Field(
                    "npc",
                    "Actual unassigned politician",
                    tuple((x, clean(contacts[x]["name"])) for x in data["unassigned"]),
                ),
                Field(
                    "sphere",
                    "Sphere of influence",
                    tuple(zip(rules.SPHERES, rules.LABELS, strict=True)),
                ),
                Field("feelings", "Your own private feelings / Personal NPC Bond", paragraph=True),
            ]
        elif mode == "aid":
            fields = [
                Field(
                    "npc",
                    "Actual recipient politician",
                    tuple((x, clean(p["name"])) for x, p in contacts.items()),
                ),
                Field(
                    "scene",
                    "Actual performed scene",
                    tuple((x["id"], x["label"]) for x in data["scenes"]),
                ),
                Field("activity", "What you actually did in their assigned sphere", paragraph=True),
                Field("benefit", "Actual resulting NPC benefit", paragraph=True),
                Field("action", "Your completed action ID, if one exists", required=False),
            ]
        elif mode == "budget" or mode == "tag" or mode.startswith("reserve:"):
            fields = [
                Field(
                    "politician",
                    "Whose actual Strings?",
                    tuple(
                        (x, clean(p["name"]))
                        for x, p in contacts.items()
                        if p["balance"] and p["balance"] >= (3 if mode == "budget" else 1)
                    ),
                )
            ]
            if mode == "tag":
                fields.extend(
                    [
                        Field(
                            "target",
                            "Actual affected NPC",
                            tuple((x["id"], clean(x["name"])) for x in data["npcs"]),
                        ),
                        Field("label", "Actual new Tag"),
                    ]
                )
            if not mode.startswith("reserve:"):
                fields.append(Field("account", "Actual cash-out", paragraph=True))
        elif mode == "cause":
            fields = [
                Field("work", "Actual pending BudgetLow6.2 source work ID"),
                Field(
                    "original",
                    "Original affected NPC",
                    tuple((x["id"], clean(x["name"])) for x in data["npcs"]),
                ),
                Field("jobs", "Actual post-firing NPC jobs, comma separated"),
                Field("consequence", "Exact original pending consequence", paragraph=True),
                Field(
                    "kind",
                    "Actual cause source",
                    (
                        ("pilot_play", "Completed original Cadre Play"),
                        ("handler_play", "Completed original Handler Play"),
                    ),
                ),
                Field("cause", "Actual completed source ID"),
                Field("account", "Factual action → this particular consequence", paragraph=True),
            ]
        else:
            fields = (
                [Field("account", "Actual factual NPC benefit", paragraph=True)]
                if mode.startswith("benefit:")
                else [
                    Field(
                        "confirm",
                        "Apply actual reserved job loss",
                        (("actual", "Perform source effect and spend reserved String"),),
                    )
                ]
            )
        if any(x.options == () and x.key in ("npc", "politician", "scene") for x in fields):
            raise WorkflowError(
                "No actual eligible contact/source remains; reopen the saved controls"
            )

        async def submit(actual: discord.Interaction, values: dict[str, Any]) -> str:
            human = viewer_from_interaction(actual)
            key = str(actual.id)
            if mode == "assign":
                result = await asyncio.to_thread(
                    service.assign,
                    human,
                    key,
                    data["id"],
                    data["revision"],
                    values["npc"][0],
                    values["sphere"][0],
                    values["feelings"],
                )
            elif mode == "aid":
                result = await asyncio.to_thread(
                    service.record_aid,
                    human,
                    key,
                    data["id"],
                    data["revision"],
                    values["npc"][0],
                    int(values["scene"][0]),
                    values["activity"],
                    values["benefit"],
                    action=values.get("action") or None,
                )
            elif mode.startswith("benefit:"):
                result = await asyncio.to_thread(
                    service.confirm_aid, human, key, mode[8:], data["revision"], values["account"]
                )
            elif mode.startswith("reserve:"):
                result = await asyncio.to_thread(
                    service.reserve_scapegoat,
                    human,
                    key,
                    mode[8:],
                    data["revision"],
                    values["politician"][0],
                )
            elif mode.startswith("finish:"):
                result = await asyncio.to_thread(
                    service.finish_scapegoat, human, key, mode[7:], data["revision"]
                )
            elif mode == "cause":
                result = await asyncio.to_thread(
                    service.record_cause,
                    human,
                    key,
                    data["id"],
                    data["revision"],
                    values["work"],
                    Choice(
                        rule_id=rules.JOB_LOSS,
                        target=values["original"][0],
                        npc_jobs=tuple(x.strip() for x in values["jobs"].split(",")),
                        account=values["consequence"],
                    ),
                    values["kind"][0],
                    values["cause"],
                    values["account"],
                )
            else:
                result = await asyncio.to_thread(
                    service.cash,
                    human,
                    key,
                    data["id"],
                    data["revision"],
                    values["politician"][0],
                    cast(Literal["budget", "tag"], mode),
                    values["account"],
                    target=values.get("target", (None,))[0],
                    label=values.get("label"),
                )
            return (
                "Actual political source/effect saved. Continue real pending work "
                "in Requests. Reference: " + str(result["id"])
            )

        form = NativeForm(
            viewer.user_id,
            "Politician Bribery Fund",
            "Source facts, genuine aid and actual effects only. A factual "
            "benefit record is not generated consent or another person's reply.",
            fields,
            submit,
        )
        await reply(current, form.text(), form)

    await reply(
        interaction,
        "\n".join(lines)[:1900],
        Picker(viewer.user_id, "Political source / actual actions", tuple(options), choose),
    )
