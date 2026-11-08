"""Original-owner Wyvern choices and lossless private table readback."""

import asyncio
import json
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.ledger import clean
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.m3_memory_pages import MemoryForm, MemoryHistory
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine import m3_wyvern as rules
from girlframe.engine.m2 import ChoiceAnswer, PlayInput
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.services.m2_game import GameService
from girlframe.services.m3_wyvern import WyvernService


def _readback(data: dict[str, Any]) -> str:
    lines = []
    for question in data.get("questions", ()):
        lines.append(clean(question["text"]))
        for answer in question.get("answers", ()):
            lines.append("Author " + str(answer["author"]) + ": " + clean(answer["text"]))
    for voice in data.get("voices", ()):
        lines.append("Author " + str(voice["author"]) + ": " + clean(voice["text"]))
    return "\n\n".join(lines)


def _saved_text(saved: dict[str, Any]) -> str:
    source, labels = saved["source"], saved["labels"]
    lines = [clean(saved["kind"].removeprefix("wyvern_").replace("_", " ").title())]
    if labels:
        lines.extend(clean(key.title() + ": " + value) for key, value in labels.items())
    for key in ("room", "name", "description", "answer", "rules_answer"):
        if source.get(key):
            lines.append(clean(source[key]))
    if source.get("play"):
        lines.append(clean(source["play"].removeprefix("wyvern_").replace("_", " ")))
        lines.append("Actual roll total: " + str(source["total"]))
    if source.get("target_frame"):
        lines.append("Strike target: the selected original parked Frame")
    if "stubborn" in source:
        lines.append("Cannot be dismissed" if source["stubborn"] else "Temporary mind")
    if "questions" in source and isinstance(source["questions"], list):
        if saved["kind"] == "wyvern_deep":
            lines.extend(clean(text) for text in source["questions"])
    if saved["kind"] == "wyvern_cargo":
        lines.append(
            "Unloaded"
            if source["ended_event"]
            else "Carried inside the Wyvern"
            if source["boarded_event"]
            else "Waiting for the actual Frame owner"
        )
    elif any(
        source.get(key)
        for key in (
            "completed_event",
            "ended_event",
            "returned_event",
            "gave_up_event",
            "closed_event",
        )
    ):
        lines.append("Resolved")
    else:
        lines.append("Saved; any required follow-ups remain pending")
    if content := _readback(saved):
        lines.append(content)
    return "\n\n".join(lines)


async def open_choice(
    interaction: discord.Interaction, game: GameService, decision: dict[str, Any]
) -> None:
    data, kind = decision["detail"], decision["kind"]
    if kind == "wyvern_child":
        from girlframe.discord_adapter.m2_ui import open_play

        await open_play(interaction, game, parent=decision)
        return
    fields = []
    if kind == "wyvern_questions":
        fields.append(
            Field(
                "options",
                "Your Frame questions",
                tuple(tuple(x) for x in data["questions"]),
                minimum=data["count"],
                maximum=data["count"],
            )
        )
        if data["danger"]:
            fields.append(
                Field(
                    "danger",
                    "Your return danger",
                    (
                        ("delay", "It takes time to return safely"),
                        ("escape", "A real Play is required to escape"),
                    ),
                )
            )
    elif kind in ("wyvern_unmark", "wyvern_rouse_cost"):
        if data["count"]:
            fields.append(
                Field(
                    "identities",
                    "Your actual Identities",
                    tuple(tuple(x) for x in data["identities"]),
                    minimum=data["count"],
                    maximum=data["count"],
                )
            )
        if data["heat"]:
            fields.append(
                Field("heat", "Heat you gain", tuple((str(x), str(x)) for x in range(1, 11)))
            )
    elif kind in ("wyvern_danger", "wyvern_wraith", "wyvern_shield_bond"):
        fields.append(Field("options", "Your choice", tuple(tuple(x) for x in data["options"])))
        if kind == "wyvern_wraith":
            fields.append(Field("name", "Name, if this mind has never been named", required=False))
    elif kind == "wyvern_wraith_rules":
        fields.extend(
            [
                Field(
                    "profile",
                    "Rules for this actual Frame mind",
                    (("frame_bound_npc", "Frame-bound NPC mind"),),
                ),
                Field("rules", "Your actual rules for this mind", paragraph=True),
            ]
        )
        if data["tag"]:
            fields.append(Field("tag", "Your Tag for the actual mind"))
    elif kind == "wyvern_answers_done":
        fields.append(
            Field(
                "confirm",
                "Close the answered Frame questions",
                (("close", "I have finished asking these answered questions"),),
            )
        )
    if kind != "wyvern_wraith_rules":
        fields.append(Field("account", "Your actual source account", paragraph=True))

    async def access(current: discord.Interaction) -> None:
        await asyncio.to_thread(game.decision, viewer_from_interaction(current), decision["id"])

    async def save(
        current: discord.Interaction,
        values: dict[str, Any],
        assignments: dict[str, str] | None = None,
    ) -> str:
        supplied: dict[str, str] = {}
        if values.get("danger"):
            supplied["danger"] = values["danger"][0]
        if kind == "wyvern_wraith" and values.get("name"):
            supplied["name"] = values["name"]
        if kind == "wyvern_wraith_rules":
            supplied = {}
            if values.get("tag"):
                supplied["tag"] = values["tag"]
        if assignments:
            supplied["mentor_tags"] = json.dumps(assignments)
        await asyncio.to_thread(
            game.respond,
            viewer_from_interaction(current),
            str(current.id),
            decision["id"],
            decision["revision"],
            ChoiceAnswer(
                options=tuple(values["profile"])
                if kind == "wyvern_wraith_rules"
                else ("done",)
                if kind == "wyvern_answers_done"
                else tuple(values.get("options", ())),
                denied=tuple(values.get("identities", ())),
                number=int(values["heat"][0]) if values.get("heat") else None,
                fields=supplied,
                text=values["rules"] if kind == "wyvern_wraith_rules" else values["account"],
            ),
        )
        return "Your actual Wyvern choice is saved."

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str | None:
        mentor_tags = data.get("requirements", {}).get("mentor_tags", ())
        erased = values.get("identities", ())
        if kind == "wyvern_rouse_cost" and mentor_tags and erased:
            # Assign actual original Mentor Tags to the exact selected erasures.
            async def mapped(latest: discord.Interaction, mapping: dict[str, Any]) -> str:
                return await save(
                    latest,
                    values,
                    {
                        identity: mapping[identity][0]
                        for identity in erased
                        if mapping[identity][0] != "none_remaining"
                    },
                )

            mapping_form = NativeForm(
                current.user.id,
                "Mentor Tags",
                "Choose in erasure order. Each actual Mentor Tag is consumed once; "
                "choose no remaining Tag only after earlier erasures consume them all.",
                [
                    Field(
                        identity,
                        "Mentor Tag for " + dict(data["identities"])[identity],
                        tuple((x["id"], x["label"]) for x in mentor_tags)
                        + (("none_remaining", "No Mentor Tag remains after earlier erasures"),),
                    )
                    for identity in erased
                ],
                mapped,
            )
            await reply(current, mapping_form.text(), mapping_form)
            return None
        return await save(current, values)

    instructions = (
        _readback(data) if kind == "wyvern_answers_done" else "Choose your own printed outcome."
    )
    form = MemoryForm(interaction.user.id, "WYVERN", instructions, fields, submit, authorize=access)
    await reply(interaction, form.text(), form)


async def _play(
    interaction: discord.Interaction,
    service: WyvernService,
    menu: dict[str, Any],
    play: str,
    party: str | None = None,
) -> None:
    fields = []
    if play == "wyvern_protector":
        fields.append(
            Field(
                "target",
                "The actual person you shield",
                tuple((x["token"], x["label"]) for x in menu["targets"]),
            )
        )
    fields.extend(
        [
            Field(
                "heat",
                "Actual Heat you spend",
                tuple((str(x), str(x)) for x in range(menu["heat"] + 1)),
            ),
            Field("account", "What you actually do", paragraph=True),
        ]
    )
    if menu["identities"]:
        fields.append(
            Field(
                "identity",
                "Optional Identity to mark",
                tuple(tuple(x) for x in menu["identities"]),
                minimum=0,
                required=False,
            )
        )
        fields.append(
            Field("gain", "Heat gained for marking", tuple((str(x), str(x)) for x in range(6)))
        )

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        ref = next(
            (x["ref"] for x in menu["targets"] if x["token"] == values.get("target", (None,))[0]),
            None,
        )
        await asyncio.to_thread(
            service.game.begin,
            viewer_from_interaction(current),
            str(current.id),
            int(current.channel_id or 0),
            menu["sheet_revision"],
            PlayInput(
                play=play,
                context=values["account"],
                trigger_confirmed=True,
                heat=int(values["heat"][0]),
                identity=values.get("identity", (None,))[0] if values.get("identity") else None,
                gain=int(values.get("gain", ("0",))[0]) if values.get("identity") else 0,
                target_actor=ActorRef.model_validate(ref) if ref else None,
                source_work=party,
            ),
        )
        return "Your Wyvern Play is confirmed."

    form = NativeForm(
        interaction.user.id, "WYVERN", "Confirm your actual source Play.", fields, submit
    )
    await reply(interaction, form.text(), form)


async def _purchase(
    interaction: discord.Interaction, service: WyvernService, menu: dict[str, Any], rule: str
) -> None:
    fields = [Field("account", "Your voluntary two-Permission purchase", paragraph=True)]
    if rule == rules.DEEP:
        fields.extend(
            [
                Field("first", "Your first new Frame question", paragraph=True),
                Field("second", "Your second new Frame question", paragraph=True),
            ]
        )
    if rule == rules.RENOVATE:
        fields.extend(
            [
                Field("room", "Which actual room you restore", paragraph=True),
                Field(
                    "kind",
                    "The object you find",
                    (
                        ("contraband", "A contraband object belonging to a previous Cadre"),
                        ("past", "An object from the Handler's past"),
                        ("void", "An object steeped in Void"),
                    ),
                ),
                Field("name", "Found Girl Asset name"),
                Field("description", "Found Girl Asset description", paragraph=True),
                Field(
                    "replace",
                    "If at cap: actual replaceable Girl Asset",
                    tuple(tuple(x) for x in menu.get("girl_replacements", ())),
                    minimum=0,
                    required=False,
                ),
            ]
            if menu.get("girl_replacements")
            else [
                Field("room", "Which actual room you restore", paragraph=True),
                Field(
                    "kind",
                    "The object you find",
                    (
                        ("contraband", "Previous Cadre contraband"),
                        ("past", "An object from the Handler's past"),
                        ("void", "An object steeped in Void"),
                    ),
                ),
                Field("name", "Found Girl Asset name"),
                Field("description", "Found Girl Asset description", paragraph=True),
            ]
        )

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        extra: dict[str, Any] = {}
        if rule == rules.DEEP:
            extra["questions"] = (values["first"], values["second"])
        elif rule == rules.RENOVATE:
            extra.update(
                room=values["room"],
                kind=values["kind"][0],
                name=values["name"],
                description=values["description"],
                replace=values.get("replace", (None,))[0] if values.get("replace") else None,
            )
        await asyncio.to_thread(
            service.purchase,
            viewer_from_interaction(current),
            str(current.id),
            menu["revision"],
            rule,
            values["account"],
            **extra,
        )
        return "Your actual two-Permission source acquisition is saved."

    form = NativeForm(
        interaction.user.id,
        "WYVERN Requisition",
        "Choose the actual printed acquisition.",
        fields,
        submit,
    )
    await reply(interaction, form.text(), form)


async def open_wyvern(
    interaction: discord.Interaction, service: WyvernService, identity: str | None = None
) -> None:
    viewer = viewer_from_interaction(interaction)
    if identity is not None:
        saved = await asyncio.to_thread(service.view, viewer, identity)
        source, kind = saved["source"], saved["kind"]

        async def access(current: discord.Interaction) -> None:
            await asyncio.to_thread(service.view, viewer_from_interaction(current), identity)

        fields = []
        form: NativeForm
        if kind == "wyvern_question" and not source["closed_event"]:
            fields = [Field("answer", "Your contribution as the Frame", paragraph=True)]

            async def answer(current: discord.Interaction, values: dict[str, Any]) -> str:
                await asyncio.to_thread(
                    service.answer,
                    viewer_from_interaction(current),
                    str(current.id),
                    identity,
                    saved["revision"],
                    values["answer"],
                )
                return "Your own Frame answer is saved with its author."

            form = MemoryForm(
                interaction.user.id,
                "Frame question",
                "Selected question: "
                + clean(source["text"])
                + "\n\nSaved Frame contributions:\n"
                + _readback(saved),
                fields,
                answer,
                authorize=access,
            )
            await reply(interaction, form.text(), form)
            return
        if kind == "wyvern_party" and not source["bound_action"]:
            owed = tuple(ActorRef.model_validate(x) for x in saved["owed_roles"])
            # Service proves every selected role's actual controller on submission.
            fields = (
                [
                    Field(
                        "roles",
                        "Your actual companion roles",
                        tuple((x.token, x.kind + ":" + x.entity) for x in owed),
                        minimum=1,
                        maximum=len(owed),
                    )
                ]
                if owed
                else []
            )
            if fields:

                async def attend(current: discord.Interaction, values: dict[str, Any]) -> str:
                    await asyncio.to_thread(
                        service.attend,
                        viewer_from_interaction(current),
                        str(current.id),
                        identity,
                        saved["revision"],
                        tuple(x for x in owed if x.token in values["roles"]),
                    )
                    return "Your actual companion attendance is saved."

                form = NativeForm(
                    interaction.user.id,
                    "Frame companions",
                    "Attend only the actual roles you control.",
                    fields,
                    attend,
                )
                await reply(interaction, form.text(), form)
            else:
                menu = await asyncio.to_thread(
                    service.menu, viewer, int(interaction.channel_id or 0)
                )
                await _play(interaction, service, menu, "wyvern_explore", identity)
            return
        if kind == "wyvern_danger" and source["kind"] == "delay" and not source["returned_event"]:

            async def elapsed(current: discord.Interaction, values: dict[str, Any]) -> str:
                await asyncio.to_thread(
                    service.elapsed,
                    viewer_from_interaction(current),
                    str(current.id),
                    identity,
                    saved["revision"],
                    values["account"],
                )
                return "The actual elapsed time and safe return are saved."

            form = NativeForm(
                interaction.user.id,
                "Return safely",
                "The original Handler records the actual time spent returning.",
                [Field("account", "Actual chronology of the delayed safe return", paragraph=True)],
                elapsed,
            )
            await reply(interaction, form.text(), form)
            return
        if (
            kind == "wyvern_shield"
            and source["high"]
            and not source["ended_event"]
            and saved.get("approachers")
        ):

            async def approach(current: discord.Interaction, values: dict[str, Any]) -> str:
                ref = next(
                    x["ref"] for x in saved["approachers"] if x["token"] == values["actor"][0]
                )
                await asyncio.to_thread(
                    service.approach,
                    viewer_from_interaction(current),
                    str(current.id),
                    identity,
                    saved["revision"],
                    ActorRef.model_validate(ref),
                    values["account"],
                )
                return "Your actual approach is recorded. Its own give-up choice is in your Inbox."

            form = NativeForm(
                interaction.user.id,
                "Shielded person",
                "Record only an actual approach by your own role.",
                [
                    Field(
                        "actor",
                        "Your actual approaching role",
                        tuple((x["token"], x["label"]) for x in saved["approachers"]),
                    ),
                    Field("account", "Your actual approach", paragraph=True),
                ],
                approach,
            )
            await reply(interaction, form.text(), form)
            return
        if (
            kind == "wyvern_renovation"
            and source["kind"] == "past"
            and not source["answered_event"]
            and viewer.user_id == source["handler_controller"]
        ):

            async def past(current: discord.Interaction, values: dict[str, Any]) -> str:
                await asyncio.to_thread(
                    service.past_answer,
                    viewer_from_interaction(current),
                    str(current.id),
                    identity,
                    saved["revision"],
                    values["answer"],
                )
                return "Your actual answer and found Asset are saved."

            form = NativeForm(
                interaction.user.id,
                "Object from your past",
                clean(source["name"]) + "\n" + clean(source["description"]),
                [Field("answer", "What is the object from your past?", paragraph=True)],
                past,
            )
            await reply(interaction, form.text(), form)
            return
        if kind == "wyvern_wraith" and source["active"]:
            options = [
                ("voice", "Play this actual mind"),
                ("control", "Take its actual rules control and play it"),
            ]
            if not source["stubborn"]:
                options.append(("dismiss", "I am done with this temporary mind"))

            async def mind(current: discord.Interaction, values: dict[str, Any]) -> str:
                option = values["operation"][0]
                if option == "dismiss":
                    await asyncio.to_thread(
                        service.dismiss,
                        viewer_from_interaction(current),
                        str(current.id),
                        identity,
                        saved["revision"],
                    )
                else:
                    await asyncio.to_thread(
                        service.voice,
                        viewer_from_interaction(current),
                        str(current.id),
                        identity,
                        saved["revision"],
                        values["text"],
                        take_control=option == "control",
                    )
                return "Your actual Frame mind source is saved."

            form = MemoryForm(
                interaction.user.id,
                source["name"],
                clean(source["rules_answer"]) + "\n\n" + _readback(saved),
                [
                    Field("operation", "Your source action", tuple(options)),
                    Field("text", "Your actual contribution", paragraph=True),
                ],
                mind,
                authorize=access,
            )
            await reply(interaction, form.text(), form)
            return
        if kind == "wyvern_cargo" and not source["ended_event"]:

            async def cargo(current: discord.Interaction, values: dict[str, Any]) -> str:
                method = service.unload if source["boarded_event"] else service.accept_cargo
                await asyncio.to_thread(
                    method,
                    viewer_from_interaction(current),
                    str(current.id),
                    identity,
                    saved["revision"],
                )
                return "Your actual physical Frame carriage is saved."

            form = NativeForm(
                interaction.user.id,
                "Frame carriage",
                "Confirm the actual Frame operation.",
                [
                    Field(
                        "operation",
                        "Your actual operation",
                        (
                            (
                                "confirm",
                                "Unload the held Frame"
                                if source["boarded_event"]
                                else "Authorize boarding my actual Frame",
                            ),
                        ),
                    )
                ],
                cargo,
            )
            await reply(interaction, form.text(), form)
            return
        if kind == "wyvern_approach" and not source["gave_up_event"]:

            async def giveup(current: discord.Interaction, values: dict[str, Any]) -> str:
                await asyncio.to_thread(
                    service.give_up,
                    viewer_from_interaction(current),
                    str(current.id),
                    identity,
                    saved["revision"],
                    tag=values.get("tag") or None,
                )
                return "Your own actual decision to give up is saved."

            form = NativeForm(
                interaction.user.id,
                "Hopeless approach",
                "Choose to give up; you may give the Wyvern a Tag.",
                [
                    Field(
                        "confirm", "Your actual decision", (("give_up", "I give up this approach"),)
                    ),
                    Field("tag", "Optional Tag you give the Wyvern", required=False),
                ],
                giveup,
            )
            await reply(interaction, form.text(), form)
            return
        history = _saved_text(saved)
        form_history = MemoryHistory(interaction.user.id, history, access)
        await reply(interaction, form_history.text(), form_history)
        return
    menu = await asyncio.to_thread(service.menu, viewer, int(interaction.channel_id or 0))
    options = [
        ("play:" + play, play.removeprefix("wyvern_").replace("_", " "))
        for play, _ in menu["plays"]
    ]
    options += [
        ("buy:" + x["id"], "Acquire " + x["id"].rsplit(".", 1)[-1])
        for x in menu["requisitions"]
        if not x["held"] or x["id"] == rules.RENOVATE
    ]
    options += [
        ("party", "Declare Frame exploration companions"),
        ("cargo", "Offer to carry another actual Frame"),
    ]
    if menu["roused"]:
        options.append(("roused", "Use the actual Roused Frame"))
    options += [("saved:" + x["id"], x["label"]) for x in menu["tasks"]]

    async def select(current: discord.Interaction, values: dict[str, Any]) -> None:
        operation = values["operation"][0]
        if operation.startswith("saved:"):
            await open_wyvern(current, service, operation[6:])
        elif operation.startswith("buy:"):
            await _purchase(current, service, menu, operation[4:])
        elif operation.startswith("play:"):
            play = operation[5:]
            if play == "wyvern_explore":
                await _party(current, service, menu)
            else:
                await _play(current, service, menu, play)
        elif operation == "party":
            await _party(current, service, menu)
        elif operation == "cargo":
            await _cargo(current, service, menu)
        else:
            await _roused(current, service, menu)
        return None

    form = NativeForm(
        interaction.user.id,
        "WYVERN",
        "Choose your actual Frame source.",
        [Field("operation", "Your source action", tuple(options))],
        select,
    )
    await reply(interaction, form.text(), form)


async def _party(
    interaction: discord.Interaction, service: WyvernService, menu: dict[str, Any]
) -> None:
    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        refs = tuple(
            ActorRef.model_validate(x["ref"])
            for x in menu["targets"]
            if x["token"] in values.get("companions", ())
        )
        result = await asyncio.to_thread(
            service.party,
            viewer_from_interaction(current),
            str(current.id),
            int(current.channel_id or 0),
            menu["revision"],
            refs,
        )
        return (
            "Your party is saved. Each other controller attends their actual role; reopen "
            + str(result["id"])
            + " to continue."
        )

    fields = (
        [
            Field(
                "companions",
                "The actual companions you bring",
                tuple((x["token"], x["label"]) for x in menu["targets"]),
                minimum=0,
                maximum=len(menu["targets"]),
                required=False,
            )
        ]
        if menu["targets"]
        else [Field("alone", "Your party", (("alone", "I explore alone"),))]
    )
    form = NativeForm(
        interaction.user.id,
        "Explore the Frame",
        "Declare the real exploration party.",
        fields,
        submit,
    )
    await reply(interaction, form.text(), form)


async def _cargo(
    interaction: discord.Interaction, service: WyvernService, menu: dict[str, Any]
) -> None:
    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        ref = next(x["ref"] for x in menu["targets"] if x["token"] == values["target"][0])
        await asyncio.to_thread(
            service.propose_cargo,
            viewer_from_interaction(current),
            str(current.id),
            int(current.channel_id or 0),
            menu["revision"],
            ActorRef.model_validate(ref),
        )
        return "The actual Frame owner has a carriage offer."

    form = NativeForm(
        interaction.user.id,
        "Frame carriage",
        "Offer to carry another genuine Vital Frame.",
        [
            Field(
                "target",
                "The actual Frame owner",
                tuple((x["token"], x["label"]) for x in menu["targets"]),
            )
        ],
        submit,
    )
    await reply(interaction, form.text(), form)


async def _roused(
    interaction: discord.Interaction, service: WyvernService, menu: dict[str, Any]
) -> None:
    # Actual target Assets and incoming sources are discovered by the service.
    data = await asyncio.to_thread(
        service.roused_options,
        viewer_from_interaction(interaction),
        int(interaction.channel_id or 0),
    )
    options = [(x["id"], x["label"]) for x in data["options"]]

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        chosen = next(x for x in data["options"] if x["id"] == values["use"][0])
        await asyncio.to_thread(
            service.use_roused,
            viewer_from_interaction(current),
            str(current.id),
            int(current.channel_id or 0),
            data["revision"],
            ActorRef.model_validate(chosen["target"]),
            chosen["kind"],
            asset=chosen.get("asset"),
            target_frame=chosen.get("target_frame"),
            incoming=chosen.get("incoming"),
        )
        return "Your actual Roused effect is committed once."

    form = NativeForm(
        interaction.user.id,
        "Roused Frame",
        "Choose one actual use of your Roused Frame.",
        [Field("use", "The actual effect", tuple(options))],
        submit,
    )
    await reply(interaction, form.text(), form)
