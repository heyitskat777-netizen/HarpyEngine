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
    from girlframe.services.m3_off_duty_cycle import CycleService

    cycle = CycleService(service)
    progress = await asyncio.to_thread(cycle.review, viewer, data["id"])
    actions: list[tuple[str, str]] = []
    if viewer.user_id == progress["handler"] and data["phase"] != "complete":
        actions.append(("observation_order", "Place a Girl under Void Observation"))
        actions.append(("observation_hiding", "Review attempts to hide Void changes"))
    if progress["rewards_need_refresh"]:
        actions.append(("refresh_rewards", "Refresh current Frame bonus tasks"))
    if data["phase"] == "preparing" and viewer.user_id == progress["handler"]:
        actions.append(("activate", "Finish preparation and begin Off-Duty"))
    elif data["phase"] == "active":
        own = progress["own"]
        if progress["sheet"] is not None and not (own and own["recovered"]):
            if own is None or own["roll"] is None:
                actions.append(
                    (
                        "play",
                        "Void Observation / resume your saved Play"
                        if own and own.get("observation")
                        else "Go Off-Duty / resume your saved Play",
                    )
                )
            elif own["roll"]["stage"] == "tag_window":
                actions.append(("play", "Resume your roll's Tag decisions"))
            elif own["scene"] is None and not own["scene_declined"]:
                actions.append(("scene", "Choose your Off-Duty scene"))
            else:
                actions.append(("recover", "Review your sheet recovery"))
        for scene in progress["invitations"]:
            if viewer.user_id not in scene["acknowledgements"]:
                actions.append(
                    (
                        "ack:" + str(scene["owner"]),
                        "Confirm your participation in an Off-Duty scene",
                    )
                )
        scene = progress["handler_scene"]
        if scene is not None and viewer.user_id not in scene["acknowledgements"]:
            actions.append(("ack:handler", "Confirm your participation in the Handler scene"))
        if viewer.user_id == progress["handler"]:
            if scene is None:
                actions.append(("handler_scene", "Set your Handler Off-Duty scene"))
            if not progress["status_reviewed"]:
                actions.append(("status", "Review the Cadre's Status"))
            else:
                actions.append(("finish", "Review world effects and end Off-Duty"))
    if not rows and not actions:
        await reply(
            interaction,
            f"Off-Duty is {data['phase']}; {data['pending_count']} required items remain. "
            "Your own items appear in /character requests. Nothing advances automatically.",
        )
        return

    async def choose(current: discord.Interaction, identity: str) -> None:
        if identity.startswith("action:"):
            if identity in ("action:observation_order", "action:observation_hiding"):
                from girlframe.discord_adapter.m3_observation import open_order
                from girlframe.services.m3_observation import ObservationService

                await open_order(
                    current,
                    ObservationService(service),
                    data["id"],
                    review=identity.endswith("observation_hiding"),
                )
                return
            from girlframe.discord_adapter.m3_off_duty_cycle import open_action

            await open_action(current, cycle, data["id"], identity.removeprefix("action:"))
            return
        row = rows[identity]
        if row["kind"] == "director_presence":
            from girlframe.discord_adapter.m3_director import open_review as open_director
            from girlframe.services.m3_director import DirectorService

            await open_director(current, DirectorService(service.missions), identity)
        elif row["kind"] in ("observation_choice", "observation_effect"):
            from girlframe.discord_adapter.m3_observation import open_work as open_observation
            from girlframe.services.m3_observation import ObservationService

            await open_observation(current, ObservationService(service), identity)
        elif row["kind"] in (
            "frame_off_duty_reward",
            "frame_reward_court",
            "frame_reward_interest",
        ):
            from girlframe.discord_adapter.m3_frame_rewards import open_reward
            from girlframe.services.m3_frame_rewards import RewardService

            await open_reward(current, RewardService(service), identity)
        elif row["kind"] in (
            "punishment",
            "punishment_consult",
            "punishment_paired_identity_heat",
            "punishment_helpless",
        ):
            from girlframe.discord_adapter.m3_punishments import open_discipline
            from girlframe.services.m3_punishments import PunishmentService

            await open_discipline(current, PunishmentService(service.store), identity)
        elif row["kind"] == "doctor_credit":
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
        elif row["kind"] == "strain_endgame_effect":
            from girlframe.services.m3_strain import StrainService

            saved = await asyncio.to_thread(
                StrainService(service).work, viewer_from_interaction(current), identity
            )
            if saved["body"]["rule_id"] == "strain.rebellion.endgame.1":
                from girlframe.discord_adapter.m3_rebel_leader import open_leader
                from girlframe.services.m3_rebel_leader import LeaderService

                await open_leader(current, LeaderService(service.store), identity)
            elif saved["body"]["rule_id"] == "strain.rebellion.endgame.2":
                from girlframe.discord_adapter.m3_rebel_merge import open_merger
                from girlframe.services.m3_rebel_merge import MergerService

                await open_merger(current, MergerService(service.store), identity)
            else:
                await reply(
                    current,
                    "Review this Endgame in /character requests. "
                    "Its actual effects remain required.",
                )
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
        tuple(("action:" + key, label) for key, label in actions)
        + tuple(
            (identity, cast(str, row["kind"]).replace("_", " ").title())
            for identity, row in rows.items()
        ),
        choose,
    )
    await view.show(interaction)
