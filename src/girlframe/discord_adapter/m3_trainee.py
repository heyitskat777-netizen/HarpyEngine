"""Human-authored actual teachings, original-role choices and saved discipline."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.services.m3_trainee import TraineeService


async def open_trainee(
    interaction: discord.Interaction, service: TraineeService, identity: str | None = None
) -> None:
    viewer = viewer_from_interaction(interaction)
    if identity is None:
        channel = int(interaction.channel_id or 0)
        data = await asyncio.to_thread(service.menu, viewer, channel)
        options = [("teaching", "Record an actual teaching by your original Mentor")]
        if not data["can_teach"]:
            options = []
        options.extend((x["id"], x["label"]) for x in data["history"])
        if not options:
            await reply(interaction, "No current original-Mentor teaching or saved source here.")
            return

        async def choose(current: discord.Interaction, values: dict[str, Any]) -> str | None:
            if values["source"][0] != "teaching":
                await open_trainee(current, service, values["source"][0])
                return None

            async def submit(response: discord.Interaction, answer: dict[str, Any]) -> str:
                result = await asyncio.to_thread(
                    service.record_teaching,
                    viewer_from_interaction(response),
                    str(response.id),
                    channel,
                    data["revision"],
                    answer["account"],
                )
                return "Actual teaching saved. Open its source to make your Trainee choice: " + str(
                    result["id"]
                )

            form = NativeForm(
                current.user.id,
                "Actual Mentor teaching",
                "Describe the actual teaching by your original Mentor, intentional or incidental. "
                "Do not invent their speech or import private notes. This does not roll dice.",
                [Field("account", "Actual teaching and factual scene context", paragraph=True)],
                submit,
            )
            await reply(current, form.text(), form)
            return None

        form = NativeForm(
            viewer.user_id,
            "Trainee",
            "Your original-person teachings and outcomes.",
            [Field("source", "Actual source", tuple(options))],
            choose,
        )
        await reply(interaction, form.text(), form)
        return
    data = await asyncio.to_thread(service.view, viewer, identity)
    summary = (
        ("Actual teaching: " + data["teaching"] + ". ")
        if data["teaching"]
        else "Mentor duty report. "
    )
    summary += "Phase: " + data["phase"] + "."
    if data["selected_account"]:
        summary += " Your actual chosen response: " + data["selected_account"] + "."
    if data["identity"]:
        summary += " Your erased Identity: " + data["identity"] + "."
    if data["embraced"]:
        summary += " Your embraced Mentor Tag: " + data["embraced"] + "."
    if data["heat"]:
        summary += " Your actual Heat gained: " + str(data["heat"]) + "."
    if data["report"]:
        summary += " Actual reported shirking: " + data["report"] + "."
    if data["review"]:
        summary += " Source-attributed Handler finding: " + data["review"] + "."
    if (
        data["case"]
        and data["actionable"]
        and data["phase"] in ("mentor_punishment", "handler_punishment")
    ):
        from girlframe.discord_adapter.m3_role_punishments import open_role_punishment
        from girlframe.services.m3_role_punishments import RolePunishmentService

        await open_role_punishment(interaction, RolePunishmentService(service.game), data["case"])
        return
    options = []
    if data["phase"] == "choice" and data["actionable"]:
        if data["identities"]:
            options.append(
                ("erase", "Erase a contradictory Identity; embrace an existing Mentor Tag")
            )
        options.extend(
            (
                ("act", "Actually act immediately on the teaching; gain1–3 Heat"),
                ("challenge", "Actually challenge or insult; Mentor owes immediate Punishment"),
            )
        )
    if data["phase"] == "mentor" and data["actionable"]:
        options.append(("punish", "Administer your actual immediate Mentor Punishment"))
    if data["can_report"]:
        options.append(("report", "Report actual shirking to the original Handler"))
    if data["phase"] == "reported" and data["actionable"]:
        options.append(
            ("review", "Confirm actual source-attributed shirking; Punish Mentor instead")
        )
    if not options:
        await reply(interaction, summary)
        return

    async def select(current: discord.Interaction, values: dict[str, Any]) -> str | None:
        operation = values["operation"][0]
        if operation == "punish":
            result = await asyncio.to_thread(
                service.punish,
                viewer_from_interaction(current),
                str(current.id),
                identity,
                data["revision"],
            )
            from girlframe.discord_adapter.m3_role_punishments import open_role_punishment
            from girlframe.services.m3_role_punishments import RolePunishmentService

            await open_role_punishment(current, RolePunishmentService(service.game), result["case"])
            return None
        fields = []
        if operation == "erase":
            fields.append(
                Field(
                    "identity",
                    "Your actual contradictory Identity",
                    tuple((x["id"], x["name"]) for x in data["identities"]),
                )
            )
            if data["tags"]:
                fields.append(
                    Field(
                        "tag",
                        "Actual original-Mentor Tag you must embrace",
                        tuple((x["id"], x["label"]) for x in data["tags"]),
                    )
                )
        if operation == "act":
            fields.append(
                Field("heat", "Printed actual Heat gained", (("1", "1"), ("2", "2"), ("3", "3")))
            )
            if data["actions"]:
                fields.append(
                    Field(
                        "action",
                        "Actual completed mechanical Play, if applicable",
                        tuple((x["id"], x["label"]) for x in data["actions"]),
                        minimum=0,
                        required=False,
                    )
                )
        fields.append(
            Field(
                "account",
                {
                    "erase": "Explain the actual contradiction with this teaching",
                    "act": "Actual performed action; no unperformed mechanical outcomes",
                    "challenge": "Your actual challenge or insult",
                    "report": "Actual source-attributed shirking you report to Handler",
                    "review": "Your truthful factual finding; preserve original people and source",
                }[operation],
                paragraph=True,
            )
        )

        async def submit(response: discord.Interaction, answer: dict[str, Any]) -> str:
            actual = viewer_from_interaction(response)
            if operation == "report":
                await asyncio.to_thread(
                    service.report_shirking,
                    actual,
                    str(response.id),
                    identity,
                    data["revision"],
                    answer["account"],
                )
            elif operation == "review":
                await asyncio.to_thread(
                    service.resolve_report,
                    actual,
                    str(response.id),
                    identity,
                    data["revision"],
                    answer["account"],
                )
            else:
                await asyncio.to_thread(
                    service.choose,
                    actual,
                    str(response.id),
                    identity,
                    data["revision"],
                    operation,
                    identity_id=(answer.get("identity") or (None,))[0],
                    tag=(answer.get("tag") or (None,))[0],
                    heat=int((answer.get("heat") or ("0",))[0]),
                    account=answer["account"],
                    source_action=(answer.get("action") or (None,))[0],
                )
            return (
                "Your actual outcome is saved. Pending discipline keeps its real source controls."
            )

        form = NativeForm(
            current.user.id,
            "Your actual Trainee response",
            "Actual performed fiction only. Mechanical actions require their completed source. "
            "No fabricated speech/consent or free resource effects. OOC pause remains available.",
            fields,
            submit,
        )
        await reply(current, form.text(), form)
        return None

    form = NativeForm(
        viewer.user_id,
        "Your saved Trainee source",
        summary,
        [Field("operation", "Your actual owned response", tuple(options))],
        select,
    )
    await reply(interaction, form.text(), form)
