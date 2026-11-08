"""Private original-human Newgirl intimacy, independent choices and discovery receipts."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine.m2 import ChoiceAnswer, PlayInput
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.services.m2_game import GameService
from girlframe.services.m3_newgirl_sex import NewgirlSexService


async def open_choice(
    interaction: discord.Interaction, game: GameService, decision: dict[str, Any]
) -> None:
    detail = decision["detail"]
    fields = []
    if detail["options"]:
        fields.append(
            Field(
                "options", "Your actual printed choice", tuple(tuple(x) for x in detail["options"])
            )
        )
    if detail["assets"]:
        fields.append(
            Field(
                "asset",
                "Only if damage: actual Newgirl Asset",
                tuple((x["id"], x["label"]) for x in detail["assets"]),
                minimum=0,
                required=False,
            )
        )
    fields.append(Field("text", detail["label"], paragraph=True))

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        await asyncio.to_thread(
            game.respond,
            viewer_from_interaction(current),
            str(current.id),
            decision["id"],
            decision["revision"],
            ChoiceAnswer(
                options=values.get("options", ()),
                denied=values.get("asset", ()),
                text=values["text"],
            ),
        )
        return "Your actual original-person response is saved. Real damage work keeps its controls."

    form = NativeForm(
        interaction.user.id,
        "Newgirl Sex: " + detail["partner"],
        "Author only your actual words or printed decision. Another human's response is theirs. "
        "OOC safety pause remains available; no interface choice fabricates consent.",
        fields,
        submit,
    )
    await reply(interaction, form.text(), form)


async def open_newgirl_sex(
    interaction: discord.Interaction, service: NewgirlSexService, identity: str | None = None
) -> None:
    viewer = viewer_from_interaction(interaction)
    channel = int(interaction.channel_id or 0)
    if identity is None:
        data = await asyncio.to_thread(service.menu, viewer, channel)
        options = (
            [("invite", "Propose actual voluntary intimacy with original Girls")]
            if data["partners"]
            else []
        )
        options.extend((x["id"], x["label"]) for x in data["history"])
        if not options:
            await reply(
                interaction, "No supported original-person source or private saved history here."
            )
            return

        async def choose(current: discord.Interaction, values: dict[str, Any]) -> str | None:
            if values["source"][0] != "invite":
                await open_newgirl_sex(current, service, values["source"][0])
                return None

            async def invite(response: discord.Interaction, answer: dict[str, Any]) -> str:
                partners = tuple(
                    ActorRef.model_validate(x["ref"])
                    for x in data["partners"]
                    if ActorRef.model_validate(x["ref"]).token in answer["partners"]
                )
                result = await asyncio.to_thread(
                    service.invite,
                    viewer_from_interaction(response),
                    str(response.id),
                    channel,
                    partners,
                    data["revision"],
                    answer["account"],
                )
                return "Actual source proposed; each original person must confirm: " + str(
                    result["id"]
                )

            form = NativeForm(
                current.user.id,
                "Actual Newgirl intimacy source",
                "Choose actual people together here. Each human confirms only their own "
                "voluntary participation; no fictional dialogue or consent is inferred.",
                [
                    Field(
                        "partners",
                        "Actual original partners",
                        tuple(
                            (ActorRef.model_validate(x["ref"]).token, x["label"])
                            for x in data["partners"]
                        ),
                        minimum=1,
                        maximum=len(data["partners"]),
                    ),
                    Field("account", "Your actual voluntary source proposal", paragraph=True),
                ],
                invite,
            )
            await reply(current, form.text(), form)
            return None

        form = NativeForm(
            viewer.user_id,
            "Newgirl intimacy and original Mentors",
            "Your actual source and private history.",
            [Field("source", "Source", tuple(options))],
            choose,
        )
        await reply(interaction, form.text(), form)
        return
    data = await asyncio.to_thread(service.view, viewer, identity)
    if data["kind"] == "discovery":
        summary = "Addressed actual discovery: " + data["account"]
        if data["learned"]:
            summary += ". Actual learned receipt: " + data["learned"]
        if data["tag"]:
            summary += ". Actual optional Mentor Tag: " + data["tag"]
        if not data["can_learn"] and not data["can_tag"]:
            await reply(interaction, summary)
            return
        learn = data["can_learn"]

        async def record(current: discord.Interaction, values: dict[str, Any]) -> str:
            method = service.learn if learn else service.discovery_tag
            await asyncio.to_thread(
                method,
                viewer_from_interaction(current),
                str(current.id),
                identity,
                data["revision"],
                values["text"],
            )
            return (
                "Actual learned receipt saved."
                if learn
                else "Your optional actual Mentor Tag is saved."
            )

        form = NativeForm(
            viewer.user_id,
            "Actual discovered Mentor intimacy",
            summary,
            [
                Field(
                    "text",
                    "What you actually learned" if learn else "Your actual Mentor Tag",
                    paragraph=True,
                )
            ],
            record,
        )
        await reply(interaction, form.text(), form)
        return
    summary = "Your actual Newgirl source: " + data["phase"] + ". " + data["proposal"]
    options = []
    if data["can_confirm"]:
        options.append(("confirm", "Your own actual voluntary response"))
    if data["can_roll"]:
        options.append(("roll", "Actual performed Newgirl Sex Play"))
    if data["mentors"] and data["discovery_targets"] and viewer.user_id == data["actor"]:
        options.append(("disclose", "Record actual addressed discovery of Mentor intimacy"))
    if not options:
        await reply(interaction, summary + ". Resume actual pending choices/work through Requests.")
        return

    async def choose_operation(current: discord.Interaction, values: dict[str, Any]) -> str | None:
        operation = values["operation"][0]
        if operation == "confirm":

            async def confirm(response: discord.Interaction, answer: dict[str, Any]) -> str:
                await asyncio.to_thread(
                    service.confirm,
                    viewer_from_interaction(response),
                    str(response.id),
                    identity,
                    data["revision"],
                    answer["accept"][0] == "yes",
                    answer["account"],
                )
                return "Your own actual voluntary source response is saved."

            fields = [
                Field(
                    "accept",
                    "Your actual choice",
                    (("yes", "Voluntarily participate"), ("no", "Decline")),
                ),
                Field("account", "Your own actual voluntary source account", paragraph=True),
            ]
            submit = confirm
        elif operation == "roll":
            sheet = await asyncio.to_thread(service.game.sheet, viewer_from_interaction(current))

            async def roll(response: discord.Interaction, answer: dict[str, Any]) -> str:
                result = await asyncio.to_thread(
                    service.game.begin,
                    viewer_from_interaction(response),
                    str(response.id),
                    data["channel"],
                    sheet["revision"],
                    PlayInput(
                        play="newgirl_sex",
                        source_work=identity,
                        heat=int(answer["heat"][0]),
                        context=answer["account"],
                        trigger_confirmed=True,
                    ),
                )
                return "Actual source Play prepared: " + str(result["action_id"])

            fields = [
                Field(
                    "heat",
                    "Actual Heat spent",
                    tuple((str(x), str(x)) for x in range(sheet["heat"] + 1)),
                ),
                Field("account", "Actual performed voluntary source", paragraph=True),
            ]
            submit = roll
        else:

            async def disclose(response: discord.Interaction, answer: dict[str, Any]) -> str:
                mentor = ActorRef.model_validate(
                    next(
                        x
                        for x in data["mentors"]
                        if ActorRef.model_validate(x).token == answer["mentor"][0]
                    )
                )
                observer = ActorRef.model_validate(
                    next(
                        x["ref"]
                        for x in data["discovery_targets"]
                        if ActorRef.model_validate(x["ref"]).token == answer["observer"][0]
                    )
                )
                await asyncio.to_thread(
                    service.disclose,
                    viewer_from_interaction(response),
                    str(response.id),
                    identity,
                    mentor,
                    observer,
                    data["revision"],
                    answer["account"],
                    witness=answer["basis"][0] == "witness",
                    channel=data["channel"],
                )
                return "Actual addressed source saved; its recipient owns the learned receipt."

            fields = [
                Field(
                    "mentor",
                    "Actual source Mentor",
                    tuple(
                        (
                            ActorRef.model_validate(x).token,
                            next(
                                p["label"]
                                for p in data["partners"]
                                if ActorRef.model_validate(p["ref"]) == ActorRef.model_validate(x)
                            ),
                        )
                        for x in data["mentors"]
                    ),
                ),
                Field(
                    "observer",
                    "Actual addressed third party",
                    tuple(
                        (ActorRef.model_validate(x["ref"]).token, x["label"])
                        for x in data["discovery_targets"]
                    ),
                ),
                Field(
                    "basis",
                    "Actual source",
                    (
                        ("disclosure", "Truthful addressed disclosure"),
                        ("witness", "Actual original witness"),
                    ),
                ),
                Field(
                    "account",
                    "Actual performed communication or discovered witness facts",
                    paragraph=True,
                ),
            ]
            submit = disclose
        form = NativeForm(current.user.id, "Your actual Newgirl source", summary, fields, submit)
        await reply(current, form.text(), form)
        return None

    form = NativeForm(
        viewer.user_id,
        "Your saved original-person intimacy source",
        summary,
        [Field("operation", "Your actual owned control", tuple(options))],
        choose_operation,
    )
    await reply(interaction, form.text(), form)
