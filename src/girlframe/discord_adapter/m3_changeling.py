"""Actual speakers, affected humans and original Handler own their Changeling choices."""

import asyncio
from typing import Any, cast

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.ledger import clean
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.m3_memory_pages import MemoryForm, MemoryHistory
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine import m3_changeling as rules
from girlframe.engine.m2 import ChoiceAnswer, PlayInput
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.services.m2_game import GameService
from girlframe.services.m3_changeling import ChangelingService
from girlframe.services.onboarding import WorkflowError


async def open_choice(
    interaction: discord.Interaction, game: GameService, decision: dict[str, Any]
) -> None:
    detail, kind = decision["detail"], decision["kind"]
    fields: list[Field] = []
    if kind == "changeling_low_erase":
        fields.append(Field("identity", "Your actual erased Identity", tuple(detail["identities"])))
    elif kind == "changeling_recent":
        fields.append(Field("start_event", "Actual event starting the last few fictional minutes"))
    elif kind == "changeling_taste":
        fields.append(
            Field(
                "taste",
                "Do the actual changes suit your tastes?",
                (("yes", "Yes"), ("no", "No: give your Tag")),
            )
        )
        fields.append(Field("tag", "Your actual Tag if no", required=False))
    elif kind in ("changeling_clay_owner", "changeling_clay_handler"):
        copies = detail.get("copies", ())
        options = tuple(detail["facets"])
        fields.append(
            Field(
                "facets",
                "Actual facets you change",
                options,
                minimum=detail["minimum"],
                maximum=detail["maximum"],
                required=detail["minimum"] > 0,
            )
        )
        if copies:
            fields.append(
                Field(
                    "copy",
                    "Or look exactly like an actual known person",
                    tuple((x["id"], x["label"]) for x in copies),
                    minimum=0,
                    required=False,
                )
            )
    else:
        raise WorkflowError("Use the actual pending Changeling source response")
    fields.append(Field("account", "Your actual source account", paragraph=True))

    async def access(current: discord.Interaction) -> None:
        await asyncio.to_thread(game.decision, viewer_from_interaction(current), decision["id"])

    async def save(
        current: discord.Interaction, values: dict[str, Any], facets: dict[str, str]
    ) -> str:
        answer = ChoiceAnswer(
            text=values.get("tag", "")
            if kind == "changeling_taste" and values["taste"] == ("no",)
            else values["account"],
            denied=tuple(values.get("identity", ())),
            options=tuple(values.get("facets", ())) if not values.get("copy") else (),
            flag=values["taste"] == ("yes",) if kind == "changeling_taste" else None,
            fields={"start_event": values["start_event"]}
            if kind == "changeling_recent"
            else {"copy": values["copy"][0]}
            if values.get("copy")
            else facets,
        )
        await asyncio.to_thread(
            game.respond,
            viewer_from_interaction(current),
            str(current.id),
            decision["id"],
            decision["revision"],
            answer,
        )
        return "Your actual owned Changeling consequence is saved."

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str | None:
        chosen = tuple(values.get("facets", ()))
        if chosen and not values.get("copy"):

            async def change(response: discord.Interaction, answers: dict[str, Any]) -> str:
                return await save(response, values, {key: answers[key] for key in chosen})

            form = MemoryForm(
                current.user.id,
                "Actual body changes",
                "Describe only each selected physical facet.",
                [Field(key, rules.FACET_LABELS[key], paragraph=True) for key in chosen],
                change,
                authorize=access,
            )
            await reply(current, form.text(), form)
            return None
        return await save(current, values, {})

    form = MemoryForm(
        interaction.user.id,
        "Changeling result",
        "The actual printed chooser authors this consequence.",
        fields,
        submit,
        authorize=access,
    )
    await reply(interaction, form.text(), form)


async def _play(
    interaction: discord.Interaction,
    service: ChangelingService,
    play: str,
    source: str | None = None,
) -> None:
    from girlframe.discord_adapter.m3_dampener import fields as dampener_fields
    from girlframe.discord_adapter.m3_dampener import modifier
    from girlframe.discord_adapter.m3_prince import fields as prince_fields
    from girlframe.discord_adapter.m3_prince import prepared_values
    from girlframe.services.m3_dampener import DampenerService

    sheet = await asyncio.to_thread(service.game.sheet, viewer_from_interaction(interaction))
    identities = [x for x in sheet["identities"] if not x["marked"]]
    fields = [
        Field(
            "heat", "Actual Heat spent", tuple((str(x), str(x)) for x in range(sheet["heat"] + 6))
        ),
        Field("account", "What you actually do", paragraph=True),
    ]
    if identities:
        fields.extend(
            [
                Field(
                    "identity",
                    "Optional actual Identity to mark",
                    tuple((x["id"], x["name"]) for x in identities),
                    minimum=0,
                    required=False,
                ),
                Field(
                    "gain", "Heat gained from marking", tuple((str(x), str(x)) for x in range(6))
                ),
                Field(
                    "pair_share",
                    "Paired Heat sent to your actual Pair",
                    tuple((str(x), str(x)) for x in range(6)),
                ),
            ]
        )
    fields.extend(await dampener_fields(interaction, DampenerService(service.game)))
    fields.extend(await prince_fields(interaction, service.game))

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        await asyncio.to_thread(
            service.game.begin,
            viewer_from_interaction(current),
            str(current.id),
            int(current.channel_id or 0),
            sheet["revision"],
            PlayInput(
                **prepared_values(values),
                play=play,
                context=values["account"],
                trigger_confirmed=True,
                heat=int(values["heat"][0]),
                identity=values.get("identity", (None,))[0] if values.get("identity") else None,
                gain=int(values.get("gain", ("0",))[0]) if values.get("identity") else 0,
                pair_share=int(values.get("pair_share", ("0",))[0])
                if values.get("identity")
                else 0,
                dampener_modifier=modifier(values),
                source_work=source,
            ),
        )
        return "Your actual Changeling Play is confirmed."

    form = NativeForm(
        interaction.user.id,
        "CHANGELING",
        "Confirm your actual source, Heat and Identity costs.",
        fields,
        submit,
    )
    await reply(interaction, form.text(), form)


async def _saved(
    interaction: discord.Interaction, service: ChangelingService, identity: str
) -> None:
    shown = await asyncio.to_thread(service.view, viewer_from_interaction(interaction), identity)
    body, kind = shown["body"], shown["kind"]
    lines = [kind.removeprefix("changeling_").replace("_", " ").title()]
    if shown.get("current_subject"):
        actual = ActorRef.model_validate(shown["current_subject"])
        lines.append("Current actual subject: " + actual.kind + ":" + actual.entity)
    lines.append(
        "Completed" if body.get("completed_event") or body.get("replaced_event") else "Saved source"
    )
    for field in ("text", "account", "label", "question", "answer"):
        if isinstance(body.get(field), str):
            lines.append(clean(body[field]))
    if body.get("total") is not None:
        lines.append("Actual result: " + str(body["total"]))
    for question in shown.get("questions", ()):
        lines.append(clean(question["question"]))
        if question["answer"] is not None:
            lines.append("Answer:\n" + clean(question["answer"]))
    for change in shown.get("changes", ()):
        lines.extend(
            clean(rules.FACET_LABELS[key] + ": " + value) for key, value in change["values"].items()
        )
    if shown.get("copied_label"):
        lines.append("Copied Identity: " + clean(shown["copied_label"]))
    for observation in shown.get("effect", {}).get("observations", ()):
        lines.append("Through their actual eyes:\n" + clean(observation["text"]))
    text = "\n\n".join(lines)

    async def access(current: discord.Interaction) -> None:
        await asyncio.to_thread(service.view, viewer_from_interaction(current), identity)

    fields: list[Field] = []
    if kind == "changeling_question" and shown["actionable"]:
        fields = [Field("answer", "Your actual answer", paragraph=True)]
    elif kind == "changeling_fingers":
        if shown.get("counter"):
            fields = [
                Field(
                    "kind",
                    "Your optional printed response",
                    (
                        ("pass", "Pass"),
                        ("question", "Ask a question"),
                        ("erase", "Erase a caster Identity"),
                        ("tag", "Give the caster a Tag"),
                    ),
                ),
                Field("text", "Your question or Tag", paragraph=True, required=False),
            ]
            if shown["identities"]:
                fields.append(
                    Field(
                        "identity",
                        "Caster Identity if erasing",
                        tuple(shown["identities"]),
                        minimum=0,
                        required=False,
                    )
                )
        elif shown.get("damage"):
            fields = [Field("asset", "Your actual Asset to damage", tuple(shown["assets"]))]
        elif shown.get("fry"):
            fields = [
                Field(
                    "outcome",
                    "Actual human NPC outcome",
                    (("helpless", "Helpless"), ("dead", "Dead")),
                )
            ]
        elif shown.get("observe"):
            fields = [Field("observation", "What your actual eyes see here", paragraph=True)]
        elif shown.get("consent"):
            fields = [
                Field(
                    "consent",
                    "Accept this actual remote Sex initiation?",
                    (("yes", "Accept"), ("no", "Decline")),
                )
            ]
        elif any(
            x["answer_event"] is None
            and x.get("current_answerer", x["answerer"]["controller"]) == interaction.user.id
            for x in shown.get("questions", ())
        ):
            unanswered = [
                x
                for x in shown["questions"]
                if x["answer_event"] is None
                and x.get("current_answerer", x["answerer"]["controller"]) == interaction.user.id
            ]
            fields = [
                Field(
                    "question",
                    "Your actual owed question",
                    tuple((x["id"], x["question"]) for x in unanswered),
                ),
                Field("answer", "Your actual answer", paragraph=True),
            ]
    elif kind == "changeling_reconditioning" and shown["actionable"]:
        fields = [
            Field(
                "tag",
                "Your optional absent Tag",
                (("pass", "Pass"), *((x, x) for x in shown["tags"])),
            )
        ]
    elif kind == "changeling_assault_gift" and shown["actionable"]:
        fields = [Field("give", "Implant one actual String?", (("yes", "Yes"), ("no", "No")))]
    elif kind == "changeling_blank" and shown["actionable"] and shown.get("copies"):
        copies = shown["copies"]
        conversations = shown["conversations"]
        fields = [
            Field(
                "copy",
                "Actual disclosed Identity content",
                tuple((x["identity"], x["label"]) for x in copies),
            ),
            Field(
                "first",
                "First actual conversation source",
                tuple((x["id"], x["text"]) for x in conversations),
            ),
            Field(
                "second",
                "Other person's actual conversation source",
                tuple((x["id"], x["text"]) for x in conversations),
            ),
        ]

    if (
        not fields
        and kind == "changeling_fingers"
        and body["kind"] == "sex"
        and body.get("consent_event")
    ):
        from girlframe.discord_adapter.m3_changeling_sex import open_changeling_sex
        from girlframe.services.m3_changeling_sex import ChangelingSexService

        await open_changeling_sex(interaction, ChangelingSexService(service.game), identity)
        return
    effect = shown.get("effect", {})
    child = effect.get("child")
    pause = effect.get("pause")
    if pause:
        text += "\n\nScene permission state: " + clean(pause["state"])
        if pause.get("error"):
            text += "\n" + clean(pause["error"])
    child_actor = ActorRef.model_validate(effect["body"]["actor"]) if child else None
    child_owner = body.get("controllers", {}).get(child_actor.token) if child_actor else None
    if not fields and (
        (child and child_owner == interaction.user.id) or pause and pause.get("retry")
    ):
        from girlframe.discord_adapter.m2_ui import open_play

        operations: list[tuple[str, str]] = []
        if (
            child
            and child_owner == interaction.user.id
            and (pause is None or pause["state"] == "held")
        ):
            operations.append(("perform", "Make the real legally triggered Play"))
        if pause and pause.get("retry"):
            operations.append(("retry", "Retry actual scene permissions"))
        if operations:

            async def perform(current: discord.Interaction, values: dict[str, Any]) -> str | None:
                if values["perform"] == ("retry",):
                    from girlframe.services.p1_source_pause import retry

                    await asyncio.to_thread(
                        retry,
                        service.game,
                        viewer_from_interaction(current),
                        str(current.id),
                        identity,
                    )
                    return "Actual scene permission retry queued. Reopen the saved source."
                descriptor = dict(
                    id=identity,
                    revision=shown["revision"],
                    kind="changeling_" + effect["kind"],
                    actor=effect["body"]["actor"],
                    parent=child["parent"],
                    action_id=child["parent"],
                    channel=effect["body"]["cast"]["channel"],
                    body=dict(source_work=identity),
                    detail={},
                )
                await open_play(current, service.game, parent=descriptor)
                return None

            form = MemoryForm(
                interaction.user.id,
                "Actual source performance",
                text,
                [Field("perform", "Your actual source control", tuple(operations))],
                perform,
                authorize=access,
            )
            await reply(interaction, form.text(), form)
            return
    if kind == "changeling_speech" and shown.get("push"):
        fields = [Field("tag", "Your actual pushed Tag (pay lower Status)")]

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        viewer, key, revision = viewer_from_interaction(current), str(current.id), shown["revision"]
        if kind == "changeling_question":
            await asyncio.to_thread(
                service.answer, viewer, key, revision, identity, values["answer"]
            )
        elif kind == "changeling_fingers":
            if values.get("observation"):
                await asyncio.to_thread(
                    service.observe_eyes, viewer, key, revision, identity, values["observation"]
                )
            elif values.get("consent"):
                await asyncio.to_thread(
                    service.consent, viewer, key, revision, identity, values["consent"] == ("yes",)
                )
            elif values.get("answer"):
                await asyncio.to_thread(
                    service.answer, viewer, key, revision, values["question"][0], values["answer"]
                )
            elif shown.get("counter"):
                await asyncio.to_thread(
                    service.counter,
                    viewer,
                    key,
                    revision,
                    identity,
                    values["kind"][0],
                    text=values.get("text", ""),
                    identity_id=values.get("identity", (None,))[0]
                    if values.get("identity")
                    else None,
                )
            elif shown.get("damage"):
                await asyncio.to_thread(
                    service.damage, viewer, key, revision, identity, values["asset"][0]
                )
            else:
                await asyncio.to_thread(
                    service.fry, viewer, key, revision, identity, values["outcome"][0]
                )
        elif kind == "changeling_speech":
            await asyncio.to_thread(service.push, viewer, key, revision, identity, values["tag"])
        elif kind == "changeling_reconditioning":
            await asyncio.to_thread(
                service.recondition,
                viewer,
                key,
                revision,
                identity,
                None if values["tag"] == ("pass",) else values["tag"][0],
            )
        elif kind == "changeling_assault_gift":
            await asyncio.to_thread(
                service.assault_gift, viewer, key, revision, identity, values["give"] == ("yes",)
            )
        else:
            selected = next(x for x in shown["copies"] if x["identity"] == values["copy"][0])
            await asyncio.to_thread(
                service.copy_blank,
                viewer,
                key,
                revision,
                identity,
                ActorRef.model_validate(selected["other"]),
                selected["identity"],
                (values["first"][0], values["second"][0]),
            )
        return "Your actual original source choice is saved."

    if fields:
        form = MemoryForm(
            interaction.user.id, "Private Changeling source", text, fields, submit, authorize=access
        )
        await reply(interaction, form.text(), form)
    else:
        history = MemoryHistory(interaction.user.id, text, access)
        await reply(interaction, history.text(), history)


async def open_changeling(
    interaction: discord.Interaction, service: ChangelingService, identity: str | None = None
) -> None:
    if identity is not None:
        await _saved(interaction, service, identity)
        return
    menu = await asyncio.to_thread(
        service.menu, viewer_from_interaction(interaction), int(interaction.channel_id or 0)
    )
    options = [("history:" + x["id"], x["label"]) for x in menu["tasks"]]
    if menu["roles"]:
        options.extend(
            [
                ("speak", "Author your actual speech"),
                ("body", "Establish actual body/brain facts"),
                ("appearance", "Describe existing appearance"),
                ("show_appearance", "Show your actual appearance"),
                ("disclose", "Disclose your own actual Identity"),
            ]
        )
        options.extend(("play:" + x["id"], x["label"]) for x in menu["plays"])
        options.extend(("buy:" + x["id"], "Acquire " + x["label"]) for x in menu["requisitions"])
    if menu["nodes"]:
        options.append(("fingers", "Use an actual Psych String"))
    if menu["accesses"]:
        options.append(("implant", "Perform the actual Web Implant"))
    if not options:
        await reply(
            interaction,
            "No owned saved Changeling source. Use an actual joined scene for new source work.",
        )
        return

    async def select(current: discord.Interaction, values: dict[str, Any]) -> str | None:
        token = values["entry"][0]
        if token.startswith("history:"):
            await _saved(current, service, token.removeprefix("history:"))
        elif token.startswith("play:"):
            play = token.removeprefix("play:")
            if play == "changeling_blank_slate":
                if not menu["definitions"]:
                    raise WorkflowError(
                        "Another actual person must author their real who-you-are statement"
                    )

                async def definition(
                    response: discord.Interaction, choices: dict[str, Any]
                ) -> None:
                    await _play(response, service, play, choices["speech"][0])

                form = NativeForm(
                    current.user.id,
                    "Actual defining statement",
                    "Choose the original actual addressed source.",
                    [
                        Field(
                            "speech",
                            "Who actually told you who you are?",
                            tuple((x["id"], x["label"]) for x in menu["definitions"]),
                        )
                    ],
                    definition,
                )
                await reply(current, form.text(), form)
            else:
                await _play(current, service, play)
        else:
            await _operation(current, service, menu, token)
        return None

    form = NativeForm(
        interaction.user.id,
        "CHANGELING",
        "Original humans author source facts and their own printed choices.",
        [Field("entry", "Actual source or private history", tuple(options))],
        select,
    )
    await reply(interaction, form.text(), form)


async def _operation(
    interaction: discord.Interaction,
    service: ChangelingService,
    menu: dict[str, Any],
    operation: str,
) -> None:
    roles = {x["id"]: x for x in menu["roles"]}
    targets = {x["id"]: x for x in menu["targets"]}
    role_field = Field(
        "actor", "Your actual acting role", tuple((x, row["label"]) for x, row in roles.items())
    )
    target_field = Field(
        "target",
        "Actual addressed other role",
        tuple((x, row["label"]) for x, row in targets.items()),
    )
    fields: list[Field] = []
    if operation == "speak":
        fields = [
            role_field,
            target_field,
            Field(
                "kind",
                "Actual speech",
                (
                    ("definition", "Tell them who they are"),
                    ("conversation", "Talk with them"),
                    ("push", "Push after actual mid Blank Slate"),
                ),
            ),
            Field("text", "Your actual words", paragraph=True),
            Field("session", "Actual mid source ID for push only", required=False),
        ]
    elif operation == "body":
        fields = [
            target_field,
            Field(
                "kind",
                "Actual source body category",
                tuple((x, x) for x in ("girl", "gorgon", "harpy", "handler", "human_npc", "other")),
            ),
            Field("account", "Actual original body and brain evidence", paragraph=True),
        ]
    elif operation == "appearance":
        fields = [
            role_field,
            *[Field(key, label, paragraph=True) for key, label in rules.FACET_LABELS.items()],
        ]
    elif operation == "show_appearance":
        fields = [
            Field(
                "appearance",
                "Your actual recorded appearance",
                tuple((x["id"], x["label"]) for x in menu["appearances"]),
            ),
            target_field,
        ]
    elif operation == "disclose":
        fields = [
            Field(
                "speech",
                "Your actual conversation",
                tuple((x["id"], x["label"]) for x in menu["conversations"]),
            ),
            Field(
                "identity",
                "Your actual possessed Identity",
                tuple(
                    dict(
                        (identity, label)
                        for speech in menu["conversations"]
                        for identity, label in speech["identities"]
                    ).items()
                ),
            ),
        ]
    elif operation == "fingers":
        fields = [
            Field(
                "node",
                "Your actual unspent String",
                tuple((x["id"], x["label"]) for x in menu["nodes"]),
            ),
            Field(
                "kind",
                "One actual effect",
                tuple(
                    (x, x.replace("_", " "))
                    for x in (
                        "pause",
                        "sight",
                        "interrupt",
                        "question",
                        "flirt_plus",
                        "flirt_minus",
                        "sex",
                        "fry",
                        "damage",
                    )
                ),
            ),
            Field("account", "Your actual declared effect", paragraph=True),
            Field("question", "Question if chosen", paragraph=True, required=False),
            Field("incoming", "Actual pending Play ID if interrupting", required=False),
            Field("scene", "Subject's actual scene ID if seeing", required=False),
        ]
    elif operation == "implant":
        fields = [
            Field(
                "access",
                "Actual Handler-proved access",
                tuple((x["id"], x["label"]) for x in menu["accesses"]),
            ),
            Field("account", "Actual implantation performance", paragraph=True),
        ]
    elif operation.startswith("buy:"):
        fields = [Field("account", "Voluntary actual two-Permission acquisition", paragraph=True)]
    else:
        raise WorkflowError("Use the actual saved source operation")

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        viewer, key, revision = viewer_from_interaction(current), str(current.id), menu["revision"]
        channel = int(current.channel_id or 0)
        actor = (
            ActorRef.model_validate(roles[values["actor"][0]]["actor"])
            if values.get("actor")
            else None
        )
        target = (
            ActorRef.model_validate(targets[values["target"][0]]["actor"])
            if values.get("target")
            else None
        )
        if operation == "speak":
            assert actor is not None and target is not None
            await asyncio.to_thread(
                service.speak,
                viewer,
                key,
                revision,
                channel,
                actor,
                target,
                values["kind"][0],
                values["text"],
                session=values.get("session") or None,
            )
        elif operation == "body":
            assert target is not None
            await asyncio.to_thread(
                service.body_fact,
                viewer,
                key,
                revision,
                channel,
                target,
                values["kind"][0],
                values["account"],
            )
        elif operation == "appearance":
            assert actor is not None
            await asyncio.to_thread(
                service.appearance,
                viewer,
                key,
                revision,
                channel,
                actor,
                {facet: values[facet] for facet in rules.FACETS},
            )
        elif operation == "show_appearance":
            assert target is not None
            await asyncio.to_thread(
                service.disclose_appearance,
                viewer,
                key,
                revision,
                channel,
                values["appearance"][0],
                target,
            )
        elif operation == "disclose":
            await asyncio.to_thread(
                service.disclose_identity,
                viewer,
                key,
                revision,
                values["speech"][0],
                values["identity"],
            )
        elif operation == "fingers":
            await asyncio.to_thread(
                service.fingers,
                viewer,
                key,
                revision,
                channel,
                values["node"][0],
                cast(rules.FingerKind, values["kind"][0]),
                values["account"],
                question=values.get("question") or None,
                incoming=values.get("incoming") or None,
                subject_scene=values.get("scene") or None,
            )
        elif operation == "implant":
            await asyncio.to_thread(
                service.implant, viewer, key, revision, values["access"][0], values["account"]
            )
        else:
            await asyncio.to_thread(
                service.purchase,
                viewer,
                key,
                revision,
                operation.removeprefix("buy:"),
                values["account"],
            )
        return "Your actual human-authored source is saved."

    form = NativeForm(
        interaction.user.id,
        "Changeling source",
        "Use the original actual roles. Recorded facts do not author "
        "another person's dialogue or consent.",
        fields,
        submit,
    )
    await reply(interaction, form.text(), form)
