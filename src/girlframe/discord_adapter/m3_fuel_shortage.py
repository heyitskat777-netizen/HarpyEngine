"""Human-owned scheduling and actual same-battle unavoidable-loss selections."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_fuel_shortage import LossSelection
from girlframe.services.m3_fuel_shortage import FuelService
from girlframe.services.onboarding import WorkflowError


def battle_fields(data: dict[str, Any]) -> list[Field]:
    """Only the actual reviewed Context's source-owned options, added to its form."""
    fields = []
    for index, source in enumerate(data["arms"], 1):
        prefix = "fuel:" + source["id"] + ":"
        if source["npcs"]:
            fields.append(
                Field(
                    prefix + "npc",
                    f"Fuel shortage {index}: actual NPC affected",
                    tuple((x["ref"]["entity"], x["label"]) for x in source["npcs"]),
                    0,
                    1,
                    required=False,
                )
            )
        if source["locations"]:
            fields.append(
                Field(
                    prefix + "site",
                    f"Fuel shortage {index}: actual site affected",
                    tuple((x["id"], x["label"]) for x in source["locations"]),
                    0,
                    1,
                    required=False,
                )
            )
        if source["npcs"]:
            fields.append(
                Field(
                    prefix + "npc_outcome",
                    "NPC outcome (default: killed)",
                    (
                        ("die", "Killed"),
                        ("capture", "Captured by actual Gorgon"),
                        ("corrupt", "Receives actual NPC Void Tag"),
                    ),
                    0,
                    1,
                    required=False,
                )
            )
        if source["locations"]:
            fields.append(
                Field(
                    prefix + "site_outcome",
                    "Site outcome (default: destroyed)",
                    (
                        ("destroy", "Destroyed"),
                        ("capture", "Captured; buildings retained"),
                        ("corrupt", "Corrupted; buildings retained"),
                    ),
                    0,
                    1,
                    required=False,
                )
            )
        if source.get("threats"):
            fields.append(
                Field(
                    prefix + "threat",
                    "Actual nearby Gorgon (capture/corruption)",
                    tuple((x["ref"]["entity"], x["label"]) for x in source["threats"]),
                    0,
                    1,
                    required=False,
                )
            )
        if source.get("handler_choice"):
            fields.append(
                Field(
                    prefix + "manifestation",
                    "Handler: actual NPC Void manifestation",
                    (
                        ("brain", "Void of the brain"),
                        ("bones", "Void of the bones"),
                        ("flesh", "Void of the flesh"),
                        ("abstract", "Void of the abstract"),
                    ),
                    0,
                    1,
                    required=False,
                )
            )
        if source.get("manifestations") or not source.get("handler_choice"):
            fields.append(
                Field(
                    prefix + "manifestation_source",
                    "Actual saved Handler choice",
                    tuple(
                        (x["id"], "NPC Void: " + x["manifestation"])
                        for x in source.get("manifestations", [])
                    )
                    or (("pending", "Await actual Handler choice on saved Fuel card"),),
                    0,
                    1,
                    required=False,
                )
            )
        fields.append(
            Field(
                prefix + "account",
                f"Fuel shortage {index}: actual unavoidable loss",
                paragraph=True,
            )
        )
    return fields


def battle_losses(data: dict[str, Any], values: dict[str, Any]) -> tuple[LossSelection, ...]:
    result = []
    for source in data["arms"]:
        prefix = "fuel:" + source["id"] + ":"
        npc = tuple(values.get(prefix + "npc", ()))
        site = tuple(values.get(prefix + "site", ()))
        people = {x["ref"]["entity"]: x["ref"] for x in source["npcs"]}
        locations = {x["id"] for x in source["locations"]}
        if (
            len(npc) > 1
            or len(site) > 1
            or (npc and npc[0] not in people)
            or (site and site[0] not in locations)
        ):
            raise WorkflowError("Choose an actual available body/site from this battle source")
        npc_outcome = (values.get(prefix + "npc_outcome") or ("die",))[0] if npc else "die"
        site_outcome = (
            (values.get(prefix + "site_outcome") or ("destroy",))[0] if site else "destroy"
        )
        threat = values.get(prefix + "threat", ())
        actual_threats = {x["ref"]["entity"]: x["ref"] for x in source.get("threats", [])}
        if threat and (len(threat) != 1 or threat[0] not in actual_threats):
            raise WorkflowError("Choose this source's actual placed Gorgon threat")
        manifestation = None
        manifestation_source = None
        if npc_outcome == "corrupt":
            chosen = next(iter(values.get(prefix + "manifestation_source", ())), None)
            if source.get("handler_choice") and chosen is None:
                manifestation = next(iter(values.get(prefix + "manifestation", ())), None)
            else:
                plan = next(
                    (x for x in source.get("manifestations", []) if x["id"] == chosen), None
                )
                if (
                    plan is None
                    or plan["target"] != people[npc[0]]
                    or not threat
                    or plan["threat"] != actual_threats[threat[0]]
                ):
                    raise WorkflowError(
                        "HANDLER_MANIFESTATION_PENDING: actual Handler chooses on saved Fuel card"
                    )
                manifestation, manifestation_source = plan["manifestation"], plan["id"]
        result.append(
            LossSelection.model_validate(
                dict(
                    source=source["id"],
                    npc=ActorRef.model_validate(people[npc[0]]) if npc else None,
                    location=site[0] if site else None,
                    account=str(values.get(prefix + "account", "")),
                    npc_outcome=npc_outcome,
                    location_outcome=site_outcome,
                    threat=ActorRef.model_validate(actual_threats[threat[0]]) if threat else None,
                    manifestation=manifestation,
                    manifestation_source=manifestation_source,
                )
            )
        )
    return tuple(result)


async def open_manifestation(
    interaction: discord.Interaction, service: FuelService, identity: str
) -> None:
    data = await asyncio.to_thread(
        service.manifestation_menu, viewer_from_interaction(interaction), identity
    )
    if not data["contexts"]:
        await reply(
            interaction, "No actual proposed battle currently has a supported NPC Void choice."
        )
        return

    async def context(current: discord.Interaction, values: dict[str, Any]) -> None:
        source = next(x for x in data["contexts"] if x["id"] == values["context"][0])

        async def choose(final: discord.Interaction, answers: dict[str, Any]) -> str:
            target = next(
                x["ref"] for x in source["npcs"] if x["ref"]["entity"] == answers["npc"][0]
            )
            threat = next(
                x["ref"] for x in source["threats"] if x["ref"]["entity"] == answers["threat"][0]
            )
            await asyncio.to_thread(
                service.choose_manifestation,
                viewer_from_interaction(final),
                str(final.id),
                identity,
                source["id"],
                ActorRef.model_validate(target),
                ActorRef.model_validate(threat),
                answers["manifestation"][0],
                data["revision"],
            )
            return (
                "Your actual Handler choice is saved. The adjudicator still owns "
                "the real loss selection; no Void or discovery was invented."
            )

        form = NativeForm(
            current.user.id,
            "Actual Handler NPC Void choice",
            "Choose the printed manifestation for this real NPC and threat. "
            "This alone does not corrupt, reveal, perform surgery or answer for that NPC.",
            [
                Field(
                    "npc",
                    "Actual NPC",
                    tuple((x["ref"]["entity"], x["label"]) for x in source["npcs"]),
                ),
                Field(
                    "threat",
                    "Actual nearby Gorgon",
                    tuple((x["ref"]["entity"], x["label"]) for x in source["threats"]),
                ),
                Field(
                    "manifestation",
                    "Printed NPC Void manifestation",
                    tuple((x, "Void of the " + x) for x in ("brain", "bones", "flesh", "abstract")),
                ),
            ],
            choose,
        )
        await reply(current, form.text(), form)

    form = NativeForm(
        interaction.user.id,
        "Choose actual proposed battle",
        "Only the real Handler authors this manifestation; "
        "the other adjudicator can use the saved choice.",
        [
            Field(
                "context",
                "Actual pending battle",
                tuple((x["id"], x["label"]) for x in data["contexts"]),
            )
        ],
        context,
    )
    await reply(interaction, form.text(), form)


async def open_fuel_shortage(
    interaction: discord.Interaction, service: FuelService, identity: str | None = None
) -> None:
    viewer = viewer_from_interaction(interaction)
    if identity is None:
        with service.store.engine.connect() as c:
            sources = service._tasks(c, viewer)
        if not sources:
            await reply(interaction, "No saved fuel-shortage source belongs to this role.")
            return

        async def choose(current: discord.Interaction, values: dict[str, Any]) -> None:
            await open_fuel_shortage(current, service, values["source"][0])

        form = NativeForm(
            interaction.user.id,
            "Your actual fuel-shortage sources",
            "Read the original scheduling and real battle-loss records.",
            [
                Field(
                    "source",
                    "Actual source",
                    tuple(
                        (x["id"], f"Fuel shortage {index}: {x['phase']}")
                        for index, x in enumerate(sources, 1)
                    ),
                )
            ],
            choose,
        )
        await reply(interaction, form.text(), form)
        return
    data = await asyncio.to_thread(service.view, viewer, identity)
    if data["can_arm"]:

        async def arm(current: discord.Interaction, values: dict[str, Any]) -> str:
            await asyncio.to_thread(
                service.arm,
                viewer_from_interaction(current),
                str(current.id),
                identity,
                data["revision"],
            )
            return (
                "The actual fuel shortage is armed for the next genuine Cadre battle. "
                "A mission alone does not spend it. The adjudicator must record a real "
                "unavoidable loss before that battle can proceed."
            )

        form = NativeForm(
            interaction.user.id,
            "Fuel shortage — actual next battle",
            "Save this selected Strain consequence as a real future-battle obligation. "
            "No target or outcome is invented now; arming does not prevent the printed loss.",
            [Field("operation", "Actual scheduling", (("arm", "Arm the next real battle delay"),))],
            arm,
        )
        await reply(interaction, form.text(), form)
        return
    if data["phase"] == "handler_choice":
        await open_manifestation(interaction, service, identity)
        return
    value = data["record"]
    if value["battle"] is None:
        text = (
            "Fuel shortage — armed. The next subsequent actual Cadre battle declaration "
            "must receive its real unavoidable loss at confirmation. "
            "Ordinary mission activity does not consume this source."
        )
    else:
        outcomes = []
        if value["original_npc"]:
            kind = value["loss"].get("npc_outcome", "die")
            outcomes.append(
                value["original_npc"]["name"]
                + " — "
                + {
                    "die": "killed",
                    "capture": "captured by the actual Gorgon",
                    "corrupt": "actual Void of the " + str(value["loss"].get("manifestation")),
                }[kind]
            )
        if value["original_location"]:
            kind = value["loss"].get("location_outcome", "destroy")
            outcomes.append(
                value["original_location"]["name"]
                + " — "
                + {
                    "destroy": "destroyed",
                    "capture": "captured; buildings retained",
                    "corrupt": "corrupted; buildings retained",
                }[kind]
            )
        text = "Fuel shortage — " + data["phase"] + ".\n" + "; ".join(outcomes)
        text += "\n" + value["loss"]["account"]
        text += (
            "\nThe loss happened before a prevention roll. Genuine followups keep their own work."
        )
    if data.get("can_manifestation"):
        menu = await asyncio.to_thread(service.manifestation_menu, viewer, identity)
        if menu["contexts"]:

            async def choose(current: discord.Interaction, values: dict[str, Any]) -> None:
                await open_manifestation(current, service, identity)

            form = NativeForm(
                interaction.user.id,
                "Fuel shortage — actual Handler choice",
                text,
                [
                    Field(
                        "operation",
                        "Optional actual source choice",
                        (("manifestation", "Choose NPC Void manifestation for proposed battle"),),
                    )
                ],
                choose,
            )
            await reply(interaction, form.text(), form)
            return
    await reply(interaction, text)
