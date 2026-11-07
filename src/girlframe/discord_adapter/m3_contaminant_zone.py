"""Owned quarantine creation, factual world people and ordinary source Play controls."""

import asyncio
from typing import Any
from uuid import uuid4

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.ledger import clean
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine import m3_contaminant_zone as rules
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_harpy_defeat_state import NativeHarpyFacts
from girlframe.engine.m3_void_state import HarpyIdentity
from girlframe.engine.m3_world_state import AdversaryPilot, Asset, Location
from girlframe.services.m3_contaminant_zone import ContaminantZoneService

LABELS = {
    "void_relief": "Reduce Void Strain until breach",
    "dormancy": "Actual Gorgons become Dormant",
    "rebel_replacement": "Replace actual contained Rebel Groups with Harpies",
    "field_study": "Protected field study and actual NPC manager",
}


def cells(text: str) -> tuple[tuple[int, int], ...]:
    result = []
    for line in text.splitlines():
        if line.strip():
            x, y = line.split(",")
            result.append((int(x.strip()), int(y.strip())))
    return tuple(result)


async def _establish(
    interaction: discord.Interaction, service: ContaminantZoneService, data: dict[str, Any]
) -> None:
    async def area(current: discord.Interaction, values: dict[str, Any]) -> None:
        request = rules.Quarantine(
            cells=cells(values["cells"]),
            effects=values["effects"],
            perimeter=values["perimeter"],
            account=values["account"],
            study=rules.StudySetup(
                location=Location(id="preview", name="preview", cell=(0, 0), kind="important"),
                manager="preview",
            )
            if "field_study" in values["effects"]
            else None,
        )
        actual = set(request.cells)
        groups = (
            [x for x in data["groups"] if x["cells"] and {tuple(c) for c in x["cells"]} <= actual]
            if "rebel_replacement" in request.effects
            else []
        )
        pending = dict(
            cells=request.cells,
            effects=request.effects,
            perimeter=request.perimeter,
            account=request.account,
        )
        await _replacement(current, service, data, pending, groups, [])

    await NativeForm(
        interaction.user.id,
        "Establish an actual quarantine",
        "Choose one contiguous area of at least two map squares, and exactly two rules. "
        "Describe the actual perimeter. This changes real territory and selected world effects.",
        [
            Field("cells", "Map cells, one x,y per line", paragraph=True),
            Field(
                "effects",
                "Exactly two printed rules",
                tuple((x, LABELS[x]) for x in rules.EFFECTS),
                2,
                2,
            ),
            Field("perimeter", "Actual quarantine perimeter", paragraph=True),
            Field("account", "Actual quarantine establishment", paragraph=True),
        ],
        area,
    ).present(interaction)


async def _replacement(
    interaction: discord.Interaction,
    service: ContaminantZoneService,
    data: dict[str, Any],
    pending: dict[str, Any],
    groups: list[dict[str, Any]],
    replacements: list[rules.HarpyReplacement],
) -> None:
    if not groups:
        await _study(interaction, service, data, pending, replacements)
        return
    group = groups[0]

    async def create(current: discord.Interaction, values: dict[str, Any]) -> None:
        identity = "contaminant-harpy:" + str(uuid4())
        cell = cells(values["cell"])[0]
        capabilities = []
        for family, field in (("girl", "girl_assets"), ("frame", "frame_assets")):
            for line in values.get(field, "").splitlines():
                if line.strip():
                    name, description = line.split(":", 1)
                    capabilities.append(
                        Asset(
                            id=str(uuid4()),
                            name=name.strip(),
                            description=description.strip(),
                            family="girl" if family == "girl" else "frame",
                        )
                    )
        person = AdversaryPilot(
            id=identity,
            name=values["name"],
            kind="harpy",
            girl="harpy",
            frame="harpy",
            cell=cell,
            controller=current.user.id,
            assets=tuple(capabilities),
            revealed=True,
        )
        facts = NativeHarpyFacts(
            actor=ActorRef(kind="external_pilot", entity=identity),
            linked=values["body"] == ("linked",),
            girl_cell=cell,
            frame_cell=cell,
            heat=int(values["heat"]),
            frame_shutdown=False,
            body_incapacitated=False,
            custody="free",
            identities=tuple(
                HarpyIdentity(id=str(uuid4()), name=line.strip())
                for line in values.get("identities", "").splitlines()
                if line.strip()
            ),
            tags=(),
            account=values["account"],
            facts_confirmed=True,
        )
        await _replacement(
            current,
            service,
            data,
            pending,
            groups[1:],
            replacements + [rules.HarpyReplacement(group=group["id"], person=person, facts=facts)],
        )

    await NativeForm(
        interaction.user.id,
        "Actual Harpy replacing " + clean(group["name"])[:60],
        "Author the actual new world Harpy you control, her existing capabilities and factual "
        "normal free, capable body. This destroys the organization; it does not kill its members. "
        "Each capability line is name:description. A Harpy Frame needs actual Frame capabilities.",
        [
            Field("name", "Actual Harpy name"),
            Field("cell", "An actual group square x,y"),
            Field(
                "body",
                "Actual new body's relationship to her Frame",
                (
                    ("linked", "Linked, capable, Frame functioning"),
                    ("outside", "Outside, capable, Frame functioning"),
                ),
            ),
            Field("heat", "Actual current Heat (integer)"),
            Field(
                "girl_assets",
                "Actual Girl capabilities: name:description",
                paragraph=True,
                required=False,
            ),
            Field("frame_assets", "Actual Frame capabilities: name:description", paragraph=True),
            Field("identities", "Actual Identities, one per line", paragraph=True, required=False),
            Field("account", "Actual new person and resource facts", paragraph=True),
        ],
        create,
    ).present(interaction)


async def _study(
    interaction: discord.Interaction,
    service: ContaminantZoneService,
    data: dict[str, Any],
    pending: dict[str, Any],
    replacements: list[rules.HarpyReplacement],
) -> None:
    async def finish(current: discord.Interaction, study: rules.StudySetup | None) -> None:
        result = await asyncio.to_thread(
            service.quarantine,
            viewer_from_interaction(current),
            str(current.id),
            data["acquisition"],
            data["revision"],
            rules.Quarantine(**pending, replacements=tuple(replacements), study=study),
        )
        await open_zone(current, service, result["id"])

    if "field_study" not in pending["effects"]:
        await finish(interaction, None)
        return

    async def assign(current: discord.Interaction, values: dict[str, Any]) -> None:
        selected = next(x for x in data["npcs"] if x["id"] == values["manager"][0])
        await finish(
            current,
            rules.StudySetup(
                location=Location(
                    id="contaminant-site:" + str(uuid4()),
                    name=values["name"],
                    cell=tuple(selected["cell"]),
                    kind="important",
                ),
                manager=selected["id"],
            ),
        )

    await NativeForm(
        interaction.user.id,
        "Actual protected field study",
        "Assign a living available NPC already in the area. The real site is established at "
        "their actual square; no person moves. A square already occupied by a major location "
        "requires a distinct actual site rather than overwriting it.",
        [
            Field("name", "Actual field study location"),
            Field(
                "manager",
                "Actual NPC already there",
                tuple(
                    (x["id"], clean(x["name"])[:100])
                    for x in data["npcs"]
                    if tuple(x["cell"]) in set(pending["cells"])
                ),
            ),
        ],
        assign,
    ).present(interaction)


async def open_zone(
    interaction: discord.Interaction, service: ContaminantZoneService, identity: str | None = None
) -> None:
    data = await asyncio.to_thread(service.menu, viewer_from_interaction(interaction), identity)
    if data["kind"] == "buy":

        async def buy(current: discord.Interaction, values: dict[str, Any]) -> str:
            await asyncio.to_thread(
                service.buy,
                viewer_from_interaction(current),
                str(current.id),
                data["award"],
                data["revision"],
                values["account"],
            )
            return (
                "One genuine held award acquired Contaminant Zone. Open its saved History controls."
            )

        await NativeForm(
            interaction.user.id,
            "Acquire Contaminant Zone",
            "Spend this actual held Handler advancement. "
            "Quarantines then choose two printed rules.",
            [Field("account", "Actual advancement acquisition", paragraph=True)],
            buy,
        ).present(interaction)
        return
    if data["kind"] == "awards":

        async def choose(current: discord.Interaction, values: dict[str, Any]) -> None:
            await open_zone(current, service, values["award"][0])

        await NativeForm(
            interaction.user.id,
            "Contaminant Zone",
            "Choose an actual held award.",
            [
                Field(
                    "award",
                    "Held award",
                    tuple((x["id"], clean(x["label"])[:100]) for x in data["awards"]),
                )
            ],
            choose,
        ).present(interaction)
        return
    if data["kind"] == "acquired":

        async def control(current: discord.Interaction, values: dict[str, Any]) -> None:
            if values["operation"] == ("quarantine",):
                await _establish(current, service, data)
            else:
                await open_zone(current, service, values["operation"][0])

        await NativeForm(
            interaction.user.id,
            "Contaminant Zone — actual world controls",
            "Establish a real quarantine or reopen its saved private source history. "
            "The actual warp-area Play is also available through your normal Handler Plays.",
            [
                Field(
                    "operation",
                    "Actual source operation",
                    (("quarantine", "Establish an actual quarantine"),)
                    + tuple(
                        (
                            x["id"],
                            "Broken quarantine"
                            if x["broken_event"]
                            else clean(x["perimeter"])[:100],
                        )
                        for x in data["zones"]
                    ),
                )
            ],
            control,
        ).present(interaction)
        return
    body = data["body"]
    if body["broken_event"]:
        await reply(
            interaction,
            "Actual quarantine was broken. Relief and protection ended; territory, "
            "people, site and prior Class/group outcomes remain.\n" + clean(body["breach_account"]),
        )
        return

    async def operation(current: discord.Interaction, values: dict[str, Any]) -> None:
        if values["operation"] == ("warp",):
            result = await asyncio.to_thread(
                service.start_warp,
                viewer_from_interaction(current),
                str(current.id),
                body["id"],
                data["revision"],
            )
            from girlframe.discord_adapter.m3_handler_plays import open_play
            from girlframe.services.m3_handler_plays import HandlerPlayService

            await open_play(current, HandlerPlayService(service.store), result["id"])
            return

        async def breach(answer: discord.Interaction, facts: dict[str, Any]) -> str:
            selected = next(
                x
                for x in data["actors"]
                if ActorRef.model_validate(x["ref"]).token == facts["actor"][0]
            )
            await asyncio.to_thread(
                service.break_quarantine,
                viewer_from_interaction(answer),
                str(answer.id),
                body["id"],
                data["revision"],
                ActorRef.model_validate(selected["ref"]),
                cells(facts["cell"])[0],
                facts["account"],
            )
            return "The actual breach is recorded. Only this zone's relief/protection expired."

        await NativeForm(
            current.user.id,
            "Record an actual quarantine breach",
            "As actual world facilitator, record the real perimeter failure "
            "and its already-present "
            "actor/cell. This is a world event, not an acknowledgment or a way to move someone.",
            [
                Field(
                    "actor",
                    "Actual present breach actor",
                    tuple(
                        (ActorRef.model_validate(x["ref"]).token, clean(x["label"])[:100])
                        for x in data["actors"]
                    ),
                ),
                Field("cell", "Their actual affected zone cell x,y"),
                Field("account", "Actual breach and perimeter failure", paragraph=True),
            ],
            breach,
        ).present(current)

    await NativeForm(
        interaction.user.id,
        "Actual active quarantine",
        clean(body["perimeter"])
        + "\nCells: "
        + str(body["cells"])
        + "\nRules: "
        + ", ".join(LABELS[x] for x in body["effects"]),
        [
            Field(
                "operation",
                "Actual source operation",
                (
                    ("warp", "Warp the area: actual Handler Play"),
                    ("breach", "Record actual quarantine break"),
                ),
            )
        ],
        operation,
    ).present(interaction)
