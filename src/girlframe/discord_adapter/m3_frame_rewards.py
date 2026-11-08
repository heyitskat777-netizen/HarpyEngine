"""Private source-specific Frame reward selectors, signed by the actual decision owner."""

import asyncio
import json
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field
from girlframe.discord_adapter.m3_strain_effects import WAIT, DependentForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine.fanbase import Fanbase
from girlframe.engine.m3_frame_rewards import Claim
from girlframe.services.m3_frame_rewards import RewardService
from girlframe.services.onboarding import WorkflowError


def one(values: dict[str, Any], key: str) -> str | None:
    return next(iter(values.get(key, ())), None)


async def open_reward(
    interaction: discord.Interaction, service: RewardService, identity: str
) -> None:
    viewer = viewer_from_interaction(interaction)
    data = await asyncio.to_thread(service.get, viewer, identity)
    if data["state"] == "resolved":
        await reply(interaction, "This Frame reward review is already saved.")
        return
    if data["state"] == "awaiting_interest":
        await reply(
            interaction,
            "Your offering is saved. The Handler must record their own interest decision; "
            "no bonus is granted yet.",
        )
        return
    if data["owner_id"] != str(viewer.user_id):
        if data["mode"] == "interest":
            await reply(interaction, "Waiting for the Handler's own interest decision.")
            return
        await reply(
            interaction,
            "The Queen holder recorded for this Off-Duty Play makes this saved choice. "
            "Their response stays pending.",
        )
        return
    if data.get("issue"):
        await reply(interaction, data["issue"])
        return
    if not data["ready"]:
        await reply(
            interaction,
            "Complete the actual Go Off-Duty Play and Tag choices first. "
            "This review stays saved; no response is supplied for you.",
        )
        return
    frame, mode = data["frame"], data["mode"]
    instructions = (
        "Review the condition for this Off-Duty Play, then confirm your own factual "
        "declaration. A saved review cannot grant the same bonus twice."
    )
    if mode == "interest":
        instructions = (
            "Offering: "
            + data["offering"]
            + "\nAccount: "
            + data["account"]
            + "\nOnly you record whether you found it interesting."
        )
    elif frame == "WYVERN 0.4":
        instructions += (
            " A qualifying offering is sent to your Handler for their own interest decision."
        )
    if frame == "THE PRINCE" and data.get("fanbase"):
        fans = Fanbase.model_validate_json(json.dumps(data["fanbase"]))
        instructions += "\nDemanded: " + ", ".join(fans.label(x) for x in fans.demanded)
        instructions += "\nRejected: " + ", ".join(fans.label(x) for x in fans.rejected)

    def build(values: dict[str, Any]) -> list[Field]:
        if mode == "interest":
            return [
                Field(
                    "interest",
                    "Did you find this offering interesting?",
                    (("yes", "Yes — this qualifies"), ("no", "No — this does not qualify")),
                )
            ]
        if mode == "queen":
            return [
                Field("recipient", "Who served your purposes best?", data["pilots"] or WAIT),
                Field("account", "Your own reason for the award", paragraph=True),
            ]
        fields = [
            Field(
                "fulfilled",
                {
                    "THE PRINCE": "Did you follow your Fanbase's demands?",
                    "CONSUME": "Did you bring back a prisoner for your Handler?",
                    "JANUS": "Did you demonstrate your Core was harmless?",
                    "WYVERN 0.4": "Did you bring your Handler something interesting?",
                    "THE ENFORCER": "Did you bring Rebel custody or disobedience evidence?",
                    "CHANGELING": "Did your adjustments lead to another Girl's good behaviour?",
                    "PROJECT ANKOU": "Did you successfully minimize civilian casualties?",
                }[frame],
                (("yes", "The qualifying event occurred"), ("no", "This trigger did not occur")),
            )
        ]
        if one(values, "fulfilled") == "yes":
            if frame in ("CONSUME", "THE ENFORCER"):
                if frame == "THE ENFORCER":
                    fields.append(
                        Field(
                            "route",
                            "Which printed condition?",
                            (
                                ("prisoner", "A Rebel prisoner"),
                                ("evidence", "Cadremate disobedience evidence"),
                            ),
                        )
                    )
                if frame == "CONSUME" or one(values, "route") == "prisoner":
                    fields.append(
                        Field("prisoner", "Actual delivered prisoner", data["prisoners"] or WAIT)
                    )
                elif one(values, "route") == "evidence":
                    fields.append(Field("evidence", "Describe the actual evidence", paragraph=True))
            elif frame == "JANUS":
                fields.append(Field("official", "Who saw the demonstration?", data["officials"]))
            elif frame == "WYVERN 0.4":
                fields.append(Field("offering", "What did you bring your Handler?", paragraph=True))
            elif frame == "CHANGELING":
                fields.append(
                    Field(
                        "influenced",
                        "Which other Girl?",
                        tuple(x for x in data["pilots"] if x[0] != data["subject_id"]) or WAIT,
                    )
                )
        fields.append(Field("account", "Brief actual trigger / no-trigger account", paragraph=True))
        return fields

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        if mode == "interest":
            if one(values, "interest") not in ("yes", "no"):
                raise WorkflowError("Choose your own explicit Yes or No response.")
            result = await asyncio.to_thread(
                service.answer_interest,
                viewer_from_interaction(current),
                str(current.id),
                identity,
                data["revision"],
                data["game_revision"],
                one(values, "interest") == "yes",
            )
        elif mode == "queen":
            result = await asyncio.to_thread(
                service.apply,
                viewer_from_interaction(current),
                str(current.id),
                identity,
                data["revision"],
                data["game_revision"],
                None,
                int(one(values, "recipient") or "0"),
                values["account"],
            )
        else:
            if one(values, "fulfilled") not in ("yes", "no"):
                raise WorkflowError("Choose an explicit trigger or no-trigger response.")
            fulfilled = one(values, "fulfilled") == "yes"
            details: dict[str, Any] = {}
            if fulfilled:
                if (
                    frame == "CONSUME"
                    or frame == "THE ENFORCER"
                    and one(values, "route") == "prisoner"
                ):
                    details["prisoner"] = one(values, "prisoner")
                elif frame == "THE ENFORCER":
                    details["evidence"] = values.get("evidence", "")
                elif frame == "JANUS":
                    details["official"] = one(values, "official")
                elif frame == "WYVERN 0.4":
                    details["offering"] = values.get("offering", "")
                elif frame == "CHANGELING":
                    details["influenced_pilot"] = int(one(values, "influenced") or "0")
            result = await asyncio.to_thread(
                service.apply,
                viewer_from_interaction(current),
                str(current.id),
                identity,
                data["revision"],
                data["game_revision"],
                Claim(fulfilled=fulfilled, account=values["account"], **details),
            )
        if result["state"] == "awaiting_interest":
            return (
                "Offering saved for the Handler's own interest decision. "
                "No bonus has been granted yet."
            )
        return (
            "Frame reward saved: +1 Permission."
            if result["reward_granted"]
            else "No-trigger review saved; no Permission was granted."
        )

    form = DependentForm(
        viewer.user_id,
        data.get("frame_label", frame) + " — Off-Duty Permission",
        instructions,
        build,
        submit,
    )
    await reply(interaction, form.text(), form)
