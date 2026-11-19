"""Owner-bound scene roles; joining never claims travel, consent or piloting."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.ledger import clean
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.m3_actors import LABELS
from girlframe.discord_adapter.m3_punishments import Picker
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.services.m3_cast import CastService
from girlframe.services.onboarding import WorkflowError


async def open_cast(interaction: discord.Interaction, service: CastService) -> None:
    viewer, channel = viewer_from_interaction(interaction), interaction.channel_id
    if channel is None:
        await reply(interaction, "Open scene roles in its bound server channel.")
        return
    data = await asyncio.to_thread(service.view, viewer, channel)
    owned = await asyncio.to_thread(service.actors.choices, viewer)
    own_cast = {x["token"]: x for x in data["roles"] if x.get("own")}
    options: list[tuple[str, str]] = []
    actions: dict[str, tuple[str, ActorRef | None]] = {}
    prompt_roles = {}
    for role in owned["actors"]:
        if role["token"] not in own_cast:
            token = "join:" + role["token"]
            options.append(
                (token, "Join as " + role["label"][:60] + " (" + LABELS[role["kind"]] + ")")
            )
            actions[token] = ("join", ActorRef.model_validate(role["ref"]))
    for token, role in own_cast.items():
        key = "withdraw:" + token
        options.append((key, "Withdraw " + role["label"][:75]))
        actions[key] = ("withdraw", ActorRef.model_validate(role["ref"]))
        if role.get("job_prompts"):
            prompt_key = "prompts:" + token
            options.append((prompt_key, "Review job prompts for " + role["label"][:65]))
            prompt_roles[prompt_key] = token
    if data["may_facilitate"] and not data["own_facilitator"]:
        options.append(("facilitate", "Join as facilitator (no fictional character)"))
        actions["facilitate"] = ("facilitate", None)
    if data["own_facilitator"]:
        options.append(("withdraw_facilitator", "Stop facilitating this scene"))
        actions["withdraw_facilitator"] = ("withdraw_facilitator", None)
    for role in data["adjudicator_options"]:
        key = "adjudicate:" + role["token"]
        options.append((key, "Offer " + role["label"][:55] + " for Handler-rule responses"))
        actions[key] = ("adjudicate", ActorRef.model_validate(role["ref"]))

    async def prompt_role(current: discord.Interaction, key: str) -> dict[str, Any]:
        roles: list[dict[str, Any]] = (
            await asyncio.to_thread(service.view, viewer_from_interaction(current), channel)
        )["roles"]
        role = next(
            (x for x in roles if x["token"] == prompt_roles[key] and x.get("job_prompts")), None
        )
        if role is None:
            raise WorkflowError("Reopen your current original NPC role.")
        return role

    async def choose(current: discord.Interaction, token: str) -> None:
        if token in prompt_roles:
            role = await prompt_role(current, token)

            async def show_job(click: discord.Interaction, job: str) -> None:
                latest = await prompt_role(click, token)
                prompts = latest["job_prompts"].get(job)
                if not prompts:
                    raise WorkflowError("Reopen the original NPC's current jobs.")
                await reply(
                    click,
                    "**"
                    + clean(latest["label"])
                    + " · "
                    + job.replace("_", " ").title()
                    + "**\n"
                    + "\n".join("• " + prompt for prompt in prompts)
                    + "\nUse the scene's normal authority to resolve any effects.",
                )

            jobs = tuple((job, job.replace("_", " ").title()) for job in role["job_prompts"])
            if len(jobs) == 1:
                await show_job(current, jobs[0][0])
            else:
                await Picker(
                    viewer.user_id, "Choose one of this NPC's current jobs.", jobs, show_job
                ).show(current)
            return
        action, ref = actions[token]

        async def submit(actor: discord.Interaction, values: dict[str, Any]) -> str:
            await asyncio.to_thread(
                service.change,
                viewer_from_interaction(actor),
                str(actor.id),
                channel,
                data["game_revision"],
                data["cast_revision"],
                action,
                ref,
            )
            return "Your scene role is saved. Reopen /mission cast to review it."

        form = NativeForm(
            viewer.user_id,
            "Confirm scene role",
            dict(options)[token] + ". This records who you control in the scene. "
            "Fictional location, piloting and consent need their own rules.",
            [Field("confirm", "Confirm", (("yes", "Save this scene role"),))],
            submit,
        )
        await reply(current, form.text(), form)

    text = "**Scene roles**\n" + "\n".join(x["label"] for x in data["roles"])
    text += "\nFacilitating and playing the Handler are separate roles."
    if data["adjudicator_selected"]:
        text += "\nA Director is selected for Handler-rule responses."
    if not options:
        await reply(interaction, text[:1800])
        return
    await Picker(viewer.user_id, text[:1600], tuple(options), choose).show(interaction)
