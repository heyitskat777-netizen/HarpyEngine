"""Actual Ankou source controls, owned replies and private saved records."""

import asyncio
from typing import Any, Literal, cast

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.ledger import clean
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.m3_memory_pages import MemoryHistory
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine import m3_ankou as rules
from girlframe.engine.m2 import ChoiceAnswer, PlayInput
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.services import m3_ankou_feedback_sequences as sequences
from girlframe.services.m2_game import GameService
from girlframe.services.m3_ankou import AnkouService
from girlframe.services.onboarding import WorkflowError

YES = (("yes", "Yes"), ("no", "No"))


def _one(values: dict[str, Any], key: str, default: str = "") -> str:
    return str(values.get(key, (default,))[0])


async def _form(
    interaction: discord.Interaction, title: str, account: str, fields: list[Field], callback: Any
) -> None:
    form = NativeForm(interaction.user.id, title, account, fields, callback)
    await reply(interaction, form.text(), form)


async def open_choice(
    interaction: discord.Interaction, game: GameService, decision: dict[str, Any]
) -> None:
    detail, kind = decision["detail"], decision["kind"]
    fields = []
    if kind == "ankou_processor_benefits":
        entries = tuple((x["id"], x["label"]) for x in detail["identities"])
        unmarked = tuple((x["id"], x["label"]) for x in detail["identities"] if x["marked"])
        assets = (("none", "No cap replacement"),) + tuple(
            (x["id"], x["label"]) for x in detail["assets"]
        )
        for n in range(detail["count"]):
            fields.append(
                Field(
                    "benefit" + str(n),
                    "Benefit " + str(n + 1),
                    tuple((x, x.title()) for x in detail["benefits"]),
                )
            )
            if entries:
                fields.append(
                    Field(
                        "erase" + str(n),
                        "If Identity benefit: erase",
                        (("none", "Not selected"),) + entries,
                        required=False,
                    )
                )
            if unmarked:
                fields.append(
                    Field(
                        "unmark" + str(n),
                        "If Identity benefit: unmark different",
                        (("none", "Not selected"),) + unmarked,
                        required=False,
                    )
                )
            fields.append(
                Field(
                    "gain" + str(n),
                    "If Identity benefit: actual Heat gain",
                    tuple((str(x), str(x)) for x in (1, 2, 3)),
                    required=False,
                )
            )
            fields.append(
                Field(
                    "replace" + str(n),
                    "If temporary Asset: cap replacement",
                    assets,
                    required=False,
                )
            )
    elif kind == "ankou_processor_symptoms":
        fields = [
            Field(
                "options",
                "Actual processor symptoms",
                tuple((x, x) for x in detail["symptoms"]),
                minimum=detail["symptom_count"],
                maximum=detail["symptom_count"],
            )
        ]
    elif kind == "ankou_interrupt":
        fields = [
            Field("accept", "Erase an actual Tag and attempt an interrupt?", YES),
            Field(
                "play",
                "Actual interrupt Play",
                tuple((x, x.replace("_", " ")) for x in detail["plays"]),
            ),
            Field("text", "Actual account"),
        ]
        if detail["tags"]:
            fields.append(
                Field(
                    "tag",
                    "Actual acting-person Tag",
                    tuple((x["id"], x["label"]) for x in detail["tags"]),
                )
            )
    elif kind == "ankou_interrupt_child":
        from girlframe.discord_adapter.m2_ui import open_pending

        if detail.get("child"):
            await open_pending(interaction, game)
        else:
            await open_ankou(interaction, AnkouService(game), detail["source"])
        return
    else:
        raise WorkflowError("Use an actual Ankou result source")

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> None:
        actual: dict[str, str] = {}
        if kind == "ankou_processor_benefits":
            options = tuple(_one(values, "benefit" + str(n)) for n in range(detail["count"]))
            for n, option in enumerate(options):
                for key in (
                    ("erase", "unmark", "gain")
                    if option == "identity"
                    else ("replace",)
                    if option in ("eyes", "will")
                    else ()
                ):
                    value = _one(values, key + str(n))
                    if value and value != "none":
                        actual[key + str(n)] = value
            answer = ChoiceAnswer(options=options, fields=actual)
        elif kind == "ankou_processor_symptoms":
            answer = ChoiceAnswer(options=tuple(values["options"]))
        else:
            accepted = _one(values, "accept") == "yes"
            answer = ChoiceAnswer(
                flag=accepted,
                options=(_one(values, "play"),) if accepted else (),
                fields=dict(tag=_one(values, "tag")) if accepted else {},
                text=values.get("text", ""),
            )
        await asyncio.to_thread(
            game.respond,
            viewer_from_interaction(current),
            str(current.id),
            decision["id"],
            decision["revision"],
            answer,
        )
        await reply(
            current, "Actual source result saved. Reopen Requests for real outstanding work."
        )

    await _form(
        interaction,
        "Ankou — " + kind.removeprefix("ankou_"),
        "Choose the actual owned printed outcome; no recipient reply is invented.",
        fields,
        submit,
    )


async def open_ankou(
    interaction: discord.Interaction, service: AnkouService, identity: str | None = None
) -> None:
    viewer = viewer_from_interaction(interaction)
    if identity:
        data = await asyncio.to_thread(service.view, viewer, identity)
        await _record(interaction, service, data)
        return
    channel = interaction.channel_id
    if channel is None:
        raise WorkflowError("Open Ankou in an actual joined scene channel")
    menu = await asyncio.to_thread(service.menu, viewer, channel)
    options: list[tuple[str, str]] = []
    if menu["frame"]:
        options.extend(
            (
                ("processor", "Processor Core"),
                ("relay", "Activate Emotional Relay"),
                ("buy", "Acquire a printed Requisition"),
                ("obsession", "Choose actual Obsession"),
                ("encounter", "Record actual touch/seeing/private-spying context"),
                ("quickchange", "Quickchange at actual Go Off-Duty"),
                ("stalker", "Stalker actual location"),
                ("request_source", "Ask the actual source person for factual context/disclosure"),
            )
        )
    options.extend(("record:" + x["id"], x["label"]) for x in menu["tasks"])
    if not options:
        await reply(interaction, "No actual owned Ankou source or addressed work is recorded.")
        return

    async def select(current: discord.Interaction, values: dict[str, Any]) -> None:
        selected = _one(values, "operation")
        if selected.startswith("record:"):
            await open_ankou(current, service, selected.removeprefix("record:"))
        else:
            await _operation(current, service, menu, selected)

    await _form(
        interaction,
        "PROJECT ANKOU",
        "Actual source choices and durable private history.",
        [Field("operation", "Control", tuple(options))],
        select,
    )


async def _operation(
    interaction: discord.Interaction, service: AnkouService, menu: dict[str, Any], operation: str
) -> None:
    channel = interaction.channel_id
    if channel is None:
        raise WorkflowError("Use the actual joined source scene channel")
    people = menu.get("known_people", menu["people"])
    refs = {x["id"]: ActorRef.model_validate(x["ref"]) for x in people}
    person_fields = tuple((x["id"], x["label"]) for x in people)
    fields = [Field("account", "Actual source account")]
    if operation == "processor":
        fields = [
            Field(
                "heat",
                "Actual Heat to spend",
                tuple((str(x), str(x)) for x in range(menu["heat"] + 1)),
            ),
            Field(
                "identity",
                "Optional actual Identity mark",
                (("none", "No mark"),)
                + tuple((x["id"], x["label"]) for x in menu["identities"] if not x["marked"]),
            ),
            Field("gain", "Heat from actual mark", tuple((str(x), str(x)) for x in (1, 2, 3))),
            Field("cadre", "Exempt your actual Cadre?", YES),
            Field(
                "exempt",
                "One additional exempt person",
                (("none", "No additional exemption"),)
                + tuple((x["id"], x["label"]) for x in menu["people"]),
            ),
            *fields,
        ]
    elif operation == "relay":
        fields = [
            Field(
                "benefits",
                "Two actual scene benefits",
                tuple((x, x.title()) for x in rules.BENEFITS),
                minimum=2,
                maximum=2,
            ),
            *fields,
        ]
    elif operation == "buy":
        fields = [
            Field(
                "rule",
                "Actual new Requisition",
                tuple(
                    (x, x.removeprefix(rules.PREFIX).replace("-", " "))
                    for x in rules.REQUISITIONS
                    if x not in menu["held"]
                ),
            ),
            *fields,
        ]
    elif operation in ("obsession", "stalker"):
        if not person_fields:
            raise WorkflowError("Establish actual known source people first")
        fields = [Field("person", "Actual original person", person_fields), *fields]
    elif operation == "encounter":
        fields = [
            Field("person", "Actual original other person", person_fields),
            Field(
                "kind",
                "Factual interaction",
                (
                    ("touch", "Actual touch"),
                    ("seen", "Actually saw them"),
                    ("spy", "Target's actual expectation of privacy"),
                ),
            ),
            Field("period", "Actual Off-Duty period, if sighting", required=False),
            Field("private", "Target actually expects privacy?", YES),
            *fields,
        ]
    elif operation == "request_source":
        fields = [
            Field("person", "Actual original source person", person_fields),
            Field(
                "kind",
                "Source request",
                (
                    ("disclosure", "Actual Identity/Tag source disclosure"),
                    ("spy_context", "Target's actual expectation of privacy"),
                    ("company", "Actual Stalker companionship"),
                ),
            ),
            *fields,
        ]
    elif operation == "quickchange":
        if not menu["periods"]:
            raise WorkflowError("Use the actual active GoOffDuty opportunity")
        fields = [
            Field("period", "Actual period", tuple((x["id"], x["label"]) for x in menu["periods"])),
            Field(
                "erase",
                "Optional actual Identity erasure",
                (("none", "No erasure"),)
                + tuple((x["id"], x["label"]) for x in menu["identities"]),
            ),
            Field(
                "resource",
                "Actual disclosed source",
                (("none", "No writing"),) + tuple((x["id"], x["label"]) for x in menu["disclosed"]),
            ),
            *fields,
        ]

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> None:
        viewer = viewer_from_interaction(current)
        key = str(current.id)
        account = values.get("account", "")
        if operation == "processor":
            exempt = _one(values, "exempt")
            proposed = await asyncio.to_thread(
                service.propose_processor,
                viewer,
                key + ":proposal",
                channel,
                menu["revision"],
                account,
                exempt_cadre=_one(values, "cadre") == "yes",
                exempt=refs.get(exempt),
            )
            latest = await asyncio.to_thread(service.menu, viewer, channel)
            identity = _one(values, "identity")
            result = await asyncio.to_thread(
                service.game.begin,
                viewer,
                key,
                channel,
                latest["sheet_revision"],
                PlayInput(
                    play=rules.PLAY,
                    trigger_confirmed=True,
                    context=account,
                    heat=int(_one(values, "heat")),
                    identity=identity if identity != "none" else None,
                    gain=int(_one(values, "gain")) if identity != "none" else 0,
                    source_work=proposed["id"],
                ),
            )
        elif operation == "relay":
            result = await asyncio.to_thread(
                service.activate_relay,
                viewer,
                key,
                channel,
                menu["revision"],
                tuple(values["benefits"]),
                account,
            )
        elif operation == "buy":
            result = await asyncio.to_thread(
                service.buy, viewer, key, menu["revision"], _one(values, "rule"), account
            )
        elif operation == "obsession":
            result = await asyncio.to_thread(
                service.choose_obsession,
                viewer,
                key,
                menu["revision"],
                refs[_one(values, "person")],
                account,
            )
        elif operation == "stalker":
            from girlframe.services.m2_state import load_state
            from girlframe.services.m3_ankou import stalker_view

            with service.store.engine.connect() as c:
                result = stalker_view(
                    service.game,
                    c,
                    load_state(c, service.store.campaign_id),
                    ActorRef.model_validate(menu["actor"]),
                    refs[_one(values, "person")],
                )
            await reply(current, "Actual source-authorized location: " + clean(str(result)))
            return
        elif operation == "encounter":
            result = await asyncio.to_thread(
                service.encounter,
                viewer,
                key,
                channel,
                menu["revision"],
                ActorRef.model_validate(menu["actor"]),
                refs[_one(values, "person")],
                cast(Literal["touch", "spy", "seen"], _one(values, "kind")),
                account,
                period=values.get("period") or None,
                thinks_private=_one(values, "private") == "yes",
            )
        elif operation == "request_source":
            from girlframe.services.m3_ankou import request_source

            result = await asyncio.to_thread(
                request_source,
                service.game,
                viewer,
                key,
                menu["revision"],
                channel,
                refs[_one(values, "person")],
                cast(Literal["disclosure", "spy_context", "company"], _one(values, "kind")),
                account,
            )
        elif operation == "quickchange":
            selected = next(
                (x for x in menu["disclosed"] if x["id"] == _one(values, "resource")), None
            )
            result = await asyncio.to_thread(
                service.quickchange,
                viewer,
                key,
                menu["revision"],
                _one(values, "period"),
                erase=None if _one(values, "erase") == "none" else _one(values, "erase"),
                source_person=ActorRef.model_validate(selected["person"]) if selected else None,
                source_identity=selected["id"]
                if selected and selected["kind"] == "identity"
                else None,
                source_tag=selected["id"] if selected and selected["kind"] == "tag" else None,
                account=account,
            )
        else:
            raise WorkflowError("Use an actual source control")
        await reply(
            current,
            "Actual source saved: "
            + str(result.get("id", result.get("action_id", "")))
            + ". Use /choice resume or Requests for owned work.",
        )

    await _form(
        interaction,
        "Ankou — " + operation,
        "Record the real source and actual human choices; no performance is invented.",
        fields,
        submit,
    )


async def _record(
    interaction: discord.Interaction, service: AnkouService, data: dict[str, Any]
) -> None:
    source = data["source"]
    options: list[tuple[str, str]] = []
    if data.get("can_unlink"):
        options.append(("unlink", "Actually unlink processors"))
    if data.get("can_activate"):
        options.append(("activate", "Activate outstanding Feedback in this joined free scene"))
    if data.get("step"):
        options.append(("step", "Open current actual Feedback step"))
    if data.get("can_choose"):
        options.append(("choose", "Answer actual owned source"))
    if data.get("can_answer"):
        options.append(("purpose", "Author actual response to begged purpose"))
    if data.get("can_write"):
        options.append(("write", "Write actual given purpose"))
    if data.get("counter"):
        options.append(("child", "Perform actual required Play"))
    if data.get("can_resume"):
        options.append(("resume", "Resume actual child"))
    if data.get("pause", {}).get("retry"):
        options.append(("pause", "Retry actual scene permission pause/restore"))
    for name, label in (
        ("speak", "Actual head-speech"),
        ("touch", "Actual touch and self-Asset damage"),
        ("sense", "Sense vague actual locations"),
        ("tag", "Give actual source Tag"),
        ("npc_off_duty", "Record this NPC's actual GoOffDuty"),
    ):
        if data.get("can_" + name):
            options.append((name, label))
    if data.get("can_save_notice"):
        options.append(("save_notice", "Save addressed notice to private history"))
    options.append(("history", "Private saved source"))

    async def select(current: discord.Interaction, values: dict[str, Any]) -> None:
        choice = _one(values, "operation")
        if choice == "save_notice":
            from girlframe.services.m3_ankou import save_notice

            await asyncio.to_thread(
                save_notice,
                service.game,
                viewer_from_interaction(current),
                str(current.id),
                data["revision"],
                data["id"],
            )
            await open_ankou(current, service, data["id"])
            return
        if choice == "history":

            async def access(current: discord.Interaction) -> None:
                await asyncio.to_thread(service.view, viewer_from_interaction(current), data["id"])

            view = MemoryHistory(current.user.id, clean(json_text(source)), access)
            await reply(current, view.text(), view)
            return
        if choice == "step":
            await open_ankou(current, service, data["step"])
            return
        if choice == "resume":
            from girlframe.discord_adapter.m2_ui import open_pending

            await open_pending(current, service.game)
            return
        if choice == "child":
            await _child(current, service.game, data["counter"])
            return
        if choice == "pause":
            from girlframe.services.p1_source_pause import retry

            await asyncio.to_thread(
                retry,
                service.game,
                viewer_from_interaction(current),
                str(current.id),
                source.get("sequence", data["id"]),
            )
            await open_ankou(current, service, data["id"])
            return
        if choice == "sense":
            from girlframe.services.m2_state import load_state
            from girlframe.services.m3_ankou import sense_view

            with service.store.engine.connect() as c:
                sensed = sense_view(
                    service.game,
                    c,
                    load_state(c, service.store.campaign_id),
                    ActorRef.model_validate(source["actor"]),
                    data["id"],
                )
            await reply(current, "Vague sensed locations: " + clean(str(sensed)))
            return
        fields = [Field("account", "Actual source account")]
        if choice == "speak":
            fields.insert(
                0,
                Field(
                    "person",
                    "Actual recipient in range",
                    tuple((x["id"], x["label"]) for x in data["people"]),
                ),
            )
        elif choice == "touch":
            fields = [
                Field(
                    "encounter",
                    "Actual authored touch",
                    tuple((x["id"], x["label"]) for x in data["encounters"]),
                ),
                Field(
                    "asset",
                    "Actual self-Asset damage",
                    tuple((x["id"], x["label"]) for x in data["assets"]),
                ),
                *fields,
            ]
        elif choice == "tag":
            fields.insert(0, Field("label", "Actual source Tag"))
        if choice == "choose" and data["kind"] == "relay":
            fields.insert(
                0,
                Field(
                    "choice",
                    "Handler chooses one consequence",
                    (
                        ("death", "Hear actual NPC deaths"),
                        ("nominees", "Intense partners nominate actual Plays"),
                        ("feedback", "Actual Feedback Loop"),
                    ),
                ),
            )
        elif choice == "choose" and data["kind"] == "task":
            task_kind = source["kind"]
            available = (
                ("fight", "fawn")
                if task_kind == "fight_fawn"
                else ("seen", "not_seen")
                if task_kind == "missed_obsession"
                else tuple(data["nomination_options"])
                if task_kind == "nominate"
                else ("answer",)
            )
            fields.insert(
                0,
                Field(
                    "choice",
                    "Actual owned outcome",
                    tuple((x, x.replace("_", " ")) for x in available),
                ),
            )
            if task_kind == "death_identity":
                fields.append(Field("erase", "Actual eligible Identity to erase"))
            if task_kind == "disclosure":
                fields = [
                    Field(
                        "choice",
                        "Actual resource to disclose",
                        tuple((x["id"], x["label"]) for x in data["resources"]),
                    ),
                    Field("account", "Actual disclosure account"),
                ]
            elif task_kind == "spy_context":
                fields = [
                    Field(
                        "choice", "Did you actually think you were doing something private?", YES
                    ),
                    Field("account", "Your actual factual account"),
                ]
            elif task_kind == "company":
                fields = [
                    Field(
                        "companions",
                        "Actual physical companions",
                        (("none", "Nobody"),)
                        + tuple((x["id"], x["label"]) for x in data["company_options"]),
                        minimum=1,
                        maximum=max(1, len(data["company_options"])),
                    ),
                    Field("account", "Actual factual account"),
                ]
        elif choice == "choose" and data["kind"] == "feedback_step":
            fields = [
                Field(
                    "choice",
                    "Actual Feedback outcome",
                    tuple((x, x.title()) for x in ("bond", "purpose", "tear", "die")),
                ),
                Field(
                    "target",
                    "Actual source person",
                    (("none", "None: death outcome"),)
                    + tuple(
                        (
                            x["id"],
                            x["label"]
                            + (" (Bond/Purpose only)" if x["ref"]["kind"] != "pilot" else ""),
                        )
                        for x in data["targets"]
                    ),
                ),
                Field(
                    "asset",
                    "If tear: actual Asset",
                    (("none", "No Asset selected"),)
                    + tuple((x["id"], x["label"]) for x in data["assets"]),
                ),
                Field(
                    "opponent",
                    "Actual opponent for last Girl-Asset loss",
                    (("unknown", "Not established"), ("none", "Explicitly no opponent"))
                    + tuple((x["id"], x["label"]) for x in data["targets"]),
                ),
                Field(
                    "replace",
                    "If Bond Asset at cap: actual Girl Asset replacement",
                    (("none", "No cap replacement"),)
                    + tuple((x["id"], x["label"]) for x in data["assets"]),
                    required=False,
                ),
                Field("name", "If Bond rewrite: actual psychological Asset name", required=False),
                Field(
                    "battle",
                    "Actual source occurs in battle?",
                    (("unknown", "Unknown"), ("yes", "Yes"), ("no", "No")),
                ),
                *fields,
            ]
        elif choice == "purpose":
            fields.insert(0, Field("given", "Give an actual purpose?", YES))
        elif choice == "write":
            fields = [
                Field(
                    "replace",
                    "Cap-required actual Identity replacement",
                    (("none", "Free slot"),)
                    + tuple((x["id"], x["label"]) for x in data["identities"]),
                )
            ]

        async def submit(answering: discord.Interaction, answers: dict[str, Any]) -> None:
            viewer, key = viewer_from_interaction(answering), str(answering.id)
            account = answers.get("account", "")
            if choice == "speak":
                target = next(
                    ActorRef.model_validate(x["ref"])
                    for x in data["people"]
                    if x["id"] == _one(answers, "person")
                )
                await asyncio.to_thread(
                    service.speak, viewer, key, data["revision"], data["id"], target, account
                )
            elif choice == "touch":
                await asyncio.to_thread(
                    service.touch,
                    viewer,
                    key,
                    data["revision"],
                    data["id"],
                    _one(answers, "encounter"),
                    _one(answers, "asset"),
                    account,
                )
            elif choice == "tag":
                await asyncio.to_thread(
                    service.give_source_tag,
                    viewer,
                    key,
                    data["revision"],
                    data["id"],
                    "obsession" if data["kind"] == "obsession" else "spy",
                    answers["label"],
                )
            elif choice == "npc_off_duty":
                from girlframe.services.m3_ankou import npc_off_duty

                await asyncio.to_thread(
                    npc_off_duty,
                    service.game,
                    viewer,
                    key,
                    data["revision"],
                    ActorRef.model_validate(source["target"]),
                    account,
                )
            elif choice == "unlink":
                await asyncio.to_thread(
                    service.unlink, viewer, key, data["revision"], data["id"], account
                )
            elif choice == "activate":
                await asyncio.to_thread(
                    sequences.activate,
                    service.game,
                    viewer,
                    key,
                    data["id"],
                    int(answering.channel_id or 0),
                    data["revision"],
                    account,
                )
            elif choice == "purpose":
                await asyncio.to_thread(
                    sequences.answer_purpose,
                    service.game,
                    viewer,
                    key,
                    data["id"],
                    data["revision"],
                    _one(answers, "given") == "yes",
                    account,
                )
            elif choice == "write":
                await asyncio.to_thread(
                    sequences.write_purpose,
                    service.game,
                    viewer,
                    key,
                    data["id"],
                    data["revision"],
                    None if _one(answers, "replace") == "none" else _one(answers, "replace"),
                )
            elif data["kind"] == "relay":
                await asyncio.to_thread(
                    service.choose_consequence,
                    viewer,
                    key,
                    data["revision"],
                    data["id"],
                    cast(Literal["death", "nominees", "feedback"], _one(answers, "choice")),
                    account,
                )
            elif data["kind"] == "task":
                await asyncio.to_thread(
                    service.choose_task,
                    viewer,
                    key,
                    data["revision"],
                    data["id"],
                    "\n".join(
                        next(x["value"] for x in data["company_options"] if x["id"] == item)
                        if item != "none"
                        else "none"
                        for item in answers["companions"]
                    )
                    if source["kind"] == "company"
                    else _one(answers, "choice"),
                    account,
                    identity_to_erase=answers.get("erase"),
                )
            else:
                refs = {x["id"]: ActorRef.model_validate(x["ref"]) for x in data["targets"]}
                battle = _one(answers, "battle")
                await asyncio.to_thread(
                    sequences.choose,
                    service.game,
                    viewer,
                    key,
                    data["id"],
                    data["revision"],
                    cast(Literal["bond", "purpose", "tear", "die"], _one(answers, "choice")),
                    refs.get(_one(answers, "target")),
                    account,
                    asset=None if _one(answers, "asset") == "none" else _one(answers, "asset"),
                    replace=None
                    if _one(answers, "replace") == "none"
                    else _one(answers, "replace") or None,
                    name=answers.get("name") or None,
                    in_battle=None if battle == "unknown" else battle == "yes",
                    opponent=refs.get(_one(answers, "opponent")),
                    no_opponent=_one(answers, "opponent") == "none",
                )
            await open_ankou(answering, service, data["id"])

        await _form(current, "Ankou actual source", data["summary"], fields, submit)

    status = data["summary"]
    if data.get("pause"):
        status += (
            "\nActual permission pause: "
            + str(data["pause"]["state"])
            + " "
            + str(data["pause"].get("error") or "")
        )
    await _form(
        interaction,
        "Ankou private source",
        status,
        [Field("operation", "Control", tuple(options))],
        select,
    )


def json_text(source: dict[str, Any]) -> str:
    lines = []
    for key in (
        "account",
        "purpose",
        "choice",
        "consequence",
        "benefits",
        "symptoms",
        "ordinal",
        "count",
        "total",
        "completed_event",
        "unlinked_event",
    ):
        if source.get(key) is not None:
            lines.append(key.replace("_", " ").title() + ": " + str(source[key]))
    return (
        "\n\n".join(lines)
        or "Original source preserved. Actual mechanical choices remain in Requests."
    )


async def _child(
    interaction: discord.Interaction, game: GameService, parent: dict[str, Any]
) -> None:
    allowed = tuple(parent["body"].get("allowed", ()))
    selected = parent.get("play") or (allowed[0] if len(allowed) == 1 else None)
    if selected is None:

        async def choose(current: discord.Interaction, values: dict[str, Any]) -> None:
            await _child(current, game, parent | dict(play=_one(values, "play")))

        await _form(
            interaction,
            "Actual Ankou source Play",
            "Perform one actual offered Play; ordinary costs and responses remain real.",
            [
                Field(
                    "play", "Actual offered Play", tuple((x, x.replace("_", " ")) for x in allowed)
                )
            ],
            choose,
        )
    elif selected == "alpha_sex":
        from girlframe.discord_adapter.m3_required_plays import open_required

        await open_required(interaction, game, parent["body"]["source_work"])
    elif selected == "all_out_assault":
        from girlframe.discord_adapter.m3_battle import open_declaration
        from girlframe.services.m3_battle import BattleService

        await open_declaration(
            interaction, BattleService(game.store), parent=parent | dict(play=selected)
        )
    else:
        from girlframe.discord_adapter.m2_ui import open_play

        await open_play(interaction, game, parent=parent | dict(play=selected), _pilot=True)
