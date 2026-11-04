"""Private native Off-Duty preparation and owned credit declarations."""

import asyncio
from typing import Any, cast

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.m3_punishments import Picker
from girlframe.discord_adapter.onboarding import reply
from girlframe.services.m3_off_duty import OffDutyService


async def open_credit(
    interaction: discord.Interaction, service: OffDutyService, identity: str
) -> None:
    viewer = viewer_from_interaction(interaction)
    data = await asyncio.to_thread(service.credit_review, viewer, identity)
    if data["state"] != "pending":
        await reply(interaction, "This credit declaration is already saved.")
        return

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        selected = values["recipient"][0]
        await asyncio.to_thread(
            service.credit,
            viewer_from_interaction(current),
            str(current.id),
            data["period_id"],
            data["period_revision"],
            data["game_revision"],
            None if selected == "none" else int(selected),
            values["account"],
        )
        return (
            "Credit declaration saved once. Reopen /mission off_duty "
            "or your requests for pending work."
        )

    form = NativeForm(
        viewer.user_id,
        "DoctorDoctor — credit sharing",
        "Record whether you gave another Pilot credit for your deed. "
        "Selecting a recipient grants them 1 Permission on confirmation; "
        "offline Pilots remain eligible. No one answers on your behalf.",
        [
            Field(
                "recipient",
                "Who received credit?",
                (("none", "No credit-sharing trigger"),) + tuple(data["recipients"]),
            ),
            Field("account", "Brief factual account", paragraph=True),
        ],
        submit,
    )
    await reply(interaction, form.text(), form)


async def open_period(interaction: discord.Interaction, service: OffDutyService) -> None:
    viewer = viewer_from_interaction(interaction)
    data = await asyncio.to_thread(service.current, viewer)
    if data is None:
        with service.store.engine.connect() as c:
            service.missions._handler(c, viewer)

        async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
            await asyncio.to_thread(
                service.begin, viewer_from_interaction(current), str(current.id)
            )
            return "Off-Duty preparation saved. Reopen /mission off_duty for required work."

        form = NativeForm(
            viewer.user_id,
            "Begin Off-Duty preparation",
            "Start a saved period for the canonical Cadre. Strain, scenes, recovery "
            "and required consequences remain explicit work before the period can end.",
            [Field("confirm", "Confirm period start", (("begin", "Begin preparation"),))],
            submit,
        )
        await reply(interaction, form.text(), form)
        return
    rows = {row["id"]: row for row in data["work"]}
    if not rows:
        await reply(
            interaction,
            f"Off-Duty is {data['phase']}; {data['pending_count']} required items remain. "
            "Your own items appear in /character requests. Nothing advances automatically.",
        )
        return

    async def choose(current: discord.Interaction, identity: str) -> None:
        row = rows[identity]
        if row["kind"] == "doctor_credit":
            await open_credit(current, service, identity)
        elif row["kind"] in ("off_duty_strain_start", "strain_roll", "strain_endgame"):
            from girlframe.discord_adapter.m3_strain import open_work
            from girlframe.services.m3_strain import StrainService

            await open_work(current, StrainService(service), identity)
        elif row["kind"] in (
            "doctor_frame_replacement",
            "frame_replacement_package",
            "frame_replacement_court",
        ):
            from girlframe.discord_adapter.m3_replacement import open_replacement
            from girlframe.services.m3_replacement import ReplacementService

            await open_replacement(current, ReplacementService(service.missions), identity)
        elif row["kind"] == "strain_event":
            from girlframe.discord_adapter.m3_strain_effects import open_effect
            from girlframe.services.m3_strain import StrainService
            from girlframe.services.m3_strain_effects import EffectService

            await open_effect(current, EffectService(StrainService(service)), identity)
        else:
            await reply(
                current,
                "This effect is awaiting rules support. "
                "It remains required; this menu cannot finish it or end Off-Duty.",
            )

    view = Picker(
        viewer.user_id,
        f"**Off-Duty — {data['phase']}**\n"
        f"{data['pending_count']} required items remain. Choose your own saved work.",
        tuple(
            (identity, cast(str, row["kind"]).replace("_", " ").title())
            for identity, row in rows.items()
        ),
        choose,
    )
    await view.show(interaction)
