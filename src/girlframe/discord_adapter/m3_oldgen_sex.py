"""Private voluntary source and original owned Oldgen Sex result controls."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine import m3_oldgen_sex as rules
from girlframe.engine.m2 import ChoiceAnswer, PlayInput
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.services.m2_game import GameService
from girlframe.services.m3_oldgen_sex import OldgenSexService
from girlframe.services.onboarding import WorkflowError

DISCLOSURE = (
    "Confirm only your own actual voluntary interaction. Oldgen's source-owned effects can "
    "change Tags, Status, a maxim, a Bond or actual ability to act. Each human keeps their "
    "own printed choices; no further consent is inferred. OOC pause remains available."
)


async def open_choice(
    interaction: discord.Interaction, game: GameService, decision: dict[str, Any]
) -> None:
    data = decision["detail"]
    kind = decision["kind"]
    if kind == "oldgen_sex_creep":
        fields = [
            Field(
                "effects",
                "Do you actually think Oldgen is a creep?",
                (("yes", "Yes"), ("no", "No")),
            )
        ]
    elif kind == "oldgen_sex_rewrite":
        fields = [
            Field(
                "effects",
                "Your own optional low result",
                (("rewrite", "Rewrite an actual owned maxim"), ("decline", "Decline"))
                if data["rewrite"]
                else (("decline", "No owned maxim to rewrite — decline"),),
            )
        ]
        if data["rewrite"]:
            fields += [
                Field(
                    "maxim",
                    "Actual owned maxim if rewriting",
                    tuple(data["rewrite"]),
                    minimum=0,
                    required=False,
                ),
                Field("text", "Actual rewritten maxim", paragraph=True, required=False),
            ]
    else:
        fields = [
            Field(
                "effects",
                "Your actual printed effects",
                tuple(data["options"]),
                minimum=data["minimum"],
                maximum=data["maximum"],
                required=data["minimum"] > 0,
            ),
            Field("tag", "Actual Tag label if chosen", required=False),
        ]
        if data["maxims"]:
            fields.append(
                Field(
                    "maxim",
                    "Actual marked Oldgen maxim if chosen",
                    tuple(data["maxims"]),
                    minimum=0,
                    required=False,
                )
            )

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str | None:
        if data.get("unsupported_status") and "status" in values.get("effects", ()):
            # A choice of an unsupported consequence is a request for adjudication,
            # never permission to invent NPC rank or partially apply the other effects.
            fresh = await asyncio.to_thread(
                game.decision, viewer_from_interaction(current), decision["id"]
            )
            if fresh["revision"] != decision["revision"]:
                raise WorkflowError("This choice changed. Reopen your actual pending result.")
            if not fresh["detail"].get("unsupported_status"):
                raise WorkflowError("Reopen the current result and its supported choices.")
            from girlframe.discord_adapter.p1_facilitator import open_missing_source

            await open_missing_source(
                current, game, "action", fresh["parent"], "choice:" + fresh["kind"]
            )
            return None
        supplied = {}
        if values.get("tag", "").strip():
            supplied["tag"] = values["tag"]
        if values.get("maxim"):
            supplied["maxim"] = values["maxim"][0]
        await asyncio.to_thread(
            game.respond,
            viewer_from_interaction(current),
            str(current.id),
            decision["id"],
            decision["revision"],
            ChoiceAnswer(
                options=values.get("effects", ()), fields=supplied, text=values.get("text", "")
            ),
        )
        return "Your actual owned Oldgen Sex result is saved."

    disclosure = DISCLOSURE
    if data.get("unsupported_status"):
        disclosure += (
            " NPC Status has no automated ranked resource here. Confirming it opens a private "
            "GM decision request and leaves ALL effects pending; no rank or completion is invented."
        )
    form = NativeForm(interaction.user.id, "Oldgen: your actual result", disclosure, fields, submit)
    await reply(interaction, form.text(), form)


async def open_oldgen_sex(
    interaction: discord.Interaction,
    service: OldgenSexService,
    identity: str | None = None,
    *,
    learned_source: str | None = None,
) -> None:
    viewer = viewer_from_interaction(interaction)
    channel = int(interaction.channel_id or 0)
    if identity is not None:
        data = await asyncio.to_thread(service.view, viewer, identity)
        if data["phase"] == "invited" and viewer.user_id == data["counterpart"]:

            async def respond(current: discord.Interaction, values: dict[str, Any]) -> str:
                await asyncio.to_thread(
                    service.respond,
                    viewer_from_interaction(current),
                    str(current.id),
                    identity,
                    data["revision"],
                    values["accept"][0] == "yes",
                    values["account"],
                    npc_contact_account=values.get("npc_contact") or None,
                )
                return "Your own actual voluntary source response is saved."

            form = NativeForm(
                viewer.user_id,
                "Your actual source answer",
                DISCLOSURE + " Proposed source: " + data["proposal"],
                [
                    Field(
                        "accept",
                        "Your actual voluntary source",
                        (("yes", "Confirm"), ("no", "Decline")),
                    ),
                    Field("account", "Your own actual answer", paragraph=True),
                ]
                + (
                    [
                        Field(
                            "npc_contact",
                            "If accepting: actual physical contact, outside enclosures",
                            paragraph=True,
                            required=False,
                        )
                    ]
                    if data["target"]["kind"] == "npc"
                    else []
                ),
                respond,
            )
        elif data["phase"] == "accepted" and viewer.user_id == data["caster"]:
            sheet = await asyncio.to_thread(service.game.sheet, viewer)

            async def begin(current: discord.Interaction, values: dict[str, Any]) -> str:
                result = await asyncio.to_thread(
                    service.game.begin,
                    viewer_from_interaction(current),
                    str(current.id),
                    channel,
                    sheet["revision"],
                    PlayInput(
                        play=rules.PLAY,
                        source_work=identity,
                        target_actor=ActorRef.model_validate(data["target"]),
                        heat=int(values["heat"][0]),
                        context=values["account"],
                        trigger_confirmed=True,
                    ),
                )
                return "Your actual Oldgen Sex Play is prepared: " + str(result["action_id"])

            form = NativeForm(
                viewer.user_id,
                "Actual Oldgen Sex Play",
                DISCLOSURE,
                [
                    Field(
                        "heat",
                        "Actual Heat spent",
                        tuple((str(x), str(x)) for x in range(sheet["heat"] + 1)),
                    ),
                    Field("account", "Your actual confirmed interaction", paragraph=True),
                ],
                begin,
            )
        else:
            await reply(
                interaction,
                "Your actual Oldgen interaction: "
                + data["phase"]
                + ". Effects: "
                + (", ".join(x["kind"] for x in data["effects"]) or "none")
                + ".",
            )
            return
        await reply(interaction, form.text(), form)
        return
    data = await asyncio.to_thread(service.menu, viewer, channel)
    if learned_source is not None and learned_source not in {x["id"] for x in data["lessons"]}:
        raise WorkflowError("Reopen your actual available learned Oldgen source")
    options = [("invite", "Propose your actual voluntary source")] if data["targets"] else []
    options.extend((x["id"], "Your saved interaction: " + x["phase"]) for x in data["sessions"])
    options.extend(
        ("withdraw:" + x["id"], "Withdraw your unused invitation")
        for x in data["sessions"]
        if x["can_withdraw"]
    )
    if not options:
        await reply(
            interaction, "No actual Oldgen intimacy source controls or private history here."
        )
        return

    async def choose(current: discord.Interaction, values: dict[str, Any]) -> str | None:
        selected = values["action"][0]
        if selected.startswith("withdraw:"):
            await asyncio.to_thread(
                service.withdraw,
                viewer_from_interaction(current),
                str(current.id),
                selected.removeprefix("withdraw:"),
                data["revision"],
            )
            return (
                "Unused invitation withdrawn; original consent remains history, not a new answer."
            )
        if selected != "invite":
            await open_oldgen_sex(current, service, selected)
            return None

        async def invite(response: discord.Interaction, answer: dict[str, Any]) -> str:
            target = next(x for x in data["targets"] if x["token"] == answer["target"][0])
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
            return "Saved. The actual counterpart answers the voluntary source invitation."

        form = NativeForm(
            current.user.id,
            "Actual Oldgen source",
            DISCLOSURE,
            [
                Field(
                    "target",
                    "Actual original counterpart",
                    tuple((x["token"], x["label"]) for x in data["targets"]),
                ),
                Field("account", "Your actual voluntary interaction", paragraph=True),
            ]
            + (
                [
                    Field(
                        "lesson",
                        "One actual lesson for this source",
                        tuple((x["id"], x["label"]) for x in data["lessons"]),
                    )
                ]
                if data["lessons"]
                else []
            ),
            invite,
        )
        await reply(current, form.text(), form)
        return None

    form = NativeForm(
        viewer.user_id,
        "Oldgen Sex source controls",
        DISCLOSURE,
        [Field("action", "Your actual source", tuple(options))],
        choose,
    )
    await reply(interaction, form.text(), form)
