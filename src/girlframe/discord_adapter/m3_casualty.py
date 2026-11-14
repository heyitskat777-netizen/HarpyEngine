"""Private Casualty costs, real voluntary Sex choices, parts and source histories."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine import m3_casualty as rules
from girlframe.engine.m2 import ChoiceAnswer, PlayInput
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.services.m2_game import GameService
from girlframe.services.m3_casualty import CasualtyService


async def open_choice(
    interaction: discord.Interaction, game: GameService, decision: dict[str, Any]
) -> None:
    data, kind = decision["detail"], decision["kind"]
    if data.get("unsupported_npc") or data.get("waiting"):
        await reply(interaction, data["guidance"])
        return
    fields = []
    if data["options"] and kind != "casualty_focus":
        fields.append(
            Field("options", "Your actual printed choice", tuple(tuple(x) for x in data["options"]))
        )
    if kind in ("casualty_present", "casualty_high_part"):
        fields.append(
            Field(
                "parts",
                "Actual original body parts",
                tuple((x["id"], x["label"]) for x in data["parts"]),
                minimum=data["minimum"],
                maximum=data["maximum"],
                required=kind != "casualty_present",
            )
        )
    if kind == "casualty_focus":
        fields.extend(
            Field(
                x["id"],
                "Your actual response: " + x["label"],
                tuple(tuple(y) for y in data["options"]),
            )
            for x in data["presented"]
        )
    if kind == "casualty_unmark" and data["identities"]:
        fields.append(
            Field(
                "identity",
                "Optional actual marked Identity",
                tuple((x["id"], x["label"]) for x in data["identities"]),
                minimum=0,
                required=False,
            )
        )
    if kind == "casualty_high_asset" and not data.get("npc_damage"):
        fields.append(
            Field(
                "asset",
                "Actual counterpart Asset you damage",
                tuple((x["id"], x["label"]) for x in data["assets"]),
            )
        )
    if data.get("heat"):
        fields.append(Field("heat", "Your own printed Heat gain", (("3", "3"), ("4", "4"))))
    elif kind == "casualty_low_both":
        fields.extend(
            (
                Field("self", "Only if give: Tag you give yourself", required=False),
                Field("other", "Only if give: Tag you give the counterpart", required=False),
            )
        )
    elif kind != "casualty_unmark":
        fields.append(
            Field(
                "text",
                data["label"],
                paragraph=True,
                required=kind not in ("casualty_roll_push", "casualty_low_tag"),
            )
        )

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        options = (
            values.get("parts", ())
            if kind in ("casualty_present", "casualty_high_part")
            else values.get("options", ())
        )
        context = (
            {x["id"]: values[x["id"]][0] for x in data.get("presented", [])}
            if kind == "casualty_focus"
            else (
                {k: values.get(k, "") for k in ("self", "other")}
                if kind == "casualty_low_both" and options == ("give",)
                else {}
            )
        )
        await asyncio.to_thread(
            game.respond,
            viewer_from_interaction(current),
            str(current.id),
            decision["id"],
            decision["revision"],
            ChoiceAnswer(
                options=options,
                denied=values.get("asset", ()) or values.get("identity", ()),
                fields=context,
                text=values.get("text", ""),
                number=int(values["heat"][0]) if values.get("heat") else None,
            ),
        )
        return "Your actual choice is saved. Remaining choices and real consequences stay pending."

    form = NativeForm(
        interaction.user.id,
        "Your actual Casualty choice",
        "Real people, body and resources only. Breaking a Link prevents piloting until repair. "
        "Ordinary broken Brain is distinct from actual destruction. OOC pause remains available.",
        fields,
        submit,
    )
    await reply(interaction, form.text(), form)


async def open_learned_casualty(
    interaction: discord.Interaction, service: CasualtyService, lesson: str
) -> None:
    channel = int(interaction.channel_id or 0)
    data = await asyncio.to_thread(
        service.learned_menu, viewer_from_interaction(interaction), channel, lesson
    )
    targets = {ActorRef.model_validate(x["ref"]).token: x for x in data["targets"]}

    async def propose(current: discord.Interaction, values: dict[str, Any]) -> str:
        result = await asyncio.to_thread(
            service.invite,
            viewer_from_interaction(current),
            str(current.id),
            channel,
            ActorRef.model_validate(targets[values["target"][0]]["ref"]),
            data["revision"],
            values["account"],
            learned_source=lesson,
        )
        return (
            "Original-body source proposed; the actual counterpart independently answers: "
            + str(result["id"])
        )

    form = NativeForm(
        interaction.user.id,
        "Learned Casualty original-body source",
        "This lesson creates no body parts or consent. Use your original proven body.",
        [
            Field(
                "target",
                "Actual counterpart",
                tuple((key, x["label"]) for key, x in targets.items()),
            ),
            Field("account", "Your actual voluntary source", paragraph=True),
        ],
        propose,
    )
    await reply(interaction, form.text(), form)


async def open_casualty(
    interaction: discord.Interaction,
    service: CasualtyService,
    identity: str | None = None,
    *,
    page: int = 0,
    allow_withdraw: bool = True,
) -> None:
    viewer, channel = viewer_from_interaction(interaction), int(interaction.channel_id or 0)
    if identity:
        data = await asyncio.to_thread(service.view, viewer, identity)
        if data["kind"] != "sex":
            record = data["record"]
            label = data["source"]
            summary = "Your actual " + label + " source."
            if record.get("account"):
                summary += " Actual account: " + record["account"]
            if label == "Barely":
                summary += (
                    " Erased Identity: "
                    + record["identity"]["name"]
                    + "; repaired Asset: "
                    + record["asset_name"]
                )
            if record.get("part"):
                summary += " Original part: " + rules.LABELS[record["part"]]
            await reply(interaction, summary)
            return
        if allow_withdraw and data.get("can_withdraw"):
            options = [("withdraw", "Withdraw the unused invitation; preserve its source")]
            if data["can_roll"]:
                options.append(("continue", "Use this actually accepted source"))

            async def manage(current: discord.Interaction, values: dict[str, Any]) -> str | None:
                if values["operation"] == ("withdraw",):
                    await asyncio.to_thread(
                        service.withdraw_learned,
                        viewer_from_interaction(current),
                        str(current.id),
                        identity,
                        data["revision"],
                    )
                    return "Invitation withdrawn; a fresh source needs fresh consent."
                await open_casualty(current, service, identity, allow_withdraw=False)
                return None

            form = NativeForm(
                interaction.user.id,
                "Your learned original-body source",
                "Your original source remains private and belongs to its actual participants.",
                [Field("operation", "Action", tuple(options))],
                manage,
            )
            await reply(interaction, form.text(), form)
            return
        summary = "Your actual Casualty intimacy source: " + data["phase"] + ". " + data["proposal"]
        if data["target"]["kind"] == "npc":
            if data.get("npc_resources_ready"):
                summary += (
                    " Each beneficiary chooses their own 3–4 Heat. NPC harm uses the "
                    "actual attacker-owned printed consequence, and the NPC controller "
                    "chooses the Casualty's real broken part. Optional NPC unmarks use "
                    "witnessed original Identities."
                )
            else:
                summary += (
                    " NPC_RESOURCE_SETUP_REQUIRED: record this original NPC's actual "
                    "resources before a new roll. A retained high result remains pending "
                    "until real resources are supplied; its original roll is preserved. "
                    "Optional Identity unmark remains pending without actual resources; "
                    "the controller may explicitly decline it."
                )
        if not data["can_confirm"] and not data["can_roll"]:
            await reply(
                interaction,
                summary + ". Actual pending choices and damage work remain in Requests.",
            )
            return
        confirming = data["can_confirm"]
        if confirming:
            fields = [
                Field(
                    "accept",
                    "Your own actual voluntary response",
                    (("yes", "Voluntarily participate"), ("no", "Decline")),
                ),
                Field("account", "Your actual voluntary source account", paragraph=True),
                Field(
                    "npc_contact",
                    "NPC only: actual contact outside enclosures",
                    paragraph=True,
                    required=False,
                ),
            ]
        else:
            sheet = await asyncio.to_thread(service.game.sheet, viewer)
            fields = [
                Field(
                    "heat",
                    "Actual Heat spent",
                    tuple((str(x), str(x)) for x in range(sheet["heat"] + 1)),
                ),
                Field("account", "Actual performed source", paragraph=True),
            ]

        async def proceed(current: discord.Interaction, values: dict[str, Any]) -> str:
            if confirming:
                await asyncio.to_thread(
                    service.confirm,
                    viewer_from_interaction(current),
                    str(current.id),
                    identity,
                    data["revision"],
                    values["accept"][0] == "yes",
                    values["account"],
                    npc_contact_account=(values.get("npc_contact") or None)
                    if values["accept"][0] == "yes"
                    else None,
                )
            else:
                await asyncio.to_thread(
                    service.game.begin,
                    viewer_from_interaction(current),
                    str(current.id),
                    data["channel"],
                    sheet["revision"],
                    PlayInput(
                        play=rules.PLAY,
                        source_work=identity,
                        target_actor=ActorRef.model_validate(data["target"]),
                        heat=int(values["heat"][0]),
                        context=values["account"],
                        trigger_confirmed=True,
                    ),
                )
            return "Your actual source response is saved."

        form = NativeForm(
            viewer.user_id, "Your original voluntary Casualty source", summary, fields, proceed
        )
        await reply(interaction, form.text(), form)
        return
    menu = await asyncio.to_thread(service.menu, viewer, channel)
    options = [("replacement", "Missing hardware: supplied replacement and installation")]
    if menu.get("barely_available") and menu["identities"] and menu["assets"]:
        options.append(("barely", "Erase Identity to undamage a real Asset"))
    if menu["available"]:
        options.append(("body", "Record/review actual original ideal parts"))
        if any(x["condition"] == "broken" for x in menu["parts"]):
            options.append(("repair", "Repair one broken original part for1 Permission"))
            if menu.get("payment_needed"):
                options.append(("payment", "Ask financial partner to approve this exact1P repair"))
        if any(x["condition"] == "intact" for x in menu["parts"]):
            options.append(("helpless", "Actually push: break part and become Helpless"))
        if menu["sex_targets"]:
            options.append(("sex", "Propose actual voluntary Casualty intimacy"))
    if menu["find_targets"]:
        options.append(("find", "Actually find a source Helpless Casualty"))
    if menu["damage_targets"]:
        options.append(("damage", "Record your actual performed Handler part damage"))
    capacity = 25 - len(options) - 2
    pages = max(1, (len(menu["history"]) + capacity - 1) // capacity)
    page = min(max(page, 0), pages - 1)
    options.extend(
        (x["id"], x["label"]) for x in menu["history"][page * capacity : (page + 1) * capacity]
    )
    if page:
        options.append(("page:" + str(page - 1), "Previous saved records"))
    if page + 1 < pages:
        options.append(("page:" + str(page + 1), "Next saved records"))
    if not options:
        await reply(interaction, "No supported actual Casualty source or private history here.")
        return

    async def select(current: discord.Interaction, values: dict[str, Any]) -> str | None:
        kind = values["source"][0]
        if kind == "replacement":
            from girlframe.discord_adapter.m3_casualty_replacement import open_replacement
            from girlframe.services.m3_casualty_replacement import ReplacementService

            await open_replacement(current, ReplacementService(service.game))
            return None
        if kind.startswith("page:"):
            await open_casualty(current, service, page=int(kind.split(":")[1]))
            return None
        if kind == "body":
            await asyncio.to_thread(service.body, viewer_from_interaction(current), str(current.id))
            await open_casualty(current, service)
            return None
        if kind not in ("barely", "repair", "payment", "helpless", "sex", "find", "damage"):
            await open_casualty(current, service, kind)
            return None
        fields: list[Field] = []
        if kind == "barely":
            if menu.get("barely_lessons"):
                fields.append(
                    Field(
                        "lesson",
                        "Actual one-use lesson",
                        tuple((x["id"], x["label"]) for x in menu["barely_lessons"]),
                    )
                )
            fields.extend(
                (
                    Field(
                        "identity",
                        "Actual Identity erased",
                        tuple((x["id"], x["label"]) for x in menu["identities"]),
                    ),
                    Field(
                        "asset",
                        "Actual damaged Asset",
                        tuple((x["id"], x["label"]) for x in menu["assets"]),
                    ),
                )
            )
        if kind in ("repair", "payment", "helpless"):
            fields.append(
                Field(
                    "part",
                    "Actual original part",
                    tuple(
                        (x["id"], x["label"])
                        for x in menu["parts"]
                        if x["condition"]
                        == ("broken" if kind in ("repair", "payment") else "intact")
                    ),
                )
            )
        if kind == "sex":
            fields.append(
                Field(
                    "target",
                    "Actual original counterpart",
                    tuple(
                        (ActorRef.model_validate(x["ref"]).token, x["label"])
                        for x in menu["sex_targets"]
                    ),
                )
            )
        if kind == "find":
            fields.append(
                Field(
                    "found",
                    "Your actual role and encountered body",
                    tuple((x["id"], x["label"]) for x in menu["find_targets"]),
                )
            )
        if kind == "damage":
            fields.extend(
                (
                    Field(
                        "actor",
                        "Actual original Casualty",
                        tuple(
                            (ActorRef.model_validate(x["ref"]).token, x["label"])
                            for x in menu["damage_targets"]
                        ),
                    ),
                    Field(
                        "part",
                        "Actual original part",
                        tuple((x, rules.LABELS[x]) for x in rules.PARTS),
                    ),
                    Field(
                        "condition",
                        "Actual performed degree",
                        (
                            ("broken", "Broken"),
                            ("destroyed", "Actually destroyed"),
                            ("removed", "Actually removed"),
                        ),
                    ),
                )
            )
        if kind != "repair":
            fields.append(Field("account", "Your actual performed source account", paragraph=True))

        async def submit(response: discord.Interaction, answer: dict[str, Any]) -> str:
            human, key = viewer_from_interaction(response), str(response.id)
            if kind == "barely":
                await asyncio.to_thread(
                    service.barely,
                    human,
                    key,
                    menu["revision"],
                    answer["identity"][0],
                    answer["asset"][0],
                    answer["account"],
                    lesson=next(iter(answer.get("lesson", ())), None),
                )
            elif kind == "repair":
                await asyncio.to_thread(
                    service.repair_part, human, key, menu["revision"], answer["part"][0]
                )
            elif kind == "payment":
                await asyncio.to_thread(
                    service.request_part_payment,
                    human,
                    key,
                    menu["revision"],
                    answer["part"][0],
                    answer["account"],
                )
            elif kind == "helpless":
                await asyncio.to_thread(
                    service.push_helpless,
                    human,
                    key,
                    menu["revision"],
                    answer["part"][0],
                    answer["account"],
                )
            elif kind == "sex":
                actor = next(
                    x["ref"]
                    for x in menu["sex_targets"]
                    if ActorRef.model_validate(x["ref"]).token == answer["target"][0]
                )
                await asyncio.to_thread(
                    service.invite,
                    human,
                    key,
                    channel,
                    ActorRef.model_validate(actor),
                    menu["revision"],
                    answer["account"],
                )
            elif kind == "find":
                source = next(x for x in menu["find_targets"] if x["id"] == answer["found"][0])
                await asyncio.to_thread(
                    service.record_found,
                    human,
                    key,
                    source["source"],
                    menu["revision"],
                    ActorRef.model_validate(source["finder"]),
                    channel,
                    answer["account"],
                )
            else:
                actor = next(
                    x["ref"]
                    for x in menu["damage_targets"]
                    if ActorRef.model_validate(x["ref"]).token == answer["actor"][0]
                )
                await asyncio.to_thread(
                    service.damage_part,
                    human,
                    key,
                    menu["revision"],
                    ActorRef.model_validate(actor),
                    answer["part"][0],
                    answer["condition"][0],
                    answer["account"],
                )
            return (
                "Your real Casualty source/effect is saved. Existing mandatory work is preserved."
            )

        form = NativeForm(
            current.user.id,
            "Your actual Casualty source",
            "Broken-part repair costs1 Permission. Destroyed/removed parts "
            "need actual replacement. Brain destruction kills. "
            "Handler facts grant no consent or unrelated work closure. OOC pause stays available.",
            fields,
            submit,
        )
        await reply(current, form.text(), form)
        return None

    form = NativeForm(
        viewer.user_id,
        "Casualty original body/source controls",
        "Your actual source and private history.",
        [Field("source", "Actual source/control", tuple(options))],
        select,
    )
    await reply(interaction, form.text(), form)
