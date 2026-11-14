"""Original native Girl/NPC private replies and genuine source performances."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine.m3_kicked_puppy import QUESTION, QUESTION_TEXT
from girlframe.services.m2_game import GameService
from girlframe.services.m3_npc_flirt import NpcFlirtService

QUESTIONS = {
    "hurt": "Who do you want me to hurt?",
    "be": "Who do you want me to be?",
    "hide": "What do you want me to hide?",
    "fears": "How could I alleviate your fears?",
    "name": "What do you want me to call you?",
    "intimacy": "Do you want to have sex with me?",
}


async def open_choice(
    interaction: discord.Interaction, game: GameService, decision: dict[str, Any]
) -> None:
    data, kind = decision["npc_flirt"], decision["kind"]
    fields = []
    if kind == "npc_flirt_actor":
        fields = [
            Field(
                "question",
                "Your actual question",
                tuple(
                    (x, QUESTION_TEXT if x == QUESTION else QUESTIONS[x]) for x in data["questions"]
                ),
            )
        ]
        if data["identities"]:
            fields.append(
                Field(
                    "unmark",
                    "Optional own marked Identities (up to2)",
                    tuple((x["id"], x["name"]) for x in data["identities"]),
                    minimum=0,
                    maximum=2,
                    required=False,
                )
            )
        if data["tier"] == "high":
            fields += [
                Field(
                    "extra",
                    "How your actual Flirt goes too far",
                    (
                        ("escape", "NPC escapes through real damage/Play, or becomes Helpless"),
                        ("handler", "Actual Handler notices and makes a Play"),
                        ("owe", "NPC may give you a Tag; you cannot refuse until resolved"),
                    ),
                ),
                Field("text", "Describe how you actually go too far", paragraph=True),
            ]
    elif kind == "npc_flirt_target":
        fields = [
            Field(
                "text",
                "What pushes you away?"
                if data["tier"] == "low"
                else (
                    QUESTION_TEXT
                    if data["question"] == QUESTION
                    else QUESTIONS.get(
                        data["question"], "Your actual NPC answer and wanted outcome"
                    )
                ),
                paragraph=True,
            )
        ]
        if data["tier"] == "low":
            fields.append(
                Field(
                    "question",
                    "Optional printed return question",
                    tuple(QUESTIONS.items()),
                    minimum=0,
                    required=False,
                )
            )
        elif data["question"] == "intimacy":
            fields.append(
                Field(
                    "intimacy",
                    "Your actual intimacy/safety confirmation",
                    (
                        ("yes", "Actually confirmed"),
                        ("no", "Not confirmed; safety controls remain"),
                    ),
                    minimum=0,
                    required=False,
                )
            )
    elif kind == "npc_flirt_escape":
        options = [
            ("helpless", "Become actually Helpless against this Girl"),
            ("damage", "Suffer a real NPC Asset-replacement consequence to escape"),
        ]
        if data["jobs"]:
            options.append(("play", "Perform a real supported job Play to escape"))
        fields = [Field("escape", "Your actual NPC choice", tuple(options))]
    elif kind == "npc_flirt_play":
        fields = [
            Field(
                "job",
                "Actual source-owned NPC job Play",
                tuple((x["id"], x["move"]) for x in data["jobs"]),
            ),
            Field(
                "text",
                "Your actual addressed rendition (nonmechanical Conversation only)",
                paragraph=True,
            ),
        ]
    else:
        fields = [
            Field(
                "text",
                "Actual NPC-given Tag"
                if kind == "npc_flirt_owe"
                else "Your actual answer to the NPC's returned question",
                paragraph=True,
            )
        ]

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        from girlframe.engine.m2 import ChoiceAnswer

        if kind == "npc_flirt_actor":
            answer = ChoiceAnswer(
                options=(values["question"][0],),
                denied=tuple(values.get("unmark", ())),
                fields={"extra": values["extra"][0]} if data["tier"] == "high" else {},
                text=values.get("text", ""),
            )
        elif kind == "npc_flirt_target":
            answer = ChoiceAnswer(
                text=values["text"],
                options=tuple(values.get("question", ())),
                flag=values["intimacy"][0] == "yes" if values.get("intimacy") else None,
            )
        elif kind == "npc_flirt_escape":
            answer = ChoiceAnswer(options=(values["escape"][0],))
        elif kind == "npc_flirt_play":
            job = next(x for x in data["jobs"] if x["id"] == values["job"][0])
            answer = ChoiceAnswer(
                options=(job["id"],), fields={"move": job["move"]}, text=values["text"]
            )
        else:
            answer = ChoiceAnswer(text=values["text"])
        await asyncio.to_thread(
            game.respond,
            viewer_from_interaction(current),
            str(current.id),
            decision["id"],
            decision["revision"],
            answer,
        )
        return "Your actual source response is saved."

    await NativeForm(
        interaction.user.id,
        "Actual NPC Flirt response",
        (
            "The original Princess authors this actual Girl's one-Play decision; "
            "the performing Girl retains her own resources. Safety pause remains available."
            if data.get("directed") and kind in ("npc_flirt_actor", "npc_flirt_answer")
            else "Answer for the displayed Girl/NPC role. Safety pause remains available."
        ),
        fields,
        submit,
    ).present(interaction)


async def open_npc_flirt(
    interaction: discord.Interaction, service: NpcFlirtService, identity: str | None = None
) -> None:
    viewer = viewer_from_interaction(interaction)
    if identity is None:
        rows = await asyncio.to_thread(lambda: _rows(service, viewer))
        if not rows:
            await reply(interaction, "No original NPC Flirt source or saved performance for you.")
            return

        async def select(current: discord.Interaction, values: dict[str, Any]) -> str | None:
            await open_npc_flirt(current, service, values["source"][0])
            return None

        await NativeForm(
            interaction.user.id,
            "Your actual NPC interactions",
            "Original source replies and performed followthrough remain private.",
            [Field("source", "Saved original source", tuple((x["id"], x["label"]) for x in rows))],
            select,
        ).present(interaction)
        return
    data = await asyncio.to_thread(service.view, viewer, identity)
    source = data["source"]
    options = [
        ("choice:" + x["id"], "Your pending actual source response") for x in data["pending"]
    ]
    if data["can_order"]:
        options.append(("order", "Give this Girl an actual direct NPC instruction"))
    if data["can_perform"]:
        options.append(("perform", "Record actual fulfillment of the NPC's wanted outcome"))
    if data["can_judge"]:
        options += [
            ("judge:" + x["id"], "Judge the actual performed followthrough")
            for x in data["performances"]
            if x["kind"] == "followthrough"
            and not any(y["performance"] == x["id"] for y in data["judgments"])
        ]
    text = source["actor_label"] + " → " + source["target_label"] + ": " + source["phase"] + "."
    if source["wanted"]:
        text += " Original NPC wanted: " + source["wanted"]
    text += " Saved performances: " + "; ".join(x["rendition"] for x in data["performances"])
    if data.get("order_blocked"):
        text += " " + data["order_blocked"]
    if not options:
        await reply(interaction, text)
        return

    async def choose(current: discord.Interaction, values: dict[str, Any]) -> str | None:
        selected = values["operation"][0]
        if selected.startswith("choice:"):
            decision = await asyncio.to_thread(
                service.game.decision,
                viewer_from_interaction(current),
                selected.removeprefix("choice:"),
            )
            await open_choice(current, service.game, decision)
            return None
        if selected == "order":
            fields = [Field("instruction", "Your actual direct NPC instruction", paragraph=True)]
        elif selected == "perform":
            fields = [
                Field("account", "Actual addressed nonmechanical fulfillment", paragraph=True),
                Field(
                    "performed_action",
                    "If mechanical: genuine completed source Action",
                    required=False,
                ),
            ]
        else:
            value = next(
                x for x in data["performances"] if x["id"] == selected.removeprefix("judge:")
            )
            fields = [
                Field(
                    "accepted",
                    "Did this actual performance fulfill your specific wanted outcome?",
                    (("yes", "Actually fulfilled"), ("no", "Not fulfilled")),
                ),
                Field("account", "Your own actual judgment of this rendition", paragraph=True),
            ]
            text_for_judgment = value["rendition"]

        async def submit(response: discord.Interaction, answer: dict[str, Any]) -> str | None:
            actual_viewer = viewer_from_interaction(response)
            if selected == "order":
                from girlframe.discord_adapter.m3_npc_orders import open_order
                from girlframe.services.m3_npc_orders import NpcOrderService

                await open_order(
                    response,
                    NpcOrderService(service.game),
                    int(source["actor"]["entity"]),
                    answer["instruction"],
                    origin_kind="npc_flirt",
                )
                return None
            if selected == "perform":
                await asyncio.to_thread(
                    service.record_followthrough,
                    actual_viewer,
                    str(response.id),
                    identity,
                    data["revision"],
                    int(source["cast"]["channel"]),
                    answer["account"],
                    performed_action=answer.get("performed_action") or None,
                )
                return "Performance saved for the original NPC controller's judgment."
            await asyncio.to_thread(
                service.confirm_followthrough,
                actual_viewer,
                str(response.id),
                selected.removeprefix("judge:"),
                data["revision"],
                answer["accepted"][0] == "yes",
                answer["account"],
            )
            return (
                "Actual source judgment saved; only genuine fulfillment deepens the original Bond."
            )

        await NativeForm(
            current.user.id,
            "Actual NPC followthrough",
            text if selected in ("perform", "order") else text + " Rendition: " + text_for_judgment,
            fields,
            submit,
        ).present(current)
        return None

    await NativeForm(
        interaction.user.id,
        "Original NPC Flirt history",
        text,
        [Field("operation", "Your actual source controls", tuple(options))],
        choose,
    ).present(interaction)


def _rows(service: NpcFlirtService, viewer: Any) -> list[dict[str, Any]]:
    with service.store.engine.connect() as c:
        return service._tasks(c, viewer)
