"""Addressed Marriage notice, exact financial approval and actual witnessed discovery."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.ledger import clean
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.m3_punishments import Picker
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.services.m3_intracadre_marriage import MarriageService


async def open_marriage(
    interaction: discord.Interaction, service: MarriageService, identity: str | None = None
) -> None:
    viewer = viewer_from_interaction(interaction)
    data = await asyncio.to_thread(service.view, viewer, identity)
    if "source" not in data:
        if data["marriages"] and identity is None:
            choices = {x["id"]: x["label"] for x in data["marriages"]}

            async def saved(current: discord.Interaction, selected: str) -> None:
                await open_marriage(current, service, selected)

            await reply(
                interaction,
                "Your actual Marriage records and saved controls.",
                Picker(viewer.user_id, "Marriage records", tuple(choices.items()), saved),
            )
            return
        girls = {ActorRef.model_validate(x["ref"]).token: x for x in data["girls"]}
        held = [x for x in data["awards"] if identity in (None, x["id"])]
        if not data["can_declare"] or len(girls) < 2 or not held:
            await reply(interaction, "No actual held Marriage Award and eligible original pair.")
            return

        async def declare(current: discord.Interaction, values: dict[str, Any]) -> str:
            first = ActorRef.model_validate(girls[values["first"][0]]["ref"])
            second = ActorRef.model_validate(girls[values["second"][0]]["ref"])
            result = await asyncio.to_thread(
                service.declare,
                viewer_from_interaction(current),
                str(current.id),
                values["award"][0],
                data["revision"],
                first,
                second,
                first if values["financial"][0] == "first" else second,
                first if values["status"][0] == "first" else second,
                values["account"],
            )
            return (
                "Partners declared. Both original Girls have their addressed notice "
                "in Requests. Reference: " + str(result["id"])
            )

        form = NativeForm(
            viewer.user_id,
            "Declare Intracadre Marriage",
            "Deepen the real Bond. Choose the shared Status anchor and the financial partner; "
            "the other takes both Girls' Punishments. Human dialogue and OOC pause stay voluntary.",
            [
                Field(
                    "award", "Actual held advancement", tuple((x["id"], x["label"]) for x in held)
                ),
                Field(
                    "first", "First original Girl", tuple((k, x["label"]) for k, x in girls.items())
                ),
                Field(
                    "second",
                    "Second original Girl",
                    tuple((k, x["label"]) for k, x in girls.items()),
                ),
                Field(
                    "financial",
                    "Who controls both Permissions?",
                    (("first", "First Girl"), ("second", "Second Girl")),
                ),
                Field(
                    "status",
                    "Whose existing Status becomes shared?",
                    (("first", "First Girl"), ("second", "Second Girl")),
                ),
                Field("account", "Your actual addressed declaration to the pair", paragraph=True),
            ],
            declare,
        )
        await reply(interaction, form.text(), form)
        return
    source = data["source"]
    lines = [
        "**Intracadre Marriage — addressed original-pair notice**",
        clean(source["account"]),
        "Financial partner: "
        + clean(data["names"][source["financial"]["entity"]])
        + "; Punishment partner: "
        + clean(data["names"][source["punished"]["entity"]]),
        "Shared budget: " + str(data["permissions"]) + " Permissions."
        if data["permissions"] is not None
        else "Shared budget is private to the original pair.",
        clean(data["legal_partner_sex"]),
        "Outsider Flirt may lead to Punishment when actually caught; no automatic chat monitoring.",
    ]
    if data["recovery"]:
        await reply(interaction, "\n\n".join(lines + [data["recovery"]])[:1950])
        return
    if data.get("quote"):
        quote = data["quote"]
        lines.extend(
            [
                "Requested product: " + clean(quote["product"].replace("_", " ")),
                "Exact price: " + str(quote["price"]) + " Permissions.",
                clean(quote["account"]),
            ]
        )
        task = next(x for x in data["tasks"] if x["id"] == quote["id"])
        if task["pending"] and quote["wallet"]["entity"] == str(viewer.user_id):

            async def approve(current: discord.Interaction, values: dict[str, Any]) -> str:
                await asyncio.to_thread(
                    service.approve_payment,
                    viewer_from_interaction(current),
                    str(current.id),
                    quote["id"],
                    data["revision"],
                    values["account"],
                )
                return (
                    "Exact payment authorized. No funds reserved; the original Girl's player "
                    "completes the existing purchase."
                )

            form = NativeForm(
                viewer.user_id,
                "Approve this exact Marriage payment",
                "\n\n".join(lines),
                [Field("account", "Your actual spending decision", paragraph=True)],
                approve,
            )
            await reply(interaction, form.text(), form)
        else:
            lines.append(
                "Complete an approved product through its existing "
                "original-recipient purchase control."
            )
            await reply(interaction, "\n\n".join(lines)[:1950])
        return
    for caught in data.get("caught", []):
        lines.extend(
            [
                "**Actual witnessed outsider Flirt**",
                clean(caught["account"]),
                "Allocated Punishment source: " + caught["work"],
            ]
        )
    options = [(x["id"], x["label"]) for x in data["tasks"] if x["id"] != source["id"]]
    if str(viewer.user_id) in (source["first"]["entity"], source["second"]["entity"]):
        if str(viewer.user_id) != source["financial"]["entity"]:
            options.insert(0, ("request", "Request an exact source-priced payment"))
    options.append(("caught", "Report an outsider Flirt you actually witnessed"))

    async def choose(current: discord.Interaction, selected: str) -> None:
        if selected == "request":
            products = await asyncio.to_thread(
                service.products, viewer_from_interaction(current), source["id"]
            )
            categories = tuple(dict.fromkeys(x["category"] for x in products))

            async def category(
                next_interaction: discord.Interaction, selected_category: str
            ) -> None:
                grouped = [x for x in products if x["category"] == selected_category]
                product_ids = tuple(dict.fromkeys(x["product"] for x in grouped))

                async def product(final_interaction: discord.Interaction, product_id: str) -> None:
                    choices = {
                        str(i): x for i, x in enumerate(grouped) if x["product"] == product_id
                    }

                    async def request(submit: discord.Interaction, values: dict[str, Any]) -> str:
                        chosen = choices[values["product"][0]]
                        result = await asyncio.to_thread(
                            service.request_payment,
                            viewer_from_interaction(submit),
                            str(submit.id),
                            source["id"],
                            data["revision"],
                            chosen["product"],
                            chosen["detail"],
                            values["account"],
                        )
                        return (
                            "Exact payment request saved for your financial partner. Reference: "
                            + str(result["id"])
                        )

                    form = NativeForm(
                        viewer.user_id,
                        "Request exact source-priced payment",
                        "No reservation or debt. Your partner decides the spending; "
                        "you still complete "
                        "the existing purchase with your own original body and resource choices.",
                        [
                            Field(
                                "product",
                                "Actual product / source",
                                tuple(
                                    (k, x["label"] + " — " + str(x["price"]) + "P")
                                    for k, x in choices.items()
                                ),
                            ),
                            Field("account", "Actual purchase request", paragraph=True),
                        ],
                        request,
                    )
                    await reply(final_interaction, form.text(), form)

                await reply(
                    next_interaction,
                    "Choose the actual priced product.",
                    Picker(
                        viewer.user_id,
                        "Product",
                        tuple(
                            (x, x.rsplit(".", 1)[-1].replace("_", " ").replace("-", " "))
                            for x in product_ids
                        ),
                        product,
                    ),
                )

            await reply(
                current,
                "Choose your actual purchase source.",
                Picker(
                    viewer.user_id, "Purchase category", tuple((x, x) for x in categories), category
                ),
            )
        elif selected == "caught":
            candidates = await asyncio.to_thread(
                service.witnessed_flirts, viewer_from_interaction(current), source["id"]
            )
            if not candidates:
                await reply(
                    current,
                    "No completed outsider Flirt has a supported source-time "
                    "physical witness role for you.",
                )
                return
            indexed = {str(i): x for i, x in enumerate(candidates)}

            async def report(submit: discord.Interaction, values: dict[str, Any]) -> str:
                witnessed = indexed[values["action"][0]]
                result = await asyncio.to_thread(
                    service.report_caught,
                    viewer_from_interaction(submit),
                    str(submit.id),
                    source["id"],
                    witnessed["id"],
                    ActorRef.model_validate(witnessed["observer"]),
                    values["account"],
                )
                return (
                    "Actual observation addressed to the original pair and Handler. "
                    "Required Punishment: " + str(result["work"])
                )

            form = NativeForm(
                viewer.user_id,
                "Actually caught an outsider Flirt",
                "Physical presence alone does not report anything. State only the fictional moment "
                "you actually witnessed; private chat/OOC cast knowledge is not discovery.",
                [
                    Field(
                        "action",
                        "Actual performed Flirt",
                        tuple((k, x["label"]) for k, x in indexed.items()),
                    ),
                    Field(
                        "account", "What you actually witnessed (addressed report)", paragraph=True
                    ),
                ],
                report,
            )
            await reply(current, form.text(), form)
        else:
            await open_marriage(current, service, selected)

    if options:
        await reply(
            interaction,
            "\n\n".join(lines)[:1950],
            Picker(viewer.user_id, "Marriage controls", tuple(options), choose),
        )
    else:
        await reply(interaction, "\n\n".join(lines)[:1950])
