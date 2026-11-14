"""Actual native DoctorDoctor source choices; each patient owns their sheet details."""

import asyncio
import json
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.m3_modular import replacement_fields, replacements
from girlframe.discord_adapter.m3_punishments import Picker
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine import m3_doctor as rules
from girlframe.engine.m2 import ChoiceAnswer, PlayInput
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.services.m3_doctor import DoctorService
from girlframe.services.onboarding import WorkflowError


async def open_doctor(interaction: discord.Interaction, service: DoctorService) -> None:
    if interaction.channel_id is None:
        raise WorkflowError("Use the original joined scene channel")
    from girlframe.services.m3_doctor_procedures import ProcedureService

    calls = await asyncio.to_thread(
        ProcedureService(service.game).call_menu,
        viewer_from_interaction(interaction),
        interaction.channel_id,
    )
    if not calls["native"]:
        await open_call(interaction, service, calls)
        return
    data = await asyncio.to_thread(
        service.menu, viewer_from_interaction(interaction), interaction.channel_id
    )
    options = [("roll", "Nanobot Injection / Here for Support")]
    if calls["doctors"]:
        options.append(("call", "Call another Doctor — Running Ragged"))
    if data["acquisitions"]:
        options.append(("buy", "Acquire a native Requisition (2 Permissions; unmark one box)"))
    for rule, kind in (
        (rules.NURSE, "nurse"),
        (rules.ANGEL, "angel"),
        (rules.WINGS, "wings"),
        (rules.RAGGED, "ragged"),
        (rules.ADRENAL, "adrenal"),
    ):
        if rule in data["held"]:
            options.append((kind, rules.TITLES[rule]))

    async def choose(current: discord.Interaction, kind: str) -> None:
        if kind == "call":
            await open_call(current, service, calls)
        elif kind == "roll":
            await open_roll(current, service)
        else:
            await open_procedure(current, service, data, kind)

    await Picker(
        interaction.user.id,
        "DoctorDoctor — Obsolescence " + str(data["track"]) + "/8",
        tuple(options),
        choose,
    ).show(interaction)


async def open_call(
    interaction: discord.Interaction, service: DoctorService, data: dict[str, Any]
) -> None:
    """The caller declares their own call, then either participant pays their Tag."""
    from girlframe.services.m3_doctor_procedures import ProcedureService

    if not data["doctors"]:
        raise WorkflowError("No other joined Doctor has actual Running Ragged")

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        doctor = next(x for x in data["doctors"] if x["token"] == values["doctor"][0])
        assert interaction.channel_id is not None
        result = await asyncio.to_thread(
            ProcedureService(service.game).propose,
            viewer_from_interaction(current),
            str(current.id),
            data["revision"],
            interaction.channel_id,
            ActorRef.model_validate(data["caller"]),
            "ragged",
            values["account"],
            called_doctor=ActorRef.model_validate(doctor["ref"]),
        )
        return (
            "Your actual call is saved. Either participant may mark their own Tag in the Inbox: "
            + str(result["id"])
        )

    await NativeForm(
        interaction.user.id,
        "Call a Doctor — Running Ragged",
        "Declare your actual call. Arrival requires either participant's own unmarked Tag.",
        [
            Field(
                "doctor", "Doctor to call", tuple((x["token"], x["label"]) for x in data["doctors"])
            ),
            Field("account", "Describe your actual call", paragraph=True),
        ],
        submit,
    ).present(interaction)


async def open_roll(interaction: discord.Interaction, service: DoctorService) -> None:
    if interaction.channel_id is None:
        raise WorkflowError("Use the original joined scene channel")
    data = await asyncio.to_thread(
        service.menu, viewer_from_interaction(interaction), interaction.channel_id
    )
    if not data["choices"]:
        await reply(
            interaction,
            "No reviewed native Doctor ability is available. Track: " + str(data["track"]) + "/8.",
        )
        return
    from girlframe.discord_adapter.m3_dampener import fields as dampener_fields
    from girlframe.discord_adapter.m3_dampener import modifier as dampener_modifier
    from girlframe.services.m3_dampener import DampenerService

    dampener_controls = await dampener_fields(
        interaction, DampenerService(service.game), ActorRef.model_validate(data["actor"])
    )

    targets = list(
        {
            row["token"]: row
            for row in data["targets"]
            + data.get("npc_nanobot_targets", [])
            + data.get("npc_support_targets", [])
        }.values()
    )

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        target = next(x for x in targets if x["token"] == values["target"][0])
        if target["ref"]["kind"] == "npc":
            eligible = data[
                "npc_support_targets"
                if values["play"][0] == "doctor_support"
                else "npc_nanobot_targets"
            ]
            if target["token"] not in {row["token"] for row in eligible}:
                raise WorkflowError("Choose an actual NPC counterpart supported by this ability")
        assert interaction.channel_id is not None
        result = await asyncio.to_thread(
            service.game.begin,
            viewer_from_interaction(current),
            str(current.id),
            interaction.channel_id,
            data["sheet_revision"],
            PlayInput(
                play=values["play"][0],
                target_actor=ActorRef.model_validate(target["ref"]),
                heat=int(values["heat"][0]),
                dampener_modifier=dampener_modifier(values),
                context=values["account"],
                trigger_confirmed=True,
            ),
        )
        return (
            "Actual Doctor action prepared: "
            + str(result["action_id"])
            + ". Resume Pending choices."
        )

    await NativeForm(
        interaction.user.id,
        "DoctorDoctor Mk. II",
        "Planned Obsolescence: "
        + str(data["track"])
        + "/8. Actual Nanobot use marks one box; it does not move either body. "
        "NPCs: Here for Support uses their own controller and Tags. "
        "New NPC Nanobot Injection is unavailable: required NPC medical mechanics are "
        "incomplete. Previously rolled NPC actions retain their pending recovery choices.",
        [
            Field("play", "Actual ability", tuple((x["id"], x["label"]) for x in data["choices"])),
            Field(
                "target",
                "Actual patient or protector",
                tuple((x["token"], x["label"]) for x in targets),
            ),
            Field("heat", "Heat", tuple((str(x), str(x)) for x in range(data["heat"] + 1))),
            Field("account", "Describe the actual medical trigger", paragraph=True),
        ]
        + dampener_controls,
        submit,
    ).present(interaction)


async def open_choice(
    interaction: discord.Interaction, service: DoctorService, identity: str
) -> None:
    data = await asyncio.to_thread(
        service.game.decision, viewer_from_interaction(interaction), identity
    )
    detail = data["doctor"]
    if detail.get("unsupported"):
        from girlframe.discord_adapter.p1_facilitator import open_missing_source

        await open_missing_source(
            interaction, service.game, "action", data["parent"], "choice:" + data["kind"]
        )
        return
    if data["kind"] == "doctor_handler":
        from girlframe.discord_adapter.m3_handler_plays import open_play
        from girlframe.services.m3_handler_plays import HandlerPlayService

        grant = data["body"].get("handler_grant")
        if not grant:
            raise WorkflowError("Recover the actual required Handler grant first")
        await open_play(interaction, HandlerPlayService(service.store), grant)
        return
    if data["kind"] == "doctor_support_response":
        options: tuple[tuple[str, str], ...] = (("protect", "Protect the actual Doctor"),)
        if data["body"].get("may_refuse"):
            options += (("refuse", "Decline to protect"),)
        fields = [
            Field("decision", "Actual protection", options),
            Field("bond", "If protecting: deepen Bond?", (("no", "No"), ("yes", "Yes"))),
        ]
    elif data["kind"] == "doctor_support_refused":
        consequences: tuple[tuple[str, str], ...] = (("tag", "Give a Tag"),)
        if not detail.get("npc"):
            consequences += (("status", "Lower Status"),)
        fields = [
            Field("decision", "Consequence", consequences),
            Field("tag", "Only for Tag: actual new Tag", required=False),
        ]
    elif data["kind"] == "doctor_nanobot_benefits":
        choices: tuple[tuple[str, str], ...] = (
            ("repair", "Repair two actual damaged Assets"),
            ("identity", "Patient may unmark an actual Identity"),
        )
        if detail.get("npc"):
            choices = ()
        if detail["effects"]:
            choices += (("remove", "Remove a supported actual ongoing effect"),)
        fields = [
            Field(
                "choices",
                "Printed benefits",
                choices,
                minimum=detail["minimum"],
                maximum=detail["maximum"],
            )
        ]
        if detail["effects"]:
            fields.append(
                Field(
                    "effect",
                    "Only for removal: actual ongoing effect",
                    tuple((x["id"], x["label"]) for x in detail["effects"]),
                    minimum=0,
                    required=False,
                )
            )
    elif detail.get("npc"):
        fields = [
            Field(
                "confirm",
                "Confirm actual received treatment",
                (("confirm", detail["effect"]["label"]),),
            )
        ]
    else:
        fields = []
        if detail["repair"] and detail["assets"]:
            count = min(detail["repair"], len(detail["assets"]))
            fields.append(
                Field(
                    "assets",
                    "Your actual damaged Assets",
                    tuple((x["id"], x["label"]) for x in detail["assets"]),
                    minimum=count,
                    maximum=count,
                )
            )
        if detail["identity"] and detail["identities"]:
            fields.append(
                Field(
                    "identity",
                    "Your actual marked Identity",
                    tuple((x["id"], x["label"]) for x in detail["identities"]),
                    minimum=0,
                    required=False,
                )
            )
        if detail["repair"]:
            fields.extend(replacement_fields(detail["modular"], detail["repair"]))
        if not fields:
            fields = [
                Field("none", "No eligible sheet details", (("none", "No eligible changes exist"),))
            ]

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        if data["kind"] == "doctor_support_response":
            answer = ChoiceAnswer(
                options=tuple(values["decision"]), fields={"bond": values["bond"][0]}
            )
        elif data["kind"] == "doctor_support_refused":
            answer = ChoiceAnswer(
                options=tuple(values["decision"]),
                text=values.get("tag", "") if values["decision"] == ("tag",) else "",
            )
        elif data["kind"] == "doctor_nanobot_benefits":
            answer = ChoiceAnswer(
                options=tuple(values["choices"]),
                fields={"effect": values["effect"][0]} if values.get("effect") else {},
            )
        elif detail.get("npc"):
            answer = ChoiceAnswer(options=tuple(values["confirm"]))
        else:
            chosen = replacements(values)
            answer = ChoiceAnswer(
                options=tuple(values.get("assets", ())),
                fields=({"identity": values["identity"][0]} if values.get("identity") else {})
                | (
                    {"modular": json.dumps([x.model_dump(mode="json") for x in chosen])}
                    if chosen
                    else {}
                ),
            )
        await asyncio.to_thread(
            service.game.respond,
            viewer_from_interaction(current),
            str(current.id),
            identity,
            data["revision"],
            answer,
        )
        return "Actual Doctor response saved. Continue the original pending choices."

    await NativeForm(
        interaction.user.id,
        "DoctorDoctor — your owned response",
        "Select actual existing resources; no locked Identity is unmarked.",
        fields,
        submit,
    ).present(interaction)


async def open_procedure(
    interaction: discord.Interaction, service: DoctorService, data: dict[str, Any], kind: str
) -> None:
    from girlframe.services.m3_doctor_care import CareService
    from girlframe.services.m3_doctor_procedures import ProcedureService
    from girlframe.services.m3_doctor_requisitions import DoctorRequisitionService

    fields = [Field("account", "Describe the actual source action", paragraph=True)]
    if kind == "buy":
        fields.insert(
            0,
            Field(
                "rule",
                "Native Requisition",
                tuple((x["id"], x["label"]) for x in data["acquisitions"]),
            ),
        )
    elif kind in ("nurse", "angel", "ragged"):
        targets = [
            x
            for x in data["nurse_targets" if kind in ("nurse", "angel") else "targets"]
            if x["ref"] != data["actor"]
        ]
        if not targets:
            raise WorkflowError("Join the actual other person to the source scene first")
        fields.insert(
            0,
            Field(
                "target", "Actual other person", tuple((x["token"], x["label"]) for x in targets)
            ),
        )
    elif kind == "wings":
        if not data["wings_assets"] or data["heat"] < 2:
            raise WorkflowError(
                "An actual damaged donor Frame Asset and at least two Heat are required"
            )
        fields[:0] = [
            Field(
                "asset",
                "Damaged donor Frame Asset",
                tuple((x["token"], x["label"]) for x in data["wings_assets"]),
            ),
            Field(
                "heat",
                "Heat (at least 2)",
                tuple((str(x), str(x)) for x in range(2, data["heat"] + 1)),
            ),
        ]
        if data["wings_replacements"]:
            fields.insert(
                1,
                Field(
                    "replace",
                    "Your non-Void Frame Asset to replace at the cap",
                    tuple((x["id"], x["label"]) for x in data["wings_replacements"]),
                ),
            )

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        viewer = viewer_from_interaction(current)
        if kind == "buy":
            await asyncio.to_thread(
                DoctorRequisitionService(service.game).buy,
                viewer,
                str(current.id),
                data["revision"],
                values["rule"][0],
                values["account"],
            )
            return "Actual native Requisition acquired; one Obsolescence box unmarked."
        if kind == "adrenal":
            await asyncio.to_thread(
                ProcedureService(service.game).adrenal,
                viewer,
                str(current.id),
                data["revision"],
                values["account"],
            )
            return "Actual Helplessness ended; Obsolescence marked. Asset damage remains."
        assert interaction.channel_id is not None
        if kind in ("nurse", "angel"):
            target = next(x for x in data["nurse_targets"] if x["token"] == values["target"][0])
            result = await asyncio.to_thread(
                CareService(service.game).propose,
                viewer,
                str(current.id),
                data["revision"],
                interaction.channel_id,
                ActorRef.model_validate(target["ref"]),
                values["account"],
                angel=kind == "angel",
            )
        else:
            item = (
                next(x for x in data["wings_assets"] if x["token"] == values["asset"][0])
                if kind == "wings"
                else next(x for x in data["targets"] if x["token"] == values["target"][0])
            )
            result = await asyncio.to_thread(
                ProcedureService(service.game).propose,
                viewer,
                str(current.id),
                data["revision"],
                interaction.channel_id,
                ActorRef.model_validate(item["ref"]),
                kind,
                values["account"],
                asset=item["id"] if kind == "wings" else None,
                heat=int(values["heat"][0]) if kind == "wings" else 0,
                replace=values["replace"][0] if values.get("replace") else None,
            )
        return (
            "Actual owned request saved. The original participants can reopen it in the Inbox: "
            + str(result["id"])
        )

    await NativeForm(
        interaction.user.id,
        "DoctorDoctor — " + kind,
        "Declare only the performed source action. Other people's owned responses remain theirs.",
        fields,
        submit,
    ).present(interaction)


async def open_care(
    interaction: discord.Interaction, service: DoctorService, identity: str
) -> None:
    from girlframe.services.m3_doctor_care import CareService

    care = CareService(service.game)
    data = await asyncio.to_thread(care.get, viewer_from_interaction(interaction), identity)
    if not data["can_confirm"] and data["care"]["phase"] != "recovery":
        await reply(interaction, "Actual care state: " + data["care"]["phase"])
        return

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        operation = care.recover if data["care"]["phase"] == "recovery" else care.confirm
        await asyncio.to_thread(
            operation,
            viewer_from_interaction(current),
            str(current.id),
            identity,
            data["revision"],
            values["account"],
        )
        return "Your actual source-owned care confirmation is saved."

    await NativeForm(
        interaction.user.id,
        "Actual Doctor care",
        data["care"]["account"],
        [Field("account", "Confirm the actual care you received/provided", paragraph=True)],
        submit,
    ).present(interaction)


async def open_request(
    interaction: discord.Interaction, service: DoctorService, identity: str
) -> None:
    from girlframe.services.m3_doctor_procedures import ProcedureService

    source = ProcedureService(service.game)
    data = await asyncio.to_thread(source.get, viewer_from_interaction(interaction), identity)
    if not data["can_confirm"]:
        await reply(interaction, "Waiting for the original source-owned response.")
        return
    fields = [Field("account", "Confirm the actual tearing / call and arrival", paragraph=True)]
    if data["procedure"]["kind"] == "ragged":
        if not data["tags"]:
            raise WorkflowError("An actual participant must mark their own unmarked Tag")
        fields.insert(
            0,
            Field(
                "tag", "Your actual Tag to mark", tuple((x["id"], x["label"]) for x in data["tags"])
            ),
        )

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        if data["procedure"]["kind"] == "protection":
            await asyncio.to_thread(
                source.stop_protecting,
                viewer_from_interaction(current),
                str(current.id),
                identity,
                data["revision"],
                values["account"],
            )
            return "Actual protection has ended."
        await asyncio.to_thread(
            source.confirm,
            viewer_from_interaction(current),
            str(current.id),
            identity,
            data["revision"],
            values["account"],
            values["tag"][0] if values.get("tag") else None,
        )
        return "Actual source action completed."

    await NativeForm(
        interaction.user.id,
        "DoctorDoctor — actual " + data["procedure"]["kind"],
        data["procedure"]["account"],
        fields,
        submit,
    ).present(interaction)
