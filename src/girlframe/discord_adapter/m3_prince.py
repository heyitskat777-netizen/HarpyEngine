"""Private original-person Prince performance, audience and Off-Duty controls."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine import m3_prince as rules
from girlframe.engine.m2 import ChoiceAnswer, PlayInput
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.services.m2_game import GameService
from girlframe.services.m3_prince import PrinceService
from girlframe.services.onboarding import WorkflowError

YES = (("yes", "Yes"), ("no", "No"))


async def fields(interaction: discord.Interaction, game: GameService) -> list[Field]:
    data = await asyncio.to_thread(
        PrinceService(game).demand_menu, viewer_from_interaction(interaction)
    )
    if not data["available"]:
        return []
    result = [
        Field(
            "prince_demands",
            "Actual relation to my Fanbase demands",
            (("following", "I am following them"), ("against", "This is the named contrary act")),
            minimum=0,
            required=False,
        ),
        Field(
            "prince_demand_account",
            "Actual demand-following or contrary-act account",
            paragraph=True,
            required=False,
        ),
    ]
    if data["exceptions"]:
        result.append(
            Field(
                "prince_exception",
                "Actual completed Keep/Disobey for this contrary act",
                tuple((x["id"], x["label"][:100]) for x in data["exceptions"]),
                minimum=0,
                required=False,
            )
        )
    return result


def prepared_values(values: dict[str, Any]) -> dict[str, Any]:
    chosen = values.get("prince_demands", ())
    account = values.get("prince_demand_account", "")
    exception = values.get("prince_exception", ())
    return (
        (dict(prince_demands=chosen[0]) if chosen else {})
        | (dict(prince_demand_account=account) if account else {})
        | (dict(prince_exception=exception[0]) if exception else {})
    )


async def open_membership(
    interaction: discord.Interaction, game: GameService, prince: ActorRef, member: ActorRef
) -> None:
    service = PrinceService(game)
    data = await asyncio.to_thread(
        service.member_menu, viewer_from_interaction(interaction), prince, member
    )

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        await asyncio.to_thread(
            service.member,
            viewer_from_interaction(current),
            str(current.id),
            data["revision"],
            prince,
            member,
            values["demographic"][0],
            values["account"],
        )
        return "Your actual original person's factual fan membership is saved."

    await NativeForm(
        interaction.user.id,
        "Actual fan membership",
        "Author only your actual controlled person, not another player's private intention.",
        [
            Field(
                "demographic",
                "Your actual fan demographic",
                tuple((x["id"], x["label"]) for x in data["demographics"]),
            ),
            Field("account", "Your actual factual membership account", paragraph=True),
        ],
        submit,
    ).present(interaction)


async def open_choice(
    interaction: discord.Interaction, game: GameService, decision: dict[str, Any]
) -> None:
    detail = decision.get("prince", decision.get("detail", {}))
    if "detail" in detail:
        detail = detail["detail"]
    fields = []
    if detail.get("options"):
        fields.append(
            Field(
                "option", "Your actual printed choice", tuple(tuple(x) for x in detail["options"])
            )
        )
    if detail.get("tags"):
        fields.append(
            Field(
                "tags",
                "Your actual Tags conflicting with this part",
                tuple((x["id"], x["label"]) for x in detail["tags"]),
                minimum=0,
                maximum=len(detail["tags"]),
                required=False,
            )
        )
    fields.append(
        Field(
            "account",
            "Actual rendition, conflict, comparison Tag or demand-following account",
            paragraph=True,
            required=False,
        )
    )

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        await asyncio.to_thread(
            game.respond,
            viewer_from_interaction(current),
            str(current.id),
            decision["id"],
            decision["revision"],
            ChoiceAnswer(
                options=tuple(values.get("option", ())),
                denied=tuple(values.get("tags", ())),
                text=values.get("account", ""),
            ),
        )
        return "Your actual owned Prince response is saved. Resume any remaining source work."

    await NativeForm(
        interaction.user.id,
        "Prince: actual source choice",
        "Each original person owns their response. Private Tags and intentions stay private.",
        fields,
        submit,
    ).present(interaction)


async def _begin(
    interaction: discord.Interaction, service: PrinceService, data: dict[str, Any]
) -> None:
    record = data["record"]
    sheet = await asyncio.to_thread(service.game.sheet, viewer_from_interaction(interaction))
    identities = [
        x for x in sheet["identities"] + sheet.get("additional_identities", []) if not x["marked"]
    ]
    fields = [
        Field(
            "identity",
            "Optional actual owned Identity",
            tuple((x["id"], x["name"]) for x in identities),
            minimum=0,
            required=False,
        ),
        Field(
            "gain",
            "Identity Heat gained; 0 without marking",
            tuple((str(x), str(x)) for x in range(6)),
        ),
        Field("share", "Paired Heat sent to Pair", tuple((str(x), str(x)) for x in range(6))),
        Field(
            "heat",
            "Actual Heat to spend",
            tuple((str(x), str(x)) for x in range(sheet["heat"] + 6)),
        ),
        Field("piloting", "Actually piloting your Frame?", YES),
        Field(
            "exception",
            "If contrary: your actual completed Keep/Disobey",
            tuple((x["id"], x["label"]) for x in data.get("exceptions", [])),
            minimum=0,
            required=False,
        ),
    ]

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        identity = values.get("identity", ())
        prepared = PlayInput.model_validate(
            dict(
                play=rules.PLAY,
                source_work=record["id"],
                identity=identity[0] if identity else None,
                gain=int(values["gain"][0]),
                pair_share=int(values["share"][0]),
                heat=int(values["heat"][0]),
                piloting=values["piloting"][0] == "yes",
                context=record["part"],
                trigger_confirmed=True,
                prince_demands="following" if record["following"] else "against",
                prince_demand_account=record["account"],
                prince_exception=values["exception"][0] if values.get("exception") else None,
            )
        )
        result = await asyncio.to_thread(
            service.game.begin,
            viewer_from_interaction(current),
            str(current.id),
            record["cast"]["channel"],
            sheet["revision"],
            prepared,
        )
        return (
            "Actual Performer Play confirmed: "
            + str(result["action_id"])
            + ". Complete its real choices."
        )

    await NativeForm(
        interaction.user.id,
        "Play the actual part",
        record["part"] + "\nMark demographics only while following demands. "
        "A contrary act requires actual Keep/Disobey first.",
        fields,
        submit,
    ).present(interaction)


async def _record(
    interaction: discord.Interaction, service: PrinceService, data: dict[str, Any]
) -> None:
    value, kind = data["record"], data["kind"]
    viewer = viewer_from_interaction(interaction)
    fields: list[Field] = []
    if kind == "DemandAttempt" and value["action"] is None:
        sheet = await asyncio.to_thread(service.game.sheet, viewer)
        identities = [
            x
            for x in sheet["identities"] + sheet.get("additional_identities", [])
            if not x["marked"] and not x["id"].startswith("fan:") and ":fan:" not in x["id"]
        ]
        fields = [
            Field(
                "play",
                "Actual Play required by Fanbase expectations",
                (("keep_your_head", "Keep Your Head"), ("disobey_orders", "Disobey Orders")),
            ),
            Field(
                "identity",
                "Optional actual ordinary owned Identity",
                tuple((x["id"], x["name"]) for x in identities),
                minimum=0,
                required=False,
            ),
            Field(
                "gain",
                "Identity Heat gained; 0 without marking",
                tuple((str(x), str(x)) for x in range(6)),
            ),
            Field("share", "Paired Heat sent to Pair", tuple((str(x), str(x)) for x in range(6))),
            Field(
                "heat",
                "Actual Heat committed",
                tuple((str(x), str(x)) for x in range(sheet["heat"] + 6)),
            ),
            Field("piloting", "Actually piloting your Frame?", YES),
        ]

        async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
            identity = values.get("identity", ())
            prepared = PlayInput.model_validate(
                dict(
                    play=values["play"][0],
                    source_work=value["id"],
                    identity=identity[0] if identity else None,
                    gain=int(values["gain"][0]),
                    pair_share=int(values["share"][0]),
                    heat=int(values["heat"][0]),
                    piloting=values["piloting"][0] == "yes",
                    context=value["account"],
                    trigger_confirmed=True,
                    prince_demands="against",
                    prince_demand_account=value["account"],
                )
            )
            result = await asyncio.to_thread(
                service.game.begin,
                viewer_from_interaction(current),
                str(current.id),
                value["cast"]["channel"],
                sheet["revision"],
                prepared,
            )
            return "Actual Fanbase exception Play confirmed: " + str(result["action_id"])
    elif kind == "Performance":
        if data.get("choices"):
            choice = await asyncio.to_thread(
                service.game.decision, viewer, data["choices"][0]["id"]
            )
            await open_choice(interaction, service.game, choice)
            return
        if not value["action"] and viewer.user_id == value["caster"]:
            await _begin(interaction, service, data)
            return
        if (
            value["completed_event"]
            and not value["broken_event"]
            and viewer.user_id == value["caster"]
        ):
            fields = [
                Field(
                    "account", "The actual temporary or final break from this part", paragraph=True
                )
            ]

            async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
                await asyncio.to_thread(
                    service.break_character,
                    viewer_from_interaction(current),
                    str(current.id),
                    data["revision"],
                    value["id"],
                    values["account"],
                )
                return (
                    "The break is saved; its actual source determines the one dismissed allowance."
                )
        else:
            await reply(
                interaction,
                "Saved performance: "
                + value["part"]
                + ". Resume the actual original Play from your decisions.",
            )
            return
    elif kind == "Recognition" and not value["completed_event"]:
        if value["branch"] is None and viewer.user_id == value["counterpart"]:
            fields = [
                Field(
                    "option",
                    "Your actual relationship to this Frame's legacy",
                    (
                        ("predecessor", "I met the predecessor"),
                        ("mission", "I saw you on a previous mission"),
                        ("secret", "I keep it close for now"),
                    ),
                ),
                Field("account", "Your actual source account", paragraph=True),
            ]
        elif (
            value["branch"] == "predecessor"
            and not value["question_event"]
            and viewer.user_id == value["caster"]
        ):
            fields = [
                Field(
                    "option",
                    "Your optional real question",
                    (("ask", "Ask about my predecessor"), ("pass", "Do not ask")),
                ),
                Field("text", "Question, if asking", paragraph=True, required=False),
                Field("account", "Your actual response", paragraph=True),
            ]
        elif (
            value["branch"] == "predecessor"
            and value["question_event"]
            and viewer.user_id == value["counterpart"]
        ):
            fields = [
                Field("text", "Actual Tag comparing the two original people"),
                Field(
                    "account",
                    "Your actual answer to: " + (value["question"] or "No question was asked"),
                    paragraph=True,
                ),
            ]
        elif value["branch"] == "secret" and viewer.user_id == value["handler_controller"]:
            fields = [
                Field("account", "Actual expression flashing across their face", paragraph=True)
            ]
        if fields:

            async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
                await asyncio.to_thread(
                    service.legacy,
                    viewer_from_interaction(current),
                    str(current.id),
                    data["revision"],
                    value["id"],
                    values.get("option", ("answer",))[0],
                    values["account"],
                    values.get("text", ""),
                )
                return "The actual owned legacy response is saved."
    elif kind == "OffDutyTask" and not value["completed_event"]:
        fanbase = data["fanbase"]
        if value["rule"] == rules.TV:
            fields = [
                Field(
                    "option",
                    "Your printed TV Interviews effect",
                    (
                        ("adjust", "Adjust my actual demands"),
                        ("replace", "Exchange an actual demographic and adjust demands"),
                        ("fan", "Introduce an actual Foundation recruit fan"),
                    ),
                ),
                Field(
                    "demanded",
                    "For adjustment: exactly two demanded qualities, one per line",
                    paragraph=True,
                    required=False,
                ),
                Field(
                    "rejected",
                    "For adjustment: exactly two rejected qualities, one per line",
                    paragraph=True,
                    required=False,
                ),
                Field(
                    "demographic",
                    "Existing demographic for recruit or removal",
                    tuple((x["id"], x["name"]) for x in fanbase["demographics"]),
                    minimum=0,
                    required=False,
                ),
                Field(
                    "new_demographic", "If exchanging: actual new demographic name", required=False
                ),
                Field("name", "If recruiting: actual new fan's name", required=False),
                Field("cell", "Recruit's actual known map position x,y", required=False),
                Field("account", "Actual interview/adjustment or fan introduction", paragraph=True),
            ]
        else:
            fields = [
                Field(
                    "option",
                    "Actual funded performance opportunity",
                    (
                        ("perform", "Actually perform the funded concert"),
                        ("decline", "Decline this next-OffDuty opportunity"),
                    ),
                ),
                Field("new_demographic", "Actual new audience demographic", required=False),
                Field("asset_name", "Real Girl fame Asset name", required=False),
                Field(
                    "asset_description",
                    "Real near-worldwide fame Asset description",
                    paragraph=True,
                    required=False,
                ),
                Field(
                    "replace",
                    "Only at cap: actual ordinary non-Void Girl Asset",
                    tuple((x["id"], x["label"]) for x in data["replace"]),
                    minimum=0,
                    required=False,
                ),
                Field("account", "Actual performance or decision", paragraph=True),
            ]

        async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
            option = values["option"][0]
            coords = (
                tuple(int(x.strip()) for x in values["cell"].split(","))
                if values.get("cell")
                else None
            )
            if coords is not None and len(coords) != 2:
                raise WorkflowError("Use the recruit's actual known x,y position")
            old = values.get("demographic", ("",))[0]
            await asyncio.to_thread(
                service.off_duty,
                viewer_from_interaction(current),
                str(current.id),
                data["revision"],
                value["id"],
                option,
                values["account"],
                demanded=tuple(
                    x.strip() for x in values.get("demanded", "").splitlines() if x.strip()
                ),
                rejected=tuple(
                    x.strip() for x in values.get("rejected", "").splitlines() if x.strip()
                ),
                demographic=old if option == "fan" else values.get("new_demographic", ""),
                lose=old if option == "replace" else "",
                name=values.get("name", ""),
                cell=(coords[0], coords[1]) if coords else None,
                asset_name=values.get("asset_name", ""),
                asset_description=values.get("asset_description", ""),
                replace=values.get("replace", (None,))[0],
            )
            return "The actual printed Off-Duty effect and its real resources are saved."
    elif kind == "Grant" and value["rule"] == rules.BAD:
        if not data.get("disobediences"):
            await reply(
                interaction,
                "The Handler has the reveal-plan Play. "
                "Real completed disobedience is required before using it.",
            )
            return
        fields = [
            Field(
                "action",
                "Actual completed original disobedience",
                tuple((x["id"], x["label"]) for x in data["disobediences"]),
            ),
            Field("account", "Actually reveal how it was part of your plan", paragraph=True),
        ]

        async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
            await asyncio.to_thread(
                service.reveal_plan,
                viewer_from_interaction(current),
                str(current.id),
                data["revision"],
                value["id"],
                values["account"],
                channel=current.channel_id,
                action=values["action"][0],
            )
            return "The real reveal is saved for the actual addressed scene recipients."
    elif kind == "PlanGrant" and viewer.user_id == value["controller"]:
        fields = [
            Field(
                "account",
                "Actually reveal how that disobedience was part of your plan",
                paragraph=True,
            )
        ]

        async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
            await asyncio.to_thread(
                service.reveal_plan,
                viewer_from_interaction(current),
                str(current.id),
                data["revision"],
                value["id"],
                values["account"],
                channel=current.channel_id,
            )
            return "The actual reveal is saved for the addressed original scene participants."
    elif (
        kind == "Violation"
        and value["disclosed"]
        and not value["decided_event"]
        and viewer.user_id == value["controller"]
    ):
        fields = [
            Field(
                "punish",
                "Your actual Handler discipline decision",
                (
                    ("yes", "Use a genuine source-owned Punishment"),
                    ("no", "No Punishment for this actual breach"),
                ),
            ),
            Field("account", "Your actual discipline decision", paragraph=True),
        ]

        async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
            await asyncio.to_thread(
                service.decide_violation,
                viewer_from_interaction(current),
                str(current.id),
                data["revision"],
                value["id"],
                values["punish"][0] == "yes",
                values["account"],
            )
            return "The actual Handler decision is saved; complete any real Punishment source."

    if not fields:
        account = (
            value.get("answer")
            or value.get("account")
            or value.get("part")
            or "The original owned source is saved."
        )
        await reply(interaction, "Saved Prince record: " + account)
        return
    await NativeForm(
        interaction.user.id,
        "Prince: " + kind,
        "Actual original source and independently owned choices.",
        fields,
        submit,
    ).present(interaction)


async def open_prince(
    interaction: discord.Interaction,
    service: PrinceService,
    identity: str | None = None,
    *,
    page: int = 0,
) -> None:
    viewer = viewer_from_interaction(interaction)
    if identity:
        await _record(interaction, service, await asyncio.to_thread(service.view, viewer, identity))
        return
    if interaction.channel_id is None:
        raise WorkflowError("Use the actual original scene channel")
    channel = interaction.channel_id
    data = await asyncio.to_thread(service.menu, viewer, channel)
    targets = {x["id"]: ActorRef.model_validate(x["ref"]) for x in data["targets"]}
    options = [("buy", "Acquire an actual Prince Requisition")] if data["purchases"] else []
    if data["fanbase"]:
        options.extend(
            (
                ("perform", "Actually play a part for someone"),
                ("recognize", "Actual person seems to know my Frame legacy"),
                ("violation", "Record an actual demand breach/attempt"),
                ("exception", "Actual Keep/Disobey before going against demands"),
            )
        )
    tasks = data["tasks"][page * 20 : (page + 1) * 20]
    options.extend((x["id"], x["label"]) for x in tasks)
    if page:
        options.append(("previous", "Previous saved records"))
    if len(data["tasks"]) > (page + 1) * 20:
        options.append(("next", "More saved records"))
    if not options:
        await reply(interaction, "No actual owned Prince source is available here.")
        return

    async def choose(current: discord.Interaction, values: dict[str, Any]) -> None:
        selected = values["source"][0]
        if selected in ("previous", "next"):
            await open_prince(current, service, page=page + (1 if selected == "next" else -1))
            return
        if selected not in ("buy", "perform", "recognize", "violation", "exception"):
            await open_prince(current, service, selected)
            return
        if selected == "buy":
            fields = [
                Field(
                    "rule",
                    "Actual source-priced Requisition",
                    tuple(
                        (x["id"], x["title"] + " · " + str(x["price"]) + " Permissions")
                        for x in data["purchases"]
                    ),
                ),
                Field(
                    "quote",
                    "If financial partner owns your wallet",
                    (
                        ("no", "Complete my actual purchase"),
                        ("yes", "Request their exact source-price approval first"),
                    ),
                ),
                Field("account", "Actual acquisition request", paragraph=True),
            ]
        elif selected in ("perform", "recognize"):
            fields = [
                Field(
                    "target",
                    "Actual on-scene person",
                    tuple((x["id"], x["label"]) for x in data["targets"]),
                ),
                Field(
                    "account",
                    "Actual part/source or indication of legacy recognition",
                    paragraph=True,
                ),
            ]
            if selected == "perform":
                fields.extend(
                    [
                        Field("part", "The actual part you are playing", paragraph=True),
                        Field(
                            "following",
                            "Does this actual part follow current Fanbase demands?",
                            YES,
                        ),
                    ]
                )
        elif selected == "violation":
            fields = [
                Field("account", "Actual breach or deliberate contrary attempt", paragraph=True),
                Field("disclose", "Actually disclose this source to the Handler?", YES),
            ]
        else:
            fields = [
                Field(
                    "account",
                    "The actual named contrary act requiring Keep/Disobey",
                    paragraph=True,
                )
            ]

        async def submit(response: discord.Interaction, answers: dict[str, Any]) -> str:
            person = viewer_from_interaction(response)
            if selected == "buy":
                method = service.request_payment if answers["quote"] == ("yes",) else service.buy
                result = await asyncio.to_thread(
                    method,
                    person,
                    str(response.id),
                    data["revision"],
                    answers["rule"][0],
                    answers["account"],
                )
            elif selected == "perform":
                result = await asyncio.to_thread(
                    service.perform,
                    person,
                    str(response.id),
                    data["revision"],
                    channel,
                    targets[answers["target"][0]],
                    answers["part"],
                    answers["following"] == ("yes",),
                    answers["account"],
                )
            elif selected == "recognize":
                result = await asyncio.to_thread(
                    service.recognize,
                    person,
                    str(response.id),
                    data["revision"],
                    channel,
                    targets[answers["target"][0]],
                    answers["account"],
                )
            elif selected == "violation":
                result = await asyncio.to_thread(
                    service.report_violation,
                    person,
                    str(response.id),
                    data["revision"],
                    channel,
                    answers["account"],
                    answers["disclose"] == ("yes",),
                )
            else:
                result = await asyncio.to_thread(
                    service.exception_attempt,
                    person,
                    str(response.id),
                    data["revision"],
                    channel,
                    answers["account"],
                )
            return (
                "Actual Prince source saved: "
                + str(result["id"])
                + ". Reopen it from your private records."
            )

        await NativeForm(
            current.user.id,
            "Prince: " + selected,
            "Use actual original people, source facts and your own choices.",
            fields,
            submit,
        ).present(current)

    await NativeForm(
        interaction.user.id,
        "The Prince",
        "Actual protected fan demographics, owned source choices and saved private records.",
        [Field("source", "Your actual source or record", tuple(options))],
        choose,
    ).present(interaction)
