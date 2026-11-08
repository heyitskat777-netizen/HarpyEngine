"""Human-owned advice responses and private actual maxim controls."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine.m2 import ChoiceAnswer, PlayInput
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.services.m2_game import GameService
from girlframe.services.m3_oldgen import OldgenService


async def open_choice(
    interaction: discord.Interaction, game: GameService, decision: dict[str, Any]
) -> None:
    detail = decision["detail"]
    fields = [
        Field(
            "account",
            "Your actual listening account"
            if decision["kind"] == "oldgen_listen"
            else "Your new target-only one-use maxim",
            paragraph=True,
        )
    ]
    if detail["unmark"]:
        fields.append(
            Field(
                "unmark",
                "Optional actual Identity or maxim to unmark",
                tuple(detail["unmark"]),
                minimum=0,
            )
        )

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        await asyncio.to_thread(
            game.respond,
            viewer_from_interaction(current),
            str(current.id),
            decision["id"],
            decision["revision"],
            ChoiceAnswer(text=values["account"], denied=values.get("unmark", ())),
        )
        return "Your original owned advice result is saved."

    form = NativeForm(
        interaction.user.id,
        "Old Dog, New Pups",
        "Use your own actual result. Listening is a fictional consequence; "
        "OOC pause remains available.",
        fields,
        submit,
    )
    await reply(interaction, form.text(), form)


async def open_oldgen(
    interaction: discord.Interaction, service: OldgenService, identity: str | None = None
) -> None:
    viewer = viewer_from_interaction(interaction)
    channel = int(interaction.channel_id or 0)
    if identity is not None:
        shown = await asyncio.to_thread(service.view, viewer, identity)
        if not shown["available"]:
            await reply(interaction, shown["text"] + " — " + shown["status"] + ".")
            return
        data = await asyncio.to_thread(service.menu, viewer, channel)
        selected = next((x for x in data["maxims"] if x["id"] == identity), None)
        if selected is None or not data["scene_available"]:
            await reply(
                interaction,
                shown["text"] + " — " + shown["status"] + ". Open its actual scene to use it.",
            )
            return
        options = [
            ("reinforce", "Actual reinforcement: give 2 Heat"),
            ("reject", "Actual rejection: give a Tag"),
        ]
        if shown["replacements"] and shown["poor"]:
            options.append(("rewrite", "Actual rejected/poor outcome: rewrite Identity"))

        async def choose_effect(current: discord.Interaction, values: dict[str, Any]) -> str | None:
            effect = values["effect"][0]
            targets = [
                x
                for x in data["subjects"]
                if ActorRef.model_validate(x["ref"]).entity != str(viewer.user_id)
                and (selected["subject"] is None or x["ref"] == selected["subject"])
            ]
            fields = [
                Field(
                    "target",
                    "Actual other Girl",
                    tuple((ActorRef.model_validate(x["ref"]).token, x["label"]) for x in targets),
                ),
                Field("account", "Actual reinforcement or rejection", paragraph=True),
            ]
            if effect == "reject":
                fields.append(Field("tag", "Actual Tag label"))
            elif effect == "rewrite":
                fields.extend(
                    [
                        Field(
                            "replacement",
                            "Actual legal Identity",
                            tuple((x["id"], x["name"]) for x in shown["replacements"]),
                        ),
                        Field("name", "Actual rewritten Identity"),
                    ]
                )

            async def use(response: discord.Interaction, answer: dict[str, Any]) -> str:
                subject = ActorRef.model_validate(
                    next(
                        x["ref"]
                        for x in targets
                        if ActorRef.model_validate(x["ref"]).token == answer["target"][0]
                    )
                )
                await asyncio.to_thread(
                    service.use,
                    viewer_from_interaction(response),
                    str(response.id),
                    identity,
                    subject,
                    "reinforce" if effect == "reinforce" else "reject",
                    channel,
                    data["revision"],
                    answer["account"],
                    tag=answer.get("tag", ""),
                    replaced=answer.get("replacement", (None,))[0],
                    name=answer.get("name", ""),
                    poor=shown["poor"][0] if effect == "rewrite" else None,
                )
                return "Your actual maxim consequence is saved."

            form = NativeForm(
                current.user.id, "Use your actual maxim", selected["text"], fields, use
            )
            await reply(current, form.text(), form)
            return None

        form = NativeForm(
            viewer.user_id,
            "Your actual maxim",
            selected["text"],
            [Field("effect", "Actual printed consequence", tuple(options))],
            choose_effect,
        )
        await reply(interaction, form.text(), form)
        return
    data = await asyncio.to_thread(service.menu, viewer, channel)
    options = [("maxim:" + x["id"], x["text"]) for x in data["maxims"]]
    options.extend(
        ("poor:" + x["id"], "Record actual rejected/poor outcome: " + x["text"])
        for x in data["adjudicate"]
    )
    sheet = await asyncio.to_thread(service.game.sheet, viewer) if data["can_advise"] else {}
    if data["can_advise"]:
        options.insert(0, ("advice", "Give actual advice: Old Dog, New Pups"))
    if not options:
        await reply(interaction, "No actual available Oldgen maxim or advice controls here.")
        return

    async def choose(current: discord.Interaction, values: dict[str, Any]) -> str | None:
        selected = values["action"][0]
        if selected.startswith("maxim:"):
            await open_oldgen(current, service, selected.removeprefix("maxim:"))
            return None
        if selected.startswith("poor:"):

            async def poor(response: discord.Interaction, answer: dict[str, Any]) -> str:
                await asyncio.to_thread(
                    service.record_poor,
                    viewer_from_interaction(response),
                    str(response.id),
                    selected.removeprefix("poor:"),
                    channel,
                    data["revision"],
                    answer["account"],
                )
                return "The actual Handler-authored rejection and poor outcome is saved."

            form = NativeForm(
                current.user.id,
                "Actual rejected maxim and poor outcome",
                "Record only actual human-authoritative game facts, "
                "without automatic dialogue or consent.",
                [Field("account", "Actual rejection and poor outcome", paragraph=True)],
                poor,
            )
        else:
            targets = [
                x
                for x in data["subjects"]
                if ActorRef.model_validate(x["ref"]).entity != str(viewer.user_id)
            ]

            async def advice(response: discord.Interaction, answer: dict[str, Any]) -> str:
                target = ActorRef.model_validate(
                    next(
                        x["ref"]
                        for x in targets
                        if ActorRef.model_validate(x["ref"]).token == answer["target"][0]
                    )
                )
                result = await asyncio.to_thread(
                    service.game.begin,
                    viewer_from_interaction(response),
                    str(response.id),
                    channel,
                    sheet["revision"],
                    PlayInput(
                        play="old_dog_new_pups",
                        target=int(target.entity),
                        heat=int(answer["heat"][0]),
                        context=answer["account"],
                        trigger_confirmed=True,
                    ),
                )
                return "Your actual advice Play is prepared: " + str(result["action_id"])

            form = NativeForm(
                current.user.id,
                "Old Dog, New Pups",
                "Spend actual Heat and give actual advice.",
                [
                    Field(
                        "target",
                        "Actual other Girl",
                        tuple(
                            (ActorRef.model_validate(x["ref"]).token, x["label"]) for x in targets
                        ),
                    ),
                    Field(
                        "heat",
                        "Actual Heat spent",
                        tuple((str(x), str(x)) for x in range(sheet["heat"] + 1)),
                    ),
                    Field("account", "Your actual advice", paragraph=True),
                ],
                advice,
            )
        await reply(current, form.text(), form)
        return None

    form = NativeForm(
        viewer.user_id,
        "Oldgen",
        "Actual maxims and original human-owned advice results.",
        [Field("action", "Your actual control", tuple(options))],
        choose,
    )
    await reply(interaction, form.text(), form)
