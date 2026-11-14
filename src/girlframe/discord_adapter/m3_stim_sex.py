"""Private voluntary Stim source controls and actual owned printed outcomes."""

import asyncio
from typing import Any, Literal, cast

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine.m2 import ChoiceAnswer, PlayInput
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.services.m2_game import GameService
from girlframe.services.m3_stim_sex import SexService
from girlframe.services.onboarding import WorkflowError


async def open_choice(
    interaction: discord.Interaction, game: GameService, decision: dict[str, Any]
) -> None:
    detail = decision["detail"]
    fields = [
        Field(
            "options",
            "Your actual printed choice",
            tuple((x[0], x[1]) for x in detail["options"]),
            minimum=detail["minimum"],
            maximum=detail["maximum"],
        )
    ]
    if detail["tag"]:
        fields.append(Field("tag", "Only if giving a Tag: your authored label", required=False))

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        await asyncio.to_thread(
            game.respond,
            viewer_from_interaction(current),
            str(current.id),
            decision["id"],
            decision["revision"],
            ChoiceAnswer(
                options=values["options"],
                text=values.get("tag", "") if "tag" in values["options"] else "",
            ),
        )
        return "Your actual Stim choice is saved; remaining people keep their own choices."

    form = NativeForm(
        interaction.user.id,
        "Stim: your owned outcome",
        "Choose exactly the printed quota. A drug is a temporary Tag; physiological effects "
        "follow its real lifetime. No consent or dialogue is inferred.",
        fields,
        submit,
    )
    await reply(interaction, form.text(), form)


async def open_stim(
    interaction: discord.Interaction,
    service: SexService,
    identity: str | None = None,
    *,
    learned_source: str | None = None,
) -> None:
    viewer = viewer_from_interaction(interaction)
    channel = int(interaction.channel_id or 0)
    if identity is not None:
        value = await asyncio.to_thread(service.view, viewer, identity)
        if value.get("lesson_cancelled"):
            await reply(
                interaction,
                "You cancelled this unrolled learned source. Its lesson is unused; "
                "a new source requires a fresh invitation and the counterpart's own answer.",
            )
            return
        if value["phase"] == "invited" and value["counterpart"] == viewer.user_id:

            async def respond(current: discord.Interaction, values: dict[str, Any]) -> str:
                await asyncio.to_thread(
                    service.respond,
                    viewer_from_interaction(current),
                    str(current.id),
                    identity,
                    value["revision"],
                    values["accept"][0] == "yes",
                    values["account"],
                    npc_contact_account=values.get("npc_contact")
                    if values["accept"][0] == "yes"
                    else None,
                )
                return (
                    "Your own source reply is saved. This grants no consent to other interactions."
                )

            form = NativeForm(
                viewer.user_id,
                "Your actual voluntary Stim source",
                value["proposal"],
                [
                    Field(
                        "accept",
                        "Your own source confirmation",
                        (
                            ("yes", "Confirm this voluntary actual interaction"),
                            ("no", "Decline this source"),
                        ),
                    ),
                    Field("account", "Your own source confirmation or refusal", paragraph=True),
                    *(
                        [
                            Field(
                                "npc_contact",
                                "If accepting: actual body contact outside enclosures and rides",
                                paragraph=True,
                                required=False,
                            )
                        ]
                        if value["target"]["kind"] == "npc"
                        else []
                    ),
                ],
                respond,
            )
            await reply(interaction, form.text(), form)
            return
        if value["phase"] == "accepted" and value["caster"] == viewer.user_id:
            sheet = await asyncio.to_thread(service.game.sheet, viewer)
            identities = [
                x
                for x in sheet["identities"] + sheet.get("additional_identities", [])
                if not x["marked"]
            ]

            async def play(current: discord.Interaction, values: dict[str, Any]) -> str:
                result = await asyncio.to_thread(
                    service.game.begin,
                    viewer_from_interaction(current),
                    str(current.id),
                    channel,
                    sheet["revision"],
                    PlayInput(
                        play="stim_sex",
                        source_work=identity,
                        target_actor=ActorRef.model_validate(value["target"]),
                        heat=int(values["heat"][0]),
                        context=values["account"],
                        trigger_confirmed=True,
                        identity=values["identity"][0] if values.get("identity") else None,
                        gain=int(values["gain"][0]),
                        disposable_heat=cast(Literal[0, 3, 4], int(values["disposable"][0])),
                    ),
                )
                return "Actual Stim Sex Play prepared: " + str(result["action_id"])

            form = NativeForm(
                viewer.user_id,
                "Prepare actual Stim Sex",
                "Use the actual accepted voluntary source. Original Heat and Identity rules apply; "
                "at five Heat or more spend all. OOC pause remains available.",
                [
                    Field(
                        "identity",
                        "Optional actual Identity to mark",
                        tuple((x["id"], x["name"]) for x in identities),
                        minimum=0,
                        required=False,
                    ),
                    Field(
                        "gain", "Ordinary Identity Heat", tuple((str(x), str(x)) for x in range(4))
                    ),
                    Field(
                        "disposable",
                        "Optional eligible Identity disposal",
                        (
                            ("0", "Keep the marked Identity"),
                            ("3", "Remove it:3 additional Heat"),
                            ("4", "Remove it:4 additional Heat"),
                        ),
                    ),
                    Field(
                        "heat",
                        "Actual Heat spent",
                        tuple((str(x), str(x)) for x in range(sheet["heat"] + 8)),
                    ),
                    Field("account", "Your actual source trigger", paragraph=True),
                ],
                play,
            )
            await reply(interaction, form.text(), form)
            return
        drugs = (
            ", ".join(x["label"] + (" (expired)" if x["expired"] else "") for x in value["drugs"])
            or "none"
        )
        effects = (
            ", ".join(x["kind"] + (": " + x["tag"] if x["tag"] else "") for x in value["effects"])
            or "none"
        )
        if value.get("npc_order_effect"):

            async def issue(current: discord.Interaction, values: dict[str, Any]) -> str:
                from girlframe.services.m3_npc_orders import NpcOrderService

                result = await asyncio.to_thread(
                    NpcOrderService(service.game).issue,
                    viewer_from_interaction(current),
                    str(current.id),
                    channel,
                    ActorRef.model_validate(value["target"]),
                    int(value["actor"]["entity"]),
                    value["revision"],
                    values["instruction"],
                    origin_kind="stim_sex",
                    source_effect=value["npc_order_effect"],
                )
                return "Actual NPC Order saved; the Pilot owns their reply. " + str(
                    result["action_id"]
                )

            form = NativeForm(
                viewer.user_id,
                "Stim: actual NPC Order",
                "This original NPC can give the drugged Pilot Orders until the real drug expires. "
                "The Pilot still chooses their response and may Disobey. Drugs: " + drugs,
                [Field("instruction", "Your actual NPC's direct Order", paragraph=True)],
                issue,
            )
            await reply(interaction, form.text(), form)
            return
        await reply(
            interaction,
            "Your Stim source: "
            + value["phase"]
            + ". Drugs: "
            + drugs
            + ". Actual effects: "
            + effects
            + ".",
        )
        return
    data = await asyncio.to_thread(service.menu, viewer, channel)
    if learned_source is not None and learned_source not in {x["id"] for x in data["lessons"]}:
        raise WorkflowError("Reopen your actual available learned source")
    options = [("invite", "Record an actual voluntary source")] if data["targets"] else []
    options.extend((x["id"], "Your original Stim source: " + x["phase"]) for x in data["sessions"])
    options.extend(
        ("withdraw:" + x["id"], "Withdraw your unused delegated invitation")
        for x in data["sessions"]
        if x["can_withdraw"]
    )
    if not options:
        await reply(interaction, "No current supported Stim source or private saved history here.")
        return

    async def choose(current: discord.Interaction, values: dict[str, Any]) -> str | None:
        selected = values["source"][0]
        if selected.startswith("withdraw:"):
            await asyncio.to_thread(
                service.withdraw,
                viewer_from_interaction(current),
                str(current.id),
                selected.removeprefix("withdraw:"),
                data["revision"],
            )
            return "Unused source withdrawn; new participation requires a fresh answer."
        if values["source"][0] != "invite":
            await open_stim(current, service, values["source"][0])
            return None

        async def invite(response: discord.Interaction, answer: dict[str, Any]) -> str:
            target = next(
                x
                for x in data["targets"]
                if ActorRef.model_validate(x["ref"]).token == answer["target"][0]
            )
            await asyncio.to_thread(
                service.invite,
                viewer_from_interaction(response),
                str(response.id),
                channel,
                ActorRef.model_validate(target["ref"]),
                data["revision"],
                answer["account"],
                learned_source=next(iter(answer.get("lesson", ())), learned_source),
            )
            return (
                "Actual source invitation saved. The other human owns their source reply "
                "in Requests."
            )

        form = NativeForm(
            current.user.id,
            "Voluntary Stim source",
            "Describe only your actual proposed interaction. The original other human must author "
            "their own confirmation; no performance or consent is fabricated.",
            [
                Field(
                    "target",
                    "Actual original counterpart",
                    tuple(
                        (ActorRef.model_validate(x["ref"]).token, x["label"])
                        for x in data["targets"]
                    ),
                ),
                Field("account", "Your actual voluntary source", paragraph=True),
            ]
            + (
                [
                    Field(
                        "lesson",
                        "One actual lesson for this voluntary source",
                        tuple((x["id"], x["label"]) for x in data["lessons"]),
                    )
                ]
                if data["lessons"]
                else []
            ),
            invite,
        )
        if learned_source is not None:
            form.values["lesson"] = (learned_source,)
        await reply(current, form.text(), form)
        return None

    form = NativeForm(
        viewer.user_id,
        "Stim source controls",
        "Your actual source and saved private history.",
        [Field("source", "Your control", tuple(options))],
        choose,
    )
    await reply(interaction, form.text(), form)
