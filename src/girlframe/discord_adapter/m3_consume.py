"""Owned CONSUME source choices, actual acquisitions and durable private controls."""

import asyncio
import json
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.ledger import clean
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.m3_memory_pages import MemoryForm, MemoryHistory
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine import m3_consume as rules
from girlframe.engine.m2 import ChoiceAnswer, PlayInput
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.services.m2_game import GameService
from girlframe.services.m3_consume import ConsumeService
from girlframe.services.onboarding import WorkflowError


async def open_choice(
    interaction: discord.Interaction, game: GameService, decision: dict[str, Any]
) -> None:
    data, kind = decision["detail"], decision["kind"]
    if kind in ("consume_child", "consume_order_child"):
        from girlframe.discord_adapter.m2_ui import open_play

        await open_play(interaction, game, parent=decision)
        return
    fields = []
    if data["options"]:
        fields.append(
            Field("option", "Your actual printed outcome", tuple(tuple(x) for x in data["options"]))
        )
    if kind == "consume_eat":
        if data["own_cost"]:
            fields.append(
                Field(
                    "own_asset",
                    "Your actual Asset to damage",
                    tuple(tuple(x) for x in data["own_assets"]),
                )
            )
        if data["target_assets"]:
            fields.append(
                Field(
                    "target_asset",
                    "If biting: actual target Asset",
                    tuple(tuple(x) for x in data["target_assets"]),
                    minimum=0,
                    required=False,
                )
            )
    elif kind == "consume_time_eat" and data["identities"]:
        fields.append(
            Field(
                "identity",
                "If giving: your actual Identity to mark",
                tuple(tuple(x) for x in data["identities"]),
                minimum=0,
                required=False,
            )
        )
    elif kind == "consume_partake":
        fields.append(
            Field(
                "girl_asset",
                "Your actual Girl Asset",
                tuple(tuple(x) for x in data["girl_assets"]),
                minimum=0,
                required=False,
            )
        )
        if data["frame_assets"]:
            fields.append(
                Field(
                    "frame_assets",
                    "If regrowing: up to two Frame Assets",
                    tuple(tuple(x) for x in data["frame_assets"]),
                    minimum=0,
                    maximum=2,
                    required=False,
                )
            )
        if data["frame_replacements"]:
            fields.append(
                Field(
                    "replace_frame",
                    "If excreting at cap: Frame Asset to replace",
                    tuple(tuple(x) for x in data["frame_replacements"]),
                    minimum=0,
                    required=False,
                )
            )
        fields.extend(
            [
                Field("new_name", "If excreting: actual new Frame Asset name", required=False),
                Field(
                    "new_description",
                    "If excreting: actual new Frame Asset description",
                    paragraph=True,
                    required=False,
                ),
                Field(
                    "appearance",
                    "If emerging changed: your actual new appearance",
                    paragraph=True,
                    required=False,
                ),
            ]
        )
    fields.append(
        Field(
            "account",
            "Your actual Tag"
            if kind == "consume_feral" and data["tier"] == "low"
            else "Your actual source account",
            paragraph=True,
        )
    )

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str | None:
        option = values.get("option", ())
        selected = option[0] if option else None
        supplied: dict[str, str] = {}
        if kind == "consume_eat":
            if values.get("own_asset"):
                supplied["own_asset"] = values["own_asset"][0]
            if selected == "bite" and values.get("target_asset"):
                supplied["target_asset"] = values["target_asset"][0]
        elif kind == "consume_time_eat" and selected == "give" and values.get("identity"):
            supplied["identity"] = values["identity"][0]
        elif kind == "consume_partake" and selected != "pass":
            if values.get("girl_asset"):
                supplied["girl_asset"] = values["girl_asset"][0]
            if selected == "regrow":
                chosen = tuple(values.get("frame_assets", ()))
                supplied["frame_assets"] = json.dumps(list(chosen))
                missing = [token for token in chosen if token in data["regrow_missing"]]
                at_cap = missing[data["regrow_free"] :]
                if at_cap:
                    replacements = tuple(
                        (key, label)
                        for key, label in data["regrow_replacements"]
                        if key not in chosen
                    )
                    if len(replacements) < len(at_cap):
                        raise WorkflowError(
                            "Make actual legal Frame space before selecting this regrowth"
                        )

                    async def access(response: discord.Interaction) -> None:
                        await asyncio.to_thread(
                            game.decision, viewer_from_interaction(response), decision["id"]
                        )

                    async def replace(
                        response: discord.Interaction, answers: dict[str, Any]
                    ) -> str:
                        mapping = {
                            token: answers["replacement_" + str(index)][0]
                            for index, token in enumerate(at_cap)
                        }
                        fields = supplied | {"regrow_replacements": json.dumps(mapping)}
                        await asyncio.to_thread(
                            game.respond,
                            viewer_from_interaction(response),
                            str(response.id),
                            decision["id"],
                            decision["revision"],
                            ChoiceAnswer(
                                options=tuple(option), fields=fields, text=values["account"]
                            ),
                        )
                        return "The actual Girl cost and source-proved regrowth are saved."

                    form = MemoryForm(
                        current.user.id,
                        "Actual Frame space",
                        "Choose a distinct actual non-Void replacement "
                        "for each component at the cap.",
                        [
                            Field(
                                "replacement_" + str(index),
                                "Replace for " + dict(data["frame_assets"])[token],
                                replacements,
                            )
                            for index, token in enumerate(at_cap)
                        ],
                        replace,
                        authorize=access,
                    )
                    await reply(current, form.text(), form)
                    return None
            elif selected == "excrete":
                supplied["new_asset"] = json.dumps(
                    dict(
                        name=values.get("new_name", ""),
                        description=values.get("new_description", ""),
                        damaged=False,
                        void=True,
                    )
                )
                if values.get("replace_frame"):
                    supplied["replace_frame"] = values["replace_frame"][0]
            elif selected == "appearance":
                supplied["appearance"] = values.get("appearance", "")
        await asyncio.to_thread(
            game.respond,
            viewer_from_interaction(current),
            str(current.id),
            decision["id"],
            decision["revision"],
            ChoiceAnswer(options=tuple(option), fields=supplied, text=values["account"]),
        )
        return "Your actual owned CONSUME source choice is saved."

    form = NativeForm(
        interaction.user.id,
        "CONSUME",
        "Choose your own actual printed consequence. "
        "Required real effects and performance remain owed.",
        fields,
        submit,
    )
    await reply(interaction, form.text(), form)


async def open_consume(
    interaction: discord.Interaction, service: ConsumeService, identity: str | None = None
) -> None:
    viewer, channel = viewer_from_interaction(interaction), int(interaction.channel_id or 0)
    if identity is not None:
        saved = await asyncio.to_thread(service.view, viewer, identity)
        source = saved["source"]
        if saved["type"] == "permit":
            if source["completed_event"] or source["superior"] is True:
                await reply(
                    interaction,
                    "Saved actual Cannibal target: "
                    + ("acquired" if source["receipt"] else "excluded by the actual hierarchy fact")
                    + ".",
                )
                return
            if source["review_event"] is None and viewer.user_id != source["handler_controller"]:
                await reply(
                    interaction, "Waiting for the original Handler's factual hierarchy account."
                )
                return
            if source["review_event"] is None:
                fields = [
                    Field(
                        "superior",
                        "Is this actual target your superior?",
                        (("no", "No"), ("yes", "Yes")),
                    ),
                    Field("account", "Your actual factual hierarchy account", paragraph=True),
                ]

                async def review(current: discord.Interaction, values: dict[str, Any]) -> str:
                    await asyncio.to_thread(
                        service.review_permit,
                        viewer_from_interaction(current),
                        str(current.id),
                        identity,
                        saved["revision"],
                        values["superior"] == ("yes",),
                        values["account"],
                    )
                    return "The original Handler's factual hierarchy account is saved."

                form = NativeForm(
                    interaction.user.id,
                    "Actual Cannibal target",
                    "This records the real hierarchy; it does not author anyone's consent.",
                    fields,
                    review,
                )
                await reply(interaction, form.text(), form)
                return
            if not saved["own"]:
                await reply(
                    interaction,
                    "Your factual hierarchy account is saved; "
                    "the original Pilot owns the actual payment choice.",
                )
                return
            menu = await asyncio.to_thread(service.menu, viewer, channel)

            async def acquire_permit(current: discord.Interaction, values: dict[str, Any]) -> str:
                await asyncio.to_thread(
                    service.purchase,
                    viewer_from_interaction(current),
                    str(current.id),
                    menu["source_sha256"],
                    rules.FORMS,
                    values["account"],
                    hierarchy=identity,
                )
                return "Your actual two-Permission target-specific legal Requisition is saved."

            form = NativeForm(
                interaction.user.id,
                "Cannibal Requisition Forms",
                "Confirm exactly two of your actual Permissions. "
                "Legal permission does not imply consent or custody.",
                [Field("account", "Your voluntary actual acquisition", paragraph=True)],
                acquire_permit,
            )
            await reply(interaction, form.text(), form)
            return
        if saved["type"] == "regrowth":

            async def read(current: discord.Interaction) -> None:
                await asyncio.to_thread(service.view, viewer_from_interaction(current), identity)

            history = MemoryHistory(
                interaction.user.id,
                "\n".join(
                    (
                        "**Your actual regrown Frame component**",
                        "Original missing feature: " + clean(source["original"]["name"]),
                        "New intact component: " + clean(source["component"]["name"]),
                        clean(source["component"]["description"]),
                        "Void: " + ("retained" if source["component"]["void"] else "no"),
                        "Original loss: " + clean(source["loss_event"]),
                        "Regrowth source: " + clean(source["event"]),
                        "Old physical links and occupants were not restored.",
                    )
                ),
                read,
            )
            await reply(interaction, history.text(), history)
            return
        if saved["type"] == "mouth":
            if source["ended_event"]:
                await reply(
                    interaction,
                    "Saved actual mouth hold: ended. Its independent Helplessness has ended.",
                )
                return

            async def end_hold(current: discord.Interaction, values: dict[str, Any]) -> str:
                await asyncio.to_thread(
                    service.release_mouth,
                    viewer_from_interaction(current),
                    str(current.id),
                    identity,
                    saved["revision"],
                    values["account"],
                )
                return (
                    "The actual body part has left the mouth; this source's Helplessness has ended."
                )

            form = NativeForm(
                interaction.user.id,
                "Actual mouth hold",
                "Record the real physical ending. Other Helplessness sources remain independent.",
                [Field("account", "Your actual physical ending account", paragraph=True)],
                end_hold,
            )
            await reply(interaction, form.text(), form)
            return
        if saved["type"] == "consumption":
            resolved = saved.get("resolution")
            if saved.get("pending_sprite"):
                await reply(
                    interaction,
                    "Saved Eat choice: "
                    + source["option"]
                    + ". Waiting for the Sprite's actual response.",
                )
                return
            if resolved and resolved["recipient"] != resolved["original_target"]:
                await reply(
                    interaction,
                    "A Sprite intercepted the damaging bite and paid with its actual Asset. "
                    "The intended target was spared."
                    + (
                        " Feeding was applied after the harm resolved."
                        if resolved["feeding_event"]
                        else " Feeding awaits the actual consequence."
                    ),
                )
                return
            if source["option"] != "swallow" or saved["vulnerable"] or source["escaped_event"]:
                await reply(
                    interaction,
                    "Saved actual Eat outcome: "
                    + source["option"]
                    + ("; escaped" if source["escaped_event"] else "")
                    + ".",
                )
                return

            async def rip_out(current: discord.Interaction, values: dict[str, Any]) -> str:
                await asyncio.to_thread(
                    service.rip_out,
                    viewer_from_interaction(current),
                    str(current.id),
                    identity,
                    saved["revision"],
                    values["account"],
                )
                return "The actual original nonvulnerable prisoner has ripped their way out."

            form = NativeForm(
                interaction.user.id,
                "Actual swallowed prisoner",
                "The original nonvulnerable prisoner owns the real escape; "
                "no invented movement or replacement body.",
                [Field("account", "Your actual rip-out account", paragraph=True)],
                rip_out,
            )
            await reply(interaction, form.text(), form)
            return
    menu = await asyncio.to_thread(service.menu, viewer, channel)
    operations = list(menu["plays"]) + [
        ("acquire", "Acquire an actual Requisition"),
        ("permit", "Choose a real Cannibal target"),
    ]

    async def select(current: discord.Interaction, values: dict[str, Any]) -> None:
        operation = values["operation"][0]
        if operation == "acquire":
            choices = [
                (x["id"], x["id"].removeprefix(rules.BASE).replace("-", " "))
                for x in menu["requisitions"]
                if not x["held"] and x["id"] != rules.FORMS
            ]

            async def purchase(response: discord.Interaction, selected: dict[str, Any]) -> str:
                await asyncio.to_thread(
                    service.purchase,
                    viewer_from_interaction(response),
                    str(response.id),
                    menu["source_sha256"],
                    selected["rule"][0],
                    selected["account"],
                )
                return "Your actual two-Permission Frame Requisition is saved."

            form = NativeForm(
                current.user.id,
                "CONSUME Requisition",
                "Confirm exactly two actual Permissions for your selected original Frame ability.",
                [
                    Field("rule", "Actual printed Requisition", tuple(choices)),
                    Field("account", "Your voluntary actual acquisition", paragraph=True),
                ],
                purchase,
            )
        elif operation == "permit":

            async def propose(response: discord.Interaction, selected: dict[str, Any]) -> str:
                target = next(
                    x for x in menu["legal_targets"] if x["token"] == selected["target"][0]
                )
                await asyncio.to_thread(
                    service.propose_permit,
                    viewer_from_interaction(response),
                    str(response.id),
                    channel,
                    menu["revision"],
                    ActorRef.model_validate(target["ref"]),
                    selected["account"],
                )
                return (
                    "Your actual chosen target awaits the original Handler's "
                    "factual hierarchy account."
                )

            form = NativeForm(
                current.user.id,
                "Cannibal target",
                "Choose the real person; payment occurs only after the actual hierarchy fact.",
                [
                    Field(
                        "target",
                        "Actual target",
                        tuple((x["token"], x["label"]) for x in menu["legal_targets"]),
                    ),
                    Field("account", "Your actual target choice", paragraph=True),
                ],
                propose,
            )
        else:
            fields = []
            if operation == "consume_eat":
                fields.append(
                    Field(
                        "target",
                        "Actual person you lunge at",
                        tuple((x["token"], x["label"]) for x in menu["targets"]),
                    )
                )
                fields.append(
                    Field(
                        "heat",
                        "Actual Heat to spend",
                        tuple(
                            (str(x), str(x))
                            for x in range(
                                (0 if menu["hunger"] == "Ravenous" else min(menu["heat"], 25)) + 1
                            )
                        ),
                    )
                )
            fields.append(
                Field(
                    "account",
                    "Your actual lunge" if operation == "consume_eat" else "Your actual impulse",
                    paragraph=True,
                )
            )

            async def begin(response: discord.Interaction, selected: dict[str, Any]) -> str:
                target = next(
                    (x for x in menu["targets"] if selected.get("target") == (x["token"],)), None
                )
                await asyncio.to_thread(
                    service.game.begin,
                    viewer_from_interaction(response),
                    str(response.id),
                    channel,
                    menu["sheet_revision"],
                    PlayInput(
                        play=operation,
                        target_actor=ActorRef.model_validate(target["ref"]) if target else None,
                        heat=int(selected.get("heat", ("0",))[0]),
                        context=selected["account"],
                        trigger_confirmed=True,
                    ),
                )
                return "Your genuine CONSUME Play is saved for its actual roll and owned choices."

            form = NativeForm(
                current.user.id,
                "CONSUME",
                "Use the actual source trigger, body and hunger. "
                "Feral uses its printed hunger basis.",
                fields,
                begin,
            )
        await reply(current, form.text(), form)

    form = NativeForm(
        interaction.user.id,
        "CONSUME — " + menu["hunger"],
        "Your original physical Frame's current hunger and actual source controls.",
        [Field("operation", "Actual source workflow", tuple(operations))],
        select,
    )
    await reply(interaction, form.text(), form)
