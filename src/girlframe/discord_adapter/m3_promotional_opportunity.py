"""Owned exact map selections, actual authored contents and source-proved takeover."""

import asyncio
import json
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.ledger import clean
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine import m3_promotional_opportunity as rules
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_harpy_defeat_state import NativeHarpyFacts
from girlframe.engine.m3_void_state import HarpyIdentity
from girlframe.engine.m3_world_state import (
    AdversaryPilot,
    Asset,
    Board,
    CorePlan,
    Faction,
    Gorgon,
    Location,
    Npc,
)
from girlframe.services.m3_promotional_opportunity import PromotionalOpportunityService
from girlframe.services.onboarding import WorkflowError

BOONS = (
    ("useful", "A useful location"),
    ("mysterious", "A mysterious location"),
    ("defended_base", "A well-defended base"),
    ("two_cities", "Two cities"),
    ("personnel", "Competent and loyal personnel"),
)
THREATS = (
    ("rebels", "A new Rebel Faction"),
    ("dormant", "Dormant Gorgon in Gorgon Territory"),
    ("erratic", "Erratic Gorgon wandering wilderness"),
    ("territory", "8 Gorgon Territory squares"),
    ("harpy", "An active Harpy"),
)


def _board(old: Board, side: str, depth: int) -> Board:
    if depth < 2:
        raise WorkflowError("Author an adjoining map with valid increasing coordinate bounds")
    lo, hi = old.minimum, old.maximum
    if side == "east":
        return Board(minimum=(hi[0] + 1, lo[1]), maximum=(hi[0] + depth, hi[1]))
    if side == "west":
        return Board(minimum=(lo[0] - depth, lo[1]), maximum=(lo[0] - 1, hi[1]))
    if side == "north":
        return Board(minimum=(lo[0], hi[1] + 1), maximum=(hi[0], hi[1] + depth))
    if side == "south":
        return Board(minimum=(lo[0], lo[1] - depth), maximum=(hi[0], lo[1] - 1))
    raise WorkflowError("Choose the actual adjoining map edge")


async def open_opportunity(
    interaction: discord.Interaction,
    service: PromotionalOpportunityService,
    identity: str | None = None,
) -> None:
    data = await asyncio.to_thread(service.menu, viewer_from_interaction(interaction), identity)
    if data["acquisition"]:
        region = data["region"]
        if region["responsible"]:
            await reply(
                interaction,
                "You are responsible for Quadrant13. Its actual sites, people "
                "and threats remain on the canonical World. Your Base intake uses this office.",
            )
            return
        if not data["deaths"]:
            await reply(
                interaction,
                "Quadrant13 is unlocked. Its actual rival Handler remains the "
                "office holder until your source-proved real downfall. Complete the original "
                "NPC damage/death source through ordinary Handler Plays.",
            )
            return

        async def claim(current: discord.Interaction, values: dict[str, Any]) -> str:
            await asyncio.to_thread(
                service.take_over,
                viewer_from_interaction(current),
                str(current.id),
                data["acquisition"],
                data["revision"],
                values["death"][0],
            )
            return "Actual rival downfall proved. You now take responsibility for Quadrant13."

        await NativeForm(
            interaction.user.id,
            "Take regional responsibility",
            "Use the actual completed original rival's death source. This does not move any body.",
            [
                Field(
                    "death",
                    "Actual original rival death",
                    tuple((x["id"], x["label"]) for x in data["deaths"]),
                )
            ],
            claim,
        ).present(interaction)
        return
    if not data["awards"] or data["board"] is None:
        await reply(
            interaction, "Use your actual held advancement in an existing initialized World."
        )
        return

    async def select(current: discord.Interaction, values: dict[str, Any]) -> None:
        old = Board.model_validate_json(json.dumps(data["board"]))
        bounds = _board(old, values["side"][0], int(values["depth"]))
        cells = tuple(
            (x, y)
            for x in range(bounds.minimum[0], bounds.maximum[0] + 1)
            for y in range(bounds.minimum[1], bounds.maximum[1] + 1)
        )
        options = tuple((str(i), f"({cell[0]}, {cell[1]})") for i, cell in enumerate(cells))
        members = tuple((str(x["id"]), clean(x["label"])[:100]) for x in data["members"])
        award = values["award"][0]
        prefix = "quad13:" + award + ":"
        parts: dict[str, Any] = dict(
            bounds=bounds, boons=values["boons"], threats=values["threats"]
        )
        stages = ("rival",) + tuple(values["boons"]) + tuple(values["threats"]) + ("confirm",)

        def cell(fields: dict[str, Any], key: str = "cell") -> tuple[int, int]:
            return cells[int(fields[key][0])]

        async def stage(step: discord.Interaction, index: int) -> None:
            kind = stages[index]
            fields = []
            title = dict(BOONS + THREATS).get(kind, kind)
            if kind == "rival":
                fields = [
                    Field("name", "Actual rival Handler's name"),
                    Field("controller", "Actual human controlling this NPC", members),
                    Field("cell", "Actual regional office square", options),
                    Field("detail", "Actual rival person and regional office", paragraph=True),
                ]
            elif kind in ("useful", "mysterious", "defended_base"):
                fields = [
                    Field("name", "Actual location name"),
                    Field("cell", "Actual square", options),
                    Field("detail", "Actual purpose or physical fortifications", paragraph=True),
                ]
                if kind == "defended_base":
                    fields += [
                        Field("guard", "Actual garrison guard's name"),
                        Field("controller", "Actual guard controller", members),
                    ]
            elif kind == "two_cities":
                fields = [
                    Field("first", "First actual city name"),
                    Field("cell", "First square", options),
                    Field("second", "Second actual city name"),
                    Field("other_cell", "Second square", options),
                ]
            elif kind == "personnel":
                fields = [
                    Field("name", "Actual competent loyal staff member"),
                    Field("controller", "Actual NPC controller", members),
                    Field("cell", "Actual staff station", options),
                    Field(
                        "job",
                        "Actual competence",
                        tuple(
                            (x, x) for x in ("base_personnel", "mechanic", "scientist", "doctor")
                        ),
                    ),
                    Field("detail", "Actual role, competence and loyalty", paragraph=True),
                ]
            elif kind == "rebels":
                fields = [
                    Field("name", "Actual new Rebel faction"),
                    Field("cell", "Actual faction footprint", options),
                    Field("detail", "Actual organization and objective", paragraph=True),
                ]
            elif kind in ("dormant", "erratic"):
                from girlframe.engine.m3_world import CLASS_ASSETS

                fields = [
                    Field("name", "Actual Gorgon name"),
                    Field("cell", "Actual wilderness square", options),
                    Field(
                        "type",
                        "Actual printed Type",
                        tuple(
                            (x, x)
                            for x in (
                                "incubus",
                                "doppleganger",
                                "jackdaw",
                                "mother",
                                "sentinel",
                                "leviathan",
                                "growth",
                                "parasite",
                            )
                        ),
                    ),
                    Field("asset", "Actual Core-protecting Asset name"),
                    Field("description", "Actual Core-protecting Asset", paragraph=True),
                    Field("weakness", "Actual conversational Core weakness", paragraph=True),
                ]
                fields += [
                    Field("other" + str(i), "Actual additional Gorgon Asset " + str(i + 1))
                    for i in range(1, CLASS_ASSETS[kind])
                ]
            elif kind == "territory":
                fields = [
                    Field(
                        "cells",
                        "Eight actual Gorgon Territory squares",
                        options,
                        minimum=8,
                        maximum=8,
                    )
                ]
            elif kind == "harpy":
                fields = [
                    Field("name", "Actual active Harpy"),
                    Field("controller", "Actual Harpy controller", members),
                    Field("cell", "Actual linked body/Frame square", options),
                    Field("identity", "Actual unmarked personal Identity"),
                    Field("heat", "Actual current Heat"),
                    Field("girl", "Actual Void Girl Asset"),
                    Field("frame", "Actual Frame Asset"),
                ]
            elif kind == "confirm":
                fields = [
                    Field("account", "Actual authored regional map and contents", paragraph=True)
                ]

            async def save(followup: discord.Interaction, entered: dict[str, Any]) -> str | None:
                if kind == "confirm":
                    setup = rules.Setup.model_validate(parts | dict(account=entered["account"]))
                    await asyncio.to_thread(
                        service.acquire,
                        viewer_from_interaction(followup),
                        str(followup.id),
                        award,
                        data["revision"],
                        setup,
                    )
                    return "Quadrant13 unlocked. Open its private History card for takeover."
                ref = prefix + kind
                if kind == "rival":
                    parts["rival"] = Npc(
                        id=ref,
                        name=entered["name"],
                        jobs=("handler",),
                        controller=int(entered["controller"][0]),
                        cell=cell(entered),
                        detail=entered["detail"],
                        revealed=True,
                        employment="foundation",
                    )
                elif kind in ("useful", "mysterious", "defended_base"):
                    site = Location(
                        id=ref,
                        name=entered["name"],
                        cell=cell(entered),
                        kind="base" if kind == "defended_base" else "important",
                    )
                    parts[kind] = (
                        rules.Defence(
                            location=site,
                            detail=entered["detail"],
                            guards=(
                                Npc(
                                    id=ref + ":guard",
                                    name=entered["guard"],
                                    jobs=("guard",),
                                    detail="Actual garrison defending " + site.name,
                                    controller=int(entered["controller"][0]),
                                    cell=site.cell,
                                    revealed=True,
                                    employment="foundation",
                                ),
                            ),
                        )
                        if kind == "defended_base"
                        else rules.Site(location=site, detail=entered["detail"])
                    )
                elif kind == "two_cities":
                    parts["cities"] = (
                        Location(
                            id=ref + ":1", name=entered["first"], cell=cell(entered), kind="city"
                        ),
                        Location(
                            id=ref + ":2",
                            name=entered["second"],
                            cell=cell(entered, "other_cell"),
                            kind="city",
                        ),
                    )
                elif kind == "personnel":
                    parts["personnel"] = (
                        Npc(
                            id=ref,
                            name=entered["name"],
                            jobs=(entered["job"][0],),
                            controller=int(entered["controller"][0]),
                            cell=cell(entered),
                            detail=entered["detail"],
                            employment="foundation",
                            revealed=True,
                        ),
                    )
                elif kind == "rebels":
                    parts["rebels"] = Faction(
                        id=ref,
                        name=entered["name"],
                        kind="rebel",
                        cells=(cell(entered),),
                        description=entered["detail"],
                    )
                elif kind in ("dormant", "erratic"):
                    assets: tuple[Asset, ...] = (
                        Asset(
                            id=ref + ":core",
                            name=entered["asset"],
                            description=entered["description"],
                            family="gorgon",
                        ),
                    )
                    from girlframe.engine.m3_world import CLASS_ASSETS

                    for i in range(1, CLASS_ASSETS[kind]):
                        label = entered["other" + str(i)]
                        assets += (
                            Asset(
                                id=ref + ":other:" + str(i),
                                name=label,
                                description=label,
                                family="gorgon",
                            ),
                        )
                    parts[kind] = Gorgon(
                        id=ref,
                        name=entered["name"],
                        cell=cell(entered),
                        gorgon_class=kind,
                        types=entered["type"],
                        assets=assets,
                        revealed=True,
                        core_plan=CorePlan(assets=(assets[0].id,), weakness=entered["weakness"]),
                    )
                elif kind == "territory":
                    parts["territory"] = tuple(cells[int(x)] for x in entered["cells"])
                elif kind == "harpy":
                    person = AdversaryPilot(
                        id=ref,
                        name=entered["name"],
                        kind="harpy",
                        girl="Harpy",
                        frame="Harpy",
                        controller=int(entered["controller"][0]),
                        cell=cell(entered),
                        revealed=True,
                        assets=(
                            Asset(
                                id=ref + ":girl",
                                name=entered["girl"],
                                description=entered["girl"],
                                family="girl",
                                void=True,
                            ),
                            Asset(
                                id=ref + ":frame",
                                name=entered["frame"],
                                description=entered["frame"],
                                family="frame",
                                void=True,
                            ),
                        ),
                    )
                    parts["harpy"] = rules.HarpySetup(
                        person=person,
                        facts=NativeHarpyFacts(
                            actor=ActorRef(kind="external_pilot", entity=ref),
                            linked=True,
                            girl_cell=person.cell,
                            frame_cell=person.cell,
                            heat=int(entered["heat"]),
                            frame_shutdown=False,
                            body_incapacitated=False,
                            custody="free",
                            identities=(
                                HarpyIdentity(id=ref + ":identity", name=entered["identity"]),
                            ),
                            tags=(),
                            account="Actual active linked Harpy resources authored for this map",
                            facts_confirmed=True,
                        ),
                    )
                await stage(followup, index + 1)
                return None

            await NativeForm(
                step.user.id,
                "Quadrant13: " + str(title),
                "Author actual regional people and resources. Fixed defences and competence "
                "do not grant free player Assets, automatic success or automatic damage.",
                fields,
                save,
            ).present(step)

        await stage(current, 0)

    await NativeForm(
        interaction.user.id,
        "Unlock Quadrant13",
        "Choose three printed boons and two threats, then author their real contents. "
        "This is your table's authored adjoining geography.",
        [
            Field(
                "award",
                "Actual held award",
                tuple((x["id"], clean(x["label"])[:100]) for x in data["awards"]),
            ),
            Field("boons", "Three printed boons", BOONS, minimum=3, maximum=3),
            Field("threats", "Two printed threats", THREATS, minimum=2, maximum=2),
            Field(
                "side",
                "Actual adjoining edge",
                tuple((x, x) for x in ("east", "west", "north", "south")),
            ),
            Field("depth", "Authored map depth in squares"),
        ],
        select,
    ).present(interaction)
