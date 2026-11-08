"""Owned Feedback decisions, explicit human purposes and actual reprisal preparation."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine.m2 import ChoiceAnswer, PlayInput
from girlframe.services.m2_game import GameService
from girlframe.services.m3_ankou_feedback import FeedbackService


async def open_feedback(
    interaction: discord.Interaction, service: FeedbackService, identity: str | None = None
) -> None:
    viewer = viewer_from_interaction(interaction)
    if identity is None:
        with service.store.engine.connect() as c:
            entries = service._tasks(c, viewer)
        if not entries:
            await reply(interaction, "No actual owned Ankou Feedback source is recorded.")
            return

        async def select(current: discord.Interaction, values: dict[str, Any]) -> None:
            await open_feedback(current, service, values["source"][0])

        await NativeForm(
            viewer.user_id,
            "Ankou Feedback",
            "Actual private sources and history.",
            [Field("source", "Saved Feedback", tuple((x["id"], x["label"]) for x in entries))],
            select,
        ).present(interaction)
        return
    data = await asyncio.to_thread(service.view, viewer, identity)
    choices = await asyncio.to_thread(service.game.choices, viewer)
    row = next(
        (
            x
            for x in choices
            if x["action_id"] == data["action"] and x["kind"].startswith("ankou_feedback_")
        ),
        None,
    )
    if row:
        await open_choice(interaction, service.game, row["id"])
        return
    detail = "Saved Feedback: " + data["phase"]
    if data.get("phase") == "ended":
        detail += ". The interrupted original Play ended before dice; it was not performed."
    if data.get("purpose"):
        detail += "\nActual purpose response: " + data["purpose"]
    await reply(interaction, detail + "\nContinue other real Play choices through Play controls.")


async def open_choice(interaction: discord.Interaction, game: GameService, identity: str) -> None:
    viewer = viewer_from_interaction(interaction)
    data = await asyncio.to_thread(game.decision, viewer, identity)
    detail, kind = data["ankou_feedback"], data["kind"]
    if kind == "ankou_feedback_choice":
        people = tuple((x["token"], x["label"]) for x in detail["people"])
        assets = tuple((x["id"], x["name"]) for x in detail["assets"] if not x["void"])
        fields = [
            Field(
                "effect",
                "Actual Feedback choice",
                (
                    ("bond", "Cut a real Bond and rewrite it as a Girl Asset"),
                    ("purpose", "Beg an actual person for purpose"),
                    ("tear", "Tear off an actual Asset and make a real reprisal"),
                    ("die", "Accept actual source death"),
                ),
            ),
            Field(
                "target", "Actual scene person (unless dying)", people, minimum=0, required=False
            ),
            Field(
                "asset",
                "If tearing: actual physically accessible owned Asset",
                assets,
                minimum=0,
                required=False,
            ),
            Field("name", "If rewriting a Bond: new Asset name", required=False),
            Field(
                "replace",
                "If at Girl Asset cap: replace an eligible Asset",
                tuple(
                    (x["id"], x["name"])
                    for x in detail["assets"]
                    if x["family"] == "girl" and not x["void"]
                ),
                minimum=0,
                required=False,
            ),
            Field("account", "Your actual source action or rewriting", paragraph=True),
        ]
    elif kind == "ankou_feedback_purpose":
        fields = [
            Field(
                "give",
                "Your own actual response",
                (("yes", "Give a purpose"), ("no", "Explicitly refuse")),
            ),
            Field("account", "Your actual purpose or explicit refusal", paragraph=True),
        ]
    elif kind == "ankou_feedback_identity":
        fields = [
            Field(
                "replace",
                "Only if at cap: actual ordinary Identity to replace",
                tuple((x["id"], x["name"]) for x in detail["identities"] if not x["protected"]),
                minimum=0,
                required=False,
            )
        ]
    else:
        fields = [
            Field(
                "context", "Your actual immediate Flirt against the source person", paragraph=True
            )
        ]

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        if kind == "ankou_feedback_child":
            from girlframe.engine.m3_actor_state import ActorRef

            target = ActorRef.model_validate(detail["target"])
            result = await asyncio.to_thread(
                game.begin,
                viewer_from_interaction(current),
                str(current.id),
                data["channel"],
                detail["sheet_revision"],
                PlayInput(
                    play="flirt",
                    parent=data["parent"],
                    source_work=detail["id"],
                    target=int(target.entity),
                    heat=detail["heat"],
                    context=values["context"],
                    trigger_confirmed=True,
                ),
            )
            return "Actual targeted reprisal prepared. Complete every real child choice. " + str(
                result["action_id"]
            )
        if kind == "ankou_feedback_choice":
            choice = values["effect"][0]
            specific = (
                {} if choice == "die" else {"target": next(iter(values.get("target", ())), "")}
            )
            if choice == "bond":
                specific["name"] = values.get("name", "")
                if values.get("replace"):
                    specific["replace"] = values["replace"][0]
            elif choice == "tear":
                specific["asset"] = next(iter(values.get("asset", ())), "")
            answer = ChoiceAnswer(options=(choice,), fields=specific, text=values["account"])
        elif kind == "ankou_feedback_purpose":
            answer = ChoiceAnswer(flag=values["give"][0] == "yes", text=values["account"])
        else:
            answer = ChoiceAnswer(
                fields={"replace": values["replace"][0]} if values.get("replace") else {}
            )
        await asyncio.to_thread(
            game.respond,
            viewer_from_interaction(current),
            str(current.id),
            identity,
            data["revision"],
            answer,
        )
        return "Your actual source decision is saved. No other person's response is inferred."

    await NativeForm(
        viewer.user_id,
        "Ankou: " + kind.removeprefix("ankou_feedback_"),
        "The actual mark and Heat were committed before dice. "
        "Use only your own source decisions; safety remains available. "
        + (detail.get("request") or "")
        + "\n"
        + (detail["purpose"] or ""),
        fields,
        submit,
    ).present(interaction)
