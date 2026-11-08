"""Handler-owned Strain selectors; no rolling on open and no effect-waiver buttons."""

import asyncio
from typing import Any, cast

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.m3_off_duty import open_period
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine.m3_strain import PAGES, StartFacts
from girlframe.engine.m3_strain_catalog import ENDGAMES, ROWS
from girlframe.services.m3_strain import StrainService
from girlframe.services.onboarding import WorkflowError

FACT_LABELS = {
    "harpy_or_prevented_since_last": "Since last Off-Duty: Girl became/nearly became a Harpy?",
    "all_gorgons_dormant_or_benevolent": "Are all current Gorgons Dormant or Benevolent?",
    "girl_leaked_information": "Did a Girl leak Foundation information?",
    "girl_attempted_handler_kill_escape_or_rebel_capture": (
        "Girl tried to kill Handler, escape, or was rebel-captured?"
    ),
    "rebel_handler_killed": "Was a rebel Handler killed?",
    "rebel_pilot_captured_and_broken": "Was a rebel Pilot captured and broken?",
    "structure_destroyed": "Was a city, base or major structure destroyed?",
    "girl_death_or_severe": ("Any non-exempt Girl deaths or independent Severe Punishments?"),
    "frame_full_or_all_frames_some_repairs": (
        "Did one Frame need full repairs, or every Frame some repair?"
    ),
    "last_mission_success_no_frame_death_infrastructure_loss": (
        "Last mission successful without Frame, life or major structure loss?"
    ),
    "budget_contributor_moderately_punished": "Was a budget-contributing Girl Moderately Punished?",
}


async def open_strain(interaction: discord.Interaction, service: StrainService) -> None:
    viewer = viewer_from_interaction(interaction)
    data = await asyncio.to_thread(service.get, viewer)
    if data["strain"] is not None:
        await open_period(interaction, service.periods)
        return

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        await asyncio.to_thread(
            service.configure,
            viewer_from_interaction(current),
            str(current.id),
            data["game_revision"],
            cast(Any, values["scenario"][0]),
            frozenset(cast(Any, values.get("high", ()))),
        )
        return "Starting Strain recorded. Open /mission off_duty to start or resume preparation."

    form = NativeForm(
        viewer.user_id,
        "Choose the starting Strain scenario",
        "Choose the printed scenario and its exact number of High tracks. "
        "This initializes Strain once; it does not roll any dice.",
        [
            Field(
                "scenario",
                "Starting situation",
                (
                    ("business_as_usual", "Business As Usual — 0 High"),
                    ("disaster_management", "Disaster Management — 1 High"),
                    ("barely_hanging_on", "Barely Hanging On — 2 High"),
                    ("falling_apart", "Everything's Falling Apart — 3 High"),
                ),
            ),
            Field(
                "high",
                "Which tracks start High?",
                (("void", "Void"), ("rebellion", "Rebellion"), ("budget", "Budget")),
                0,
                3,
                required=False,
            ),
        ],
        submit,
    )
    await reply(interaction, form.text(), form)


async def open_work(
    interaction: discord.Interaction, service: StrainService, identity: str
) -> None:
    viewer = viewer_from_interaction(interaction)
    data = await asyncio.to_thread(service.work, viewer, identity)
    body, kind = data["body"], data["kind"]
    if data["state"] != "pending":
        await reply(
            interaction,
            "This selection is saved. Reopen /mission off_duty for actual remaining effects.",
        )
        return
    if kind == "off_duty_strain_start":
        if not data["initialized"]:
            await reply(interaction, "Choose the initial scenario with /mission strain first.")
            return
        if body.get("stage") == "pending_effects":
            await reply(
                interaction,
                "Start triggers are recorded. Finish saved Strain dice/column choices "
                "and their actual mechanical effects through /mission off_duty. "
                "This gate cannot be acknowledged away.",
            )
            return
        fields = [
            Field(key, label, (("yes", "Yes"), ("no", "No"))) for key, label in FACT_LABELS.items()
        ]
        fields.append(Field("account", "Factual trigger review", paragraph=True))
        instructions = (
            "Review events since the last Off-Duty. Answer every question explicitly. "
            "Current Void Assets are checked automatically against canon. "
            "This queues three actual d6 rolls; it does not select their columns."
        )

        exemptions = data.get("budget_death_exemptions", ())
        if exemptions:
            instructions += (
                " Proved source exemptions apply only to these actual deaths: "
                + "; ".join(str(value["label"]) for value in exemptions)
                + ". Independent Severe Punishments and other Budget causes still count."
            )

        async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
            if not set(FACT_LABELS) <= set(values):
                raise WorkflowError(
                    "Answer every factual trigger question before preparing Strain."
                )
            if any(values[key] not in (("yes",), ("no",)) for key in FACT_LABELS):
                raise WorkflowError("Choose an explicit Yes or No for each factual trigger.")
            facts = StartFacts(
                **data["canonical_facts"],
                **{key: values[key][0] == "yes" for key in FACT_LABELS},
                account=values["account"],
            )
            await asyncio.to_thread(
                service.prepare,
                viewer_from_interaction(current),
                str(current.id),
                data["off_duty_id"],
                data["period_revision"],
                data["game_revision"],
                facts,
            )
            return (
                "Start review saved. Reopen /mission off_duty for the three pending Strain rolls."
            )
    elif kind == "strain_roll" and body.get("stage") == "die":
        fields = [
            Field("confirm", "Roll this pending die", (("roll", "Roll once and save the result"),))
        ]
        instructions = (
            f"{body['track'].title()} — {body['severity'].title()} table. "
            "No roll happens until you confirm. Reopening retains the saved result."
        )

        async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
            result = await asyncio.to_thread(
                service.roll,
                viewer_from_interaction(current),
                str(current.id),
                identity,
                data["revision"],
                data["game_revision"],
            )
            return (
                f"Saved d6: {result['face']}. Reopen /mission off_duty "
                "to choose either event column."
            )
    elif kind == "strain_roll" and body.get("stage") == "column":
        row = ROWS[(body["track"], body["severity"])][body["face"] - 1]
        fields = [
            Field(
                "option",
                "Choose the actual event column",
                tuple((str(i), label) for i, label in enumerate(row, 1)),
            )
        ]
        instructions = (
            f"Saved d6: {body['face']} — {body['track'].title()} {body['severity']}. "
            f"Book PDF {PAGES[(body['track'], body['severity'])]}. "
            "These short summaries select an event; its complete effects remain required work."
        )

        async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
            await asyncio.to_thread(
                service.choose,
                viewer_from_interaction(current),
                str(current.id),
                identity,
                data["revision"],
                data["game_revision"],
                int(values["option"][0]),
            )
            return "Event column saved. Its effects and any recursive rolls remain required work."
    elif kind == "strain_endgame":
        options = tuple((str(i), ENDGAMES[body["track"]][i - 1]) for i in data["endgame_options"])
        if not options:
            await reply(
                interaction,
                "No unused enabled Endgame remains. This source question needs "
                "an explicit recorded policy revision; no reroll or substitute was made.",
            )
            return
        fields = [Field("option", "Choose an unused Endgame", options)]
        if body["track"] == "rebellion":
            if not data["rebel_groups"]:
                await reply(
                    interaction, "Introduce an actual active Rebel Group, then reopen this Endgame."
                )
                return
            fields.append(
                Field(
                    "faction",
                    "Actual active Rebel Group",
                    tuple((x["id"], x["label"]) for x in data["rebel_groups"]),
                )
            )
        instructions = (
            "Choose a previously unused slot. Ancillary is disabled. "
            "Actual Endgame effects remain required work."
        )

        async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
            await asyncio.to_thread(
                service.choose,
                viewer_from_interaction(current),
                str(current.id),
                identity,
                data["revision"],
                data["game_revision"],
                int(values["option"][0]),
                endgame=True,
                faction=values["faction"][0] if body["track"] == "rebellion" else None,
            )
            return "Endgame selected once. Resolve its actual effects before advancing."
    else:
        raise WorkflowError("Resume this task through its specific supported resolver.")
    form = NativeForm(viewer.user_id, "Strain preparation", instructions, fields, submit)
    await reply(interaction, form.text(), form)
