"""Owned Court choices and private original-person records; no synthetic replies."""

import asyncio
from typing import Any, cast

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.ledger import clean
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.m3_memory_pages import MemoryHistory
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine import m3_red_queen as rules
from girlframe.engine.m2 import ChoiceAnswer, PlayInput
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.services.m2_game import GameService
from girlframe.services.m3_red_queen import RedQueenService, personality_options, transfer_options

YES = (("yes", "Yes"), ("no", "No"))


async def _form(
    interaction: discord.Interaction,
    title: str,
    instructions: str,
    fields: list[Field],
    callback: Any,
) -> None:
    form = NativeForm(interaction.user.id, title, instructions, fields, callback)
    await reply(interaction, form.text(), form)


def _one(values: dict[str, Any], key: str, default: str = "") -> str:
    return str(values.get(key, (default,))[0])


def _readback(data: dict[str, Any]) -> str:
    value = data["source"]
    lines = [data["kind"].removeprefix("red_queen_").replace("_", " ").title()]
    lines.extend(
        label.title() + ": " + clean(text) for label, text in data.get("labels", {}).items()
    )
    for label in ("role", "text", "account", "instruction", "allegation", "consequence", "scope"):
        if value.get(label):
            lines.append(label.title() + ": " + clean(value[label]))
    lines.extend("Fictional memory: " + clean(x) for x in value.get("memories", ()))
    lines.extend(
        clean(key.removeprefix("answer:").removeprefix("return:")) + ": " + clean(text)
        for key, text in value.get("replies", {}).items()
        if key.startswith(("answer:", "return:"))
    )
    if "total" in value:
        lines.append("Actual completed roll total: " + str(value["total"]))
    lines.append(
        "Resolved"
        if any(value.get(x) for x in ("completed_event", "restored_event"))
        else "Saved; genuine source follow-ups remain visible in Requests."
    )
    return "\n\n".join(lines)


async def open_choice(
    interaction: discord.Interaction, game: GameService, decision: dict[str, Any]
) -> None:
    data, kind = decision["detail"], decision["kind"]
    fields = []
    if kind == "red_queen_consult":
        fields = [
            Field(
                "options",
                "AMs to recall and unmark",
                tuple((x["id"], x["label"]) for x in data["ams"]),
                minimum=data["minimum"],
                maximum=data["maximum"],
                required=bool(data["minimum"]),
            )
        ]
        if data["low"]:
            fields.append(
                Field(
                    "queen",
                    "Someone else receives the Queen",
                    tuple((x["id"], x["label"]) for x in data["targets"]),
                )
            )
        else:
            fields.append(Field("text", "Your actual Decree"))
            if data["high"]:
                fields.append(
                    Field(
                        "advice",
                        "Self-borne AM after recall to ask for advice",
                        tuple((x["id"], x["label"]) for x in data["ams"]),
                    )
                )
    elif kind in ("red_queen_questions", "red_queen_reciprocal"):
        fields = [
            Field(
                "options",
                "Your actual printed questions",
                tuple(tuple(x) for x in data["questions"]),
                minimum=data["minimum"],
                maximum=data["maximum"],
                required=bool(data["minimum"]),
            )
        ]
        if kind == "red_queen_questions":
            fields.append(
                Field("tag", "Optional observation Tag if your AM is assigned", required=False)
            )
    elif kind in ("red_queen_answers", "red_queen_reciprocal_answer"):
        fields = [Field("answer:" + key, text) for key, text in data["questions"]]
    elif kind == "red_queen_tag":
        fields = [
            Field("flag", "Give the noticed observer a Tag?", YES),
            Field("text", "Your actual optional Tag", required=False),
        ]
    elif kind in ("red_queen_memory_category", "red_queen_memory_handler"):
        fields = [
            Field("options", "Actual memory category", tuple(tuple(x) for x in data["categories"])),
            Field("text", "The actual person, place, day or time range"),
            Field(
                "years",
                "If time range: at least one year?",
                (("1+", "At least one year"), ("not_year", "Another category")),
            ),
        ]
        if kind == "red_queen_memory_category":
            fields.append(
                Field(
                    "am", "Your existing Court AM to install", tuple(tuple(x) for x in data["ams"])
                )
            )
    elif kind == "red_queen_memory_links":
        for index, category in enumerate(data["categories"]):
            fields += [
                Field(
                    f"memories{index}",
                    category["kind"].title() + ": actual fictional memories, one per line",
                ),
            ]
            if data["identities"]:
                fields.append(
                    Field(
                        f"identities{index}",
                        "All actual linked legal Identities",
                        tuple(tuple(x) for x in data["identities"]),
                        minimum=0,
                        maximum=len(data["identities"]),
                        required=False,
                    )
                )
    else:
        raise ValueError("Open this actual pending Court response")

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        supplied = {}
        for key, value in values.items():
            if key in ("options", "flag", "text"):
                continue
            if key.startswith("answer:"):
                supplied[key[7:]] = value
            elif key.startswith("identities"):
                supplied[key] = ",".join(value)
            elif isinstance(value, (tuple, list)):
                supplied[key] = value[0]
            else:
                supplied[key] = value
        answer = ChoiceAnswer(
            options=tuple(values.get("options", ())),
            fields=supplied,
            text=values.get("text", ""),
            flag=(_one(values, "flag") == "yes") if "flag" in values else None,
        )
        await asyncio.to_thread(
            game.respond,
            viewer_from_interaction(current),
            str(current.id),
            decision["id"],
            decision["revision"],
            answer,
        )
        return "Your actual owned Court response is saved."

    await _form(
        interaction,
        "The Red Queen",
        "Only your actual source role answers. Saved fictional memory does not alter OOC history.",
        fields,
        submit,
    )


async def _play(
    interaction: discord.Interaction, service: RedQueenService, menu: dict[str, Any], play: str
) -> None:
    fields = [
        Field(
            "heat", "Actual Heat to spend", tuple((str(x), str(x)) for x in range(menu["heat"] + 4))
        ),
        Field(
            "identity",
            "Optional own Identity to mark",
            (("none", "No Identity"), *tuple(tuple(x) for x in menu["identities"])),
        ),
        Field(
            "gain",
            "Heat from marking Identity",
            (("0", "None"), ("1", "1"), ("2", "2"), ("3", "3")),
        ),
        Field("context", "Actual performed source/trigger account"),
    ]
    if play != "red_queen_consult":
        fields.append(
            Field(
                "target",
                "Actual original target",
                tuple((x["id"], x["label"]) for x in menu["targets"] if x["ref"] != menu["actor"]),
            )
        )
        kind = "distant" if play == "red_queen_panopticon" else "brain"
        contexts = [x for x in menu["contexts"] if x["kind"] == kind]
        if not contexts:
            await reply(interaction, "Record the actual observation or brain-access source first.")
            return
        fields.append(
            Field("source", "Actual source facts", tuple((x["id"], x["label"]) for x in contexts))
        )

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        target = next(
            (
                ActorRef.model_validate(x["ref"])
                for x in menu["targets"]
                if x["id"] == _one(values, "target")
            ),
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
                context=values["context"],
                trigger_confirmed=True,
                heat=int(_one(values, "heat")),
                identity=None if _one(values, "identity") == "none" else _one(values, "identity"),
                gain=int(_one(values, "gain")),
                target_actor=target,
                source_work=_one(values, "source") or None,
            ),
        )
        return "Your actual Court Play is awaiting its real scene lock and roll."

    await _form(
        interaction,
        play.removeprefix("red_queen_").title(),
        "Perform the actual trigger; record truthful observation or brain access.",
        fields,
        submit,
    )


async def open_red_queen(
    interaction: discord.Interaction, service: RedQueenService, identity: str | None = None
) -> None:
    viewer = viewer_from_interaction(interaction)
    if identity:
        data = await asyncio.to_thread(service.view, viewer, identity)
        source = data["source"]
        if data["can_child"]:
            from girlframe.discord_adapter.m3_red_queen_support import open_mark_child

            await open_mark_child(interaction, service.game, identity)
            return
        if data["can_answer"]:

            async def answer(current: discord.Interaction, values: dict[str, Any]) -> str:
                await asyncio.to_thread(
                    service.answer_advice,
                    viewer_from_interaction(current),
                    str(current.id),
                    data["revision"],
                    identity,
                    values["instruction"],
                )
                return "Your actual advice is saved; required Court advice becomes a genuine Order."

            await _form(
                interaction,
                "Actual Court advice",
                "Author your own advice. No other person can supply your words.",
                [Field("instruction", "Your actual advice")],
                answer,
            )
            return
        if data["can_endorse"]:

            async def endorse(current: discord.Interaction, values: dict[str, Any]) -> str:
                await asyncio.to_thread(
                    service.endorse,
                    viewer_from_interaction(current),
                    str(current.id),
                    data["revision"],
                    identity,
                )
                return "The actual Director endorsement and genuine consequence are saved."

            await _form(
                interaction,
                "Director endorsement",
                clean(source["allegation"])
                + "\nRequested consequence: "
                + clean(source["consequence"]),
                [
                    Field(
                        "confirm",
                        "Actual Director endorsement",
                        (("endorse", "Endorse the required consequence"),),
                    )
                ],
                endorse,
            )
            return
        if data["can_restore"]:
            restoration = await asyncio.to_thread(service.restoration_options, viewer, identity)
            if restoration["options"]:

                async def restore(current: discord.Interaction, values: dict[str, Any]) -> str:
                    chosen = next(
                        x for x in restoration["options"] if x["id"] == _one(values, "association")
                    )
                    await asyncio.to_thread(
                        service.restore_memory,
                        viewer_from_interaction(current),
                        str(current.id),
                        restoration["revision"],
                        identity,
                        chosen["event"],
                        chosen["source"],
                        None if _one(values, "am") == "none" else _one(values, "am"),
                        values["account"],
                    )
                    return (
                        "Your actual source memory is restored; any chosen AM assignment is saved."
                    )

                await _form(
                    interaction,
                    "Restore fictional memory",
                    _readback(data),
                    [
                        Field(
                            "association",
                            "Your actual newly gained associated Identity or NPC Tag",
                            tuple((x["id"], x["label"]) for x in restoration["options"]),
                        ),
                        Field(
                            "am",
                            "Optional AM assignment",
                            (
                                ("none", "No AM assignment"),
                                *tuple(tuple(x) for x in restoration["ams"]),
                            ),
                        ),
                        Field(
                            "account",
                            "How this actual source Identity is associated with the lost memory",
                        ),
                    ],
                    restore,
                )
                return
        history = _readback(data)

        async def access(current: discord.Interaction) -> None:
            await asyncio.to_thread(service.view, viewer_from_interaction(current), identity)

        pages = MemoryHistory(interaction.user.id, history, access)
        await reply(interaction, pages.text(), pages)
        return
    menu = await asyncio.to_thread(service.menu, viewer, int(interaction.channel_id or 0))
    options = []
    if menu["can_initialize"]:
        options.append(("initialize", "Import actual accepted Court"))
    options.extend(
        ("play:" + play, play.removeprefix("red_queen_").replace("_", " ").title())
        for play, _ in menu["plays"]
    )
    options.extend(
        ("buy:" + x["id"], "Acquire " + x["label"])
        for x in menu["requisitions"]
        if not x["held"] or x["id"] == rules.ACCUSATION
    )
    for court in menu["courts"]:
        if court["can_mark"]:
            options.extend(
                ("mark:" + x["id"], "Mark " + x["label"])
                for x in court["ams"]
                if not x["marked_event"]
            )
    if menu["courts"]:
        options.extend(
            (
                ("context", "Record actual observation/access/watching"),
                ("transfer", "Transfer an actual self-borne AM"),
                ("copy", "Copy a newly Intense person"),
                ("breach", "Report an actual Decree breach"),
                ("accuse", "Erase an actual Biting Accusation"),
            )
        )
    if menu["judgements"]:
        options.append(("judge", "Judgement on High: lower actual Tag recipient Status"))
    options.extend(("saved:" + x["id"], x["label"]) for x in menu["tasks"])
    if not options:
        await reply(interaction, "No current owned Court control is available.")
        return

    async def select(current: discord.Interaction, values: dict[str, Any]) -> str | None:
        option = _one(values, "operation")
        if option == "initialize":
            await asyncio.to_thread(
                service.initialize,
                viewer_from_interaction(current),
                str(current.id),
                menu["revision"],
            )
            return "The genuine accepted Court and original people are imported."
        if option.startswith("saved:"):
            await open_red_queen(current, service, option[6:])
            return None
        if option.startswith("play:"):
            await _play(current, service, menu, option[5:])
            return None
        if option.startswith("buy:"):

            async def buy(latest: discord.Interaction, answers: dict[str, Any]) -> str:
                await asyncio.to_thread(
                    service.buy,
                    viewer_from_interaction(latest),
                    str(latest.id),
                    menu["revision"],
                    option[4:],
                    answers["account"],
                )
                return "The actual paid original-Frame Requisition is saved."

            await _form(
                current,
                "Acquire Court Requisition",
                "Costs two actual Permissions. Existing financial decision authority applies.",
                [Field("account", "Actual acquisition account")],
                buy,
            )
        elif option.startswith("mark:"):
            await _mark(current, service, menu, option[5:])
        else:
            await _operation(current, service, menu, option)
        return None

    await _form(
        interaction,
        "THE RED QUEEN",
        "Choose an actual source control or reopen your private saved record.",
        [Field("operation", "Your Court control", tuple(options))],
        select,
    )


async def _mark(
    interaction: discord.Interaction, service: RedQueenService, menu: dict[str, Any], am: str
) -> None:
    value = next(x for court in menu["courts"] for x in court["ams"] if x["id"] == am)
    ordinary = {
        "The Queen": (("status", "Raise actual Status"),),
        "The Consort": (("flirt", "Perform real Flirt"), ("bond", "Deepen actual Bond")),
        "The Knight": (("assault", "Perform real Assault"),),
        "The Doll": (("doll", "Next actual Disobey is 7 or less"),),
        "The Traitor": (("helpless", "Become actually Helpless"),),
    }
    kinds = ordinary.get(
        value["role"], (("modifier", "Apply copy +/-1 against original person"),)
    ) + (("order", "Regiment Commander remote Order"),)
    fields = [
        Field("kind", "Actual printed effect", kinds),
        Field(
            "counterpart",
            "Other actual person if required",
            (("none", "Not required"), *tuple((x["id"], x["label"]) for x in menu["targets"])),
        ),
        Field("instruction", "Actual direct instruction if Order", required=False),
        Field("amount", "Copy modifier if applicable", (("-1", "-1"), ("1", "+1"))),
        Field(
            "roll",
            "Actual pending Play if copy modifier",
            (
                ("none", "Not a copy modifier"),
                *tuple((x["id"], x["label"]) for x in menu["pending_rolls"]),
            ),
        ),
    ]

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        counterpart = next(
            (
                ActorRef.model_validate(x["ref"])
                for x in menu["targets"]
                if x["id"] == _one(values, "counterpart")
            ),
            None,
        )
        result = await asyncio.to_thread(
            service.mark,
            viewer_from_interaction(current),
            str(current.id),
            int(current.channel_id or 0),
            menu["revision"],
            am,
            cast(Any, _one(values, "kind")),
            counterpart=counterpart,
            instruction=values.get("instruction", ""),
            amount=int(_one(values, "amount")) if _one(values, "kind") == "modifier" else 0,
            roll=None if _one(values, "roll") == "none" else _one(values, "roll"),
        )
        return "Actual Court mark saved. Any real required Play or Order remains owed: " + str(
            result["id"]
        )

    await _form(
        interaction,
        "Mark " + value["role"],
        "Only the Queen marks. The bearer authors their own Play; OOC pause remains available.",
        fields,
        submit,
    )


async def _operation(
    interaction: discord.Interaction, service: RedQueenService, menu: dict[str, Any], operation: str
) -> None:
    targets = tuple((x["id"], x["label"]) for x in menu["targets"])
    ams = tuple((x["id"], x["label"]) for court in menu["courts"] for x in court["ams"])
    fields = []
    if operation == "context":
        fields = [
            Field(
                "court",
                "Actual source Red Queen",
                tuple((x["id"], x["label"]) for x in menu["courts"]),
            ),
            Field("target", "Actual subject", targets),
            Field(
                "kind",
                "Actual performed source",
                (
                    ("distant", "Observed from a distance"),
                    ("brain", "Actually restrained brain access"),
                    ("watching", "Handler actually watching"),
                ),
            ),
            Field("account", "Truthful factual account of actual source"),
        ]
    elif operation == "transfer":
        fields = [
            Field("am", "AM actually assigned to you", ams),
            Field("target", "Actual recipient", targets),
            Field(
                "kind",
                "Completed source",
                (
                    ("sex", "Actual completed Sex"),
                    ("bond", "Actual weakened Bond"),
                    ("punishment", "Actual higher-Status Punishment"),
                ),
            ),
            Field("account", "Actual source account"),
        ]
    elif operation == "copy":
        fields = [
            Field("target", "Actual newly Intense person", targets),
        ]
    elif operation == "breach":
        if not menu["decrees"]:
            await reply(interaction, "Create an actual Decree through Consult first.")
            return
        fields = [
            Field(
                "decree",
                "Your actual Decree",
                tuple((x["id"], x["label"]) for x in menu["decrees"]),
            ),
            Field("target", "Actual AM bearer who breached it", targets),
            Field("account", "Your actual interpreted breach"),
        ]
    elif operation == "judge":
        fields = [
            Field(
                "judgement",
                "Actual witnessed Tag",
                tuple((x["id"], x["label"]) for x in menu["judgements"]),
            )
        ]
    elif operation == "accuse":
        if (
            not menu["accusation_purchases"]
            or not menu["directors"]
            or not menu["accusation_targets"]
        ):
            await reply(
                interaction,
                "An actual unspent Accusation, source Director and real subject are required.",
            )
            return
        fields = [
            Field(
                "purchase",
                "Actual unspent Accusation",
                tuple((x["id"], x["label"]) for x in menu["accusation_purchases"]),
            ),
            Field(
                "target",
                "Actual accused subject",
                tuple((x["id"], x["label"]) for x in menu["accusation_targets"]),
            ),
            Field(
                "director",
                "Actual source Director",
                tuple((x["id"], x["label"]) for x in menu["directors"]),
            ),
            Field("allegation", "Your accusation considered true"),
            Field(
                "effect",
                "Desired supported consequence",
                (
                    ("punishment", "Actual Girl discipline"),
                    ("npc_tag", "Give the actual NPC a Tag"),
                    ("administrative_closure", "Actual City/Base administrative closure"),
                ),
            ),
            Field(
                "punishment",
                "Discipline kind if relevant",
                (("stimulant_injection", "Stimulant injection"), ("beating", "Beating")),
            ),
            Field("detail", "Actual NPC Tag or closure account", required=False),
            Field("consequence", "The desired consequence in your own words"),
        ]

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str | None:
        actual_viewer = viewer_from_interaction(current)
        target = next(
            (
                ActorRef.model_validate(x["ref"])
                for x in menu["targets"]
                if x["id"] == _one(values, "target")
            ),
            None,
        )
        if operation == "context":
            actor = ActorRef.model_validate(
                next(x["actor"] for x in menu["courts"] if x["id"] == _one(values, "court"))
            )
            assert target is not None
            result = await asyncio.to_thread(
                service.record_context,
                actual_viewer,
                str(current.id),
                int(current.channel_id or 0),
                menu["revision"],
                cast(Any, _one(values, "kind")),
                actor,
                target,
                values["account"],
            )
        elif operation in ("transfer", "copy"):
            assert target is not None
            from girlframe.services.m2_state import load_state

            def actual_options() -> list[dict[str, str]]:
                with service.store.engine.connect() as c:
                    state = load_state(c, service.store.campaign_id)
                    actor = ActorRef.model_validate(menu["actor"])
                    return (
                        transfer_options(
                            service.game, c, state, actor, target, cast(Any, _one(values, "kind"))
                        )
                        if operation == "transfer"
                        else personality_options(service.game, c, state, actor, target)
                    )

            sources = await asyncio.to_thread(actual_options)
            if not sources:
                raise ValueError(
                    "No actual qualifying completed source exists for these original people"
                )

            async def choose(latest: discord.Interaction, selection: dict[str, Any]) -> str:
                original = _one(selection, "source")
                if operation == "transfer":
                    outcome = await asyncio.to_thread(
                        service.transfer,
                        viewer_from_interaction(latest),
                        str(latest.id),
                        menu["revision"],
                        _one(values, "am"),
                        target,
                        original,
                        cast(Any, _one(values, "kind")),
                    )
                else:
                    outcome = await asyncio.to_thread(
                        service.copy_personality,
                        viewer_from_interaction(latest),
                        str(latest.id),
                        menu["revision"],
                        target,
                        original,
                    )
                return "The actual source-bound Court effect is saved: " + str(outcome["id"])

            await _form(
                current,
                "Choose actual completed source",
                "Choose the genuine original event; no action or relationship is invented.",
                [
                    Field(
                        "source",
                        "Actual qualifying source",
                        tuple((x["id"], x["label"]) for x in sources),
                    )
                ],
                choose,
            )
            return None
        elif operation == "breach":
            assert target is not None
            result = await asyncio.to_thread(
                service.report_breach,
                actual_viewer,
                str(current.id),
                menu["revision"],
                _one(values, "decree"),
                target,
                values["account"],
            )
        elif operation == "judge":
            chosen = next(x for x in menu["judgements"] if x["id"] == _one(values, "judgement"))
            result = await asyncio.to_thread(
                service.judge,
                actual_viewer,
                str(current.id),
                menu["revision"],
                chosen["context"],
                chosen["tag"],
            )
        else:
            accused = next(
                x for x in menu["accusation_targets"] if x["id"] == _one(values, "target")
            )
            director = next(x for x in menu["directors"] if x["id"] == _one(values, "director"))
            effect = _one(values, "effect")
            detail = (
                {"kind": _one(values, "punishment")}
                if effect == "punishment"
                else {"label": values.get("detail", "")}
                if effect == "npc_tag"
                else {"account": values.get("detail", "")}
            )
            result = await asyncio.to_thread(
                service.accuse,
                actual_viewer,
                str(current.id),
                menu["revision"],
                _one(values, "purchase"),
                cast(Any, accused["kind"]),
                accused["target"],
                values["allegation"],
                values["consequence"],
                consequence_kind=cast(Any, effect),
                consequence_detail=detail,
                director=ActorRef.model_validate(director["ref"]),
            )

        return "Your actual source is saved: " + str(result["id"])

    await _form(
        interaction,
        operation.replace("_", " ").title(),
        "Use actual original source records and human-authored facts.",
        fields,
        submit,
    )
