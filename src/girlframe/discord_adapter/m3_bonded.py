"""Actual Pair sources and privately owned Bonded choices."""

import asyncio
import json
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine import m3_bonded as rules
from girlframe.engine.m2 import ChoiceAnswer, PlayInput
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.services.m2_game import GameService
from girlframe.services.m3_bonded import BondedService


def _answer(values: dict[str, Any]) -> ChoiceAnswer:
    content = {
        k: v
        for k, v in values.items()
        if k not in ("options", "identities", "tags") and isinstance(v, str)
    }
    return ChoiceAnswer(
        options=values.get("options", ()),
        denied=values.get("identities", values.get("tags", ())),
        text=json.dumps(content),
    )


def _choice_fields(data: dict[str, Any]) -> list[Field]:
    kind = data["kind"]
    fields = []
    if data["options"]:
        fields.append(
            Field(
                "options",
                "Your actual printed choice",
                tuple(tuple(x) for x in data["options"]),
                minimum=0 if kind == "bonded_mid" else 1,
                maximum=data["maximum"],
                required=kind != "bonded_mid",
            )
        )
    if kind == "bonded_mid" or kind == "bonded_low":
        if data["identities"]:
            fields.append(
                Field(
                    "identities",
                    "Actual marked Identity cost (one per request / one if continuing)",
                    tuple((x["id"], x["label"]) for x in data["identities"]),
                    minimum=0,
                    maximum=min(4, len(data["identities"])),
                    required=False,
                )
            )
    if kind == "bonded_high" and data["tags"]:
        fields.append(
            Field(
                "tags",
                "Any of your actual Tags you give her; none is allowed",
                tuple((x["id"], x["label"]) for x in data["tags"]),
                minimum=0,
                maximum=len(data["tags"]),
                required=False,
            )
        )
    fields.append(Field("account", "Your actual words / performed outcome", paragraph=True))
    if kind == "bonded_side":
        fields.append(
            Field(
                "question", "If staying: ask when she comes for you", paragraph=True, required=False
            )
        )
        if data["tier"] == "high":
            fields.extend(
                [
                    Field("weapon_name", "If needed: actual found weapon name", required=False),
                    Field(
                        "weapon_description",
                        "If needed: actual found weapon description",
                        paragraph=True,
                        required=False,
                    ),
                ]
            )
    if kind == "bonded_reply":
        fields.append(
            Field(
                "content",
                "Your actual " + str(data.get("request") or "Tag") + " reply / performed change",
                paragraph=True,
                required=False,
            )
        )
    return fields


async def open_choice(
    interaction: discord.Interaction, game: GameService, decision: dict[str, Any]
) -> None:
    data = decision.get("bonded") or decision["detail"]

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        await asyncio.to_thread(
            game.respond,
            viewer_from_interaction(current),
            str(current.id),
            decision["id"],
            decision["revision"],
            _answer(values),
        )
        return (
            "Your actual owned response is saved. "
            "Separate requests and actual Orders keep their controls."
        )

    form = NativeForm(
        interaction.user.id,
        "Bonded: your actual response",
        "Author only your own words and actions. Actual Pair replies belong to her. "
        "OOC safety remains available.",
        _choice_fields(data),
        submit,
    )
    await reply(interaction, form.text(), form)


async def _play(
    interaction: discord.Interaction,
    game: GameService,
    *,
    play: str,
    source: str,
    context: str,
    target: ActorRef | None = None,
    delegated_target: ActorRef | None = None,
    channel: int | None = None,
    title: str = "Actual Bonded source Play",
) -> None:
    sheet = await asyncio.to_thread(game.sheet, viewer_from_interaction(interaction))
    identities = [x for x in sheet["identities"] if not x["marked"]]
    identities += [x for x in sheet.get("additional_identities", ()) if not x["marked"]]
    fields = [
        Field(
            "heat",
            "Actual Heat to spend",
            tuple((str(x), str(x)) for x in range(sheet["heat"] + 6)),
        )
    ]
    if identities:
        fields += [
            Field(
                "identity",
                "Optional actual unmarked Identity",
                tuple((x["id"], x["name"]) for x in identities),
                minimum=0,
                required=False,
            ),
            Field(
                "gain",
                "Heat from Identity (Paired exactly5)",
                tuple((str(x), str(x)) for x in (1, 2, 3, 5)),
            ),
            Field(
                "share",
                "Only Paired: Heat given to actual Pair",
                tuple((str(x), str(x)) for x in range(6)),
            ),
        ]
    fields.append(Field("context", "Actual legal trigger / performed source", paragraph=True))

    async def start(current: discord.Interaction, values: dict[str, Any]) -> str:
        prepared = PlayInput(
            play=play,
            source_work=source,
            heat=int(values["heat"][0]),
            identity=values.get("identity", (None,))[0] if values.get("identity") else None,
            gain=int(values.get("gain", ("1",))[0]) if values.get("identity") else 0,
            pair_share=int(values.get("share", ("0",))[0]),
            target=int(target.entity) if target else None,
            target_actor=delegated_target,
            context=context if target is not None else values["context"],
            trigger_confirmed=True,
        )
        result = await asyncio.to_thread(
            game.begin,
            viewer_from_interaction(current),
            str(current.id),
            channel if channel is not None else int(interaction.channel_id or 0),
            sheet["revision"],
            prepared,
        )
        return "Actual source Play prepared; resume its real roll/choices: " + str(
            result["action_id"]
        )

    form = NativeForm(
        interaction.user.id,
        title,
        "Use real resources and your actual trigger. Preparing does not perform the Play.",
        fields,
        start,
    )
    await reply(interaction, form.text(), form)


async def open_child(interaction: discord.Interaction, game: GameService, child_id: str) -> None:
    service = BondedService(game)
    menu = await asyncio.to_thread(service.menu, viewer_from_interaction(interaction), None)
    for row in menu["history"]:
        data = await asyncio.to_thread(
            service.view, viewer_from_interaction(interaction), row["id"]
        )
        child = data.get("child")
        if child and child["id"] == child_id:
            if child["child"]:
                await reply(
                    interaction,
                    "Resume the actual child Play through its saved controls: " + child["child"],
                )
            else:
                await _play(
                    interaction,
                    game,
                    play=child["play"],
                    source=child_id,
                    context=child["account"],
                    target=ActorRef.model_validate(child["target"]),
                    channel=data["channel"],
                )
            return
    await reply(interaction, "Open your original witnessed-affection source first.")


async def open_bonded(
    interaction: discord.Interaction, service: BondedService, identity: str | None = None
) -> None:
    viewer = viewer_from_interaction(interaction)
    channel = int(interaction.channel_id or 0)
    if identity is None:
        data = await asyncio.to_thread(service.menu, viewer, channel)
        options = [
            (
                x,
                {
                    "side": "Always By Her Side",
                    "intimacy": "Actual witnessed affection",
                    "sex": "Actual voluntary intimacy",
                }[x],
            )
            for x in data["available"]
        ]
        options += [(x["id"], x["label"]) for x in data["history"]]
        if not options:
            await reply(interaction, "No actual Bonded source or addressed private history here.")
            return

        async def pick(current: discord.Interaction, values: dict[str, Any]) -> str | None:
            kind = values["source"][0]
            if kind not in ("side", "intimacy", "sex"):
                await open_bonded(current, service, kind)
                return None
            people = [x for x in data["people"] if kind != "intimacy" or x["ref"] != data["pair"]]
            fields = []
            if kind == "side":
                fields.append(
                    Field(
                        "apart",
                        "Actual fiction: I want to be with her and we are apart",
                        (("yes", "Yes, we are actually apart"),),
                    )
                )
            if kind != "side":
                fields.append(
                    Field(
                        "person",
                        "Actual onlooker" if kind == "intimacy" else "Actual intimate partner",
                        tuple(
                            (ActorRef.model_validate(x["ref"]).token, x["label"]) for x in people
                        ),
                    )
                )
            if kind == "sex":
                fields.append(
                    Field(
                        "route",
                        "Actual source route",
                        (
                            ("pair", "With my actual Pair"),
                            ("seven", "With someone else: actual unrolled7- result"),
                            ("delegated", "With someone else: use my Pair's actual Sex rule"),
                        ),
                    )
                )
            if kind == "sex" and len(data.get("delegated_rules", ())) > 1:
                fields.append(
                    Field(
                        "delegated_rule",
                        "Only borrowed route: actual current Pair Sex rule",
                        tuple((x["id"], x["label"]) for x in data["delegated_rules"]),
                        minimum=0,
                        required=False,
                    )
                )
            fields.append(
                Field("account", "Your actual voluntary source / factual affection", paragraph=True)
            )

            async def propose(response: discord.Interaction, answer: dict[str, Any]) -> str:
                person = next(
                    (
                        ActorRef.model_validate(x["ref"])
                        for x in people
                        if ActorRef.model_validate(x["ref"]).token in answer.get("person", ())
                    ),
                    None,
                )
                result = await asyncio.to_thread(
                    service.propose,
                    viewer_from_interaction(response),
                    str(response.id),
                    channel,
                    data["revision"],
                    kind,
                    answer["account"],
                    target=person if kind == "sex" else None,
                    observer=person if kind == "intimacy" else None,
                    route=answer.get("route", ("pair",))[0],
                    apart=answer.get("apart") == ("yes",),
                    delegated_rule=answer.get("delegated_rule", (None,))[0]
                    if answer.get("delegated_rule")
                    else None,
                )
                return "Actual source saved; original people retain their choices: " + str(
                    result["id"]
                )

            form = NativeForm(
                current.user.id,
                "Actual Bonded source",
                "No consent, performance or private intention is inferred. "
                "Choose only actual original people.",
                fields,
                propose,
            )
            await reply(current, form.text(), form)
            return None

        form = NativeForm(
            viewer.user_id,
            "Bonded: actual Pair and private history",
            "Your actual source controls.",
            [Field("source", "Source", tuple(options))],
            pick,
        )
        await reply(interaction, form.text(), form)
        return
    data = await asyncio.to_thread(service.view, viewer, identity)
    summary = "Your actual " + data["kind"] + " source: " + data["phase"] + ". " + data["account"]
    if data.get("delegation"):
        summary += "\nActual delegated source: " + data["delegation"]["session"]
        if data["delegation"].get("action"):
            summary += " · actual Play " + data["delegation"]["action"]
    for detail in data["details"]:
        summary += "\n" + detail["kind"] + ": " + detail["account"]
    pause = data.get("pause")
    if pause:
        summary += "\nScene permission state: " + pause["state"]
        if pause.get("error"):
            summary += ". " + pause["error"]
    options = (
        [("retry_pause", "Retry actual scene permissions")] if pause and pause.get("retry") else []
    )
    if data.get("unrolled_gender"):
        options.append(("unrolled_gender", "Actual Animal Tag source / waiting state"))
    for flag, label in (
        ("confirm", "Your own voluntary participation response"),
        ("roll", "Actual source Play"),
        ("activate", "Record actual performed diceless source"),
        ("choose", "Your actual owned diceless outcome"),
        ("help", "Your genuine performed help"),
    ):
        if data.get("can_" + flag):
            options.append((flag, label))
    if data["child"]:
        options.append(("child", "Actual Play against the original onlooker"))
    if (
        data["route"] == "delegated"
        and data["phase"] in ("accepted", "bound", "complete")
        and viewer.user_id == int(data["actor"]["entity"])
    ):
        options.append(("delegated", "Use actual Pair-rule source without a copied person"))
    options += [("order:" + x["id"], "Issue your actual requested Order") for x in data["orders"]]
    if not options:
        await reply(
            interaction, summary + "\nResume actual pending rolled choices through Requests."
        )
        return

    async def operate(current: discord.Interaction, values: dict[str, Any]) -> str | None:
        operation = values["operation"][0]
        if operation == "retry_pause":
            from girlframe.services.p1_source_pause import retry

            await asyncio.to_thread(
                retry, service.game, viewer_from_interaction(current), str(current.id), identity
            )
            return "Actual scene permission restoration/retry queued. Reopen the source."
        if operation == "unrolled_gender":
            from girlframe.discord_adapter.p1_unrolled_sex import open_tasks

            await open_tasks(current, service.game, identity)
            return None
        if operation == "roll":
            await _play(
                current,
                service.game,
                play=rules.SIDE_PLAY if data["kind"] == "side" else rules.SEX_PLAY,
                source=identity,
                context=data["account"],
                channel=data["channel"],
            )
            return None
        if operation == "child":
            await open_child(current, service.game, data["child"]["id"])
            return None
        if operation == "delegated":
            from girlframe.discord_adapter.m3_bonded_support import open_delegated

            await open_delegated(current, service.game, identity)
            return None
        fields = [Field("account", "Your actual words / performed factual account", paragraph=True)]
        if operation == "confirm":
            fields.insert(
                0,
                Field(
                    "accept",
                    "Your actual voluntary choice",
                    (("yes", "Participate"), ("no", "Decline")),
                ),
            )
        if operation == "choose":
            fields.insert(
                0,
                Field(
                    "options",
                    "Your actual printed outcome",
                    tuple(tuple(x) for x in data["options"]),
                ),
            )
            if data["identities"]:
                fields.append(
                    Field(
                        "identities",
                        "If continuing: unmark your actual marked Identity",
                        tuple((x["id"], x["label"]) for x in data["identities"]),
                        minimum=0,
                        required=False,
                    )
                )
            if data["kind"] == "intimacy":
                fields += [
                    Field("tag", "If Tag: actual label", required=False),
                    Field(
                        "play",
                        "If making Play: actual source",
                        (("flirt", "Flirt"), ("brutalize", "Brutalize"), ("snoop", "Snoop")),
                        minimum=0,
                        required=False,
                    ),
                    Field(
                        "context",
                        "If making Play: actual legal trigger",
                        paragraph=True,
                        required=False,
                    ),
                ]

        async def submit(response: discord.Interaction, answer: dict[str, Any]) -> str:
            who, key = viewer_from_interaction(response), str(response.id)
            if operation == "confirm":
                await asyncio.to_thread(
                    service.confirm,
                    who,
                    key,
                    identity,
                    data["revision"],
                    answer["accept"][0] == "yes",
                    answer["account"],
                )
            elif operation == "choose":
                if isinstance(answer.get("play"), tuple):
                    answer["play"] = answer["play"][0] if answer["play"] else ""
                await asyncio.to_thread(
                    service.choose, who, key, identity, data["revision"], _answer(answer)
                )
            elif operation.startswith("order:"):
                detail = next(x for x in data["orders"] if x["id"] == operation[6:])
                await asyncio.to_thread(
                    service.game.issue_order,
                    who,
                    key,
                    data["channel"],
                    int(detail["target"]["entity"]),
                    detail["account"],
                )
            else:
                await asyncio.to_thread(
                    service.activate if operation == "activate" else service.help,
                    who,
                    key,
                    identity,
                    data["revision"],
                    answer["account"],
                )
            return "Your actual source response is saved; reopen it through Requests."

        form = NativeForm(current.user.id, "Bonded: " + operation, summary, fields, submit)
        await reply(current, form.text(), form)
        return None

    form = NativeForm(
        viewer.user_id,
        "Your actual Bonded source",
        summary,
        [Field("operation", "Actual source control", tuple(options))],
        operate,
    )
    await reply(interaction, form.text(), form)
