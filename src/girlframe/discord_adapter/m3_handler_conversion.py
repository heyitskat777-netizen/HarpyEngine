"""Private actual Harpy repossession, performed treatment and owned Mockingbird choices."""

import asyncio
from typing import Any, Literal

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.ledger import clean
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine.creation import AssetChoice
from girlframe.engine.creation_catalog import CATALOG
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_handler_conversion import MockingbirdPackage
from girlframe.engine.npc_bonds import NPC_ROLES
from girlframe.services.m3_handler_conversion import HandlerConversionService
from girlframe.services.onboarding import WorkflowError


async def open_conversion(
    interaction: discord.Interaction,
    service: HandlerConversionService,
    identity: str | None = None,
) -> None:
    data = await asyncio.to_thread(service.menu, viewer_from_interaction(interaction), identity)
    if identity is None:
        if not data["candidates"]:
            await reply(
                interaction, "No eligible original reborn Harpy has actual Foundation custody."
            )
            return

        async def begin(current: discord.Interaction, values: dict[str, Any]) -> str:
            actor = next(x["actor"] for x in data["candidates"] if x["token"] == values["actor"][0])
            await asyncio.to_thread(
                service.open,
                viewer_from_interaction(current),
                str(current.id),
                data["revision"],
                ActorRef.model_validate(actor),
            )
            return (
                "Actual capture source saved. Extraction, transport and treatment remain required."
            )

        await NativeForm(
            interaction.user.id,
            "Repossess an actually captured Harpy",
            "This opens a source-bound original-person process. It grants no conversion or award.",
            [
                Field(
                    "actor",
                    "Actual captured original Harpy",
                    tuple((x["token"], x["label"]) for x in data["candidates"]),
                )
            ],
            begin,
        ).present(interaction)
        return
    phase = data["phase"]
    if phase == "complete":
        if not data["claimable"]:
            await reply(
                interaction,
                "Actual Mockingbird conversion saved. "
                + (
                    "One genuine ordinary award is saved."
                    if data["award"]
                    else "Conversion is saved; the ordinary cap and mark govern any later award."
                ),
            )
            return

        async def claim(current: discord.Interaction, values: dict[str, Any]) -> str:
            await asyncio.to_thread(
                service.claim,
                viewer_from_interaction(current),
                str(current.id),
                identity,
                data["revision"],
            )
            return "Original completed source claimed once in this actual free Session."

        await NativeForm(
            interaction.user.id,
            "Claim actual capture/conversion",
            "Actual conversion is already saved. Claiming consumes this Session's ordinary slot.",
            [
                Field(
                    "claim",
                    "Genuine original source",
                    (("claim", "Claim this completed conversion"),),
                )
            ],
            claim,
        ).present(interaction)
        return
    if data["pending_physical"] and data["judge"]:
        item = data["physicals"][-1]

        async def physical_review(current: discord.Interaction, values: dict[str, Any]) -> str:
            await asyncio.to_thread(
                service.review_physical,
                viewer_from_interaction(current),
                str(current.id),
                identity,
                data["revision"],
                values["result"][0] == "yes",
                values["account"],
            )
            return "Actual physical outcome reviewed; no body or Frame movement is inferred."

        await NativeForm(
            interaction.user.id,
            "Actual captured-body physical result",
            clean(item["account"])
            + "\nReview actual performed "
            + item["operation"]
            + "; a proposal, absent response or contradictory known location is insufficient.",
            [
                Field(
                    "result",
                    "Actual result",
                    (
                        ("yes", "This physical event actually occurred"),
                        ("no", "This proposed result did not occur"),
                    ),
                ),
                Field("account", "Actual factual outcome and physical source", paragraph=True),
            ],
            physical_review,
        ).present(interaction)
        return
    if (
        phase in ("captured", "extracted")
        and data["owns_physical"]
        and not data["pending_physical"]
    ):
        operation: Literal["extract", "transport"] = (
            "extract" if phase == "captured" else "transport"
        )

        async def physical(current: discord.Interaction, values: dict[str, Any]) -> str:
            destination = next(
                (
                    tuple(x["cell"])
                    for x in data["bases"]
                    if values.get("destination") and x["id"] == values["destination"][0]
                ),
                None,
            )
            await asyncio.to_thread(
                service.physical,
                viewer_from_interaction(current),
                str(current.id),
                identity,
                data["revision"],
                operation,
                values["account"],
                destination,
            )
            return "Actual custodian action sent to GM factual review."

        fields = [
            Field(
                "account", "Actual performed " + operation + " and body/Frame facts", paragraph=True
            )
        ]
        if operation == "transport":
            fields.append(
                Field(
                    "destination",
                    "Actual Foundation destination Base",
                    tuple((x["id"], x["label"]) for x in data["bases"]),
                )
            )
        await NativeForm(
            interaction.user.id,
            "Actual captured Harpy " + operation,
            "Record the actual physical event. Existing Frame consent, known locations "
            "and real custodian position remain required. Only the body travels in transport.",
            fields,
            physical,
        ).present(interaction)
        return
    if phase == "transported" and data["judge"]:

        async def treatment(current: discord.Interaction, values: dict[str, Any]) -> str:
            await asyncio.to_thread(
                service.treat,
                viewer_from_interaction(current),
                str(current.id),
                identity,
                data["revision"],
                values["purge"],
                values["organs"],
                values["conditioning"],
                values["recovery"][0] == "awake",
            )
            return "Actual purge, organ treatment and reprogramming saved."

        await NativeForm(
            interaction.user.id,
            "Actual Harpy repossession treatment",
            "Record completed institutional treatment of this exact transported original. No dice, "
            "fictional cooperation or new treatment charge is invented.",
            [
                Field("purge", "Actual poisons purged without Frame metabolism", paragraph=True),
                Field("organs", "Actual organs studied, treated or excised", paragraph=True),
                Field("conditioning", "Actual drugs and reprogramming performed", paragraph=True),
                Field(
                    "recovery",
                    "Actual treated body's medical condition",
                    (
                        ("awake", "Actual medical waking/recovery completed"),
                        ("unchanged", "Preserve existing incapacity or inactive vitals"),
                    ),
                ),
            ],
            treatment,
        ).present(interaction)
        return
    if phase == "treated" and data["owner"]:
        assets = tuple((x, x) for x in CATALOG["MOCKINGBIRD"]["assets"])
        roles = tuple((str(i), role) for i, role in enumerate(NPC_ROLES["MOCKINGBIRD"]))

        async def package(current: discord.Interaction, values: dict[str, Any]) -> str:
            girl = next(x["ref"] for x in data["girls"] if x["token"] == values["girl"][0])
            bonds = [
                (
                    int(values["role"][0]),
                    ActorRef.model_validate(
                        next(x["ref"] for x in data["npcs"] if x["token"] == values["npc"][0])
                    ),
                )
            ]
            if values.get("npc2") and values["npc2"][0] != "none":
                if not values.get("role2"):
                    raise WorkflowError("Choose the second NPC's actual printed role")
                bonds.append(
                    (
                        int(values["role2"][0]),
                        ActorRef.model_validate(
                            next(x["ref"] for x in data["npcs"] if x["token"] == values["npc2"][0])
                        ),
                    )
                )
            selected = values["assets"]
            result = MockingbirdPackage(
                assets=(
                    AssetChoice(name=selected[0], description=values["description1"]),
                    AssetChoice(name=selected[1], description=values["description2"]),
                ),
                void_asset=values["void"][0],
                girl_bond=ActorRef.model_validate(girl),
                npc_bonds=tuple(bonds),
                appearance=values["appearance"],
            )
            await asyncio.to_thread(
                service.package,
                viewer_from_interaction(current),
                str(current.id),
                identity,
                data["revision"],
                result,
            )
            return "Your exact Mockingbird package saved for source review."

        npcs = tuple((x["token"], x["label"]) for x in data["npcs"])
        await NativeForm(
            interaction.user.id,
            "Your resulting Mockingbird",
            "Choose post-treatment Girl resources and printed starting Bonds. The physical "
            "Frame retains its damage and Void. Choosing does not imply fictional cooperation.",
            [
                Field("assets", "Two printed Girl Assets", assets, 2, 2),
                Field("description1", "Describe first selected Asset", paragraph=True),
                Field("description2", "Describe second selected Asset", paragraph=True),
                Field("void", "Selected Asset altered by Void", assets),
                Field("appearance", "Actual post-treatment appearance", paragraph=True),
                Field(
                    "girl",
                    "Actual Girl Personal Bond",
                    tuple((x["token"], x["label"]) for x in data["girls"]),
                ),
                Field("role", "Actual printed NPC role", roles),
                Field("npc", "Actual NPC", npcs),
                Field("role2", "Second printed NPC role if chosen", roles, 0, 1, required=False),
                Field(
                    "npc2",
                    "Optional second actual NPC",
                    (("none", "No second NPC Bond"),) + npcs,
                    0,
                    1,
                    required=False,
                ),
            ],
            package,
        ).present(interaction)
        return
    package_data = data.get("package")
    package_text = ""
    if package_data:
        package_text = (
            "\nResulting Girl Assets: "
            + "; ".join(
                clean(x["name"])
                + ": "
                + clean(x["description"])
                + (" (Void-altered)" if x["name"] == package_data["void_asset"] else "")
                for x in package_data["assets"]
            )
            + "\nAppearance: "
            + clean(package_data["appearance"])
        )
        girl = next(
            (x["label"] for x in data["girls"] if x["ref"] == package_data["girl_bond"]),
            "Original selected Girl",
        )
        package_text += "\nPersonal Bond: " + clean(girl)
        for slot, ref in package_data["npc_bonds"]:
            npc = next(
                (x["label"] for x in data["npcs"] if x["ref"] == ref), "Original selected NPC"
            )
            package_text += "\n" + NPC_ROLES["MOCKINGBIRD"][slot] + ": " + clean(npc)
    if phase == "package" and data["judge"]:

        async def review(current: discord.Interaction, values: dict[str, Any]) -> str:
            await asyncio.to_thread(
                service.review,
                viewer_from_interaction(current),
                str(current.id),
                identity,
                data["revision"],
                int(values["position"][0]),
                values["account"],
            )
            return (
                "Actual treatment/package reviewed. Original human controls exact final activation."
            )

        await NativeForm(
            interaction.user.id,
            "Actual Mockingbird conversion review",
            "Review the original human's package and treatment. Preserve the actual body, Frame "
            "and surviving resource state; Status is an actual roster insertion." + package_text,
            [
                Field(
                    "position",
                    "Actual Status position (first is highest)",
                    tuple((str(i), str(i + 1)) for i in range(len(data["girls"]) + 1)),
                ),
                Field("account", "Actual completed conversion and package review", paragraph=True),
            ],
            review,
        ).present(interaction)
        return
    if phase == "ready" and data["owner"]:

        async def complete(current: discord.Interaction, values: dict[str, Any]) -> str:
            await asyncio.to_thread(
                service.complete,
                viewer_from_interaction(current),
                str(current.id),
                identity,
                data["revision"],
            )
            return (
                "Actual current Mockingbird installed once. Ordinary award eligibility is separate."
            )

        await NativeForm(
            interaction.user.id,
            "Confirm your actual Mockingbird activation",
            "Confirm your exact resulting Girl package. The old Harpy cannot remain "
            "a second live actor; the physical Frame is neither replaced nor repaired."
            + package_text
            + "\nActual Status position: "
            + str(data["status_position"] + 1),
            [
                Field(
                    "confirm",
                    "Original human's resulting package",
                    (("confirm", "Confirm this exact package"),),
                )
            ],
            complete,
        ).present(interaction)
        return
    await reply(
        interaction,
        "This exact original source is saved. Its next actual owner controls the next step.",
    )
