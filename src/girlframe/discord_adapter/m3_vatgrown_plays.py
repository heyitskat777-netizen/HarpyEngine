"""Private original-role Vatgrown learning, Investor and source-evidence controls."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine import m3_vatgrown_plays as rules
from girlframe.engine.creation_details import DESIRES
from girlframe.engine.m2 import ChoiceAnswer, PlayInput
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.services.m2_game import GameService
from girlframe.services.m3_vatgrown_plays import VatgrownPlaysService


async def open_choice(
    interaction: discord.Interaction, game: GameService, decision: dict[str, Any]
) -> None:
    detail, kind = decision["detail"], decision["kind"]
    service = VatgrownPlaysService(game)
    if kind == "vat_sex_depart":
        data = await asyncio.to_thread(
            service.view, viewer_from_interaction(interaction), detail["session"]
        )
        if detail["discipline"]:
            from girlframe.discord_adapter.m3_role_punishments import open_role_punishment
            from girlframe.services.m3_role_punishments import RolePunishmentService

            session = data["session"]
            with game.store.engine.connect() as c:
                from girlframe.services.m2_state import load_state

                state = load_state(c, game.store.campaign_id)
                discipline = rules.find(state, rules.Discipline, session["discipline"])
            if not discipline.completed_event:
                await open_role_punishment(
                    interaction, RolePunishmentService(game), discipline.case
                )
                return

        async def depart(current: discord.Interaction, values: dict[str, Any]) -> str:
            await asyncio.to_thread(
                service.depart,
                viewer_from_interaction(current),
                str(current.id),
                detail["session"],
                data["revision"],
                values["account"],
            )
            return "The actual counterpart left; the Vatgrown owns the remaining learning."

        form = NativeForm(
            interaction.user.id,
            "Actual departure",
            "Record your actual source departure after any chosen Punishment.",
            [Field("account", "Your actual departure", paragraph=True)],
            depart,
        )
        await reply(interaction, form.text(), form)
        return
    fields = []
    if kind == "vat_sex_learn":
        if detail["tier"] != "high":
            fields.append(
                Field(
                    "effects",
                    "Your actual learning choices",
                    tuple((x, x.replace("_", " ")) for x in detail["effects"]),
                    minimum=detail["required"],
                    maximum=detail["required"],
                )
            )
        if detail["identities"]:
            fields.append(
                Field(
                    "identities",
                    "If copying: actual counterpart Identities",
                    tuple((x["id"], x["name"]) for x in detail["identities"]),
                    minimum=0,
                    maximum=2,
                    required=False,
                )
            )
        else:
            fields.append(
                Field("identity", "If copying: one matching counterpart Identity", required=False)
            )
        fields.append(
            Field(
                "replacements",
                "Only required legal ordinary replacement slots",
                tuple((x["id"], x["name"]) for x in detail["replacements"]),
                minimum=0,
                maximum=2,
                required=False,
            )
        )
        if detail["plays"]:
            fields.append(
                Field(
                    "play",
                    "If learning: actual counterpart Play",
                    tuple((x["id"], x["label"]) for x in detail["plays"]),
                    minimum=0,
                    required=False,
                )
            )
        fields.extend(
            [
                Field(
                    "plans", "If selected: actual planning question", paragraph=True, required=False
                ),
                Field(
                    "good",
                    "If selected: how can I be good for you?",
                    paragraph=True,
                    required=False,
                ),
            ]
        )
    elif kind == "vat_sex_judge":
        fields.append(
            Field(
                "judgment",
                "Your actual answer judgment",
                (
                    ("accept", "I accept the actual answer"),
                    ("dislike", "I dislike it; no Punishment"),
                    ("punish", "I dislike it and choose real Punishment"),
                ),
            )
        )
    fields.append(
        Field(
            "account",
            "Your actual question or honest answer"
            if kind != "vat_sex_learn"
            else "Your actual learning account",
            paragraph=True,
        )
    )

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        options = (
            ("identity", "play")
            if kind == "vat_sex_learn" and detail["tier"] == "high"
            else tuple(values.get("effects", values.get("judgment", ())))
        )
        specific = {x: ",".join(values[x]) for x in ("identities", "replacements") if values.get(x)}
        specific.update({x: values[x] for x in ("identity", "plans", "good") if values.get(x)})
        if values.get("play"):
            specific["play"] = values["play"][0]
        await asyncio.to_thread(
            game.respond,
            viewer_from_interaction(current),
            str(current.id),
            decision["id"],
            decision["revision"],
            ChoiceAnswer(options=options, fields=specific, text=values["account"]),
        )
        return "Your original person's actual Vatgrown source choice is saved."

    form = NativeForm(
        interaction.user.id,
        "Vatgrown learning",
        (
            detail.get("question")
            or "High learning belongs to the counterpart. "
            "Leaving remains a separate actual obligation."
        ),
        fields,
        submit,
    )
    await reply(interaction, form.text(), form)


async def _sex(
    interaction: discord.Interaction, service: VatgrownPlaysService, data: dict[str, Any]
) -> None:
    value, viewer = data["session"], viewer_from_interaction(interaction)
    if data["choices"]:
        decision = await asyncio.to_thread(service.game.decision, viewer, data["choices"][0]["id"])
        await open_choice(interaction, service.game, decision)
        return
    if value["phase"] == "invited" and viewer.user_id == value["counterpart"]:

        async def respond(current: discord.Interaction, values: dict[str, Any]) -> str:
            await asyncio.to_thread(
                service.respond,
                viewer_from_interaction(current),
                str(current.id),
                value["id"],
                data["revision"],
                values["accept"][0] == "yes",
                values["account"],
            )
            return "Your actual voluntary source response is saved."

        form = NativeForm(
            interaction.user.id,
            "Actual voluntary source",
            value["proposal"] + "\nConfirm your own actual original person and this source only.",
            [
                Field("accept", "Your actual response", (("yes", "Confirm"), ("no", "Decline"))),
                Field("account", "Your actual own account", paragraph=True),
            ],
            respond,
        )
    elif value["phase"] == "accepted" and viewer.user_id == value["caster"]:
        sheet = await asyncio.to_thread(service.game.sheet, viewer)

        async def begin(current: discord.Interaction, values: dict[str, Any]) -> str:
            result = await asyncio.to_thread(
                service.game.begin,
                viewer_from_interaction(current),
                str(current.id),
                value["cast"]["channel"],
                sheet["revision"],
                PlayInput(
                    play=rules.PLAY,
                    source_work=value["id"],
                    heat=int(values["heat"][0]),
                    context=value["proposal"],
                    trigger_confirmed=True,
                ),
            )
            return "Actual source prepared: " + str(result["action_id"])

        form = NativeForm(
            interaction.user.id,
            "Vatgrown source roll",
            "Spend the actual available Heat under the ordinary rules.",
            [Field("heat", "Actual Heat", tuple((str(x), str(x)) for x in range(1, 11)))],
            begin,
        )
    elif data.get("side") and not data["side"]["released_event"] and not data["side"]["left_event"]:
        if viewer.user_id == value["caster"]:
            from girlframe.discord_adapter.m3_vatgrown_support import open_vatgrown_departure

            await open_vatgrown_departure(interaction, service.game, value["id"])
            return

        async def release(current: discord.Interaction, values: dict[str, Any]) -> str:
            await asyncio.to_thread(
                service.send_away,
                viewer_from_interaction(current),
                str(current.id),
                value["id"],
                data["revision"],
                values["account"],
            )
            return "The actual original counterpart sent the Vatgrown away."

        form = NativeForm(
            interaction.user.id,
            "Send the original Vatgrown away",
            "You own the actual source release, separate from OOC safety.",
            [Field("account", "Your actual release", paragraph=True)],
            release,
        )
    else:
        learning = "\n".join(
            ["Copied Identity: " + x["text"] for x in data.get("copies", ())]
            + [
                "Learned once: " + x["rule"].rsplit(".", 1)[-1].replace("-", " ")
                for x in data.get("learned", ())
            ]
        )
        if any(x.get("can_dose") for x in data.get("learned", ())):

            async def dose(current: discord.Interaction, values: dict[str, Any]) -> None:
                from girlframe.discord_adapter.m3_dose_up import open_dose_up
                from girlframe.services.m3_dose_up import DoseUpService

                await open_dose_up(current, DoseUpService(service.game.store, service.game))

            form = NativeForm(
                interaction.user.id,
                "Actual learned Dose Up",
                learning + "\nUse your own body and Heat for this one learned Play.",
                [Field("action", "Actual learned Play", (("dose", "Use actual Dose Up"),))],
                dose,
            )
            await reply(interaction, form.text(), form)
            return
        await reply(
            interaction,
            "Saved Vatgrown source: "
            + value["phase"]
            + "\n"
            + (value["answer"] or value["proposal"])
            + ("\n" + learning if learning else ""),
        )
        return
    await reply(interaction, form.text(), form)


async def _investment(
    interaction: discord.Interaction, service: VatgrownPlaysService, data: dict[str, Any]
) -> None:
    value, viewer = data["investment"], viewer_from_interaction(interaction)
    fields: list[Field] = []
    if value["phase"] == "select" and str(viewer.user_id) == value["owner"]["entity"]:

        async def select(current: discord.Interaction, answers: dict[str, Any]) -> None:
            investor = next(x for x in data["investors"] if x["id"] == answers["investor"][0])

            async def remove(response: discord.Interaction, values: dict[str, Any]) -> str:
                await asyncio.to_thread(
                    service.low_investor,
                    viewer_from_interaction(response),
                    str(response.id),
                    value["id"],
                    data["revision"],
                    ActorRef.model_validate(investor["actor"]),
                    values["desire"][0],
                    values["account"],
                )
                return (
                    "The actual desire was removed; the original Investor still owes the real Tag."
                )

            form = NativeForm(
                current.user.id,
                "Waning Investor",
                "Remove one actual desire for this actual low period.",
                [
                    Field(
                        "desire",
                        "Actual current desire",
                        tuple((x, x) for x in investor["desires"]),
                    ),
                    Field("account", "Actual interest loss", paragraph=True),
                ],
                remove,
            )
            await reply(current, form.text(), form)

        form = NativeForm(
            interaction.user.id,
            "Prime Investment low",
            "Choose the actual waning Investor.",
            [
                Field(
                    "investor",
                    "Actual Investor",
                    tuple(
                        (x["id"], x["actor"]["kind"] + ":" + x["actor"]["entity"])
                        for x in data["investors"]
                        if x["desires"]
                    ),
                )
            ],
            select,
        )
        await reply(interaction, form.text(), form)
        return
    if value["phase"] == "low_tag" and viewer.user_id == value["controller"]:
        fields = [Field("account", "Your actual Tag label")]

        async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
            await asyncio.to_thread(
                service.low_tag,
                viewer_from_interaction(current),
                str(current.id),
                value["id"],
                data["revision"],
                values["account"],
            )
            return "The actual original Investor gave the required Tag."
    elif value["phase"] == "judgment" and viewer.user_id == value["controller"]:
        fields = [
            Field(
                "good",
                "Actual performed work was good?",
                (("yes", "Yes: offer actual answer favour"), ("no", "No favour")),
            ),
            Field(
                "question", "If good: question you offer to answer", paragraph=True, required=False
            ),
            Field("account", "Your actual source judgment", paragraph=True),
        ]

        async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
            await asyncio.to_thread(
                service.judge_scene,
                viewer_from_interaction(current),
                str(current.id),
                value["id"],
                data["revision"],
                values["good"][0] == "yes",
                values.get("question", ""),
                values["account"],
            )
            return "The original Investor's actual scene judgment and offer are saved."
    elif value["phase"] == "new_desire" and viewer.user_id == value["controller"]:
        fields = [
            Field("desire", "Your actual new desire"),
            Field("account", "Actual source context", paragraph=True),
        ]

        async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
            await asyncio.to_thread(
                service.new_desire,
                viewer_from_interaction(current),
                str(current.id),
                value["id"],
                data["revision"],
                values["desire"],
                values["account"],
            )
            return "The actual desire was added; a gift requires genuine fulfilment."
    elif value["phase"] == "fulfilment_judgment" and viewer.user_id == value["controller"]:
        fields = [
            Field(
                "fulfilled",
                "Did the actual completed performance fulfil your desire?",
                (("yes", "Yes: offer the chosen actual Girl Requisition"), ("no", "No reward")),
            ),
            Field(
                "gift",
                "Your suitable actual Girl Requisition",
                (
                    ("creature_comforts", "Creature Comforts"),
                    ("privacy", "Privacy"),
                    ("visiting_home", "Visiting Home"),
                    ("retirement", "Retirement"),
                ),
            ),
            Field("account", "Actual outcome and suitability judgment", paragraph=True),
        ]

        async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
            await asyncio.to_thread(
                service.fulfil,
                viewer_from_interaction(current),
                str(current.id),
                value["id"],
                data["revision"],
                values["fulfilled"][0] == "yes",
                values["account"],
                kind=values["gift"][0],
            )
            return "The actual fulfilment judgment is saved."
    elif value["phase"] == "fulfil" and str(viewer.user_id) == value["owner"]["entity"]:
        from girlframe.discord_adapter.m3_vatgrown_support import open_investment_performance

        await open_investment_performance(interaction, service.game, value["id"])
        return
    else:
        await reply(
            interaction,
            "Actual Prime Investment: "
            + value["phase"]
            + ".\n"
            + (
                value["desire"]
                or "Complete the real OffDuty scene/invitations through its period card."
            ),
        )
        return
    form = NativeForm(
        interaction.user.id,
        "Prime Investment",
        "Actual original Investor, period and human-owned outcome.",
        fields,
        submit,
    )
    await reply(interaction, form.text(), form)


async def open_vatgrown_plays(
    interaction: discord.Interaction, service: VatgrownPlaysService, identity: str | None = None
) -> None:
    viewer = viewer_from_interaction(interaction)
    if identity is None:
        data = await asyncio.to_thread(service.menu, viewer, int(interaction.channel_id or 0))
        options = [(x["id"], x["label"]) for x in data["tasks"]]
        if data["can_invite"]:
            options.insert(0, ("invite", "Actual voluntary Vatgrown source"))
        if data["possible_investors"]:
            options.append(("investor", "Propose actual added Investor"))
        if not options:
            await reply(
                interaction, "No owned remaining Vatgrown source or available actual source here."
            )
            return

        async def choose(current: discord.Interaction, values: dict[str, Any]) -> None:
            chosen = values["source"][0]
            if chosen not in ("invite", "investor"):
                await open_vatgrown_plays(current, service, chosen)
                return
            candidates = data["targets"] if chosen == "invite" else data["possible_investors"]
            fields = [
                Field(
                    "target",
                    "Actual original scene person",
                    tuple((x["id"], x["label"]) for x in candidates),
                ),
                Field("account", "Actual voluntary proposal", paragraph=True),
            ]
            if chosen == "investor":
                fields.insert(
                    1,
                    Field(
                        "desires",
                        "One or two printed Investor desires",
                        tuple((x, x) for x in DESIRES),
                        minimum=1,
                        maximum=2,
                    ),
                )

            async def propose(response: discord.Interaction, answers: dict[str, Any]) -> str:
                target = ActorRef.model_validate(
                    next(x["ref"] for x in candidates if x["id"] == answers["target"][0])
                )
                if chosen == "invite":
                    result = await asyncio.to_thread(
                        service.invite,
                        viewer_from_interaction(response),
                        str(response.id),
                        data["channel"],
                        target,
                        data["revision"],
                        answers["account"],
                    )
                else:
                    result = await asyncio.to_thread(
                        service.propose_investor,
                        viewer_from_interaction(response),
                        str(response.id),
                        data["revision"],
                        target,
                        tuple(answers["desires"]),
                        answers["account"],
                    )
                return "Your actual source proposal is saved: " + str(result["id"])

            form = NativeForm(
                current.user.id,
                "Actual Vatgrown proposal",
                "Use original people and their own confirmations. "
                "Handler disclosure remains private.",
                fields,
                propose,
            )
            await reply(current, form.text(), form)

        form = NativeForm(
            interaction.user.id,
            "Vatgrown sources",
            "Private remaining source workflows and durable original history.",
            [Field("source", "Actual source", tuple(options))],
            choose,
        )
        await reply(interaction, form.text(), form)
        return
    data = await asyncio.to_thread(service.view, viewer, identity)
    if data["type"] == "sex":
        await _sex(interaction, service, data)
        return
    if data["type"] == "investment":
        await _investment(interaction, service, data)
        return
    if data["type"] == "offer":
        from girlframe.services.m3_vatgrown_support import accept_offer

        async def accept(current: discord.Interaction, values: dict[str, Any]) -> str:
            result = await asyncio.to_thread(
                accept_offer,
                service.game,
                viewer_from_interaction(current),
                str(current.id),
                identity,
                data["revision"],
                values["account"],
            )
            return "The actual offered Creature Comforts receipt is saved: " + str(result)

        form = NativeForm(
            interaction.user.id,
            "Offered Girl Requisition",
            "Actual Investor-funded Creature Comforts. No false purchase or Permission charge.",
            [Field("account", "Your actual acceptance", paragraph=True)],
            accept,
        )
    elif data["type"] == "favour":
        value = data["favour"]
        if not value["resolution_event"] and viewer.user_id == value["controller"]:

            async def resolve_favour(current: discord.Interaction, values: dict[str, Any]) -> str:
                await asyncio.to_thread(
                    service.favour_reply,
                    viewer_from_interaction(current),
                    str(current.id),
                    identity,
                    data["revision"],
                    values["back"][0] == "yes",
                    values["account"],
                )
                return "Your actual offered answer or explicit back-down is saved."

            form = NativeForm(
                interaction.user.id,
                "Actual offered favour",
                value["question"],
                [
                    Field(
                        "back",
                        "Back down instead of actually answering?",
                        (("no", "Give actual answer"), ("yes", "Explicitly back down")),
                    ),
                    Field("account", "Actual answer or back-down account", paragraph=True),
                ],
                resolve_favour,
            )
        elif (
            value["backed_down"] is True
            and not value["tag_event"]
            and value["actor"]["entity"] == str(viewer.user_id)
        ):

            async def give_tag(current: discord.Interaction, values: dict[str, Any]) -> str:
                await asyncio.to_thread(
                    service.favour_tag,
                    viewer_from_interaction(current),
                    str(current.id),
                    identity,
                    data["revision"],
                    values["give"][0] == "yes",
                    values["account"],
                )
                return "Your actual optional Investor Tag choice is saved."

            form = NativeForm(
                interaction.user.id,
                "Actual Investor back-down",
                "You own this optional Tag, independent of the completed period.",
                [
                    Field("give", "Give a Tag?", (("yes", "Give"), ("no", "Decline"))),
                    Field("account", "Actual Tag label or decline", paragraph=True),
                ],
                give_tag,
            )
        else:
            await reply(
                interaction,
                value["question"]
                + "\n"
                + (value["answer"] or "Waiting for the actual original party."),
            )
            return
    elif data["type"] == "violation":
        value = data["violation"]
        if viewer.user_id == value["author"] and not value["disclosed_event"]:

            async def disclose(current: discord.Interaction, values: dict[str, Any]) -> str:
                await asyncio.to_thread(
                    service.disclose,
                    viewer_from_interaction(current),
                    str(current.id),
                    identity,
                    data["revision"],
                    values["account"],
                )
                return "Your actual explicit Handler disclosure is saved."

            form = NativeForm(
                interaction.user.id,
                "Private original evidence",
                value["account"]
                + "\nSubmitting explicitly discloses this private source to the Handler.",
                [Field("account", "Your actual explicit disclosure", paragraph=True)],
                disclose,
            )
        elif (
            not value["judgment_event"]
            and value["disclosed_handler"]
            and value["disclosed_handler"]["entity"] == str(viewer.user_id)
        ):

            async def judge(current: discord.Interaction, values: dict[str, Any]) -> str:
                await asyncio.to_thread(
                    service.judge_violation,
                    viewer_from_interaction(current),
                    str(current.id),
                    identity,
                    data["revision"],
                    values["punish"][0] == "yes",
                    values["account"],
                )
                return "The actual known evidence and optional discipline decision are saved."

            form = NativeForm(
                interaction.user.id,
                "Actual disclosed evidence",
                value["account"],
                [
                    Field("punish", "Choose real Punishment?", (("yes", "Yes"), ("no", "No"))),
                    Field("account", "Your actual source adjudication", paragraph=True),
                ],
                judge,
            )
        else:
            await reply(
                interaction,
                value["account"]
                + "\nActual source judgment: "
                + (value["judgment_event"] or "Not disclosed or awaiting the original Handler."),
            )
            return
    else:
        value = data["investor"]
        if value["added_event"]:
            await reply(interaction, "Actual Investor: " + ", ".join(value["desires"]))
            return
        if not value["quote_event"]:

            async def quote(current: discord.Interaction, values: dict[str, Any]) -> str:
                price = int(values["price"]) if value["actor"]["kind"] == "pilot" else None
                await asyncio.to_thread(
                    service.quote_investor,
                    viewer_from_interaction(current),
                    str(current.id),
                    identity,
                    data["revision"],
                    price,
                    values["account"],
                )
                return "The actual Handler consent and exact quote are saved."

            fields = [Field("account", "Your actual Handler consent", paragraph=True)]
            if value["actor"]["kind"] == "pilot":
                fields.insert(0, Field("price", "Exact positive Permission price"))
            form = NativeForm(
                interaction.user.id,
                "Actual Investor quote",
                "A Girl must voluntarily confirm the Handler's exact positive quote.",
                fields,
                quote,
            )
        else:

            async def pay(current: discord.Interaction, values: dict[str, Any]) -> str:
                await asyncio.to_thread(
                    service.accept_investor,
                    viewer_from_interaction(current),
                    str(current.id),
                    identity,
                    data["revision"],
                    values["account"],
                )
                return "The actual Investor source and voluntary quoted payment are saved."

            form = NativeForm(
                interaction.user.id,
                "Actual Investor acceptance",
                "Quoted Permissions: "
                + str(value["quote"])
                + ". Confirm only your own actual spend.",
                [Field("account", "Actual explicit acceptance", paragraph=True)],
                pay,
            )
    await reply(interaction, form.text(), form)
